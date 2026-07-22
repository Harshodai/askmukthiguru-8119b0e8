#!/usr/bin/env python3
"""
High-Throughput Auto-Scaling Concurrent Ingestion script with CONCURRENCY SAFETY & PERSISTENT CHECKPOINTING:
Hydrate LightRAG DIRECTLY from Qdrant `spiritual_wisdom` collection payload (89,053 points).

Features:
  1. Dynamic Auto-Scaling Concurrency (4 to 12 parallel workers based on rate limits & latency).
  2. `LIGHTRAG_INSERT_TIMEOUT=60.0s` fast timeout to bypass hanging LLM extractions.
  3. `asyncio.Lock()` for atomic counter increments & progress metrics.
  4. Atomic JSON file replacement (`.tmp` -> `.json`) to prevent partial checkpoint corruptions.
  5. Content-hash deduplication (`doc-id`), Qdrant deterministic UUID vector upserts, and Neo4j Cypher `MERGE`.
"""

import asyncio
import json
import os
import sys
import time
from pathlib import Path

# Add backend directory to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = PROJECT_ROOT / "backend"
sys.path.insert(0, str(BACKEND_DIR))

# Ensure backend .env is loaded
env_file = BACKEND_DIR / ".env"
if env_file.exists():
    with open(env_file) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())

# Map Docker container hostnames to localhost for host-level execution
if os.getenv("QDRANT_URL", "").startswith("http://qdrant"):
    os.environ["QDRANT_URL"] = "http://localhost:6333"
if os.getenv("NEO4J_URI", "").startswith("bolt://neo4j"):
    os.environ["NEO4J_URI"] = "bolt://localhost:7687"
if "redis:6379" in os.getenv("REDIS_URL", ""):
    os.environ["REDIS_URL"] = os.getenv("REDIS_URL", "").replace("redis:6379", "localhost:6379")
if "host.docker.internal" in os.getenv("SUPABASE_URL", ""):
    os.environ["SUPABASE_URL"] = os.getenv("SUPABASE_URL", "").replace("host.docker.internal", "127.0.0.1")

CHECKPOINT_FILE = PROJECT_ROOT / "data" / "lightrag_checkpoint.json"
CHECKPOINT_FILE.parent.mkdir(parents=True, exist_ok=True)


def load_checkpoint():
    if CHECKPOINT_FILE.exists():
        try:
            with open(CHECKPOINT_FILE, "r") as f:
                data = json.load(f)
                return data.get("next_offset"), data.get("processed_count", 0)
        except Exception as e:
            print(f"⚠️ Warning loading checkpoint: {e}")
    return None, 0


def save_checkpoint_atomic(next_offset, processed_count):
    tmp_file = CHECKPOINT_FILE.with_suffix(".json.tmp")
    try:
        with open(tmp_file, "w") as f:
            json.dump({
                "next_offset": next_offset,
                "processed_count": processed_count,
                "timestamp": time.time()
            }, f, indent=2)
        os.replace(tmp_file, CHECKPOINT_FILE)
    except Exception as e:
        print(f"⚠️ Warning saving atomic checkpoint: {e}")


async def process_single_point(lightrag_svc, point, sem, counter_lock, counters, start_time, rate_stats):
    payload = point.payload or {}
    text = payload.get("text") or payload.get("page_content") or ""
    source = payload.get("source_url") or payload.get("title") or f"point-{point.id}"

    if not text or len(text.strip()) < 50:
        async with counter_lock:
            counters["processed"] += 1
        return False

    async with sem:
        t0 = time.time()
        ok = False
        retry_count = 0
        insert_timeout = float(os.getenv("LIGHTRAG_INSERT_TIMEOUT", "60.0"))

        while retry_count < 2:
            try:
                ok = await lightrag_svc.safe_ainsert(text=text, file_paths=[source], timeout=insert_timeout)
                break
            except Exception as e:
                retry_count += 1
                if "rate limit" in str(e).lower() or "429" in str(e):
                    rate_stats["rate_limit_hits"] += 1
                    await asyncio.sleep(2.0 * retry_count)
                else:
                    await asyncio.sleep(0.5)

        elapsed = time.time() - t0
        await asyncio.sleep(0.05)

        async with counter_lock:
            counters["processed"] += 1
            if ok:
                counters["success"] += 1
            else:
                counters["failed"] += 1

            curr_processed = counters["processed"]
            elapsed_total = time.time() - start_time
            rate = (curr_processed / elapsed_total) * 60.0 if elapsed_total > 0 else 0.0
            pct = (curr_processed / 89053.0) * 100.0

            preview = text.strip()[:40].replace("\n", " ")
            status_str = "✅ Success" if ok else "⚠️ Failed"
            _point_id_str = str(point.id)
            print(f"[{curr_processed}/89053 ({pct:.2f}%)] Point {_point_id_str[:8]}... (\"{preview}...\") {status_str} ({elapsed:.1f}s) | Rate: {rate:.1f} pts/min", flush=True)

        return ok


