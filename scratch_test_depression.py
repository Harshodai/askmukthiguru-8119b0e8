import requests
import json
import sys

url = "http://localhost:8000/api/chat"
payload = {
    "user_message": "why I am feeling depressed",
    "messages": []
}

headers = {
    "Content-Type": "application/json",
    "X-Test-Key": "super-secret-jwt-token-with-at-least-32-characters-long"
}

try:
    print(f"Sending POST to {url}...")
    res = requests.post(url, json=payload, headers=headers, timeout=60.0)
    print(f"Status Code: {res.status_code}")
    print("Response JSON:")
    try:
        print(json.dumps(res.json(), indent=2))
    except Exception:
        print(res.text)
except Exception as e:
    print(f"Error: {e}")
