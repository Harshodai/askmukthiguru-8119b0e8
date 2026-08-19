"""Qdrant indexing operations: upsert, delete, backup, count, scroll."""

from __future__ import annotations

import functools
import logging
import time
from typing import Optional

from qdrant_client import QdrantClient
from qdrant_client.http.models import (
    FieldCondition,
    Filter,
    FilterSelector,
    MatchValue,
    PointStruct,
)

from app.config import settings
from services.qdrant.metrics import track_upsert_latency
from services.qdrant.utils import QdrantUtils
from services.tenant_context import TenantContext, get_tenant_collection

logger = logging.getLogger(__name__)


def retry_with_backoff(max_retries=3, initial_delay=1):
    """Exponential backoff decorator for Qdrant operations."""

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            delay = initial_delay
            last_exception = None
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    if attempt == max_retries - 1:
                        break
                    logger.warning(
                        f"Qdrant {func.__name__} failed (attempt {attempt + 1}/{max_retries}): {e}. Retrying in {delay}s..."
                    )
                    time.sleep(delay)
                    delay *= 2

            logger.error(f"Qdrant {func.__name__} failed after {max_retries} attempts.")
            raise last_exception

        return wrapper

    return decorator


class QdrantIndexer:
    """Handles chunk upsert, source-level deletion, backup, and counts."""

    def __init__(self, client: QdrantClient, collection: Optional[str] = None) -> None:

        self._client = client
        if collection:
            self._collection = collection
        else:
            # Use tenant context for collection name to support multi-tenancy
            self._collection = get_tenant_collection(settings.qdrant_collection)
        self._utils = QdrantUtils()

    @retry_with_backoff(max_retries=3)
    @track_upsert_latency
    def upsert_chunks(
        self,
        texts: list[str],
        vectors: list[list[float]],
        metadatas: list[dict],
        sparse_vectors: Optional[list[dict]] = None,
    ) -> int:
        """
        Batch upsert text chunks with dense + optional sparse vectors.

        Uses deterministic IDs based on source_url:chunk_index:raptor_level
        for automatic deduplication on re-ingestion.
        """
        len_texts, len_vectors, len_metadatas = len(texts), len(vectors), len(metadatas)
        if not (len_texts == len_vectors == len_metadatas):
            raise ValueError(
                f"upsert_chunks: length mismatch — texts={len_texts}, "
                f"vectors={len_vectors}, metadatas={len_metadatas}"
            )

        # ------------------------------------------------------------------
        # Quality gate at the storage boundary — the LAST line of defence.
        #
        # `ingest/pipeline.py:_embed_and_upsert` gates earlier (before embedding,
        # so it also saves the embed cost), but it is not the only writer:
        # `ingest/raptor.py:118` upserts LLM-generated summaries, and several
        # standalone scripts under scripts/ingestion/ build chunks themselves and
        # never touch IngestionPipeline at all. The 2026-08-01 audit found 29.4%
        # of the live corpus contaminated precisely because validation lived on
        # one path instead of at the chokepoint every path must cross.
        #
        # Gating here means no caller — pipeline, RAPTOR, ad-hoc script, or a
        # script written next year — can put LLM chain-of-thought or an ASR
        # decoder loop into the corpus. Rejections are logged with the matched
        # artifact so they stay auditable, never silently dropped.
        # ------------------------------------------------------------------
        from services.text_quality_filter import select_clean

        keep, rejected = select_clean(texts)
        if rejected:
            logger.warning(
                "upsert_chunks: rejected %d/%d chunks failing the quality gate "
                "(collection=%s). First: %r in %r",
                len(rejected),
                len_texts,
                self._collection,
                rejected[0][1],
                rejected[0][2],
            )
            texts = [texts[i] for i in keep]
            vectors = [vectors[i] for i in keep]
            metadatas = [metadatas[i] for i in keep]
            if sparse_vectors:
                sparse_vectors = [
                    sparse_vectors[i] if i < len(sparse_vectors) else {} for i in keep
                ]
        if not texts:
            logger.warning(
                "upsert_chunks: every chunk was rejected by the quality gate "
                "(collection=%s) — nothing written",
                self._collection,
            )
            return 0

        # ------------------------------------------------------------------
        # Batch-level repeat guard. The quality gate above judges one chunk at
        # a time and therefore cannot see a generator stuck in a loop: each of
        # the 227 identical copies found in the 2026-08-01 corpus measurement
        # was individually innocent, and `make_point_id` hashes chunk_index, so
        # every copy earned its own point id and all of them persisted.
        # The signal only exists across the batch — exactly what this layer can
        # see and the per-chunk filter cannot.
        # ------------------------------------------------------------------
        from services.text_quality_filter import collapse_repeats, is_repeat_alarm

        sources = [m.get("source_url") or "__missing_source__" for m in metadatas]
        point_ids = [
            self._utils.make_point_id(
                m.get("source_url", ""),
                m.get("chunk_index", i),
                m.get("raptor_level", 0),
            )
            for i, m in enumerate(metadatas)
        ]
        keep_unique, repeats = collapse_repeats(texts, sources, metadatas=metadatas)
        if repeats:
            worst_text, worst_count, worst_source = repeats[0]
            dropped_total = sum(count for _, count, _ in repeats)
            alarm = is_repeat_alarm(repeats)
            # A handful of duplicates is ordinary; a run of them means the
            # upstream writer stopped advancing, and the corpus damage starts
            # before this gate. Say so loudly enough to be actionable.
            (logger.error if alarm else logger.warning)(
                "upsert_chunks: collapsed %d duplicate chunks across %d distinct "
                "texts (collection=%s). Worst: %d copies of %r from source %r.%s",
                dropped_total,
                len(repeats),
                self._collection,
                worst_count,
                worst_text,
                worst_source,
                " A repeat run this long indicates an upstream generator loop — "
                "investigate the writer, not just this batch."
                if alarm
                else "",
            )

            # Reconcile stale Qdrant points for dropped duplicate chunks before upsert
            keep_set = set(keep_unique)
            stale_point_ids = [point_ids[i] for i in range(len(metadatas)) if i not in keep_set]

            if stale_point_ids:
                try:
                    self._client.delete(
                        collection_name=self._collection,
                        points_selector=stale_point_ids,
                    )
                except Exception as exc:
                    logger.warning("Failed to delete stale Qdrant points before upsert: %s", exc)

            texts = [texts[i] for i in keep_unique]
            vectors = [vectors[i] for i in keep_unique]
            metadatas = [metadatas[i] for i in keep_unique]
            point_ids = [point_ids[i] for i in keep_unique]
            if sparse_vectors:
                sparse_vectors = [
                    sparse_vectors[i] if i < len(sparse_vectors) else {} for i in keep_unique
                ]

        points = []
        for i, (text, vector, meta, point_id) in enumerate(
            zip(texts, vectors, metadatas, point_ids)
        ):
            # Build named vector dict
            vector_dict = {"dense": vector}
            if sparse_vectors and i < len(sparse_vectors):
                sparse_vec = sparse_vectors[i]
                # Only include sparse if it has meaningful data to avoid 400 Bad Request
                if sparse_vec and (len(sparse_vec.get("indices", [])) > 0 or len(sparse_vec) > 0):
                    vector_dict["sparse"] = self._utils.sparse_dict_to_vector(sparse_vec)

            # `phonetic_tokens` is no longer written. It existed to feed a
            # phonetic prefetch in QdrantSearcher that was removed for latency
            # (see the "Dropping the extra summary/phonetic prefetches" comment
            # there), leaving a per-chunk token list on every point that nothing
            # queried — 36% of blue and 100% of green. Restoring Indic
            # misspelling tolerance means re-adding BOTH the prefetch and this
            # write; services/phonetic.py:IndicPhoneticMatcher is still there for that.
            payload = {"text": text, **meta}
            payload.setdefault("tenant_id", TenantContext.get() or settings.default_tenant_id)
            payload.setdefault("corpus_id", settings.default_corpus_id)
            # Task #17 rights gate (services/qdrant/searcher.py) mandatorily filters on
            # this field when settings.require_licensed_domain_reads is True. Only
            # Sri Preethaji/Sri Krishnaji's own approved sources are ever ingested here
            # (see CLAUDE.md's data-source constraint) -- this pipeline never handles
            # other-teacher content, unlike ontology_writer.py's Neo4j BEING-node stamp,
            # which does need the registered/unverified distinction. Without this write,
            # every chunk indexed here was permanently unretrievable under the gate.
            payload.setdefault("domain_rights_status", "licensed")
            point = PointStruct(
                id=point_id,
                vector=vector_dict,
                payload=payload,
            )
            points.append(point)

        # Batch upsert in chunks of 200 (bumped from 100 — Task E2.6; safe for the
        # payload sizes used here: text + small meta per point).
        batch_size = 200
        for i in range(0, len(points), batch_size):
            batch = points[i : i + batch_size]
            self._client.upsert(
                collection_name=self._collection,
                points=batch,
            )

        logger.info(f"Upserted {len(points)} chunks to {self._collection}")
        return len(points)

    def check_source_exists(self, source_url: str) -> bool:
        """Check if any points with this source_url already exist (dedup check)."""
        try:
            results, _ = self._client.scroll(
                collection_name=self._collection,
                scroll_filter=Filter(
                    must=[FieldCondition(key="source_url", match=MatchValue(value=source_url))]
                ),
                limit=1,
                with_payload=False,
            )
            return len(results) > 0
        except Exception:
            return False

    def backup_source(self, source_url: str, backup_collection: str) -> bool:
        """
        Copy all points for a source to a backup collection.
        Acts as a safety net before re-processing.
        """
        try:
            # Ensure backup collection exists
            collections = [c.name for c in self._client.get_collections().collections]
            if backup_collection not in collections:
                source_config = self._client.get_collection(self._collection).config.params
                self._client.create_collection(
                    collection_name=backup_collection,
                    vectors_config=source_config.vectors,
                    sparse_vectors_config=source_config.sparse_vectors,
                )
                logger.info(f"Created backup collection: {backup_collection}")

            # Scroll all points for this source
            points, _ = self._client.scroll(
                collection_name=self._collection,
                scroll_filter=Filter(
                    must=[FieldCondition(key="source_url", match=MatchValue(value=source_url))]
                ),
                limit=1000,  # Sources rarely have more than 1000 chunks
                with_payload=True,
                with_vectors=True,
            )

            if not points:
                return False

            # Convert to PointStruct for upsert
            backup_points = []
            for p in points:
                backup_points.append(PointStruct(id=p.id, vector=p.vector, payload=p.payload))

            self._client.upsert(collection_name=backup_collection, points=backup_points)
            logger.info(
                f"Backed up {len(backup_points)} points for {source_url} to {backup_collection}"
            )
            return True
        except Exception as e:
            logger.error(f"Backup failed for {source_url}: {e}")
            return False

    def restore_from_backup(self, source_url: str, backup_collection: str) -> bool:
        """
        Restore a single source from a backup collection into the main collection.

        Iceberg-style rollback counterpart to backup_source(): deletes whatever is
        currently indexed for source_url in the main collection, then re-upserts the
        backed-up points. Used when a downstream step (RAPTOR, LightRAG, Neo4j
        consolidation) fails after a source has already been re-ingested, so a
        partially-processed source never gets left indexed.

        ponytail: promoted from scripts/migrate_data.py's standalone free function —
        single source of truth for restore logic instead of two copies.
        """
        try:
            self.delete_by_source(source_url)

            points, _ = self._client.scroll(
                collection_name=backup_collection,
                scroll_filter=Filter(
                    must=[FieldCondition(key="source_url", match=MatchValue(value=source_url))]
                ),
                limit=1000,
                with_payload=True,
                with_vectors=True,
            )

            if not points:
                logger.warning(f"No backup data found for {source_url} in {backup_collection}")
                return False

            restore_points = [
                PointStruct(id=p.id, vector=p.vector, payload=p.payload) for p in points
            ]
            self._client.upsert(collection_name=self._collection, points=restore_points)
            logger.info(f"Restored {len(restore_points)} points from backup for {source_url}")
            return True
        except Exception as e:
            logger.error(f"Restore failed for {source_url}: {e}")
            return False

    def prune_backups(self, prefix: str, max_backups: int = 5) -> None:
        """
        List all collections with the given prefix and keep only the last N.
        Deletes the oldest collections based on alphanumeric order (works with timestamps).
        """
        try:
            collections = [c.name for c in self._client.get_collections().collections]
            backups = sorted([c for c in collections if c.startswith(prefix)])

            if len(backups) > max_backups:
                to_delete = backups[: len(backups) - max_backups]
                for coll in to_delete:
                    logger.info(f"Pruning old backup collection: {coll}")
                    self._client.delete_collection(coll)
        except Exception as e:
            logger.error(f"Failed to prune backups: {e}")

    def delete_by_source(self, source_url: str) -> None:
        """Delete all points with a given source_url (for re-ingestion)."""
        try:
            self._client.delete(
                collection_name=self._collection,
                points_selector=FilterSelector(
                    filter=Filter(
                        must=[FieldCondition(key="source_url", match=MatchValue(value=source_url))]
                    )
                ),
            )
            logger.info(f"Deleted existing points for source: {source_url}")
        except Exception as e:
            logger.error(f"Failed to delete points for {source_url}: {e}")

    def get_all_texts(self, page_size: int = 10000) -> list[dict]:
        """Retrieve all stored texts with metadata via paginated scroll."""
        all_records = []
        offset = None

        while True:
            records, next_offset = self._client.scroll(
                collection_name=self._collection,
                limit=page_size,
                with_payload=True,
                with_vectors=False,
                offset=offset,
            )
            all_records.extend(records)

            if next_offset is None or len(records) == 0:
                break
            offset = next_offset

        return [
            {
                "text": r.payload.get("text", ""),
                "source_url": r.payload.get("source_url", ""),
                "title": r.payload.get("title", ""),
                "speaker": r.payload.get("speaker", "Unknown"),
                "topic": r.payload.get("topic", "Spiritual"),
                "chunk_index": r.payload.get("chunk_index", 0),
                "content_type": r.payload.get("content_type", ""),
                "raptor_level": r.payload.get("raptor_level", 0),
            }
            for r in all_records
        ]

    def count(self) -> int:
        """Get total number of indexed chunks."""
        info = self._client.get_collection(self._collection)
        return info.points_count
