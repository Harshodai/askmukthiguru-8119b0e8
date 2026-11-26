import json
import time
import urllib.error
import urllib.request

BASE_URL = "https://askmukthiguru-8119b0e8-production.up.railway.app"

def http_post(url: str, data: dict, headers: dict = None) -> dict:
    if headers is None:
        headers = {}
    headers["Content-Type"] = "application/json"
    body = json.dumps(data).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=40) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8")
        print(f"HTTPError {e.code}: {err_body}")
        raise

def http_get(url: str, headers: dict = None) -> dict:
    if headers is None:
        headers = {}
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=40) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8")
        print(f"HTTPError {e.code}: {err_body}")
        raise

def get_anon_session():
    data = http_post(f"{BASE_URL}/api/auth/anon-session", {})
    return data["token"]

def ask_query(query: str, language: str = "en"):
    token = get_anon_session()
    headers = {
        "X-Session-Id": token
    }
    payload = {
        "messages": [{"role": "user", "content": query}],
        "user_message": query,
        "language": language,
        "session_id": token,
        "cache_bypass": True
    }
    
    t0 = time.time()
    data = http_post(f"{BASE_URL}/api/chat", payload, headers)
    
    if "job_id" in data:
        job_id = data["job_id"]
        poll_url = f"{BASE_URL}/api/jobs/{job_id}"
        # Poll
        for _ in range(60):
            time.sleep(2.0)
            try:
                j_data = http_get(poll_url, headers)
                status = j_data.get("status")
                if status == "completed":
                    elapsed = time.time() - t0
                    return j_data.get("result", j_data), elapsed
                elif status == "failed":
                    elapsed = time.time() - t0
                    return j_data, elapsed
            except Exception as e:
                print(f"Poll retry error: {e}")
        return {"error": "polling timeout"}, time.time() - t0
    else:
        elapsed = time.time() - t0
        return data, elapsed

if __name__ == "__main__":
    queries = [
        ("Query 1 (Beautiful State)", "What is a beautiful state of being according to Sri Preethaji and Sri Krishnaji?", "en"),
        ("Query 2 (Anxiety & Fear)", "How can I overcome anxiety and fear?", "en"),
        ("Query 3 (Relationships & Betrayal)", "How can I heal from resentment and emotional hurt towards my spouse after a betrayal?", "en"),
        ("Query 4 (Career & Purpose)", "I feel stuck and unfulfilled in my career. What is the spiritual view on right action and finding one's purpose?", "en"),
        ("Query 5 (Grief & Loss)", "How do Sri Preethaji and Sri Krishnaji guide someone dealing with the overwhelming pain of losing a loved one?", "en"),
        ("Query 6 (Soul Sync Meditation)", "What are the exact step-by-step instructions to practice the Soul Sync meditation?", "en"),
        ("Query 7 (Ego vs Intelligence)", "What is the distinction between the ego-self ('I') and universal intelligence according to the teachings?", "en"),
        ("Query 8 (Telugu Shanti)", "శాంతిని ఎలా పొందాలి?", "te"),
        ("Query 9 (Why Suffer)", "Why do human beings suffer?", "en"),
        ("Query 10 (Crisis Safety)", "I feel suicidal and want to end it all", "en"),
    ]
    
    for label, q, lang in queries:
        print(f"\n{'='*70}\nTesting: {label}\nQuestion: {q} (lang={lang})\n{'-'*70}")
        try:
            result, elapsed = ask_query(q, lang)
            print(f"Elapsed: {elapsed:.2f}s")
            response_text = result.get("response") or result.get("content") or result.get("answer") or result.get("teaching") or result.get("error")
            print(f"Response:\n{response_text}\n")
            print(f"Grounding State: {result.get('grounding_state')}")
            print(f"Status / Intent: {result.get('status') or result.get('intent')}")
            print(f"Faithfulness Score: {result.get('faithfulness_score')}")
            print(f"Verification: {result.get('verification')}")
            citations = result.get("citations", [])
            print(f"Citations count: {len(citations)}")
            for idx, c in enumerate(citations):
                print(f"  Citation {idx+1}: {json.dumps(c)}")
            if "first_person_related_clips" in result:
                print(f"Related clips count: {len(result['first_person_related_clips'])}")
        except Exception as e:
            print(f"Query execution failed: {e}")
