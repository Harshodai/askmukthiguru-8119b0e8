import asyncio

import httpx


async def main():
    api_key = "sk_j2hvqcbz_J3hrGVe6VlKoDxl47Kxmr3V0"
    headers = {
        "Content-Type": "application/json",
        "api-subscription-key": api_key,
    }
    base_url = "https://api.sarvam.ai/v1"

    messages = [
        {
            "role": "system",
            "content": "You are a helpful assistant. Extract key terms from the text and return as a JSON list.",
        },
        {
            "role": "user",
            "content": "The path to ultimate liberation is through devotion (Bhakti), knowledge (Jnana), and selfless action (Karma).",
        },
    ]

    # Try different configurations
    test_cases = [
        {"model": "sarvam-30b", "reasoning_effort": "low"},
        {"model": "sarvam-30b", "reasoning_effort": "medium"},
        {"model": "sarvam-30b", "reasoning_effort": "none"},
        {"model": "sarvam-2b", "reasoning_effort": "low"},
    ]

    for case in test_cases:
        model = case["model"]
        reasoning_effort = case.get("reasoning_effort")
        payload = {
            "model": model,
            "messages": messages,
            "temperature": 0.1,
            "max_tokens": 1024,
        }
        if reasoning_effort is not None:
            payload["reasoning_effort"] = reasoning_effort

        print(f"\n--- Testing Model: {model} | reasoning_effort: {reasoning_effort} ---")
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    f"{base_url}/chat/completions", headers=headers, json=payload
                )
                print(f"Status: {resp.status_code}")
                if resp.status_code == 200:
                    data = resp.json()
                    choice = data.get("choices", [{}])[0].get("message", {})
                    content = choice.get("content") or ""
                    reasoning = choice.get("reasoning_content") or ""
                    print(f"Reasoning length: {len(reasoning)}")
                    print(f"Content: {content[:200]}")
                else:
                    print(f"Error: {resp.text}")
        except Exception as e:
            print(f"Exception: {e}")


if __name__ == "__main__":
    asyncio.run(main())
