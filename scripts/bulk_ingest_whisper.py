#!/usr/bin/env python3
"""
Mukthi Guru — Bulk Knowledge Ingestion (Hardened)

Scope: The Four Sacred Secrets ONLY.
Strategy:
  1. PageIndex → Qdrant (specialized page-aware chunking)
  2. Chunked LightRAG → Neo4j (graph entity extraction in safe ~8K segments)

Environment: Must be run from the project root with PYTHONPATH set:
  export PYTHONPATH=$PYTHONPATH:$(pwd)/backend
  source .venv_host/bin/activate
  python scripts/bulk_ingest_whisper.py
"""
import sys
import os
import asyncio
import time
import logging
import json
import subprocess

# ── Setup Paths ─────────────────────────────────────────────
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BACKEND_DIR = os.path.join(BASE_DIR, "backend")
sys.path.insert(0, BACKEND_DIR)

# ── Load env vars from .env (secrets stay out of source) ────
from dotenv import load_dotenv

# Load backend/.env for Sarvam API key and other config
load_dotenv(os.path.join(BACKEND_DIR, ".env"))

# Override infrastructure URLs for host-side execution (not Docker-internal)
os.environ["QDRANT_URL"] = "http://localhost:6333"
os.environ["NEO4J_URI"] = "bolt://localhost:7687"
os.environ["NEO4J_USERNAME"] = "neo4j"
os.environ["NEO4J_PASSWORD"] = os.environ.get("NEO4J_PASSWORD", "mukthiguru_neo4j_pass")
os.environ["REDIS_URL"] = f"redis://:{os.environ.get('REDIS_PASSWORD', 'mukthiguru_redis_pass')}@localhost:6379/0"
os.environ["SUPABASE_URL"] = "http://localhost:54321"
os.environ["WHISPER_ONLY"] = "true"

# Ensure system tools and venv tools are in path
VENV_BIN = os.path.abspath(os.path.join(BASE_DIR, ".venv_host/bin"))
os.environ["PATH"] = f"{VENV_BIN}:/opt/homebrew/bin:/usr/local/bin:{os.environ['PATH']}"

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)
logger = logging.getLogger("bulk_ingest")

STATE_FILE = os.path.join(BASE_DIR, "scripts/ingestion_state.json")

# ── Chunked LightRAG Insertion ──────────────────────────────
LIGHTRAG_CHUNK_SIZE = 8000   # chars per chunk (safe for graph extraction)
LIGHTRAG_CHUNK_OVERLAP = 500  # overlap to preserve context at boundaries
LIGHTRAG_SLEEP_BETWEEN = 3.0  # seconds between chunks (thermal throttling)


def chunk_text(text: str, chunk_size: int = LIGHTRAG_CHUNK_SIZE, overlap: int = LIGHTRAG_CHUNK_OVERLAP) -> list[str]:
    """Split text into overlapping chunks at sentence boundaries."""
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))

        # Try to break at sentence boundary
        if end < len(text):
            # Look backwards from 'end' for a sentence-ending punctuation
            for boundary_char in ['. ', '.\n', '!\n', '?\n', '! ', '? ']:
                last_boundary = text.rfind(boundary_char, start + chunk_size // 2, end)
                if last_boundary != -1:
                    end = last_boundary + len(boundary_char)
                    break

        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)

        # Move forward, subtracting overlap
        start = max(start + 1, end - overlap)

    return chunks


async def safe_lightrag_insert(lightrag_service, full_text: str, source_name: str):
    """Insert text into LightRAG in safe, chunked segments to prevent SIGSEGV."""
    chunks = chunk_text(full_text)
    total = len(chunks)
    logger.info(f"LightRAG: Splitting {len(full_text):,} chars into {total} chunks (~{LIGHTRAG_CHUNK_SIZE} chars each)")

    for i, chunk in enumerate(chunks, 1):
        logger.info(f"LightRAG: Inserting chunk {i}/{total} ({len(chunk):,} chars) for [{source_name}]")
        try:
            await lightrag_service.ainsert(chunk)
            logger.info(f"LightRAG: ✅ Chunk {i}/{total} done")
        except Exception as e:
            logger.error(f"LightRAG: ❌ Chunk {i}/{total} failed: {e}")
            # Continue with remaining chunks — partial graph is better than none

        if i < total:
            logger.info(f"LightRAG: Cooling down {LIGHTRAG_SLEEP_BETWEEN}s...")
            await asyncio.sleep(LIGHTRAG_SLEEP_BETWEEN)

    logger.info(f"LightRAG: ✅ All {total} chunks processed for [{source_name}]")


