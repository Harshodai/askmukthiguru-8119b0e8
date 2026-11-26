"""Multi-Persona Interaction & Simulation Script.

Simulates 3 distinct personas:
1. Spiritual Seeker: Inner pain, meditation practice, practice feedback, saving answers.
2. Intellectual Inquirer: Ego, consciousness, relationship dynamics across multiple turns.
3. Stressed Student: Exam anxiety, focus, fear, 3-minute pre-test practice.
"""

import json
import os
import time

import requests

BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")


def poll_job(session, job_id, token, max_retries=40, delay=2):
    url = f"{BASE_URL}/api/jobs/{job_id}"
    headers = {"X-Session-Id": token}
    for _attempt in range(max_retries):
        resp = session.get(url, headers=headers)
        if resp.status_code == 200:
            data = resp.json()
            if data.get("status") == "completed":
                return data.get("result", {})
            if data.get("status") in ("failed", "error"):
                return {"error": data.get("error", "Job failed"), "status": data.get("status")}
        time.sleep(delay)
    return {"error": "Polling timed out", "status": "timeout"}


def send_chat_turn(session, token, messages, user_msg):
    url = f"{BASE_URL}/api/chat"
    headers = {"Content-Type": "application/json", "X-Session-Id": token}
    payload = {
        "messages": messages,
        "user_message": user_msg,
        "session_id": token,
        "incognito": False,
    }
    start = time.time()
    resp = session.post(url, headers=headers, json=payload)
    elapsed = round(time.time() - start, 2)

    if resp.status_code == 200:
        data = resp.json()
        return data, elapsed
    elif resp.status_code == 202:
        job_id = resp.json().get("job_id")
        result = poll_job(session, job_id, token)
        total_elapsed = round(time.time() - start, 2)
        return result, total_elapsed
    else:
        return {"error": resp.text, "status_code": resp.status_code}, elapsed


def create_anon_session(session):
    resp = session.post(f"{BASE_URL}/api/auth/anon-session", json={})
    resp.raise_for_status()
    data = resp.json()
    return data.get("session_id"), data.get("token")


