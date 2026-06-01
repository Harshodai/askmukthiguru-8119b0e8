import asyncio
import logging
import os
import sys

# Add backend to path
sys.path.append(os.getcwd())

# Set environment variables for local testing (pointing to localhost instead of Docker hostnames)
os.environ["QDRANT_URL"] = "http://localhost:6333"
os.environ["NEO4J_URI"] = "bolt://localhost:7687"
os.environ.setdefault("REDIS_URL", os.environ.get("REDIS_URL") or (_ for _ in ()).throw(RuntimeError("REDIS_URL env var is required")))
os.environ["SUPABASE_URL"] = "http://localhost:54321"

from app.dependencies import get_container
from rag.graph import create_initial_state

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("QA_Wiring")

TEST_CASES = [
    {
        "name": "CASUAL",
        "query": "Namaste Mukthi Guru, how are you today?",
        "expected_intent": "CASUAL",
    },
    {
        "name": "SPIRITUAL_QUERY",
        "query": "What are the Four Sacred Secrets?",
        "expected_intent": "FACTUAL",
    },
    {
        "name": "DISTRESS_DETECTION",
        "query": "I feel so lost and hopeless, I don't know what to do.",
        "expected_intent": "DISTRESS",
    },
    {
        "name": "MEDITATION_FLOW",
        "turns": [
            {"query": "Can you guide me through a meditation?", "expected_intent": "MEDITATION"},
            {"query": "I am ready", "expected_intent": "MEDITATION_CONTINUE"},
            {"query": "Done with that", "expected_intent": "MEDITATION_CONTINUE"},
        ],
    },
]


async def run_qa_check():
    print("\n" + "=" * 50)
    print("MUKTHI GURU COMPREHENSIVE WIRING CHECK")
    print("=" * 50 + "\n")

    container = get_container()
    graph = container.rag_graph

    results = []

    for case in TEST_CASES:
        print(f"Testing: {case['name']}")

        try:
            if "turns" in case:
                # Multi-turn test
                state = create_initial_state("")
                for i, turn in enumerate(case["turns"]):
                    print(f"  Turn {i + 1}: '{turn['query']}'")
                    state["question"] = turn["query"]

                    result = await graph.ainvoke(state)

                    intent = result.get("intent", "UNKNOWN")
                    answer = result.get("final_answer") or result.get("response") or ""
                    meditation_step = result.get("meditation_step", 0)

                    print(f"    Detected Intent: {intent}")
                    print(f"    Meditation Step: {meditation_step}")
                    print(f"    Response Preview: {answer[:80]}...")

                    # Update state for next turn
                    state = result

                    if not answer:
                        raise ValueError(f"Empty response in turn {i + 1}")

                print("\u2705 PASSED: Multi-turn sequence functional")
                results.append((case["name"], True, "OK"))
            else:
                # Single-turn test
                print(f"Query: '{case['query']}'")
                state = create_initial_state(case["query"])

                result = await graph.ainvoke(state)

                intent = result.get("intent", "UNKNOWN")
                answer = result.get("final_answer") or result.get("response") or ""

                print(f"Detected Intent: {intent}")
                print(f"Response Preview: {answer[:150]}...")

                if not answer:
                    print("\u274c FAILED: Empty response")
                    results.append((case["name"], False, "Empty response"))
                    continue

                print("\u2705 PASSED: Wiring functional")
                results.append((case["name"], True, "OK"))

        except Exception as e:
            print(f"\u274c FAILED: Error during execution: {e}")
            results.append((case["name"], False, str(e)))

        print("-" * 30)

    print("\n" + "=" * 50)
    print("SUMMARY")
    print("=" * 50)
    all_passed = True
    for name, success, msg in results:
        status = "\u2705" if success else "\u274c"
        print(f"{status} {name}: {msg}")
        if not success:
            all_passed = False

    if all_passed:
        print("\n\u2728 ALL WIRING FUNCTIONAL \u2728")
        sys.exit(0)
    else:
        print("\n\u26a0\ufe0f SOME TESTS FAILED")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(run_qa_check())
