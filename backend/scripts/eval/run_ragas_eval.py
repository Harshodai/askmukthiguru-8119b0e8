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
import urllib.parse
from typing import Any

import httpx

GOLDEN_QUESTIONS_FILE = os.path.join(os.path.dirname(__file__), "golden_questions.json")


def _validate_endpoint(endpoint: str) -> str | None:
    """Return an error message if endpoint is unsafe to call, else None.

    No credential is sent by this harness, but the endpoint must still be a
    well-formed http(s) URL; non-loopback plain-http targets are refused and
    the client never follows redirects (follow_redirects=False), so a 3xx
    cannot silently reroute requests to an unvalidated host.
    """
    try:
        parsed = urllib.parse.urlparse(endpoint)
    except ValueError:
        return f"Endpoint is not a valid URL: {endpoint!r}"
    if parsed.scheme not in ("http", "https"):
        return f"Endpoint must use http or https (got scheme {parsed.scheme!r}): {endpoint}"
    host = parsed.hostname or ""
    is_loopback = host in {"localhost", "127.0.0.1", "::1"}
    if not is_loopback and parsed.scheme != "https":
        return f"Endpoint must be https or loopback (got {endpoint!r})"
    return None


def _normalize_citation_url(url: str) -> str:
    """Canonical citation form for equality comparison: query/fragment stripped,
    lowercased, trailing slash removed. Compare for equality, never substring."""
    try:
        parsed = urllib.parse.urlsplit(url)
        return (parsed.scheme + "://" + parsed.netloc + parsed.path).strip().lower().rstrip("/")
    except ValueError:
        return url.strip().lower().rstrip("/")


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


def evaluate_abstention(
    answer: str, should_abstain: bool, expected_keywords: list[str] | None = None
) -> bool:
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


async def _get_anon_session_token(client: httpx.AsyncClient) -> str:
    """Mint a fresh signed anon session token (resolve_anon_identity() rejects a
    bare client-chosen session_id in production). Fetched per question so the
    per-session anon quota (settings.anon_quota_messages, default 5) doesn't
    throttle a 50-question golden-set run."""
    from app.config import settings
    from rag.timeout_utils import timeout_with_margin

    r = await client.post(
        "/api/auth/anon-session",
        timeout=timeout_with_margin(settings.benchmark_anon_session_timeout),
    )
    r.raise_for_status()
    return r.json()["token"]


