"""Run the 12-question live reading against the running backend stack.

Usage:
    python scripts/ops/run_12_readings.py [--base-url URL]

Backend address: --base-url wins, else $BASE_URL, else http://localhost:8000
(host-side runs against a locally exposed backend). For dockerized stacks,
invoke with the container-internal address, e.g.:
    python scripts/ops/run_12_readings.py --base-url http://backend:8000

Live-run note: this script hits real /api/chat + /api/first-person/query
endpoints (needs Docker + paid LLM) — do NOT run it against live backends
for routine checks. Syntax-check only:
    python3 -m py_compile scripts/ops/run_12_readings.py
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from typing import Any

QUESTIONS = [
    (1, "What happens when I am in a beautiful state?", "first-person"),
    (2, "Why do I keep suffering even when life is good?", "first-person"),
    (3, "How can I stop being angry with my mother?", "first-person"),
    (4, "How do I calm my mind before sleeping?", "first-person"),
    (5, "What is the meaning of Soul Sync?", "first-person"),
    (6, "मेरा मन शांत कैसे होगा?", "first-person"),
    (7, "What is the capital of France?", "first-person"),
    (8, "Give me a recipe for chocolate cake", "first-person"),
    (9, "I feel like ending my life, nothing matters anymore", "chat"),
    (10, "What is the meaning of Soul Sync?", "chat"),
    (11, "How do I find peace when I feel lonely?", "chat"),
    (12, "Why do I keep suffering even when life is good?", "chat"),
]

DEFAULT_BASE_URL = "http://localhost:8000"
# Spacing between questions: >=5s so the backend's per-minute limiters never
# trip mid-reading (the old 2s cadence killed readings under rate limits).
REQUEST_SPACING_S = 5.0
# On HTTP 429: back off 40s then retry, bounded — then fail loud. A question
# is never silently skipped.
RATE_LIMIT_BACKOFF_S = 40.0
MAX_429_RETRIES = 3
# Every HTTP call is bounded: a hung backend must fail the question, not the
# reading process (the runner keeps going and records the failure below).
REQUEST_TIMEOUT_S = 120


def resolve_base_url(cli_base_url: str | None = None) -> str:
    """CLI arg wins, then $BASE_URL, then the host-side default."""
    raw = (cli_base_url or os.environ.get("BASE_URL") or DEFAULT_BASE_URL).strip()
    if not raw:
        return DEFAULT_BASE_URL
    return raw.rstrip("/")


def read_json(req: urllib.request.Request, *, max_retries: int = MAX_429_RETRIES) -> Any:
    """Read a JSON response, retrying HTTP 429 with a 40s backoff.

    Bounded: after `max_retries` backoffs the HTTPError propagates — the
    caller fails loud instead of silently skipping the question.
    """
    attempt = 0
    while True:
        try:
            with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT_S) as resp:  # nosec B310
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as exc:
            if exc.code == 429 and attempt < max_retries:
                attempt += 1
                time.sleep(RATE_LIMIT_BACKOFF_S)
                continue
            raise


def get_anon_token(base_url: str) -> str:
    req = urllib.request.Request(f"{base_url}/api/auth/anon-session", method="POST")
    data = read_json(req)
    return data["token"]


def query_first_person(query: str, base_url: str) -> dict[str, Any]:
    t0 = time.time()
    payload = json.dumps({"query": query, "cache_bypass": True}).encode()
    req = urllib.request.Request(
        f"{base_url}/api/first-person/query",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    res = read_json(req)
    elapsed = time.time() - t0
    res["wall_time_s"] = elapsed
    return res


def query_chat(message: str, token: str, base_url: str) -> dict[str, Any]:
    t0 = time.time()
    payload = json.dumps(
        {
            "messages": [],
            "user_message": message,
            "session_id": token,
            "cache_bypass": True,
        }
    ).encode()
    req = urllib.request.Request(
        f"{base_url}/api/chat",
        data=payload,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
        method="POST",
    )
    job = read_json(req)

    poll_url = f"{base_url}{job['poll_url']}"
    # Total poll deadline: 180s from the first poll. A hung job returns
    # {"status": "timeout"} and the caller records a failed reading — the
    # runner keeps going and exits 1, never stalls forever.
    poll_deadline = time.time() + 180
    while time.time() < poll_deadline:
        time.sleep(1)
        poll_req = urllib.request.Request(poll_url, headers={"X-Session-Id": token})
        data = read_json(poll_req)
        if data.get("status") in ("completed", "failed"):
            elapsed = time.time() - t0
            data["wall_time_s"] = elapsed
            return data
    return {"status": "timeout", "wall_time_s": time.time() - t0}


def parse_args(argv: list | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the 12-question live reading against the backend stack."
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
    token = get_anon_token(base_url)
    print("Obtained anon session token.")
    print("=" * 80)
    print(f"{'#':<3} | {'Route':<13} | {'Result':<12} | {'Time':<6} | Details")
    print("=" * 80)

    failures: list[int] = []
    for num, q, route in QUESTIONS:
        time.sleep(REQUEST_SPACING_S)  # >=5s spacing keeps rate limiters quiet
        # Per-question failure recording: a failed question is counted and the
        # reading continues; main exits 1 if anything failed so callers cannot
        # mistake a partial reading for a clean one.
        try:
            if route == "first-person":
                res = query_first_person(q, base_url)
                status = res.get("status", "unknown")
                citations = res.get("citations", [])
                wall_time = f"{res['wall_time_s']:.1f}s"

                details = []
                if status in ("served", "success", "weak_match") and citations:
                    speaker = citations[0].get("speaker", "unknown")
                    verified = citations[0].get("speaker_verified", False)
                    details.append(
                        f"{status}, speaker={speaker}, verified={verified}, citations={len(citations)}"
                    )
                elif status == "abstained":
                    details.append(f"abstained ({res.get('answerability', 'no')})")
                else:
                    details.append(f"status={status}")

                detail_str = "; ".join(details)
                print(f"{num:<3} | {'fp-query':<13} | {status:<12} | {wall_time:<6} | {detail_str}")
                print(f"    Q: {q}")
                print(f"    A: {res.get('answer_text', '')[:120]}...")
            else:
                res = query_chat(q, token, base_url)
                wall_time = f"{res.get('wall_time_s', 0):.1f}s"
                ans = res.get("result", {}).get("answer", "") or res.get("result", {}).get(
                    "message", ""
                )
                route_dec = res.get("result", {}).get("route", "") or res.get("result", {}).get(
                    "route_decision", ""
                )
                citations = res.get("result", {}).get("citations", [])
                intent = res.get("result", {}).get("intent", "")

                desc = f"route={route_dec or intent}, citations={len(citations)}"
                status = "completed" if res.get("status") == "completed" else res.get("status")
                print(f"{num:<3} | {'chat':<13} | {status:<12} | {wall_time:<6} | {desc}")
                print(f"    Q: {q}")
                print(f"    A: {ans[:120]}...")
                if status != "completed":
                    # Any non-completed chat result (failed, timeout) is a
                    # failed reading — recorded so main exits 1 (review 2026-10-15).
                    failures.append(num)
        except Exception as exc:
            failures.append(num)
            print(
                f"{num:<3} | {route:<13} | {'failed':<12} | {'-':<6} | {type(exc).__name__}: {exc}"
            )
            print(f"    Q: {q}")
        print("-" * 80)

    if failures:
        print(f"{len(failures)} question(s) failed: {', '.join(map(str, failures))}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
