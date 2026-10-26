#!/usr/bin/env python3
"""
Live latency benchmark for the first_person_bridge optimisation.
Runs 3 canonical queries and reports stage timings.
Usage: python3 scripts/ops/bench_fp_latency.py
"""
import json, time, sys
import urllib.request, urllib.error

BASE = "http://localhost:8000"

def post_json(url, body):
    data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())

def bench(label, query):
    # Get session token
    sess = post_json(f"{BASE}/api/auth/anon-session", {})
    # Use signed token first (required by /api/chat); fall back to session_id
    token = sess.get("token") or sess.get("session_id") or ""

    payload = {
        "user_message": query,
        "session_id": token,
        "messages": [],
        # NOTE: "stream" is not a supported field on /api/chat?wait=true
    }
    t0 = time.monotonic()
    resp = post_json(f"{BASE}/api/chat?wait=true", payload)
    elapsed = (time.monotonic() - t0) * 1000

    grounding = resp.get("grounding_state", "?")
    route = resp.get("route_decision", resp.get("domain_route", "?"))
    cits = len(resp.get("citations", []))
    st = resp.get("node_timings") or {}
    print(f"\n{'='*60}")
    print(f"  Query : {label}")
    print(f"  Route : {route}")
    print(f"  State : {grounding}")
    print(f"  Citations: {cits}")
    print(f"  Wall time: {elapsed:.0f}ms")
    if st:
        print(f"  Node timings: {json.dumps(st, indent=4)}")
    print(f"{'='*60}")
    return elapsed

if __name__ == "__main__":
    print("Warming up health check...")
    req = urllib.request.Request(f"{BASE}/api/health", method="GET")
    with urllib.request.urlopen(req, timeout=10) as r:
        pass
    time.sleep(1)

    queries = [
        ("Suffering (FP happy path)", "How can one be free from suffering?"),
        ("Comparison (fast short-circuit)", "What is the difference between meditation and contemplation?"),
        ("Distress (compassion path)", "I am feeling restless and anxious about the future, what can I do?"),
    ]
    results = []
    had_failure = False
    for label, q in queries:
        try:
            ms = bench(label, q)
            results.append((label, ms))
        except Exception as e:
            print(f"ERROR on {label}: {e}", file=sys.stderr)
            had_failure = True
        time.sleep(3)  # respect 20/min rate limit

    print("\n\nSUMMARY")
    print("-"*50)
    for label, ms in results:
        status = "🟢 FAST" if ms < 5000 else "🟡 OK" if ms < 8000 else "🔴 SLOW"
        print(f"  {status}  {ms:.0f}ms  — {label}")

    if had_failure:
        sys.exit(1)
