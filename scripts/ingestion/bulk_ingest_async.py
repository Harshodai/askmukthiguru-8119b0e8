#!/usr/bin/env python3
"""
Mukthi Guru — Bounded Concurrent Knowledge Ingestion (Async)

Scope: The Four Sacred Secrets + YouTube Playlists.
Concurrency Architecture:
  - asyncio.Semaphore(N) bounds parallel workers.
  - Keeps Neo4j transactions isolated to avoid lock-wait timeouts/deadlocks.
  - Prevents local MPS (Apple Silicon GPU) VRAM thrashing.
  - Shares the same state file (scripts/ingestion_state.json) to resume seamlessly.
  - Strictly obeys the 60 RPM Sarvam Cloud API rate limit via the backend's
    built-in asyncio.Lock inside SarvamCloudService.

Hardening Features (SDLC):
  - CircuitBreaker: pauses ingestion after N consecutive failures to prevent
    API credit burn during infrastructure outages.
  - Dead Letter Queue (DLQ): categorizes errors as transient/permanent/partial
    and stores them for targeted retry.
  - ETA Reporting: rolling average latency with estimated time remaining.
  - Dual-DB Status: tracks qdrant_status and lightrag_status independently.
  - Atomic State Writes: tempfile + rename to prevent JSON corruption.
  - Jitter Backoff: randomized delay to prevent thundering herd.

Run command:
  PYTHONUNBUFFERED=1 PYTHONPATH=backend .venv_host/bin/python3 scripts/ingestion/bulk_ingest_async.py 2>&1 | tee scripts/bulk_ingest_async.log
"""

import argparse
import asyncio
import enum
import json
import logging
import os
import random
import signal
import subprocess
import sys
import tempfile
import time
from collections import deque

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
os.environ["NEO4J_PASSWORD"] = os.environ.get("NEO4J_PASSWORD", "mukthiguru_neo4j_pass")
os.environ["REDIS_URL"] = (
    f"redis://:{os.environ.get('REDIS_PASSWORD', 'mukthiguru_redis_pass')}@localhost:6379/0"
)
os.environ["SUPABASE_URL"] = "http://localhost:54321"
os.environ["WHISPER_ONLY"] = "true"

# Ensure system tools and venv tools are in path
VENV_BIN = os.path.abspath(os.path.join(BASE_DIR, ".venv_host/bin"))
os.environ["PATH"] = f"{VENV_BIN}:/opt/homebrew/bin:/usr/local/bin:{os.environ['PATH']}"

log_format = "%(asctime)s [%(levelname)s] [%(threadName)s] %(name)s: %(message)s"
log_file = os.path.join(BASE_DIR, "scripts/ingestion_status_async.log")

logging.basicConfig(
    level=logging.INFO,
    format=log_format,
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(log_file, mode="a", encoding="utf-8"),
    ],
)
logger = logging.getLogger("bulk_ingest_async")

STATE_FILE = os.path.join(BASE_DIR, "scripts/ingestion_state.json")

SUMMARY_FILE = os.path.join(BASE_DIR, "scripts/ingestion_summary.json")

# ── Chunked LightRAG Insertion ──────────────────────────────
# Chunk size for LightRAG: smaller chunks = more API calls but safer per-call.
# 1500 chars balances sarvam-m's context window (2048 tokens ≈ 8K chars input + 2K output)
# with minimizing total API calls. Each chunk triggers 2-4 Sarvam API calls internally.
LIGHTRAG_CHUNK_SIZE = int(os.environ.get("RAG_CHUNK_SIZE", 1500))
LIGHTRAG_CHUNK_OVERLAP = int(os.environ.get("RAG_CHUNK_OVERLAP", 150))
LIGHTRAG_SLEEP_BETWEEN = 2.0  # seconds between chunks


# ── Circuit Breaker ─────────────────────────────────────────
class CBState(enum.Enum):
    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Failing — pausing requests
    HALF_OPEN = "half_open"  # Testing recovery


