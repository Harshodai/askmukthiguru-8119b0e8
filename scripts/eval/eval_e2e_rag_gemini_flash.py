#!/usr/bin/env python3
"""
Full E2E RAG Evaluation — NO hardcoded draft.
Runs the real pipeline (Retrieval → RAG → Tone Adaptation) via ChatEngine.
Evaluates Gemini 3.6 Flash, Gemini 3.5 Flash, Gemini 2.5 Flash.
Flushes both Redis & Qdrant semantic cache before every model run.
"""

import asyncio
import logging
import os
import subprocess
import sys

os.environ.setdefault("NEO4J_URI", "bolt://localhost:7687")
os.environ.setdefault("QDRANT_URL", "http://localhost:6333")

backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "backend"))
env_path = os.path.join(backend_dir, ".env")
if os.path.exists(env_path):
    try:
        from dotenv import load_dotenv
        load_dotenv(env_path, override=False)
    except ImportError:
        pass

sys.path.insert(0, backend_dir)

from app.config import settings
from services.container_builder import ContainerBuilder
from app.chat_engine import ChatEngine
from services.openrouter_service import OpenRouterService
from services.guru_brain.persona_discriminator import PersonaDiscriminator

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("eval_e2e_real")

TEST_QUERY = "I want to experience deeper inner peace. What teachings or practices do you suggest?"

MODELS = [
    ("google/gemini-3.6-flash", "Gemini 3.6 Flash"),
    ("google/gemini-3.5-flash", "Gemini 3.5 Flash"),
    ("google/gemini-2.5-flash", "Gemini 2.5 Flash"),
]


def flush_caches():
    """Flush Redis + Qdrant semantic cache before each run."""
    logger.info("🧹 Flushing Redis & Qdrant caches...")
    try:
        subprocess.run(
            ["docker", "exec", "mukthiguru-redis", "redis-cli", "-a", "mukthiguru_redis_pass", "FLUSHALL"],
            capture_output=True, check=False,
        )
    except Exception as e:
        logger.warning(f"Redis flush: {e}")
    try:
        script = os.path.join(os.path.dirname(__file__), "..", "ops", "flush_cache.py")
        subprocess.run([sys.executable, script], capture_output=True, check=False)
    except Exception as e:
        logger.warning(f"Qdrant flush: {e}")


async def run():
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        logger.error("OPENROUTER_API_KEY missing!")
        return

    logger.info("=" * 80)
    logger.info("FULL E2E RAG EVALUATION — Real retrieval, no hardcoded draft")
    logger.info(f"Query: '{TEST_QUERY}'")
    logger.info("=" * 80 + "\n")

    results = []

    for model_id, model_name in MODELS:
        flush_caches()
        logger.info(f"\n🚀 Model: {model_name} ({model_id})")
        logger.info("-" * 60)

        try:
            # Swap generation model before building container
            settings.openrouter_generation_model = model_id

            container = ContainerBuilder().build()
            engine = ChatEngine(container=container)

            # Real discriminator using same OpenRouter model
            llm_svc = OpenRouterService()
            discriminator = PersonaDiscriminator(llm_service=llm_svc)

            t0 = asyncio.get_event_loop().time()
            final_text = await engine.chat(
                message=TEST_QUERY,
                user_id="e2e-eval-user",
            )
            elapsed = asyncio.get_event_loop().time() - t0

            # Score against persona discriminator
            eval_res = await discriminator.evaluate_persona(
                user_query=TEST_QUERY,
                response_text=final_text,
            )

            results.append({
                "model_id": model_id,
                "model_name": model_name,
                "latency_s": round(elapsed, 2),
                "score": eval_res.overall_score,
                "intimacy": eval_res.intimacy_score,
                "kg_align": eval_res.ontology_score,
                "cliche": eval_res.cliche_penalty,
                "response": final_text,
            })

            logger.info(f"✅ Score: {eval_res.overall_score:.1f}/10 | Latency: {elapsed:.2f}s")
            logger.info(f"   Intimacy: {eval_res.intimacy_score:.1f} | OKF: {eval_res.ontology_score:.1f} | Cliché: {eval_res.cliche_penalty:.1f}")

        except Exception as exc:
            logger.error(f"❌ {model_name}: {exc}", exc_info=True)

    # ── Final leaderboard ──
    print("\n" + "=" * 80)
    print("  🏆 E2E RAG BENCHMARK — GEMINI FLASH FAMILY (Real pipeline, no draft)")
    print("=" * 80)
    for r in sorted(results, key=lambda x: x["score"], reverse=True):
        print(f"\n📌 {r['model_name']} ({r['model_id']})")
        print(f"   Latency   : {r['latency_s']}s")
        print(f"   Score     : {r['score']:.1f}/10  |  Intimacy: {r['intimacy']:.1f}  OKF: {r['kg_align']:.1f}  Cliché: {r['cliche']:.1f}")
        print(f"\n   ── Answer ──────────────────────────────────────────────────────")
        print(f"   {r['response'][:1200]}")
        print(f"   ────────────────────────────────────────────────────────────────\n")


if __name__ == "__main__":
    asyncio.run(run())
