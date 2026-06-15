import asyncio
import os
import sys

# Add backend to path so we can import services
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../backend")))

from app.config import settings
from services.openrouter_service import OpenRouterService

async def test():
    service = OpenRouterService()
    questions = [
        "What is the relationship between suffering and inner truth?",
        "Can I apply Spiritual Right Action to decide if I should launch a hostile takeover of a rival tech startup?",
        "Mera mind bohot dysfunctional ho gaya hai, hamesha suffering state me rehta hu. Kaise isko beautiful state me badlu?",
        "Can I practice Soul Sync on Mars or does the gravity mess up the golden light?",
    ]
    for q in questions:
        res = await service.classify_intent_and_complexity(q)
        print(f"Q: {q}\nResult: {res}\n")

if __name__ == "__main__":
    asyncio.run(test())