class CircuitBreaker:
    """
    Simple circuit breaker to prevent API credit burn during infrastructure outages.
    After `failure_threshold` consecutive failures, enters OPEN state and pauses
    for `cooldown_seconds`. After cooldown, enters HALF_OPEN and allows one probe.
    """

    def __init__(self, failure_threshold: int = 5, cooldown_seconds: float = 120.0):
        self.state = CBState.CLOSED
        self.failure_threshold = failure_threshold
        self.cooldown_seconds = cooldown_seconds
        self._consecutive_failures = 0
        self._opened_at: float = 0.0

    def record_success(self):
        self._consecutive_failures = 0
        self.state = CBState.CLOSED

    def record_failure(self):
        self._consecutive_failures += 1
        if self._consecutive_failures >= self.failure_threshold:
            if self.state != CBState.OPEN:
                logger.warning(
                    f"🔴 CircuitBreaker OPENED after {self._consecutive_failures} consecutive failures. "
                    f"Cooling down for {self.cooldown_seconds:.0f}s..."
                )
            self.state = CBState.OPEN
            self._opened_at = time.time()

    async def wait_if_open(self):
        """Block until circuit recovers. Logs remaining wait time."""
        while self.state == CBState.OPEN:
            elapsed = time.time() - self._opened_at
            remaining = self.cooldown_seconds - elapsed
            if remaining <= 0:
                logger.info("🟡 CircuitBreaker entering HALF_OPEN — probing next request...")
                self.state = CBState.HALF_OPEN
                break
            logger.warning(
                f"⏸️  CircuitBreaker OPEN — waiting {remaining:.0f}s before next attempt..."
            )
            await asyncio.sleep(min(remaining, 30.0))

    @property
    def is_healthy(self) -> bool:
        return self.state == CBState.CLOSED


# Shared circuit breaker instance
_circuit_breaker = CircuitBreaker(failure_threshold=5, cooldown_seconds=120.0)


# ── ETA / Progress Tracker ──────────────────────────────────
class ProgressTracker:
    """Tracks rolling average latency and projects ETA."""

    def __init__(self, total: int, window: int = 10):
        self.total = total
        self.done = 0
        self.failed = 0
        self._latencies: deque = deque(maxlen=window)
        self._run_start = time.time()

    def record(self, latency: float, success: bool):
        self.done += 1
        if not success:
            self.failed += 1
        self._latencies.append(latency)

    def eta_str(self) -> str:
        remaining = self.total - self.done
        if not self._latencies or remaining <= 0:
            return "—"
        avg = sum(self._latencies) / len(self._latencies)
        eta_sec = avg * remaining
        h, rem = divmod(int(eta_sec), 3600)
        m, s = divmod(rem, 60)
        return f"{h}h {m}m {s}s"

    def summary_line(self) -> str:
        elapsed = time.time() - self._run_start
        avg = sum(self._latencies) / len(self._latencies) if self._latencies else 0
        return (
            f"Progress: {self.done}/{self.total} | "
            f"Failed: {self.failed} | "
            f"Avg: {avg:.0f}s/video | "
            f"ETA: {self.eta_str()} | "
            f"Elapsed: {elapsed/3600:.1f}h"
        )


# Shared progress tracker (initialized in main)
_progress: ProgressTracker | None = None


# ── Error Categorization ─────────────────────────────────────
def classify_error(error: Exception) -> str:
    """
    Classify error as: 'permanent' | 'transient' | 'partial'
    permanent  → no transcript, video deleted/private — do not retry
    transient  → network, rate limits, timeouts — safe to retry
    partial    → Qdrant ok, LightRAG failed — tracked separately
    """
    msg = str(error).lower()
    permanent_signals = [
        "extraction failed",
        "no transcript",
        "private video",
        "video unavailable",
        "has been removed",
        "does not exist",
        "sign in to confirm",
    ]
    for sig in permanent_signals:
        if sig in msg:
            return "permanent"
    return "transient"


def chunk_text(
    text: str,
    chunk_size: int = LIGHTRAG_CHUNK_SIZE,
    overlap: int = LIGHTRAG_CHUNK_OVERLAP,
) -> list[str]:
    """Split text into overlapping chunks at sentence boundaries."""
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
        global _shutdown_requested
        if _shutdown_requested:
            logger.warning(
                f"LightRAG: Shutdown requested. Aborting remaining {total - i + 1} chunks for [{source_name}]"
            )
            raise Exception("Shutdown requested during LightRAG insertion")

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


# ── Book Ingestion (In-Process) ─────────────────────────────
def ingest_book_to_qdrant(json_path: str):
    """Ingest book structure into Qdrant in-process."""
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

    child_splitter = RecursiveCharacterTextSplitter(
        chunk_size=400,
        chunk_overlap=50,
        length_function=len,
    )

    def flatten_tree(nodes, parent_title="", level=0, cluster_id=1):
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


# ── YouTube Playlists Configuration ─────────────────────────
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
    "69IrsSXeBTg",
    "igSp4H0OWLE",
    "TqxxCYnAxo8",
    "O-6f5wQXSu8",
]


def get_video_ids_from_playlist(playlist_url: str) -> list[str]:
    """Resolve playlist URL to video IDs via yt-dlp Python API."""
    try:
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
    """Fetch transcript text using backend's hybrid loader (which checks pre-extracted first)."""
    try:
        from ingest.youtube_loader import fetch_transcript_hybrid

        loop = asyncio.get_running_loop()
        res = await loop.run_in_executor(
            None, lambda: fetch_transcript_hybrid(video_id, max_accuracy=True)
        )
        if res and res.get("text"):
            return res["text"]
    except Exception as e:
        logger.error(f"fetch_transcript_hybrid failed for {video_id}: {e}")

    return ""


