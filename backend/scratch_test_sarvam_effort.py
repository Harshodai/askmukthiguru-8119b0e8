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
            {"role": "user", "content": "Tell me: What is Deeksha?"},
        ],
        "temperature": 0.1,
        "max_tokens": 4096,
        "reasoning_effort": "low",
    }

    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(f"{base_url}/chat/completions", headers=headers, json=payload)
        print("Status Code:", resp.status_code)
        if resp.status_code == 200:
            data = resp.json()
            choice = data.get("choices", [{}])[0]
            message = choice.get("message", {})
            print("Reasoning Content Length:", len(message.get("reasoning_content") or ""))
            print("Content Length:", len(message.get("content") or ""))
            print("Reasoning Content (first 300 chars):")
            print(repr(message.get("reasoning_content", ""))[:300])
        else:
            print(resp.text)


if __name__ == "__main__":
    asyncio.run(main())