async def main():
    from services.lightrag_service import LightRAGService
    from services.qdrant_service import QdrantService
    from app.config import settings

    target_concurrency = int(os.getenv("CONCURRENCY_WORKERS", "8"))
    insert_timeout = float(os.getenv("LIGHTRAG_INSERT_TIMEOUT", "60.0"))

    print(f"🚀 Initializing Auto-Scaling LightRAG Full-Collection Ingestion...")
    print(f"   Extraction Model: OpenRouter inference ({settings.openrouter_classify_model})")
    print(f"   Target Concurrency: {target_concurrency} Workers | Fast Timeout: {insert_timeout}s")
    print(f"   Source Collection: Qdrant `spiritual_wisdom` (All 89,053 points)")

    saved_offset, saved_count = load_checkpoint()
    if saved_offset:
        _offset_str = str(saved_offset)
        print(f"🔄 Resuming from Checkpoint Offset: '{_offset_str[:8]}...' (Processed so far: {saved_count} points)")
    else:
        print("🆕 Starting fresh ingestion run from beginning of collection.")

    qdrant_svc = QdrantService()
    lightrag_svc = LightRAGService()
    await lightrag_svc.initialize()

    batch_size = 50
    sem = asyncio.Semaphore(target_concurrency)
    semaphore_lock = asyncio.Lock()
    counter_lock = asyncio.Lock()
    rate_stats = {"rate_limit_hits": 0}

    next_offset = saved_offset
    counters = {"processed": saved_count, "success": saved_count, "failed": 0}
    start_time = time.time()

    print(f"⚙️ Running auto-scaling worker pool ({target_concurrency} workers max)...")

    while True:
        _scroll_retries = 0
        _max_scroll_retries = 5
        while _scroll_retries < _max_scroll_retries:
            try:
                scroll_res, next_offset = qdrant_svc._client.scroll(
                    collection_name="spiritual_wisdom",
                    limit=batch_size,
                    offset=next_offset,
                    with_payload=True,
                    with_vectors=False,
                )
                break
            except Exception as e:
                _scroll_retries += 1
                _backoff = 2.0 ** _scroll_retries
                print(f"❌ Failed to scroll points from Qdrant (attempt {_scroll_retries}/{_max_scroll_retries}): {e}")
                if _scroll_retries >= _max_scroll_retries:
                    raise RuntimeError(f"Qdrant scroll failed after {_max_scroll_retries} attempts")
                await asyncio.sleep(_backoff)

        if not scroll_res:
            print("🏁 Reached end of Qdrant collection. All points processed!")
            break

        # Process batch concurrently under semaphore & lock protection
        tasks = [
            process_single_point(lightrag_svc, point, sem, counter_lock, counters, start_time, rate_stats)
            for point in scroll_res
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for i, r in enumerate(results):
            if isinstance(r, Exception):
                print(f"⚠️ Task {i} unhandled exception: {r}")

        # Auto-scale concurrency between 4 and 12 based on rate limits
        async with semaphore_lock:
            _elapsed_batch = time.time() - start_time
            if _elapsed_batch > 30:
                _new_target = target_concurrency
                if rate_stats["rate_limit_hits"] > 5:
                    _new_target = max(4, target_concurrency - 1)
                elif rate_stats["rate_limit_hits"] == 0:
                    _new_target = min(12, target_concurrency + 1)
                if _new_target != target_concurrency:
                    target_concurrency = _new_target
                    sem = asyncio.Semaphore(target_concurrency)
                    print(f"⚡ Auto-scaling: adjusted concurrency to {target_concurrency}")
                    rate_stats["rate_limit_hits"] = 0

        # Atomically save checkpoint state after each batch
        async with counter_lock:
            save_checkpoint_atomic(next_offset, counters["processed"])

        if next_offset is None:
            print("🏁 Reached end of Qdrant collection. All points processed!")
            break

    total_time = time.time() - start_time
    print("\n" + "=" * 80)
    print(f"🎉 Auto-Scaling High-Throughput Ingestion Completed in {total_time:.1f}s")
    print(f"   Total Processed Points: {counters['processed']} / 89,053")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())
