import time

import requests


def test_chat():
    url = "http://localhost/api/chat"
    payload = {"messages": [], "user_message": "Hello, who are you?"}
    print(f"Sending request to {url}...")
    start = time.time()
    try:
        response = requests.post(url, json=payload, headers={"Content-Type": "application/json"})
        print(f"Status: {response.status_code}")
        print(f"Response: {response.text}")
    except Exception as e:
        print(f"Error: {e}")
    print(f"Took {time.time() - start:.2f}s")


if __name__ == "__main__":
    test_chat()