# ── State and Cancellation ──────────────────────────────────
_shutdown_requested = False


def _signal_handler(signum, frame):
    global _shutdown_requested
    sig_name = signal.Signals(signum).name
    logger.warning(
        f"⚠️ Received {sig_name} — will save state and shutdown gracefully once current items conclude."
    )
    _shutdown_requested = True


def _atomic_save_state(state: dict, path: str):
    """Write state atomically via tempfile+rename to prevent JSON corruption on crash."""
    dir_ = os.path.dirname(path)
    try:
        with tempfile.NamedTemporaryFile(
            "w", dir=dir_, suffix=".tmp", delete=False, encoding="utf-8"
        ) as tf:
            json.dump(state, tf, indent=2)
            tf_name = tf.name
        os.replace(tf_name, path)  # atomic on POSIX
    except Exception as e:
        logger.error(f"Atomic state write failed: {e}")
        # fallback
        with open(path, "w") as f:
            json.dump(state, f, indent=2)


def _jitter_sleep(base_seconds: float, max_jitter_pct: float = 0.25) -> float:
    """Returns base_seconds + random jitter (up to max_jitter_pct of base)."""
    jitter = random.uniform(0, base_seconds * max_jitter_pct)
    return min(base_seconds + jitter, 120.0)  # cap at 120s