async def run_evaluation(
    endpoint: str,
    output_file: str | None = None,
    limit_per_category: int | None = None,
) -> dict[str, Any]:
    url_error = _validate_endpoint(endpoint)
    if url_error:
        raise ValueError(url_error)
    golden_set = load_golden_set()
    if limit_per_category:
        counts: dict[str, int] = {}
        filtered_set = []
        for item in golden_set:
            cat = item.get("category", "default")
            if counts.get(cat, 0) < limit_per_category:
                filtered_set.append(item)
                counts[cat] = counts.get(cat, 0) + 1
        golden_set = filtered_set
    print(f"Loaded {len(golden_set)} golden evaluation questions.")
    print(f"Targeting endpoint: {endpoint}")

    results = []
    category_scores: dict[str, list[dict]] = {}

    from app.config import settings
    from rag.timeout_utils import timeout_with_margin

    async with httpx.AsyncClient(
        base_url=endpoint,
        timeout=timeout_with_margin(settings.benchmark_chat_timeout),
        follow_redirects=False,
    ) as client:
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
            citations: list[str] = []
            faithfulness_score = None
            error = None

            try:
                token = await _get_anon_session_token(client)
                resp = await client.post(
                    "/api/chat",
                    json={
                        "messages": [],
                        "user_message": question,
                        "session_id": token,
                        "language": item.get("language", "en"),
                        "incognito": True,
                    },
                )
                status_code = resp.status_code
                if status_code == 200:
                    data = resp.json()
                    answer = data.get("response", "")
                    citations = data.get("citations", [])
                    faithfulness_score = data.get("faithfulness_score")
                else:
                    error = f"HTTP {status_code}: {resp.text[:100]}"
            except Exception as exc:
                error = str(exc)

            latency = time.time() - start_time

            kw_recall = calculate_keyword_recall(answer, expected_keywords)
            abstention_correct = evaluate_abstention(answer, should_abstain, expected_keywords)
            if expected_citations and citations:
                citation_set = {_normalize_citation_url(u) for u in citations}
                matched = sum(
                    1 for e in expected_citations if _normalize_citation_url(e) in citation_set
                )
                citation_validity = matched / max(len(expected_citations), 1)
            elif not expected_citations:
                citation_validity = 1.0
            else:
                citation_validity = 0.0

            faith_display = (
                f"{faithfulness_score * 100:.0f}%" if faithfulness_score is not None else "N/A"
            )

            eval_entry = {
                "id": q_id,
                "category": category,
                "question": question,
                "latency_s": round(latency, 2),
                "status_code": status_code,
                "answer_length": len(answer),
                "keyword_recall": round(kw_recall, 2),
                "abstention_correct": abstention_correct,
                "faithfulness_score": (
                    round(faithfulness_score, 2) if faithfulness_score is not None else None
                ),
                "citation_validity": round(citation_validity, 2),
                "citation_count": len(citations),
                "error": error,
            }
            results.append(eval_entry)
            category_scores.setdefault(category, []).append(eval_entry)

            print(
                f"[{idx}/{len(golden_set)}] {category:<12} | "
                f"KW Recall: {kw_recall * 100:>3.0f}% | "
                f"Faith: {faith_display:>4} | "
                f"Cite Valid: {citation_validity * 100:>3.0f}% | "
                f"Abstain OK: {'✓' if abstention_correct else '✗'} | "
                f"Latency: {latency:>4.1f}s | "
                f"{q_id}"
            )

    # Calculate Aggregate Metrics
    avg_latency = sum(r["latency_s"] for r in results) / max(len(results), 1)
    avg_kw_recall = sum(r["keyword_recall"] for r in results) / max(len(results), 1)
    faith_scores = [r["faithfulness_score"] for r in results if r["faithfulness_score"] is not None]
    faith_unavailable = len(results) - len(faith_scores)
    avg_faithfulness = sum(faith_scores) / len(faith_scores) if faith_scores else 0.0
    avg_citation_validity = sum(r["citation_validity"] for r in results) / max(len(results), 1)
    abstain_accuracy = sum(1 for r in results if r["abstention_correct"]) / max(len(results), 1)

    cat_summaries = {}
    for cat, items in category_scores.items():
        cat_faith = [i["faithfulness_score"] for i in items if i["faithfulness_score"] is not None]
        cat_summaries[cat] = {
            "count": len(items),
            "avg_latency": round(sum(i["latency_s"] for i in items) / len(items), 2),
            "avg_kw_recall": round(sum(i["keyword_recall"] for i in items) / len(items), 2),
            "avg_faithfulness": round(sum(cat_faith) / len(cat_faith), 2) if cat_faith else 0.0,
            "faithfulness_count": len(cat_faith),
            "avg_citation_validity": round(
                sum(i["citation_validity"] for i in items) / len(items), 2
            ),
            "abstain_accuracy": round(
                sum(1 for i in items if i["abstention_correct"]) / len(items), 2
            ),
        }

    summary = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "total_questions": len(golden_set),
        "overall_avg_latency_s": round(avg_latency, 2),
        "overall_kw_recall": round(avg_kw_recall, 2),
        "overall_faithfulness": round(avg_faithfulness, 2),
        "faithfulness_unavailable": faith_unavailable,
        "overall_citation_validity": round(avg_citation_validity, 2),
        "overall_abstain_accuracy": round(abstain_accuracy, 2),
        "category_summaries": cat_summaries,
        "results": results,
    }

    print("\n" + "=" * 60)
    print("EVALUATION SUMMARY REPORT")
    print("=" * 60)
    print(f"Overall Keyword Recall:   {avg_kw_recall * 100:.1f}%")
    print(
        f"Overall Faithfulness:     {avg_faithfulness * 100:.1f}% "
        f"({faith_unavailable} of {len(results)} unanswered)"
    )
    print(f"Overall Citation Validity:{avg_citation_validity * 100:.1f}%")
    print(f"Abstention Accuracy:      {abstain_accuracy * 100:.1f}%")
    print(f"Average Latency:          {avg_latency:.2f}s")
    print("-" * 60)
    for cat, stat in cat_summaries.items():
        print(
            f"  {cat:<14}: Recall {stat['avg_kw_recall'] * 100:>5.1f}% | Faith {stat['avg_faithfulness'] * 100:>5.1f}% | Cite {stat['avg_citation_validity'] * 100:>5.1f}% | Abstain {stat['abstain_accuracy'] * 100:>5.1f}% | Latency {stat['avg_latency']:>4.1f}s"
        )

    if output_file:
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2)
        print(f"\nReport saved to {output_file}")

    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run Golden Set RAGAS Evaluation")
    parser.add_argument("--endpoint", default="http://localhost:8000", help="Backend API base URL")
    parser.add_argument(
        "--out", default="scripts/eval/eval_report.json", help="Output JSON report file"
    )
    parser.add_argument(
        "--limit-per-category",
        type=int,
        default=None,
        help="Optional limit on number of questions evaluated per category",
    )
    args = parser.parse_args()

    asyncio.run(run_evaluation(args.endpoint, args.out, args.limit_per_category))
