import requests
import json
import sys
import time

url = "http://localhost:8000/api/chat"
payload = {
    "user_message": "what teachings you have in your repository, what kind of things you can answer me right now",
    "messages": []
}

headers = {
    "Content-Type": "application/json",
    "X-Test-Key": "super-secret-jwt-token-with-at-least-32-characters-long"
}

try:
    print(f"Sending POST to {url}...")
    start_time = time.time()
    res = requests.post(url, json=payload, headers=headers, timeout=60.0)
    duration = time.time() - start_time
    print(f"Status Code: {res.status_code} (took {duration:.2f}s)")
    print("Response JSON:")
    try:
        print(json.dumps(res.json(), indent=2))
    except Exception:
        print(res.text)
except Exception as e:
    print(f"Error: {e}")
