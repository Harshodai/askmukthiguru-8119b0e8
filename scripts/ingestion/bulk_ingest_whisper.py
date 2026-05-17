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
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
BACKEND_DIR = os.path.join(BASE_DIR, "backend")
sys.path.insert(0, BACKEND_DIR)

# ── Load env vars from .env (secrets stay out of source) ────
from dotenv import load_dotenv

# Load backend/.env for Sarvam API key and other config
load_dotenv(os.path.join(BACKEND_DIR, ".env"))

# Override infrastructure URLs for host-side execution (not Docker-internal)
os.environ["LLM_PROVIDER"] = "ollama"
os.environ["OLLAMA_MODEL"] = "deepseek-r1:7b"
os.environ["OLLAMA_CLASSIFY_MODEL"] = "deepseek-r1:7b"
os.environ["SARVAM_API_KEY"] = "none"
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

log_format = '%(asctime)s [%(levelname)s] %(name)s: %(message)s'
log_file = os.path.join(BASE_DIR, "scripts/ingestion_status.log")

logging.basicConfig(
    level=logging.INFO,
    format=log_format,
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(log_file, mode='a', encoding='utf-8')
    ]
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
            # Prepend clear contextual source name header directly to text inserted into knowledge graph
            chunk_with_header = f"[Source: {source_name}]\n{chunk}"
            await lightrag_service.ainsert(chunk_with_header)
            logger.info(f"LightRAG: ✅ Chunk {i}/{total} done")
        except Exception as e:
            logger.error(f"LightRAG: ❌ Chunk {i}/{total} failed: {e}")
            # Continue with remaining chunks — partial graph is better than none

        if i < total:
            logger.info(f"LightRAG: Cooling down {LIGHTRAG_SLEEP_BETWEEN}s...")
            await asyncio.sleep(LIGHTRAG_SLEEP_BETWEEN)

    logger.info(f"LightRAG: ✅ All {total} chunks processed for [{source_name}]")


# ── YouTube Ingestion Configuration ─────────────────────────
PLAYLIST_URLS = [
    "https://www.youtube.com/playlist?list=PLOVU2e0ZosYDt1cdrKnT1AZs4UHpFU5wo",
    "https://www.youtube.com/playlist?list=PLOVU2e0ZosYAVXIxzJLscsY7bdpB8vhxU",
    "https://www.youtube.com/playlist?list=PLOVU2e0ZosYCZoSlsJgsCRwAKSn9k1YuK",
    "https://www.youtube.com/playlist?list=PLOVU2e0ZosYDmh7p1PgnP-_tgUYqyXPtL",
    "https://www.youtube.com/playlist?list=PLOVU2e0ZosYCTBAlMLmObAThmuHcXNEOX",
    "https://www.youtube.com/playlist?list=PLOVU2e0ZosYA7uSMmmEKwe0Obgz1d1jRc",
    "https://www.youtube.com/playlist?list=PLOVU2e0ZosYC595WV7FBH289VgWl3b7ag",
    "https://www.youtube.com/playlist?list=PLOVU2e0ZosYD-DlHYhKWl0emMFdZ1RVRS",
    "https://www.youtube.com/playlist?list=PLOVU2e0ZosYASfJzL48hq1SCn2R-hgzc0",
    "https://www.youtube.com/playlist?list=PLOVU2e0ZosYBSc9RMV9VRiVmHaMH-O39W",
    "https://www.youtube.com/playlist?list=PLOVU2e0ZosYDEhRkk3-4HfMC4779U5iDU",
    "https://www.youtube.com/playlist?list=PLOVU2e0ZosYBGXFR_4jCmVntbgBa3sx1y",
    "https://www.youtube.com/playlist?list=PLOVU2e0ZosYASkt24BpnguWFJxbVH9msA",
    "https://www.youtube.com/playlist?list=PLOVU2e0ZosYAmto9MigKY42WaYh3VA9WX",
    "https://www.youtube.com/playlist?list=PLOVU2e0ZosYCAolwoj_qQuhhFdUiwhfpB",
    "https://www.youtube.com/playlist?list=PLOVU2e0ZosYBf8aBXcB4fvJBBHB4qY4Id",
    "https://www.youtube.com/playlist?list=PLOVU2e0ZosYAnKphMrZs9FnKHLvDp5mz9",
    "https://www.youtube.com/playlist?list=PLOVU2e0ZosYBi5t50biQKPGiGVy_tl5x5",
    "https://www.youtube.com/playlist?list=PLOVU2e0ZosYCTKE3_cQvMGNUwB4LeXXjI",
    "https://www.youtube.com/playlist?list=PLOVU2e0ZosYAZ4sVGeWaQwelTckkbftBt",
]


