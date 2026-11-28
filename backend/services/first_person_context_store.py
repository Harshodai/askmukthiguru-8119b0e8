"""Qdrant adapter for the fp-context-v1 parent/child index.

Writes and reads are strict: every child payload is validated through
``domain.first_person_context.SourceSpan`` (``extra="forbid"``) before it is
returned to the harness, and a parent is only returned when its own record and
all requested children agree on ``parent_unit_id``, ``guru_id`` and
``corpus_version``.

Grouped retrieval uses Qdrant's ``query_points_groups`` when the installed
client exposes it and falls back to a bounded client-side grouping otherwise.
The fallback is deliberate: a missing grouping API must not silently change the
serving contract, and it must never widen the candidate set beyond the searched
window.
"""

from __future__ import annotations

import logging
import re
import uuid
from collections.abc import Iterable, Mapping, Sequence
from typing import Any, Optional, TypedDict, overload

from qdrant_client import QdrantClient
from qdrant_client.http.models import (
    FieldCondition,
    Filter,
    Fusion,
    FusionQuery,
    MatchAny,
    MatchValue,
    PointStruct,
    Prefetch,
    SparseVector,
)

from app.config import settings
from domain.first_person_context import (
    _VALIDATED_EDGE_ISSUE_TOKEN,
    BoundaryStatus,
    CompletenessStatus,
    ParentContext,
    ParentUnit,
    SourceSpan,
    SpeakerRole,
    ValidatedCrossParentEdge,
    _is_same_or_shared_guru,
    clip_text_hash,
)
from domain.speaker_provenance import (
    AUTOMATED_PROVENANCE_KEYS,
    HUMAN_REVIEW_KEYS,
    speaker_write_violations,
)
from ingest.verbatim.boundaries import boundary_defects
from services.first_person_rights import source_is_authoritatively_licensed
from services.first_person_video_decisions import blocked_video_ids_or_none, video_is_blocked
from services.guru_registry import canonical_guru_id
from services.text_quality_filter import find_artifact

logger = logging.getLogger(__name__)


def _normalize_sparse_query(query_sparse: Any) -> Optional[tuple[list[int], list[float]]]:
    """Normalize sparse vector input to (indices, values) regardless of dict format."""
    if not query_sparse:
        return None
    if isinstance(query_sparse, dict):
        if "indices" in query_sparse and "values" in query_sparse:
            try:
                indices = [int(i) for i in query_sparse["indices"]]
                values = [float(v) for v in query_sparse["values"]]
                if indices and values:
                    return indices, values
            except (ValueError, TypeError):
                return None
        else:
            try:
                indices = [int(k) for k in query_sparse.keys()]
                values = [float(v) for v in query_sparse.values()]
                if indices and values:
                    return indices, values
            except (ValueError, TypeError):
                return None
    return None


RECORD_TYPE_CHILD = "retrieval_child"
RECORD_TYPE_PARENT = "parent_unit"

_SERVABILITY_PAYLOAD_KEYS: tuple[str, ...] = (
    "record_type",
    "rights_cleared",
    "domain_rights_status",
    "speaker_role",
    "speaker_verified",
    "video_id",
    "speaker_id",
    "guru_id",
    "start_ms",
    "end_ms",
    "quality_status",
    "quarantine_reason",
    *AUTOMATED_PROVENANCE_KEYS,
    *HUMAN_REVIEW_KEYS,
)

_ADJACENCY_BLOCKING_BOUNDARY_DEFECTS = frozenset(
    {
        "head_orphan_punctuation",
        "head_headless_predicate",
        "head_conjunction",
        "head_fragment",
        "tail_dangling_word",
        "tail_severed_relative_clause",
    }
)
_ADJACENCY_DANGLING_CONJUNCTION_RE = re.compile(
    r"\b(or|and|so|but|because)\s*[.,;:!?…—–-]*$", re.IGNORECASE
)
_SEVERED_PREPOSITION_OPENER_RE = re.compile(
    r"^(?:for|in|of|to|with|as|if|at|on|by|from|into|onto|about|than|through)\s+",
    re.IGNORECASE,
)


class _PromiseClip(TypedDict):
    """Typed, minimal projection accepted by the canonical H4 helper."""

    video_id: str
    point_id: str
    id: str
    clip_id: str
    transcript_hash: str
    start_ms: int
    end_ms: int
    verbatim_text: str


def _span_promise_clip(span: SourceSpan) -> _PromiseClip:
    """Project a typed child into the canonical first-person H4 clip shape."""
    point_id = point_id_for_record(span.source_span_id)
    return {
        "video_id": span.video_id,
        "point_id": point_id,
        "id": point_id,
        "clip_id": point_id,
        "transcript_hash": span.transcript_hash,
        "start_ms": span.start_ms,
        "end_ms": span.end_ms,
        "verbatim_text": span.verbatim_text,
    }


def _span_is_blocked_promise(span: SourceSpan) -> bool:
    """Apply the canonical H4 predicate without importing the store at module load time."""
    # The local import keeps first_person_store -> service imports cycle-safe while ensuring
    # this path cannot drift from the write/pipeline promise predicate.
    from services.first_person_store import is_blocked_promise_clip

    return is_blocked_promise_clip(dict(_span_promise_clip(span)))


