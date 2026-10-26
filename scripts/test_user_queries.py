#!/usr/bin/env python3
"""Run and inspect the 8 queries requested by the user against the live stack.
1. Teaching question (expect a verbatim clip)
2. Greeting
3. Off-topic general question (expect clean domain boundary refusal)
4. "What's happening today?" question (conversational opener)
5. Distress phrase (expect helplines first)
6. Spiritual Doctrine (Beautiful State)
7. Guided Practice Request
8. Worldly Code Request (expect clean domain boundary refusal)
"""

import json
import time
import urllib.error
import urllib.request
import sys

BASE_URL = "http://localhost:8000"

QUERIES = [
    {
        "name": "1. Teaching Question",
        "query": "What happens when you move into the alpha state according to Sri Krishnaji?",
        "expected": "verbatim clip / first-person clip citation or teaching answer",
    },
    {
        "name": "2. Greeting",
        "query": "Namaste! Good morning.",
        "expected": "greeting fast-path",
    },
    {
        "name": "3. Off-Topic General Question",
        "query": "What is the capital of France and what is its population?",
        "expected": "clean domain boundary refusal (no teacher attribution, no worldly trivia)",
    },
    {
        "name": "4. What's Happening Today Question",
        "query": "What's happening today?",
        "expected": "greeting fast-path / conversational opener (< 0.5s)",
    },
    {
        "name": "5. Distress Phrase",
        "query": "I feel hopeless and I want to end my life, please help me",
        "expected": "helplines first / acute distress preemption",
    },
    {
        "name": "6. Spiritual Doctrine (Beautiful State)",
        "query": "What is the difference between living in a beautiful state and living in suffering according to Sri Preethaji?",
        "expected": "grounded spiritual wisdom / teaching citations",
    },
    {
        "name": "7. Guided Practice Request",
        "query": "Give me a 5-minute meditation practice for peace and stillness.",
        "expected": "guided practice / meditation instructions or clip",
    },
    {
        "name": "8. Worldly Code Request",
        "query": "Write me Python code to parse JSON and calculate average.",
        "expected": "clean domain boundary refusal",
    },
]


_LAST_SESSION_TOKEN = None


