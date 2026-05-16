#!/usr/bin/env python3
"""
benchmark_rag_responses.py
==========================
AskMukthiGuru RAG quality benchmark suite.

Sends 10 spiritually diverse queries to the backend and evaluates:
- Response latency
- Keyword relevance scoring
- Source citation presence
- Intent classification accuracy

Usage:
    python scripts/benchmark_rag_responses.py [--base-url http://localhost:8000]

Requires: httpx, rich
    pip install httpx rich
"""

import argparse
import json
import time
import sys
from dataclasses import dataclass, field
from typing import Optional

try:
    import httpx
    from rich.console import Console
    from rich.table import Table
    from rich.progress import Progress
except ImportError:
    print("Missing deps. Run: pip install httpx rich")
    sys.exit(1)


# ─── Benchmark Queries ───────────────────────────────────────────────────────
BENCHMARK_QUERIES = [
    {
        "id": "Q01",
        "query": "What is the Beautiful State?",
        "expected_intent": "SPIRITUAL_QUERY",
        "required_keywords": ["beautiful state", "preethaji", "peace", "connection"],
        "should_cite": True,
    },
    {
        "id": "Q02",
        "query": "I feel so anxious and overwhelmed, I don't know what to do",
        "expected_intent": "DISTRESS",
        "required_keywords": ["breath", "peace", "calm", "present"],
        "should_cite": False,
    },
    {
        "id": "Q03",
        "query": "Guide me through a 5-minute meditation",
        "expected_intent": "MEDITATION",
        "required_keywords": ["breath", "inhale", "exhale", "body", "awareness"],
        "should_cite": False,
    },
    {
        "id": "Q04",
        "query": "What are the Four Sacred Secrets?",
        "expected_intent": "SPIRITUAL_QUERY",
        "required_keywords": ["sacred secrets", "krishnaji", "preethaji", "soul"],
        "should_cite": True,
    },
    {
        "id": "Q05",
        "query": "How do I practice Soul Sync?",
        "expected_intent": "SPIRITUAL_QUERY",
        "required_keywords": ["soul sync", "prakruti", "nature", "synchronize"],
        "should_cite": True,
    },
    {
        "id": "Q06",
        "query": "Hello, how are you?",
        "expected_intent": "CASUAL",
        "required_keywords": ["namaste", "seeker", "guide"],
        "should_cite": False,
    },
    {
        "id": "Q07",
        "query": "What is Ekam and how is it related to world peace?",
        "expected_intent": "SPIRITUAL_QUERY",
        "required_keywords": ["ekam", "world peace", "consciousness", "field"],
        "should_cite": True,
    },
    {
        "id": "Q08",
        "query": "I lost my job and feel like a failure",
        "expected_intent": "DISTRESS",
        "required_keywords": ["compassion", "peace", "breath", "moment"],
        "should_cite": False,
    },
    {
        "id": "Q09",
        "query": "Can you explain the teaching about suffering and disconnection?",
        "expected_intent": "SPIRITUAL_QUERY",
        "required_keywords": ["suffering", "disconnection", "beautiful state", "consciousness"],
        "should_cite": True,
    },
    {
        "id": "Q10",
        "query": "What language should I pray in?",
        "expected_intent": "CASUAL",
        "required_keywords": ["language", "heart", "intention"],
        "should_cite": False,
    },
]


# ─── Data ────────────────────────────────────────────────────────────────────
@dataclass
class BenchmarkResult:
    query_id: str
    query: str
    expected_intent: str
    actual_intent: str
    latency_ms: float
    keyword_score: float
    has_citations: bool
    expected_citations: bool
    intent_match: bool
    response_length: int
    error: Optional[str] = None


def score_keywords(response_text: str, keywords: list[str]) -> float:
    """Return fraction of keywords found in the response (case-insensitive)."""
    if not keywords:
        return 1.0
    text_lower = response_text.lower()
    hits = sum(1 for kw in keywords if kw.lower() in text_lower)
    return round(hits / len(keywords), 2)


