"""Golden-set evaluator.

NOTE (2026-09-16): evaluation/bench.py is the consolidated golden-bank
runner (one CLI, one schema). This script stays for its RAGAS-library
faithfulness/answer_relevancy/context_precision/context_recall metrics,
which bench.py does not compute.

Calls the deployed backend for each question,
runs RAGAS faithfulness, answer_relevancy, context_precision, and
context_recall, and enforces an answer-source diversity guard. Exits
non-zero when any threshold fails so the GitHub Actions gate blocks the
deploy.

Usage:
  python backend/evaluation/run_golden_eval.py \
    --dataset backend/evaluation/golden_dataset.json \
    --out eval_report.json \
    --faithfulness-min 0.88 \
    --relevancy-min 0.80 \
    --context-precision-min 0.72 \
    --context-recall-min 0.72 \
    --min-distinct-sources 2
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import httpx

BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.config import settings  # noqa: E402


def call_backend(url: str, token: str | None, question: str) -> dict[str, Any]:
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    payload = {"messages": [], "user_message": question}
    r = httpx.post(f"{url.rstrip('/')}/api/chat", json=payload, headers=headers, timeout=120)
    r.raise_for_status()
    return r.json()


def diversity_violation(citations: list[dict], min_distinct: int) -> bool:
    if not citations:
        return False
    top = citations[:3]
    sources = {c.get("source_id") or c.get("video_id") or c.get("url") for c in top}
    return len([s for s in sources if s]) < min_distinct


def score_golden_eval(
    items: list[dict[str, Any]],
    answers: list[str],
    contexts: list[list[str]] | None = None,
    refs: list[str] | None = None,
    questions: list[str] | None = None,
    args: argparse.Namespace | None = None,
    faithfulness_min: float = 0.88,
    relevancy_min: float = 0.80,
    context_precision_min: float = 0.72,
    context_recall_min: float = 0.72,
    min_distinct_sources: int = 2,
    diversity_violations: int = 0,
    failed: int = 0,
) -> dict[str, Any]:
    if args is not None:
        faithfulness_min = getattr(args, "faithfulness_min", faithfulness_min)
        relevancy_min = getattr(args, "relevancy_min", relevancy_min)
        context_precision_min = getattr(args, "context_precision_min", context_precision_min)
        context_recall_min = getattr(args, "context_recall_min", context_recall_min)
        min_distinct_sources = getattr(args, "min_distinct_sources", min_distinct_sources)

    contexts = contexts or [[""] for _ in answers]
    refs = refs or ["" for _ in answers]
    questions = questions or ["" for _ in answers]

    # RAGAS scoring (deferred import so script runs without ragas in dev)
    scoring_method = "ragas"
    faithfulness_score: float | None = None
    relevancy_score: float | None = None
    context_precision_score: float | None = None
    context_recall_score: float | None = None
    concept_overlap_score: float | None = None
    try:
        from datasets import Dataset  # type: ignore
        from ragas import evaluate  # type: ignore
        from ragas.metrics import (
            answer_relevancy,
            context_precision,
            context_recall,
            faithfulness,
        )  # type: ignore

        ds = Dataset.from_dict(
            {
                "question": questions,
                "answer": answers,
                "contexts": contexts,
                "reference": refs,
            }
        )
        result = evaluate(
            ds, metrics=[faithfulness, answer_relevancy, context_precision, context_recall]
        )
        faithfulness_score = float(result["faithfulness"])
        relevancy_score = float(result["answer_relevancy"])
        context_precision_score = float(result["context_precision"])
        context_recall_score = float(result["context_recall"])
    except Exception as e:
        print(f"[WARN] RAGAS unavailable ({e}); falling back to heuristic concept-overlap.")
        # Heuristic: fraction of must_mention concepts present in answer,
        # penalised when reject_if tokens are present.
        scoring_method = "concept_overlap_fallback"
        hits, total = 0, 0
        for it, ans in zip(items, answers, strict=False):
            must = it.get("must_mention", [])
            reject = it.get("reject_if", [])
            if it.get("expected_intent") == "REFUSE":
                total += 1
                if must and not any(r.lower() in ans.lower() for r in reject):
                    if any(c.lower() in ans.lower() for c in must):
                        hits += 1
            else:
                for c in must:
                    total += 1
                    if c.lower() in ans.lower():
                        hits += 1
        concept_overlap_score = hits / total if total else 0.0
        faithfulness_score = None
        relevancy_score = None
        context_precision_score = None
        context_recall_score = None

    if scoring_method == "ragas":
        faithfulness_pass: bool | str = (
            faithfulness_score >= faithfulness_min
            if faithfulness_score is not None
            else False
        )
        relevancy_pass: bool | str = (
            relevancy_score >= relevancy_min
            if relevancy_score is not None
            else False
        )
        context_precision_pass: bool | str = (
            context_precision_score >= context_precision_min
            if context_precision_score is not None
            else False
        )
        context_recall_pass: bool | str = (
            context_recall_score >= context_recall_min
            if context_recall_score is not None
            else False
        )
        concept_overlap_pass: bool | None = None
        judge_metrics_pass = (
            faithfulness_pass
            and relevancy_pass
            and context_precision_pass
            and context_recall_pass
        )
    else:
        faithfulness_pass = "unmeasured"
        relevancy_pass = "unmeasured"
        context_precision_pass = "unmeasured"
        context_recall_pass = "unmeasured"
        concept_overlap_pass = concept_overlap_score >= faithfulness_min
        judge_metrics_pass = concept_overlap_pass

    diversity_pass = diversity_violations == 0

    report = {
        "questions_total": len(items),
        "questions_failed": failed,
        "scoring_method": scoring_method,
        "note": (
            None
            if scoring_method == "ragas"
            else (
                "concept_overlap_fallback: RAGAS is uninstalled or judge LLM API key is not configured in CI. "
                "Faithfulness, answer_relevancy, context_precision, and context_recall are unmeasured (None), "
                "and only concept_overlap_score (% of must_mention concepts present without reject_if tokens) "
                "is evaluated."
            )
        ),
        "concept_overlap_score": concept_overlap_score if scoring_method != "ragas" else None,
        "concept_overlap_pass": concept_overlap_pass,
        "faithfulness": faithfulness_score,
        "answer_relevancy": relevancy_score,
        "context_precision": context_precision_score,
        "context_recall": context_recall_score,
        "diversity_violations": diversity_violations,
        "faithfulness_pass": faithfulness_pass,
        "relevancy_pass": relevancy_pass,
        "context_precision_pass": context_precision_pass,
        "context_recall_pass": context_recall_pass,
        "diversity_pass": diversity_pass,
        "judge_metrics_pass": judge_metrics_pass,
        "thresholds": {
            "faithfulness_min": faithfulness_min,
            "relevancy_min": relevancy_min,
            "context_precision_min": context_precision_min,
            "context_recall_min": context_recall_min,
            "min_distinct_sources": min_distinct_sources,
        },
    }
    return report


# Aliases for convenience / alternative imports
compute_eval_report = score_golden_eval
evaluate_golden_set = score_golden_eval


def main(cli_args: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--dataset", required=True, type=Path)
    p.add_argument("--out", required=True, type=Path)
    p.add_argument("--faithfulness-min", type=float, default=0.88)
    p.add_argument("--relevancy-min", type=float, default=0.80)
    p.add_argument("--context-precision-min", type=float, default=0.72)
    p.add_argument("--context-recall-min", type=float, default=0.72)
    p.add_argument("--min-distinct-sources", type=int, default=2)
    args = p.parse_args(cli_args)

    backend_url = settings.backend_url
    if not backend_url:
        print("BACKEND_URL not set, eval skipped", file=sys.stderr)
        return 1
    token = settings.backend_token

    items = json.loads(args.dataset.read_text())["items"]
    questions, answers, contexts, refs = [], [], [], []
    failed = 0
    diversity_violations = 0

    for it in items:
        question = it.get("question") or it.get("query")
        if not question:
            print(
                f"[FAIL] {it.get('id', '<unknown>')}: item has neither question nor query",
                file=sys.stderr,
            )
            failed += 1
            continue
        success = True
        try:
            resp = call_backend(backend_url, token, question)
        except Exception as e:
            print(f"[FAIL] {it['id']}: {e}", file=sys.stderr)
            failed += 1
            success = False

        if success:
            ans = resp.get("response") or resp.get("answer") or ""
            cites = resp.get("citations", [])
            ctx = [c.get("text") or c.get("snippet") or "" for c in cites] or [""]
        else:
            ans = ""
            cites = []
            ctx = [""]

        questions.append(question)
        answers.append(ans)
        contexts.append(ctx)
        must = it.get("must_mention", [])
        refs.append("The expected answer must cover: " + ", ".join(must) if must else question)
        if success and diversity_violation(cites, args.min_distinct_sources):
            diversity_violations += 1
            print(f"[DIVERSITY] {it['id']}: top-3 citations not diverse enough")

    report = score_golden_eval(
        items=items,
        answers=answers,
        contexts=contexts,
        refs=refs,
        questions=questions,
        args=args,
        diversity_violations=diversity_violations,
        failed=failed,
    )
    args.out.write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))

    judge_metrics_pass = report["judge_metrics_pass"]
    diversity_pass = report["diversity_pass"]

    if not (
        judge_metrics_pass
        and diversity_pass
        and failed == 0
    ):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
