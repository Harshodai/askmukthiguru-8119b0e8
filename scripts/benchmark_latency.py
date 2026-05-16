#!/usr/bin/env python3
"""
benchmark_latency.py — AskMukthiGuru RAG pipeline latency benchmark.

Usage:
  python3 scripts/benchmark_latency.py [--url http://localhost:8000] [--n 20]

Reports p50, p95, p99 latency in milliseconds across a set of realistic
spiritual query types. Matches the format from the cost analysis document.
"""
import argparse
import asyncio
import json
import statistics
import sys
import time
from typing import NamedTuple

try:
    import httpx
except ImportError:
    print("ERROR: Install httpx first:  pip install httpx")
    sys.exit(1)

# Representative spiritual queries — covers all intent types
TEST_QUERIES = [
    # CASUAL / greeting
    ("casual", "Namaste, I would like to learn more about the beautiful state."),
    ("casual", "Who are Sri Preethaji and Sri Krishnaji?"),
    # QUERY / spiritual knowledge
    ("query",  "What is the Four Sacred Secrets teaching?"),
    ("query",  "Explain the concept of Ekam in Preethaji's teachings."),
    ("query",  "What does it mean to live in a beautiful state?"),
    ("query",  "How does one practice the Serene Mind technique?"),
    ("query",  "What is consciousness according to the O&O Academy?"),
    ("query",  "Tell me about the Ekam World Peace Festival."),
    # DISTRESS
    ("distress", "I feel very stressed and helpless, I don't know what to do."),
    ("distress", "Everything feels unbearable. I need peace right now."),
    # Mixed / follow-up
    ("followup", "Can you say more about the breath practice you mentioned?"),
    ("followup", "How long does the Serene Mind meditation take?"),
]


class BenchmarkResult(NamedTuple):
    intent: str
    query: str
    latency_ms: float
    status: int
    detected_intent: str
    meditation_step: int
    error: str


async def run_one(
    client: httpx.AsyncClient,
    url: str,
    intent: str,
    query: str,
    timeout: float = 30.0,
) -> BenchmarkResult:
    t0 = time.perf_counter()
    try:
        r = await client.post(
            f"{url}/api/chat",
            json={
                "messages": [{"role": "user", "content": query}],
                "user_message": query,
                "meditation_step": 0,
            },
            timeout=timeout,
        )
        elapsed_ms = (time.perf_counter() - t0) * 1000
        if r.status_code == 200:
            body = r.json()
            return BenchmarkResult(
                intent=intent,
                query=query[:60],
                latency_ms=round(elapsed_ms, 1),
                status=r.status_code,
                detected_intent=body.get("intent", "?"),
                meditation_step=body.get("meditation_step", 0),
                error="",
            )
        else:
            return BenchmarkResult(intent, query[:60], round(elapsed_ms, 1), r.status_code, "?", 0, r.text[:80])
    except Exception as e:
        elapsed_ms = (time.perf_counter() - t0) * 1000
        return BenchmarkResult(intent, query[:60], round(elapsed_ms, 1), 0, "?", 0, str(e)[:80])


def percentile(data: list[float], p: float) -> float:
    if not data:
        return 0.0
    sorted_data = sorted(data)
    k = (len(sorted_data) - 1) * p / 100
    f, c = int(k), min(int(k) + 1, len(sorted_data) - 1)
    return round(sorted_data[f] + (sorted_data[c] - sorted_data[f]) * (k - f), 1)


async def main(url: str, n: int) -> None:
    print(f"\n🔍 AskMukthiGuru RAG Latency Benchmark")
    print(f"   Backend : {url}")
    print(f"   Queries : {n} (cycling through {len(TEST_QUERIES)} templates)")
    print(f"   Timeout : 30s per query\n")

    # Health check first
    async with httpx.AsyncClient() as client:
        try:
            h = await client.get(f"{url}/api/health", timeout=5.0)
            print(f"✅ Backend health: {h.status_code} — {h.text[:60]}\n")
        except Exception as e:
            print(f"❌ Cannot reach backend at {url}: {e}")
            print("   Start Docker: make docker-rebuild (or npm run dev + backend)")
            sys.exit(1)

        results: list[BenchmarkResult] = []
        queries = [TEST_QUERIES[i % len(TEST_QUERIES)] for i in range(n)]

        print(f"{'#':>3}  {'Intent':<10}  {'ms':>7}  {'Detected':<12}  Query")
        print("─" * 80)

        for i, (intent, query) in enumerate(queries, 1):
            r = await run_one(client, url, intent, query)
            results.append(r)
            flag = "❌" if r.error else "✅"
            print(f"{i:>3}  {r.intent:<10}  {r.latency_ms:>7.1f}  {r.detected_intent:<12}  {r.query}")
            if r.error:
                print(f"     └─ ERROR: {r.error}")

    # Statistics
    ok = [r.latency_ms for r in results if not r.error]
    errors = [r for r in results if r.error]

    print("\n" + "═" * 80)
    print("📊  RESULTS\n")

    if ok:
        print(f"  Queries run   : {len(results)}")
        print(f"  Successful    : {len(ok)}")
        print(f"  Errors        : {len(errors)}")
        print(f"")
        print(f"  p50 latency   : {percentile(ok, 50):>8.1f} ms")
        print(f"  p75 latency   : {percentile(ok, 75):>8.1f} ms")
        print(f"  p95 latency   : {percentile(ok, 95):>8.1f} ms")
        print(f"  p99 latency   : {percentile(ok, 99):>8.1f} ms")
        print(f"  Mean latency  : {statistics.mean(ok):>8.1f} ms")
        print(f"  Max latency   : {max(ok):>8.1f} ms")
        print()

        # Verdict
        p99 = percentile(ok, 99)
        if p99 < 4000:
            print(f"  ✅ p99 {p99:.0f}ms — EXCELLENT. Ready to market.")
        elif p99 < 8000:
            print(f"  ⚠️  p99 {p99:.0f}ms — ACCEPTABLE. Consider disabling CoVe/Self-RAG.")
        else:
            print(f"  ❌ p99 {p99:.0f}ms — TOO SLOW. Disable layers 10-11 before marketing.")

        # By intent
        by_intent: dict[str, list[float]] = {}
        for r in results:
            if not r.error:
                by_intent.setdefault(r.intent, []).append(r.latency_ms)
        print()
        print("  Latency by intent type:")
        for intent_type, lats in sorted(by_intent.items()):
            print(f"    {intent_type:<12} p50={percentile(lats, 50):>7.1f}ms  p95={percentile(lats, 95):>7.1f}ms  n={len(lats)}")

    else:
        print("  ❌ All queries failed. Backend unreachable or misconfigured.")

    print("\n" + "═" * 80)

    # Export JSON
    out = {
        "backend": url,
        "n": n,
        "p50_ms": percentile(ok, 50) if ok else None,
        "p95_ms": percentile(ok, 95) if ok else None,
        "p99_ms": percentile(ok, 99) if ok else None,
        "mean_ms": round(statistics.mean(ok), 1) if ok else None,
        "error_rate": len(errors) / len(results) if results else 1.0,
        "results": [r._asdict() for r in results],
    }
    out_path = "benchmark_results.json"
    with open(out_path, "w") as f:
        json.dump(out, f, indent=2)
    print(f"\n  Full results saved to: {out_path}")
    print()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AskMukthiGuru latency benchmark")
    parser.add_argument("--url", default="http://localhost:8000", help="Backend base URL")
    parser.add_argument("--n", type=int, default=20, help="Number of queries to send")
    args = parser.parse_args()
    asyncio.run(main(args.url, args.n))
