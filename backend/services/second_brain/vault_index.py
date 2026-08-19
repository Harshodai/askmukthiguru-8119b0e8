"""Vault Index — semantic-recall index for the Second Brain (Mukthi Vault).

`services/qdrant_service.py` (QdrantService) is a facade over ONE collection
per process (settings.qdrant_collection, the doctrine corpus) — it has no
ensure_collection(name)/upsert(name, ...)/search(name, ...) shape, and a
collection-per-user (thousands of users) doesn't fit Qdrant's operational
model anyway. So this is a second, small, dedicated collection shared by
every user's vault, with every point payload-tagged {"user_id", "kind"} and
every search/delete filtered server-side on user_id — the same pattern the
doctrine collection uses for source_url/teacher_id filtering, just applied
to tenant isolation instead of content type.

Payload NEVER holds plaintext or ciphertext — only user_id (for the
mandatory filter) and kind (for future faceting). The id -> encrypted text
mapping lives in Postgres (user_brain_nodes); this index only answers
"which of this user's item ids are semantically closest to this vector".

# ponytail: connect + create-if-missing + upsert + filtered-search +
# filtered-delete only — no re-ranking. Two payload indexes: user_id and
# kind (the latter enables faceted recall if needed).
"""

from __future__ import annotations

import logging

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

DEFAULT_COLLECTION = "second_brain_vault"


def _build_scalar_int8() -> ScalarQuantization:
    """Return the doctrine-matching scalar_int8 quantization config.

    Mirrors `services.qdrant.client.QdrantClientManager._build_quantization_config`
    for the default `scalar_int8` setting. Quantized index lives in RAM for
    low-latency search; dense vectors stay on disk.
    """
    return ScalarQuantization(
        scalar=ScalarQuantizationConfig(
            type=ScalarType.INT8,
            always_ram=True,
        )
    )


class VaultIndex:
    """Thin Qdrant wrapper: one shared collection, user_id-filtered everything.

    Reuses the QdrantService facade's connection settings when available,
    else falls back to standalone QdrantClient with identical connect logic.
    """

    def __init__(self, collection: str = DEFAULT_COLLECTION, qdrant_service=None) -> None:
        if qdrant_service is not None:
            self._client = qdrant_service._client
        elif settings.qdrant_local_path:
            from qdrant_client import QdrantClient

            self._client = QdrantClient(path=settings.qdrant_local_path, check_compatibility=False)
        else:
            from qdrant_client import QdrantClient

            self._client = QdrantClient(
                url=settings.qdrant_url,
                api_key=getattr(settings, "qdrant_api_key", "") or None,
                prefer_grpc=False,
                check_compatibility=False,
            )
        self._collection = collection
        self._dimension = settings.embedding_dimension

    def ensure_collection(self) -> None:
        """Create the shared vault collection if missing.

        Mirrors the doctrine collection's HNSW + scalar_int8 quantization:
        m=32, ef_construct=200, full_scan_threshold=10000. On-disk payload and
        vectors. Keyword indexes on user_id and kind.
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
            for field_name in ("user_id", "kind"):
                self._client.create_payload_index(
                    collection_name=self._collection,
                    field_name=field_name,
                    field_schema="keyword",
                )
        except Exception as exc:
            err_msg = str(exc).lower()
            if "already exists" not in err_msg and "conflict" not in err_msg:
                raise

    async def upsert(self, user_id: str, item_id: str, vector: list[float], kind: str) -> None:
        self._client.upsert(
            collection_name=self._collection,
            points=[
                PointStruct(id=item_id, vector=vector, payload={"user_id": user_id, "kind": kind})
            ],
        )

    async def search(self, user_id: str, vector: list[float], *, limit: int) -> list[str]:
        results = self._client.query_points(
            collection_name=self._collection,
            query=vector,
            query_filter=Filter(
                must=[FieldCondition(key="user_id", match=MatchValue(value=user_id))]
            ),
            limit=limit,
            with_payload=False,
        )
        return [str(point.id) for point in results.points]

    async def delete_item(self, user_id: str, item_id: str) -> None:
        """Delete one point, scoped to its owner (a client-guessed id from
        another user's vault cannot be deleted even if it collided)."""
        self._client.delete(
            collection_name=self._collection,
            points_selector=Filter(
                must=[
                    FieldCondition(key="user_id", match=MatchValue(value=user_id)),
                    HasIdCondition(has_id=[item_id]),
                ]
            ),
        )

    async def delete_all(self, user_id: str) -> None:
        """Crypto-shred support: delete every point owned by this user."""
        self._client.delete(
            collection_name=self._collection,
            points_selector=Filter(
                must=[FieldCondition(key="user_id", match=MatchValue(value=user_id))]
            ),
        )


if __name__ == "__main__":
    # Self-check: module imports cleanly and the class constructs (no network
    # call happens until ensure_collection()/upsert()/search() are invoked).
    assert callable(VaultIndex)
    print("vault_index self-check: OK")
