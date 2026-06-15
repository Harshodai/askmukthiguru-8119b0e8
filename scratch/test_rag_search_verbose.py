import os
import sys
from dotenv import load_dotenv

sys.path.insert(0, "/Users/harshodaikolluru/Public/askmukthiguru-8119b0e8/backend")
env_path = "/Users/harshodaikolluru/Public/askmukthiguru-8119b0e8/backend/.env"
load_dotenv(dotenv_path=env_path)

os.environ["QDRANT_URL"] = "http://localhost:6333"
os.environ["NEO4J_URI"] = "bolt://localhost:7687"
os.environ["REDIS_URL"] = "redis://:mukthiguru_redis_pass@localhost:6379/0"
os.environ["SUPABASE_URL"] = "http://localhost:54321"

import asyncio
from services.container_builder import ContainerBuilder

async def main():
    builder = ContainerBuilder()
    container = builder.build()
    
    query = "what are the upcoming programs of sri krishnaji and preethaji"
    state = {
        "question": query,
        "history": [],
        "session_id": "verbose-test-session",
        "user_id": "anonymous"
    }
    
    print("Executing graph step-by-step...")
    async for event in container.standard_graph.astream(state, stream_mode="updates"):
        for node_name, node_update in event.items():
            print(f"\n--- Node '{node_name}' completed ---")
            if node_update is None:
                print("  (Returned None)")
                continue
            if not isinstance(node_update, dict):
                print(f"  Returned: {node_update}")
                continue
            for key, val in node_update.items():
                if key in ["web_search_results", "documents", "relevant_docs", "reranked_docs"]:
                    print(f"  {key}: count={len(val) if val else 0}")
                elif key == "answer" or key == "final_answer":
                    print(f"  {key}: '{val[:120]}...'")
                else:
                    print(f"  {key}: {val}")

if __name__ == "__main__":
    asyncio.run(main())
