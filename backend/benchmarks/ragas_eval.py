#!/usr/bin/env python3
"""
ragas_eval.py — Faithfulness evaluation for AskMukthiGuru.

Two modes:

  (default) live-endpoint mode — hits the real /api/chat endpoint with
    questions from question_bank.py, using the signed anon-session-token flow
    (POST /api/auth/anon-session -> resolve_anon_identity), and reports the
    pipeline's OWN faithfulness_score / verification / hallucination_flag /
    citations / query_tier fields, plus the reject-rate delta against
    settings.faithfulness_floor — i.e. what % of currently-accepted answers
    would flip to REJECTED under an explicit floor gate. This is the real
    production signal needed for threshold tuning (task #41).

  --legacy-ragas — the original static 4-question dataset scored by the RAGAS
    library's OpenAI-judge metrics. Requires OPENAI_API_KEY, which is outside
    this project's $0-budget open-source stack (root CLAUDE.md). Never calls
    the live backend. Kept only for anyone who wants to run it manually with
    their own key — git history shows this path has never actually been run
    (2 commits, both unrelated repo-wide refactors).

Usage:
  cd backend
  .venv/bin/python benchmarks/ragas_eval.py --endpoint http://localhost:8000
  .venv/bin/python benchmarks/ragas_eval.py --endpoint https://askmukthiguru-8119b0e8-production.up.railway.app --limit 2
  .venv/bin/python benchmarks/ragas_eval.py --legacy-ragas
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
import time
import urllib.parse
from pathlib import Path
from typing import Any, Optional

# Add backend to path
sys.path.append(str(Path(__file__).parent.parent))

import httpx

try:
    from benchmarks.question_bank import QUERIES
except ImportError:
    # Fallback if run directly as scripts/benchmarks/ragas_eval.py
    from question_bank import QUERIES

try:
    from datasets import Dataset

    from ragas import evaluate
    from ragas.metrics import (
        answer_relevancy,
        context_precision,
        context_recall,
        faithfulness,
    )

    RAGAS_AVAILABLE = True
except ImportError:
    RAGAS_AVAILABLE = False

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

REPORT_DIR = Path(__file__).resolve().parent / "reports"

# Standard Ragas benchmark dataset using public teachings (legacy mode only)
EVAL_DATASET = {
    "question": [
        "What is the Beautiful State?",
        "How do I deal with suffering according to Sri Krishnaji?",
        "What are the Four Sacred Secrets of O&O Academy?",
        "What is the first step of Soul Sync meditation?",
    ],
    "contexts": [
        [
            "The Beautiful State is a state of connection, joy, and peace. It is the absence of suffering."
        ],
        ["Suffering is a doorway to transformation. You must observe it to overcome it."],
        [
            "The Four Sacred Secrets include: Spiritual Vision, Inner Truth, Universal Intelligence, and Spiritual Right Action."
        ],
        ["The first step of Soul Sync is deep breathing (breath awareness) for 8 counts."],
    ],
    "answer": [
        "The Beautiful State is a state of connection and joy, characterized by the absence of suffering.",
        "According to Sri Krishnaji, suffering is a doorway to transformation and must be observed.",
        "The Four Sacred Secrets are: Spiritual Vision, Inner Truth, Universal Intelligence, and Spiritual Right Action.",
        "The first step of the practice is taking deep breaths for 8 counts.",
    ],
    "ground_truth": [
        "The Beautiful State is a state devoid of suffering, full of peace and connection.",
        "Sri Krishnaji teaches that observing suffering transforms it.",
        "The Four Sacred Secrets are Spiritual Vision, Inner Truth, Universal Intelligence, and Spiritual Right Action.",
        "The first step of Soul Sync is deep breathing.",
    ],
}


def run_evaluation():
    """Legacy static-dataset RAGAS evaluation (OpenAI-judge metrics). Never
    calls the live backend — see module docstring for why this is opt-in only."""
    logger.info("Starting legacy static Ragas RAG Evaluation...")

    if not RAGAS_AVAILABLE:
        logger.error("Ragas package is not installed. Run: pip install ragas")
        return

    if "OPENAI_API_KEY" not in os.environ:
        logger.warning("OPENAI_API_KEY not set. Ragas uses OpenAI by default.")
        logger.warning("Please set your OPENAI_API_KEY or configure custom LLM wrapper.")

    dataset = Dataset.from_dict(EVAL_DATASET)

    try:
        result = evaluate(
            dataset,
            metrics=[
                context_precision,
                context_recall,
                faithfulness,
                answer_relevancy,
            ],
        )
        logger.info("Evaluation Completed Successfully!")

        df = result.to_pandas()
        print("\n--- Ragas Evaluation Results ---")
        print(df.to_markdown() if hasattr(df, "to_markdown") else df)

        REPORT_DIR.mkdir(parents=True, exist_ok=True)
        df.to_csv(REPORT_DIR / "ragas_evaluation.csv", index=False)
        logger.info("Results saved to %s", REPORT_DIR / "ragas_evaluation.csv")

    except Exception as e:
        logger.error(f"Ragas evaluation failed: {e}")


# ═══════════════════════════════════════════════════════════════════════════
# LIVE-ENDPOINT FAITHFULNESS EVAL (real signal — task #41)
# ═══════════════════════════════════════════════════════════════════════════

# Doctrine + reasoning categories from question_bank.py that carry citations
# and are meaningful faithfulness/hallucination probes.
DEFAULT_LIVE_CATEGORIES = [
    "doctrine_four_secrets",
    "doctrine_soul_sync",
    "doctrine_deeksha",
    "complex_multi_hop",
]


def _validate_endpoint(endpoint: str, test_key: Optional[str]) -> Optional[str]:
    """Return an error message if endpoint is unsafe to call, else None.

    The X-Test-Key backdoor secret must never be sent to an unvalidated host:
    loopback is fine (local dev), any other host must be https. Redirects are
    refused by the client (follow_redirects=False) so a 3xx can never bounce
    the keyed request to a host we did not validate.
    """
    try:
        parsed = urllib.parse.urlparse(endpoint)
    except ValueError:
        return f"Endpoint is not a valid URL: {endpoint!r}"
    if parsed.scheme not in ("http", "https"):
        return f"Endpoint must use http or https (got scheme {parsed.scheme!r}): {endpoint}"
    host = parsed.hostname or ""
    is_loopback = host in {"localhost", "127.0.0.1", "::1"}
    if test_key and not is_loopback and parsed.scheme != "https":
        return f"Endpoint with a test key must be https or loopback (got {endpoint!r})"
    return None


async def _get_anon_session_token(client: httpx.AsyncClient, endpoint: str) -> str:
    """Mint a fresh signed anon session token — required in production per
    resolve_anon_identity() (a bare client-chosen session_id is rejected).
    Fetched fresh per question so the per-session anon quota
    (settings.anon_quota_messages, default 5) never throttles the eval run."""
    r = await client.post(f"{endpoint}/api/auth/anon-session", timeout=15.0)
    r.raise_for_status()
    return r.json()["token"]


def _select_live_questions(categories: list[str], limit_per_category: int) -> list[dict[str, str]]:
    selected = []
    for cat in categories:
        for item in QUERIES.get(cat, [])[:limit_per_category]:
            q = item.get("q", "")
            if q:
                selected.append({"category": cat, "q": q})
    return selected


async def _ask(
    client: httpx.AsyncClient,
    endpoint: str,
    token: str,
    question: str,
    test_key: Optional[str],
) -> dict[str, Any]:
    headers = {"X-Test-Key": test_key} if test_key else {}
    payload = {
        "messages": [],
        "user_message": question,
        "session_id": token,
        "incognito": True,
    }
    r = await client.post(f"{endpoint}/api/chat", json=payload, headers=headers, timeout=180.0)
    r.raise_for_status()
    return r.json()


async def run_live_endpoint_eval(
    endpoint: str,
    categories: list[str],
    limit_per_category: int,
    pace_seconds: float,
    test_key: Optional[str],
) -> dict[str, Any]:
    from app.config import settings

    url_error = _validate_endpoint(endpoint, test_key)
    if url_error:
        raise ValueError(url_error)

    questions = _select_live_questions(categories, limit_per_category)
    logger.info("Live faithfulness eval: %d questions against %s", len(questions), endpoint)

    results: list[dict[str, Any]] = []
    async with httpx.AsyncClient(follow_redirects=False) as client:
        for i, item in enumerate(questions):
            t0 = time.perf_counter()
            error = None
            data: dict[str, Any] = {}
            try:
                token = await _get_anon_session_token(client, endpoint)
                data = await _ask(client, endpoint, token, item["q"], test_key)
            except Exception as exc:
                error = str(exc)
            latency_ms = (time.perf_counter() - t0) * 1000

            verification = data.get("verification")
            entry = {
                "category": item["category"],
                "question": item["q"],
                "error": error,
                "blocked": bool(data.get("blocked")),
                "faithfulness_score": data.get("faithfulness_score"),
                "verification_ran": verification is not None,
                "hallucination_flag": bool(data.get("hallucination_flag")),
                "citations_count": len(data.get("citations") or []),
                "query_tier": data.get("query_tier"),
                "latency_ms": round(latency_ms, 1),
            }
            results.append(entry)
            print(
                f"  [{i + 1}/{len(questions)}] {item['category']:<24} "
                f"faith={entry['faithfulness_score']!s:<6} "
                f"verified={'Y' if entry['verification_ran'] else 'N'} "
                f"halluc={'Y' if entry['hallucination_flag'] else 'N'} "
                f"cites={entry['citations_count']} tier={entry['query_tier']} "
                f"({latency_ms:.0f}ms) — {item['q'][:60]}"
                + (f"  ERROR: {error}" if error else "")
            )

            if i < len(questions) - 1:
                await asyncio.sleep(pace_seconds)

    # Reject-rate delta: among answers the pipeline currently ACCEPTED (not
    # blocked, faithfulness_score present), what % would flip to REJECTED if
    # settings.faithfulness_floor were enforced as an explicit gate?
    accepted = [r for r in results if not r["blocked"] and r["faithfulness_score"] is not None]
    would_flip = [r for r in accepted if r["faithfulness_score"] < settings.faithfulness_floor]
    reject_rate_delta = len(would_flip) / len(accepted) if accepted else 0.0
    verified_rate = sum(1 for r in results if r["verification_ran"]) / len(results) if results else 0.0
    avg_faith = sum(r["faithfulness_score"] for r in accepted) / len(accepted) if accepted else 0.0
    halluc_rate = sum(1 for r in results if r["hallucination_flag"]) / len(results) if results else 0.0

    summary = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "endpoint": endpoint,
        "faithfulness_floor": settings.faithfulness_floor,
        "total_questions": len(results),
        "accepted_count": len(accepted),
        "verification_ran_rate": round(verified_rate, 3),
        "avg_faithfulness_accepted": round(avg_faith, 3),
        "hallucination_flag_rate": round(halluc_rate, 3),
        "reject_rate_delta_under_floor": round(reject_rate_delta, 3),
        "would_flip_to_rejected": [r["question"][:80] for r in would_flip],
        "results": results,
    }

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    report_path = REPORT_DIR / "live_faithfulness_eval.json"
    with open(report_path, "w") as f:
        json.dump(summary, f, indent=2)

    print("\n" + "=" * 70)
    print("LIVE FAITHFULNESS EVAL — SUMMARY")
    print("=" * 70)
    print(f"  Endpoint:                    {endpoint}")
    print(f"  Questions run:               {summary['total_questions']}")
    print(f"  Verification actually ran:   {summary['verification_ran_rate']:.0%}")
    print(f"  Avg faithfulness (accepted): {summary['avg_faithfulness_accepted']:.2f}")
    print(f"  Hallucination flag rate:     {summary['hallucination_flag_rate']:.0%}")
    print(f"  Faithfulness floor:          {settings.faithfulness_floor}")
    print(
        f"  Reject-rate delta under floor: {summary['reject_rate_delta_under_floor']:.0%} "
        f"({len(would_flip)}/{len(accepted)} accepted answers would flip to REJECTED)"
    )
    print(f"  Report saved to: {report_path}")
    print("=" * 70 + "\n")
    return summary


def _parse_args() -> argparse.Namespace:
    from app.config import settings

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--endpoint", default=settings.benchmark_endpoint)
    parser.add_argument("--test-key", default=settings.benchmark_secret or settings.jwt_secret)
    parser.add_argument(
        "--categories",
        default=",".join(DEFAULT_LIVE_CATEGORIES),
        help="Comma-separated question_bank.py category names to sample from.",
    )
    parser.add_argument("--limit", type=int, default=2, help="Questions per category.")
    parser.add_argument(
        "--pace-seconds",
        type=float,
        default=8.0,
        help="Delay between requests — keep >= 6s for the default RATE_LIMIT_PER_MINUTE=10.",
    )
    parser.add_argument(
        "--legacy-ragas",
        action="store_true",
        help="Run the old static-dataset OpenAI-judge RAGAS mode instead (needs OPENAI_API_KEY, never hits the live backend).",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    if args.legacy_ragas:
        run_evaluation()
    else:
        categories = [c.strip() for c in args.categories.split(",") if c.strip()]
        asyncio.run(
            run_live_endpoint_eval(
                endpoint=args.endpoint,
                categories=categories,
                limit_per_category=args.limit,
                pace_seconds=args.pace_seconds,
                test_key=args.test_key,
            )
        )
