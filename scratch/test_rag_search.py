import os
import sys
from dotenv import load_dotenv

# Set sys path to include backend
sys.path.insert(0, "/Users/harshodaikolluru/Public/askmukthiguru-8119b0e8/backend")

# Load backend/.env
env_path = "/Users/harshodaikolluru/Public/askmukthiguru-8119b0e8/backend/.env"
load_dotenv(dotenv_path=env_path)

# Override docker-internal URLs with host-accessible localhost URLs
os.environ["QDRANT_URL"] = "http://localhost:6333"
os.environ["NEO4J_URI"] = "bolt://localhost:7687"
os.environ["REDIS_URL"] = "redis://:mukthiguru_redis_pass@localhost:6379/0"
os.environ["SUPABASE_URL"] = "http://localhost:54321"

# Import settings and force overrides directly
from app.config import settings
settings.qdrant_url = "http://localhost:6333"
settings.neo4j_uri = "bolt://localhost:7687"
settings.redis_url = "redis://:mukthiguru_redis_pass@localhost:6379/0"
settings.supabase_url = "http://localhost:54321"

print(f"DEBUG: settings.qdrant_url = {settings.qdrant_url}")
print(f"DEBUG: settings.neo4j_uri = {settings.neo4j_uri}")
print(f"DEBUG: settings.redis_url = {settings.redis_url}")

import asyncio
from services.container_builder import ContainerBuilder

async def main():
    print("Building local service container...")
    builder = ContainerBuilder()
    container = builder.build()

    
    # Check if web search is enabled and initialized
    if container.web_search:
        print(f"Web Search is ENABLED. Allowed domains: {container.web_search.allowed_domains}")
    else:
        print("Web Search is DISABLED!")
        
    query = "what are the upcoming programs of sri krishnaji and preethaji"
    print(f"\nSending end-to-end RAG query: '{query}'...")
    
    # Run the query through standard_graph
    state = {
        "question": query,
        "history": [],
        "session_id": "local-test-session",
        "user_id": "anonymous"
    }
    
    # standard_graph is a CompiledStateGraph, invoke it asynchronously
    result = await container.standard_graph.ainvoke(state)
    
    print("\n--- RESPONSE ---")
    print(result.get("final_answer"))
    print("\n--- CITATIONS ---")
    print(result.get("citations"))
    print("\n--- WEB SEARCH RESULTS ---")
    print(result.get("web_search_results"))
    print("\n--- INTENT ---")
    print(result.get("intent"))

if __name__ == "__main__":
    asyncio.run(main())
