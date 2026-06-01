import asyncio

import httpx


async def main():
    api_key = "sk_ssncd4ha_x9XJumPZYpGPS1lqw8x6pH6G"
    base_url = "https://api.sarvam.ai/v1"
    headers = {
        "Content-Type": "application/json",
        "api-subscription-key": api_key,
    }
    payload = {
        "model": "sarvam-30b",
        "messages": [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Tell me in 2 sentences: What is Deeksha?"},
        ],
        "temperature": 0.1,
        "max_tokens": 1024,
    }

    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(f"{base_url}/chat/completions", headers=headers, json=payload)
        print("Status Code:", resp.status_code)
        try:
            data = resp.json()
            print("Choice keys:", data.get("choices", [{}])[0].get("message", {}).keys())
            message = data.get("choices", [{}])[0].get("message", {})
            print("Content (first 200 chars):")
            print(repr(message.get("content", ""))[:200])
            print("Reasoning Content (first 200 chars):")
            print(repr(message.get("reasoning_content", ""))[:200])
        except Exception as e:
            print("Failed to decode json:", e)
            print(resp.text[:500])


if __name__ == "__main__":
    asyncio.run(main())
