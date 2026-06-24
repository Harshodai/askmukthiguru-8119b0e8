#!/usr/bin/env python3
"""
Mukthi Guru — Bulk Knowledge Ingestion (Hardened)

Scope: The Four Sacred Secrets + YouTube Playlists.
Strategy:
  1. PageIndex → Qdrant (specialized page-aware chunking, in-process)
  2. Chunked LightRAG → Neo4j (graph entity extraction in safe ~8K segments)
  3. YouTube → Qdrant + Neo4j (Whisper STT + graph)

Environment: Must be run from the project root:
  PYTHONUNBUFFERED=1 PYTHONPATH=backend .venv_host/bin/python3 scripts/ingestion/bulk_ingest_whisper.py 2>&1 | tee scripts/bulk_ingest.log

Resilience:
  - caffeinate -dims prevents sleep even on lid close (AC power)
  - State file tracks progress — safe to restart after crash
  - Retries with exponential backoff for YouTube rate limits
  - Graceful shutdown on SIGINT/SIGTERM saves state
"""

import argparse
import asyncio
import json
import logging
import os
import signal
import subprocess
import sys
import time

# ── Force unbuffered stdout for real-time logging ───────────
os.environ["PYTHONUNBUFFERED"] = "1"

# ── Setup Paths ─────────────────────────────────────────────
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
BACKEND_DIR = os.path.join(BASE_DIR, "backend")
sys.path.insert(0, BACKEND_DIR)

# ── Load env vars from .env (secrets stay out of source) ────
from dotenv import load_dotenv

# Load backend/.env for Sarvam API key and other config
load_dotenv(os.path.join(BACKEND_DIR, ".env"))

# Override infrastructure URLs for host-side execution (not Docker-internal)
os.environ["LLM_PROVIDER"] = "sarvam_cloud"
os.environ["QDRANT_URL"] = "http://localhost:6333"
os.environ["NEO4J_URI"] = "bolt://localhost:7687"
os.environ["NEO4J_USERNAME"] = "neo4j"
if "NEO4J_PASSWORD" not in os.environ:
    raise RuntimeError("NEO4J_PASSWORD env var is required")
os.environ["REDIS_URL"] = (
    f"redis://:{os.environ['REDIS_PASSWORD']}@localhost:6379/0"
)
os.environ["SUPABASE_URL"] = "http://localhost:54321"
os.environ["WHISPER_ONLY"] = "true"

# Ensure system tools and venv tools are in path
VENV_BIN = os.path.abspath(os.path.join(BASE_DIR, ".venv_host/bin"))
os.environ["PATH"] = f"{VENV_BIN}:/opt/homebrew/bin:/usr/local/bin:{os.environ['PATH']}"

log_format = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
log_file = os.path.join(BASE_DIR, "scripts/ingestion_status.log")

logging.basicConfig(
    level=logging.INFO,
    format=log_format,
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(log_file, mode="a", encoding="utf-8"),
    ],
)
logger = logging.getLogger("bulk_ingest")

STATE_FILE = os.path.join(BASE_DIR, "scripts/ingestion_state.json")

# ── Chunked LightRAG Insertion ──────────────────────────────
# Dynamically bind to config-driven RAG_CHUNK_SIZE, defaulting to a safe 2000 characters (instead of 8000)
# to prevent token overload and reasoning cutoff for Indian multilingual models.
LIGHTRAG_CHUNK_SIZE = int(os.environ.get("RAG_CHUNK_SIZE", 2000))
LIGHTRAG_CHUNK_OVERLAP = int(os.environ.get("RAG_CHUNK_OVERLAP", 200))
LIGHTRAG_SLEEP_BETWEEN = 3.0  # seconds between chunks (thermal throttling)


