"""
Mukthi Guru — First-Person Verbatim Store (D3 / Versioned Store)

Implements the dedicated Qdrant collection for first-person verbatim teachings
(`first_person_v1`). Stores pointers to exact recorded words rather than LLM text.

Schema & Features:
  - Multi-vector support:
      * `passage_dense`: 1024d dense embedding of teacher's verbatim words
      * `question_dense`: 1024d dense embedding of paired host / offline questions
      * `passage_sparse`: Lexical sparse vector (BGE-M3)
  - Point IDs: Deterministic UUIDv5 based on (transcript_hash, start_ms, end_ms)
  - Invariants:
      * Host speech is strictly forbidden from first-person indexing
      * start_ms >= 0 and end_ms > start_ms
      * transcript_hash must be a valid 64-char SHA-256 hex string
      * Max 1 clip per video in search results (deduplication)
"""

from __future__ import annotations

import logging
from typing import Any, Optional
import uuid

from qdrant_client import QdrantClient
from qdrant_client.http.models import (
    Distance,
    FieldCondition,
    Filter,
    Fusion,
    FusionQuery,
    MatchValue,
    PointStruct,
    Prefetch,
    SparseIndexParams,
    SparseVector,
    SparseVectorParams,
    VectorParams,
)

from app.config import settings
from services.qdrant.client import QdrantClientManager

logger = logging.getLogger(__name__)

# Fixed namespace for deterministic UUIDv5 generation
# B.R0 (bake-off retrieve.py) fuses dense and sparse ranks at depth 60.
RRF_PREFETCH_DEPTH = 60

FIRST_PERSON_NAMESPACE = uuid.UUID("b3f9479e-4e67-4a0b-9d48-6a5814e5f7a2")

# Permitted speaker labels — strict allowlist. Anything else (including
# "both"/"unknown") is not a verified single-teacher recording and must never
# be indexed as first-person teaching.
ALLOWED_SPEAKERS = {
    "Sri Preethaji",
    "Sri Krishnaji",
}


def make_first_person_point_id(transcript_hash: str, start_ms: int, end_ms: int) -> str:
    """
    Generate a deterministic UUIDv5 point ID for a first-person clip.
    Guarantees idempotent upserts across pipeline retries.
    """
    key = f"{transcript_hash}:{start_ms}:{end_ms}"
    return str(uuid.uuid5(FIRST_PERSON_NAMESPACE, key))


def validate_clip_entry(clip: dict[str, Any]) -> None:
    """
    Validate first-person data invariants before indexing.
    Raises ValueError if any invariant is violated.
    """
    required_fields = [
        "video_id",
        "start_ms",
        "end_ms",
        "speaker",
        "transcript_hash",
        "verbatim_text",
    ]
    for field in required_fields:
        if field not in clip or clip[field] is None:
            raise ValueError(f"Missing required first-person field: '{field}'")

    if not isinstance(clip["start_ms"], int) or clip["start_ms"] < 0:
        raise ValueError(f"start_ms must be non-negative integer, got {clip['start_ms']}")

    if not isinstance(clip["end_ms"], int) or clip["end_ms"] <= clip["start_ms"]:
        raise ValueError(
            f"end_ms ({clip['end_ms']}) must be strictly greater than start_ms ({clip['start_ms']})"
        )

    t_hash = clip["transcript_hash"]
    if not isinstance(t_hash, str) or len(t_hash) != 64 or not all(c in "0123456789abcdefABCDEF" for c in t_hash):
        raise ValueError(f"transcript_hash must be a 64-char hex SHA-256 string, got '{t_hash}'")

    if clip["speaker"] not in ALLOWED_SPEAKERS:
        raise ValueError(
            f"speaker must be one of {sorted(ALLOWED_SPEAKERS)}, got '{clip['speaker']}'"
        )

    if not str(clip["verbatim_text"]).strip():
        raise ValueError("verbatim_text cannot be empty")


def deduplicate_clips_by_video(results: list[dict[str, Any]], max_clips: int = 3) -> list[dict[str, Any]]:
    """
    Ensure no more than one clip per video is returned in the final result list.
    """
    seen_videos: set[str] = set()
    deduped: list[dict[str, Any]] = []

    for r in results:
        vid = r.get("video_id")
        if vid and vid not in seen_videos:
            seen_videos.add(vid)
            deduped.append(r)
            if len(deduped) >= max_clips:
                break

    return deduped


