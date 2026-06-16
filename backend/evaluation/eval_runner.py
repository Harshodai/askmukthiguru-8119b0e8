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

from evaluation.llm_judge import CompositeScore, LLMJudge, DimensionScore, _safe_json_parse  # noqa: E402

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


async def run_batched_evaluation(
    *,
    questions: list[EvalQuestion],
    endpoint: str,
    auth_token: str | None,
    judge: LLMJudge,
    session_id_prefix: str,
    request_timeout_s: int,
    context_max_chars: int,
    max_concurrent: int,
) -> list[QuestionResult]:
    import aiohttp
    from app.config import settings

    # Step 1: call all chat endpoints concurrently
    logger.info("Calling chat endpoint for all %d questions concurrently...", len(questions))
    sem = asyncio.Semaphore(max_concurrent)

    async def _call_chat(q: EvalQuestion, idx: int) -> tuple[EvalQuestion, ChatResponse | None]:
        async with sem:
            resp = await call_chat_endpoint(
                endpoint=endpoint,
                question=q.text,
                session_id=f"{session_id_prefix}-{idx}",
                auth_token=auth_token,
                timeout_s=request_timeout_s,
            )
            return q, resp

    chat_results = await asyncio.gather(*[_call_chat(q, i) for i, q in enumerate(questions)])

    # Separate successful chat responses from failed ones
    successful_chats: list[tuple[EvalQuestion, ChatResponse]] = []
    final_results: dict[str, QuestionResult] = {}

    for q, resp in chat_results:
        if resp is None:
            final_results[q.id] = QuestionResult(
                id=q.id,
                category=q.category,
                language=q.language,
                question=q.text,
                expected_refusal=q.expected_refusal,
                response=None,
                composite=None,
                failed_reason="chat_endpoint_unreachable",
            )
        else:
            successful_chats.append((q, resp))

    if not successful_chats:
        logger.warning("All chat endpoint calls failed. Skipping judge batch.")
        return [final_results.get(q.id) or QuestionResult(
            id=q.id, category=q.category, language=q.language, question=q.text,
            expected_refusal=q.expected_refusal, response=None, composite=None,
            failed_reason="chat_endpoint_unreachable"
        ) for q in questions]

    if judge.client.is_stub:
        logger.info("Judge client is stub (no API key). Simulating passing scores.")
        for q, resp in successful_chats:
            dim_scores = {}
            for dim_name in LLMJudge.DEFAULT_DIMENSIONS:
                rubric = judge.rubrics.get(dim_name, {})
                threshold = float(rubric.get("pass_threshold", 0.8))
                dim_scores[dim_name] = DimensionScore(
                    name=dim_name,
                    score=1.0,
                    pass_threshold=threshold,
                    rationale="stub: no judge configured",
                    failure_mode=None,
                    judge_latency_ms=0,
                    judge_tokens_in=0,
                    judge_tokens_out=0,
                )
            composite_score = CompositeScore(
                query=q.text,
                composite=1.0,
                weighted_mean=1.0,
                dimensions=dim_scores,
                all_pass=True,
                total_judge_tokens=0,
                total_judge_latency_ms=0,
            )
            final_results[q.id] = QuestionResult(
                id=q.id,
                category=q.category,
                language=q.language,
                question=q.text,
                expected_refusal=q.expected_refusal,
                response=resp,
                composite=composite_score,
            )
        return [final_results[q.id] for q in questions]

    # Step 2: Compile judge batch requests
    logger.info("Compiling judge batch requests...")
    # Verify that model is anthropic
    provider, model_name = judge.config.provider_model.split(":", 1)
    if provider.strip().lower() != "anthropic":
        raise ValueError(
            f"Message Batches API is only supported for 'anthropic' provider models, got {judge.config.provider_model}"
        )

    api_key = (
        getattr(settings, "anthropic_api_key", "")
        or getattr(settings, "emergent_llm_key", "")
    )
    if not api_key:
        raise ValueError("No API key available for Anthropic Message Batches API.")

    requests_payload = []

    for q, resp in successful_chats:
        context = resp.retrieved_context[:context_max_chars]
        meta = {
            "category": q.category,
            "language": q.language,
            "intent": resp.intent,
            "route_decision": resp.route_decision,
        }
        for dim_name in LLMJudge.DEFAULT_DIMENSIONS:
            if dim_name not in judge.rubrics:
                continue
            rubric = judge.rubrics[dim_name]
            system_prompt = rubric.get("system_prompt", "")
            user_template = rubric.get("user_template", "")

            rendered_user_prompt = (
                user_template
                .replace("{{query}}", q.text)
                .replace("{{answer}}", resp.final_answer or "")
                .replace("{{context}}", context or "")
                .replace("{{citations}}", "\n".join(resp.citations))
                .replace("{{expected_refusal}}", "true" if q.expected_refusal else "false")
                .replace("{{meta}}", json.dumps(meta, ensure_ascii=False))
            )

            custom_id = f"{q.id}:{dim_name}"

            requests_payload.append({
                "custom_id": custom_id,
                "params": {
                    "model": model_name.strip(),
                    "max_tokens": 1024,
                    "system": [
                        {
                            "type": "text",
                            "text": system_prompt,
                            "cache_control": {"type": "ephemeral"}
                        }
                    ],
                    "messages": [
                        {
                            "role": "user",
                            "content": rendered_user_prompt
                        }
                    ]
                }
            })

    # Step 3: POST batch
    logger.info("Submitting batch of %d requests to Anthropic...", len(requests_payload))
    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
        "anthropic-beta": "prompt-caching-2024-07-31",
    }

    batch_url = "https://api.anthropic.com/v1/messages/batches"
    async with aiohttp.ClientSession() as session:
        async with session.post(batch_url, json={"requests": requests_payload}, headers=headers) as post_resp:
            if post_resp.status >= 400:
                err_text = await post_resp.text()
                raise RuntimeError(f"Anthropic batch submission failed with {post_resp.status}: {err_text}")
            batch_data = await post_resp.json()

        batch_id = batch_data["id"]
        logger.info("Batch submitted successfully. Batch ID: %s. Polling status...", batch_id)

        # Step 4: Poll status
        poll_url = f"{batch_url}/{batch_id}"
        poll_interval = 15
        while True:
            await asyncio.sleep(poll_interval)
            async with session.get(poll_url, headers=headers) as status_resp:
                if status_resp.status >= 400:
                    logger.warning("Failed to poll batch status: %s", status_resp.status)
                    continue
                status_data = await status_resp.json()

            status = status_data.get("processing_status")
            counts = status_data.get("request_counts", {})
            logger.info(
                "Batch status: %s (processing=%d, succeeded=%d, errored=%d)",
                status,
                counts.get("processing", 0),
                counts.get("succeeded", 0),
                counts.get("errored", 0),
            )

            if status == "ended":
                results_url = status_data.get("results_url")
                break

        if not results_url:
            raise RuntimeError("Batch ended but no results_url was provided.")

        # Step 5: Download results
        logger.info("Downloading batch results...")
        async with session.get(results_url, headers=headers) as results_resp:
            if results_resp.status >= 400:
                raise RuntimeError(f"Failed to download batch results: {results_resp.status}")
            results_text = await results_resp.text()

    # Step 6: Parse results and reconstruct scores
    logger.info("Parsing results and reconstructing scores...")
    batch_results: dict[str, dict] = {}
    for line in results_text.splitlines():
        if not line.strip():
            continue
        try:
            item = json.loads(line)
            custom_id = item["custom_id"]
            batch_results[custom_id] = item["result"]
        except Exception as e:
            logger.warning("Failed to parse JSONL line: %s", e)

    # Group results by question ID
    question_dim_scores_map: dict[str, dict[str, DimensionScore]] = {}

    for q, resp in successful_chats:
        question_dim_scores_map[q.id] = {}
        for dim_name in LLMJudge.DEFAULT_DIMENSIONS:
            if dim_name not in judge.rubrics:
                continue
            rubric = judge.rubrics[dim_name]
            threshold = float(rubric.get("pass_threshold", 0.8))
            custom_id = f"{q.id}:{dim_name}"

            res = batch_results.get(custom_id)
            score_val = 0.0
            rationale = "Result missing from batch output"
            failure_mode = "batch_missing"
            tokens_in = 0
            tokens_out = 0

            if res:
                result_type = res.get("type")
                if result_type == "succeeded":
                    msg = res.get("message") or {}
                    content_list = msg.get("content") or []
                    text = content_list[0].get("text", "") if content_list else ""
                    parsed_res = _safe_json_parse(text)
                    usage = msg.get("usage") or {}
                    tokens_in = usage.get("input_tokens", 0)
                    tokens_out = usage.get("output_tokens", 0)

                    score_raw = parsed_res.get("score")
                    try:
                        score_val = float(score_raw)
                    except (TypeError, ValueError):
                        score_val = 0.0
                    score_val = max(0.0, min(1.0, score_val))
                    rationale = str(parsed_res.get("rationale", ""))[:600]
                    failure_mode = parsed_res.get("failure_mode") if score_val < threshold else None
                elif result_type == "errored":
                    err = res.get("error") or {}
                    rationale = f"Batch API error: {err.get('message', 'unknown')}"
                    failure_mode = "batch_api_error"

            question_dim_scores_map[q.id][dim_name] = DimensionScore(
                name=dim_name,
                score=score_val,
                pass_threshold=threshold,
                rationale=rationale,
                failure_mode=failure_mode,
                judge_latency_ms=0,
                judge_tokens_in=tokens_in,
                judge_tokens_out=tokens_out,
            )

    # Assemble CompositeScore and QuestionResult for each question
    for q, resp in successful_chats:
        q_scores = question_dim_scores_map[q.id]
        scores_list = [q_scores[d] for d in LLMJudge.DEFAULT_DIMENSIONS if d in q_scores]

        composite = min(s.score for s in scores_list) if scores_list else 0.0
        weights = judge.config.default_weights
        total_weight = sum(weights.get(name, 1.0) for name in q_scores) or 1.0
        weighted_mean = (
            sum(q_scores[name].score * weights.get(name, 1.0) for name in q_scores)
            / total_weight
        )
        all_pass = all(s.passes for s in scores_list)
        tokens = sum((s.judge_tokens_in or 0) + (s.judge_tokens_out or 0) for s in scores_list)

        composite_score = CompositeScore(
            query=q.text,
            composite=float(composite),
            weighted_mean=float(weighted_mean),
            dimensions=q_scores,
            all_pass=all_pass,
            total_judge_tokens=tokens,
            total_judge_latency_ms=0,
        )

        final_results[q.id] = QuestionResult(
            id=q.id,
            category=q.category,
            language=q.language,
            question=q.text,
            expected_refusal=q.expected_refusal,
            response=resp,
            composite=composite_score,
        )

    return [final_results[q.id] for q in questions]


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
    parser.add_argument(
        "--use-batch",
        action="store_true",
        help="Use Anthropic Message Batches API for evaluation judge queries.",
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

    if args.use_batch:
        results = asyncio.run(run_batched_evaluation(
            questions=questions,
            endpoint=args.endpoint,
            auth_token=args.auth_token,
            judge=judge,
            session_id_prefix=session_id_prefix,
            request_timeout_s=args.request_timeout,
            context_max_chars=args.context_max_chars,
            max_concurrent=args.max_concurrent_requests,
        ))
    else:
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
