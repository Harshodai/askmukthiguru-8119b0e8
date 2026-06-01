import asyncio

import httpx


async def main():
    api_key = "sk_ssncd4ha_x9XJumPZYpGPS1lqw8x6pH6G"
    base_url = "https://api.sarvam.ai/v1"
    headers = {
        "api-subscription-key": api_key,
    }
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{base_url}/models", headers=headers)
        print("Status Code:", resp.status_code)
        if resp.status_code == 200:
            try:
                data = resp.json()
                print("Models:")
                for m in data.get("data", []):
                    print(f"- {m.get('id')}")
            except Exception as e:
                print("Failed to decode json:", e)
                print(resp.text[:500])
        else:
            print(resp.text)


if __name__ == "__main__":
    asyncio.run(main())
