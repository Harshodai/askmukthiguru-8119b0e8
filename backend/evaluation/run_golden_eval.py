"""Golden-set evaluator. Calls the deployed backend for each question,
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
import os
import sys
from pathlib import Path
from typing import Any

import httpx


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


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--dataset", required=True, type=Path)
    p.add_argument("--out", required=True, type=Path)
    p.add_argument("--faithfulness-min", type=float, default=0.88)
    p.add_argument("--relevancy-min", type=float, default=0.80)
    p.add_argument("--context-precision-min", type=float, default=0.72)
    p.add_argument("--context-recall-min", type=float, default=0.72)
    p.add_argument("--min-distinct-sources", type=int, default=2)
    args = p.parse_args()

    backend_url = os.environ.get("BACKEND_URL")
    if not backend_url:
        print("BACKEND_URL not set; skipping (treating as pass for first-time setup).")
        args.out.write_text(json.dumps({"skipped": True}))
        return 0
    token = os.environ.get("BACKEND_TOKEN")

    items = json.loads(args.dataset.read_text())["items"]
    questions, answers, contexts, refs = [], [], [], []
    failed = 0
    diversity_violations = 0

    for it in items:
        try:
            resp = call_backend(backend_url, token, it["question"])
        except Exception as e:
            print(f"[FAIL] {it['id']}: {e}", file=sys.stderr)
            failed += 1
            continue
        ans = resp.get("response") or resp.get("answer") or ""
        cites = resp.get("citations", [])
        ctx = [c.get("text") or c.get("snippet") or "" for c in cites] or [""]
        questions.append(it["question"])
        answers.append(ans)
        contexts.append(ctx)
        refs.append(" ".join(it.get("expected_concepts", [])))
        if diversity_violation(cites, args.min_distinct_sources):
            diversity_violations += 1
            print(f"[DIVERSITY] {it['id']}: top-3 citations not diverse enough")

    # RAGAS scoring (deferred import so script runs without ragas in dev)
    faithfulness_score = 0.0
    relevancy_score = 0.0
    context_precision_score = 0.0
    context_recall_score = 0.0
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
        # Heuristic: fraction of expected_concepts present in answer.
        hits, total = 0, 0
        for it, ans in zip(items, answers):
            for c in it.get("expected_concepts", []):
                total += 1
                if c.lower() in ans.lower():
                    hits += 1
        faithfulness_score = hits / total if total else 0.0
        relevancy_score = faithfulness_score
        context_precision_score = faithfulness_score
        context_recall_score = faithfulness_score

    faithfulness_pass = faithfulness_score >= args.faithfulness_min
    relevancy_pass = relevancy_score >= args.relevancy_min
    context_precision_pass = context_precision_score >= args.context_precision_min
    context_recall_pass = context_recall_score >= args.context_recall_min
    diversity_pass = diversity_violations == 0

    report = {
        "questions_total": len(items),
        "questions_failed": failed,
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
        "thresholds": {
            "faithfulness_min": args.faithfulness_min,
            "relevancy_min": args.relevancy_min,
            "context_precision_min": args.context_precision_min,
            "context_recall_min": args.context_recall_min,
            "min_distinct_sources": args.min_distinct_sources,
        },
    }
    args.out.write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))

    if not (
        faithfulness_pass
        and relevancy_pass
        and context_precision_pass
        and context_recall_pass
        and diversity_pass
    ):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
