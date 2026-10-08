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

import hashlib
import logging
import uuid
from typing import Any, Optional

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
# B.R0 (bake-off retrieve.py) fuses dense and sparse ranks (tuned to depth 30).
RRF_PREFETCH_DEPTH = 30

FIRST_PERSON_NAMESPACE = uuid.UUID("b3f9479e-4e67-4a0b-9d48-6a5814e5f7a2")

# Permitted speaker labels — strict allowlist. Anything else (including
# "both"/"unknown") is not a verified single-teacher recording and must never
# be indexed as first-person teaching.
from services.guru_registry import allowed_speaker_labels  # noqa: E402

ALLOWED_SPEAKERS = set(allowed_speaker_labels())  # config/gurus.yaml

# Canonical re-upload map: two YouTube IDs hosting the SAME audio discourse
# collapse to one identity at write time (audit LIVE_INDEX_QUALITY_2026-10-04
# §4: `9id3ygnEhh8` 2 pts vs `AQUZcU5L9xE` 1 pt, same transcript_hash).
# Point IDs are uuid5(transcript_hash, start_ms, end_ms) — video_id is NOT in
# the ID — so remapping video_id/group_id/source_url unifies serve-time
# identity (per-video dedup keys on video_id) at zero index churn.
# Direction: incumbent-majority (9id3ygnEhh8 already holds 2/3 live points);
# both URLs play identical audio, so direction is display-only.
# Residual: jittered spans (e.g. ±200 ms) still yield distinct point IDs —
# true point-level collapse needs span re-windowing (D2 span-provenance work:
# backend/ingest/pipeline.py timing resolvers, test_d2_span_provenance.py),
# which is out of scope for this write-path guard.
CANONICAL_VIDEO_IDS: dict[str, str] = {
    "AQUZcU5L9xE": "9id3ygnEhh8",
}


def canonical_video_id(video_id: str) -> str:
    """Map a re-uploaded YouTube ID to its canonical identity (no-op otherwise)."""
    return CANONICAL_VIDEO_IDS.get(video_id, video_id)


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
    if (
        not isinstance(t_hash, str)
        or len(t_hash) != 64
        or not all(c in "0123456789abcdefABCDEF" for c in t_hash)
    ):
        raise ValueError(f"transcript_hash must be a 64-char hex SHA-256 string, got '{t_hash}'")

    if clip["speaker"] not in ALLOWED_SPEAKERS:
        raise ValueError(
            f"speaker must be one of {sorted(ALLOWED_SPEAKERS)}, got '{clip['speaker']}'"
        )

    if not str(clip["verbatim_text"]).strip():
        raise ValueError("verbatim_text cannot be empty")
    expected_hash = hashlib.sha256(str(clip["verbatim_text"]).encode("utf-8")).hexdigest()
    if t_hash.casefold() != expected_hash:
        raise ValueError(
            "transcript_hash must equal sha256(verbatim_text.encode('utf-8')).hexdigest()"
        )
    if clip.get("first_person_eligible", True) is not True:
        raise ValueError("first_person_eligible must be true for indexed clips")
    if clip.get("provenance_kind") == "curated_okf":
        raise ValueError("curated OKF entries cannot be indexed as first-person clips")


