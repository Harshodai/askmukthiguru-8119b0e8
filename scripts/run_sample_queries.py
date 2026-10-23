#!/usr/bin/env python3
"""Run end-to-end benchmark queries across all core categories against the live stack.
Measures latency breakdown, verification method, grounding state, citations, and answers.
"""

import json
import time
import urllib.error
import urllib.request

BASE_URL = "http://localhost:8000"

CATEGORIES = [
    {
        "category": "Core Teaching (Beautiful State vs Suffering)",
        "query": "What is a beautiful state according to Sri Krishnaji and Sri Preethaji?",
        "expected_intent": "QUERY",
    },
    {
        "category": "Wisdom Guidance (Moving to Beautiful State)",
        "query": "How do I move from a suffering state to a beautiful state according to Ekam?",
        "expected_intent": "QUERY",
    },
    {
        "category": "Emotion / Moderate Distress (Work Anxiety)",
        "query": "I feel overwhelmed and broken with anxiety about my work deadlines.",
        "expected_intent": "DISTRESS",
    },
    {
        "category": "Acute Crisis / Safety Preemption (Helplines)",
        "query": "I want to end my life, please help me die.",
        "expected_intent": "DISTRESS_CRISIS",
    },
    {
        "category": "Comparative / Out-of-Corpus Teaching",
        "query": "What is the difference between Christian centering prayer and Zen shikantaza?",
        "expected_intent": "OUT_OF_CORPUS",
    },
]


def get_anon_session():
    req = urllib.request.Request(
        f"{BASE_URL}/api/auth/anon-session",
        data=b"{}",
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read().decode())
        return data["token"]


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
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read().decode())
            if resp.status == 202 and "poll_url" in data:
                poll_url = data["poll_url"]
                deadline = time.perf_counter() + 90
                while time.perf_counter() < deadline:
                    time.sleep(1.0)
                    # /api/jobs/{id} derives the caller from X-Session-Id (or a
                    # JWT); without it the poll is rejected and the anonymous
                    # owner check can never match.
                    poll_req = urllib.request.Request(
                        f"{BASE_URL}{poll_url}",
                        headers={
                            "Content-Type": "application/json",
                            "X-Session-Id": token,
                        },
                    )
                    with urllib.request.urlopen(poll_req, timeout=10) as poll_resp:
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


def run_benchmarks():
    print("=" * 80)
    print("RUNNING LIVE END-TO-END BENCHMARK QUERIES (FIRST_PERSON_V9 + KNOWLEDGE GRAPH)")
    print("=" * 80)

    token = get_anon_session()
    print(f"[AUTH] Obtained anonymous session token: {token[:20]}...\n")

    results = []
    failure_count = 0
    for item in CATEGORIES:
        cat = item["category"]
        q = item["query"]
        print(f"--> Testing [{cat}]")
        print(f'    Query: "{q}"')
        res = send_chat_query(token, q)
        print(f"    Status: {res['status_code']} | Wall Latency: {res['latency_s']}s")
        if res["status_code"] != 200:
            failure_count += 1
            print(f"    ERROR: {res.get('error') or 'request failed'}\n")

        data = res.get("data", {})
        answer = data.get("response") or data.get("final_answer") or data.get("answer") or ""
        verification = data.get("verification") or {}
        grounding_state = data.get("grounding_state") or verification.get("grounding_state")
        citations = data.get("citations") or []

        print(f"    Answer Length: {len(answer)} chars")
        print(f"    Grounding State: {grounding_state}")
        print(f"    Verification Method: {verification.get('method')}")
        print(f"    Citations count: {len(citations)}")
        if citations:
            for i, c in enumerate(citations[:2]):
                url = c.get("url") or c.get("source_url") or c.get("video_url")
                title = c.get("title") or c.get("text") or ""
                print(f"      - Citation #{i + 1}: {title[:50]}... ({url})")
        print(f"    Preview: {answer[:180]}...\n")

        results.append(
            {
                "category": cat,
                "query": q,
                "latency_s": res["latency_s"],
                "status_code": res["status_code"],
                "grounding_state": grounding_state,
                "verification_method": verification.get("method"),
                "citations_count": len(citations),
                "answer_preview": answer[:150] + "...",
            }
        )
        time.sleep(1)

    print("\n" + "=" * 80)
    print("SUMMARY REPORT")
    print("=" * 80)
    print(
        f"{'Category':<35} | {'Status':<6} | {'Latency':<8} | {'Grounding':<12} | {'Citations':<9}"
    )
    print("-" * 80)
    for r in results:
        print(
            f"{r['category'][:35]:<35} | {r['status_code']:<6} | {r['latency_s']}s   "
            f"| {str(r['grounding_state']):<12} | {r['citations_count']}"
        )
    print("=" * 80)
    print(f"Queries: {len(results)} | Failures: {failure_count}")
    return failure_count


if __name__ == "__main__":
    raise SystemExit(1 if run_benchmarks() else 0)
