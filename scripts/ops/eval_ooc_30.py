"""Run out-of-corpus questions through /api/first-person/query and check for 0 leaks.

Usage:
    python scripts/ops/eval_ooc_30.py [--base-url URL]

Backend address: --base-url wins, else $BASE_URL, else http://localhost:8000
(host-side runs against a locally exposed backend). For dockerized stacks,
invoke with the container-internal address, e.g.:
    python scripts/ops/eval_ooc_30.py --base-url http://backend:8000

Live-run note: this script hits the real /api/first-person/query endpoint
(needs Docker + paid LLM for the relevance scorer) — do NOT run it against
live backends for routine checks. Each of the 32 questions is one billable
scorer pass plus pacing sleeps; a full run takes ~5 minutes. Syntax-check only:
    python3 -m py_compile scripts/ops/eval_ooc_30.py
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request

DEFAULT_BASE_URL = "http://localhost:8000"

# Finite per-request timeout so one hung backend can't stall the whole run;
# a timeout lands in the same `failed` path as any other request error.
REQUEST_TIMEOUT_S = 30

# Pacing (review 2026-10-15): 5s between requests keeps the backend's rate
# limiters quiet; a 429 gets a bounded backoff (10s + 30s = 40s cap) before
# the request is recorded as failed — never an unbounded retry loop.
REQUEST_SPACING_S = 5
_429_BACKOFF_S = (10, 30)

OOC_QUESTIONS = [
    "What is the capital of Australia?",
    "How far is the Moon from the Earth?",
    "Who wrote the novel Pride and Prejudice?",
    "What is the population of Japan?",
    "When did World War Two end?",
    "Give me a recipe for chocolate cake",
    "What is the capital of France?",
    "How do I fix a leaking kitchen faucet?",
    "What is the speed of light in vacuum?",
    "Who won the 2022 FIFA World Cup?",
    "Explain quantum superposition in simple terms",
    "What are the main ingredients of spaghetti carbonara?",
    "How many bones are in the adult human body?",
    "What is the chemical formula for sulfuric acid?",
    "Who painted the Mona Lisa?",
    "What is the currency of Brazil?",
    "How does a four-stroke internal combustion engine work?",
    "What is the boiling point of liquid nitrogen?",
    "Who discovered penicillin?",
    "How many players are on a basketball team on court?",
    "What is the tallest mountain in North America?",
    "What year was the Eiffel Tower completed?",
    "How do I calculate the area of a circle?",
    "What is the difference between Python and JavaScript?",
    "What is the distance between New York and London?",
    "Who is the current Prime Minister of Canada?",
    "What causes solar eclipses?",
    "How many chromosomes do humans have?",
    "What is the capital of South Africa?",
    "What is Moore's Law in computing?",
    "How do airplanes generate lift?",
    "What is the atomic number of Gold?",
]


def _post_json_with_429_backoff(req) -> dict:
    """urlopen + JSON decode with a bounded 429 retry (10s + 30s = 40s cap).

    Non-429 errors and exhausted backoff re-raise to the caller's `failed`
    path — a request only lands there after every allowed retry.
    """
    attempt = 0
    while True:
        try:
            with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT_S) as resp:  # nosec B310
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as exc:
            if exc.code != 429 or attempt >= len(_429_BACKOFF_S):
                raise
            backoff = _429_BACKOFF_S[attempt]
            attempt += 1
            print(f"    429 rate-limited — backing off {backoff}s before retry")
            time.sleep(backoff)


def resolve_base_url(cli_base_url: str | None = None) -> str:
    """CLI arg wins, then $BASE_URL, then the host-side default."""
    raw = (cli_base_url or os.environ.get("BASE_URL") or DEFAULT_BASE_URL).strip()
    if not raw:
        return DEFAULT_BASE_URL
    return raw.rstrip("/")


def parse_args(argv: list | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run out-of-corpus questions against the backend stack."
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


def main(argv: list | None = None):
    args = parse_args(argv)
    base_url = resolve_base_url(args.base_url)
    print(f"Backend: {base_url}")
    print(f"Testing {len(OOC_QUESTIONS)} out-of-corpus questions...")
    leaks = []
    failed = []
    times = []

    for idx, q in enumerate(OOC_QUESTIONS, 1):
        payload = json.dumps({"query": q, "cache_bypass": True}).encode()
        req = urllib.request.Request(
            f"{base_url}/api/first-person/query",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        t0 = time.time()
        try:
            data = _post_json_with_429_backoff(req)
            el = time.time() - t0
            times.append(el)
            status = data.get("status")
            cits = data.get("citations", [])

            if status != "abstained" or len(cits) > 0:
                print(
                    f"[{idx}/{len(OOC_QUESTIONS)}] LEAK DETECTED! Q: {q} | status={status} | citations={len(cits)}"
                )
                leaks.append((q, status, len(cits)))
            else:
                print(f"[{idx}/{len(OOC_QUESTIONS)}] OK (abstained in {el:.2f}s) | Q: {q}")
        except Exception as e:
            print(f"[{idx}/{len(OOC_QUESTIONS)}] ERROR: {q} -> {e}")
            failed.append((q, str(e)[:120]))
        time.sleep(REQUEST_SPACING_S)

    print("=" * 60)
    print(f"Total OOC Tested: {len(OOC_QUESTIONS)}")
    print(f"Total Leaks: {len(leaks)}")
    print(f"Total Failed (not evaluated): {len(failed)}")
    for q, err in failed:
        print(f"  FAILED: {q} -> {err}")
    print(f"Leak Rate: {len(leaks) / len(OOC_QUESTIONS) * 100:.1f}%")
    if times:
        print(
            f"Latency: min={min(times):.2f}s, avg={sum(times) / len(times):.2f}s, max={max(times):.2f}s"
        )
    print("=" * 60)

    if leaks:
        print("FAIL: Out-of-corpus leaks found!")
        return 1
    if failed:
        print("FAIL: some questions could not be evaluated (see FAILED lines)!")
        return 1
    print("SUCCESS: Zero out-of-corpus leaks (100% honest abstention).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