class FirstPersonStore:
    """
    Vector storage and hybrid retrieval service for first-person verbatim teachings.
    """

    DEFAULT_COLLECTION = "first_person_v1"

    PAYLOAD_INDEXES: list[tuple[str, str]] = [
        ("video_id", "keyword"),
        ("start_ms", "integer"),
        ("end_ms", "integer"),
        ("speaker", "keyword"),
        ("transcript_hash", "keyword"),
        ("group_id", "keyword"),
        ("source_url", "keyword"),
        ("teacher_id", "keyword"),
        ("teacher_ids", "keyword"),
        ("provenance_kind", "keyword"),
        ("quality_status", "keyword"),
        ("first_person_eligible", "keyword"),
        ("verbatim_text", "text"),
        ("question_text", "text"),
    ]

    def __init__(
        self,
        collection: Optional[str] = None,
        client: Optional[QdrantClient] = None,
        dimension: int = 1024,
    ) -> None:
        self._collection = collection or getattr(settings, "first_person_collection", self.DEFAULT_COLLECTION)
        self._dimension = dimension or getattr(settings, "embedding_dimension", 1024)
        if client is not None:
            self._client = client
        else:
            self._client = QdrantClientManager().client

    @property
    def client(self) -> QdrantClient:
        return self._client

    @property
    def collection(self) -> str:
        return self._collection

    def init_collection(self) -> None:
        """
        Create the first_person_v1 collection with multi-vector configuration
        (passage_dense, question_dense, passage_sparse) and payload indexes.
        """
        existing = [c.name for c in self._client.get_collections().collections]
        if self._collection in existing:
            logger.info(f"[FirstPersonStore] Collection '{self._collection}' already exists.")
            return

        logger.info(f"[FirstPersonStore] Creating multi-vector collection '{self._collection}'")
        self._client.create_collection(
            collection_name=self._collection,
            vectors_config={
                "passage_dense": VectorParams(
                    size=self._dimension,
                    distance=Distance.COSINE,
                    on_disk=False,
                ),
                "question_dense": VectorParams(
                    size=self._dimension,
                    distance=Distance.COSINE,
                    on_disk=False,
                ),
            },
            sparse_vectors_config={
                "passage_sparse": SparseVectorParams(
                    index=SparseIndexParams(on_disk=True)
                )
            },
        )

        for field_name, schema_type in self.PAYLOAD_INDEXES:
            try:
                self._client.create_payload_index(
                    collection_name=self._collection,
                    field_name=field_name,
                    field_schema=schema_type,
                )
            except Exception as e:
                logger.warning(
                    f"[FirstPersonStore] Could not create index on {self._collection}.{field_name}: {e}"
                )

        logger.info(f"[FirstPersonStore] Successfully initialized collection '{self._collection}'")

    def upsert_clips(
        self,
        clips: list[dict[str, Any]],
        passage_dense_vectors: list[list[float]],
        question_dense_vectors: Optional[list[list[float]]] = None,
        passage_sparse_vectors: Optional[list[dict[str, Any]]] = None,
    ) -> int:
        """
        Validate and index clips into Qdrant using deterministic UUIDv5 point IDs.
        """
        if not clips:
            return 0

        n = len(clips)
        if len(passage_dense_vectors) != n:
            raise ValueError(
                f"Count mismatch: {n} clips but {len(passage_dense_vectors)} passage dense vectors"
            )

        points: list[PointStruct] = []
        for i, clip in enumerate(clips):
            # Enforce validation invariants
            validate_clip_entry(clip)

            point_id = make_first_person_point_id(
                transcript_hash=clip["transcript_hash"],
                start_ms=clip["start_ms"],
                end_ms=clip["end_ms"],
            )

            named_vectors: dict[str, Any] = {
                "passage_dense": passage_dense_vectors[i],
            }

            # Only set question_dense when a real question embedding exists —
            # a passage-dense fallback copy would double-count the passage in
            # RRF fusion against itself.
            if question_dense_vectors and i < len(question_dense_vectors) and question_dense_vectors[i]:
                named_vectors["question_dense"] = question_dense_vectors[i]

            if passage_sparse_vectors and i < len(passage_sparse_vectors) and passage_sparse_vectors[i]:
                sp = passage_sparse_vectors[i]
                indices = sp.get("indices", [])
                values = sp.get("values", [])
                if indices and values:
                    named_vectors["passage_sparse"] = SparseVector(
                        indices=indices,
                        values=values,
                    )

            # Construct safe payload. teacher_id/teacher_ids come from the
            # clip itself — a "both"/two-teacher default would misattribute
            # a single-speaker clip.
            payload = {
                "video_id": clip["video_id"],
                "start_ms": clip["start_ms"],
                "end_ms": clip["end_ms"],
                "speaker": clip["speaker"],
                "transcript_hash": clip["transcript_hash"],
                "group_id": clip.get("group_id", clip["video_id"]),
                "source_url": clip.get("source_url", f"https://www.youtube.com/watch?v={clip['video_id']}"),
                "teacher_id": clip.get("teacher_id"),
                "teacher_ids": clip.get("teacher_ids"),
                "provenance_kind": clip.get("provenance_kind", "speech_turn_clip"),
                "quality_status": clip.get("quality_status", "verified_verbatim"),
                "first_person_eligible": clip.get("first_person_eligible", True),
                "verbatim_text": clip["verbatim_text"],
                "question_text": clip.get("question_text", ""),
            }

            # Optional fields persisted only when present on the clip.
            for optional_key in (
                "display_text",
                "parent_id",
                "video_url",
                "duration_ms",
                "rights_cleared",
                "channel",
                "layer_sha256",
                "caption_status",
            ):
                if optional_key in clip:
                    payload[optional_key] = clip[optional_key]

            points.append(
                PointStruct(
                    id=point_id,
                    vector=named_vectors,
                    payload=payload,
                )
            )

        self._client.upsert(
            collection_name=self._collection,
            points=points,
            wait=True,
        )
        logger.info(f"[FirstPersonStore] Successfully upserted {len(points)} clips into '{self._collection}'")
        return len(points)

    def points_servable(self, point_ids: list[str]) -> bool:
        """True only if every point still exists and still passes the search filter
        (first_person_eligible, and rights_cleared unless unregistered serving is on)."""
        points = self.client.retrieve(
            collection_name=self.collection,
            ids=list(point_ids),
            with_payload=["first_person_eligible", "rights_cleared"],
            with_vectors=False,
        )
        if len(points) != len(set(point_ids)):
            return False
        need_rights = not getattr(settings, "first_person_serve_unregistered", False)
        return all(
            (p.payload or {}).get("first_person_eligible") is True
            and (not need_rights or (p.payload or {}).get("rights_cleared") is True)
            for p in points
        )

    def search_hybrid(
        self,
        query_dense_vector: list[float],
        query_sparse_vector: Optional[dict[str, Any]] = None,
        teacher_id: Optional[str] = None,
        limit: int = 10,
        dedup_limit: int = 3,
    ) -> list[dict[str, Any]]:
        """
        RRF hybrid search over passage_dense + passage_sparse (bake-off B.R0).
        Returns up to dedup_limit clips, max 1 per video_id.
        """
        # Build filter: only first_person_eligible (and, by default,
        # rights_cleared) points, optionally scoped to one teacher.
        must_conditions: list[FieldCondition] = [
            FieldCondition(key="first_person_eligible", match=MatchValue(value=True))
        ]
        if not getattr(settings, "first_person_serve_unregistered", False):
            must_conditions.append(
                FieldCondition(key="rights_cleared", match=MatchValue(value=True))
            )
        if teacher_id and teacher_id.lower() not in ("both", "all", ""):
            must_conditions.append(
                FieldCondition(key="teacher_id", match=MatchValue(value=teacher_id.lower()))
            )

        search_filter = Filter(must=must_conditions)

        # Only passage_dense + passage_sparse are prefetched. question_dense
        # is deliberately NOT prefetched here: today it is frequently a copy
        # of the passage vector (see upsert_clips), which would double-count
        # the same signal twice in RRF fusion.
        prefetch_queries = [
            Prefetch(
                query=query_dense_vector,
                using="passage_dense",
                limit=max(limit * 2, RRF_PREFETCH_DEPTH),
                filter=search_filter,
            ),
        ]

        if query_sparse_vector and query_sparse_vector.get("indices"):
            sp_vector = SparseVector(
                indices=query_sparse_vector["indices"],
                values=query_sparse_vector["values"],
            )
            prefetch_queries.append(
                Prefetch(
                    query=sp_vector,
                    using="passage_sparse",
                    limit=max(limit * 2, RRF_PREFETCH_DEPTH),
                    filter=search_filter,
                )
            )

        results = self._client.query_points(
            collection_name=self._collection,
            prefetch=prefetch_queries,
            query=FusionQuery(fusion=Fusion.RRF),
            limit=limit,
            with_payload=True,
            with_vectors=["passage_dense"],
        )

        formatted: list[dict[str, Any]] = []
        for p in results.points:
            item = dict(p.payload or {})
            item["point_id"] = str(p.id)
            item["score"] = float(p.score) if p.score is not None else 0.0
            raw_vector = getattr(p, "vector", None)
            item["passage_dense"] = raw_vector.get("passage_dense") if isinstance(raw_vector, dict) else None
            formatted.append(item)

        # Enforce max 1 clip per video invariant
        return deduplicate_clips_by_video(formatted, max_clips=dedup_limit)

    def count(self) -> int:
        """Return total points in collection."""
        res = self._client.count(collection_name=self._collection, exact=True)
        return res.count