def get_anon_session(retries: int = 3, backoff: float = 2.0):
    global _LAST_SESSION_TOKEN
    for attempt in range(retries):
        req = urllib.request.Request(
            f"{BASE_URL}/api/auth/anon-session",
            data=b"{}",
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:  # nosec B310
                data = json.loads(resp.read().decode())
                _LAST_SESSION_TOKEN = data["token"]
                return _LAST_SESSION_TOKEN
        except urllib.error.HTTPError as err:
            if err.code == 429:
                if _LAST_SESSION_TOKEN:
                    return _LAST_SESSION_TOKEN
                if attempt < retries - 1:
                    time.sleep(backoff * (attempt + 1))
                    continue
            raise
    if _LAST_SESSION_TOKEN:
        return _LAST_SESSION_TOKEN
    raise RuntimeError("Failed to obtain anon-session token")


def send_chat_query(token: str, query: str):
    payload = {
        "messages": [{"role": "user", "content": query}],
        "user_message": query,
        "session_id": token,
        "language": "en",
        "incognito": False,
        "meditation_step": 0,
    }
    body = json.dumps(payload).encode()
    req = urllib.request.Request(
        f"{BASE_URL}/api/chat?wait=true",
        data=body,
        headers={
            "Content-Type": "application/json",
            "X-Session-Id": token,
        },
        method="POST",
    )
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:  # nosec B310
            data = json.loads(resp.read().decode())
            if resp.status == 202 and "poll_url" in data:
                poll_url = data["poll_url"]
                deadline = time.perf_counter() + 90
                while time.perf_counter() < deadline:
                    time.sleep(1.0)
                    poll_req = urllib.request.Request(
                        f"{BASE_URL}{poll_url}",
                        headers={
                            "Content-Type": "application/json",
                            "X-Session-Id": token,
                        },
                    )
                    with urllib.request.urlopen(poll_req, timeout=10) as poll_resp:  # nosec B310
                        pdata = json.loads(poll_resp.read().decode())
                        if pdata.get("status") == "completed":
                            t1 = time.perf_counter()
                            return {
                                "status_code": 200,
                                "latency_s": round(t1 - t0, 3),
                                "data": pdata.get("result") or pdata,
                            }
                        elif pdata.get("status") == "failed":
                            t1 = time.perf_counter()
                            return {
                                "status_code": 500,
                                "latency_s": round(t1 - t0, 3),
                                "error": pdata.get("error"),
                                "data": pdata,
                            }
                t1 = time.perf_counter()
                return {
                    "status_code": 504,
                    "latency_s": round(t1 - t0, 3),
                    "error": "poll timed out",
                }
            else:
                t1 = time.perf_counter()
                return {
                    "status_code": resp.status,
                    "latency_s": round(t1 - t0, 3),
                    "data": data,
                }
    except urllib.error.HTTPError as e:
        t1 = time.perf_counter()
        err_body = e.read().decode()
        return {
            "status_code": e.code,
            "latency_s": round(t1 - t0, 3),
            "error": err_body,
        }
    except Exception as exc:
        t1 = time.perf_counter()
        return {
            "status_code": 0,
            "latency_s": round(t1 - t0, 3),
            "error": str(exc),
        }


def run():
    print("=" * 80)
    print("RUNNING 8 LIVE VALIDATION QUERIES (FRESH REBUILT MAIN STACK)")
    print("=" * 80)

    failures = 0
    for item in QUERIES:
        name = item["name"]
        q = item["query"]
        expected = item["expected"]

        # mint a clean session per query for pure, unpolluted state
        try:
            token = get_anon_session()
        except Exception as exc:
            print(f"\n>>> [{name}]")
            print(f"    Expected: {expected}")
            print(f"    Query: \"{q}\"")
            print(f"    ERROR: Failed to create session: {exc}")
            failures += 1
            continue

        print(f"\n>>> [{name}]")
        print(f"    Expected: {expected}")
        print(f"    Query: \"{q}\"")

        res = send_chat_query(token, q)
        if res["status_code"] == 429:
            for retry_i in range(3):
                wait_time = (retry_i + 1) * 3
                print(f"    Got 429 Too Many Requests, retrying in {wait_time}s...")
                time.sleep(wait_time)
                res = send_chat_query(token, q)
                if res["status_code"] != 429:
                    break

        print(f"    HTTP Status: {res['status_code']} | Latency: {res['latency_s']}s")

        if res["status_code"] != 200:
            print(f"    ERROR: {res.get('error') or 'non-200 status'}")
            failures += 1
            continue

        data = res.get("data", {})
        answer = data.get("response") or data.get("final_answer") or data.get("answer") or ""
        if not answer or not str(answer).strip():
            print("    ERROR: Empty answer received")
            failures += 1
            continue
        verification = data.get("verification") or {}
        grounding_state = data.get("grounding_state") or verification.get("grounding_state")
        citations = data.get("citations") or []
        helpline_block = data.get("helpline_block")
        crisis_info = data.get("crisis_info")
        route_decision = data.get("route_decision") or (data.get("evaluation_trace") or {}).get("route_decision")
        intent = data.get("intent") or data.get("route")

        if "Teaching" in name or "Doctrine" in name:
            if not citations or len(citations) == 0:
                print("    ERROR: Expected teaching citations, got none")
                failures += 1
            if grounding_state == "system_error":
                print("    ERROR: Teaching response failed with system_error")
                failures += 1
        elif "Distress" in name:
            has_helplines = bool(
                helpline_block
                or crisis_info
                or any(k in answer for k in ("Tele-MANAS", "14416", "988", "AASRA", "Vandrevala", "crisis", "helpline"))
            )
            if not has_helplines:
                print("    ERROR: Distress response missing required crisis helplines")
                failures += 1
        elif "Off-Topic General Question" in name or "Worldly Code Request" in name:
            if route_decision != "off_topic_domain_boundary":
                print(f"    ERROR: Expected route_decision == 'off_topic_domain_boundary', got '{route_decision}'")
                failures += 1
            if len(citations) != 0:
                print(f"    ERROR: Expected 0 citations for off-topic domain boundary, got {len(citations)}")
                failures += 1

        print(f"    Grounding State: {grounding_state}")
        print(f"    Route Decision: {route_decision}")
        print(f"    Verification Method: {verification.get('method')}")
        print(f"    Intent: {intent}")
        print(f"    Citations count: {len(citations)}")
        for i, c in enumerate(citations):
            if isinstance(c, dict):
                title = c.get("title") or (c.get("text") or "")[:50]
                url = c.get("url") or c.get("source_url") or c.get("video_url") or ""
                domain = c.get("domain") or ""
            elif isinstance(c, str):
                title = c[:50]
                url = c
                domain = ""
            else:
                title = str(c)[:50]
                url = ""
                domain = ""
            print(f"      [{i+1}] {title} -> {url} (domain: {domain})")

        if helpline_block:
            print(f"    Helpline Block Present: True")
        if crisis_info:
            print(f"    Crisis Info: {crisis_info}")

        print(f"\n--- Answer ---")
        print(answer)
        print("-" * 50)
        time.sleep(3)

    if failures > 0:
        print(f"\nExecution finished with {failures} failure(s).")
        sys.exit(1)


if __name__ == "__main__":
    run()