async def main():
    from app.dependencies import get_container
    container = get_container()

    # Initialize LightRAG for Knowledge Graph extraction
    if container.lightrag:
        await container.lightrag.initialize()

    pipeline = container.ingestion

    # ── Load State ──────────────────────────────────────────
    state = {"processed_videos": [], "processed_docs": [], "metrics": {}}
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f:
            state = json.load(f)
    if "metrics" not in state:
        state["metrics"] = {}

    def save_state():
        with open(STATE_FILE, "w") as f:
            json.dump(state, f, indent=2)

    # ── Ingest: The Four Sacred Secrets ─────────────────────
    doc_name = "The_Four_Sacred_Secrets.pdf"
    doc_path = os.path.join(BASE_DIR, doc_name)

    if doc_name in state["processed_docs"]:
        logger.info(f"⏭️  Skipping already processed document: {doc_name}")
    elif not os.path.exists(doc_path):
        logger.error(f"❌ Document not found: {doc_path}")
    else:
        logger.info(f"{'='*60}")
        logger.info(f"INGESTING: {doc_name}")
        logger.info(f"{'='*60}")
        start_time = time.time()

        try:
            # STEP 1: PageIndex → Qdrant (specialized page-aware chunking)
            logger.info("Step 1/2: PageIndex → Qdrant (page-aware vector ingestion)...")
            ingest_script = os.path.join(BASE_DIR, "scripts/ingest_four_sacred_secrets.py")
            if os.path.exists(ingest_script):
                cmd = [sys.executable, ingest_script]
                env = os.environ.copy()
                env["PYTHONPATH"] = f"{BACKEND_DIR}:{env.get('PYTHONPATH', '')}"
                subprocess.run(cmd, env=env, check=True)
                logger.info("Step 1/2: ✅ PageIndex → Qdrant complete")
            else:
                logger.warning(f"PageIndex script not found: {ingest_script}, using standard ingest")
                await pipeline.ingest_file(doc_path)

            # STEP 2: Chunked LightRAG → Neo4j (graph entity extraction)
            logger.info("Step 2/2: LightRAG → Neo4j (chunked graph extraction)...")
            json_path = os.path.join(BASE_DIR, "results/The_Four_Sacred_Secrets_structure.json")
            if os.path.exists(json_path) and container.lightrag:
                with open(json_path, "r") as f:
                    data = json.load(f)

                # Extract full text from structure nodes
                def get_text_recursive(nodes):
                    t = ""
                    for n in nodes:
                        t += n.get("text", "") + "\n"
                        t += n.get("summary", "") + "\n"
                        if "nodes" in n:
                            t += get_text_recursive(n["nodes"])
                    return t

                full_text = get_text_recursive(data.get("structure", []))
                if full_text.strip():
                    await safe_lightrag_insert(container.lightrag, full_text, doc_name)
                    logger.info("Step 2/2: ✅ LightRAG → Neo4j complete")
                else:
                    logger.warning("No text extracted from structure JSON")
            elif not container.lightrag:
                logger.warning("LightRAG not available — skipping graph extraction")
            else:
                logger.warning(f"Structure JSON not found: {json_path}")

            latency = time.time() - start_time
            state["processed_docs"].append(doc_name)
            state["metrics"][doc_name] = {
                "latency": latency,
                "status": "success",
            }
            save_state()
            logger.info(f"✅ Document Ingested: {doc_name} in {latency:.1f}s")

        except Exception as e:
            latency = time.time() - start_time
            state["metrics"][doc_name] = {
                "latency": latency,
                "status": "failed",
                "error": str(e),
            }
            save_state()
            logger.error(f"❌ Document Failed: {doc_name} | {e}", exc_info=True)

    # ── Summary ─────────────────────────────────────────────
    logger.info(f"\n{'='*60}")
    logger.info("BULK INGESTION COMPLETE")
    logger.info(f"{'='*60}")
    logger.info(f"Total Docs Processed: {len(state['processed_docs'])}")
    for doc in state["processed_docs"]:
        m = state["metrics"].get(doc, {})
        logger.info(f"  📄 {doc} — {m.get('status', 'unknown')} ({m.get('latency', 0):.1f}s)")
    logger.info(f"{'='*60}")


if __name__ == "__main__":
    asyncio.run(main())
