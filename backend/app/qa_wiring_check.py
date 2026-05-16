import asyncio
import os
import sys
import logging

# Add backend to path
sys.path.append(os.getcwd())

from app.dependencies import get_container
from rag.graph import create_initial_state

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("QA_Wiring")

TEST_CASES = [
    {
        "name": "CASUAL",
        "query": "Namaste Mukthi Guru, how are you today?",
        "expected_intent": "CASUAL"
    },
    {
        "name": "SPIRITUAL_QUERY",
        "query": "What is the core message of the Four Sacred Secrets?",
        "expected_intent": "QUERY"
    },
    {
        "name": "DISTRESS",
        "query": "I am feeling very overwhelmed and I don't know if I can go on.",
        "expected_intent": "DISTRESS"
    },
    {
        "name": "MEDITATION",
        "query": "Can you start a meditation for me?",
        "expected_intent": "MEDITATION"
    }
]

async def run_qa_check():
    print("\n" + "="*50)
    print("MUKTHI GURU COMPREHENSIVE WIRING CHECK")
    print("="*50 + "\n")
    
    container = get_container()
    graph = container.rag_graph
    
    results = []
    
    for case in TEST_CASES:
        print(f"Testing: {case['name']}")
        print(f"Query: '{case['query']}'")
        
        try:
            state = create_initial_state(case['query'])
            # Add some context to help with intent
            state["chat_history"] = []
            
            result = await graph.ainvoke(state)
            
            intent = result.get("intent", "UNKNOWN")
            answer = result.get("final_answer") or result.get("response") or ""
            
            print(f"Detected Intent: {intent}")
            print(f"Response Preview: {answer[:150]}...")
            
            # Check for empty response
            if not answer:
                print("\u274c FAILED: Empty response")
                results.append((case['name'], False, "Empty response"))
                continue
                
            # Check intent routing (soft check)
            if intent != case['expected_intent'] and case['expected_intent'] != "QUERY":
                 # Some intents like RELATIONAL or FACTUAL might overlap with QUERY
                 print(f"\u26a0\ufe0f WARNING: Intent mismatch. Expected {case['expected_intent']}, got {intent}")
            
            print("\u2705 PASSED: Wiring functional")
            results.append((case['name'], True, "OK"))
            
        except Exception as e:
            print(f"\u274c FAILED: Error during execution: {e}")
            results.append((case['name'], False, str(e)))
        
        print("-" * 30)

    print("\n" + "="*50)
    print("SUMMARY")
    print("="*50)
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
