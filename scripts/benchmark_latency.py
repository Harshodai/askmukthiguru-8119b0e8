#!/usr/bin/env python3
"""
benchmark_latency.py — Comprehensive AskMukthiGuru RAG pipeline benchmark.

Covers: latency (p50/p95/p99), TTFT, intent accuracy, citation quality,
cache hit rates, concurrent load, Serene Mind triggers, and cost estimation.

Usage:
  pip install httpx
  python3 scripts/benchmark_latency.py [--url http://localhost:8000] [--n 50] [--concurrency 5]
"""
import argparse, asyncio, hashlib, json, math, os, statistics, sys, time, uuid
from typing import NamedTuple

try:
    import httpx
except ImportError:
    print("ERROR: pip install httpx"); sys.exit(1)

# ═══════════════════════════════════════════════════════════════════════════
# Real spiritual questions sourced from Ekam.org, O&O Academy teachings,
# Four Sacred Secrets book, and common seeker queries.
# ═══════════════════════════════════════════════════════════════════════════
QUERIES = {
    "casual": [
        "Namaste Mukthi Guru, how are you today?",
        "Hello, I'm new here. What is this about?",
        "Good morning, can you tell me about yourself?",
        "What kind of guidance do you offer?",
        "Who created you?",
    ],
    "spiritual_knowledge": [
        # Four Sacred Secrets
        "What are the Four Sacred Secrets?",
        "Explain the first sacred secret — Spiritual Vision.",
        "How does the second secret about Inner Truth help dissolve suffering?",
        "What does it mean to access the Universal Intelligence?",
        "What is Spiritual Right Action according to Preethaji and Krishnaji?",
        # Beautiful State
        "What is the beautiful state of consciousness?",
        "How is the beautiful state different from happiness?",
        "Why do Sri Preethaji and Krishnaji say there are only two states?",
        "What causes us to shift from the beautiful state to the suffering state?",
        # O&O Academy / Ekam
        "What is the O&O Academy?",
        "Tell me about the Ekam World Peace Festival.",
        "What is the significance of the Ekam mantra Humsa Sohum Ekam?",
        "Who are Sri Preethaji and Sri Krishnaji?",
        "What courses does the O&O Academy offer?",
        # Soul Sync
        "What is Soul Sync and how does it work?",
        "How long is a Soul Sync practice session?",
        "What are the benefits of regular Soul Sync practice?",
        "Can beginners practice Soul Sync without prior experience?",
        # Serene Mind
        "How does the Serene Mind technique work?",
        "What happens to the amygdala during Serene Mind practice?",
        "Is Serene Mind the same as regular meditation?",
        # Deeper teachings
        "What is the relationship between consciousness and suffering?",
        "How does one develop an inner connection with the Divine?",
        "What is Ojas in the context of Ekam Health Practice?",
        "Explain the concept of Tejas and Prana in Ekam teachings.",
    ],
    "distress": [
        "I feel so lost and hopeless, I don't know what to do.",
        "Everything feels unbearable. I need peace right now.",
        "I am very stressed and anxious, nothing is working.",
        "I feel very alone, nobody understands my pain.",
        "I can't sleep, my mind won't stop racing with worries.",
        "I feel like giving up on everything.",
        "My heart is heavy with grief and I can't move forward.",
    ],
    "followup": [
        "Can you say more about what you just mentioned?",
        "How do I actually practice that in daily life?",
        "What if I can't calm my mind during the practice?",
        "How long does it take to see results?",
        "Is there a specific time of day I should do this?",
    ],
    "edge_case": [
        "",  # empty
        "a",  # single char
        "What is 2+2?",  # off-topic
        "Tell me a joke about spirituality.",  # humor
        "Can you write Python code for me?",  # code request
        "x" * 2000,  # very long input
    ],
    "cache_duplicate": [
        "What are the Four Sacred Secrets?",  # repeat to test cache
        "What are the Four Sacred Secrets?",
        "What is the beautiful state?",
        "What is the beautiful state?",
    ],
}


class Result(NamedTuple):
    category: str; query_preview: str; latency_ms: float; ttft_ms: float
    status: int; detected_intent: str; meditation_step: int
    has_citations: bool; citation_count: int; response_len: int; error: str


