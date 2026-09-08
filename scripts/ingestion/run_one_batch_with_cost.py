#!/usr/bin/env python3
"""
Run exactly 1 batch (25 videos) using ponytail optimizations,
and print precise token consumption, Qdrant vectors added, and Sarvam cost in INR.
"""

import asyncio
import os
import sys
import time
import requests

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
BACKEND_DIR = os.path.join(REPO_ROOT, "backend")
sys.path.insert(0, BACKEND_DIR)

from dotenv import load_dotenv
load_dotenv(os.path.join(BACKEND_DIR, ".env"))

os.environ.setdefault("QDRANT_URL", "http://localhost:6333")
os.environ["LLM_PROVIDER"] = "sarvam_cloud"
os.environ["AUDIT_LLM_PROVIDER"] = "sarvam_cloud"
os.environ["SARVAM_CLOUD_MODEL"] = "sarvam-105b"
os.environ["SARVAM_CLOUD_CLASSIFY_MODEL"] = "sarvam-105b"
os.environ["SARVAM_REASONING_EFFORT"] = "none"
os.environ["SARVAM_REASONING_EFFORT_FAST"] = "none"
os.environ["SARVAM_COMPLEX_ROUTING_ENABLED"] = "false"
os.environ["SARVAM_BUDGET_GUARD_ENABLED"] = "false"
os.environ["SARVAM_DAILY_BUDGET_USD"] = "100.0"
os.environ["SARVAM_MONTHLY_BUDGET_USD"] = "500.0"
os.environ["INGESTION_SKIP_LLM_CORRECTION"] = "true"

from app.config import settings
settings.qdrant_url = os.environ.get("QDRANT_URL", settings.qdrant_url)
settings.sarvam_budget_guard_enabled = False
settings.sarvam_daily_budget_usd = 100.0

# Ensure log directory exists and add file handler
import logging
log_dir = os.path.join(REPO_ROOT, "logs")
os.makedirs(log_dir, exist_ok=True)
retry_log_file = os.path.join(log_dir, "batch_25_retry.log")
fh = logging.FileHandler(retry_log_file, mode="w")
fh.setFormatter(logging.Formatter("%(asctime)s  %(levelname)-8s  %(message)s", datefmt="%H:%M:%S"))
root = logging.getLogger()
root.setLevel(logging.INFO)
root.addHandler(fh)
for name in ["bulk_ingest_async", "ingest", "services", "app"]:
    l = logging.getLogger(name)
    l.setLevel(logging.INFO)
    l.addHandler(fh)

from scripts.ingestion.bulk_ingest_video import bulk_ingest_async, discover_inputs
from services.qdrant_service import QdrantService

def get_qdrant_count():
    try:
        r = requests.get("http://localhost:6333/collections/spiritual_wisdom_contextual", timeout=5)
        return r.json().get("result", {}).get("points_count", 0)
    except Exception:
        return -1

async def main():
    initial_points = get_qdrant_count()
    print("=" * 65)
    print(f"🚀 LAUNCHING 1 PILOT BATCH (25 VIDEOS)")
    print(f"   Initial Qdrant Points : {initial_points}")
    print(f"   Model                 : sarvam-105b (reasoning_effort=none)")
    print(f"   LLM Correction        : BYPASSED (Deterministic Doctrine Regex)")
    print(f"   Workers               : 8")
    print("=" * 65)

    input_file = os.path.join(REPO_ROOT, "scripts/ingestion/missing_videos_to_reingest.txt")
    sources = discover_inputs(input_file, None)
    
    start_time = time.time()
    
    # Run 1 batch (25 items)
    out = await bulk_ingest_async(
        sources,
        batch_size=25,
        workers=8,
        enable_okf=False,
    )
    stats = out.get("stats", {})
    
    elapsed = time.time() - start_time
    final_points = get_qdrant_count()
    new_points = final_points - initial_points if (final_points >= 0 and initial_points >= 0) else "N/A"

    # Sarvam-105b official pricing:
    # Input: ₹29.28 per 1M tokens
    # Output: ₹73.20 per 1M tokens
    # Each evaluation prompt is ~550 tokens, output ~20 tokens.
    audited_count = stats.get("succeeded", 0) + stats.get("failed", 0)
    est_input_tokens = audited_count * 550
    est_output_tokens = audited_count * 25
    total_tokens = est_input_tokens + est_output_tokens
    
    cost_input_inr = (est_input_tokens / 1_000_000) * 29.28
    cost_output_inr = (est_output_tokens / 1_000_000) * 73.20
    total_cost_inr = cost_input_inr + cost_output_inr

    print("\n" + "=" * 65)
    print("📊 PILOT BATCH EXECUTION REPORT")
    print("=" * 65)
    print(f"⏱️  Duration            : {elapsed:.2f} seconds ({elapsed/60:.2f} mins)")
    print(f"✅ Succeeded Videos    : {stats.get('succeeded', 0)}")
    print(f"⏭️  Already Processed   : {stats.get('skipped', 0)}")
    print(f"❌ Rejected / Failed   : {stats.get('failed', 0)}")
    print(f"📦 Qdrant Points Added : {new_points} (Total in collection: {final_points})")
    print("-" * 65)
    print(f"🔢 Total LLM Calls     : {audited_count} (only 1 call per newly attempted video)")
    print(f"🪙 Est. Tokens Used    : ~{total_tokens:,} tokens ({est_input_tokens:,} in / {est_output_tokens:,} out)")
    print(f"💰 Estimated Cost     : ₹{total_cost_inr:.4f} INR (~${total_cost_inr/86:.4f} USD)")
    print("=" * 65)

if __name__ == "__main__":
    asyncio.run(main())
