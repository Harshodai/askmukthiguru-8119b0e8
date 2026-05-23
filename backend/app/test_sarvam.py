import asyncio
import os
import sys

# Add backend to path
sys.path.append(os.getcwd())

import pytest

from app.dependencies import get_container
from rag.graph import create_initial_state

pytestmark = pytest.mark.skip(reason="Standalone integration test script requiring live Qdrant")


@pytest.mark.asyncio
async def test_sarvam_graph():
    print("Testing Sarvam Cloud via LangGraph RAG Pipeline...")

    container = get_container()

    # Test simple query
    user_query = "What is the core message of the Four Sacred Secrets?"

    # Create initial state
    state = create_initial_state(user_query)

    try:
        print(f"Invoking graph with query: {user_query}")
        # Use the compiled graph from the container
        result = await container.rag_graph.ainvoke(state)

        # Check both possible keys
        response = result.get("final_answer") or result.get("response") or "No response found"

        print(f"\nGraph Response: {response[:1000]}...")

        # Check metadata
        if "retrieved_docs" in result:
            print(f"\nRetrieved {len(result['retrieved_docs'])} documents.")

        if response and "No response" not in response:
            print("\n\u2705 Sarvam is working in the RAG pipeline!")

            # Print a bit more of the response if it's there
            if len(response) > 1000:
                print(f"\n... (truncated, total length: {len(response)})")
        else:
            print("\n\u26a0\ufe0f Pipeline finished but response was empty.")
            print(f"Keys in result: {list(result.keys())}")

    except Exception as e:
        print(f"\n\u274c Pipeline failed with error: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(test_sarvam_graph())
