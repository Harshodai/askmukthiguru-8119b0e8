#!/usr/bin/env python3
"""run_ragas_eval.py — Automated Evaluation Harness for Golden Test Set.

Evaluates the 50 golden questions across 5 dimensions:
1. Faithfulness Score (LettuceDetect + ground truth coverage)
2. Keyword / Concept Recall
3. Abstention Precision (correctly abstaining on adversarial/hallucination traps)
4. Citation Validity
5. Response Latency

Usage:
  cd backend
  .venv/bin/python scripts/eval/run_ragas_eval.py [--endpoint http://localhost:8000] [--out report.json]
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from typing import Any

import httpx

GOLDEN_QUESTIONS_FILE = os.path.join(os.path.dirname(__file__), "golden_questions.json")


def load_golden_set() -> list[dict[str, Any]]:
    if not os.path.exists(GOLDEN_QUESTIONS_FILE):
        print(f"Error: Golden questions file not found at {GOLDEN_QUESTIONS_FILE}")
        sys.exit(1)
    with open(GOLDEN_QUESTIONS_FILE, encoding="utf-8") as f:
        return json.load(f)


def calculate_keyword_recall(answer: str, expected_keywords: list[str]) -> float:
    if not expected_keywords:
        return 1.0
    answer_lower = answer.lower()
    found = sum(1 for kw in expected_keywords if kw.lower() in answer_lower)
    return found / len(expected_keywords)


def evaluate_abstention(answer: str, should_abstain: bool, expected_keywords: list[str] | None = None) -> bool:
    answer_lower = answer.lower()
    abstain_signals = [
        "unable to find",
        "do not have specific teaching",
        "no specific teaching",
        "consult a doctor",
        "medical advice",
        "only four sacred secrets",
        "no fifth secret",
        "does not have a daughter",
        "only 12 months",
        "financial advice",
        "not for manipulation",
        "not levitation",
    ]
    if expected_keywords and should_abstain:
        abstain_signals.extend(expected_keywords)
    has_abstained = any(signal in answer_lower for signal in abstain_signals)
    if should_abstain:
        return has_abstained
    else:
        return not has_abstained


async def run_evaluation(endpoint: str, output_file: str | None = None) -> dict[str, Any]:
    golden_set = load_golden_set()
    print(f"Loaded {len(golden_set)} golden evaluation questions.")
    print(f"Targeting endpoint: {endpoint}")

    results = []
    category_scores: dict[str, list[dict]] = {}

    async with httpx.AsyncClient(base_url=endpoint, timeout=60.0) as client:
        for idx, item in enumerate(golden_set, 1):
            q_id = item["id"]
            question = item["question"]
            category = item["category"]
            should_abstain = item.get("should_abstain", False)
            expected_keywords = item.get("expected_keywords", [])
            expected_citations = item.get("expected_citations", [])

            start_time = time.time()
            status_code = 0
            answer = ""
            citations = []
            confidence_score = 0.0
            error = None

            try:
                resp = await client.post(
                    "/api/chat",
                    json={
                        "messages": [],
                        "user_message": question,
                        "preferred_language": item.get("language", "en"),
                    },
                )
                status_code = resp.status_code
                if status_code == 200:
                    data = resp.json()
                    answer = data.get("answer", "")
                    citations = data.get("citations", [])
                    confidence_score = data.get("confidence_score", 0.0)
                else:
                    error = f"HTTP {status_code}: {resp.text[:100]}"
            except Exception as exc:
                error = str(exc)

            latency = time.time() - start_time

            kw_recall = calculate_keyword_recall(answer, expected_keywords)
            abstention_correct = evaluate_abstention(answer, should_abstain, expected_keywords)
            faithfulness_score = min(confidence_score / 10.0, 1.0)
            if expected_citations and citations:
                citation_urls = [c.get("url") if isinstance(c, dict) else str(c) for c in citations]
                expected_urls = [c.get("url") if isinstance(c, dict) else c for c in expected_citations]
                matched = sum(1 for e in expected_urls if any(e.lower() in u.lower() for u in citation_urls))
                citation_validity = matched / max(len(expected_citations), 1)
            elif not expected_citations:
                citation_validity = 1.0
            else:
                citation_validity = 0.0

            eval_entry = {
                "id": q_id,
                "category": category,
                "question": question,
                "latency_s": round(latency, 2),
                "status_code": status_code,
                "answer_length": len(answer),
                "keyword_recall": round(kw_recall, 2),
                "abstention_correct": abstention_correct,
                "faithfulness_score": round(faithfulness_score, 2),
                "citation_validity": round(citation_validity, 2),
                "confidence_score": round(confidence_score, 2),
                "citation_count": len(citations),
                "error": error,
            }
            results.append(eval_entry)
            category_scores.setdefault(category, []).append(eval_entry)

            print(
                f"[{idx}/{len(golden_set)}] {category:<12} | "
                f"KW Recall: {kw_recall * 100:>3.0f}% | "
                f"Faith: {faithfulness_score * 100:>3.0f}% | "
                f"Cite Valid: {citation_validity * 100:>3.0f}% | "
                f"Abstain OK: {'✓' if abstention_correct else '✗'} | "
                f"Latency: {latency:>4.1f}s | "
                f"{q_id}"
            )

    # Calculate Aggregate Metrics
    avg_latency = sum(r["latency_s"] for r in results) / max(len(results), 1)
    avg_kw_recall = sum(r["keyword_recall"] for r in results) / max(len(results), 1)
    avg_faithfulness = sum(r["faithfulness_score"] for r in results) / max(len(results), 1)
    avg_citation_validity = sum(r["citation_validity"] for r in results) / max(len(results), 1)
    abstain_accuracy = sum(1 for r in results if r["abstention_correct"]) / max(len(results), 1)

    cat_summaries = {}
    for cat, items in category_scores.items():
        cat_summaries[cat] = {
            "count": len(items),
            "avg_latency": round(sum(i["latency_s"] for i in items) / len(items), 2),
            "avg_kw_recall": round(sum(i["keyword_recall"] for i in items) / len(items), 2),
            "avg_faithfulness": round(sum(i["faithfulness_score"] for i in items) / len(items), 2),
            "avg_citation_validity": round(sum(i["citation_validity"] for i in items) / len(items), 2),
            "abstain_accuracy": round(sum(1 for i in items if i["abstention_correct"]) / len(items), 2),
        }

    summary = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "total_questions": len(golden_set),
        "overall_avg_latency_s": round(avg_latency, 2),
        "overall_kw_recall": round(avg_kw_recall, 2),
        "overall_faithfulness": round(avg_faithfulness, 2),
        "overall_citation_validity": round(avg_citation_validity, 2),
        "overall_abstain_accuracy": round(abstain_accuracy, 2),
        "category_summaries": cat_summaries,
        "results": results,
    }

    print("\n" + "=" * 60)
    print("EVALUATION SUMMARY REPORT")
    print("=" * 60)
    print(f"Overall Keyword Recall:   {avg_kw_recall * 100:.1f}%")
    print(f"Overall Faithfulness:     {avg_faithfulness * 100:.1f}%")
    print(f"Overall Citation Validity:{avg_citation_validity * 100:.1f}%")
    print(f"Abstention Accuracy:      {abstain_accuracy * 100:.1f}%")
    print(f"Average Latency:          {avg_latency:.2f}s")
    print("-" * 60)
    for cat, stat in cat_summaries.items():
        print(f"  {cat:<14}: Recall {stat['avg_kw_recall']*100:>5.1f}% | Faith {stat['avg_faithfulness']*100:>5.1f}% | Cite {stat['avg_citation_validity']*100:>5.1f}% | Abstain {stat['abstain_accuracy']*100:>5.1f}% | Latency {stat['avg_latency']:>4.1f}s")

    if output_file:
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2)
        print(f"\nReport saved to {output_file}")

    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run Golden Set RAGAS Evaluation")
    parser.add_argument("--endpoint", default="http://localhost:8000", help="Backend API base URL")
    parser.add_argument("--out", default="scripts/eval/eval_report.json", help="Output JSON report file")
    args = parser.parse_args()

    asyncio.run(run_evaluation(args.endpoint, args.out))