async def bench_one(client: httpx.AsyncClient, url: str, cat: str, query: str, timeout: float = 60.0) -> Result:
    preview = (query[:55] + "…") if len(query) > 55 else query
    t0 = time.perf_counter()
    try:
        r = await client.post(f"{url}/api/chat", json={
            "messages": [{"role": "user", "content": query}],
            "user_message": query, "meditation_step": 0,
        }, timeout=timeout)
        total = (time.perf_counter() - t0) * 1000
        if r.status_code == 200:
            b = r.json()
            cites = b.get("citations", [])
            resp = b.get("response", "")
            return Result(cat, preview, round(total, 1), round(total * 0.3, 1),  # approx TTFT
                          200, b.get("intent", "?"), b.get("meditation_step", 0),
                          len(cites) > 0, len(cites), len(resp), "")
        return Result(cat, preview, round(total, 1), 0, r.status_code, "?", 0, False, 0, 0, r.text[:80])
    except Exception as e:
        return Result(cat, preview, round((time.perf_counter() - t0) * 1000, 1), 0, 0, "?", 0, False, 0, 0, str(e)[:80])


async def bench_stream(client: httpx.AsyncClient, url: str, query: str) -> dict:
    """Test streaming endpoint — measure TTFT and total stream time."""
    t0 = time.perf_counter()
    ttft = None
    chunks = 0
    try:
        async with client.stream("POST", f"{url}/api/chat/stream", json={
            "messages": [{"role": "user", "content": query}],
            "user_message": query, "meditation_step": 0,
        }, timeout=60.0) as resp:
            async for line in resp.aiter_lines():
                if ttft is None and line.strip():
                    ttft = (time.perf_counter() - t0) * 1000
                chunks += 1
        total = (time.perf_counter() - t0) * 1000
        return {"ttft_ms": round(ttft or total, 1), "total_ms": round(total, 1), "chunks": chunks, "error": ""}
    except Exception as e:
        return {"ttft_ms": 0, "total_ms": round((time.perf_counter() - t0) * 1000, 1), "chunks": 0, "error": str(e)[:80]}


def pct(data: list[float], p: float) -> float:
    if not data: return 0.0
    s = sorted(data)
    k = (len(s) - 1) * p / 100
    f = int(k)
    return round(s[f] + (s[min(f+1, len(s)-1)] - s[f]) * (k - f), 1)


async def run_concurrent(client: httpx.AsyncClient, url: str, n: int) -> list[float]:
    """Fire n simultaneous requests to test concurrency."""
    query = "What is the beautiful state?"
    tasks = [bench_one(client, url, "concurrent", query, timeout=90.0) for _ in range(n)]
    results = await asyncio.gather(*tasks)
    return [r.latency_ms for r in results if not r.error]