CORE_VIDEO_IDS = [
    "69IrsSXeBTg",  # Soul Sync
    "igSp4H0OWLE",  # Serene Mind
    "TqxxCYnAxo8",  # Beautiful State
    "O-6f5wQXSu8",  # Daily Reflection
]

INTER_VIDEO_DELAY = 5


def get_video_ids_from_playlist(playlist_url: str) -> list[str]:
    """Resolve playlist URL to video IDs via yt-dlp."""
    try:
        result = subprocess.run(
            ["yt-dlp", "--flat-playlist", "--print", "id",
             "--playlist-items", "1-1000", playlist_url],
            capture_output=True, text=True, timeout=300
        )
        if result.returncode != 0:
            logger.error(f"yt-dlp error: {result.stderr[:200]}")
            return []
        ids = [l.strip() for l in result.stdout.strip().split("\n") if l.strip()]
        logger.info(f"Playlist resolved: {len(ids)} videos")
        return ids
    except Exception as e:
        logger.error(f"Playlist expansion failed: {e}")
        return []


async def fetch_transcript_text(video_id: str) -> str:
    """Fetch transcript text using the backend's hybrid loader (which triggers local Whisper if configured)."""
    try:
        from ingest.youtube_loader import fetch_transcript_hybrid
        # Run in executor because fetch_transcript_hybrid is sync and contains downloads/Whisper calls
        loop = asyncio.get_running_loop()
        res = await loop.run_in_executor(None, lambda: fetch_transcript_hybrid(video_id, max_accuracy=True))
        if res and res.get("text"):
            return res["text"]
    except Exception as e:
        logger.error(f"fetch_transcript_hybrid failed for {video_id}: {e}")

    # Fallback to youtube_transcript_api
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
        transcript_list = YouTubeTranscriptApi.get_transcript(video_id)
        return " ".join([item["text"] for item in transcript_list])
    except Exception as e:
        logger.warning(f"youtube_transcript_api failed for {video_id}: {e}")

    return ""


