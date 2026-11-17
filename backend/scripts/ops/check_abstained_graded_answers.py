#!/usr/bin/env python3
"""Re-evaluate all abstained questions from graded-9-live against the live backend.

Evaluates route decisions, grounding states, citations, and reasons.
Per Invariant X29, retries on 429 and throttles between queries.
"""

import json
import os
import sys
import time
import requests

BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")
BENCHMARK_SECRET = os.getenv(
    "BENCHMARK_SECRET", "super-secret-jwt-token-with-at-least-32-characters-long"
)
DEFAULT_ROWS = os.path.expanduser(
    "~/mukthiguru_attribution_data/graded_runs/20261115-graded-9-live/rows.jsonl"
)

def acquire_session(session: requests.Session) -> str:
    """Acquire a persistent anonymous session with backoff."""
    for attempt in range(8):
        try:
            resp = session.post(f"{BASE_URL}/api/auth/anon-session", json={})
            if resp.status_code == 200:
                token = resp.json().get("token")
                if token:
                    return token
            elif resp.status_code == 429:
                print(f"Rate limited on anon-session, sleeping 4s (attempt {attempt+1})...")
                time.sleep(4)
        except Exception:
            time.sleep(2)
    raise RuntimeError("Failed to acquire anonymous session token after 8 attempts")

def load_abstained_questions(rows_path: str):
    items = []
    with open(rows_path) as f:
        for line in f:
            if not line.strip():
                continue
            r = json.loads(line)
            if r.get("answerable") and r.get("route") in ("first_person_abstain", "blocked"):
                items.append({
                    "id": r.get("id"),
                    "question": r.get("question"),
                    "prev_route": r.get("route"),
                    "prev_grounding": r.get("grounding"),
                    "set": r.get("set", "unknown"),
                })
    return items

def main():
    rows_path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_ROWS
    if not os.path.exists(rows_path):
        print(f"Error: rows file not found at {rows_path}")
        sys.exit(1)

    questions = load_abstained_questions(rows_path)
    print(f"Loaded {len(questions)} abstained answerable questions from {rows_path}")

    session = requests.Session()
    token = acquire_session(session)
    print(f"Acquired anonymous session token: {token[:16]}...")

    headers = {
        "Content-Type": "application/json",
        "X-Session-Id": token,
        "X-Test-Key": BENCHMARK_SECRET,
    }

    results = []
    now_served = 0
    still_abstained = 0

    out_file = os.path.join(
        os.path.dirname(__file__), "..", "..", "audits", "evidence", "abstained_graded9_reeval.json"
    )
    os.makedirs(os.path.dirname(out_file), exist_ok=True)

    print("\n" + "=" * 90)
    print(f"STARTING RE-EVALUATION OF {len(questions)} ABSTAINED GRADED QUESTIONS")
    print("=" * 90)

    for idx, q in enumerate(questions, 1):
        payload = {
            "messages": [{"role": "user", "content": q["question"]}],
            "user_message": q["question"],
            "session_id": token,
            "incognito": True,
        }

        data = None
        elapsed = 0.0
        for attempt in range(5):
            t0 = time.time()
            try:
                c_resp = session.post(f"{BASE_URL}/api/chat", headers=headers, json=payload, timeout=45)
                elapsed = round(time.time() - t0, 2)
                if c_resp.status_code == 429:
                    print(f"Rate limited on /api/chat, sleeping 4s (attempt {attempt+1})...")
                    time.sleep(4)
                    continue
                elif c_resp.status_code == 200:
                    data = c_resp.json()
                    break
                elif c_resp.status_code == 202:
                    job_id = c_resp.json().get("job_id")
                    for _ in range(40):
                        time.sleep(2)
                        j = session.get(f"{BASE_URL}/api/jobs/{job_id}", headers=headers).json()
                        if j.get("status") == "completed":
                            data = j.get("result", {})
                            break
                        elif j.get("status") in ("failed", "error"):
                            data = {"error": j.get("error"), "status": "failed"}
                            break
                    elapsed = round(time.time() - t0, 2)
                    break
                else:
                    data = {"error": c_resp.text, "status_code": c_resp.status_code}
                    break
            except Exception as exc:
                print(f"Request exception on {q['id']}: {exc}, retrying...")
                time.sleep(3)

        route = data.get("route_decision", "unknown") if data else "unknown"
        grounding = data.get("grounding_state", "unknown") if data else "unknown"
        citations = data.get("citations", []) if data else []
        n_cites = len(citations)
        abstain_reason = data.get("route_metadata", {}).get("abstain_reason") if data else None
        response_text = data.get("response", "") if data else ""
        preview = response_text[:120].replace("\n", " ")

        rec = {
            "id": q["id"],
            "question": q["question"],
            "set": q["set"],
            "prev_route": q["prev_route"],
            "new_route": route,
            "new_grounding": grounding,
            "citations_count": n_cites,
            "citation_titles": [c.get("title") for c in citations if isinstance(c, dict)],
            "abstain_reason": abstain_reason,
            "elapsed_s": elapsed,
            "response_preview": preview,
        }
        results.append(rec)

        if route == "first_person_bridge" and grounding == "grounded":
            now_served += 1
            status_str = f"🎉 SERVED (cites={n_cites})"
        else:
            still_abstained += 1
            status_str = f"❌ ABSTAIN ({route}, reason={abstain_reason})"

        print(f"[{idx:02d}/{len(questions):02d}] {q['id']} ({elapsed:4.1f}s): {status_str} | Q: {q['question'][:55]}")

        # Save progress incrementally
        with open(out_file, "w") as f:
            json.dump({"total": len(questions), "now_served": now_served, "still_abstained": still_abstained, "results": results}, f, indent=2)

        time.sleep(1.0)

    print("\n" + "=" * 90)
    print("RE-EVALUATION SUMMARY:")
    print(f"Total Previously Abstained: {len(questions)}")
    print(f"Now Served (Grounded):      {now_served} ({now_served/len(questions)*100:.1f}%)")
    print(f"Still Abstained:            {still_abstained} ({still_abstained/len(questions)*100:.1f}%)")
    print(f"Detailed results saved to:  {out_file}")
    print("=" * 90)

if __name__ == "__main__":
    main()