def chunk_text(
    text: str,
    chunk_size: int = LIGHTRAG_CHUNK_SIZE,
    overlap: int = LIGHTRAG_CHUNK_OVERLAP,
) -> list[str]:
    """Split text into overlapping chunks at sentence boundaries.

    FIXED: Previous version had a catastrophic 1-char sliding window bug.
    When sentence boundary search moved 'end' close to 'start', the fallback
    `start = max(start + 1, end - overlap)` would advance by only 1 character,
    generating 500+ near-duplicate chunks instead of ~54.
    """
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))

        # Try to break at sentence boundary (only if not at end of text)
        if end < len(text):
            for boundary_char in [". ", ".\n", "!\n", "?\n", "! ", "? "]:
                last_boundary = text.rfind(boundary_char, start + chunk_size // 2, end)
                if last_boundary != -1:
                    end = last_boundary + len(boundary_char)
                    break

        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)

        # Terminal condition: reached end of text
        if end >= len(text):
            break

        # Advance window — MUST make meaningful progress
        next_start = end - overlap
        if next_start <= start:
            # Overlap would cause stall/1-char slide — skip overlap entirely
            next_start = end
        start = next_start

    return chunks


async def safe_lightrag_insert(
    lightrag_service,
    full_text: str,
    source_name: str,
    state: dict | None = None,
    save_state_fn=None,
    video_id: str | None = None,
):
    """Insert text into LightRAG in safe, chunked segments with retry & exponential backoff.

    If a chunk fails after retries, it is persistently recorded in the state.
    """
    chunks = chunk_text(full_text)
    total = len(chunks)
    logger.info(
        f"LightRAG: Splitting {len(full_text):,} chars into {total} chunks (~{LIGHTRAG_CHUNK_SIZE} chars each)"
    )

    success_count = 0
    max_chunk_attempts = 3
    base_chunk_delay = 5.0  # seconds

    for i, chunk in enumerate(chunks, 1):
        logger.info(
            f"LightRAG: Inserting chunk {i}/{total} ({len(chunk):,} chars) for [{source_name}]"
        )
        chunk_with_header = f"[Source: {source_name}]\n{chunk}"

        success = False
        last_error = ""

        for attempt in range(1, max_chunk_attempts + 1):
            try:
                # Call LightRAG directly to raise exceptions on failures
                await lightrag_service.ainsert(
                    chunk_with_header, file_paths=[source_name], timeout=180.0
                )
                success = True
                break
            except Exception as e:
                last_error = str(e)
                logger.warning(
                    f"LightRAG: Chunk {i}/{total} Attempt {attempt}/{max_chunk_attempts} failed: {e}"
                )
                if attempt < max_chunk_attempts:
                    sleep_time = base_chunk_delay * (2 ** (attempt - 1))
                    logger.info(f"LightRAG: Retrying chunk {i}/{total} in {sleep_time:.1f}s...")
                    await asyncio.sleep(sleep_time)

        if success:
            success_count += 1
            logger.info(f"LightRAG: ✅ Chunk {i}/{total} done")
        else:
            logger.error(
                f"LightRAG: ❌ Chunk {i}/{total} completely failed after {max_chunk_attempts} attempts."
            )

            # Record failed chunk in state if provided
            if state is not None:
                if "failed_lightrag_chunks" not in state:
                    state["failed_lightrag_chunks"] = []

                # Check if this chunk is already tracked to avoid duplicates
                already_tracked = any(
                    c.get("source_name") == source_name and c.get("chunk_index") == i
                    for c in state["failed_lightrag_chunks"]
                )

                if not already_tracked:
                    failed_chunk_record = {
                        "source_name": source_name,
                        "video_id": video_id,
                        "chunk_index": i,
                        "total_chunks": total,
                        "chunk_content": chunk,
                        "error": last_error,
                        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                        "attempts": max_chunk_attempts,
                    }
                    state["failed_lightrag_chunks"].append(failed_chunk_record)
                    logger.info(f"LightRAG: Stored failed chunk {i}/{total} in state.")
                    if save_state_fn:
                        save_state_fn()

        if i < total:
            logger.info(f"LightRAG: Cooling down {LIGHTRAG_SLEEP_BETWEEN}s...")
            await asyncio.sleep(LIGHTRAG_SLEEP_BETWEEN)

    logger.info(
        f"LightRAG: ✅ {success_count}/{total} chunks processed successfully for [{source_name}]"
    )


