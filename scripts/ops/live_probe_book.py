import json
import time
import urllib.request
import urllib.error

BASE_URL = "https://askmukthiguru-8119b0e8-production.up.railway.app"

def http_post(url: str, data: dict, headers: dict = None) -> dict:
    if headers is None:
        headers = {}
    headers["Content-Type"] = "application/json"
    body = json.dumps(data).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=50) as resp:
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
        with urllib.request.urlopen(req, timeout=50) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8")
        print(f"HTTPError {e.code}: {err_body}")
        raise

def get_anon_session():
    data = http_post(f"{BASE_URL}/api/auth/anon-session", {})
    return data["token"]

def ask_query(query: str):
    token = get_anon_session()
    headers = {"X-Session-Id": token}
    payload = {
        "messages": [{"role": "user", "content": query}],
        "user_message": query,
        "language": "en",
        "session_id": token,
        "cache_bypass": True
    }
    t0 = time.time()
    data = http_post(f"{BASE_URL}/api/chat", payload, headers)
    if "job_id" in data:
        job_id = data["job_id"]
        poll_url = f"{BASE_URL}/api/jobs/{job_id}"
        for _ in range(60):
            time.sleep(2.0)
            j_data = http_get(poll_url, headers)
            if j_data.get("status") == "completed":
                return j_data.get("result", j_data), time.time() - t0
            elif j_data.get("status") == "failed":
                return j_data, time.time() - t0
        return {"error": "timeout"}, time.time() - t0
    return data, time.time() - t0

if __name__ == "__main__":
    queries = [
        "What are the four sacred secrets according to Sri Preethaji and Sri Krishnaji?",
        "Where can I find and read The Four Sacred Secrets by Sri Preethaji and Sri Krishnaji?"
    ]

    for q in queries:
        print("\n" + "=" * 60)
        print(f"Testing: {q}")
        print("-" * 60)
        res, elapsed = ask_query(q)
        print(f"Elapsed: {elapsed:.2f}s")
        print(f"Grounding State: {res.get('grounding_state')}")
        print(f"Faithfulness Score: {res.get('faithfulness_score')}")
        print(f"Response:\n{res.get('response')}\n")
        citations = res.get("citations", [])
        print(f"Citations count: {len(citations)}")
        for i, c in enumerate(citations, 1):
            print(f"  Citation {i}: {c.get('url')} | Title: {c.get('title')} | Speaker: {c.get('speaker')}")

