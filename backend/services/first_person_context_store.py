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
import uuid
from collections.abc import Iterable, Mapping
from typing import Any, Optional

from qdrant_client import QdrantClient
from qdrant_client.http.models import (
    FieldCondition,
    Filter,
    MatchValue,
    PointStruct,
)

from app.config import settings
from domain.first_person_context import (
    ParentContext,
    ParentUnit,
    SourceSpan,
)

logger = logging.getLogger(__name__)

RECORD_TYPE_CHILD = "retrieval_child"
RECORD_TYPE_PARENT = "parent_unit"

# Payload indexes required by the harness filters. Keep in sync with
# SourceSpan/ParentUnit fields; a missing keyword index makes a filtered search
# fall back to a full scan on large collections.
SPAN_INDEXES: tuple[tuple[str, str], ...] = (
    ("guru_id", "keyword"),
    ("video_id", "keyword"),
    ("parent_unit_id", "keyword"),
    ("source_span_id", "keyword"),
    ("record_type", "keyword"),
    ("speaker_id", "keyword"),
    ("speaker_role", "keyword"),
    ("speaker_verified", "bool"),
    ("rights_cleared", "bool"),
    ("is_verbatim", "bool"),
    ("boundary_status", "keyword"),
    ("completeness_status", "keyword"),
    ("provenance_kind", "keyword"),
    ("answer_role", "keyword"),
    ("corpus_version", "keyword"),
    ("start_ms", "integer"),
    ("end_ms", "integer"),
)


class FirstPersonContextStoreError(RuntimeError):
    """Raised when stored data violates the fp-context-v1 contract."""


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
    return data