# ── Concurrent Worker ───────────────────────────────────────
async def process_video_worker(
    vid: str,
    sem: asyncio.Semaphore,
    pipeline,
    container,
    state: dict,
    save_state_fn,
    args,
    worker_num: int = 0,
):
    """Processes a single video under concurrency bounds.

    Architecture:
      - Qdrant vector ingestion = CRITICAL (must succeed for video to be marked processed)
      - LightRAG graph extraction = BEST-EFFORT (failures are logged but don't block)
      - CircuitBreaker: pauses all workers if consecutive failures detected
      - DLQ: failed videos are categorized and stored for targeted retry
    """
    global _shutdown_requested, _progress
    if _shutdown_requested:
        return

    url = f"https://www.youtube.com/watch?v={vid}"

    async with sem:
        if _shutdown_requested:
            return

        # Wait for circuit breaker to recover before consuming semaphore slot
        await _circuit_breaker.wait_if_open()
        if _shutdown_requested:
            return

        logger.info(f"[Worker-{worker_num}] Starting: {vid}...")
        start_video_time = time.time()

        # Check if Qdrant already succeeded for this video (LightRAG backfill only)
        qdrant_already_success = False
        vid_metrics = state.get("metrics", {}).get(vid, {})
        if isinstance(vid_metrics, dict) and vid_metrics.get("qdrant_status") == "success":
            qdrant_already_success = True

        if qdrant_already_success:
            logger.info(
                f"[Worker-{worker_num}] Qdrant already success for {vid}. Bypassing Step 1 (Qdrant) and doing LightRAG backfill."
            )
            title = vid_metrics.get("title") or "Unknown"
            chunks = vid_metrics.get("chunks") or 0

            lightrag_status = "skipped"
            if args.skip_lightrag:
                lightrag_status = "skipped"
            elif container.lightrag:
                try:
                    logger.info(f"[LightRAG] Fetching transcript for backfill: {vid}...")
                    text = await fetch_transcript_text(vid)
                    if text.strip():
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
                            save_state_fn=save_state_fn,
                            video_id=vid,
                        )
                        lightrag_status = "success"
                        logger.info(f"[LightRAG] ✅ {vid} (backfill)")
                    else:
                        lightrag_status = "no_transcript"
                        logger.warning(f"[LightRAG] ⚠️ No transcript for {vid}")
                except Exception as lg_err:
                    lightrag_status = "failed"
                    logger.error(f"[LightRAG] ❌ Failed (non-fatal backfill): {lg_err}")
            else:
                lightrag_status = "service_inactive"

            # Final metrics update
            total_latency = time.time() - start_video_time
            state["metrics"][vid]["latency"] = total_latency
            state["metrics"][vid]["lightrag_status"] = lightrag_status

            # Remove from DLQ if it was in there
            if "dead_letter_queue" in state:
                state["dead_letter_queue"] = [
                    d for d in state["dead_letter_queue"] if d.get("video_id") != vid
                ]

            # Ensure it is in processed_videos
            if vid not in state["processed_videos"]:
                state["processed_videos"].append(vid)

            save_state_fn()
            _circuit_breaker.record_success()
            if _progress:
                _progress.record(total_latency, success=True)
                logger.info(
                    f"✅ {vid} ({title}) backfilled in {total_latency:.1f}s | "
                    f"{_progress.summary_line()}"
                )
            return

        max_attempts = 3
        base_retry_delay = 15.0
        last_error: Exception | None = None

        for attempt in range(1, max_attempts + 1):
            if _shutdown_requested:
                break

            try:
                # ── STEP 1: Qdrant (CRITICAL) ──
                logger.info(f"[Qdrant] {vid} (Attempt {attempt}/{max_attempts})...")
                res = await pipeline.ingest_url(url, max_accuracy=True)

                if res.get("status") == "error":
                    raise ValueError(res.get("message", "Ingestion pipeline returned error status"))

                chunks = res.get("chunks_indexed", 0)
                title = res.get("title") or res.get("metadata", {}).get("title") or "Unknown"
                logger.info(f"[Qdrant] ✅ {vid} | Title: {title} | Chunks: {chunks}")

                # MARK VIDEO AS PROCESSED immediately after Qdrant success
                qdrant_latency = time.time() - start_video_time
                if vid not in state["processed_videos"]:
                    state["processed_videos"].append(vid)
                state["metrics"][vid] = {
                    "latency": qdrant_latency,
                    "status": "success",
                    "qdrant_status": "success",
                    "title": title,
                    "chunks": chunks,
                    "lightrag_status": "pending",
                }
                save_state_fn()

                # ── STEP 2: LightRAG/Neo4j (BEST-EFFORT) ──
                lightrag_status = "skipped"
                if args.skip_lightrag:
                    lightrag_status = "skipped"
                elif container.lightrag:
                    try:
                        text = res.get("text") or res.get("transcript") or ""
                        if not text.strip():
                            logger.info(f"[LightRAG] Re-fetching transcript for {vid}...")
                            text = await fetch_transcript_text(vid)
                        else:
                            logger.info(f"[LightRAG] Reusing transcript ({len(text):,} chars)")

                        if text.strip():
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
                                save_state_fn=save_state_fn,
                                video_id=vid,
                            )
                            lightrag_status = "success"
                            logger.info(f"[LightRAG] ✅ {vid}")
                        else:
                            lightrag_status = "no_transcript"
                            logger.warning(f"[LightRAG] ⚠️ No transcript for {vid}")
                    except Exception as lg_err:
                        lightrag_status = "failed"
                        logger.error(f"[LightRAG] ❌ Failed (non-fatal): {lg_err}")
                else:
                    lightrag_status = "service_inactive"

                # Final metrics update
                total_latency = time.time() - start_video_time
                state["metrics"][vid]["latency"] = total_latency
                state["metrics"][vid]["lightrag_status"] = lightrag_status

                # Remove from DLQ if it was in there
                if "dead_letter_queue" in state:
                    state["dead_letter_queue"] = [
                        d for d in state["dead_letter_queue"] if d.get("video_id") != vid
                    ]

                save_state_fn()

                _circuit_breaker.record_success()
                if _progress:
                    _progress.record(total_latency, success=True)
                    logger.info(
                        f"✅ {vid} ({title}) done in {total_latency:.1f}s [lightrag={lightrag_status}] | "
                        f"{_progress.summary_line()}"
                    )
                    # Periodic summary every 10 completions
                    if _progress.done % 10 == 0:
                        logger.info(f"{'='*60}")
                        logger.info(f"📊 PERIODIC SUMMARY: {_progress.summary_line()}")
                        logger.info(f"{'='*60}")
                else:
                    logger.info(f"✅ {vid} ({title}) done in {total_latency:.1f}s")
                break  # Success

            except Exception as e:
                last_error = e
                latency = time.time() - start_video_time
                logger.warning(f"⚠️ Attempt {attempt}/{max_attempts} failed for {vid}: {e}")
                if attempt < max_attempts:
                    sleep_time = _jitter_sleep(base_retry_delay * attempt)
                    logger.info(f"  Retrying in {sleep_time:.1f}s (jittered)...")
                    await asyncio.sleep(sleep_time)
                else:
                    # All attempts exhausted — classify and record in DLQ
                    error_category = classify_error(e)
                    state["metrics"][vid] = {
                        "latency": latency,
                        "status": "failed",
                        "qdrant_status": "failed",
                        "lightrag_status": "skipped",
                        "error": str(e),
                        "error_category": error_category,
                    }
                    # DLQ entry
                    if "dead_letter_queue" not in state:
                        state["dead_letter_queue"] = []
                    # Remove old entry for this vid if exists
                    state["dead_letter_queue"] = [
                        d for d in state["dead_letter_queue"] if d.get("video_id") != vid
                    ]
                    state["dead_letter_queue"].append(
                        {
                            "video_id": vid,
                            "error_category": error_category,
                            "error_message": str(e),
                            "attempt_count": max_attempts,
                            "last_attempt_ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                            "will_retry": error_category == "transient",
                        }
                    )
                    save_state_fn()
                    _circuit_breaker.record_failure()
                    if _progress:
                        _progress.record(latency, success=False)
                    logger.error(
                        f"❌ {vid} failed [{error_category}] after {max_attempts} attempts: {e}"
                    )


