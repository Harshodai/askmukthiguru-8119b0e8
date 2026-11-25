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
import fcntl
import json
import os
import re
import sys
import time
from pathlib import Path
from contextlib import contextmanager

# Add backend and project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = PROJECT_ROOT / "backend" if (PROJECT_ROOT / "backend").exists() else PROJECT_ROOT
sys.path.insert(0, str(PROJECT_ROOT))
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
if (
    os.getenv("QDRANT_URL", "").startswith("http://qdrant:")
    or os.getenv("QDRANT_URL", "") == "http://qdrant"
):
    os.environ["QDRANT_URL"] = "http://localhost:6333"
if (
    os.getenv("NEO4J_URI", "").startswith("bolt://neo4j:")
    or os.getenv("NEO4J_URI", "") == "bolt://neo4j"
):
    os.environ["NEO4J_URI"] = "bolt://localhost:7687"
if "redis:6379" in os.getenv("REDIS_URL", ""):
    os.environ["REDIS_URL"] = os.getenv("REDIS_URL", "").replace("redis:6379", "localhost:6379")
if "host.docker.internal" in os.getenv("SUPABASE_URL", ""):
    os.environ["SUPABASE_URL"] = os.getenv("SUPABASE_URL", "").replace(
        "host.docker.internal", "127.0.0.1"
    )

CHECKPOINT_FILE = Path(
    os.getenv("LIGHTRAG_CHECKPOINT_FILE", str(PROJECT_ROOT / "data" / "lightrag_checkpoint.json"))
)
LIGHTRAG_PIECE_SIZE = 1500
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?\u0964\n])\s+")
_CONTEXT_HEADER_RE = re.compile(r"^(\[Context:[^\]]+\]\s*)", re.DOTALL)


def chunk_sentences(text: str, size: int = LIGHTRAG_PIECE_SIZE) -> list[str]:
    """Split text into <=size chunks on sentence boundaries (stdlib only).

    If text contains a leading [Context: ...] header, it is preserved and
    prepended to each chunk so graph extraction never loses speaker/situational grounding.
    Sentences are packed greedily so no chunk cuts mid-sentence; a single
    over-long sentence falls back to a hard cut so pieces stay bounded.
    Short texts return unchanged as a single piece.
    """
    if not text:
        return [text]

    # Extract leading [Context: ...] header if present
    match = _CONTEXT_HEADER_RE.match(text)
    header = ""
    body = text
    if match:
        header = match.group(1).strip()
        body = text[len(match.group(0)) :].strip()
        if not body:
            return [text]

    effective_size = max(300, size - len(header) - 1) if header else size

    if len(body) <= effective_size:
        return [text]

    sentences = [s for s in _SENTENCE_SPLIT_RE.split(body) if s]
    if not sentences:
        return [text]

    chunks: list[str] = []
    current = ""
    for sentence in sentences:
        while len(sentence) > effective_size:
            if current:
                chunks.append(f"{header}\n{current}".strip() if header else current)
                current = ""
            chunks.append(
                f"{header}\n{sentence[:effective_size]}".strip()
                if header
                else sentence[:effective_size]
            )
            sentence = sentence[effective_size:]
        if not sentence:
            continue
        candidate = f"{current} {sentence}".strip() if current else sentence
        if len(candidate) <= effective_size:
            current = candidate
        else:
            chunks.append(f"{header}\n{current}".strip() if header else current)
            current = sentence
    if current:
        chunks.append(f"{header}\n{current}".strip() if header else current)
    return chunks or [text]


CHECKPOINT_SCHEMA_VERSION = 2
DEFAULT_LIGHTRAG_SOURCE_COLLECTION = "spiritual_wisdom"


def resolve_source_collection() -> str:
    """Resolve the source explicitly; never inherit serving's QDRANT_COLLECTION."""
    source = os.getenv(
        "LIGHTRAG_SOURCE_COLLECTION", DEFAULT_LIGHTRAG_SOURCE_COLLECTION
    ).strip()
    if not source:
        raise ValueError("LIGHTRAG_SOURCE_COLLECTION must be a non-empty Qdrant collection name")
    return source


@contextmanager
def checkpoint_process_lock(checkpoint_file: Path | None = None):
    """Hold an OS lock for the entire run; kernel releases it if the process dies."""
    path = checkpoint_file or CHECKPOINT_FILE
    lock_path = Path(f"{path}.lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+", encoding="utf-8") as lock_handle:
        try:
            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError(
                f"Another LightRAG ingestion process holds checkpoint lock {lock_path}"
            ) from exc
        try:
            yield
        finally:
            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)


