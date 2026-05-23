import time

import requests


def test_rag_quality():
    url = "http://localhost:8000/api/chat"
    # Assuming we have an admin token or can bypass auth for testing locally
    # For now, let's just try to hit the health check and see if we can trigger a trace

    print("Testing Chat Endpoint...")
    payload = {"message": "What are the four sacred secrets?", "stream": False}

    try:
        # Note: This might fail if auth is strictly enforced.
        # I'll check if I need a token.
        response = requests.post(url, json=payload, timeout=30)
        print(f"Status: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print("Response received.")
            print("Confidence/Rerank scores would be in traces.")
        else:
            print(f"Error: {response.text}")
    except Exception as e:
        print(f"Request failed: {e}")


def check_jaeger():
    print("\nChecking Jaeger Traces...")
    jaeger_url = "http://localhost:16686/api/traces?service=mukthiguru-backend&limit=5"
    try:
        response = requests.get(jaeger_url)
        if response.status_code == 200:
            traces = response.json().get("data", [])
            print(f"Found {len(traces)} traces in Jaeger.")
            for t in traces:
                print(f"Trace ID: {t['traceID']}")
        else:
            print("Jaeger not reachable or no traces yet.")
    except Exception as e:
        print(f"Jaeger check failed: {e}")


if __name__ == "__main__":
    test_rag_quality()
    time.sleep(2)
    check_jaeger()
