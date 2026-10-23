"""Measure quiet-stack uncached latency on distinct queries against /api/first-person/query.

Usage:
    python scripts/ops/measure_quiet_stack_latency.py [--base-url URL]

Backend address: --base-url wins, else $BASE_URL, else http://localhost:8000
(host-side runs against a locally exposed backend). For dockerized stacks,
invoke with the container-internal address, e.g.:
    python scripts/ops/measure_quiet_stack_latency.py --base-url http://backend:8000

Live-run note: this script hits the real /api/first-person/query endpoint
(needs Docker + paid LLM for the relevance scorer) — do NOT run it against
live backends for routine checks. Each of the 12 questions is one billable
scorer pass plus pacing sleeps. Syntax-check only:
    python3 -m py_compile scripts/ops/measure_quiet_stack_latency.py
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import time
import urllib.error
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

# Pacing + bounded 429 backoff (review 2026-10-15): same behavior as
# eval_ooc_30.py — 5s between requests; 10s + 30s = 40s backoff cap before a
# request is counted as failed (never an unbounded retry loop).
REQUEST_SPACING_S = 5
_429_BACKOFF_S = (10, 30)

DEFAULT_BASE_URL = "http://localhost:8000"


def resolve_base_url(cli_base_url: str | None = None) -> str:
    """CLI arg wins, then $BASE_URL, then the host-side default."""
    raw = (cli_base_url or os.environ.get("BASE_URL") or DEFAULT_BASE_URL).strip()
    if not raw:
        return DEFAULT_BASE_URL
    return raw.rstrip("/")


def parse_args(argv: list | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Measure quiet-stack latency against the backend stack."
    )
    parser.add_argument(
        "--base-url",
        default=None,
        help=(
            "Backend base URL (overrides $BASE_URL, default "
            f"{DEFAULT_BASE_URL}). Use the container-internal address for "
            "dockerized stacks, e.g. http://backend:8000."
        ),
    )
    return parser.parse_args(argv)


def _post_json_with_429_backoff(req) -> dict:
    attempt = 0
    while True:
        try:
            with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT_S) as resp:  # nosec B310
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code != 429 or attempt >= len(_429_BACKOFF_S):
                raise
            backoff = _429_BACKOFF_S[attempt]
            attempt += 1
            print(f"    429 rate-limited — backing off {backoff}s before retry")
            time.sleep(backoff)


def main(argv: list | None = None) -> int:
    args = parse_args(argv)
    base_url = resolve_base_url(args.base_url)
    print(f"Backend: {base_url}")
    print(f"Measuring quiet-stack latency across {len(DISTINCT_QUESTIONS)} distinct questions...")
    latencies = []
    results = []
    failed: list[str] = []

    for idx, q in enumerate(DISTINCT_QUESTIONS, 1):
        payload = json.dumps({"query": q, "cache_bypass": True}).encode("utf-8")
        req = urllib.request.Request(
            f"{base_url}/api/first-person/query",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        t0 = time.time()
        try:
            data = _post_json_with_429_backoff(req)
            elapsed = time.time() - t0
            latencies.append(elapsed)
            status = data.get("status")
            is_direct = data.get("is_direct_answer")
            results.append((q, elapsed, status, is_direct))
            print(
                f"[{idx}/{len(DISTINCT_QUESTIONS)}] {elapsed:.2f}s | status={status} | is_direct={is_direct} | Q: {q}"
            )
        except Exception as e:
            print(f"[{idx}/{len(DISTINCT_QUESTIONS)}] ERROR on {q}: {e}")
            failed.append(q)
        time.sleep(REQUEST_SPACING_S)

    if not latencies:
        print(f"No successful requests recorded. Failed: {len(failed)}")
        return 1

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
    print(f"Total Failed: {len(failed)}")
    print(f"Min Latency: {min(latencies):.2f}s")
    print(f"Mean Latency: {statistics.mean(latencies):.2f}s")
    print(f"p50 Latency: {p50:.2f}s")
    print(f"p95 Latency: {p95:.2f}s")
    print(f"Max Latency: {max(latencies):.2f}s")
    print("=" * 60)
    if failed:
        print(f"FAIL: {len(failed)} request(s) failed.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