def load_checkpoint(
    source_collection: str,
    source_point_count: int,
    working_dir: str,
    checkpoint_file: Path | None = None,
) -> tuple[object | None, dict[str, int], bool]:
    """Load only a v2 checkpoint proven to belong to this exact source/target."""
    path = checkpoint_file or CHECKPOINT_FILE
    if not path.exists():
        return None, {"processed": 0, "success": 0, "skipped": 0, "rejected": 0, "failed": 0}, False

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(
            f"LightRAG checkpoint {path} is unreadable; inspect and repair it explicitly"
        ) from exc

    if data.get("schema_version") != CHECKPOINT_SCHEMA_VERSION:
        raise RuntimeError(
            f"Legacy/incompatible LightRAG checkpoint at {path}. "
            "It has no trustworthy source-collection identity. Do not resume it blindly; "
            "inspect the old run and choose a new LIGHTRAG_CHECKPOINT_FILE or explicitly "
            "migrate the checkpoint after reconciling the graph store."
        )

    expected = {
        "source_collection": source_collection,
        "source_point_count": source_point_count,
        "working_dir": str(Path(working_dir).resolve()),
    }
    mismatches = {
        key: (data.get(key), value)
        for key, value in expected.items()
        if data.get(key) != value
    }
    if mismatches:
        details = ", ".join(
            f"{key}: checkpoint={actual!r}, current={wanted!r}"
            for key, (actual, wanted) in mismatches.items()
        )
        raise RuntimeError(
            f"LightRAG checkpoint target mismatch ({details}). "
            "Use a separate LIGHTRAG_CHECKPOINT_FILE for a different ingestion target."
        )

    counters = {
        "processed": int(data.get("processed_count", 0)),
        "success": int(data.get("success_count", 0)),
        "skipped": int(data.get("skipped_count", 0)),
        "rejected": int(data.get("rejected_count", 0)),
        "failed": 0,
    }
    if min(counters.values()) < 0:
        raise RuntimeError(f"LightRAG checkpoint contains negative counters: {path}")
    if counters["processed"] != counters["success"] + counters["skipped"] + counters["rejected"]:
        raise RuntimeError(
            f"LightRAG checkpoint counters do not reconcile at {path}; "
            "refusing to resume from an ambiguous offset"
        )
    if counters["processed"] > source_point_count:
        raise RuntimeError(
            f"LightRAG checkpoint processed_count={counters['processed']} exceeds "
            f"current source point count={source_point_count}"
        )
    completed = bool(data.get("completed", False))
    if completed and counters["processed"] != source_point_count:
        raise RuntimeError(
            f"LightRAG checkpoint is marked complete but processed_count={counters['processed']} "
            f"does not equal source_point_count={source_point_count}"
        )
    return data.get("next_offset"), counters, completed


def save_checkpoint_atomic(
    next_offset: object | None,
    counters: dict[str, int],
    source_collection: str,
    source_point_count: int,
    working_dir: str,
    completed: bool = False,
    checkpoint_file: Path | None = None,
) -> None:
    """Durably persist a cursor only after every point in the batch is accounted for."""
    path = checkpoint_file or CHECKPOINT_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_file = path.with_suffix(path.suffix + ".tmp")
    data = {
        "schema_version": CHECKPOINT_SCHEMA_VERSION,
        "source_collection": source_collection,
        "source_point_count": source_point_count,
        "working_dir": str(Path(working_dir).resolve()),
        "next_offset": next_offset,
        "completed": completed,
        "processed_count": counters["processed"],
        "success_count": counters["success"],
        "skipped_count": counters["skipped"],
        "rejected_count": counters["rejected"],
        "timestamp": time.time(),
    }
    with tmp_file.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp_file, path)