async def main():
    # ── macOS Sleep Prevention ──────────────────────────────
    caffeinate_proc = None
    if sys.platform == "darwin":
        logger.info("macOS detected: Spawning 'caffeinate' to prevent system sleep during ingestion...")
        try:
            caffeinate_proc = subprocess.Popen(["caffeinate", "-w", str(os.getpid())])
            logger.info("✅ macOS caffeinate is active. Your laptop will not sleep during this ingestion.")
        except Exception as e:
            logger.warning(f"Failed to start caffeinate: {e}")

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
    if "processed_videos" not in state:
        state["processed_videos"] = []
    if "processed_docs" not in state:
        state["processed_docs"] = []

    def save_state():
        with open(STATE_FILE, "w") as f:
            json.dump(state, f, indent=2)

    # ── Ingest: The Four Sacred Secrets (Book) ──────────────
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
            ingest_script = os.path.join(BASE_DIR, "scripts", "ingestion", "ingest_four_sacred_secrets.py")
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

    # ── Ingest: YouTube Playlists & Videos (Dual Ingestion) ──
    logger.info(f"\n{'='*60}")
    logger.info("RESOLVING YOUTUBE PLAYLISTS & VIDEO IDS")
    logger.info(f"{'='*60}")
    all_ids = []
    for pl in PLAYLIST_URLS:
        logger.info(f"Resolving playlist: {pl}")
        all_ids.extend(get_video_ids_from_playlist(pl))
    all_ids += CORE_VIDEO_IDS

    seen = set()
    unique_ids = [v for v in all_ids if not (v in seen or seen.add(v))]
    logger.info(f"🎯 Total unique videos queued: {len(unique_ids)}")

    for vid in unique_ids:
        if vid in state["processed_videos"]:
            logger.info(f"⏭️  Skipping already processed video: {vid}")
            continue

        url = f"https://www.youtube.com/watch?v={vid}"
        logger.info(f"\n{'='*60}\n[Video Ingestion] {vid}\n{'='*60}")
        
        max_attempts = 3
        retry_delay = 15  # base retry delay in seconds
        success = False

        for attempt in range(1, max_attempts + 1):
            start_video_time = time.time()
            try:
                # STEP 1: Qdrant (dense+sparse vectors via hybrid pipeline)
                logger.info(f"[Qdrant] Ingesting video: {url} (Attempt {attempt}/{max_attempts})...")
                res = await pipeline.ingest_url(url, max_accuracy=True)
                
                # Check status return to throw error and trigger the retry delays
                if res.get("status") == "error":
                    raise ValueError(res.get("message", "Ingestion pipeline returned error status"))
                    
                chunks = res.get("chunks_indexed", 0)
                title = res.get("title") or res.get("metadata", {}).get("title") or "Unknown"
                logger.info(f"[Qdrant] ✅ Success | Title: {title} | Chunks: {chunks}")

                # STEP 2: LightRAG/Neo4j (knowledge graph via safe chunked insertion)
                if container.lightrag:
                    logger.info(f"[LightRAG] Fetching transcript for video: {vid}...")
                    text = await fetch_transcript_text(vid)
                    if text.strip():
                        # Prepend clear video details and URL in source name
                        source_name = f"YouTube Video: {title} (URL: {url})"
                        await safe_lightrag_insert(container.lightrag, text, source_name)
                        logger.info(f"[LightRAG] ✅ Success")
                    else:
                        logger.warning(f"[LightRAG] ⚠️ No transcript content retrieved")
                else:
                    logger.warning(f"[LightRAG] Service not active — skipping")

                latency = time.time() - start_video_time
                state["processed_videos"].append(vid)
                state["metrics"][vid] = {
                    "latency": latency,
                    "status": "success",
                    "title": title
                }
                save_state()
                logger.info(f"✅ Video Ingested: {vid} ({title}) in {latency:.1f}s")
                success = True
                break

            except Exception as e:
                latency = time.time() - start_video_time
                logger.warning(f"⚠️ Attempt {attempt}/{max_attempts} failed for video {vid}: {e}")
                if attempt < max_attempts:
                    sleep_time = retry_delay * attempt
                    logger.info(f"Retrying in {sleep_time}s after cooldown...")
                    await asyncio.sleep(sleep_time)
                else:
                    state["metrics"][vid] = {
                        "latency": latency,
                        "status": "failed",
                        "error": str(e),
                    }
                    save_state()
                    logger.error(f"❌ Video Failed after {max_attempts} attempts: {vid} | {e}", exc_info=True)

        if vid != unique_ids[-1]:
            logger.info(f"Waiting {INTER_VIDEO_DELAY}s between videos...")
            await asyncio.sleep(INTER_VIDEO_DELAY)

    # ── Summary ─────────────────────────────────────────────
    logger.info(f"\n{'='*60}")
    logger.info("BULK INGESTION COMPLETE")
    logger.info(f"{'='*60}")
    logger.info(f"Total Docs Processed: {len(state['processed_docs'])}")
    for doc in state["processed_docs"]:
        m = state["metrics"].get(doc, {})
        logger.info(f"  📄 {doc} — {m.get('status', 'unknown')} ({m.get('latency', 0):.1f}s)")

    logger.info(f"\nTotal Videos Processed: {len(state['processed_videos'])}")
    for vid in state["processed_videos"]:
        m = state["metrics"].get(vid, {})
        title = m.get('title', 'Unknown')
        logger.info(f"  🎥 {vid} ({title}) — {m.get('status', 'unknown')} ({m.get('latency', 0):.1f}s)")
    logger.info(f"{'='*60}")


if __name__ == "__main__":
    asyncio.run(main())
