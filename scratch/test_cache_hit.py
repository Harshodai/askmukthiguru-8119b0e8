import sys
import json
import time
import urllib.request
import urllib.error

BASE_URL = "http://localhost:8000"
CHAT_URL = f"{BASE_URL}/api/chat"

def call_chat(question: str) -> dict:
    payload = json.dumps({
        "messages": [],
        "user_message": question,
        "session_id": "test-cache-session",
        "language": "en",
        "meditation_step": 0,
    }).encode("utf-8")

    req = urllib.request.Request(
        CHAT_URL,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "X-Test-Key": "super-secret-jwt-token-with-at-least-32-characters-long",
        },
        method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            body = resp.read().decode("utf-8")
            return {"ok": True, "status": resp.status, "body": json.loads(body)}
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8")
        return {"ok": False, "status": e.code, "body": body, "error": str(e)}
    except Exception as e:
        return {"ok": False, "status": -1, "body": "", "error": str(e)}

def main():
    question = "Who are Sri Preethaji and Sri Krishnaji?"
    print("Sending Request 1 (should be cache miss / RAG)...")
    t0 = time.time()
    res1 = call_chat(question)
    elapsed1 = time.time() - t0
    if not res1["ok"]:
        print(f"Request 1 failed: {res1}")
        return
    print(f"Request 1 took {elapsed1:.2f}s. Response: {res1['body']['response'][:100]}...")
    print(f"Request 1 cache_hit: {res1['body'].get('cache_hit')} | route_decision: {res1['body'].get('route_decision')}")

    print("\nSleeping 2s...")
    time.sleep(2.0)

    print("Sending Request 2 (exact same question, should be exact cache hit)...")
    t0 = time.time()
    res2 = call_chat(question)
    elapsed2 = time.time() - t0
    if not res2["ok"]:
        print(f"Request 2 failed: {res2}")
        return
    print(f"Request 2 took {elapsed2:.2f}s. Response: {res2['body']['response'][:100]}...")
    print(f"Request 2 cache_hit: {res2['body'].get('cache_hit')} | route_decision: {res2['body'].get('route_decision')}")

    print("\nSending Request 3 (semantically similar question: 'Who is Sri Preethaji and Sri Krishnaji?', should be semantic cache hit)...")
    t0 = time.time()
    res3 = call_chat("Who is Sri Preethaji and Sri Krishnaji?")
    elapsed3 = time.time() - t0
    if not res3["ok"]:
        print(f"Request 3 failed: {res3}")
        return
    print(f"Request 3 took {elapsed3:.2f}s. Response: {res3['body']['response'][:100]}...")
    print(f"Request 3 cache_hit: {res3['body'].get('cache_hit')} | route_decision: {res3['body'].get('route_decision')}")

if __name__ == "__main__":
    main()