async def process_single_point(
    lightrag_svc, point, sem, counter_lock, counters, start_time, rate_stats, total_points
) -> str:
    """Process one source point; failed inserts are retryable, quality rejects are explicit."""
    async def _record(status: str) -> None:
        async with counter_lock:
            counters["processed"] += 1
            counters[status] += 1

    try:
        payload = point.payload or {}
        text = payload.get("text") or payload.get("page_content") or ""
        source = payload.get("source_url") or payload.get("title") or f"point-{point.id}"

        if isinstance(text, str):
            import unicodedata

            text = (
                text.replace("\x00", "")
                .replace("<|begin_of_text|>", "")
                .replace("<|eot_id|>", "")
                .replace("<|end_of_text|>", "")
            )
            text = unicodedata.normalize("NFC", text).strip()
            try:
                from services.doctrine_terms import apply_corrections

                text = apply_corrections(text)
            except Exception as exc:
                print(f"⚠️ Doctrine correction unavailable for {point.id}: {exc}", flush=True)

        if not isinstance(text, str) or len(text.strip()) < 50:
            await _record("skipped")
            return "skipped"

        # Never feed known prompt/ASR/provider artefacts into graph extraction.
        from services.text_quality_filter import find_artifact

        artifact = find_artifact(text)
        if artifact is not None:
            await _record("rejected")
            _pid = str(getattr(point, "id", "?"))[:8]
            print(f"⚠️ Point {_pid}... rejected by quality gate: {artifact[:80]!r}", flush=True)
            return "rejected"

        pieces = chunk_sentences(text)
        async with sem:
            t0 = time.time()
            insert_timeout = float(os.getenv("LIGHTRAG_INSERT_TIMEOUT", "60.0"))
            for piece_index, piece in enumerate(pieces):
                piece_ok = False
                last_error = "safe_ainsert returned false"
                for attempt in range(1, 3):
                    try:
                        piece_ok = await lightrag_svc.safe_ainsert(
                            text=piece, file_paths=[source], timeout=insert_timeout
                        ) is True
                        if piece_ok:
                            break
                        last_error = "safe_ainsert returned false"
                    except Exception as exc:
                        last_error = str(exc)
                        if "rate limit" in last_error.lower() or "429" in last_error:
                            rate_stats["rate_limit_hits"] += 1
                        print(
                            f"⚠️ Retry {attempt}/2 for point {str(point.id)[:8]} "
                            f"piece {piece_index + 1}/{len(pieces)}: {last_error[:160]}",
                            flush=True,
                        )
                    if attempt < 2:
                        await asyncio.sleep(2.0 * attempt)
                if not piece_ok:
                    await _record("failed")
                    _pid = str(getattr(point, "id", "?"))[:8]
                    print(
                        f"❌ Point {_pid}... piece {piece_index + 1}/{len(pieces)} "
                        f"failed after retries: {last_error[:200]}",
                        flush=True,
                    )
                    return "failed"

            elapsed = time.time() - t0
            await asyncio.sleep(0.05)

        await _record("success")
        rate = (counters["processed"] / max(time.time() - start_time, 0.001)) * 60.0
        pct = (counters["processed"] / max(total_points, 1)) * 100.0
        preview = text[:40].replace("\n", " ")
        print(
            f'[{counters["processed"]}/{total_points} ({pct:.2f}%)] '
            f'Point {str(point.id)[:8]}... ("{preview}...") '
            f"✅ Success ({elapsed:.1f}s) | Rate: {rate:.1f} pts/min",
            flush=True,
        )
        return "success"
    except Exception as exc:
        await _record("failed")
        _pid = str(getattr(point, "id", "?"))[:8]
        print(f"❌ Point {_pid}... unhandled ingestion error: {exc}", flush=True)
        return "failed"


