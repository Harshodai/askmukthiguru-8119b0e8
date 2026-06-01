import asyncio

import httpx


async def main():
    url = "http://localhost:8000/api/admin/ask"
    headers = {
        "Content-Type": "application/json",
        "X-Test-Key": "super-secret-jwt-token-with-at-least-32-characters-long",
    }
    payload = {
        "question": "What is the current p95 latency?",
        "kpi_context": "p95 latency: 2.1s, query volume: 1500, costs: $5.20",
    }

    print("Sending POST to /api/admin/ask...")
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(url, headers=headers, json=payload)
            print(f"Status: {resp.status_code}")
            print(f"Headers: {dict(resp.headers)}")
            print(f"Content: {resp.text}")
    except Exception as e:
        print(f"Exception: {e}")


if __name__ == "__main__":
    asyncio.run(main())
