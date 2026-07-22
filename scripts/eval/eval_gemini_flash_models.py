#!/usr/bin/env python3
"""
Evaluate OpenRouter Gemini Flash Models (3.6 Flash, 3.5 Flash, 3.5 Flash-Lite, 2.5 Flash).
Flushes cache before each model run and evaluates:
"I want to experience deeper inner peace. What teachings or practices do you suggest?"
"""

import asyncio
import logging
import os
import subprocess
import sys

# Set host env vars
os.environ["NEO4J_URI"] = "bolt://localhost:7687"
os.environ["QDRANT_URL"] = "http://localhost:6333"

backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "backend"))
env_path = os.path.join(backend_dir, ".env")
if os.path.exists(env_path):
    try:
        from dotenv import load_dotenv
        load_dotenv(env_path)
    except ImportError:
        pass

sys.path.insert(0, backend_dir)

from app.config import settings
from services.openrouter_service import OpenRouterService
from rag.nodes.guru_tone_adapter import GuruToneAdapterNode
from services.guru_brain.persona_discriminator import PersonaDiscriminator
from services.guru_brain.guru_brain_service import GuruBrainService
from services.guru_brain.guru_kg_service import GuruKGService
from services.qdrant_service import QdrantService

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("eval_gemini_flash")

TEST_QUERY = "I want to experience deeper inner peace. What teachings or practices do you suggest?"
FACTUAL_DRAFT = (
    "To experience deeper inner peace, Sri Preethaji and Sri Krishnaji teach that you must transition from a "
    "Suffering State into a Beautiful State. Inner peace is not found by changing external circumstances, but by "
    "mastering your Inner World. Observe the habitual thoughts and stories created by the ego without judgment. "
    "Bring total awareness to the present moment.\n\n"
    "### ✨ Practice: Soul Sync Meditation\n"
    "1. Sit comfortably with your spine erect and eyes closed.\n"
    "2. Take slow, deep conscious breaths, bringing full attention to your heart center.\n"
    "3. Witness any rising thoughts as mere fleeting clouds, remaining as pure unmoving awareness.\n"
    "4. Silently hold the intention: 'May all beings be free of suffering. May all beings be in a beautiful state.'"
)

GEMINI_MODELS = [
    ("google/gemini-3.6-flash", "Google Gemini 3.6 Flash"),
    ("google/gemini-3.5-flash", "Google Gemini 3.5 Flash"),
    ("google/gemini-3.5-flash-lite", "Google Gemini 3.5 Flash Lite"),
    ("google/gemini-2.5-flash", "Google Gemini 2.5 Flash"),
]

def flush_caches():
    """Flush Docker Redis and Qdrant semantic query cache before each model run."""
    logger.info("🧹 Flushing Docker Redis & Qdrant caches...")
    try:
        docker_cmd = ["docker", "exec", "mukthiguru-redis", "redis-cli", "-a", "mukthiguru_redis_pass", "FLUSHALL"]
        subprocess.run(docker_cmd, capture_output=True, text=True, check=False)
    except Exception as e:
        logger.warning(f"Redis flush warning: {e}")

    try:
        flush_script = os.path.join(os.path.dirname(__file__), "..", "ops", "flush_cache.py")
        subprocess.run([sys.executable, flush_script], capture_output=True, text=True, check=False)
    except Exception as e:
        logger.warning(f"Flush script warning: {e}")

async def run_evaluation():
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        logger.error("OPENROUTER_API_KEY is missing!")
        return

    qdrant_svc = QdrantService()
    guru_brain = GuruBrainService(qdrant_service=qdrant_svc)
    guru_kg = GuruKGService()

    logger.info("Starting Gemini Flash OpenRouter Evaluation...")
    logger.info(f"Target Seeker Question: '{TEST_QUERY}'\n")

    results = []

    for model_id, model_name in GEMINI_MODELS:
        flush_caches()
        logger.info(f"--- Evaluating Model: {model_name} ({model_id}) ---")
        try:
            settings.openrouter_generation_model = model_id
            llm_service = OpenRouterService()
            discriminator = PersonaDiscriminator(llm_service=llm_service)
            adapter = GuruToneAdapterNode(
                guru_brain_service=guru_brain,
                guru_kg_service=guru_kg,
                llm_service=llm_service,
                persona_discriminator=discriminator,
            )

            state_input = {
                "question": TEST_QUERY,
                "final_answer": FACTUAL_DRAFT,
                "guru_name": "combined",
                "request_id": f"eval-{model_id.replace('/', '_')}",
            }

            start_t = asyncio.get_event_loop().time()
            res_state = await adapter.transform_tone(state_input)
            elapsed = asyncio.get_event_loop().time() - start_t

            transformed_ans = res_state.get("final_answer", "") if isinstance(res_state, dict) else str(res_state)

            eval_res = await discriminator.evaluate_persona(user_query=TEST_QUERY, response_text=transformed_ans)

            results.append({
                "model_id": model_id,
                "model_name": model_name,
                "latency_s": round(elapsed, 2),
                "score": eval_res.overall_score,
                "intimacy": eval_res.intimacy_score,
                "kg_ontology": eval_res.ontology_score,
                "cliche_penalty": eval_res.cliche_penalty,
                "response": transformed_ans,
            })
            logger.info(f"Model {model_name} -> Score: {eval_res.overall_score:.1f}/10 (Latency: {elapsed:.2f}s)\n")

        except Exception as exc:
            logger.error(f"Failed to evaluate {model_name}: {exc}\n")

    print("\n" + "=" * 80)
    print(" 🏆 GEMINI FLASH OPENROUTER BENCHMARK RESULTS")
    print("=" * 80)
    for r in results:
        print(f"\n📌 Model: {r['model_name']} ({r['model_id']})")
        print(f"   - Latency: {r['latency_s']}s")
        print(f"   - Overall Score: {r['score']:.1f} / 10.0")
        print(f"   - Intimacy: {r['intimacy']:.1f} | KG Alignment: {r['kg_ontology']:.1f} | Cliché Penalty: {r['cliche_penalty']:.1f}")
        print(f"   - Generated Response Sample:\n{r['response']}\n")

if __name__ == "__main__":
    asyncio.run(run_evaluation())