def run_simulation():
    results = {}

    # -------------------------------------------------------------
    # PERSONA 1: Spiritual Seeker
    # -------------------------------------------------------------
    print("\n" + "=" * 60)
    print("RUNNING PERSONA 1: Spiritual Seeker (Inner pain & Meditation)")
    print("=" * 60)
    s1 = requests.Session()
    s1_id, s1_token = create_anon_session(s1)
    print(f"Persona 1 Session Created: {s1_id}")

    # Daily ritual check
    ritual = s1.get(f"{BASE_URL}/api/ritual/today").json()
    print(f"Checked Daily Ritual: {ritual.get('teaching', {}).get('source_label')}")

    # Turn 1
    p1_q1 = "I have been carrying deep emotional pain and sadness inside me. How can I begin meditation practice to heal this suffering?"
    p1_m1 = []
    print(f"\nPersona 1 Turn 1: {p1_q1}")
    r1_1, t1_1 = send_chat_turn(s1, s1_token, p1_m1, p1_q1)
    ans1_1 = r1_1.get("response") or r1_1.get("answer", "")
    citations1_1 = r1_1.get("citations", [])
    route1_1 = r1_1.get("route_decision")
    print(f"Elapsed: {t1_1}s | Route: {route1_1} | Citations: {len(citations1_1)}")
    print(f"Response: {ans1_1[:180]}...")

    # Turn 2: Follow-up & practice reflection
    p1_q2 = "I tried the meditation and focused on my breath as taught. I felt some calm, but tears came up. Is this part of the healing?"
    p1_m2 = [{"role": "user", "content": p1_q1}, {"role": "assistant", "content": ans1_1}]
    print(f"\nPersona 1 Turn 2: {p1_q2}")
    r1_2, t1_2 = send_chat_turn(s1, s1_token, p1_m2, p1_q2)
    ans1_2 = r1_2.get("response") or r1_2.get("answer", "")
    citations1_2 = r1_2.get("citations", [])
    route1_2 = r1_2.get("route_decision")
    print(f"Elapsed: {t1_2}s | Route: {route1_2} | Citations: {len(citations1_2)}")
    print(f"Response: {ans1_2[:180]}...")

    # Submit Practice Feedback
    fb_payload = {
        "query": p1_q2,
        "answer": ans1_2[:500],
        "rating": 1,
        "feedback_text": "The meditation insight helped me move through my grief with awareness.",
    }
    fb_resp = s1.post(f"{BASE_URL}/api/feedback/", json=fb_payload)
    print(f"Feedback Submission Status: {fb_resp.status_code}")

    results["persona_1"] = {
        "session_id": s1_id,
        "turn_1": {"elapsed_s": t1_1, "route": route1_1, "citations": len(citations1_1)},
        "turn_2": {"elapsed_s": t1_2, "route": route1_2, "citations": len(citations1_2)},
        "feedback_submitted": fb_resp.status_code == 200,
    }

    # -------------------------------------------------------------
    # PERSONA 2: Intellectual Inquirer
    # -------------------------------------------------------------
    print("\n" + "=" * 60)
    print("RUNNING PERSONA 2: Intellectual Inquirer (Ego & Consciousness)")
    print("=" * 60)
    s2 = requests.Session()
    s2_id, s2_token = create_anon_session(s2)
    print(f"Persona 2 Session Created: {s2_id}")

    # Explore tips
    tips = s2.get(f"{BASE_URL}/api/teachings/tips").json()
    print(f"Explored Curated Tips: {len(tips.get('tips', []))} tips available")

    # Turn 1
    p2_q1 = "What is the true nature of ego and consciousness in daily life?"
    p2_m1 = []
    print(f"\nPersona 2 Turn 1: {p2_q1}")
    r2_1, t2_1 = send_chat_turn(s2, s2_token, p2_m1, p2_q1)
    ans2_1 = r2_1.get("response") or r2_1.get("answer", "")
    citations2_1 = r2_1.get("citations", [])
    route2_1 = r2_1.get("route_decision")
    print(f"Elapsed: {t2_1}s | Route: {route2_1} | Citations: {len(citations2_1)}")
    print(f"Response: {ans2_1[:180]}...")

    # Turn 2: Relationship dynamics
    p2_q2 = "How does this distinction between ego and consciousness affect relationship dynamics with my partner?"
    p2_m2 = [{"role": "user", "content": p2_q1}, {"role": "assistant", "content": ans2_1}]
    print(f"\nPersona 2 Turn 2: {p2_q2}")
    r2_2, t2_2 = send_chat_turn(s2, s2_token, p2_m2, p2_q2)
    ans2_2 = r2_2.get("response") or r2_2.get("answer", "")
    citations2_2 = r2_2.get("citations", [])
    route2_2 = r2_2.get("route_decision")
    print(f"Elapsed: {t2_2}s | Route: {route2_2} | Citations: {len(citations2_2)}")
    print(f"Response: {ans2_2[:180]}...")

    # Turn 3: Conflict
    p2_q3 = "Why does conflict still arise even when one is aware of the ego's movements?"
    p2_m3 = p2_m2 + [{"role": "user", "content": p2_q2}, {"role": "assistant", "content": ans2_2}]
    print(f"\nPersona 2 Turn 3: {p2_q3}")
    r2_3, t2_3 = send_chat_turn(s2, s2_token, p2_m3, p2_q3)
    ans2_3 = r2_3.get("response") or r2_3.get("answer", "")
    citations2_3 = r2_3.get("citations", [])
    route2_3 = r2_3.get("route_decision")
    print(f"Elapsed: {t2_3}s | Route: {route2_3} | Citations: {len(citations2_3)}")
    print(f"Response: {ans2_3[:180]}...")

    results["persona_2"] = {
        "session_id": s2_id,
        "turn_1": {"elapsed_s": t2_1, "route": route2_1, "citations": len(citations2_1)},
        "turn_2": {"elapsed_s": t2_2, "route": route2_2, "citations": len(citations2_2)},
        "turn_3": {"elapsed_s": t2_3, "route": route2_3, "citations": len(citations2_3)},
    }

    # -------------------------------------------------------------
    # PERSONA 3: Stressed Student
    # -------------------------------------------------------------
    print("\n" + "=" * 60)
    print("RUNNING PERSONA 3: Stressed Student (Exam Anxiety & Focus)")
    print("=" * 60)
    s3 = requests.Session()
    s3_id, s3_token = create_anon_session(s3)
    print(f"Persona 3 Session Created: {s3_id}")

    # Turn 1
    p3_q1 = "I have overwhelming exam anxiety and my mind cannot focus. How do I overcome this fear of failure?"
    p3_m1 = []
    print(f"\nPersona 3 Turn 1: {p3_q1}")
    r3_1, t3_1 = send_chat_turn(s3, s3_token, p3_m1, p3_q1)
    ans3_1 = r3_1.get("response") or r3_1.get("answer", "")
    citations3_1 = r3_1.get("citations", [])
    route3_1 = r3_1.get("route_decision")
    print(f"Elapsed: {t3_1}s | Route: {route3_1} | Citations: {len(citations3_1)}")
    print(f"Response: {ans3_1[:180]}...")

    # Turn 2
    p3_q2 = "Can you give me a simple 3-minute practice I can do right before my test?"
    p3_m2 = [{"role": "user", "content": p3_q1}, {"role": "assistant", "content": ans3_1}]
    print(f"\nPersona 3 Turn 2: {p3_q2}")
    r3_2, t3_2 = send_chat_turn(s3, s3_token, p3_m2, p3_q2)
    ans3_2 = r3_2.get("response") or r3_2.get("answer", "")
    citations3_2 = r3_2.get("citations", [])
    route3_2 = r3_2.get("route_decision")
    print(f"Elapsed: {t3_2}s | Route: {route3_2} | Citations: {len(citations3_2)}")
    print(f"Response: {ans3_2[:180]}...")

    # Submit Feedback
    fb3_payload = {
        "query": p3_q2,
        "answer": ans3_2[:500],
        "rating": 1,
        "feedback_text": "The 3-minute practice idea calmed my panic before study time.",
    }
    fb3_resp = s3.post(f"{BASE_URL}/api/feedback/", json=fb3_payload)
    print(f"Feedback Submission Status: {fb3_resp.status_code}")

    results["persona_3"] = {
        "session_id": s3_id,
        "turn_1": {"elapsed_s": t3_1, "route": route3_1, "citations": len(citations3_1)},
        "turn_2": {"elapsed_s": t3_2, "route": route3_2, "citations": len(citations3_2)},
        "feedback_submitted": fb3_resp.status_code == 200,
    }

    with open("/tmp/multi_persona_results.json", "w") as f:
        json.dump(results, f, indent=2)
    print("\nAll Persona Simulations Finished. Saved to /tmp/multi_persona_results.json")


if __name__ == "__main__":
    run_simulation()
