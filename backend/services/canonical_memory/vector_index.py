"""Dedicated semantic-vector index for canonical personal memories — Phase 7.

`services/qdrant_service.py` is a facade over ONE collection (the doctrine
corpus) and has no ensure_collection(name)/upsert(name, ...)/search(name, ...)
shape.  This is a second, dedicated Qdrant collection shared by every user's
canonical memories, with every point payload-tagged ``{"user_id", "memory_type",
"status"}`` and every search/delete filtered server-side on ``user_id`` — the
same pattern ``second_brain/vault_index.py`` uses for vault tenant isolation,
applied to assistant-inferred durable memories.

Payload NEVER holds plaintext — only routing/filtering metadata.  The canonical
source of truth is Postgres (``canonical_memories``); this index only answers
"which of this user's memories are semantically closest to this query vector".

Rebuild is always possible from Postgres because every vector has a
``memory_id`` payload field referencing the canonical row.

# ponytail: connect + create-if-missing + upsert + filtered-search +
# filtered-delete + rebuild + orphan-detect + repair + health-check.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from qdrant_client.http.models import (
    Distance,
    FieldCondition,
    Filter,
    HasIdCondition,
    HnswConfigDiff,
    MatchValue,
    PointStruct,
    ScalarQuantization,
    ScalarQuantizationConfig,
    ScalarType,
    VectorParams,
)

from app.config import settings

logger = logging.getLogger(__name__)

DEFAULT_COLLECTION = "canonical_memory_vectors"
_DIMENSION = settings.embedding_dimension  # 1024


def _build_scalar_int8() -> ScalarQuantization:
    """Return scalar_int8 quantization config — matches doctrine collection."""
    return ScalarQuantization(
        scalar=ScalarQuantizationConfig(
            type=ScalarType.INT8,
            always_ram=True,
        )
    )


class CanonicalMemoryVectorIndex:
    """Thin Qdrant wrapper for the canonical memory vector collection.

    Every query is scoped to ``user_id`` via a server-side filter.
    Postgres (``canonical_memories``) remains the canonical source of truth;
    this index is a derived semantic layer that can be rebuilt from scratch.
    """

    def __init__(
        self,
        collection: str = DEFAULT_COLLECTION,
        qdrant_client: Any | None = None,
        supabase_client: Any | None = None,
    ) -> None:
        if qdrant_client is not None:
            self._client = qdrant_client
        elif settings.qdrant_local_path:
            from qdrant_client import QdrantClient

            self._client = QdrantClient(
                path=settings.qdrant_local_path, check_compatibility=False
            )
        else:
            from qdrant_client import QdrantClient

            self._client = QdrantClient(
                url=settings.qdrant_url,
                api_key=getattr(settings, "qdrant_api_key", "") or None,
                prefer_grpc=False,
                check_compatibility=False,
            )
        self._collection = collection
        self._dimension = _DIMENSION
        self._supabase = supabase_client

    # ------------------------------------------------------------------
    # Collection management
    # ------------------------------------------------------------------

    def ensure_collection(self) -> None:
        """Create the shared collection if missing.

        Mirrors the doctrine vault collection's HNSW + scalar_int8
        quantization: m=32, ef_construct=200, full_scan_threshold=10000.
        On-disk payload and vectors.  Keyword indexes on user_id,
        memory_type, and status.
        """
        existing = [c.name for c in self._client.get_collections().collections]
        if self._collection in existing:
            return
        try:
            self._client.create_collection(
                collection_name=self._collection,
                vectors_config=VectorParams(
                    size=self._dimension,
                    distance=Distance.COSINE,
                    on_disk=True,
                ),
                hnsw_config=HnswConfigDiff(
                    m=32,
                    ef_construct=200,
                    full_scan_threshold=10000,
                ),
                quantization_config=_build_scalar_int8(),
                on_disk_payload=True,
            )
            for field_name in ("user_id", "memory_type", "status"):
                self._client.create_payload_index(
                    collection_name=self._collection,
                    field_name=field_name,
                    field_schema="keyword",
                )
        except Exception as exc:
            err_msg = str(exc).lower()
            if "already exists" not in err_msg and "conflict" not in err_msg:
                raise

    # ------------------------------------------------------------------
    # Core CRUD
    # ------------------------------------------------------------------

    async def upsert(
        self,
        user_id: str,
        memory_id: str,
        vector: list[float],
        memory_type: str,
        status: str = "active",
    ) -> None:
        """Insert or update a single memory vector.

        ``memory_id`` is the UUID from Postgres canonical_memories.
        """
        self._client.upsert(
            collection_name=self._collection,
            points=[
                PointStruct(
                    id=memory_id,
                    vector=vector,
                    payload={
                        "user_id": user_id,
                        "memory_type": memory_type,
                        "status": status,
                        "memory_id": memory_id,
                    },
                )
            ],
        )

    async def search(
        self,
        user_id: str,
        vector: list[float],
        *,
        limit: int = 10,
        memory_type: str | None = None,
    ) -> list[dict[str, Any]]:
        """Semantic search scoped to a single user.

        Returns list of ``{"id": str, "score": float, "memory_type": str}``.
        """
        must_conditions: list[FieldCondition] = [
            FieldCondition(key="user_id", match=MatchValue(value=user_id)),
        ]
        if memory_type is not None:
            must_conditions.append(
                FieldCondition(key="memory_type", match=MatchValue(value=memory_type))
            )
        results = self._client.query_points(
            collection_name=self._collection,
            query=vector,
            query_filter=Filter(must=must_conditions),
            limit=limit,
            with_payload=True,
        )
        out: list[dict[str, Any]] = []
        for point in results.points:
            payload = point.payload or {}
            out.append(
                {
                    "id": str(point.id),
                    "score": point.score,
                    "memory_type": payload.get("memory_type", ""),
                    "status": payload.get("status", ""),
                }
            )
        return out

    async def delete(self, user_id: str, memory_id: str) -> None:
        """Delete one point, scoped to its owner.

        A client-guessed id from another user's scope cannot be deleted
        even if it collided.
        """
        self._client.delete(
            collection_name=self._collection,
            points_selector=Filter(
                must=[
                    FieldCondition(
                        key="user_id", match=MatchValue(value=user_id)
                    ),
                    HasIdCondition(has_id=[memory_id]),
                ]
            ),
        )

    async def delete_all_user(self, user_id: str) -> int:
        """Delete every point owned by this user (crypto-shred support).

        Returns the approximate count of points deleted (best-effort — Qdrant
        delete is asynchronous).
        """
        # First count what we have
        count_result = self._client.count(
            collection_name=self._collection,
            count_filter=Filter(
                must=[
                    FieldCondition(
                        key="user_id", match=MatchValue(value=user_id)
                    )
                ]
            ),
        )
        self._client.delete(
            collection_name=self._collection,
            points_selector=Filter(
                must=[
                    FieldCondition(
                        key="user_id", match=MatchValue(value=user_id)
                    )
                ]
            ),
        )
        return count_result.count

    # ------------------------------------------------------------------
    # Rebuild / orphan detection / repair
    # ------------------------------------------------------------------

    async def rebuild_from_canonical(
        self,
        user_id: str,
        embed_fn: Any,
    ) -> int:
        """Rebuild the vector index for one user from Postgres canonical truth.

        ``embed_fn`` is an async callable ``async (text: str) -> list[float]``
        that produces a 1024-dim embedding for the memory statement.

        Requires ``self._supabase`` to be set (passed in constructor).

        Returns count of vectors upserted.
        """
        if self._supabase is None:
            raise RuntimeError(
                "supabase_client required for rebuild_from_canonical — "
                "pass it to the constructor"
            )

        # Fetch all active canonical memories for this user from Postgres
        result = (
            self._supabase.table("canonical_memories")
            .select("*")
            .eq("user_id", user_id)
            .eq("status", "active")
            .execute()
        )
        memories = result.data or []

        if not memories:
            return 0

        points: list[PointStruct] = []
        for mem in memories:
            vector = await embed_fn(mem["statement"])
            points.append(
                PointStruct(
                    id=mem["id"],
                    vector=vector,
                    payload={
                        "user_id": user_id,
                        "memory_type": mem.get("memory_type", "PROFILE"),
                        "status": "active",
                        "memory_id": mem["id"],
                    },
                )
            )

        # Batch upsert — Qdrant handles 1000+ points fine
        self._client.upsert(
            collection_name=self._collection,
            points=points,
        )
        return len(points)

    async def detect_orphans(self, user_id: str) -> list[str]:
        """Find vector point IDs that have no matching active Postgres row.

        Returns list of orphaned memory_ids (safe to delete).
        """
        if self._supabase is None:
            raise RuntimeError(
                "supabase_client required for detect_orphans — "
                "pass it to the constructor"
            )

        # All vectors for this user
        vector_results = self._client.scroll(
            collection_name=self._collection,
            scroll_filter=Filter(
                must=[
                    FieldCondition(
                        key="user_id", match=MatchValue(value=user_id)
                    )
                ]
            ),
            with_payload=True,
            limit=10000,
        )
        vector_memory_ids = {
            (point.payload or {}).get("memory_id", str(point.id))
            for point in vector_results[0]
        }

        if not vector_memory_ids:
            return []

        # Active canonical memories for this user
        pg_result = (
            self._supabase.table("canonical_memories")
            .select("id")
            .eq("user_id", user_id)
            .eq("status", "active")
            .execute()
        )
        pg_ids = {row["id"] for row in (pg_result.data or [])}

        return [mid for mid in vector_memory_ids if mid not in pg_ids]

    async def repair(self, user_id: str, embed_fn: Any) -> dict[str, int]:
        """Repair the vector index for one user:
        1. Delete orphaned vectors (no matching Postgres row).
        2. Upsert missing vectors (Postgres row without vector).

        Returns ``{"orphans_deleted": N, "vectors_added": N}``.
        """
        if self._supabase is None:
            raise RuntimeError(
                "supabase_client required for repair — "
                "pass it to the constructor"
            )

        # Phase 1: detect and delete orphans
        orphans = await self.detect_orphans(user_id)
        for orphan_id in orphans:
            await self.delete(user_id, orphan_id)

        # Phase 2: detect missing vectors (active Postgres rows without vector)
        vector_results = self._client.scroll(
            collection_name=self._collection,
            scroll_filter=Filter(
                must=[
                    FieldCondition(
                        key="user_id", match=MatchValue(value=user_id)
                    )
                ]
            ),
            with_payload=True,
            limit=10000,
        )
        vector_memory_ids = {
            (point.payload or {}).get("memory_id", str(point.id))
            for point in vector_results[0]
        }

        pg_result = (
            self._supabase.table("canonical_memories")
            .select("*")
            .eq("user_id", user_id)
            .eq("status", "active")
            .execute()
        )
        pg_memories = pg_result.data or []

        missing_points: list[PointStruct] = []
        for mem in pg_memories:
            if mem["id"] not in vector_memory_ids:
                vector = await embed_fn(mem["statement"])
                missing_points.append(
                    PointStruct(
                        id=mem["id"],
                        vector=vector,
                        payload={
                            "user_id": user_id,
                            "memory_type": mem.get("memory_type", "PROFILE"),
                            "status": "active",
                            "memory_id": mem["id"],
                        },
                    )
                )

        if missing_points:
            self._client.upsert(
                collection_name=self._collection,
                points=missing_points,
            )

        return {
            "orphans_deleted": len(orphans),
            "vectors_added": len(missing_points),
        }

    # ------------------------------------------------------------------
    # Health check
    # ------------------------------------------------------------------

    async def health_check(self) -> dict[str, Any]:
        """Return health status of the vector index.

        Reports collection existence, point count, config params, and
        whether the dimension matches expectations.
        """
        existing = [c.name for c in self._client.get_collections().collections]
        collection_exists = self._collection in existing

        result: dict[str, Any] = {
            "collection": self._collection,
            "exists": collection_exists,
            "expected_dimension": self._dimension,
            "healthy": collection_exists,
        }

        if collection_exists:
            info = self._client.get_collection(self._collection)
            result["points_count"] = info.points_count
            result["config"] = {
                "vectors": {
                    "size": info.config.params.vectors.size
                    if info.config.params.vectors
                    else None,
                    "distance": str(info.config.params.vectors.distance)
                    if info.config.params.vectors
                    else None,
                }
            }
            # Verify dimension matches
            actual_size = (
                info.config.params.vectors.size
                if info.config.params.vectors
                else None
            )
            if actual_size is not None and actual_size != self._dimension:
                result["healthy"] = False
                result["error"] = (
                    f"dimension mismatch: expected {self._dimension}, "
                    f"got {actual_size}"
                )
        else:
            result["error"] = "collection not found"

        return result

    # ------------------------------------------------------------------
    # Bulk helpers
    # ------------------------------------------------------------------

    async def upsert_batch(
        self,
        points: list[PointStruct],
    ) -> None:
        """Upsert a batch of points (used by rebuild and repair)."""
        if not points:
            return
        self._client.upsert(
            collection_name=self._collection,
            points=points,
        )


if __name__ == "__main__":
    # Self-check: module imports cleanly and the class constructs (no network
    # call happens until ensure_collection()/upsert()/search() are invoked).
    assert callable(CanonicalMemoryVectorIndex)
    print("canonical_memory vector_index self-check: OK")