def _dense_cosine_similarity(a: Sequence[float], b: Sequence[float]) -> float:
    """Cosine similarity for Python-side dense rescoring of hybrid RRF groups."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = 0.0
    na = 0.0
    nb = 0.0
    for x, y in zip(a, b):
        fx = float(x)
        fy = float(y)
        dot += fx * fy
        na += fx * fx
        nb += fy * fy
    if na <= 0.0 or nb <= 0.0:
        return 0.0
    return dot / ((na**0.5) * (nb**0.5))


def _hit_dense_vector(hit: Any) -> Optional[list[float]]:
    vec = getattr(hit, "vector", None)
    if isinstance(vec, dict):
        v = vec.get("passage_dense")
        if isinstance(v, (list, tuple)) and v:
            return list(v)
    elif isinstance(vec, (list, tuple)) and vec:
        return list(vec)
    return None


def _group_hybrid_rescore(
    query_dense: list[float],
    hits: Sequence[Any],
    rrf_rank_idx: int,
) -> float:
    """Rank hybrid groups by dense semantic similarity with a bounded RRF tiebreaker.

    Prevents unselective sparse tokens (common verbs/nouns in BM25) from promoting
    low-similarity spans above strong (>=0.75) semantic matches while keeping genuine
    lexical coined-term matches competitive within the top candidate pool.
    """
    dense_scores: list[float] = []
    for h in hits:
        vec = _hit_dense_vector(h)
        if vec is not None and len(vec) == len(query_dense):
            dense_scores.append(_dense_cosine_similarity(query_dense, vec))
    if dense_scores:
        return max(dense_scores) + (0.015 / (1.0 + float(rrf_rank_idx)))
    return max(_ranking_score(h) for h in hits)


# Payload indexes required by the harness filters. Keep in sync with
# SourceSpan/ParentUnit fields; a missing keyword index makes a filtered search
# fall back to a full scan on large collections.
SPAN_INDEXES: tuple[tuple[str, str], ...] = (
    ("guru_id", "keyword"),
    ("video_id", "keyword"),
    ("ingest_namespace", "keyword"),
    ("parent_unit_id", "keyword"),
    ("source_span_id", "keyword"),
    ("record_type", "keyword"),
    ("speaker_id", "keyword"),
    ("speaker_role", "keyword"),
    ("speaker_verified", "bool"),
    ("rights_cleared", "bool"),
    ("domain_rights_status", "keyword"),
    ("embedding_model_family", "keyword"),  # C5
    ("is_verbatim", "bool"),
    ("boundary_status", "keyword"),
    ("completeness_status", "keyword"),
    ("provenance_kind", "keyword"),
    ("answer_role", "keyword"),
    ("corpus_version", "keyword"),
    ("start_ms", "integer"),
    ("end_ms", "integer"),
    # Graph/ontology tags carried by SourceSpan; the graph-expansion pass filters
    # children on these, so an unindexed field becomes a full scan.
    ("topic_ids", "keyword"),
    ("entity_ids", "keyword"),
    ("tags", "keyword"),
    ("category", "keyword"),
    ("facet_ids", "keyword"),
)


class FirstPersonContextStoreError(RuntimeError):
    """Raised when stored data violates the fp-context-v1 contract."""


def bare_flag_speaker_ids(payloads: Iterable[Mapping[str, Any]]) -> list[str]:
    """Child payloads that claim a verified speaker with no method that produced the claim.

    Works on raw payload dicts (the shape both builders write), not on ``SourceSpan``: a build
    must be refusable before any model validation, and the live collection already contains
    732 such points that must stay readable.
    """
    out: list[str] = []
    for payload in payloads:
        if payload.get("record_type") not in (None, RECORD_TYPE_CHILD):
            continue
        if (
            payload.get("speaker_verified") is True
            and not str(payload.get("voice_verification_method") or "").strip()
        ):
            out.append(str(payload.get("source_span_id") or payload.get("id") or "?"))
    return out


def assert_no_bare_flag_speakers(payloads: Iterable[Mapping[str, Any]], *, where: str) -> None:
    """Refuse a collection-level write that would promote label-only speaker claims (I3).

    ``FirstPersonContextStore.upsert`` refuses one span at a time; the builders write
    ``PointStruct`` batches directly and bypass it, so the collection needs its own gate. A
    non-zero count means the input was produced by an older builder that admitted a span on a
    v9 clip label alone (root cause of the 732 live points), and promoting it would ship the
    same defect into a new collection.
    """
    bad = bare_flag_speaker_ids(payloads)
    if bad:
        raise FirstPersonContextStoreError(
            f"{len(bad)} span(s) in {where} say speaker_verified=true with no "
            f"voice_verification_method (e.g. {bad[:3]}). Rebuild so a label-only span is "
            "written speaker_verified=false, or backfill a real method first "
            "(scripts.ops.backfill_v10_voice_method)."
        )


def speaker_provenance_violations(
    payloads: Iterable[Mapping[str, Any]],
) -> dict[str, list[str]]:
    """Child payloads the write rule would refuse, keyed by span id (empty means clean).

    The strict twin of :func:`bare_flag_speaker_ids`: it also catches a method with no
    score, calibration or reviewer behind it. For a promotion gate over a candidate
    collection; it reads raw payloads so a collection that still holds the 732 legacy spans
    can be *measured* without being loaded into ``SourceSpan``.
    """
    out: dict[str, list[str]] = {}
    for payload in payloads:
        if payload.get("record_type") not in (None, RECORD_TYPE_CHILD):
            continue
        violations = speaker_write_violations(payload)
        if violations:
            out[str(payload.get("source_span_id") or payload.get("id") or "?")] = violations
    return out


def assert_speaker_provenance(payloads: Iterable[Mapping[str, Any]], *, where: str) -> None:
    """Refuse a collection-level write holding any span the write rule would refuse (P3/P4).

    Stricter than :func:`assert_no_bare_flag_speakers`: a method with no score, calibration id
    or reviewer behind it is refused too. Builders call it on the exact payloads about to be
    sent; a non-zero count means a builder wrote a verified claim it cannot back.
    """
    bad = speaker_provenance_violations(payloads)
    if bad:
        sample = {k: v for k, v in list(bad.items())[:3]}
        raise FirstPersonContextStoreError(
            f"{len(bad)} span(s) in {where} claim speaker_verified=true without complete "
            f"provenance (e.g. {sample}). Rebuild so the span is written "
            "speaker_verified=false (pending_voice_check), or backfill real evidence first."
        )


# Qdrant point IDs must be UUIDs or unsigned ints; the contract IDs are sha256
# hex, so the point ID is a deterministic UUIDv5 of the contract ID.
_POINT_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_URL, "askmukthiguru/fp-context/v1")
_PARENT_PREFIX = "parent:"


def point_id_for_record(record_id: str) -> str:
    """Deterministic Qdrant point ID for a contract record ID."""
    return str(uuid.uuid5(_POINT_NAMESPACE, record_id))


def parent_point_id(parent_unit_id: str) -> str:
    return point_id_for_record(f"{_PARENT_PREFIX}{parent_unit_id}")


def _strip_record_type(payload: dict[str, Any]) -> dict[str, Any]:
    data = dict(payload)
    data.pop("record_type", None)
    data.pop("audio_start_ms", None)
    data.pop("audio_end_ms", None)
    data.pop("speaker", None)
    return data


def _clean_concept_ids(values: Optional[Sequence[str]]) -> list[str]:
    """Strip blanks and expand case variants (lower and title) plus constituent tokens
    so Qdrant keyword MatchAny reliably hits both topic_ids (lowercase) and entity_ids (capitalized)."""
    if not values:
        return []
    out: list[str] = []
    seen: set[str] = set()
    _STOP_WORDS = frozenset({"and", "the", "for", "with", "into", "from", "that", "this", "your"})
    for value in values:
        text = str(value).strip() if value is not None else ""
        if not text:
            continue
        variants = [text, text.lower(), text.title(), text.capitalize()]
        words = text.split()
        if len(words) > 1:
            for w in words:
                if len(w) >= 3 and w.lower() not in _STOP_WORDS:
                    variants.extend([w, w.lower(), w.title()])
        for var in variants:
            if var not in seen:
                seen.add(var)
                out.append(var)
    return out


_PROMO_PATTERN = re.compile(
    r"\b(congratulations|conquered|mystic secrets|available at|ekam online|course|challenge that you have conquered)\b",
    re.I,
)
_MEDITATION_DIRECTIVE_PATTERN = re.compile(
    r"\b(inhale|exhale|breath|breaths|breathe|breathing|palms|hands|eyes|thumbs|"
    r"first stage|second stage|third stage|fourth stage|fifth stage|humming|sound of a bee|aham)\b",
    re.I,
)


def _calculate_temporal_quality(hit: Any) -> float:
    base = float(getattr(hit, "score", 0.0) or 0.0)
    payload = getattr(hit, "payload", {}) or {}
    text = str(payload.get("verbatim_text") or "")
    start_ms = payload.get("start_ms")

    # 1. Promotional Outro Downweighting: heavily penalize course sales & congratulations
    if _PROMO_PATTERN.search(text):
        base *= 0.40

    # 2. Intro Banter Downweighting: discount conversational banter in the first 25s
    if isinstance(start_ms, (int, float)) and start_ms < 25000:
        base *= 0.65 + 0.35 * (max(0.0, float(start_ms)) / 25000.0)

    # 3. Direct Meditation / Practice Directive Boost
    if _MEDITATION_DIRECTIVE_PATTERN.search(text):
        base *= 1.25

    return base


def _ranking_score(hit: Any) -> float:
    """Return the raw score unless temporal quality is explicitly enabled."""
    if getattr(settings, "first_person_context_temporal_quality_enabled", False):
        return _calculate_temporal_quality(hit)
    return float(getattr(hit, "score", 0.0) or 0.0)


def deduplicate_contained_contexts(contexts: list[ParentContext]) -> list[ParentContext]:
    """Eliminate redundant contexts whose time intervals sit completely inside another context (RET-13)."""
    if len(contexts) <= 1:
        return contexts
    kept: list[ParentContext] = []
    for ctx in contexts:
        if not ctx.spans:
            continue
        c_video = getattr(ctx.spans[0], "video_id", None) or getattr(ctx.parent, "video_id", None)
        c_start = min(s.start_ms for s in ctx.spans)
        c_end = max(s.end_ms for s in ctx.spans)

        is_contained = False
        for k in kept:
            k_video = getattr(k.spans[0], "video_id", None) or getattr(k.parent, "video_id", None)
            if k_video and c_video and k_video == c_video:
                k_start = min(s.start_ms for s in k.spans)
                k_end = max(s.end_ms for s in k.spans)
                if k_start <= c_start and c_end <= k_end:
                    is_contained = True
                    break
        if not is_contained:
            kept.append(ctx)
    return kept


class FirstPersonContextStore:
    def __init__(
        self, client: QdrantClient, collection: str, *, check_health: bool = False
    ) -> None:
        self._client = client
        self._collection = collection
        if check_health:
            self._check_alias_health()

    def _check_alias_health(self) -> None:
        """Fail loudly if the (aliased) collection is empty or unreachable (C7).

        Prevents silent "0 candidates" abstains that look like retrieval-quality
        problems when an alias points at an empty or missing collection.

        Raises:
            FirstPersonContextStoreError: collection is empty or unreachable.
        """
        try:
            info = self._client.get_collection(self._collection)
            count = info.points_count or 0
        except Exception as exc:
            logger.error(
                "[FP-ALIAS-HEALTH] Cannot reach collection '%s': %s", self._collection, exc
            )
            raise FirstPersonContextStoreError(
                f"[FP-ALIAS-HEALTH] Cannot reach collection '{self._collection}': {exc}"
            ) from exc
        if count == 0:
            logger.error("[FP-ALIAS-HEALTH] Collection '%s' is empty.", self._collection)
            raise FirstPersonContextStoreError(
                f"[FP-ALIAS-HEALTH] Collection '{self._collection}' is empty. "
                "Check that the alias points to a live collection with data."
            )
        logger.info(
            "[FP-ALIAS-HEALTH] Collection '%s' healthy: %d points.", self._collection, count
        )

    @property
    def collection(self) -> str:
        return self._collection

    # ------------------------------------------------------------------ write
    def ensure_indexes(self) -> list[str]:
        """Create the payload indexes the harness filters depend on."""
        created: list[str] = []
        for key, schema in SPAN_INDEXES:
            try:
                self._client.create_payload_index(
                    collection_name=self._collection,
                    field_name=key,
                    field_schema=schema,
                    wait=True,
                )
                created.append(key)
            except Exception as exc:  # already exists / unsupported schema
                logger.debug("context store: index %s not created: %s", key, type(exc).__name__)
        return created

    def upsert(
        self,
        parent: ParentUnit,
        spans: Iterable[SourceSpan],
        vectors: Mapping[str, Any] | None = None,
    ) -> int:
        """Idempotent write of one parent plus its ordered children.

        Child points include their passage_dense/sparse vectors if provided in
        ``vectors`` (keyed by ``source_span_id``), or empty vectors when
        written payload-only.
        """
        span_list = list(spans)
        if not span_list:
            raise FirstPersonContextStoreError("cannot upsert a parent with no spans")
        if tuple(s.source_span_id for s in span_list) != parent.ordered_source_span_ids:
            raise FirstPersonContextStoreError("spans must be the parent's ordered_source_span_ids")
        for span in span_list:
            self._assert_belongs(parent, span)
            self._assert_verified_has_method(span)

        # Stamp canonical rights from the curated register; a SourceSpan's
        # caller-provided status is descriptive input, never the authority.
        from services.qdrant.indexer import resolve_source_rights_status

        points: list[PointStruct] = []
        for span in span_list:
            payload = span.to_payload()
            payload["domain_rights_status"] = resolve_source_rights_status(
                source_url=span.source_url,
                video_id=span.video_id,
            )
            points.append(
                PointStruct(
                    id=point_id_for_record(span.source_span_id),
                    vector=(vectors.get(span.source_span_id, {}) if vectors else {}),
                    payload=payload,
                )
            )
        points.append(
            PointStruct(
                id=parent_point_id(parent.parent_unit_id),
                vector={},
                payload=parent.to_payload(),
            )
        )
        self._client.upsert(collection_name=self._collection, points=points, wait=True)
        return len(points)

    @staticmethod
    def _assert_verified_has_method(span: SourceSpan) -> None:
        """A speaker claim is evidence only if the method that produced it is recorded.

        732 live v10 spans were written verified with no method (builder at a65f26b4); the
        rule existed only as a soft report in validate_release_grade(). Enforced at WRITE time
        and not in the SourceSpan validator, because the harness reads live payloads into
        SourceSpan and a model-level raise would crash on those 732 spans.

        The rule is shared with the backfill writer (``domain.speaker_provenance``): a method
        alone is not enough. An ECAPA span must carry its score, calibration id, model revision
        and the threshold in force, and a human listen must carry its reviewer, time and audio
        hash.
        """
        violations = speaker_write_violations(span.to_payload())
        if violations:
            raise FirstPersonContextStoreError(
                f"{violations[0]}: {span.source_span_id} (all: {', '.join(violations)})"
            )

    @staticmethod
    def _assert_belongs(parent: ParentUnit, span: SourceSpan) -> None:
        if span.parent_unit_id != parent.parent_unit_id:
            raise FirstPersonContextStoreError("span does not belong to parent")
        if not _is_same_or_shared_guru(span.guru_id, parent.guru_id):
            raise FirstPersonContextStoreError("span guru_id differs from parent")
        if span.video_id != parent.video_id:
            raise FirstPersonContextStoreError("span video_id differs from parent")
        if span.corpus_version != parent.corpus_version:
            raise FirstPersonContextStoreError("span corpus_version differs from parent")

    # ------------------------------------------------------------------- read
    def retrieve(
        self,
        query_dense: list[float],
        *,
        query_sparse: Optional[dict[str, Any]] = None,
        guru_id: Optional[str] = None,
        limit_parents: int = 16,
        spans_per_parent: int = 8,
        concept_ids: Optional[Sequence[str]] = None,
        span_ids: Optional[Sequence[str]] = None,
    ) -> list[ParentContext]:
        """Search children, group by parent, then hydrate whole parents.

        ``concept_ids`` narrows the candidate pool to graph-adjacent concepts:
        when it resolves to a non-empty list, a child is eligible only if its
        ``topic_ids`` or its ``entity_ids`` intersects those values. This is an
        additive filter for an extra pass at the call site — it is NOT a
        replacement for the unfiltered pass, because a span that carries no
        ontology tags would then never be retrieved. ``None`` or an empty /
        blank-only sequence leaves the filter byte-for-byte as before.
        """
        if limit_parents <= 0:
            return []
        if (
            isinstance(query_dense, (list, tuple))
            and query_dense
            and isinstance(query_dense[0], (list, tuple))
        ):
            query_dense = list(query_dense[0])
        conditions = [
            FieldCondition(key="record_type", match=MatchValue(value=RECORD_TYPE_CHILD)),
            FieldCondition(key="rights_cleared", match=MatchValue(value=True)),
            FieldCondition(key="domain_rights_status", match=MatchValue(value="licensed")),
        ]
        from app.config import settings

        require_speaker_verified = getattr(settings, "first_person_require_speaker_verified", False)
        if require_speaker_verified:
            conditions.append(FieldCondition(key="speaker_verified", match=MatchValue(value=True)))
        if guru_id and guru_id.lower() not in ("both", "all", ""):
            canonical = canonical_guru_id(guru_id) or guru_id.lower()
            conditions.append(FieldCondition(key="guru_id", match=MatchValue(value=canonical)))
        # Videos the owner rejected on the admin page are excluded here so they cannot crowd
        # real candidates out of the top-k. An invalid decisions file fails closed: no results.
        blocked_videos = blocked_video_ids_or_none()
        if blocked_videos is None:
            return []
        must_not = (
            [FieldCondition(key="video_id", match=MatchAny(any=sorted(blocked_videos)))]
            if blocked_videos
            else None
        )
        concepts = _clean_concept_ids(concept_ids)
        clean_spans = _clean_concept_ids(span_ids)
        should_conditions: list[FieldCondition] = []
        if concepts:
            should_conditions.extend(
                [
                    FieldCondition(key="topic_ids", match=MatchAny(any=concepts)),
                    FieldCondition(key="entity_ids", match=MatchAny(any=concepts)),
                    FieldCondition(key="tags", match=MatchAny(any=concepts)),
                ]
            )
        if clean_spans:
            should_conditions.append(
                FieldCondition(key="source_span_id", match=MatchAny(any=clean_spans))
            )

        if should_conditions:
            query_filter = Filter(
                must=conditions,
                must_not=must_not,
                should=should_conditions,
            )
        else:
            query_filter = Filter(must=conditions, must_not=must_not)

        # Single RRF-fused retrieval pass: when query_sparse is provided, the
        # _query_groups call already builds dense+sparse prefetches and applies
        # Fusion.RRF internally.  Doing two separate passes (dense-only then
        # hybrid) doubles the Qdrant round-trips and produces duplicate parent
        # candidates that must be deduped here.  One fused call is both cheaper
        # and more accurate (the ranker sees both signals simultaneously).
        groups = list(
            self._query_groups(
                query_dense,
                query_sparse=query_sparse,
                query_filter=query_filter,
                limit_parents=limit_parents,
                spans_per_parent=spans_per_parent,
            )
        )

        contexts: list[ParentContext] = []
        for parent_unit_id, hits, score in groups:
            try:
                context = self.fetch_parent_context(parent_unit_id, hits, score)
                teacher_spans = tuple(
                    span
                    for span in context.spans
                    if _is_same_or_shared_guru(span.guru_id, context.parent.guru_id)
                    and (span.speaker_verified is True if require_speaker_verified else True)
                )
                if not teacher_spans:
                    continue
                context = context.model_copy(update={"spans": teacher_spans})
                hit_ids = set(hits)
                hit_spans = [span for span in context.spans if span.source_span_id in hit_ids]
                if not hit_spans or any(
                    span.rights_cleared is not True
                    or not source_is_authoritatively_licensed(
                        source_url=span.source_url,
                        video_id=span.video_id,
                        domain_rights_status=span.domain_rights_status,
                    )
                    for span in context.spans
                ):
                    continue
                contexts.append(context)
                if len(contexts) >= limit_parents:
                    break
            except FirstPersonContextStoreError as exc:
                logger.warning(
                    "[ContextStore] dropping invalid parent context %s: %s", parent_unit_id, exc
                )
        return deduplicate_contained_contexts(contexts)

    def _query_groups(
        self,
        query_dense: list[float],
        *,
        query_sparse: Optional[dict[str, Any]] = None,
        query_filter: Filter,
        limit_parents: int,
        spans_per_parent: int,
    ) -> list[tuple[str, tuple[str, ...], float]]:
        parsed_sparse = _normalize_sparse_query(query_sparse)
        has_sparse = parsed_sparse is not None
        if hasattr(self._client, "query_points_groups"):
            try:
                if has_sparse:
                    prefetch_limit = max(limit_parents * spans_per_parent * 4, 80)
                    indices, values = parsed_sparse
                    sp_vector = SparseVector(
                        indices=indices,
                        values=values,
                    )
                    prefetch_queries = [
                        Prefetch(
                            query=query_dense,
                            using="passage_dense",
                            limit=prefetch_limit,
                            filter=query_filter,
                        ),
                        Prefetch(
                            query=sp_vector,
                            using="passage_sparse",
                            limit=prefetch_limit,
                            filter=query_filter,
                        ),
                    ]
                    response = self._client.query_points_groups(
                        collection_name=self._collection,
                        prefetch=prefetch_queries,
                        query=FusionQuery(fusion=Fusion.RRF),
                        group_by="parent_unit_id",
                        limit=max(limit_parents * 4, 32),
                        group_size=max(spans_per_parent, 8),
                        with_payload=["source_span_id", "start_ms", "end_ms", "verbatim_text"],
                        with_vectors=["passage_dense"],
                    )
                else:
                    response = self._client.query_points_groups(
                        collection_name=self._collection,
                        query=query_dense,
                        using="passage_dense",
                        query_filter=query_filter,
                        group_by="parent_unit_id",
                        limit=limit_parents * 3,
                        group_size=max(spans_per_parent, 8),
                        with_payload=["source_span_id", "start_ms", "end_ms", "verbatim_text"],
                    )
                out: list[tuple[str, tuple[str, ...], float]] = []
                for rank_idx, group in enumerate(getattr(response, "groups", []) or []):
                    hits = list(getattr(group, "hits", []) or [])
                    if not hits:
                        continue
                    span_ids = tuple(
                        str((hit.payload or {}).get("source_span_id") or hit.id) for hit in hits
                    )
                    score = (
                        _group_hybrid_rescore(query_dense, hits, rank_idx)
                        if has_sparse
                        else max(_ranking_score(h) for h in hits)
                    )
                    out.append((str(group.id), span_ids, score))
                if out:
                    out.sort(key=lambda item: item[2], reverse=True)
                    return out
            except Exception as exc:  # pragma: no cover - API/version dependent
                logger.debug("[ContextStore] grouped query unavailable: %s", type(exc).__name__)

        return self._group_in_python(
            query_dense,
            query_sparse=query_sparse,
            query_filter=query_filter,
            limit_parents=limit_parents,
            spans_per_parent=spans_per_parent,
        )

    def _group_in_python(
        self,
        query_dense: list[float],
        *,
        query_sparse: Optional[dict[str, Any]] = None,
        query_filter: Filter,
        limit_parents: int,
        spans_per_parent: int,
    ) -> list[tuple[str, tuple[str, ...], float]]:
        parsed_sparse = _normalize_sparse_query(query_sparse)
        has_sparse = parsed_sparse is not None
        if has_sparse:
            prefetch_limit = max(limit_parents * spans_per_parent * 4, 80)
            indices, values = parsed_sparse
            sp_vector = SparseVector(
                indices=indices,
                values=values,
            )
            prefetch_queries = [
                Prefetch(
                    query=query_dense,
                    using="passage_dense",
                    limit=prefetch_limit,
                    filter=query_filter,
                ),
                Prefetch(
                    query=sp_vector,
                    using="passage_sparse",
                    limit=prefetch_limit,
                    filter=query_filter,
                ),
            ]
            try:
                response = self._client.query_points(
                    collection_name=self._collection,
                    prefetch=prefetch_queries,
                    query=FusionQuery(fusion=Fusion.RRF),
                    limit=max(limit_parents * spans_per_parent * 4, 80),
                    with_payload=[
                        "parent_unit_id",
                        "source_span_id",
                        "start_ms",
                        "end_ms",
                        "verbatim_text",
                    ],
                    with_vectors=["passage_dense"],
                )
            except Exception as exc:  # noqa: BLE001 - a collection may have no sparse vector
                # The sparse lane is an addition, never a reason to fail retrieval: a
                # collection built before `passage_sparse` existed must still answer from
                # dense alone. Falling through here is what makes that promise true.
                logger.debug(
                    "[ContextStore] sparse prefetch unavailable; retrying dense-only: %s",
                    type(exc).__name__,
                )
                response = self._client.query_points(
                    collection_name=self._collection,
                    query=query_dense,
                    using="passage_dense",
                    query_filter=query_filter,
                    limit=limit_parents * spans_per_parent * 3,
                    with_payload=[
                        "parent_unit_id",
                        "source_span_id",
                        "start_ms",
                        "end_ms",
                        "verbatim_text",
                    ],
                )
        else:
            response = self._client.query_points(
                collection_name=self._collection,
                query=query_dense,
                using="passage_dense",
                query_filter=query_filter,
                limit=limit_parents * spans_per_parent * 3,
                with_payload=[
                    "parent_unit_id",
                    "source_span_id",
                    "start_ms",
                    "end_ms",
                    "verbatim_text",
                ],
            )
        hits = list(getattr(response, "points", []) or [])
        grouped: dict[str, list[Any]] = {}
        for hit in hits:
            parent_id = str((hit.payload or {}).get("parent_unit_id") or "")
            if not parent_id:
                continue
            bucket = grouped.setdefault(parent_id, [])
            if len(bucket) < spans_per_parent:
                bucket.append(hit)
        out = [
            (
                parent_id,
                tuple(str((hit.payload or {}).get("source_span_id") or hit.id) for hit in bucket),
                _group_hybrid_rescore(query_dense, bucket, rank_idx)
                if has_sparse
                else max(_ranking_score(hit) for hit in bucket),
            )
            for rank_idx, (parent_id, bucket) in enumerate(grouped.items())
        ]
        out.sort(key=lambda item: item[2], reverse=True)
        return out

    def fetch_parent_context(
        self,
        parent_unit_id: str,
        hit_span_ids: Iterable[str],
        score: float = 0.0,
    ) -> ParentContext:
        parent_record = self._get_record(parent_point_id(parent_unit_id))
        if parent_record is None:
            raise FirstPersonContextStoreError("parent record missing")
        payload = _strip_record_type(parent_record.payload or {})
        try:
            parent = ParentUnit.model_validate(payload)
        except Exception as exc:
            raise FirstPersonContextStoreError(f"invalid parent payload: {exc}") from exc
        if parent.parent_unit_id != parent_unit_id:
            raise FirstPersonContextStoreError("parent payload id mismatch")

        records = self._scroll_children(parent_unit_id)
        by_id: dict[str, dict[str, Any]] = {}
        for record in records:
            record_payload = _strip_record_type(record.payload or {})
            span_id = record_payload.get("source_span_id")
            if not span_id:
                raise FirstPersonContextStoreError("child payload missing source_span_id")
            if str(record.id) != point_id_for_record(str(span_id)):
                raise FirstPersonContextStoreError(f"point id does not match span id {span_id}")
            if str(span_id) in by_id:
                raise FirstPersonContextStoreError(f"duplicate child span id {span_id}")
            by_id[str(span_id)] = record_payload

        missing = [sid for sid in parent.ordered_source_span_ids if sid not in by_id]
        if missing:
            raise FirstPersonContextStoreError(
                f"{len(missing)} ordered span(s) missing from the index"
            )
        extra = [span_id for span_id in by_id if span_id not in parent.ordered_source_span_ids]
        if extra:
            raise FirstPersonContextStoreError(
                f"{len(extra)} child span(s) are not listed by the parent"
            )

        spans: list[SourceSpan] = []
        for span_id in parent.ordered_source_span_ids:
            try:
                span = SourceSpan.model_validate(_strip_record_type(by_id[span_id]))
            except Exception as exc:
                raise FirstPersonContextStoreError(
                    f"invalid span payload {span_id}: {exc}"
                ) from exc
            self._assert_belongs(parent, span)
            spans.append(span)

        for previous, current in zip(spans, spans[1:]):
            if (
                current.start_ms < previous.start_ms
                or current.source_span_index <= previous.source_span_index
            ):
                raise FirstPersonContextStoreError(
                    "parent ordered spans are not strictly chronological by "
                    "start_ms and source_span_index"
                )

        for span in spans:
            if span.start_ms < parent.start_ms or span.end_ms > parent.end_ms:
                raise FirstPersonContextStoreError(
                    f"span {span.source_span_id} falls outside parent bounds"
                )

        expected_parent_hash = clip_text_hash(" ".join(span.verbatim_text for span in spans))
        if parent.parent_text_hash != expected_parent_hash:
            raise FirstPersonContextStoreError(
                "parent_text_hash does not match ordered verbatim text"
            )

        returned_hits = tuple(hit_span_ids) or (spans[0].source_span_id,)
        return ParentContext(
            parent=parent,
            spans=tuple(spans),
            hit_span_ids=returned_hits,
            score=score,
        )

    @overload
    def enrich_to_parent_window(self, context_or_parent_id: ParentContext) -> ParentContext: ...

    @overload
    def enrich_to_parent_window(
        self, context_or_parent_id: str, span_id: str, window_size: int = 1
    ) -> list[SourceSpan]: ...

    def enrich_to_parent_window(
        self,
        context_or_parent_id: ParentContext | str,
        span_id: str | None = None,
        window_size: int = 1,
    ) -> ParentContext | list[SourceSpan]:
        """Re-hydrate a context or fetch surrounding spans of its parent unit (RAG-2).

        When called with (context: ParentContext), re-hydrates the ParentContext to
        all spans of its parent unit.
        When called with (parent_unit_id: str, span_id: str, window_size: int), returns
        a list[SourceSpan] centered on span_id with +- window_size adjacent spans.

        Raises FirstPersonContextStoreError when the stored parent/child records
        violate the fp-context-v1 contract.
        """
        from app.metrics import ENRICHMENT_WINDOW_EXPANSIONS_TOTAL

        # Case A: (parent_unit_id: str, span_id: str, window_size: int = 1)
        if isinstance(context_or_parent_id, str):
            parent_unit_id = context_or_parent_id
            target_span_id = span_id or ""
            # "No such span" is answered from the parent record WITHOUT a
            # hydration attempt: passing an unknown id into fetch_parent_context
            # raises the contract validator ("hit_span_ids must all be present in
            # spans"), which made an ordinary not-found indistinguishable from a
            # real index defect.
            try:
                parent_record = self._get_record(parent_point_id(parent_unit_id))
            except Exception as exc:
                raise FirstPersonContextStoreError(f"parent read failed: {exc}") from exc
            if parent_record is None:
                raise FirstPersonContextStoreError("parent record missing")
            try:
                parent_unit = ParentUnit.model_validate(
                    _strip_record_type(parent_record.payload or {})
                )
            except Exception as exc:
                raise FirstPersonContextStoreError(f"invalid parent payload: {exc}") from exc
            if target_span_id not in parent_unit.ordered_source_span_ids:
                ENRICHMENT_WINDOW_EXPANSIONS_TOTAL.labels(outcome="not_found").inc()
                return []
            try:
                parent_context = self.fetch_parent_context(parent_unit_id, [target_span_id])
                ordered_spans = list(parent_context.spans)
                hit_idx = next(
                    (i for i, s in enumerate(ordered_spans) if s.source_span_id == target_span_id),
                    None,
                )
                if hit_idx is None:
                    ENRICHMENT_WINDOW_EXPANSIONS_TOTAL.labels(outcome="not_found").inc()
                    return []
                start = max(0, hit_idx - window_size)
                end = min(len(ordered_spans), hit_idx + window_size + 1)
                result_spans = ordered_spans[start:end]
                if len(result_spans) > 1:
                    ENRICHMENT_WINDOW_EXPANSIONS_TOTAL.labels(outcome="expanded").inc()
                else:
                    ENRICHMENT_WINDOW_EXPANSIONS_TOTAL.labels(outcome="noop").inc()
                return result_spans
            except FirstPersonContextStoreError:
                ENRICHMENT_WINDOW_EXPANSIONS_TOTAL.labels(outcome="error").inc()
                raise
            except Exception as exc:
                # A transient read error is NOT "this parent has no such span".
                # Returning [] made the two states indistinguishable; the caller
                # (and any future one) must be able to tell a real empty window
                # from a failed read, so the failure is raised with its cause.
                logger.warning(
                    "[ContextStore] enrich_to_parent_window read failed for %s: %s",
                    parent_unit_id,
                    exc,
                )
                ENRICHMENT_WINDOW_EXPANSIONS_TOTAL.labels(outcome="error").inc()
                raise FirstPersonContextStoreError(
                    f"enrichment window read failed for parent {parent_unit_id!r}: {exc}"
                ) from exc

        # Case B: (context: ParentContext)
        context = context_or_parent_id
        # Reuses the single hydration path (fetch_parent_context) so there is no
        # second place that can diverge from the contract checks.
        try:
            widened = self.fetch_parent_context(
                context.parent.parent_unit_id,
                context.hit_span_ids,
                context.score,
            )
        except FirstPersonContextStoreError:
            ENRICHMENT_WINDOW_EXPANSIONS_TOTAL.labels(outcome="error").inc()
            raise
        except Exception as exc:  # a transient read error must not lose the hit
            logger.debug(
                "[ContextStore] enrichment re-hydration failed for %s: %s",
                context.parent.parent_unit_id,
                type(exc).__name__,
            )
            ENRICHMENT_WINDOW_EXPANSIONS_TOTAL.labels(outcome="error").inc()
            return context

        original_ids = {s.source_span_id for s in context.spans}
        widened_ids = {s.source_span_id for s in widened.spans}
        if len(widened_ids) <= len(original_ids) or not original_ids <= widened_ids:
            logger.debug(
                "[ContextStore] enrichment window did not widen %s (%d -> %d span(s))",
                context.parent.parent_unit_id,
                len(original_ids),
                len(widened_ids),
            )
            ENRICHMENT_WINDOW_EXPANSIONS_TOTAL.labels(outcome="noop").inc()
            return context
        logger.debug(
            "[ContextStore] enrichment window widened %s: %d -> %d span(s)",
            context.parent.parent_unit_id,
            len(original_ids),
            len(widened_ids),
        )
        ENRICHMENT_WINDOW_EXPANSIONS_TOTAL.labels(outcome="expanded").inc()
        return widened

    def fetch_preceding_span(
        self, current_span: SourceSpan | str, before_start_ms: int | None = None
    ) -> Optional[SourceSpan | ValidatedCrossParentEdge]:
        """Return the validated immediate previous sibling of ``current_span``.

        The two-argument ``(video_id, before_start_ms)`` form remains accepted as a
        compatibility shim for callers not yet migrated to typed adjacency; it returns
        ``None`` rather than performing the old video-wide timestamp scan.
        """
        if not isinstance(current_span, SourceSpan) or before_start_ms is not None:
            return None
        return self._fetch_adjacent_span(current_span, direction=-1)

    def fetch_succeeding_span(
        self, current_span: SourceSpan | str, after_end_ms: int | None = None
    ) -> Optional[SourceSpan]:
        """Return the validated immediate next sibling of ``current_span``.

        The two-argument ``(video_id, after_end_ms)`` form remains accepted as a
        compatibility shim for callers not yet migrated to typed adjacency; it returns
        ``None`` rather than performing the old video-wide timestamp scan.
        """
        if not isinstance(current_span, SourceSpan) or after_end_ms is not None:
            return None
        return self._fetch_adjacent_span(current_span, direction=1)

    def _fetch_adjacent_span(
        self, current_span: SourceSpan, *, direction: int
    ) -> Optional[SourceSpan | ValidatedCrossParentEdge]:
        """Resolve one adjacent child through the validated parent ordering only."""
        if direction not in (-1, 1):
            return None
        if not self._adjacency_span_is_servable(current_span):
            return None
        try:
            context = self.fetch_parent_context(
                current_span.parent_unit_id,
                [current_span.source_span_id],
            )
        except (FirstPersonContextStoreError, TypeError, ValueError) as exc:
            logger.debug(
                "[ContextStore] adjacency parent hydration failed for %s: %s",
                current_span.source_span_id,
                type(exc).__name__,
            )
            return None

        by_id = {span.source_span_id: span for span in context.spans}
        stored_current = by_id.get(current_span.source_span_id)
        if stored_current is None or stored_current != current_span:
            return None
        if not context.parent.speaker_continuity:
            return None
        if stored_current.speaker_id not in context.parent.speaker_ids:
            return None

        ordered_ids = context.parent.ordered_source_span_ids
        try:
            current_index = ordered_ids.index(stored_current.source_span_id)
        except ValueError:
            return None
        adjacent_index = current_index + direction
        if adjacent_index < 0:
            if direction < 0:
                return self._fetch_cross_parent_predecessor(current_span, context)
            return None
        if adjacent_index >= len(ordered_ids):
            return None
        adjacent = by_id.get(ordered_ids[adjacent_index])
        if adjacent is None or adjacent.source_span_id == stored_current.source_span_id:
            return None
        if not self._adjacency_span_is_servable(adjacent):
            return None
        if (
            adjacent.parent_unit_id != stored_current.parent_unit_id
            or adjacent.video_id != stored_current.video_id
            or adjacent.guru_id != stored_current.guru_id
            or adjacent.corpus_version != stored_current.corpus_version
            or adjacent.speaker_id != stored_current.speaker_id
        ):
            return None
        if not self._adjacent_coordinates_are_chronological(
            stored_current, adjacent, direction=direction
        ):
            return None

        expected_pointer = (
            stored_current.previous_span_id if direction < 0 else stored_current.next_span_id
        )
        if expected_pointer != adjacent.source_span_id:
            return None
        reciprocal_pointer = adjacent.next_span_id if direction < 0 else adjacent.previous_span_id
        if reciprocal_pointer != stored_current.source_span_id:
            return None
        return adjacent

    def _fetch_cross_parent_predecessor(
        self, current_span: SourceSpan, current_context: ParentContext
    ) -> Optional[ValidatedCrossParentEdge]:
        """Resolve the one authorized cross-parent antecedent edge.

        The predecessor is addressed by the opener's typed ``previous_span_id``;
        this intentionally never searches a video by timestamp.  Both parent
        records are hydrated completely before the edge is accepted, so the
        returned child is necessarily the last ordered child of its parent and
        the opener is the first ordered child of the current parent.
        """
        current_parent = current_context.parent
        if not current_context.spans or current_context.spans[0] != current_span:
            return None
        predecessor_id = current_span.previous_span_id
        if not predecessor_id:
            return None

        predecessor_record = self._get_record(point_id_for_record(predecessor_id))
        if predecessor_record is None:
            return None
        predecessor_payload = _strip_record_type(predecessor_record.payload or {})
        if predecessor_payload.get("source_span_id") != predecessor_id:
            return None
        if str(predecessor_record.id) != point_id_for_record(predecessor_id):
            return None
        predecessor_parent_id = str(predecessor_payload.get("parent_unit_id") or "")
        if not predecessor_parent_id or predecessor_parent_id == current_parent.parent_unit_id:
            return None

        try:
            previous_context = self.fetch_parent_context(predecessor_parent_id, [predecessor_id])
        except (FirstPersonContextStoreError, TypeError, ValueError) as exc:
            logger.debug(
                "[ContextStore] cross-parent predecessor hydration failed for %s: %s",
                predecessor_id,
                type(exc).__name__,
            )
            return None
        if not previous_context.spans:
            return None
        predecessor = previous_context.spans[-1]
        opener = current_context.spans[0]
        # A cross-parent capability is issued only from two complete parent records.  Child
        # hydration may contain FRAGMENT spans (the opener is allowed to be completed by its
        # predecessor), but uncertainty anywhere in either hydrated child set is fail-closed.
        if (
            previous_context.parent.completeness_status is not CompletenessStatus.COMPLETE
            or current_parent.completeness_status is not CompletenessStatus.COMPLETE
            or any(
                span.completeness_status is CompletenessStatus.UNCERTAIN
                for span in (*previous_context.spans, *current_context.spans)
            )
            or predecessor.completeness_status is not CompletenessStatus.COMPLETE
        ):
            return None
        if predecessor.source_span_id != predecessor_id:
            return None
        if previous_context.parent.ordered_source_span_ids[-1] != predecessor_id:
            return None
        if current_parent.ordered_source_span_ids[0] != opener.source_span_id:
            return None
        if (
            opener.previous_span_id != predecessor.source_span_id
            or predecessor.next_span_id != opener.source_span_id
        ):
            return None
        if (
            not previous_context.parent.speaker_continuity
            or not current_parent.speaker_continuity
            or previous_context.parent.boundary_status is BoundaryStatus.UNCERTAIN
            or current_parent.boundary_status is BoundaryStatus.UNCERTAIN
        ):
            return None
        if not all(
            self._adjacency_span_is_servable(span)
            for span in (*previous_context.spans, *current_context.spans)
        ):
            return None
        if {span.speaker_id for span in previous_context.spans} != {predecessor.speaker_id} or {
            span.speaker_id for span in current_context.spans
        } != {opener.speaker_id}:
            return None
        if predecessor.speaker_id not in previous_context.parent.speaker_ids:
            return None
        if opener.speaker_id not in current_parent.speaker_ids:
            return None
        if (
            predecessor.parent_unit_id == opener.parent_unit_id
            or predecessor.video_id != opener.video_id
            or predecessor.guru_id != opener.guru_id
            or predecessor.corpus_version != opener.corpus_version
            or predecessor.source_asset_id != opener.source_asset_id
            or predecessor.speaker_id != opener.speaker_id
        ):
            return None
        if predecessor.end_ms > opener.start_ms:
            return None
        if predecessor.word_end > opener.word_start:
            return None
        if previous_context.parent.end_ms > current_parent.start_ms:
            return None
        # ValidatedCrossParentEdge certifies bounded adjacency and deterministic evidence
        # integrity, not final response authorization. Its sole consumer must still pass
        # FirstPersonPipeline's selected-response gates before any answer is served.
        return ValidatedCrossParentEdge._issue(
            predecessor,
            opener,
            predecessor_parent_end_ms=previous_context.parent.end_ms,
            opener_parent_start_ms=current_parent.start_ms,
            issue_token=_VALIDATED_EDGE_ISSUE_TOKEN,
        )

    @staticmethod
    def _adjacency_span_is_servable(span: SourceSpan) -> bool:
        """Apply the narrow fail-closed gates required for sibling stitching."""
        from app.config import settings

        require_speaker_verified = getattr(settings, "first_person_require_speaker_verified", False)
        if (
            span.speaker_role not in (SpeakerRole.GURU, SpeakerRole.TEACHER)
            or (require_speaker_verified and span.speaker_verified is not True)
            or span.rights_cleared is not True
            or not source_is_authoritatively_licensed(
                source_url=span.source_url,
                video_id=span.video_id,
                domain_rights_status=span.domain_rights_status,
            )
            or span.is_verbatim is not True
            or span.boundary_status is BoundaryStatus.UNCERTAIN
        ):
            return False
        if FirstPersonContextStore._span_is_quarantined(span) or video_is_blocked(span.video_id):
            return False
        if _span_is_blocked_promise(span):
            return False
        if require_speaker_verified and speaker_write_violations(span.to_payload()):
            return False
        if clip_text_hash(span.verbatim_text) != span.source_text_hash:
            return False
        if find_artifact(span.verbatim_text) is not None:
            return False
        if _ADJACENCY_DANGLING_CONJUNCTION_RE.search(span.verbatim_text):
            return False
        defects = set(boundary_defects(span.verbatim_text.split()))
        if defects.intersection(_ADJACENCY_BLOCKING_BOUNDARY_DEFECTS):
            return False
        tokens = span.verbatim_text.split()
        # Keep this byte-for-byte equivalent to the canonical pipeline integrity condition:
        # only a lowercase token opening on a configured preposition is a severed opener.
        if (
            tokens
            and tokens[0][0].islower()
            and _SEVERED_PREPOSITION_OPENER_RE.match(span.verbatim_text.strip())
        ):
            return False
        return True

    @staticmethod
    def _span_is_quarantined(span: SourceSpan) -> bool:
        quality_status = str(span.quality_status or "").strip().casefold()
        return bool(str(span.quarantine_reason or "").strip()) or quality_status in {
            "blocked",
            "quarantined",
        }

    @staticmethod
    def _adjacent_coordinates_are_chronological(
        current_span: SourceSpan, adjacent: SourceSpan, *, direction: int
    ) -> bool:
        if direction < 0:
            return (
                adjacent.start_ms < current_span.start_ms
                and adjacent.source_span_index < current_span.source_span_index
            )
        if direction > 0:
            return (
                adjacent.start_ms > current_span.start_ms
                and adjacent.source_span_index > current_span.source_span_index
            )
        return False

    @staticmethod
    def _payload_is_quarantined(payload: Mapping[str, Any]) -> bool:
        quality_status = str(payload.get("quality_status") or "").strip().casefold()
        return bool(str(payload.get("quarantine_reason") or "").strip()) or quality_status in {
            "blocked",
            "quarantined",
        }

    # --------------------------------------------------------------- internal
    def fresh_spans_for_citations(
        self,
        point_ids: list[str],
        *,
        expected_evidence: Sequence[Mapping[str, Any]],
    ) -> Optional[list[SourceSpan]]:
        """Return current, validated child spans for an fp-context cache hit.

        Cache replay must not return Redis-derived attribution, links, timestamps, or
        display metadata.  Read the complete child payload again, apply the same
        servability gates, compare it with the cached evidence snapshot, and return
        ``SourceSpan`` objects so the caller can rebuild every user-facing citation
        field from the current payload.  ``None`` is fail-closed for missing,
        malformed, changed, or duplicated evidence.
        """
        if not point_ids:
            return None
        unique = list(dict.fromkeys(str(pid) for pid in point_ids))
        if len(unique) != len(point_ids):
            return None
        expected_by_point: dict[str, Mapping[str, Any]] = {}
        for evidence in expected_evidence:
            if not isinstance(evidence, Mapping) or not evidence.get("point_id"):
                return None
            point_id = str(evidence["point_id"])
            if point_id in expected_by_point:
                return None
            expected_by_point[point_id] = evidence
        if set(expected_by_point) != set(unique):
            return None

        # A cache hit is one parent context, not a bag of independently servable
        # children. Require one coherent parent/guru/video/corpus before hydrating.
        common_fields = ("parent_unit_id", "guru_id", "video_id", "corpus_version")
        common_values: dict[str, str] = {}
        cited_span_ids: list[str] = []
        for point_id in unique:
            evidence = expected_by_point[point_id]
            span_id = str(evidence.get("source_span_id") or "")
            if not span_id or point_id != point_id_for_record(span_id):
                return None
            cited_span_ids.append(span_id)
        if len(set(cited_span_ids)) != len(cited_span_ids):
            return None
        for field in common_fields:
            values = {str(evidence.get(field) or "") for evidence in expected_evidence}
            if len(values) != 1 or not next(iter(values)):
                return None
            common_values[field] = next(iter(values))

        try:
            hydrated = self.fetch_parent_context(
                common_values["parent_unit_id"],
                cited_span_ids,
            )
        except (FirstPersonContextStoreError, TypeError, ValueError) as exc:
            logger.debug(
                "[ContextStore] exact-cache parent hydration failed: %s", type(exc).__name__
            )
            return None

        parent = hydrated.parent
        if any(
            (
                common_values["parent_unit_id"] != parent.parent_unit_id,
                common_values["guru_id"] != parent.guru_id,
                common_values["video_id"] != parent.video_id,
                common_values["corpus_version"] != parent.corpus_version,
            )
        ):
            return None

        parent_ids = tuple(parent.ordered_source_span_ids)
        cited_set = set(cited_span_ids)
        if not cited_set.issubset(parent_ids):
            return None
        authoritative_ids = tuple(span_id for span_id in parent_ids if span_id in cited_set)
        # A reordered cached citation set is malformed, not an invitation to let
        # Redis choose answer order. Valid subsets are returned in parent order.
        if tuple(cited_span_ids) != authoritative_ids:
            return None

        spans_by_id = {span.source_span_id: span for span in hydrated.spans}
        fresh_spans: list[SourceSpan] = []
        from app.config import settings

        require_speaker_verified = getattr(settings, "first_person_require_speaker_verified", False)
        for span_id in authoritative_ids:
            span = spans_by_id.get(span_id)
            if span is None:
                return None
            if (
                span.speaker_role not in (SpeakerRole.GURU, SpeakerRole.TEACHER)
                or (require_speaker_verified and span.speaker_verified is not True)
                or span.rights_cleared is not True
                or not source_is_authoritatively_licensed(
                    source_url=span.source_url,
                    video_id=span.video_id,
                    domain_rights_status=span.domain_rights_status,
                )
                or not span.video_id
                or self._span_is_quarantined(span)
                or video_is_blocked(span.video_id)
                or (require_speaker_verified and speaker_write_violations(span.to_payload()))
            ):
                return None
            point_id = point_id_for_record(span.source_span_id)
            if not self._citation_matches_current_payload(
                point_id,
                span.to_payload(),
                expected_by_point[point_id],
            ):
                return None
            fresh_spans.append(span)
        return fresh_spans

    def points_servable(
        self,
        point_ids: list[str],
        *,
        expected_evidence: Sequence[Mapping[str, Any]] | None = None,
    ) -> bool:
        """True only if every fp-context point still exists and may be served.

        Exact-cache revalidation repeats the full first-person serve gate rather than
        trusting the fact that a point was eligible when the cached answer was made.
        When ``expected_evidence`` is supplied, each current payload is also compared with
        the exact citation evidence that produced the cached answer. IDs alone are not
        sufficient: text, clip hash, coordinates, identity, boundary/completeness, rights,
        quarantine, and the complete speaker provenance must still agree.
        """
        if not point_ids:
            return False
        unique = list(dict.fromkeys(str(pid) for pid in point_ids))
        if expected_evidence is not None:
            fresh_spans = self.fresh_spans_for_citations(
                unique,
                expected_evidence=expected_evidence,
            )
            return fresh_spans is not None and all(
                not video_is_blocked(span.video_id) for span in fresh_spans
            )
        records = self._client.retrieve(
            collection_name=self._collection,
            ids=unique,
            with_payload=list(_SERVABILITY_PAYLOAD_KEYS),
            with_vectors=False,
        )
        if len(records) != len(unique):
            return False
        if {str(record.id) for record in records} != set(unique):
            return False
        from app.config import settings

        require_speaker_verified = getattr(settings, "first_person_require_speaker_verified", False)
        for record in records:
            payload = record.payload or {}
            point_id = str(record.id)
            if payload.get("record_type") != "retrieval_child":
                return False
            if point_id not in unique:
                return False
            if payload.get("speaker_role") not in (
                SpeakerRole.GURU.value,
                SpeakerRole.TEACHER.value,
            ):
                return False
            if require_speaker_verified and payload.get("speaker_verified") is not True:
                return False
            if payload.get("rights_cleared") is not True:
                return False
            if payload.get("domain_rights_status") != "licensed":
                return False
            if not source_is_authoritatively_licensed(
                source_url=payload.get("source_url"),
                video_id=payload.get("video_id"),
                domain_rights_status=payload.get("domain_rights_status"),
            ):
                return False
            if not payload.get("video_id"):
                return False
            if self._payload_is_quarantined(payload):
                return False
            if video_is_blocked(payload.get("video_id")):
                return False
            if speaker_write_violations(payload):
                return False
        return True

    @staticmethod
    def _citation_matches_current_payload(
        point_id: str,
        payload: Mapping[str, Any],
        expected: Mapping[str, Any],
    ) -> bool:
        """Compare cached citation evidence with one freshly read Qdrant payload."""
        span_id = str(payload.get("source_span_id") or "")
        if not span_id or point_id != point_id_for_record(span_id):
            return False
        try:
            span = SourceSpan.model_validate(_strip_record_type(dict(payload)))
        except Exception:
            return False

        exact_fields: tuple[tuple[str, Any], ...] = (
            ("point_id", point_id),
            ("source_span_id", span.source_span_id),
            ("source_asset_id", span.source_asset_id),
            ("parent_unit_id", span.parent_unit_id),
            ("corpus_version", span.corpus_version),
            ("video_id", span.video_id),
            ("guru_id", span.guru_id),
            ("speaker_id", span.speaker_id),
            ("speaker_role", span.speaker_role.value),
            ("speaker_verified", span.speaker_verified),
            ("start_ms", span.start_ms),
            ("end_ms", span.end_ms),
            ("word_start", span.word_start),
            ("word_end", span.word_end),
            ("verbatim_text", span.verbatim_text),
            ("source_text_hash", span.source_text_hash),
            ("is_verbatim", span.is_verbatim),
            ("boundary_status", span.boundary_status.value),
            ("completeness_status", span.completeness_status.value),
            ("rights_cleared", span.rights_cleared),
            ("domain_rights_status", span.domain_rights_status),
            ("quality_status", span.quality_status),
            ("quarantine_reason", span.quarantine_reason),
            ("source_url", span.source_url),
        )
        for key, current_value in exact_fields:
            if key not in expected or expected.get(key) != current_value:
                return False
        # DATA-03 / T3-03: resolve both v2 (span_text_sha256 / video_transcript_sha256)
        # and v1 (transcript_hash / source_text_hash).
        exp_span_hash = expected.get("span_text_sha256") or expected.get("transcript_hash")
        actual_span_hash = span.span_text_sha256 or span.source_text_hash
        if exp_span_hash and exp_span_hash != actual_span_hash:
            return False
        exp_vid_hash = expected.get("video_transcript_sha256") or expected.get(
            "video_transcript_hash"
        )
        actual_vid_hash = span.video_transcript_sha256 or span.transcript_hash
        if exp_vid_hash and exp_vid_hash != actual_vid_hash:
            return False

        # A verified citation must carry the complete provenance snapshot. This
        # rejects old/incomplete cache entries instead of silently treating an ID
        # as evidence for a speaker claim.
        for key in (*AUTOMATED_PROVENANCE_KEYS, *HUMAN_REVIEW_KEYS):
            if key not in expected or expected.get(key) != payload.get(key):
                return False
        return True

    def dense_vectors_for_spans(self, span_ids: Sequence[str]) -> dict[str, list[float]]:
        """Read-only ``passage_dense`` lookup for a set of child span IDs.

        The harness scores a served parent with the retrieval score that produced
        the hit. When retrieval ran on a HyDE expansion, that score describes the
        expansion, not the seeker's question, so the calibrated confidence needs
        the child vectors to recompute cosine against the original query vector.
        This is a read-only fetch: it never widens a candidate set, never changes
        a payload, and returns ``{}`` when the client refuses the read so the
        caller can fall back to the retrieval score.
        """
        if not span_ids:
            return {}
        by_point: dict[str, str] = {}
        for span_id in span_ids:
            key = str(span_id or "").strip()
            if not key or key in by_point:
                continue
            by_point[point_id_for_record(key)] = key
        if not by_point:
            return {}
        try:
            records = self._client.retrieve(
                collection_name=self._collection,
                ids=list(by_point),
                with_payload=False,
                with_vectors=["passage_dense"],
            )
        except Exception as exc:  # pragma: no cover - transport dependent
            logger.debug(
                "[FirstPersonContextStore] passage_dense read unavailable: %s", type(exc).__name__
            )
            return {}
        out: dict[str, list[float]] = {}
        for record in records or ():
            span_id = by_point.get(str(getattr(record, "id", "")))
            raw = getattr(record, "vector", None)
            dense = raw.get("passage_dense") if isinstance(raw, dict) else None
            if span_id and dense:
                out[span_id] = [float(x) for x in dense]
        return out

    def _get_record(self, point_id: str) -> Any:
        records = self._client.retrieve(
            collection_name=self._collection,
            ids=[point_id],
            with_payload=True,
            with_vectors=False,
        )
        return records[0] if records else None

    def _scroll_children(self, parent_unit_id: str) -> list[Any]:
        all_records: list[Any] = []
        offset: Any = None
        while True:
            scroll_kwargs: dict[str, Any] = {
                "collection_name": self._collection,
                "scroll_filter": Filter(
                    must=[
                        FieldCondition(
                            key="record_type", match=MatchValue(value=RECORD_TYPE_CHILD)
                        ),
                        FieldCondition(
                            key="parent_unit_id", match=MatchValue(value=parent_unit_id)
                        ),
                    ]
                ),
                "limit": 256,
                "with_payload": True,
                "with_vectors": False,
            }
            if offset is not None:
                scroll_kwargs["offset"] = offset
            res = self._client.scroll(**scroll_kwargs)
            records, next_offset = res if isinstance(res, tuple) else (res, None)
            all_records.extend(records)
            if next_offset is None or next_offset == offset:
                break
            offset = next_offset
        return all_records


if __name__ == "__main__":
    from types import SimpleNamespace

    from domain.first_person_context import (
        AnswerRole,
        BoundaryStatus,
        CompletenessStatus,
        ParentUnit,
        ProvenanceKind,
        SourceSpan,
        SpeakerRole,
        clip_text_hash,
        make_parent_unit_id,
        make_source_span_id,
    )

    class _SelfCheckFakeClient:
        def __init__(self) -> None:
            self.points: dict[str, Any] = {}

        def upsert(
            self, collection_name: str, points: list[PointStruct], wait: bool = True
        ) -> None:
            for p in points:
                self.points[str(p.id)] = SimpleNamespace(
                    id=str(p.id), payload=dict(p.payload or {})
                )

        def retrieve(
            self,
            collection_name: str,
            ids: list[Any],
            with_payload: bool = True,
            with_vectors: bool = False,
        ) -> list[Any]:
            return [self.points[str(i)] for i in ids if str(i) in self.points]

        def scroll(
            self,
            collection_name: str,
            scroll_filter: Any,
            limit: int,
            offset: Any = None,
            with_payload: bool = True,
            with_vectors: bool = False,
        ) -> tuple[list[Any], Any]:
            parent_id = None
            for cond in scroll_filter.must:
                if cond.key == "parent_unit_id":
                    parent_id = cond.match.value
            matching = [
                p
                for p in self.points.values()
                if p.payload.get("record_type") == RECORD_TYPE_CHILD
                and p.payload.get("parent_unit_id") == parent_id
            ]
            return matching[:limit], None

    _fake = _SelfCheckFakeClient()
    _store = FirstPersonContextStore(client=_fake, collection="self_check")

    _text = "Awakening is a shift in consciousness."
    _hash = clip_text_hash(_text)
    _pid = make_parent_unit_id(
        guru_id="krishnaji",
        video_id="vid_sc",
        corpus_version="fp-context-v1",
        first_word_index=0,
        last_word_index=6,
    )
    _sid = make_source_span_id(
        guru_id="krishnaji",
        video_id="vid_sc",
        corpus_version="fp-context-v1",
        word_start=0,
        word_end=6,
        transcript_hash=_hash,
    )

    _s = SourceSpan(
        corpus_version="fp-context-v1",
        guru_id="krishnaji",
        video_id="vid_sc",
        source_asset_id="vid_sc",
        source_span_id=_sid,
        parent_unit_id=_pid,
        turn_id="turn_0",
        turn_index=0,
        source_span_index=0,
        speaker_id="krishnaji",
        speaker_role=SpeakerRole.GURU,
        speaker_verified=True,
        rights_cleared=True,
        caption_status="auto",
        provenance_kind=ProvenanceKind.SPEECH_TURN_SPAN,
        answer_role=AnswerRole.DIRECT,
        word_start=0,
        word_end=6,
        start_ms=1000,
        end_ms=4000,
        source_transcript_text=_text,
        verbatim_text=_text,
        transcript_hash=_hash,
        source_text_hash=_hash,
        source_url="https://youtube.com/watch?v=vid_sc",
        boundary_status=BoundaryStatus.VERIFIED,
        completeness_status=CompletenessStatus.COMPLETE,
    )
    _p = ParentUnit(
        corpus_version="fp-context-v1",
        guru_id="krishnaji",
        video_id="vid_sc",
        parent_unit_id=_pid,
        ordered_source_span_ids=(_sid,),
        start_ms=1000,
        end_ms=4000,
        parent_text_hash=_hash,
        speaker_ids=("krishnaji",),
        speaker_continuity=True,
        boundary_status=BoundaryStatus.VERIFIED,
        completeness_status=CompletenessStatus.COMPLETE,
    )

    _count = _store.upsert(_p, [_s])
    assert _count == 2, f"Expected 2 points upserted, got {_count}"

    _loaded = _store.fetch_parent_context(_pid, [_sid])
    assert _loaded is not None, "Failed to fetch parent context"
    assert _loaded.parent.parent_unit_id == _pid
    assert len(_loaded.spans) == 1
    assert _loaded.spans[0].source_span_id == _sid
    print("first_person_context_store self-check passed")