async def main(url: str, n: int, concurrency: int) -> None:
    print(f"\n{'═'*80}")
    print(f"  🔍  AskMukthiGuru RAG Pipeline — Comprehensive Benchmark")
    print(f"{'═'*80}")
    print(f"  Backend     : {url}")
    print(f"  Queries     : {n} sequential + {concurrency} concurrent")
    print(f"  Categories  : {len(QUERIES)} ({', '.join(QUERIES.keys())})")
    print(f"  Timestamp   : {time.strftime('%Y-%m-%d %H:%M:%S')}\n")

    async with httpx.AsyncClient() as client:
        # Health check
        try:
            h = await client.get(f"{url}/api/health", timeout=5.0)
            print(f"  ✅ Health: {h.status_code}\n")
        except Exception as e:
            print(f"  ❌ Cannot reach {url}: {e}")
            print("     Start Docker: make docker-rebuild")
            sys.exit(1)

        # ── Phase 1: Sequential benchmark ──
        print(f"{'─'*80}")
        print(f"  PHASE 1: Sequential Queries ({n} total)")
        print(f"{'─'*80}")
        print(f"  {'#':>3}  {'Category':<20}  {'ms':>7}  {'Intent':<12}  {'Cites':>5}  Query")

        all_queries = []
        for cat, qs in QUERIES.items():
            for q in qs:
                all_queries.append((cat, q))
        # Cycle through to reach n
        test_set = [all_queries[i % len(all_queries)] for i in range(n)]

        results: list[Result] = []
        for i, (cat, q) in enumerate(test_set, 1):
            r = await bench_one(client, url, cat, q)
            results.append(r)
            flag = "✅" if not r.error else "❌"
            print(f"  {i:>3}  {r.category:<20}  {r.latency_ms:>7.0f}  {r.detected_intent:<12}  {r.citation_count:>5}  {r.query_preview}")
            if r.error:
                print(f"       └─ {r.error}")

        # ── Phase 2: Streaming TTFT ──
        print(f"\n{'─'*80}")
        print(f"  PHASE 2: Streaming TTFT (5 queries)")
        print(f"{'─'*80}")
        stream_queries = [
            "What is the beautiful state?",
            "Guide me through a Serene Mind meditation.",
            "I feel very stressed.",
            "Tell me about the Four Sacred Secrets.",
            "Namaste, how are you?",
        ]
        stream_results = []
        for q in stream_queries:
            sr = await bench_stream(client, url, q)
            stream_results.append(sr)
            flag = "✅" if not sr["error"] else "❌"
            print(f"  {flag} TTFT={sr['ttft_ms']:>7.0f}ms  Total={sr['total_ms']:>7.0f}ms  Chunks={sr['chunks']:>3}  {q[:50]}")

        # ── Phase 3: Concurrent load ──
        print(f"\n{'─'*80}")
        print(f"  PHASE 3: Concurrent Load ({concurrency} simultaneous)")
        print(f"{'─'*80}")
        conc_latencies = await run_concurrent(client, url, concurrency)
        if conc_latencies:
            print(f"  Concurrent p50 : {pct(conc_latencies, 50):>7.0f}ms")
            print(f"  Concurrent p95 : {pct(conc_latencies, 95):>7.0f}ms")
            print(f"  Concurrent max : {max(conc_latencies):>7.0f}ms")
            print(f"  Success rate   : {len(conc_latencies)}/{concurrency}")
        else:
            print(f"  ❌ All concurrent requests failed")

    # ═══════════════════════════════════════════════════════════════════
    # ANALYSIS
    # ═══════════════════════════════════════════════════════════════════
    ok = [r for r in results if not r.error]
    errs = [r for r in results if r.error]
    lats = [r.latency_ms for r in ok]

    print(f"\n{'═'*80}")
    print(f"  📊  RESULTS")
    print(f"{'═'*80}\n")

    if lats:
        print(f"  Total queries     : {len(results)}")
        print(f"  Successful        : {len(ok)}")
        print(f"  Errors            : {len(errs)}")
        print(f"  Error rate        : {len(errs)/len(results)*100:.1f}%\n")
        print(f"  ┌────────────────────────────────────────┐")
        print(f"  │  p50 latency    : {pct(lats, 50):>8.0f} ms        │")
        print(f"  │  p75 latency    : {pct(lats, 75):>8.0f} ms        │")
        print(f"  │  p95 latency    : {pct(lats, 95):>8.0f} ms        │")
        print(f"  │  p99 latency    : {pct(lats, 99):>8.0f} ms        │")
        print(f"  │  Mean latency   : {statistics.mean(lats):>8.0f} ms        │")
        print(f"  │  Max latency    : {max(lats):>8.0f} ms        │")
        print(f"  └────────────────────────────────────────┘\n")

        # By category
        print(f"  Latency by category:")
        by_cat: dict[str, list[float]] = {}
        for r in ok:
            by_cat.setdefault(r.category, []).append(r.latency_ms)
        for cat, ls in sorted(by_cat.items(), key=lambda x: -pct(x[1], 50)):
            print(f"    {cat:<22} p50={pct(ls, 50):>7.0f}ms  p95={pct(ls, 95):>7.0f}ms  n={len(ls)}")

        # Intent accuracy
        print(f"\n  Intent detection:")
        intent_map = {"casual": "CASUAL", "spiritual_knowledge": "QUERY",
                      "distress": "DISTRESS", "followup": "QUERY"}
        correct = sum(1 for r in ok if intent_map.get(r.category, "?") == r.detected_intent)
        mapped = sum(1 for r in ok if r.category in intent_map)
        if mapped:
            print(f"    Accuracy: {correct}/{mapped} ({correct/mapped*100:.0f}%)")

        # Serene Mind triggers
        sm_triggers = [r for r in ok if r.detected_intent == "DISTRESS" or r.meditation_step > 0]
        distress_q = [r for r in ok if r.category == "distress"]
        print(f"\n  Serene Mind triggers:")
        print(f"    Distress queries: {len(distress_q)}")
        print(f"    Triggered SM    : {len(sm_triggers)}")
        if distress_q:
            print(f"    Trigger rate    : {len(sm_triggers)/len(distress_q)*100:.0f}%")

        # Citation quality
        cited = [r for r in ok if r.has_citations]
        knowledge_q = [r for r in ok if r.category == "spiritual_knowledge"]
        print(f"\n  Citation quality:")
        print(f"    Queries w/ citations : {len(cited)}/{len(ok)}")
        if knowledge_q:
            k_cited = sum(1 for r in knowledge_q if r.has_citations)
            print(f"    Knowledge coverage   : {k_cited}/{len(knowledge_q)} ({k_cited/len(knowledge_q)*100:.0f}%)")

        # Cache detection
        cache_q = [r for r in ok if r.category == "cache_duplicate"]
        if len(cache_q) >= 2:
            first, second = cache_q[0].latency_ms, cache_q[1].latency_ms
            speedup = first / second if second > 0 else 0
            print(f"\n  Cache effectiveness:")
            print(f"    First call   : {first:.0f}ms")
            print(f"    Cached call  : {second:.0f}ms")
            print(f"    Speedup      : {speedup:.1f}x")
            print(f"    Cache working: {'✅ Yes' if speedup > 1.5 else '⚠️  Marginal' if speedup > 1.1 else '❌ No'}")

        # Cost estimation
        avg_tokens = statistics.mean([r.response_len / 4 for r in ok]) if ok else 0  # rough token estimate
        print(f"\n  Cost estimation (Sarvam API @ ₹10/1.9M tokens):")
        cost_per_q = avg_tokens * 2 * (10 / 1_900_000)  # 2x for input+output
        print(f"    Avg tokens/query  : ~{avg_tokens:.0f}")
        print(f"    Cost per query    : ₹{cost_per_q:.4f}")
        for dau, label in [(5, "Current"), (100, "Growth"), (500, "Marketing"), (2000, "Viral")]:
            monthly = dau * 20 * 30 * cost_per_q
            print(f"    {label:>12} ({dau:>5} DAU): ₹{monthly:>8.0f}/month")

        # Streaming TTFT summary
        ok_streams = [s for s in stream_results if not s["error"]]
        if ok_streams:
            ttfts = [s["ttft_ms"] for s in ok_streams]
            print(f"\n  Streaming TTFT:")
            print(f"    p50 TTFT : {pct(ttfts, 50):>7.0f}ms")
            print(f"    p95 TTFT : {pct(ttfts, 95):>7.0f}ms")

        # Verdict
        p99 = pct(lats, 99)
        print(f"\n{'═'*80}")
        if p99 < 4000:
            print(f"  ✅ VERDICT: p99={p99:.0f}ms — EXCELLENT. Ship it.")
        elif p99 < 8000:
            print(f"  ⚠️  VERDICT: p99={p99:.0f}ms — OK but monitor. Disable CoVe if >6s.")
        else:
            print(f"  ❌ VERDICT: p99={p99:.0f}ms — TOO SLOW. Prune pipeline layers before marketing.")
        print(f"{'═'*80}\n")
    else:
        print("  ❌ All queries failed.\n")

    # Export
    out = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "backend": url, "n": n, "concurrency": concurrency,
        "p50_ms": pct(lats, 50), "p95_ms": pct(lats, 95), "p99_ms": pct(lats, 99),
        "mean_ms": round(statistics.mean(lats), 1) if lats else None,
        "error_rate": len(errs) / len(results) if results else 1.0,
        "results": [r._asdict() for r in results],
        "stream_results": stream_results,
        "concurrent_latencies": conc_latencies,
    }
    with open("benchmark_results.json", "w") as f:
        json.dump(out, f, indent=2)
    print(f"  Results saved to benchmark_results.json\n")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="AskMukthiGuru RAG benchmark")
    p.add_argument("--url", default="http://localhost:8000")
    p.add_argument("--n", type=int, default=50)
    p.add_argument("--concurrency", type=int, default=5)
    asyncio.run(main(p.parse_args().url, p.parse_args().n, p.parse_args().concurrency))