# ── In-Process Book Ingestion (no subprocess spawn) ─────────
def ingest_book_to_qdrant(json_path: str):
    """
    Ingest The Four Sacred Secrets PageIndex structure into Qdrant.
    Runs IN-PROCESS to share the already-loaded embedding model,
    avoiding the 2GB model reload that caused the 6-hour hang.
    """
    import uuid

    from langchain_text_splitters import RecursiveCharacterTextSplitter
    from services.embedding_service import EmbeddingService
    from services.qdrant_service import QdrantService

    logger.info("Initializing Qdrant and Embeddings (in-process)...")
    qdrant = QdrantService()
    qdrant.init_collection()
    embeddings = EmbeddingService()

    logger.info(f"Loading PageIndex structure from {json_path}...")
    with open(json_path, encoding="utf-8") as f:
        data = json.load(f)

    structure = data.get("structure", [])
    if not structure:
        logger.error("No 'structure' array found in JSON.")
        return

    # Initialize child text splitter for parent-child hierarchical chunking
    child_splitter = RecursiveCharacterTextSplitter(
        chunk_size=400,
        chunk_overlap=50,
        length_function=len,
    )

    def flatten_tree(nodes, parent_title="", level=0, cluster_id=1):
        """Recursively flatten the PageIndex tree structure into chunk items."""
        chunks = []
        for node in nodes:
            title = node.get("title", "")
            if parent_title and title:
                context_title = f"{parent_title} > {title}"
            else:
                context_title = title or parent_title

            text = node.get("text", "").strip()
            summary = node.get("summary", "").strip()

            if text:
                parent_id = str(uuid.uuid4())
                child_paragraphs = child_splitter.split_text(text)
                header = f"[Source: The_Four_Sacred_Secrets.pdf | Chapter: {context_title}]\n"

                for child_index, child_text in enumerate(child_paragraphs):
                    chunks.append(
                        {
                            "text": header + child_text,
                            "metadata": {
                                "source_url": "The_Four_Sacred_Secrets.pdf",
                                "title": context_title,
                                "speaker": "Sri Preethaji & Sri Krishnaji",
                                "topic": "Spiritual",
                                "content_type": "book",
                                "raptor_level": 0,
                                "cluster_id": cluster_id,
                                "node_id": node.get("node_id", ""),
                                "page_range": f"{node.get('start_index', '?')}-{node.get('end_index', '?')}",
                                "parent_id": parent_id,
                                "parent_text": text,
                                "is_child": True,
                            },
                        }
                    )

            if summary:
                header = (
                    f"[Source: The_Four_Sacred_Secrets.pdf | Chapter Summary: {context_title}]\n"
                )
                chunks.append(
                    {
                        "text": header + summary,
                        "metadata": {
                            "source_url": "The_Four_Sacred_Secrets.pdf",
                            "title": f"Summary: {context_title}",
                            "speaker": "Sri Preethaji & Sri Krishnaji",
                            "topic": "Spiritual",
                            "content_type": "summary",
                            "raptor_level": 1,
                            "cluster_id": cluster_id,
                            "node_id": node.get("node_id", ""),
                        },
                    }
                )

            if "nodes" in node and node["nodes"]:
                children_chunks = flatten_tree(
                    node["nodes"],
                    parent_title=context_title,
                    level=level + 1,
                    cluster_id=cluster_id,
                )
                chunks.extend(children_chunks)

            cluster_id += 1
        return chunks

    logger.info("Flattening tree structure into ingestible chunks...")
    all_chunks = flatten_tree(structure)

    for i, chunk in enumerate(all_chunks):
        chunk["metadata"]["chunk_index"] = i

    total = len(all_chunks)
    logger.info(f"Extracted {total} total chunks (text and summaries).")

    # Upsert chunks in batches
    batch_size = 20
    for i in range(0, total, batch_size):
        batch = all_chunks[i : i + batch_size]
        texts = [item["text"] for item in batch]
        metadatas = [item["metadata"] for item in batch]

        encoded = embeddings.encode_batch(texts)
        dense_vectors = encoded["dense"]
        sparse_vectors = encoded["sparse"]

        qdrant.upsert_chunks(
            texts=texts,
            vectors=dense_vectors,
            metadatas=metadatas,
            sparse_vectors=sparse_vectors,
        )
        done = min(i + len(batch), total)
        logger.info(f"  Upserted {done} / {total} chunks...")
        sys.stdout.flush()

    logger.info(f"✅ Book ingestion complete: {total} chunks indexed in Qdrant")


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
    """Resolve playlist URL to video IDs via yt-dlp Python API (not CLI)."""
    try:
        import os

        import yt_dlp

        possible_paths = [
            os.path.join(os.getcwd(), "cookies.txt"),
            os.path.join(
                os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                "cookies.txt",
            ),
            "/Users/harshodaikolluru/Public/askmukthiguru-8119b0e8/cookies.txt",
        ]
        cookie_path = None
        for path in possible_paths:
            if os.path.exists(path):
                cookie_path = path
                break

        ydl_opts = {
            "quiet": True,
            "extract_flat": True,
            "no_warnings": True,
        }
        if cookie_path:
            ydl_opts["cookiefile"] = cookie_path
            logger.info(f"Using cookies from: {cookie_path}")
        else:
            ydl_opts["cookiesfrombrowser"] = ("chrome",)
            logger.info("Using Chrome cookies-from-browser fallback")

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            result = ydl.extract_info(playlist_url, download=False)
            if result and "entries" in result:
                ids = [e.get("id") for e in result["entries"] if e and e.get("id")]
                logger.info(f"Playlist resolved: {len(ids)} videos")
                return ids
        return []
    except Exception as e:
        logger.error(f"Playlist expansion failed: {e}")
        return []


