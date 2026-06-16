"""Mukthi Guru — eval runner.

Replays a YAML-defined eval set against a live /api/chat endpoint, grades each
response with the five-dimension LLM judge, and emits a JSON+Markdown report
with composite score, per-dimension scores, failure-mode breakdown, latency
distribution, cache hit rate, and total judge cost.

Designed for two use cases:
  1. **Local quality runs** — operator runs `python -m backend.evaluation.eval_runner
     --endpoint http://localhost:8000 --dataset mukthi_guru_v1` and gets a
     human-readable report.
  2. **CI regression gate** — runs with `--baseline baseline.json --strict`.
     Exits non-zero if any dimension regresses or composite drops below
     the configured floor.

Token / credit optimization (Phase A2 requirements):
  * Judge results are NEVER cached. Each grading run is fresh so we measure
    current quality, not historical answers.
  * Generator semantic cache is honoured by the system-under-test; the harness
    flags whether each response was a cache hit in the per-question result.
  * The judge calls run concurrently (bounded by `LLM_JUDGE_MAX_CONCURRENT`).
  * The runner supports `--max N` to grade only the first N questions for
    smoke runs — useful while iterating on rubrics.
  * The runner can be pointed at a *cheaper* judge model (e.g.
    `anthropic:claude-haiku-4-5-20251001`) via env override for cheap CI runs.
  * Each question's retrieved-context text is truncated to
    `LLM_JUDGE_CONTEXT_MAX_CHARS` (default 6000) to bound judge input tokens.

No hardcodings. The eval set, judge model, thresholds, weights, concurrency,
context budget, and endpoint are all settings or CLI args.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import statistics
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import yaml

# Allow `python -m backend.evaluation.eval_runner` from repo root.
HERE = Path(__file__).resolve().parent
BACKEND_ROOT = HERE.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from evaluation.llm_judge import CompositeScore, LLMJudge  # noqa: E402

logger = logging.getLogger("mukthi_guru.eval_runner")
logging.basicConfig(
    level=os.environ.get("EVAL_LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)


# ---------------------------------------------------------------------------
# Dataset loading
# ---------------------------------------------------------------------------


@dataclass
class EvalQuestion:
    id: str
    category: str
    language: str
    text: str
    expected_refusal: bool
    notes: str = ""


def load_dataset(dataset_path: Path) -> list[EvalQuestion]:
    """Load a YAML eval set. The YAML format is:

        version: 1
        questions:
          - id: founders_001
            category: Founders
            language: en
            text: "Who is Sri Krishnaji?"
            expected_refusal: false
          ...
    """
    with dataset_path.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    questions = []
    for entry in raw.get("questions", []):
        try:
            questions.append(
                EvalQuestion(
                    id=str(entry["id"]),
                    category=str(entry.get("category", "uncategorized")),
                    language=str(entry.get("language", "en")),
                    text=str(entry["text"]),
                    expected_refusal=bool(entry.get("expected_refusal", False)),
                    notes=str(entry.get("notes", "")),
                )
            )
        except KeyError as exc:
            logger.warning("Skipping malformed eval entry: missing %s", exc)
    return questions


# ---------------------------------------------------------------------------
# Endpoint client (talks to /api/chat)
# ---------------------------------------------------------------------------


@dataclass
class ChatResponse:
    final_answer: str
    citations: list[str]
    retrieved_context: str
    intent: str
    route_decision: str
    cache_hit: bool
    latency_ms: int


async def call_chat_endpoint(
    *,
    endpoint: str,
    question: str,
    session_id: str,
    auth_token: str | None,
    timeout_s: int,
) -> ChatResponse | None:
    """POST to /api/chat and return a normalized ChatResponse. Returns None
    on transport / 4xx / 5xx failure."""
    import aiohttp

    headers = {"Content-Type": "application/json"}
    if auth_token:
        headers["Authorization"] = f"Bearer {auth_token}"
    body = {
        "user_message": question,
        "session_id": session_id,
        "language": "en",
        "messages": [],
        "meditation_step": 0,
    }
    start = time.monotonic()
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{endpoint.rstrip('/')}/api/chat",
                json=body,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=timeout_s),
            ) as resp:
                if resp.status >= 400:
                    logger.warning(
                        "chat endpoint returned %s for question %s",
                        resp.status,
                        question[:80],
                    )
                    return None
                data = await resp.json()
    except (asyncio.TimeoutError, aiohttp.ClientError) as exc:
        logger.warning("chat endpoint call failed: %s", exc)
        return None

    latency_ms = data.get("latency_ms") or int((time.monotonic() - start) * 1000)
    return ChatResponse(
        final_answer=str(data.get("response", "")),
        citations=[str(c) for c in (data.get("citations") or [])],
        retrieved_context=str(data.get("retrieved_context") or data.get("context_used", "")),
        intent=str(data.get("intent", "")),
        route_decision=str(data.get("route_decision", "")),
        cache_hit=bool(data.get("cache_hit", False)),
        latency_ms=int(latency_ms),
    )


# ---------------------------------------------------------------------------
# Single-question evaluation
# ---------------------------------------------------------------------------


@dataclass
class QuestionResult:
    id: str
    category: str
    language: str
    question: str
    expected_refusal: bool
    response: ChatResponse | None
    composite: CompositeScore | None
    failed_reason: str | None = None


async def evaluate_one(
    *,
    question: EvalQuestion,
    endpoint: str,
    auth_token: str | None,
    judge: LLMJudge,
    session_id: str,
    request_timeout_s: int,
    context_max_chars: int,
) -> QuestionResult:
    response = await call_chat_endpoint(
        endpoint=endpoint,
        question=question.text,
        session_id=session_id,
        auth_token=auth_token,
        timeout_s=request_timeout_s,
    )
    if response is None:
        return QuestionResult(
            id=question.id,
            category=question.category,
            language=question.language,
            question=question.text,
            expected_refusal=question.expected_refusal,
            response=None,
            composite=None,
            failed_reason="chat_endpoint_unreachable",
        )

    context = response.retrieved_context[:context_max_chars]
    composite = await judge.score_response(
        query=question.text,
        answer=response.final_answer,
        retrieved_context=context,
        citations=response.citations,
        expected_refusal=question.expected_refusal,
        question_meta={
            "category": question.category,
            "language": question.language,
            "intent": response.intent,
            "route_decision": response.route_decision,
        },
    )
    return QuestionResult(
        id=question.id,
        category=question.category,
        language=question.language,
        question=question.text,
        expected_refusal=question.expected_refusal,
        response=response,
        composite=composite,
    )


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------


def aggregate(results: list[QuestionResult]) -> dict[str, Any]:
    completed = [r for r in results if r.composite is not None]
    failed = [r for r in results if r.composite is None]

    if not completed:
        return {
            "questions_total": len(results),
            "questions_graded": 0,
            "questions_failed": len(failed),
            "composite_mean": 0.0,
            "dimensions": {},
            "errors": [r.failed_reason for r in failed],
        }

    per_dim_scores: dict[str, list[float]] = {}
    per_dim_pass: dict[str, list[bool]] = {}
    failure_modes: dict[str, int] = {}
    composites = []
    weighted_means = []
    cache_hits = 0
    latencies_ms: list[int] = []
    judge_tokens = 0

    for r in completed:
        composites.append(r.composite.composite)
        weighted_means.append(r.composite.weighted_mean)
        judge_tokens += r.composite.total_judge_tokens
        if r.response and r.response.cache_hit:
            cache_hits += 1
        if r.response:
            latencies_ms.append(r.response.latency_ms)
        for name, ds in r.composite.dimensions.items():
            per_dim_scores.setdefault(name, []).append(ds.score)
            per_dim_pass.setdefault(name, []).append(ds.passes)
            if ds.failure_mode:
                failure_modes[ds.failure_mode] = failure_modes.get(ds.failure_mode, 0) + 1

    by_category: dict[str, list[float]] = {}
    for r in completed:
        by_category.setdefault(r.category, []).append(r.composite.composite)

    summary = {
        "questions_total": len(results),
        "questions_graded": len(completed),
        "questions_failed": len(failed),
        "composite_min": min(composites),
        "composite_mean": statistics.mean(composites),
        "composite_p50": statistics.median(composites),
        "weighted_mean": statistics.mean(weighted_means),
        "cache_hit_rate": cache_hits / max(len(completed), 1),
        "latency_p50_ms": statistics.median(latencies_ms) if latencies_ms else 0,
        "latency_p95_ms": _p95(latencies_ms),
        "judge_tokens_total": judge_tokens,
        "dimensions": {
            name: {
                "mean": statistics.mean(scores),
                "min": min(scores),
                "pass_rate": sum(per_dim_pass[name]) / max(len(per_dim_pass[name]), 1),
            }
            for name, scores in per_dim_scores.items()
        },
        "failure_modes": failure_modes,
        "category_composite_mean": {
            cat: statistics.mean(scores) for cat, scores in by_category.items()
        },
        "errors": [r.failed_reason for r in failed],
    }
    return summary


def _p95(values: list[int]) -> int:
    if not values:
        return 0
    s = sorted(values)
    idx = max(0, int(len(s) * 0.95) - 1)
    return s[idx]


# ---------------------------------------------------------------------------
# Regression gate
# ---------------------------------------------------------------------------


def regression_check(current: dict[str, Any], baseline: dict[str, Any], tolerance: float) -> tuple[bool, list[str]]:
    """Returns (passes, regressions_list).

    A baseline regression is any per-dimension mean dropping by more than
    `tolerance` (default 0.01 = 1 percentage point absolute), or composite_mean
    dropping by more than `tolerance`. The regression list is human-readable.
    """
    regressions: list[str] = []

    base_composite = float(baseline.get("composite_mean") or 0)
    cur_composite = float(current.get("composite_mean") or 0)
    if base_composite > 0 and (base_composite - cur_composite) > tolerance:
        regressions.append(
            f"composite_mean regressed: baseline={base_composite:.4f} -> current={cur_composite:.4f}"
        )

    base_dims = (baseline.get("dimensions") or {})
    cur_dims = (current.get("dimensions") or {})
    for name, base_metrics in base_dims.items():
        base_score = float((base_metrics or {}).get("mean") or 0)
        cur_score = float((cur_dims.get(name) or {}).get("mean") or 0)
        if base_score > 0 and (base_score - cur_score) > tolerance:
            regressions.append(
                f"dim {name!r} regressed: baseline={base_score:.4f} -> current={cur_score:.4f}"
            )
    return (not regressions, regressions)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def write_markdown_report(summary: dict[str, Any], path: Path) -> None:
    lines = ["# Mukthi Guru Eval Report", ""]
    lines.append(f"- **Questions graded**: {summary.get('questions_graded')} / {summary.get('questions_total')}")
    lines.append(f"- **Composite mean**: {summary.get('composite_mean'):.4f}")
    lines.append(f"- **Composite p50**: {summary.get('composite_p50'):.4f}")
    lines.append(f"- **Weighted mean**: {summary.get('weighted_mean'):.4f}")
    lines.append(f"- **Cache hit rate**: {summary.get('cache_hit_rate'):.1%}")
    lines.append(f"- **Endpoint latency p50/p95**: {summary.get('latency_p50_ms')}ms / {summary.get('latency_p95_ms')}ms")
    lines.append(f"- **Judge tokens total**: {summary.get('judge_tokens_total')}")
    lines.append("")
    lines.append("## Per-dimension scores")
    lines.append("| Dimension | Mean | Min | Pass rate |")
    lines.append("|---|---|---|---|")
    for name, m in (summary.get("dimensions") or {}).items():
        lines.append(f"| {name} | {m['mean']:.4f} | {m['min']:.4f} | {m['pass_rate']:.1%} |")
    lines.append("")
    if summary.get("failure_modes"):
        lines.append("## Failure mode tally")
        for mode, count in sorted(summary["failure_modes"].items(), key=lambda kv: -kv[1]):
            lines.append(f"- {mode}: {count}")
        lines.append("")
    if summary.get("category_composite_mean"):
        lines.append("## Per-category composite mean")
        for cat, score in sorted(summary["category_composite_mean"].items(), key=lambda kv: kv[1]):
            lines.append(f"- {cat}: {score:.4f}")
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Mukthi Guru eval runner.")
    parser.add_argument("--endpoint", default=os.environ.get("EVAL_ENDPOINT", "http://localhost:8000"))
    parser.add_argument("--auth-token", default=os.environ.get("EVAL_AUTH_TOKEN"))
    parser.add_argument(
        "--dataset",
        default=os.environ.get("EVAL_DATASET", "mukthi_guru_v1"),
        help="Dataset filename (without .yaml extension) in evaluation/datasets/.",
    )
    parser.add_argument("--max", type=int, default=None, help="Grade only the first N questions.")
    parser.add_argument(
        "--max-concurrent-requests",
        type=int,
        default=int(os.environ.get("EVAL_MAX_CONCURRENT_REQUESTS", "4")),
    )
    parser.add_argument(
        "--request-timeout",
        type=int,
        default=int(os.environ.get("EVAL_REQUEST_TIMEOUT", "180")),
    )
    parser.add_argument(
        "--context-max-chars",
        type=int,
        default=int(os.environ.get("LLM_JUDGE_CONTEXT_MAX_CHARS", "6000")),
    )
    parser.add_argument("--baseline", default=None, help="Path to a previous report JSON for regression gating.")
    parser.add_argument("--tolerance", type=float, default=0.01)
    parser.add_argument("--strict", action="store_true", help="Exit non-zero on any regression.")
    parser.add_argument(
        "--out-json",
        default=os.environ.get("EVAL_OUT_JSON", "results/eval_report.json"),
    )
    parser.add_argument(
        "--out-md",
        default=os.environ.get("EVAL_OUT_MD", "results/eval_report.md"),
    )
    args = parser.parse_args(argv)

    dataset_path = HERE / "datasets" / f"{args.dataset}.yaml"
    if not dataset_path.is_file():
        logger.error("Dataset not found: %s", dataset_path)
        return 2

    questions = load_dataset(dataset_path)
    if args.max is not None:
        questions = questions[: args.max]
    logger.info("Loaded %d eval questions from %s", len(questions), dataset_path)

    judge = LLMJudge.from_settings()
    sem = asyncio.Semaphore(args.max_concurrent_requests)
    session_id_prefix = f"eval-{int(time.time())}"

    async def _run_one(q: EvalQuestion, idx: int) -> QuestionResult:
        async with sem:
            return await evaluate_one(
                question=q,
                endpoint=args.endpoint,
                auth_token=args.auth_token,
                judge=judge,
                session_id=f"{session_id_prefix}-{idx}",
                request_timeout_s=args.request_timeout,
                context_max_chars=args.context_max_chars,
            )

    results = asyncio.run(asyncio.gather(*[_run_one(q, i) for i, q in enumerate(questions)]))

    summary = aggregate(results)
    out_json_path = Path(args.out_json)
    out_md_path = Path(args.out_md)
    out_json_path.parent.mkdir(parents=True, exist_ok=True)
    out_md_path.parent.mkdir(parents=True, exist_ok=True)

    with out_json_path.open("w", encoding="utf-8") as f:
        json.dump({"summary": summary, "per_question": [_serialise(r) for r in results]}, f, indent=2)
    write_markdown_report(summary, out_md_path)
    logger.info("Wrote report to %s and %s", out_json_path, out_md_path)

    exit_code = 0
    if args.baseline:
        with open(args.baseline, "r", encoding="utf-8") as f:
            baseline = json.load(f).get("summary", {})
        passes, regressions = regression_check(summary, baseline, args.tolerance)
        if regressions:
            for r in regressions:
                logger.warning("REGRESSION: %s", r)
        if not passes and args.strict:
            exit_code = 1

    print(
        f"composite_mean={summary.get('composite_mean', 0):.4f}  "
        f"weighted_mean={summary.get('weighted_mean', 0):.4f}  "
        f"graded={summary.get('questions_graded')}/{summary.get('questions_total')}  "
        f"cache_hit={summary.get('cache_hit_rate', 0):.1%}"
    )
    return exit_code


def _serialise(r: QuestionResult) -> dict[str, Any]:
    """Trim a QuestionResult to JSON-safe dicts (composite has nested dataclasses)."""
    out: dict[str, Any] = {
        "id": r.id,
        "category": r.category,
        "language": r.language,
        "question": r.question,
        "expected_refusal": r.expected_refusal,
        "failed_reason": r.failed_reason,
    }
    if r.response is not None:
        out["response"] = asdict(r.response)
    if r.composite is not None:
        out["composite"] = {
            "composite": r.composite.composite,
            "weighted_mean": r.composite.weighted_mean,
            "all_pass": r.composite.all_pass,
            "judge_tokens": r.composite.total_judge_tokens,
            "dimensions": {
                name: asdict(ds) for name, ds in r.composite.dimensions.items()
            },
        }
    return out


if __name__ == "__main__":
    sys.exit(main())