async def main():
    from app.config import settings
    from services.lightrag_service import LightRAGService
    from services.qdrant_service import QdrantService

    source_collection = resolve_source_collection()
    target_concurrency = int(os.getenv("CONCURRENCY_WORKERS", "8"))
    if not 1 <= target_concurrency <= 12:
        raise ValueError("CONCURRENCY_WORKERS must be between 1 and 12")
    insert_timeout = float(os.getenv("LIGHTRAG_INSERT_TIMEOUT", "60.0"))
    working_dir = os.getenv("LIGHTRAG_WORKING_DIR", "data/lightrag")

    qdrant_svc = QdrantService()
    try:
        source_info = qdrant_svc._client.get_collection(collection_name=source_collection)
    except Exception as exc:
        raise RuntimeError(
            f"Cannot open LightRAG source collection {source_collection!r}; refusing to start"
        ) from exc
    total_points = int(source_info.points_count or 0)
    if total_points <= 0:
        raise RuntimeError(
            f"LightRAG source collection {source_collection!r} has no points; refusing an empty run"
        )

    # A kernel-managed lock prevents two processes from consuming the same cursor.
    with checkpoint_process_lock():
        saved_offset, counters, already_completed = load_checkpoint(
            source_collection=source_collection,
            source_point_count=total_points,
            working_dir=working_dir,
        )

        if already_completed:
            print(
                f"✅ LightRAG ingestion already completed for {source_collection} "
                f"({counters['processed']:,}/{total_points:,}); no work required."
            )
            return

        print("🚀 Initializing LightRAG source-to-graph ingestion...")
        print(f"   Source Qdrant collection: {source_collection} ({total_points:,} points)")
        print(f"   LightRAG working directory: {Path(working_dir).resolve()}")
        print(f"   Extraction model: OpenRouter inference ({settings.openrouter_classify_model})")
        print(
            f"   Target concurrency: {target_concurrency} workers | "
            f"insert timeout: {insert_timeout}s"
        )
        print(
            "   Checkpoint: "
            f"{counters['processed']:,}/{total_points:,} processed "
            f"(success={counters['success']:,}, skipped={counters['skipped']:,}, "
            f"rejected={counters['rejected']:,})"
        )
        if saved_offset is not None:
            print(f"🔄 Resuming from checkpoint offset {str(saved_offset)[:80]}")
        else:
            print("🆕 Starting from the beginning; no compatible checkpoint exists.")

        lightrag_svc = LightRAGService()
        await lightrag_svc.initialize()
        if not lightrag_svc._initialized:
            raise RuntimeError(
                "LightRAGService failed to initialize (Memgraph/Qdrant unreachable); aborting."
            )

        batch_size = int(os.getenv("LIGHTRAG_BATCH_SIZE", "50"))
        if not 1 <= batch_size <= 500:
            raise ValueError("LIGHTRAG_BATCH_SIZE must be between 1 and 500")

        sem = asyncio.Semaphore(target_concurrency)
        semaphore_lock = asyncio.Lock()
        counter_lock = asyncio.Lock()
        rate_stats = {"rate_limit_hits": 0}
        next_offset = saved_offset
        start_time = time.time()

        while True:
            scroll_res = None
            batch_next_offset = next_offset
            for attempt in range(1, 6):
                try:
                    scroll_res, batch_next_offset = qdrant_svc._client.scroll(
                        collection_name=source_collection,
                        limit=batch_size,
                        offset=next_offset,
                        with_payload=True,
                        with_vectors=False,
                    )
                    break
                except Exception as exc:
                    if attempt == 5:
                        raise RuntimeError(
                            f"Qdrant scroll failed 5 times for source {source_collection!r}; "
                            "checkpoint was not advanced"
                        ) from exc
                    await asyncio.sleep(2 ** attempt)
            if not scroll_res:
                print("🏁 Reached end of the selected source collection.")
                break

            results = await asyncio.gather(
                *[
                    process_single_point(
                        lightrag_svc,
                        point,
                        sem,
                        counter_lock,
                        counters,
                        start_time,
                        rate_stats,
                        total_points,
                    )
                    for point in scroll_res
                ],
                return_exceptions=True,
            )
            failed_count = sum(
                1 for result in results if result not in ("success", "skipped", "rejected")
            )
            if failed_count:
                # Do not move the cursor. The entire batch will replay on restart;
                # successful document inserts are deduplicated by LightRAG doc status.
                raise RuntimeError(
                    f"LightRAG batch at offset {str(next_offset)[:80]} had "
                    f"{failed_count}/{len(scroll_res)} retryable failures. "
                    "Checkpoint was NOT advanced; resolve provider/store failures and resume."
                )

            # Only a fully accounted batch advances the durable cursor.
            save_checkpoint_atomic(
                next_offset=batch_next_offset,
                counters=counters,
                source_collection=source_collection,
                source_point_count=total_points,
                working_dir=working_dir,
                completed=batch_next_offset is None,
            )
            next_offset = batch_next_offset

            async with semaphore_lock:
                if time.time() - start_time > 30:
                    if rate_stats["rate_limit_hits"] > 5:
                        new_target = max(1, target_concurrency - 1)
                    elif rate_stats["rate_limit_hits"] == 0:
                        new_target = min(12, target_concurrency + 1)
                    else:
                        new_target = target_concurrency
                    if new_target != target_concurrency:
                        target_concurrency = new_target
                        sem = asyncio.Semaphore(target_concurrency)
                        print(f"⚡ Auto-scaling concurrency to {target_concurrency}")
                    rate_stats["rate_limit_hits"] = 0

            print(
                f"💾 Checkpoint saved: {counters['processed']:,}/{total_points:,} "
                f"(success={counters['success']:,}, skipped={counters['skipped']:,}, "
                f"rejected={counters['rejected']:,})"
            )
            if next_offset is None:
                print("🏁 Reached end of the selected source collection.")
                break

        elapsed = time.time() - start_time
        print("\n" + "=" * 80)
        print(f"LightRAG ingestion completed in {elapsed:.1f}s")
        print(f"Source: {source_collection} ({total_points:,} points)")
        print(
            f"Processed: {counters['processed']:,} | success: {counters['success']:,} | "
            f"skipped: {counters['skipped']:,} | rejected: {counters['rejected']:,}"
        )
        print("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())
