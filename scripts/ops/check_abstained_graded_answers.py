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


def acquire_session(session: requests.Session):
    """Acquire a persistent anonymous session token, or None.

    There is no fabricated fallback: a made-up session value is not a token
    the auth/quota dependencies accept, and recording its 400/401 as an
    abstention would corrupt the evaluation artifact.
    """
    for _attempt in range(4):
        try:
            resp = session.post(f"{BASE_URL}/api/auth/anon-session", json={})
            if resp.status_code == 200:
                token = resp.json().get("token")
                if token:
                    return token
            elif resp.status_code == 429:
                print("Rate limited on anon-session; no anonymous identity available.")
                return None
        except Exception:
            time.sleep(1)
    return None


def _benchmark_headers() -> dict:
    return {
        "Content-Type": "application/json",
        "X-User-Id": "benchmark-admin-user",
        "X-Test-Key": BENCHMARK_SECRET,
    }


def _identity_accepted(session: requests.Session, headers: dict) -> bool:
    """Probe the job route to establish that this identity is accepted.

    ``/api/jobs/<unknown>`` runs the same auth + scoped-identity dependencies
    as ``/api/chat`` and ``/api/jobs/{id}``. A 404 means the identity was
    accepted and the job simply does not exist; 400/401/403 means the
    identity (or session token) is rejected and no evaluation may start.
    """
    probe_headers = dict(headers)
    try:
        resp = session.get(
            f"{BASE_URL}/api/jobs/__auth_preflight__", headers=probe_headers, timeout=15
        )
    except Exception as exc:
        print(f"Auth preflight transport failure: {exc}")
        return False
    if resp.status_code == 200:
        return True
    if resp.status_code == 404:
        # 404 means the auth passed and the job router looked up the synthetic id
        return True
    print(f"Auth preflight rejected identity: HTTP {resp.status_code} {resp.text[:200]}")
    return False


def resolve_identity(session: requests.Session):
    """Return ``(headers, session_id)`` for an accepted identity, else ``(None, None)``.

    Prefer the benchmark backdoor (X-Test-Key + X-User-Id, no session id):
    sending an anonymous session alongside the test key demotes the identity
    to ``anon:<token>`` and trips the anonymous quota
    (L-TESTAUTH-ANON-SESSION-QUOTA-COLLISION-1).
    """
    headers = _benchmark_headers()
    if _identity_accepted(session, headers):
        return headers, None
    token = acquire_session(session)
    if token:
        anon_headers = {"Content-Type": "application/json", "X-Session-Id": token}
        if _identity_accepted(session, anon_headers):
            return anon_headers, token
    return None, None


def load_abstained_questions(rows_path: str):
    items = []
    with open(rows_path) as f:
        for line in f:
            if not line.strip():
                continue
            r = json.loads(line)
            if r.get("answerable") and r.get("route") in ("first_person_abstain", "blocked"):
                items.append(
                    {
                        "id": r.get("id"),
                        "question": r.get("question"),
                        "prev_route": r.get("route"),
                        "prev_grounding": r.get("grounding"),
                        "set": r.get("set", "unknown"),
                    }
                )
    return items


def main():
    rows_path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_ROWS
    if not os.path.exists(rows_path):
        print(f"Error: rows file not found at {rows_path}")
        sys.exit(1)

    questions = load_abstained_questions(rows_path)
    print(f"Loaded {len(questions)} abstained answerable questions from {rows_path}")

    session = requests.Session()
    headers, token = resolve_identity(session)
    if headers is None:
        print(
            "Error: no accepted identity. Set X-Test-Key (BENCHMARK_SECRET with "
            "ENABLE_TEST_AUTH=true, IS_PRODUCTION=false) or provide a working "
            "/api/auth/anon-session. Refusing to start so auth errors are not "
            "recorded as abstentions."
        )
        sys.exit(2)
    print(f"Identity accepted: {'benchmark X-Test-Key' if token is None else 'anonymous session'}")

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
            "incognito": True,
        }
        if token:
            payload["session_id"] = token

        data = None
        elapsed = 0.0
        for attempt in range(5):
            t0 = time.time()
            try:
                c_resp = session.post(
                    f"{BASE_URL}/api/chat", headers=headers, json=payload, timeout=45
                )
                elapsed = round(time.time() - t0, 2)
                if c_resp.status_code == 429:
                    print(f"Rate limited on /api/chat, sleeping 4s (attempt {attempt + 1})...")
                    time.sleep(4)
                    continue
                elif c_resp.status_code in (400, 401, 403):
                    print(
                        f"Error: /api/chat rejected the identity (HTTP {c_resp.status_code}): "
                        f"{c_resp.text[:300]}. Aborting without writing the artifact."
                    )
                    sys.exit(2)
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
                        elif j.get("status") in ("failed", "error", "cancelled"):
                            print(
                                f"Error: job {job_id} for {q['id']} ended {j.get('status')}: "
                                f"{j.get('error')}. Aborting without writing the artifact."
                            )
                            sys.exit(2)
                    elapsed = round(time.time() - t0, 2)
                    break
                else:
                    print(
                        f"Error: /api/chat returned HTTP {c_resp.status_code}: "
                        f"{c_resp.text[:300]}. Aborting without writing the artifact."
                    )
                    sys.exit(2)
            except SystemExit:
                raise
            except Exception as exc:
                print(f"Request exception on {q['id']}: {exc}, retrying...")
                time.sleep(3)

        if data is None:
            print(
                f"Error: no chat response for {q['id']} after retries. "
                "Aborting without recording a false abstention."
            )
            sys.exit(2)

        route = data.get("route_decision", "unknown") if data else "unknown"
        grounding = data.get("grounding_state", "unknown") if data else "unknown"
        citations = data.get("citations", []) if data else []
        n_cites = len(citations)
        route_meta = data.get("route_metadata") or {} if data else {}
        abstain_reason = route_meta.get("abstain_reason")
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

        print(
            f"[{idx:02d}/{len(questions):02d}] {q['id']} ({elapsed:4.1f}s): {status_str} | Q: {q['question'][:55]}"
        )

        # Save progress incrementally to checkpoint
        chk_file = f"{out_file}.checkpoint"
        with open(chk_file, "w") as f:
            json.dump(
                {
                    "total": len(questions),
                    "now_served": now_served,
                    "still_abstained": still_abstained,
                    "results": results,
                },
                f,
                indent=2,
            )

        time.sleep(1.0)

    import shutil

    chk_file = f"{out_file}.checkpoint"
    if os.path.exists(chk_file):
        shutil.move(chk_file, out_file)

    print("\n" + "=" * 90)
    print("RE-EVALUATION SUMMARY:")
    print(f"Total Previously Abstained: {len(questions)}")
    print(f"Now Served (Grounded):      {now_served} ({now_served / len(questions) * 100:.1f}%)")
    print(
        f"Still Abstained:            {still_abstained} ({still_abstained / len(questions) * 100:.1f}%)"
    )
    print(f"Detailed results saved to:  {out_file}")
    print("=" * 90)


if __name__ == "__main__":
    main()