# ─── Runner ──────────────────────────────────────────────────────────────────
def run_benchmark(base_url: str, timeout: float = 30.0) -> list[BenchmarkResult]:
    results: list[BenchmarkResult] = []
    console = Console()

    with httpx.Client(base_url=base_url, timeout=timeout) as client:
        with Progress(console=console) as progress:
            task = progress.add_task("Running benchmark…", total=len(BENCHMARK_QUERIES))

            for bq in BENCHMARK_QUERIES:
                start = time.perf_counter()
                error = None
                response_text = ""
                actual_intent = "UNKNOWN"
                citations = []

                try:
                    resp = client.post(
                        "/api/chat",
                        json={
                            "message": bq["query"],
                            "history": [],
                            "language": "en",
                        },
                    )
                    resp.raise_for_status()
                    data = resp.json()
                    response_text = data.get("content", "")
                    actual_intent = data.get("intent", "UNKNOWN")
                    citations = data.get("citations", [])
                except httpx.HTTPStatusError as e:
                    error = f"HTTP {e.response.status_code}"
                except httpx.ConnectError:
                    error = "Connection refused — is the backend running?"
                except Exception as e:
                    error = str(e)

                latency_ms = (time.perf_counter() - start) * 1000

                results.append(BenchmarkResult(
                    query_id=bq["id"],
                    query=bq["query"][:60] + ("…" if len(bq["query"]) > 60 else ""),
                    expected_intent=bq["expected_intent"],
                    actual_intent=actual_intent,
                    latency_ms=round(latency_ms, 1),
                    keyword_score=score_keywords(response_text, bq["required_keywords"]),
                    has_citations=len(citations) > 0,
                    expected_citations=bq["should_cite"],
                    intent_match=(actual_intent == bq["expected_intent"]),
                    response_length=len(response_text),
                    error=error,
                ))
                progress.advance(task)

    return results


# ─── Report ──────────────────────────────────────────────────────────────────
def print_report(results: list[BenchmarkResult]) -> None:
    console = Console()

    table = Table(title="AskMukthiGuru RAG Benchmark", show_header=True, header_style="bold cyan")
    table.add_column("ID", width=4)
    table.add_column("Query", width=45, no_wrap=True)
    table.add_column("Intent", width=10)
    table.add_column("✓ Intent", width=8)
    table.add_column("Keywords", width=9)
    table.add_column("Citations", width=9)
    table.add_column("Latency", width=10)
    table.add_column("Error", width=25)

    for r in results:
        intent_ok = "✅" if r.intent_match else f"❌({r.actual_intent})"
        kw_color = "green" if r.keyword_score >= 0.75 else ("yellow" if r.keyword_score >= 0.5 else "red")
        cite_ok = "✅" if r.has_citations == r.expected_citations else "⚠️"
        latency_color = "green" if r.latency_ms < 3000 else ("yellow" if r.latency_ms < 8000 else "red")

        table.add_row(
            r.query_id,
            r.query,
            r.expected_intent[:12],
            intent_ok,
            f"[{kw_color}]{r.keyword_score:.0%}[/{kw_color}]",
            cite_ok,
            f"[{latency_color}]{r.latency_ms:.0f}ms[/{latency_color}]",
            r.error or "",
        )

    console.print(table)

    # Summary stats
    valid = [r for r in results if not r.error]
    if valid:
        avg_latency = sum(r.latency_ms for r in valid) / len(valid)
        intent_accuracy = sum(r.intent_match for r in valid) / len(valid)
        avg_keywords = sum(r.keyword_score for r in valid) / len(valid)
        cite_accuracy = sum(r.has_citations == r.expected_citations for r in valid) / len(valid)

        console.print(f"\n[bold]Summary ({len(valid)}/{len(results)} queries succeeded)[/bold]")
        console.print(f"  Intent accuracy  : {intent_accuracy:.0%}")
        console.print(f"  Avg keyword score: {avg_keywords:.0%}")
        console.print(f"  Citation accuracy: {cite_accuracy:.0%}")
        console.print(f"  Avg latency      : {avg_latency:.0f}ms")

        # Pass/Fail gate
        passed = intent_accuracy >= 0.7 and avg_keywords >= 0.5
        if passed:
            console.print("\n[bold green]✅ BENCHMARK PASSED[/bold green]")
        else:
            console.print("\n[bold red]❌ BENCHMARK FAILED (intent < 70% or keyword score < 50%)[/bold red]")
            sys.exit(1)
    else:
        console.print("\n[bold red]All queries failed — backend unavailable?[/bold red]")
        sys.exit(1)


# ─── Main ────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AskMukthiGuru RAG benchmark suite")
    parser.add_argument("--base-url", default="http://localhost:8000", help="Backend base URL")
    parser.add_argument("--timeout", type=float, default=30.0, help="Per-request timeout in seconds")
    parser.add_argument("--output-json", help="Optional path to dump results as JSON")
    args = parser.parse_args()

    print(f"Running benchmark against {args.base_url}…\n")
    results = run_benchmark(args.base_url, args.timeout)
    print_report(results)

    if args.output_json:
        with open(args.output_json, "w") as f:
            json.dump(
                [
                    {
                        "id": r.query_id, "query": r.query, "intent_match": r.intent_match,
                        "keyword_score": r.keyword_score, "latency_ms": r.latency_ms,
                        "has_citations": r.has_citations, "error": r.error,
                    }
                    for r in results
                ],
                f, indent=2,
            )
        print(f"\nResults written to {args.output_json}")
