"""
Migration Script: Re-process already ingested data to apply new RAG features.

This script:
1. Fetches all existing chunks from Qdrant.
2. Reconstructs the full text for each source (stripping old chunk headers).
3. Backs up the original data to a timestamped recovery collection.
4. Re-ingests through the pipeline with new features.
5. Rolls back automatically if re-ingestion fails.

Keeps the last 5 backup versions. Older backups are pruned.
"""

import asyncio
import datetime
import logging
import re
import sys
from collections import defaultdict

# Fix import paths
sys.path.insert(0, ".")

from app.config import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("migrate_data")

# Regex to strip old contextual chunk headers added during prior ingestion
# Matches: [Source: ... | Speaker: ... | Topic: ...]\n
HEADER_PATTERN = re.compile(
    r"\[Source:.*?(?:\| Speaker:.*?)?(?:\| Topic:.*?)?\]\s*\n?",
    re.IGNORECASE,
)


def strip_old_headers(text: str) -> str:
    """Remove contextual chunk headers that were embedded during prior ingestion."""
    return HEADER_PATTERN.sub("", text).strip()


async def restore_from_backup(qdrant, source_url: str, backup_collection: str):
    """Restore a single source from the backup collection to the main collection."""
    try:
        from qdrant_client.http.models import (
            PointStruct, Filter, FieldCondition, MatchValue,
        )

        # Delete whatever partial data exists in main
        qdrant.delete_by_source(source_url)

        # Scroll from backup
        points, _ = qdrant._client.scroll(
            collection_name=backup_collection,
            scroll_filter=Filter(
                must=[FieldCondition(key="source_url", match=MatchValue(value=source_url))]
            ),
            limit=1000,
            with_payload=True,
            with_vectors=True,
        )

        if not points:
            logger.warning(f"  No backup data found for {source_url}")
            return False

        restore_points = [
            PointStruct(id=p.id, vector=p.vector, payload=p.payload)
            for p in points
        ]

        qdrant._client.upsert(
            collection_name=qdrant._collection,
            points=restore_points,
        )
        logger.info(f"  🔄 Restored {len(restore_points)} points from backup for {source_url}")
        return True
    except Exception as e:
        logger.error(f"  ❌ RESTORE FAILED for {source_url}: {e}")
        return False


async def migrate():
    logger.info("=" * 60)
    logger.info("Starting data migration...")
    logger.info("=" * 60)

    # Initialize services (startup/shutdown are synchronous in this codebase)
    from app.dependencies import get_container, startup, shutdown
    startup()
    container = get_container()
    qdrant = container.qdrant
    pipeline = container.ingestion

    # LightRAG requires async initialization (done in main.py lifespan normally)
    try:
        await container.lightrag.initialize()
        logger.info("✅ LightRAG initialized for graph extraction")
    except Exception as e:
        logger.warning(f"⚠️  LightRAG init failed (Graph RAG will be skipped): {e}")

    try:
        # Step 1: Fetch all chunks
        logger.info("Fetching all existing chunks from Qdrant...")
        all_chunks = qdrant.get_all_texts()

        # Filter for leaf nodes only (raptor_level 0)
        leaf_chunks = [c for c in all_chunks if c.get("raptor_level") == 0]
        logger.info(f"Retrieved {len(leaf_chunks)} leaf chunks.")

        if not leaf_chunks:
            logger.info("No data to migrate. Exiting.")
            return

        # Step 2: Group by source_url
        sources = defaultdict(list)
        metadata = {}
        for c in leaf_chunks:
            url = c["source_url"]
            sources[url].append(c)
            if url not in metadata:
                metadata[url] = {
                    "title": c.get("title", ""),
                    "speaker": c.get("speaker", "Unknown"),
                    "topic": c.get("topic", "Spiritual"),
                }

        logger.info(f"Found {len(sources)} unique sources to re-process.")

        # Step 3: Create timestamped backup collection
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_prefix = f"{settings.qdrant_collection}_recovery_v"
        backup_collection = f"{backup_prefix}{timestamp}"

        # Prune old backups (keep last 5)
        logger.info("Pruning old backups (keeping last 5)...")
        qdrant.prune_backups(backup_prefix, max_backups=5)

        # Step 4: Process each source
        success_count = 0
        fail_count = 0
        skip_count = 0

        for i, (url, chunks) in enumerate(sources.items()):
            logger.info(f"\n[{i+1}/{len(sources)}] Processing: {url}")

            # 4a: Backup before touching anything
            logger.info(f"  📦 Backing up to {backup_collection}...")
            backed_up = qdrant.backup_source(url, backup_collection)
            if not backed_up:
                logger.warning(f"  ⚠️  Backup returned empty for {url}, skipping to be safe")
                skip_count += 1
                continue

            # 4b: Reconstruct text (sort by chunk_index, strip old headers)
            sorted_chunks = sorted(chunks, key=lambda x: x.get("chunk_index", 0))
            raw_texts = [c["text"] for c in sorted_chunks]
            cleaned_texts = [strip_old_headers(t) for t in raw_texts]
            full_text = " ".join(cleaned_texts)

            if len(full_text.strip()) < 50:
                logger.warning(f"  ⚠️  Reconstructed text too short ({len(full_text)} chars), skipping")
                skip_count += 1
                continue

            meta = metadata[url]
            logger.info(
                f"  📝 Reconstructed {len(full_text)} chars "
                f"(title={meta['title'][:40]}, speaker={meta['speaker']})"
            )

            # 4c: Re-ingest with new pipeline features
            try:
                result = await pipeline.ingest_raw_text(
                    text=full_text,
                    source_url=url,
                    title=meta["title"],
                    speaker=meta["speaker"],
                    topic=meta["topic"],
                    max_accuracy=True,
                    on_progress=lambda msg, pct: logger.info(f"  {int(pct*100)}%: {msg}"),
                )

                if result.get("status") == "success":
                    success_count += 1
                    logger.info(f"  ✅ Success: {result.get('chunks_indexed', 0)} chunks indexed")
                else:
                    logger.error(f"  ❌ Failed: {result.get('message', 'unknown error')}")
                    logger.info(f"  🔄 Rolling back from backup...")
                    await restore_from_backup(qdrant, url, backup_collection)
                    fail_count += 1

            except Exception as e:
                logger.error(f"  ❌ Exception during re-ingestion: {e}")
                logger.info(f"  🔄 Rolling back from backup...")
                await restore_from_backup(qdrant, url, backup_collection)
                fail_count += 1

        # Summary
        logger.info("\n" + "=" * 60)
        logger.info("MIGRATION COMPLETE")
        logger.info(f"  ✅ Success: {success_count}/{len(sources)}")
        logger.info(f"  ❌ Failed (rolled back): {fail_count}")
        logger.info(f"  ⚠️  Skipped: {skip_count}")
        logger.info(f"  📦 Backup collection: {backup_collection}")
        logger.info("=" * 60)

    finally:
        shutdown()


if __name__ == "__main__":
    asyncio.run(migrate())
