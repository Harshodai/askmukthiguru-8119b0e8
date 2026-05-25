import requests
import json
import sys

url = "http://localhost:8000/api/chat/stream"
payload = {
    "user_message": "why I am feeling depressed",
    "messages": [],
    "stream": True
}

headers = {
    "Content-Type": "application/json",
    "X-Test-Key": "super-secret-jwt-token-with-at-least-32-characters-long"
}

try:
    print(f"Sending POST stream to {url}...")
    res = requests.post(url, json=payload, headers=headers, stream=True, timeout=60.0)
    print(f"Status Code: {res.status_code}")
    for line in res.iter_lines():
        if line:
            print(line.decode('utf-8'))
except Exception as e:
    print(f"Error: {e}")