class FirstPersonContextStore:
    def __init__(self, client: QdrantClient, collection: str) -> None:
        self._client = client
        self._collection = collection

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
                logger.debug("context store: index %s not created: %s", key, exc)
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

        points = [
            PointStruct(
                id=point_id_for_record(span.source_span_id),
                vector=(vectors.get(span.source_span_id, {}) if vectors else {}),
                payload=span.to_payload(),
            )
            for span in span_list
        ]
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
    def _assert_belongs(parent: ParentUnit, span: SourceSpan) -> None:
        if span.parent_unit_id != parent.parent_unit_id:
            raise FirstPersonContextStoreError("span does not belong to parent")
        if span.guru_id != parent.guru_id:
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
        limit_parents: int = 5,
        spans_per_parent: int = 8,
    ) -> list[ParentContext]:
        """Search children, group by parent, then hydrate whole parents."""
        if limit_parents <= 0:
            return []
        conditions = [
            FieldCondition(key="record_type", match=MatchValue(value=RECORD_TYPE_CHILD)),
            FieldCondition(key="rights_cleared", match=MatchValue(value=True)),
        ]
        if guru_id and guru_id.lower() not in ("both", "all", ""):
            conditions.append(
                FieldCondition(key="guru_id", match=MatchValue(value=guru_id.lower()))
            )
        query_filter = Filter(must=conditions)

        groups = self._query_groups(
            query_dense,
            query_filter=query_filter,
            limit_parents=limit_parents,
            spans_per_parent=spans_per_parent,
        )

        contexts: list[ParentContext] = []
        for parent_unit_id, hits, score in groups:
            try:
                contexts.append(self.fetch_parent_context(parent_unit_id, hits, score))
            except FirstPersonContextStoreError:
                logger.warning("[ContextStore] dropping invalid parent context")
        return contexts

    def _query_groups(
        self,
        query_dense: list[float],
        *,
        query_filter: Filter,
        limit_parents: int,
        spans_per_parent: int,
    ) -> list[tuple[str, tuple[str, ...], float]]:
        if hasattr(self._client, "query_points_groups"):
            try:
                response = self._client.query_points_groups(
                    collection_name=self._collection,
                    query=query_dense,
                    using="passage_dense",
                    query_filter=query_filter,
                    group_by="parent_unit_id",
                    limit=limit_parents,
                    group_size=spans_per_parent,
                    with_payload=["source_span_id"],
                )
                out: list[tuple[str, tuple[str, ...], float]] = []
                for group in getattr(response, "groups", []) or []:
                    hits = list(getattr(group, "hits", []) or [])
                    if not hits:
                        continue
                    span_ids = tuple(
                        str((hit.payload or {}).get("source_span_id") or hit.id) for hit in hits
                    )
                    score = max(float(getattr(h, "score", 0.0) or 0.0) for h in hits)
                    out.append((str(group.id), span_ids, score))
                if out:
                    return out
            except Exception as exc:  # pragma: no cover - API/version dependent
                logger.debug("[ContextStore] grouped query unavailable: %s", exc)

        return self._group_in_python(
            query_dense,
            query_filter=query_filter,
            limit_parents=limit_parents,
            spans_per_parent=spans_per_parent,
        )

    def _group_in_python(
        self,
        query_dense: list[float],
        *,
        query_filter: Filter,
        limit_parents: int,
        spans_per_parent: int,
    ) -> list[tuple[str, tuple[str, ...], float]]:
        response = self._client.query_points(
            collection_name=self._collection,
            query=query_dense,
            using="passage_dense",
            query_filter=query_filter,
            limit=limit_parents * spans_per_parent * 3,
            with_payload=["parent_unit_id", "source_span_id"],
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
                max(float(hit.score or 0.0) for hit in bucket),
            )
            for parent_id, bucket in grouped.items()
        ]
        out.sort(key=lambda item: item[2], reverse=True)
        return out[:limit_parents]

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
                continue
            if str(record.id) != point_id_for_record(str(span_id)):
                raise FirstPersonContextStoreError(f"point id does not match span id {span_id}")
            by_id[str(span_id)] = record_payload

        missing = [sid for sid in parent.ordered_source_span_ids if sid not in by_id]
        if missing:
            raise FirstPersonContextStoreError(
                f"{len(missing)} ordered span(s) missing from the index"
            )

        spans: list[SourceSpan] = []
        for span_id in parent.ordered_source_span_ids:
            try:
                span = SourceSpan.model_validate(by_id[span_id])
            except Exception as exc:
                raise FirstPersonContextStoreError(
                    f"invalid span payload {span_id}: {exc}"
                ) from exc
            self._assert_belongs(parent, span)
            spans.append(span)

        returned_hits = tuple(hit_span_ids) or (spans[0].source_span_id,)
        return ParentContext(
            parent=parent,
            spans=tuple(spans),
            hit_span_ids=returned_hits,
            score=score,
        )

    # --------------------------------------------------------------- internal
    def points_servable(self, point_ids: list[str]) -> bool:
        """True only if every fp-context point still exists and may be served.

        The legacy clip store's check keys on ``first_person_eligible``, a
        field the fp-context-v1 schema does not carry, so reusing it would
        mark every harness citation unservable and silently disable the
        exact cache. The fp-context equivalent gates on the contract's own
        fields: the point is a retrieval child, its rights are cleared (unless
        unregistered serving is on) and its speaker is verified.
        """
        if not point_ids:
            return False
        unique = list(dict.fromkeys(str(pid) for pid in point_ids))
        records = self._client.retrieve(
            collection_name=self._collection,
            ids=unique,
            with_payload=["record_type", "rights_cleared", "speaker_verified"],
            with_vectors=False,
        )
        if len(records) != len(unique):
            return False
        need_rights = not getattr(settings, "first_person_serve_unregistered", False)
        for record in records:
            payload = record.payload or {}
            if payload.get("record_type") != "retrieval_child":
                return False
            if payload.get("speaker_verified") is not True:
                return False
            if need_rights and payload.get("rights_cleared") is not True:
                return False
        return True

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
                        FieldCondition(key="record_type", match=MatchValue(value=RECORD_TYPE_CHILD)),
                        FieldCondition(key="parent_unit_id", match=MatchValue(value=parent_unit_id)),
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

        def upsert(self, collection_name: str, points: list[PointStruct], wait: bool = True) -> None:
            for p in points:
                self.points[str(p.id)] = SimpleNamespace(id=str(p.id), payload=dict(p.payload or {}))

        def retrieve(self, collection_name: str, ids: list[Any], with_payload: bool = True, with_vectors: bool = False) -> list[Any]:
            return [self.points[str(i)] for i in ids if str(i) in self.points]

        def scroll(self, collection_name: str, scroll_filter: Any, limit: int, offset: Any = None, with_payload: bool = True, with_vectors: bool = False) -> tuple[list[Any], Any]:
            parent_id = None
            for cond in scroll_filter.must:
                if cond.key == "parent_unit_id":
                    parent_id = cond.match.value
            matching = [
                p for p in self.points.values()
                if p.payload.get("record_type") == RECORD_TYPE_CHILD and p.payload.get("parent_unit_id") == parent_id
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
