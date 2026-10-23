import asyncio
import logging
import os
import sys

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
BACKEND_DIR = os.path.join(BASE_DIR, "backend")
sys.path.insert(0, BACKEND_DIR)

# Must set environment BEFORE importing dependencies which loads config
os.environ["LLM_PROVIDER"] = "sarvam_cloud"
os.environ["WHISPER_LOCAL_MODEL"] = "mlx-community/whisper-large-v3-turbo"
os.environ["WHISPER_LOCAL_DEVICE"] = "mps"

from app.dependencies import get_container

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("retry_failed")

FAILED_IDS = [
    "nwQaU-agzFE",
    "hUmlujE6SN0",
    "RAOQ3ZubQGM",
    "0z-IZ2ar4eA",
    "WIUa93sXmPw",
    "sCiK7ABPcrw",
    "VxJWAmiYu_0",
    "rGcNJ_Nsuy8",
    "STlEq16n8kI",
    "NFlAszNFZdQ",
    "btbKcsb9Dzw",
]


async def retry_failed():
    logger.info("Initializing Service Container for Retry...")
    container = get_container()
    pipeline = container.ingestion

    for vid in FAILED_IDS:
        url = f"https://www.youtube.com/watch?v={vid}"
        logger.info(f"🔄 Retrying failed video: {url}")
        try:
            res = await pipeline.ingest_url(url, max_accuracy=False)
            if res.get("status") == "success":
                logger.info(f"✅ Success on retry: {url}")
            else:
                logger.error(f"❌ Still failing: {url} - {res.get('message')}")
        except Exception as e:
            logger.error(f"❌ Error on {url}: {e}")


if __name__ == "__main__":
    os.environ["LLM_PROVIDER"] = "sarvam_cloud"
    asyncio.run(retry_failed())