async def fetch_transcript_text(video_id: str) -> str:
    """Fetch transcript text using the backend's hybrid loader (which triggers local Whisper if configured)."""
    try:
        from ingest.youtube_loader import fetch_transcript_hybrid

        # Run in executor because fetch_transcript_hybrid is sync and contains downloads/Whisper calls
        loop = asyncio.get_running_loop()
        res = await loop.run_in_executor(
            None, lambda: fetch_transcript_hybrid(video_id, max_accuracy=True)
        )
        if res and res.get("text"):
            return res["text"]
    except Exception as e:
        logger.error(f"fetch_transcript_hybrid failed for {video_id}: {e}")

    return ""


# ── Graceful Shutdown ───────────────────────────────────────
_shutdown_requested = False


def _signal_handler(signum, frame):
    global _shutdown_requested
    sig_name = signal.Signals(signum).name
    logger.warning(
        f"⚠️  Received {sig_name} — will finish current item and save state before exiting."
    )
    _shutdown_requested = True


def parse_args():
    parser = argparse.ArgumentParser(description="Mukthi Guru Bulk Ingestion")
    parser.add_argument(
        "--test-playlist",
        action="store_true",
        help="Test mode: process only the first playlist",
    )
    parser.add_argument(
        "--playlist-limit",
        type=int,
        default=0,
        help="Limit number of playlists to process (0=all)",
    )
    parser.add_argument(
        "--skip-lightrag",
        action="store_true",
        help="Skip LightRAG graph extraction (saves API calls)",
    )
    parser.add_argument(
        "--skip-book",
        action="store_true",
        help="Skip book ingestion, go straight to YouTube",
    )
    parser.add_argument(
        "--video-limit",
        type=int,
        default=0,
        help="Limit total videos to process (0=all)",
    )
    parser.add_argument(
        "--video-ids",
        type=str,
        default="",
        help="Comma-separated list of specific video IDs to ingest. If provided, playlist URLs are ignored.",
    )
    parser.add_argument(
        "--retry-failed-lightrag",
        action="store_true",
        help="Retry only the failed LightRAG chunks stored in state, then exit",
    )
    parser.add_argument(
        "--tags",
        type=str,
        default="general",
        help="Comma-separated knowledge tags for ingested content (default: general)",
    )
    return parser.parse_args()