def parse_args():
    parser = argparse.ArgumentParser(description="Mukthi Guru Bounded Concurrent Ingestion")
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
        "--concurrency",
        type=int,
        default=2,
        help="Number of concurrent worker tasks (default: 2)",
    )
    parser.add_argument(
        "--video-ids",
        type=str,
        default="",
        help="Comma-separated list of specific video IDs to process (bypasses playlist resolution)",
    )
    parser.add_argument(
        "--retry-failed-lightrag",
        action="store_true",
        help="Retry only the failed LightRAG chunks stored in state, then exit",
    )
    # New hardening flags
    parser.add_argument(
        "--retry-dlq",
        action="store_true",
        help="Retry only transient-error videos from the Dead Letter Queue, then exit",
    )
    parser.add_argument(
        "--retry-lightrag-missing",
        action="store_true",
        help="Backfill LightRAG for videos with qdrant_status=success but lightrag_status unknown/failed",
    )
    parser.add_argument(
        "--clean-state",
        action="store_true",
        help="Remove permanently-failed videos from DLQ and metrics, then exit",
    )
    return parser.parse_args()


async def main():
    global _shutdown_requested, _progress
    args = parse_args()

    # ── Signal Handlers for graceful shutdown ───────────────
    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)

    # ── macOS Sleep Prevention ──────────────────────────────
    caffeinate_proc = None
    if sys.platform == "darwin":
        logger.info("macOS detected: Spawning 'caffeinate -dims' to prevent sleep...")
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
    state = {
        "processed_videos": [],
        "processed_docs": [],
        "metrics": {},
        "failed_lightrag_chunks": [],
        "dead_letter_queue": [],
    }
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            state = json.load(f)
    # Ensure all keys exist
    for k, default in [
        ("metrics", {}),
        ("processed_videos", []),
        ("processed_docs", []),
        ("failed_lightrag_chunks", []),
        ("dead_letter_queue", []),
    ]:
        if k not in state:
            state[k] = default

    def save_state():
        _atomic_save_state(state, STATE_FILE)

    # ── Pre-flight Health Checks ─────────────────────────────
    # Verify critical infrastructure is reachable before processing any videos.
    # Fail fast here instead of burning 300+ API calls with identical errors.
    _preflight_ok = True

    # 1. Qdrant health check
    try:
        import urllib.request

        with urllib.request.urlopen("http://localhost:6333/healthz", timeout=5) as resp:
            if resp.status == 200:
                logger.info("✅ Pre-flight: Qdrant is healthy (localhost:6333)")
            else:
                logger.error(f"❌ Pre-flight: Qdrant returned HTTP {resp.status}")
                _preflight_ok = False
    except Exception as e:
        logger.error(f"❌ Pre-flight: Qdrant unreachable — {e}")
        _preflight_ok = False

    # 2. Neo4j bolt health check (lightweight ping, no auth needed for reachability)
    try:
        import socket

        with socket.create_connection(("localhost", 7687), timeout=5):
            logger.info("✅ Pre-flight: Neo4j bolt port is open (localhost:7687)")
    except Exception as e:
        logger.warning(
            f"⚠️  Pre-flight: Neo4j bolt unreachable — {e}. "
            f"LightRAG graph extraction will be degraded/skipped."
        )
        # Not fatal — LightRAG gracefully degrades; Qdrant ingestion can still proceed.

    if not _preflight_ok:
        logger.error("❌ Pre-flight failed. Fix infrastructure issues before running ingestion.")
        logger.error("   Qdrant: docker ps | grep qdrant — ensure container is running")
        return

    if args.clean_state:
        before = len(state["dead_letter_queue"])
        state["dead_letter_queue"] = [
            d for d in state["dead_letter_queue"] if d.get("error_category") != "permanent"
        ]
        perm_failed = [
            k
            for k, v in state["metrics"].items()
            if isinstance(v, dict) and v.get("error_category") == "permanent"
        ]
        for vid in perm_failed:
            state["metrics"][vid]["will_retry"] = False
        save_state()
        logger.info(
            f"🧹 clean-state: removed {before - len(state['dead_letter_queue'])} permanent DLQ entries. "
            f"Marked {len(perm_failed)} metrics as will_retry=False."
        )
        return

    # ── Handle --retry-dlq (retry only transient DLQ entries) ──
    if args.retry_dlq:
        transient_dlq = [
            d
            for d in state.get("dead_letter_queue", [])
            if d.get("will_retry", True) and d.get("error_category") != "permanent"
        ]
        if not transient_dlq:
            logger.info("🎉 No transient DLQ entries to retry.")
            return
        logger.info(f"🔄 DLQ retry: {len(transient_dlq)} transient video(s)...")
        args.video_ids = ",".join(d["video_id"] for d in transient_dlq)
        # Remove them from metrics so they're queued again
        for d in transient_dlq:
            vid = d["video_id"]
            state["metrics"].pop(vid, None)
            if vid in state["processed_videos"]:
                state["processed_videos"].remove(vid)
        save_state()
        # Fall through to normal ingestion with the DLQ IDs set as video_ids

    # ── Handle --retry-lightrag-missing (backfill KG for Qdrant-only videos) ──
    if args.retry_lightrag_missing:
        needs_kg = [
            vid
            for vid, m in state["metrics"].items()
            if isinstance(m, dict)
            and m.get("qdrant_status") == "success"
            and m.get("lightrag_status", "unknown") in ("unknown", "failed", "skipped", "pending")
        ]
        if not needs_kg:
            logger.info("🎉 All videos with Qdrant success already have LightRAG status tracked.")
            return
        logger.info(f"🔄 LightRAG backfill: {len(needs_kg)} video(s) need KG ingestion...")
        args.video_ids = ",".join(needs_kg)
        # CRITICAL: Must remove from processed_videos so they pass the queue filter.
        # Without this, line 1041 silently drops all of them and nothing gets re-queued.
        # Keeping metrics intact — Qdrant upsert is idempotent if the worker re-runs it.
        for vid in needs_kg:
            if vid in state["processed_videos"]:
                state["processed_videos"].remove(vid)
        save_state()
        logger.info(
            f"  Removed {len(needs_kg)} video(s) from processed_videos for KG backfill queue."
        )
        # Fall through to normal ingestion

    # ── Handle Retry of Failed LightRAG Chunks Directly ───────
    if args.retry_failed_lightrag:
        failed_chunks = state.get("failed_lightrag_chunks", [])
        if not failed_chunks:
            logger.info("🎉 No failed LightRAG chunks stored in state. Nothing to retry!")
            return

        logger.info(f"🔄 Retrying {len(failed_chunks)} failed LightRAG chunk(s)...")
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
                        sleep_time = _jitter_sleep(base_delay * (2 ** (attempt - 1)))
                        await asyncio.sleep(sleep_time)

            if success:
                logger.info("  ✅ Chunk recovered! Removing from failed queue.")
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
                logger.error(f"  ❌ Chunk still failing after {max_attempts} attempts.")
                item["attempts"] = item.get("attempts", 3) + max_attempts
                item["timestamp"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                save_state()

            if idx < len(chunks_to_retry):
                await asyncio.sleep(LIGHTRAG_SLEEP_BETWEEN)

        logger.info(
            f"🎉 LightRAG retry: {success_count}/{len(chunks_to_retry)} chunks recovered. "
            f"{len(state['failed_lightrag_chunks'])} remaining."
        )
        return

    # ── Ingest Book (Sequential) ────────────────────────────
    doc_name = "The_Four_Sacred_Secrets.pdf"
    json_path = os.path.join(BASE_DIR, "results/The_Four_Sacred_Secrets_structure.json")

    if args.skip_book:
        logger.info("⏭️ --skip-book flag set, skipping book ingestion")
    elif doc_name in state["processed_docs"]:
        logger.info(f"⏭️ Skipping already processed document: {doc_name}")
    elif not os.path.exists(json_path):
        logger.error(f"❌ Structure JSON not found: {json_path}")
    else:
        logger.info(f"{'='*60}")
        logger.info(f"INGESTING BOOK: {doc_name}")
        logger.info(f"{'='*60}")
        start_time = time.time()

        try:
            logger.info("Step 1/2: PageIndex → Qdrant (in-process)...")
            ingest_book_to_qdrant(json_path)
            logger.info("Step 1/2: ✅ Qdrant done")

            if args.skip_lightrag:
                logger.info("Step 2/2: ⏭️ Skipping LightRAG")
            elif container.lightrag:
                logger.info("Step 2/2: LightRAG → Neo4j...")
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
                    logger.info("Step 2/2: ✅ LightRAG done")
            else:
                logger.warning("LightRAG not active")

            latency = time.time() - start_time
            state["processed_docs"].append(doc_name)
            state["metrics"][doc_name] = {
                "latency": latency,
                "status": "success",
            }
            save_state()
            logger.info(f"✅ Book Ingested in {latency:.1f}s")
        except Exception as e:
            latency = time.time() - start_time
            state["metrics"][doc_name] = {
                "latency": latency,
                "status": "failed",
                "error": str(e),
            }
            save_state()
            logger.error(f"❌ Book Ingestion Failed: {e}", exc_info=True)

    if _shutdown_requested:
        logger.info("🛑 Shutdown requested. Exiting.")
        return

    # ── YouTube Playlists Ingestion (Concurrent) ────────────
    logger.info(f"\n{'='*60}")
    logger.info("RESOLVING YOUTUBE PLAYLISTS & VIDEO IDS")
    logger.info(f"{'='*60}")

    all_ids = []
    if args.video_ids:
        all_ids = [vid.strip() for vid in args.video_ids.split(",") if vid.strip()]
        logger.info(f"🎯 Bypassing playlist resolution. Using explicit video IDs: {all_ids}")
    else:
        playlists_to_process = PLAYLIST_URLS
        if args.test_playlist:
            playlists_to_process = PLAYLIST_URLS[:1]
            logger.info("🧪 TEST MODE: Processing only first playlist")
        elif args.playlist_limit > 0:
            playlists_to_process = PLAYLIST_URLS[: args.playlist_limit]
            logger.info(f"🔢 Processing {len(playlists_to_process)} playlists")

        for pl in playlists_to_process:
            if _shutdown_requested:
                break
            logger.info(f"Resolving playlist: {pl}")
            all_ids.extend(get_video_ids_from_playlist(pl))

        if not args.test_playlist:
            all_ids += CORE_VIDEO_IDS

    seen = set()
    unique_ids = [v for v in all_ids if not (v in seen or seen.add(v))]

    # ── Primary Check: Prioritize Retries & Backfills ─────────
    primary_retry_ids = []

    # 1. Identify LightRAG backfills (Qdrant success but LightRAG failed/unknown/skipped)
    lightrag_backfill_ids = [
        vid
        for vid, m in state.get("metrics", {}).items()
        if isinstance(m, dict)
        and m.get("qdrant_status") == "success"
        and m.get("lightrag_status", "unknown") not in ("success", "skipped", "service_inactive")
    ]
    if lightrag_backfill_ids:
        logger.info(
            f"🔄 Primary Check: Found {len(lightrag_backfill_ids)} videos needing LightRAG backfill. Processing first: {lightrag_backfill_ids}"
        )
        for vid in lightrag_backfill_ids:
            if vid in state["processed_videos"]:
                state["processed_videos"].remove(vid)
        primary_retry_ids.extend(lightrag_backfill_ids)

    # 2. Identify Qdrant/general failures to retry (excluding permanent errors)
    qdrant_retry_ids = []
    for vid, m in state.get("metrics", {}).items():
        if isinstance(m, dict) and (
            m.get("status") == "failed" or m.get("qdrant_status") == "failed"
        ):
            if m.get("error_category") != "permanent" and m.get("will_retry") != False:
                qdrant_retry_ids.append(vid)

    for entry in state.get("dead_letter_queue", []):
        vid = entry.get("video_id")
        if vid and entry.get("will_retry", True) and entry.get("error_category") != "permanent":
            qdrant_retry_ids.append(vid)

    qdrant_retry_ids = list(dict.fromkeys(qdrant_retry_ids))
    if qdrant_retry_ids:
        logger.info(
            f"🔄 Primary Check: Found {len(qdrant_retry_ids)} videos needing Qdrant/general retry. Processing first: {qdrant_retry_ids}"
        )
        for vid in qdrant_retry_ids:
            if vid in state["processed_videos"]:
                state["processed_videos"].remove(vid)
            state["metrics"].pop(vid, None)
        primary_retry_ids.extend(qdrant_retry_ids)

    if lightrag_backfill_ids or qdrant_retry_ids:
        save_state()

    # Deduplicate primary_retry_ids to preserve order
    primary_retry_ids = list(dict.fromkeys(primary_retry_ids))

    # Prepend the primary_retry_ids to the unique_ids list, maintaining order and uniqueness
    seen_ids = set()
    unique_ids = [
        v for v in (primary_retry_ids + unique_ids) if not (v in seen_ids or seen_ids.add(v))
    ]

    # Apply video limit
    if args.video_limit > 0:
        unique_ids = unique_ids[: args.video_limit]
        logger.info(f"🔢 Video limit: processing {len(unique_ids)} videos")

    # Filter out already processed videos, separating into two phases
    retry_queued_ids = [
        v for v in unique_ids if v in primary_retry_ids and v not in state["processed_videos"]
    ]
    new_queued_ids = [
        v for v in unique_ids if v not in primary_retry_ids and v not in state["processed_videos"]
    ]

    total_queued = len(retry_queued_ids) + len(new_queued_ids)
    logger.info(f"🎯 Total queued: {total_queued} videos (concurrency={args.concurrency})")
    if retry_queued_ids:
        logger.info(f"👉 Phase 1 (Retries & Backfills): {len(retry_queued_ids)} videos")
    if new_queued_ids:
        logger.info(f"👉 Phase 2 (New Ingestions): {len(new_queued_ids)} videos")

    _progress = None
    if total_queued:
        _progress = ProgressTracker(total=total_queued)
        sem = asyncio.Semaphore(args.concurrency)

        # ── PHASE 1: Process and complete all retries/backfills ──
        if retry_queued_ids:
            logger.info(
                f"\n🚀 STARTING PHASE 1: Processing {len(retry_queued_ids)} retries/backfills..."
            )
            retry_tasks = [
                process_video_worker(
                    vid=vid,
                    sem=sem,
                    pipeline=pipeline,
                    container=container,
                    state=state,
                    save_state_fn=save_state,
                    args=args,
                    worker_num=i + 1,
                )
                for i, vid in enumerate(retry_queued_ids)
            ]
            await asyncio.gather(*retry_tasks)
            logger.info("✅ Phase 1 complete. All retries/backfills processed.")

        # ── PHASE 2: Process remaining new videos ──
        if new_queued_ids:
            if _shutdown_requested:
                logger.info("🛑 Shutdown requested before Phase 2. Exiting.")
                return
            logger.info(f"\n🚀 STARTING PHASE 2: Processing {len(new_queued_ids)} new videos...")
            new_tasks = [
                process_video_worker(
                    vid=vid,
                    sem=sem,
                    pipeline=pipeline,
                    container=container,
                    state=state,
                    save_state_fn=save_state,
                    args=args,
                    worker_num=i + 1,
                )
                for i, vid in enumerate(new_queued_ids)
            ]
            await asyncio.gather(*new_tasks)
            logger.info("✅ Phase 2 complete. All new videos processed.")

    # ── Structured Summary ───────────────────────────────────
    all_metrics = state.get("metrics", {})
    success_vids = [
        k for k, v in all_metrics.items() if isinstance(v, dict) and v.get("status") == "success"
    ]
    failed_vids = [
        k for k, v in all_metrics.items() if isinstance(v, dict) and v.get("status") == "failed"
    ]
    dlq_transient = [d for d in state.get("dead_letter_queue", []) if d.get("will_retry")]
    dlq_permanent = [d for d in state.get("dead_letter_queue", []) if not d.get("will_retry")]
    lg_backfill = [
        k
        for k, v in all_metrics.items()
        if isinstance(v, dict)
        and v.get("qdrant_status") == "success"
        and v.get("lightrag_status", "unknown") not in ("success", "skipped", "service_inactive")
    ]

    logger.info(f"\n{'='*60}")
    logger.info("BULK CONCURRENT INGESTION RUN COMPLETE")
    logger.info(f"{'='*60}")
    logger.info(f"  📄 Docs processed:           {len(state['processed_docs'])}")
    logger.info(f"  ✅ Videos success:           {len(success_vids)}")
    logger.info(f"  ❌ Videos failed:            {len(failed_vids)}")
    logger.info(f"  📬 DLQ (transient/retryable): {len(dlq_transient)}")
    logger.info(f"  🚫 DLQ (permanent/skip):      {len(dlq_permanent)}")
    logger.info(f"  📊 LightRAG backfill needed:  {len(lg_backfill)}")
    if _progress:
        logger.info(f"  🏁 {_progress.summary_line()}")
    if dlq_transient:
        logger.warning(f"\n⚠️  {len(dlq_transient)} transient failures → retry with: --retry-dlq")
    if lg_backfill:
        logger.info(
            f"💡 {len(lg_backfill)} videos need LightRAG → backfill with: --retry-lightrag-missing"
        )
    logger.info(f"{'='*60}")

    # Write JSON summary
    summary = {
        "run_ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "success_count": len(success_vids),
        "failed_count": len(failed_vids),
        "dlq_transient": len(dlq_transient),
        "dlq_permanent": len(dlq_permanent),
        "lightrag_backfill_needed": len(lg_backfill),
        "circuit_breaker_state": _circuit_breaker.state.value,
        "failed_video_ids": failed_vids,
        "dlq_transient_ids": [d["video_id"] for d in dlq_transient],
        "lightrag_backfill_ids": lg_backfill,
    }
    try:
        with open(SUMMARY_FILE, "w") as f:
            json.dump(summary, f, indent=2)
        logger.info(f"📝 Summary written → {SUMMARY_FILE}")
    except Exception as e:
        logger.warning(f"Could not write summary file: {e}")


if __name__ == "__main__":
    asyncio.run(main())
