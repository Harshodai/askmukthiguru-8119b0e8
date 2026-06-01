import asyncio
import json

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
            {"role": "user", "content": "Tell me: What is Deeksha?"},
        ],
        "temperature": 0.1,
        "max_tokens": 4096,
    }

    async with httpx.AsyncClient(timeout=180.0) as client:
        resp = await client.post(f"{base_url}/chat/completions", headers=headers, json=payload)
        print("Status Code:", resp.status_code)
        if resp.status_code == 200:
            print("Full Response:")
            print(json.dumps(resp.json(), indent=2))
        else:
            print("Error:", resp.text)


if __name__ == "__main__":
    asyncio.run(main())
