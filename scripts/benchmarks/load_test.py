#!/usr/bin/env python3
"""
Mukthi Guru — Performance & Latency Load Test Harness

Simulates concurrent user queries against the spiritual RAG backend
to benchmark TTFT (Time-to-First-Token) and completion latencies.
"""

import argparse
import asyncio
import logging
import statistics
import time

import httpx

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# Sample spiritual questions to test various paths (Casual, Factual, Relational)
TEST_QUESTIONS = [
    "Namaste, who are you?",  # Casual (Fast-path bypass)
    "What is the Beautiful State?",  # Factual RAG
    "Tell me about the connection between breath and mind",  # Spiritual/Meditation
    "How does Soul Sync meditation work?",  # Meditation specific
    "I am feeling really anxious and overwhelmed today",  # Distress routing
    "Tell me more about the official Amazon book",  # RAG with canonical sources
]


async def run_single_query(client: httpx.AsyncClient, url: str, question: str, stream: bool = True) -> dict:
    """Run a single request and return detailed latency metrics."""
    import os
    benchmark_secret = os.getenv("BENCHMARK_SECRET")
    headers = {"Content-Type": "application/json"}
    if benchmark_secret:
        headers["X-Test-Key"] = benchmark_secret
        
    payload = {
        "user_message": question,
        "messages": [],
        "meditation_step": 0,
        "language": "en"
    }

    endpoint = f"{url}/api/chat/stream" if stream else f"{url}/api/chat"
    start_time = time.time()
    ttft = None
    completion_time = None
    tokens_count = 0
    success = False
    accepted = False
    status_code = None
    error_msg = ""

    try:
        if stream:
            async with client.stream("POST", endpoint, json=payload, headers=headers, timeout=120.0) as response:
                status_code = response.status_code
                if response.status_code == 200:
                    async for chunk in response.aiter_text():
                        if ttft is None:
                            ttft = (time.time() - start_time) * 1000
                        # Count approximate tokens based on SSE chunks or word delimiters
                        tokens_count += len(chunk.split())
                    completion_time = (time.time() - start_time) * 1000
                    success = True
                elif response.status_code == 202:
                    # The queue contract returns JSON rather than an SSE stream.
                    # This is an admission/acknowledgement latency, not completion latency.
                    await response.aread()
                    completion_time = (time.time() - start_time) * 1000
                    ttft = completion_time
                    success = True
                    accepted = True
                else:
                    error_msg = f"HTTP {response.status_code}"
        else:
            response = await client.post(endpoint, json=payload, headers=headers, timeout=120.0)
            status_code = response.status_code
            if response.status_code in (200, 202):
                success = True
                completion_time = (time.time() - start_time) * 1000
                ttft = completion_time  # In non-streamed, TTFT equals response/ack time
                data = response.json()
                if response.status_code == 200:
                    tokens_count = len(data.get("answer", "").split())
                else:
                    # 202 means queued; no answer is available at acknowledgement time.
                    accepted = True
            else:
                error_msg = f"HTTP {response.status_code}"
    except Exception as e:
        error_msg = str(e)

    return {
        "question": question,
        "success": success,
        "accepted": accepted,
        "status_code": status_code,
        "ttft_ms": ttft,
        "completion_ms": completion_time,
        "tokens": tokens_count,
        "error": error_msg
    }


async def worker(url: str, duration: int, results: list, stream: bool):
    """Worker task that continually runs queries until duration is met."""
    start_time = time.time()
    async with httpx.AsyncClient(limits=httpx.Limits(max_connections=100)) as client:
        idx = 0
        while time.time() - start_time < duration:
            question = TEST_QUESTIONS[idx % len(TEST_QUESTIONS)]
            res = await run_single_query(client, url, question, stream)
            results.append(res)
            idx += 1
            # Brief pause between queries
            await asyncio.sleep(0.5)


async def main():
    parser = argparse.ArgumentParser(description="Mukthi Guru RAG Load Test Harness")
    parser.add_argument("--url", default="http://localhost:8000", help="Backend base URL")
    parser.add_argument("--concurrent", type=int, default=5, help="Number of concurrent users")
    parser.add_argument("--duration", type=int, default=15, help="Test duration in seconds")
    parser.add_argument("--no-stream", action="store_true", help="Disable SSE streaming")
    args = parser.parse_args()

    stream = not args.no_stream
    logger.info(f"Starting load test against: {args.url}")
    logger.info(f"Configuration: Concurrency={args.concurrent}, Duration={args.duration}s, Streaming={stream}")

    results = []
    tasks = [worker(args.url, args.duration, results, stream) for _ in range(args.concurrent)]
    
    start_test = time.time()
    await asyncio.gather(*tasks)
    total_test_duration = time.time() - start_test

    # Gather metrics
    successful_runs = [r for r in results if r["success"]]
    failed_runs = [r for r in results if not r["success"]]
    
    print("\n" + "=" * 80)
    print("                      MUKTHI GURU LOAD TEST REPORT                      ")
    print("=" * 80)
    print(f"Total Test Duration:  {total_test_duration:.2f} seconds")
    print(f"Total Requests Run:   {len(results)}")
    print(f"Successful Requests:  {len(successful_runs)} ({len(successful_runs)/max(1, len(results)):.1%})")
    print(f"  - Completed (200):   {sum(1 for r in successful_runs if not r['accepted'])}")
    print(f"  - Queued (202):      {sum(1 for r in successful_runs if r['accepted'])}")
    print(f"Failed Requests:      {len(failed_runs)} ({len(failed_runs)/max(1, len(results)):.1%})")
    
    if failed_runs:
        print("\nErrors Encountered:")
        errors = set(r["error"] for r in failed_runs)
        for err in errors:
            count = sum(1 for r in failed_runs if r["error"] == err)
            print(f"  - {err} ({count} occurrences)")

    if successful_runs:
        if any(r["accepted"] for r in successful_runs):
            print("\nNOTE: 202 latency is queue acknowledgement time; it does not prove pipeline completion.")
        ttfts = [r["ttft_ms"] for r in successful_runs if r["ttft_ms"] is not None]
        completions = [r["completion_ms"] for r in successful_runs if r["completion_ms"] is not None]
        
        print("\nLatency Metrics (Milliseconds):")
        if ttfts:
            print(f"  - Average TTFT:       {statistics.mean(ttfts):.2f} ms")
            print(f"  - p50 TTFT (Median):  {statistics.median(ttfts):.2f} ms")
            if len(ttfts) > 1:
                print(f"  - p95 TTFT:           {statistics.quantiles(ttfts, n=20)[18]:.2f} ms")
        else:
            print("  - TTFT:               N/A")
        
        if completions:
            print(f"\n  - Average Completion: {statistics.mean(completions):.2f} ms")
            print(f"  - p50 Completion:     {statistics.median(completions):.2f} ms")
            if len(completions) > 1:
                print(f"  - p95 Completion:     {statistics.quantiles(completions, n=20)[18]:.2f} ms")
        else:
            print("  - Completion:         N/A")

        tokens = [r["tokens"] for r in successful_runs]
        if tokens:
            print(f"\n  - Avg Tokens Generated: {statistics.mean(tokens):.1f} tokens")
    print("=" * 80 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
