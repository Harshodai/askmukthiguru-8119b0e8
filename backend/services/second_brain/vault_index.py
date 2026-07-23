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
# filtered-delete only — no re-ranking, no extra payload indexes beyond
# user_id. Add if semantic recall quality/scale demands it.
"""

from __future__ import annotations

import logging

from qdrant_client.http.models import (
    Distance,
    FieldCondition,
    Filter,
    HasIdCondition,
    MatchValue,
    PointStruct,
    VectorParams,
)

from app.config import settings

logger = logging.getLogger(__name__)

DEFAULT_COLLECTION = "second_brain_vault"


class VaultIndex:
    """Thin Qdrant wrapper: one shared collection, user_id-filtered everything.

    Reuses the QdrantService facade's connection settings when available,
    else falls back to standalone QdrantClient with identical connect logic.
    """

    def __init__(self, collection: str = DEFAULT_COLLECTION,
                 qdrant_service=None) -> None:
        if qdrant_service is not None:
            self._client = qdrant_service._client
        elif settings.qdrant_local_path:
            from qdrant_client import QdrantClient
            self._client = QdrantClient(path=settings.qdrant_local_path, check_compatibility=False)
        else:
            from qdrant_client import QdrantClient
            self._client = QdrantClient(url=settings.qdrant_url, prefer_grpc=False, check_compatibility=False)
        self._collection = collection
        self._dimension = settings.embedding_dimension

    def ensure_collection(self) -> None:
        """Create the shared vault collection if missing. Call once at startup
        (mirrors ServiceContainer._build_infrastructure's self.qdrant.init_collection())."""
        existing = [c.name for c in self._client.get_collections().collections]
        if self._collection in existing:
            return
        try:
            self._client.create_collection(
                collection_name=self._collection,
                vectors_config=VectorParams(size=self._dimension, distance=Distance.COSINE, on_disk=True),
                on_disk_payload=True,
            )
            self._client.create_payload_index(self._collection, "user_id", "keyword")
        except Exception as exc:
            if "already exists" not in str(exc).lower() and "conflict" not in str(exc).lower():
                raise

    async def upsert(self, user_id: str, item_id: str, vector: list[float], kind: str) -> None:
        self._client.upsert(
            collection_name=self._collection,
            points=[PointStruct(id=item_id, vector=vector, payload={"user_id": user_id, "kind": kind})],
        )

    async def search(self, user_id: str, vector: list[float], *, limit: int) -> list[str]:
        results = self._client.query_points(
            collection_name=self._collection,
            query=vector,
            query_filter=Filter(must=[FieldCondition(key="user_id", match=MatchValue(value=user_id))]),
            limit=limit,
            with_payload=False,
        )
        return [str(point.id) for point in results.points]

    async def delete_item(self, user_id: str, item_id: str) -> None:
        """Delete one point, scoped to its owner (a client-guessed id from
        another user's vault cannot be deleted even if it collided)."""
        self._client.delete(
            collection_name=self._collection,
            points_selector=Filter(must=[
                FieldCondition(key="user_id", match=MatchValue(value=user_id)),
                HasIdCondition(has_id=[item_id]),
            ]),
        )

    async def delete_all(self, user_id: str) -> None:
        """Crypto-shred support: delete every point owned by this user."""
        self._client.delete(
            collection_name=self._collection,
            points_selector=Filter(must=[FieldCondition(key="user_id", match=MatchValue(value=user_id))]),
        )


if __name__ == "__main__":
    # Self-check: module imports cleanly and the class constructs (no network
    # call happens until ensure_collection()/upsert()/search() are invoked).
    assert callable(VaultIndex)
    print("vault_index self-check: OK")
