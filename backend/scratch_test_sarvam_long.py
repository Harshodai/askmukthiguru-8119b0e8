import os
import httpx
import json
import asyncio

async def main():
    api_key = "sk_ssncd4ha_x9XJumPZYpGPS1lqw8x6pH6G"
    base_url = "https://api.sarvam.ai/v1"
    headers = {
        "Content-Type": "application/json",
        "api-subscription-key": api_key,
    }
    payload = {
        "model": "sarvam-105b",
        "messages": [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Tell me: What is Deeksha?"}
        ],
        "temperature": 0.1,
        "max_tokens": 32768,
    }
    
    async with httpx.AsyncClient(timeout=180.0) as client:
        resp = await client.post(f"{base_url}/chat/completions", headers=headers, json=payload)
        print("Status Code:", resp.status_code)
        if resp.status_code != 200:
            print("Error response text:", resp.text)
        try:
            data = resp.json()
            # print full choice message
            choice = data.get("choices", [{}])[0]
            message = choice.get("message", {})
            print("Finish Reason:", choice.get("finish_reason"))
            print("Content is None:", message.get("content") is None)
            print("Content type:", type(message.get("content")))
            print("Content (first 500 chars):")
            print(repr(message.get("content"))[:500])
            print("Reasoning Content (first 500 chars):")
            print(repr(message.get("reasoning_content"))[:500])
            print("Reasoning Content (last 500 chars):")
            print(repr(message.get("reasoning_content"))[-500:])
        except Exception as e:
            print("Failed to decode json:", e)
            print(resp.text[:1000])

if __name__ == "__main__":
    asyncio.run(main())
