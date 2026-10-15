"""Measure quiet-stack uncached latency on distinct queries against /api/first-person/query."""
import json
import statistics
import time
import urllib.request

DISTINCT_QUESTIONS = [
    "What is a beautiful state?",
    "Why do I keep suffering even when life is good?",
    "How can I stop being angry with my mother?",
    "How do I calm my mind before sleeping?",
    "What is the meaning of Soul Sync?",
    "How to overcome fear of failure?",
    "What is meditation according to Krishnaji?",
    "How does attachment create suffering?",
    "What is the difference between thoughts and awareness?",
    "How can I dissolve guilt and regret?",
    "What is the true nature of love?",
    "How to find inner silence during chaos?",
]

# Bounded HTTP: a hung backend fails the measurement loudly instead of stalling it.
REQUEST_TIMEOUT_S = 120

def main():
    print(f"Measuring quiet-stack latency across {len(DISTINCT_QUESTIONS)} distinct questions...")
    latencies = []
    results = []

    for idx, q in enumerate(DISTINCT_QUESTIONS, 1):
        payload = json.dumps({"query": q, "cache_bypass": True}).encode("utf-8")
        req = urllib.request.Request(
            "http://localhost:8000/api/first-person/query",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        t0 = time.time()
        try:
            with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT_S) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            elapsed = time.time() - t0
            latencies.append(elapsed)
            status = data.get("status")
            is_direct = data.get("is_direct_answer")
            results.append((q, elapsed, status, is_direct))
            print(f"[{idx}/{len(DISTINCT_QUESTIONS)}] {elapsed:.2f}s | status={status} | is_direct={is_direct} | Q: {q}")
        except Exception as e:
            print(f"[{idx}/{len(DISTINCT_QUESTIONS)}] ERROR on {q}: {e}")
        time.sleep(0.5)

    if not latencies:
        print("No successful requests recorded.")
        return

    latencies_sorted = sorted(latencies)
    p50 = statistics.median(latencies_sorted)
    # 95th percentile
    k = (len(latencies_sorted) - 1) * 0.95
    f = int(k)
    c = f + 1 if f + 1 < len(latencies_sorted) else f
    d = k - f
    p95 = latencies_sorted[f] + d * (latencies_sorted[c] - latencies_sorted[f])

    print("=" * 60)
    print(f"Total Requests: {len(latencies)}")
    print(f"Min Latency: {min(latencies):.2f}s")
    print(f"Mean Latency: {statistics.mean(latencies):.2f}s")
    print(f"p50 Latency: {p50:.2f}s")
    print(f"p95 Latency: {p95:.2f}s")
    print(f"Max Latency: {max(latencies):.2f}s")
    print("=" * 60)

if __name__ == "__main__":
    main()
