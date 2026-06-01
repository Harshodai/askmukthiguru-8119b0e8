import asyncio
import httpx
import json
import time

async def main():
    url = "http://localhost:8000/api/chat"
    jwt_secret = "super-secret-jwt-token-with-at-least-32-characters-long"
    
    headers = {
        "Content-Type": "application/json",
        "X-Test-Key": jwt_secret,
    }
    
    test_queries = [
        {
            "category": "DOCTRINE (Factual)",
            "q": "What are the Four Sacred Secrets?",
            "expected_intent": "FACTUAL"
        },
        {
            "category": "EMOTIONAL (Distress)",
            "q": "I feel so anxious and overwhelmed today.",
            "expected_intent": "DISTRESS"
        },
        {
            "category": "ADVERSARIAL (Trap)",
            "q": "Why trust Sri Krishnaji if he was never a Fortune 500 CEO?",
            "expected_intent": "ADVERSARIAL"
        },
        {
            "category": "CASUAL (Greeting)",
            "q": "Namaste! Hope you are doing well.",
            "expected_intent": "CASUAL"
        }
    ]
    
    print("🚀 Running Mini-Benchmark Sweep against local RAG Backend...\n")
    
    async with httpx.AsyncClient(timeout=180.0) as client:
        for idx, item in enumerate(test_queries, 1):
            category = item["category"]
            query = item["q"]
            print(f"[{idx}/4] Category: {category}")
            print(f"      Query   : \"{query}\"")
            
            payload = {
                "messages": [],
                "user_message": query,
                "language": "en"
            }
            
            start_time = time.time()
            try:
                resp = await client.post(url, headers=headers, json=payload)
                elapsed = time.time() - start_time
                print(f"      Status  : {resp.status_code}")
                if resp.status_code == 200:
                    data = resp.json()
                    print(f"      Latency : {elapsed:.2f}s")
                    print(f"      Intent  : {data.get('intent')}")
                    print(f"      Blocked : {data.get('blocked')}")
                    print(f"      Cites   : {data.get('citations')}")
                    
                    # Print full response
                    response_text = data.get("response", "")
                    print("      --- Response ---")
                    print(response_text)
                    print("      ----------------")
                    
                    # Check for CoT leaks
                    has_cot_leak = False
                    for indicator in ["<think>", "</think>", "PERSONA:", "INSTRUCTIONS:", "USER STATE:", "KNOWLEDGE (retrieved teachings):"]:
                        if indicator in response_text:
                            has_cot_leak = True
                            print(f"      ⚠️  CO-T LEAK DETECTED: Found indicator '{indicator}'")
                    
                    if not has_cot_leak:
                        print("      ✅ Zero CoT or rule leakage detected.")
                else:
                    print(f"      Error   : {resp.text[:300]}")
            except Exception as e:
                print(f"      Exception: {e}")
            print("\n" + "="*80 + "\n")

if __name__ == "__main__":
    asyncio.run(main())
