import urllib.request
import urllib.error
import json

CHAT_URL = "http://localhost:8000/api/chat"

payload = json.dumps({
    "messages": [],
    "user_message": "Who are Sri Preethaji and Sri Krishnaji?",
    "session_id": "test-bench-debug",
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
    print("Sending request...")
    with urllib.request.urlopen(req, timeout=350) as resp:
        body = resp.read().decode("utf-8")
        print("Success! Response:")
        print(body)
except urllib.error.HTTPError as e:
    print(f"HTTP Error {e.code}: {e.reason}")
    try:
        print(e.read().decode("utf-8"))
    except Exception:
        pass
except Exception as e:
    print(f"Error: {e}")
