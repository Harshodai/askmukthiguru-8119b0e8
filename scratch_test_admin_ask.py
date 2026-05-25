import requests

url = "http://localhost:8000/api/admin/ask"
headers = {
    "Content-Type": "application/json",
    "X-Test-Key": "super-secret-jwt-token-with-at-least-32-characters-long"
}
payload = {
    "question": "What is the current p95 latency?",
    "kpi_context": "p95 latency: 2.1s, query volume: 150"
}

try:
    print(f"Sending POST to {url}...")
    res = requests.post(url, json=payload, headers=headers, timeout=15.0)
    print(f"Status Code: {res.status_code}")
    print("Response JSON:")
    print(res.json())
except Exception as e:
    print(f"Error: {e}")
