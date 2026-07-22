#!/usr/bin/env python3
"""
Single-query evaluator for AskMukthiGuru with full logging, timing, and local host mapping.
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

backend_dir = Path(__file__).resolve().parents[2] / "backend"
env_path = backend_dir / ".env"
if env_path.exists():
    try:
        from dotenv import load_dotenv
        load_dotenv(env_path, override=True)
    except ImportError:
        pass

# Force localhost mappings when running outside Docker
os.environ["QDRANT_HOST"] = "localhost"
os.environ["QDRANT_URL"] = "http://localhost:6333"
os.environ["NEO4J_URI"] = "bolt://localhost:7687"
os.environ["REDIS_HOST"] = "localhost"
os.environ["REDIS_URL"] = "redis://:mukthiguru_redis_pass@localhost:6379/0"

sys.path.insert(0, str(backend_dir))


async def main():
    from services.container_builder import ContainerBuilder
    from app.chat_engine import ChatEngine
    from app.schemas import ChatRequest

    query = "I want to experience deeper inner peace. What teachings or practices do you suggest?"
    print(f"\n❓ Query: '{query}'\n")

    container = ContainerBuilder().build()
    engine = ChatEngine(container=container)

    chat_req = ChatRequest(user_message=query, messages=[{"role": "user", "content": query}], session_id="eval-single-session")

    start = asyncio.get_event_loop().time()
    res = await engine._execute_batch(chat_request=chat_req, user={"id": "eval-user"}, is_benchmark=True)
    elapsed = asyncio.get_event_loop().time() - start

    print("\n" + "=" * 80)
    print(f"⏱️ Response Time: {elapsed:.2f}s")
    print(f"🤖 Model Used: {res.model_used}")
    print("=" * 80)
    print(res.final_answer)
    print("=" * 80 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
