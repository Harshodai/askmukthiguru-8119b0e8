import json

import requests

BASE_URL = "http://localhost:8000"


def test():
    r = requests.post(f"{BASE_URL}/api/auth/anon-session")
    session_id = r.json().get("session_id")
    headers = {"Authorization": f"Bearer {session_id}"}
    payload = {
        "messages": [],
        "user_message": "What is the Beautiful State?",
        "incognito": True,
        "cache_bypass": True,
        "session_id": session_id,
    }
    r = requests.post(f"{BASE_URL}/api/chat", json=payload, headers=headers)
    print("Status code:", r.status_code)
    try:
        data = r.json()
        print("Keys:", data.keys())
        print(json.dumps(data, indent=2)[:1000])
    except Exception as e:
        print("Error parsing json:", e)


if __name__ == "__main__":
    test()
