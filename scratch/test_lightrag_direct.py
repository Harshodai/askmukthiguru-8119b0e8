import os
import sys
import traceback
from dotenv import load_dotenv

sys.path.insert(0, "/Users/harshodaikolluru/Public/askmukthiguru-8119b0e8/backend")
env_path = "/Users/harshodaikolluru/Public/askmukthiguru-8119b0e8/backend/.env"
load_dotenv(dotenv_path=env_path)

os.environ["QDRANT_URL"] = "http://localhost:6333"
os.environ["NEO4J_URI"] = "bolt://localhost:7687"
os.environ["REDIS_URL"] = "redis://:mukthiguru_redis_pass@localhost:6379/0"
os.environ["SUPABASE_URL"] = "http://localhost:54321"

import asyncio
from services.lightrag_service import lightrag_service

async def main():
    print("Initializing lightrag service...")
    await lightrag_service.initialize()
    print("Initialized. Running aquery...")
    try:
        res = await lightrag_service.aquery(
            "What are the upcoming programs featuring Sri Krishnaji? (also: krishna ji, sree krishnaji)",
            mode="hybrid",
            only_need_context=True
        )
        print("Success, response:", type(res), repr(res))
    except Exception as e:
        print("Error caught in test:")
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
