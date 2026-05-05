import requests
import json

url = "http://localhost:8000/api/chat/stream"
payload = {
    "user_message": "If the concept of 'self' is just an illusion as per Advaita, then who is the one actually experiencing this illusion?",
    "messages": [],
    "meditation_step": 0
}
headers = {"Content-Type": "application/json"}

try:
    with requests.post(url, json=payload, headers=headers, stream=True) as r:
        for line in r.iter_lines():
            if line:
                print(line.decode('utf-8'))
except Exception as e:
    print(f"Error: {e}")