def _parse_tags(raw: str) -> list[str]:
    """Normalize comma-separated tags to lowercase, deduplicated list."""
    tags = {t.strip().lower() for t in raw.split(",") if t.strip()}
    return sorted(tags) if tags else ["general"]


async def main():
    global _shutdown_requested
    args = parse_args()
    tags = _parse_tags(args.tags)

    # ── Signal Handlers for graceful shutdown ───────────────
    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)

    # ── macOS Sleep Prevention ──────────────────────────────
    # -d: prevent display sleep, -i: prevent idle sleep,
    # -m: prevent disk sleep, -s: prevent system sleep (AC power)
    # This combo survives lid close when plugged in.
    caffeinate_proc = None
    if sys.platform == "darwin":
        logger.info("macOS detected: Spawning 'caffeinate -dims' to prevent ALL sleep types...")
        try:
            caffeinate_proc = subprocess.Popen(["caffeinate", "-dims", "-w", str(os.getpid())])
            logger.info("✅ macOS caffeinate is active (-dims). Safe to close lid on AC power.")
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
        with open(STATE_FILE) as f:
            state = json.load(f)
    if "metrics" not in state:
        state["metrics"] = {}
    if "processed_videos" not in state:
        state["processed_videos"] = []
    if "processed_docs" not in state:
        state["processed_docs"] = []
    if "failed_lightrag_chunks" not in state:
        state["failed_lightrag_chunks"] = []

    def save_state():
        with open(STATE_FILE, "w") as f:
            json.dump(state, f, indent=2)

    # ── Handle Retry of Failed LightRAG Chunks Directly ───────
    if args.retry_failed_lightrag:
        failed_chunks = state.get("failed_lightrag_chunks", [])
        if not failed_chunks:
            logger.info("🎉 No failed LightRAG chunks stored in state. Nothing to retry!")
            return

        logger.info(f"🔄 Retrying {len(failed_chunks)} failed LightRAG chunk(s)...")
        # Copy to avoid mutation issues during iteration
        chunks_to_retry = list(failed_chunks)
        success_count = 0

        for idx, item in enumerate(chunks_to_retry, 1):
            source_name = item.get("source_name", "Unknown Source")
            chunk_content = item.get("chunk_content", "")
            chunk_idx = item.get("chunk_index", 0)
            total_chunks = item.get("total_chunks", 0)

            logger.info(
                f"[{idx}/{len(chunks_to_retry)}] Retrying chunk {chunk_idx}/{total_chunks} for [{source_name}]"
            )
            chunk_with_header = f"[Source: {source_name}]\n{chunk_content}"

            success = False
            max_attempts = 3
            base_delay = 5.0

            for attempt in range(1, max_attempts + 1):
                try:
                    await container.lightrag.ainsert(
                        chunk_with_header, file_paths=[source_name], timeout=180.0
                    )
                    success = True
                    break
                except Exception as e:
                    logger.warning(f"  Attempt {attempt}/{max_attempts} failed: {e}")
                    if attempt < max_attempts:
                        sleep_time = base_delay * (2 ** (attempt - 1))
                        await asyncio.sleep(sleep_time)

            if success:
                logger.info("  ✅ Chunk ingestion succeeded! Removing from failed queue.")
                success_count += 1
                state["failed_lightrag_chunks"] = [
                    c
                    for c in state["failed_lightrag_chunks"]
                    if not (
                        c.get("source_name") == source_name and c.get("chunk_index") == chunk_idx
                    )
                ]
                save_state()
            else:
                logger.error(f"  ❌ Chunk ingestion failed again after {max_attempts} attempts.")
                item["attempts"] = item.get("attempts", 3) + max_attempts
                item["timestamp"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                save_state()

            if idx < len(chunks_to_retry):
                logger.info(f"LightRAG: Cooling down {LIGHTRAG_SLEEP_BETWEEN}s...")
                await asyncio.sleep(LIGHTRAG_SLEEP_BETWEEN)

        logger.info(
            f"🎉 Failed LightRAG retry complete: {success_count} chunks successfully ingested. {len(state['failed_lightrag_chunks'])} remaining."
        )
        return

    # ── Ingest: The Four Sacred Secrets (Book) ──────────────
    doc_name = "The_Four_Sacred_Secrets.pdf"
    json_path = os.path.join(BASE_DIR, "results/The_Four_Sacred_Secrets_structure.json")

    if args.skip_book:
        logger.info("⏭️  --skip-book flag set, skipping book ingestion")
    elif doc_name in state["processed_docs"]:
        logger.info(f"⏭️  Skipping already processed document: {doc_name}")
    elif not os.path.exists(json_path):
        logger.error(f"❌ Structure JSON not found: {json_path}")
    else:
        logger.info(f"{'='*60}")
        logger.info(f"INGESTING: {doc_name}")
        logger.info(f"{'='*60}")
        start_time = time.time()

        try:
            # STEP 1: PageIndex → Qdrant (IN-PROCESS, shares loaded model)
            logger.info("Step 1/2: PageIndex → Qdrant (in-process page-aware vector ingestion)...")
            ingest_book_to_qdrant(json_path)
            logger.info("Step 1/2: ✅ PageIndex → Qdrant complete")

            # STEP 2: Chunked LightRAG → Neo4j (graph entity extraction)
            if args.skip_lightrag:
                logger.info("Step 2/2: ⏭️  --skip-lightrag flag set, skipping graph extraction")
            elif container.lightrag:
                logger.info("Step 2/2: LightRAG → Neo4j (chunked graph extraction)...")
                with open(json_path) as f:
                    data = json.load(f)

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
                    await safe_lightrag_insert(
                        lightrag_service=container.lightrag,
                        full_text=full_text,
                        source_name=doc_name,
                        state=state,
                        save_state_fn=save_state,
                        video_id=None,
                    )
                    logger.info("Step 2/2: ✅ LightRAG → Neo4j complete")
                else:
                    logger.warning("No text extracted from structure JSON")
            else:
                logger.warning("LightRAG not available — skipping graph extraction")

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

    if _shutdown_requested:
        logger.info("🛑 Shutdown requested after book ingestion. State saved.")
        return

    # ── Ingest: YouTube Playlists & Videos (Dual Ingestion) ──
    logger.info(f"\n{'='*60}")
    logger.info("RESOLVING YOUTUBE PLAYLISTS & VIDEO IDS")
    logger.info(f"{'='*60}")

    if args.video_ids:
        # User explicitly passed video ids
        unique_ids = [vid.strip() for vid in args.video_ids.split(",") if vid.strip()]
        logger.info(f"Targeting {len(unique_ids)} explicit video IDs: {unique_ids}")
    else:
        playlists_to_process = PLAYLIST_URLS
        if args.test_playlist:
            playlists_to_process = PLAYLIST_URLS[:1]
            logger.info("🧪 TEST MODE: Processing only first playlist")
        elif args.playlist_limit > 0:
            playlists_to_process = PLAYLIST_URLS[: args.playlist_limit]
            logger.info(
                f"🔢 Processing {len(playlists_to_process)} of {len(PLAYLIST_URLS)} playlists"
            )

        all_ids = []
        for pl in playlists_to_process:
            if _shutdown_requested:
                break
            logger.info(f"Resolving playlist: {pl}")
            all_ids.extend(get_video_ids_from_playlist(pl))
            time.sleep(1)

        if not args.test_playlist:
            all_ids += CORE_VIDEO_IDS

        seen = set()
        unique_ids = [v for v in all_ids if not (v in seen or seen.add(v))]

        # Prioritize previously failed videos by moving them to the beginning of the queue
        failed_ids = [
            vid
            for vid, metric in state.get("metrics", {}).items()
            if isinstance(metric, dict)
            and metric.get("status") == "failed"
            and vid not in state["processed_videos"]
        ]
        if failed_ids:
            logger.info(
                f"🔄 Found {len(failed_ids)} previously failed videos. Prioritizing them at the beginning of the queue: {failed_ids}"
            )
            unique_ids = failed_ids + [v for v in unique_ids if v not in failed_ids]

    if args.video_limit > 0:
        unique_ids = unique_ids[: args.video_limit]
        logger.info(f"🔢 Video limit: processing {len(unique_ids)} videos")

    logger.info(f"🎯 Total unique videos queued: {len(unique_ids)}")

    for vid in unique_ids:
        if _shutdown_requested:
            logger.info("🛑 Shutdown requested. Saving state...")
            save_state()
            break

        if vid in state["processed_videos"]:
            logger.info(f"⏭️  Skipping already processed video: {vid}")
            continue

        url = f"https://www.youtube.com/watch?v={vid}"
        logger.info(f"\n{'='*60}\n[Video Ingestion] {vid}\n{'='*60}")

        max_attempts = 3
        retry_delay = 15  # base retry delay in seconds
        success = False

        for attempt in range(1, max_attempts + 1):
            if _shutdown_requested:
                break

            start_video_time = time.time()
            try:
                # STEP 1: Qdrant (dense+sparse vectors via hybrid pipeline)
                logger.info(
                    f"[Qdrant] Ingesting video: {url} (Attempt {attempt}/{max_attempts})..."
                )
                logger.info(f"[Tags] {tags}")
                res = await pipeline.ingest_url(url, max_accuracy=True, tags=tags)

                # Check status return to throw error and trigger the retry delays
                if res.get("status") == "error":
                    raise ValueError(res.get("message", "Ingestion pipeline returned error status"))

                chunks = res.get("chunks_indexed", 0)
                title = res.get("title") or res.get("metadata", {}).get("title") or "Unknown"
                logger.info(f"[Qdrant] ✅ Success | Title: {title} | Chunks: {chunks}")

                # STEP 2: LightRAG/Neo4j (knowledge graph via safe chunked insertion)
                if args.skip_lightrag:
                    pass  # Silently skip — already logged at startup
                elif container.lightrag:
                    # Reuse transcript already fetched in Step 1 to avoid a second
                    # Whisper run (which would waste 15-30 min per video).
                    text = res.get("text") or res.get("transcript") or ""
                    if not text.strip():
                        logger.info(
                            f"[LightRAG] No text in Qdrant result — re-fetching transcript for video: {vid}..."
                        )
                        text = await fetch_transcript_text(vid)
                    else:
                        logger.info(
                            f"[LightRAG] Reusing transcript from Qdrant step ({len(text):,} chars) — skipping second Whisper run"
                        )
                    if text.strip():
                        logger.info(
                            "[LightRAG] Correcting spelling and domain terminology in transcript..."
                        )
                        sanitized_text = text.replace("<|begin_of_text|>", "").replace(
                            "<|eot_id|>", ""
                        )
                        corrected_text = await pipeline._corrector.correct_transcript(
                            sanitized_text, url
                        )
                        source_name = f"YouTube Video: {title} (URL: {url})"
                        await safe_lightrag_insert(
                            lightrag_service=container.lightrag,
                            full_text=corrected_text,
                            source_name=source_name,
                            state=state,
                            save_state_fn=save_state,
                            video_id=vid,
                        )
                        logger.info("[LightRAG] ✅ Success")
                    else:
                        logger.warning("[LightRAG] ⚠️ No transcript content retrieved")
                else:
                    logger.warning("[LightRAG] Service not active — skipping")

                latency = time.time() - start_video_time
                state["processed_videos"].append(vid)
                state["metrics"][vid] = {
                    "latency": latency,
                    "status": "success",
                    "title": title,
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
                    logger.error(
                        f"❌ Video Failed after {max_attempts} attempts: {vid} | {e}",
                        exc_info=True,
                    )

        if not _shutdown_requested and vid != unique_ids[-1]:
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
        title = m.get("title", "Unknown")
        logger.info(
            f"  🎥 {vid} ({title}) — {m.get('status', 'unknown')} ({m.get('latency', 0):.1f}s)"
        )

    failed = [k for k, v in state["metrics"].items() if v.get("status") == "failed"]
    if failed:
        logger.warning(f"\n⚠️  {len(failed)} items failed. Re-run this script to retry them.")

    logger.info(f"{'='*60}")


if __name__ == "__main__":
    asyncio.run(main())