def deduplicate_clips_by_video(
    results: list[dict[str, Any]],
    max_clips: int = 3,
    allow_same_video_distinct_spans: bool = False,
    min_span_gap_ms: int = 30_000,
) -> list[dict[str, Any]]:
    """
    Ensure no more than one clip per video is returned in the final result list,
    unless allow_same_video_distinct_spans is True. When True, allows up to 2
    clips from the same video IF they are disjoint by at least min_span_gap_ms (30s).
    # ponytail: allows pairing of a doctrine clip with a practical meditation clip from the same discourse.
    """
    video_clips: dict[str, list[dict[str, Any]]] = {}
    deduped: list[dict[str, Any]] = []

    for r in results:
        vid = r.get("video_id")
        if not vid:
            continue
        existing = video_clips.get(vid, [])
        if not existing:
            video_clips[vid] = [r]
            deduped.append(r)
            if len(deduped) >= max_clips:
                break
        elif allow_same_video_distinct_spans and len(existing) < 2:
            r_start = r.get("start_ms", 0)
            can_add = True
            for prev in existing:
                prev_start = prev.get("start_ms", 0)
                if abs(r_start - prev_start) < min_span_gap_ms:
                    can_add = False
                    break
            if can_add:
                video_clips[vid].append(r)
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
        ("first_person_eligible", "bool"),
        ("is_verbatim", "bool"),
        # Q-rec#1 (2026-10-04): search_hybrid filters rights_cleared==True on
        # EVERY query (:460-463) and points_servable reads it — it must be
        # indexed like every other filtered field. Additive, zero recall risk.
        # Stored values are JSON booleans, so the type must be bool: a keyword
        # index on a bool payload never fires (live: 0 indexed points).
        ("rights_cleared", "bool"),
        ("verbatim_text", "text"),
        ("question_text", "text"),
    ]

    def __init__(
        self,
        collection: Optional[str] = None,
        client: Optional[QdrantClient] = None,
        dimension: int = 1024,
    ) -> None:
        self._collection = collection or getattr(
            settings, "first_person_collection", self.DEFAULT_COLLECTION
        )
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
                "passage_sparse": SparseVectorParams(index=SparseIndexParams(on_disk=True))
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
        # Within-batch exact-duplicate guard (audit 2026-10-04 §4 fix #1):
        # same-video re-ingest jitter pairs share byte-identical text under
        # different spans. Key is (canonical video_id, cleaned verbatim_text)
        # so legitimate cross-video teaching repetition is preserved.
        # Cross-batch twins are OUT of scope here — index-level dedup owns them.
        seen_clip_keys: set[tuple[str, str]] = set()
        dupes_dropped = 0
        for i, clip in enumerate(clips):
            # Canonical re-upload identity (§4 fix #2): normalize before any
            # keying so twins share one video_id/group_id/source_url.
            canonical_vid = canonical_video_id(str(clip.get("video_id", "")))
            if canonical_vid != clip.get("video_id"):
                clip = dict(clip)
                old_vid = clip["video_id"]
                clip["video_id"] = canonical_vid
                if clip.get("group_id", old_vid) == old_vid:
                    clip["group_id"] = canonical_vid
                for url_key in ("source_url", "video_url"):
                    if old_vid in str(clip.get(url_key, "")):
                        clip[url_key] = str(clip[url_key]).replace(old_vid, canonical_vid)
                logger.info(f"[FirstPersonStore] remapped re-upload {old_vid} -> {canonical_vid}")

            # ponytail: clean ASR noise at ingestion time before storing into Qdrant
            from ingest.verbatim.asr_cleaner import clean_verbatim_text

            original_text = str(clip.get("verbatim_text", ""))
            cleaned_text = clean_verbatim_text(original_text)
            if original_text.strip() and not cleaned_text.strip():
                raise ValueError("ASR cleaner removed all text from a non-empty clip")
            if cleaned_text != original_text:
                clip = dict(clip)
                clip["verbatim_text"] = cleaned_text
                clip["transcript_hash"] = hashlib.sha256(cleaned_text.encode("utf-8")).hexdigest()

            # Enforce validation invariants
            validate_clip_entry(clip)

            dedupe_key = (str(clip["video_id"]), str(clip["verbatim_text"]))
            if dedupe_key in seen_clip_keys:
                dupes_dropped += 1
                continue
            seen_clip_keys.add(dedupe_key)

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
            if (
                question_dense_vectors
                and i < len(question_dense_vectors)
                and question_dense_vectors[i]
            ):
                named_vectors["question_dense"] = question_dense_vectors[i]

            if (
                passage_sparse_vectors
                and i < len(passage_sparse_vectors)
                and passage_sparse_vectors[i]
            ):
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
                "source_url": clip.get(
                    "source_url", f"https://www.youtube.com/watch?v={clip['video_id']}"
                ),
                "teacher_id": clip.get("teacher_id"),
                "teacher_ids": clip.get("teacher_ids"),
                "provenance_kind": clip.get("provenance_kind", "speech_turn_clip"),
                "quality_status": clip.get("quality_status", "verified_verbatim"),
                "first_person_eligible": clip.get("first_person_eligible", True),
                "is_verbatim": True,
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

        if dupes_dropped:
            logger.info(
                f"[FirstPersonStore] dropped {dupes_dropped} exact-duplicate "
                f"clip(s) within batch of {n} (kept first of each twin set)"
            )
        if not points:
            return 0

        # R2 / A-5 fail-closed write verification (audit 2026-09-29, plan Phase 1):
        # (1) every point ID must equal recomputation from the payload actually
        #     being written (uuid5(hash,start,end)); (2) the dense leg must match
        #     the declared dimension — never a silent drop or schema drift.
        for point in points:
            pl = point.payload
            recomputed = hashlib.sha256(str(pl["verbatim_text"]).encode("utf-8")).hexdigest()
            if str(pl["transcript_hash"]).casefold() != recomputed:
                raise ValueError(f"[R2] payload transcript_hash drift for point {point.id}")
            expected = make_first_person_point_id(
                pl["transcript_hash"], pl["start_ms"], pl["end_ms"]
            )
            if str(point.id) != expected:
                raise ValueError(f"[R2] point id {point.id} != recomputed {expected} from payload")
            dense = point.vector.get("passage_dense") if isinstance(point.vector, dict) else None
            if not dense or len(dense) != self._dimension:
                raise ValueError(
                    f"[R2] passage_dense dim {len(dense) if dense else 0} != "
                    f"{self._dimension} for point {point.id}"
                )

        self._client.upsert(
            collection_name=self._collection,
            points=points,
            wait=True,
        )

        # Read-back: sample first/last written points — dense vector + payload
        # must survive the write (catches silent named-vector drops, audit A-5).
        sample = points if len(points) <= 4 else points[:2] + points[-2:]
        readback = self._client.retrieve(
            collection_name=self._collection,
            ids=[str(p.id) for p in sample],
            with_payload=["transcript_hash"],
            with_vectors=["passage_dense"],
        )
        by_id = {str(r.id): r for r in readback}
        for p in sample:
            got = by_id.get(str(p.id))
            if got is None:
                raise ValueError(f"[R2] read-back missing point {p.id} after upsert")
            got_dense = (getattr(got, "vector", None) or {}).get("passage_dense")
            if not got_dense or len(got_dense) != self._dimension:
                raise ValueError(f"[R2] read-back passage_dense dim wrong for point {p.id}")
            if (got.payload or {}).get("transcript_hash") != p.payload["transcript_hash"]:
                raise ValueError(f"[R2] read-back payload drift for point {p.id}")

        logger.info(
            f"[FirstPersonStore] Successfully upserted {len(points)} clips into '{self._collection}'"
        )
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
        allow_same_video_distinct_spans: bool = False,
    ) -> list[dict[str, Any]]:
        """
        RRF hybrid search over passage_dense + passage_sparse (bake-off B.R0).
        Returns up to dedup_limit clips, max 1 per video_id (or up to 2 if distinct spans allowed).
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

        # Only passage_dense + passage_sparse are prefetched by default. question_dense
        # is enabled conditionally via settings.first_person_question_dense_enabled.
        prefetch_queries = [
            Prefetch(
                query=query_dense_vector,
                using="passage_dense",
                limit=max(limit * 2, RRF_PREFETCH_DEPTH),
                filter=search_filter,
            ),
        ]

        if getattr(settings, "first_person_question_dense_enabled", False):
            prefetch_queries.append(
                Prefetch(
                    query=query_dense_vector,
                    using="question_dense",
                    limit=max(limit, 20),
                    filter=search_filter,
                )
            )

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
            item["passage_dense"] = (
                raw_vector.get("passage_dense") if isinstance(raw_vector, dict) else None
            )
            formatted.append(item)

        # Enforce max 1 clip per video invariant (or up to 2 distinct spans if requested)
        return deduplicate_clips_by_video(
            formatted,
            max_clips=dedup_limit,
            allow_same_video_distinct_spans=allow_same_video_distinct_spans,
        )

    def count(self) -> int:
        """Return total points in collection."""
        res = self._client.count(collection_name=self._collection, exact=True)
        return res.count
