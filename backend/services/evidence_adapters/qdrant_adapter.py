"""Qdrant adapter normalizing vector/hybrid search results into EvidenceCandidate."""

from __future__ import annotations

import logging
import uuid
from typing import Any

from qdrant_client.http.models import (
    FieldCondition,
    Filter,
    Fusion,
    FusionQuery,
    MatchAny,
    MatchValue,
    Prefetch,
    SparseVector,
)

from domain.evidence_contract import EvidenceCandidate, content_sha256, make_source_id
from services.first_person_rights import source_is_authoritatively_licensed
from services.guru_registry import neutral_voice_id

logger = logging.getLogger(__name__)


def _is_uuid(value: str) -> bool:
    try:
        uuid.UUID(value)
    except ValueError:
        return False
    return True


class QdrantEvidenceAdapter:
    """Queries Qdrant collections and emits rights-gated EvidenceCandidate objects."""

    def __init__(self, client: Any, collection_name: str) -> None:
        self._client = client
        self._collection = collection_name

    def search(
        self,
        *,
        query_dense: list[float],
        query_sparse: dict[str, Any] | None = None,
        teacher_id: str | None = None,
        source_types: list[str] | None = None,
        limit: int = 20,
        require_licensed: bool = True,
        require_speaker_verified: bool = False,
        raise_on_error: bool = False,
    ) -> list[EvidenceCandidate]:
        if self._client is None or not query_dense or limit <= 0:
            return []

        must_conditions: list[FieldCondition] = []
        if require_licensed:
            must_conditions.append(
                FieldCondition(key="domain_rights_status", match=MatchValue(value="licensed"))
            )
        if require_speaker_verified:
            must_conditions.append(
                FieldCondition(key="speaker_verified", match=MatchValue(value=True))
            )
        if teacher_id and teacher_id.strip().lower() not in {"", "both", "all"}:
            tid = teacher_id.strip().lower()
            must_conditions.append(
                FieldCondition(key="guru_id", match=MatchAny(any=[tid, neutral_voice_id()]))
            )
        if source_types:
            must_conditions.append(
                FieldCondition(key="source_type", match=MatchAny(any=source_types))
            )

        qfilter = Filter(must=must_conditions) if must_conditions else None
        hits = self._execute_query(
            query_dense=query_dense,
            query_sparse=query_sparse,
            qfilter=qfilter,
            limit=limit,
            raise_on_error=raise_on_error,
        )
        return self._normalize_hits(hits, require_licensed=require_licensed)

    def fetch_by_ids(
        self, ids: list[str], *, require_licensed: bool = True
    ) -> dict[str, EvidenceCandidate]:
        """Read-only lookup of stored spans; returns {requested-or-stored id: candidate}."""
        wanted = [i for i in dict.fromkeys(ids) if i]
        if self._client is None or not wanted:
            return {}
        hits: list[Any] = []
        for key in ("source_span_id", "evidence_id"):
            points, _ = self._client.scroll(
                collection_name=self._collection,
                scroll_filter=Filter(must=[FieldCondition(key=key, match=MatchAny(any=wanted))]),
                limit=len(wanted) * 2,
                with_payload=True,
            )
            hits.extend(points)
        uuid_ids = [i for i in wanted if _is_uuid(i)]
        if uuid_ids:
            hits.extend(
                self._client.retrieve(
                    collection_name=self._collection, ids=uuid_ids, with_payload=True
                )
            )
        by_id: dict[str, EvidenceCandidate] = {}
        for h in hits:
            for ev in self._normalize_hits([h], require_licensed=require_licensed):
                by_id.setdefault(ev.evidence_id, ev)
                by_id.setdefault(str(getattr(h, "id", "")), ev)
        return by_id

    def _execute_query(
        self,
        *,
        query_dense: list[float],
        query_sparse: dict[str, Any] | None,
        qfilter: Filter | None,
        limit: int,
        raise_on_error: bool = False,
    ) -> list[Any]:
        try:
            if query_sparse and query_sparse.get("indices") and query_sparse.get("values"):
                sv = SparseVector(
                    indices=[int(i) for i in query_sparse["indices"]],
                    values=[float(v) for v in query_sparse["values"]],
                )
                res = self._client.query_points(
                    collection_name=self._collection,
                    prefetch=[
                        Prefetch(
                            query=query_dense,
                            using="passage_dense",
                            filter=qfilter,
                            limit=limit * 2,
                        ),
                        Prefetch(query=sv, using="passage_sparse", filter=qfilter, limit=limit * 2),
                    ],
                    query=FusionQuery(fusion=Fusion.RRF),
                    limit=limit,
                    with_payload=True,
                )
                return list(getattr(res, "points", None) or [])
        except Exception as exc:
            logger.debug(
                "[QdrantEvidenceAdapter] hybrid RRF query failed, falling back to dense: %s", exc
            )
        first_exc: Exception | None = None
        last_exc: Exception | None = None

        for vector_name in ("passage_dense", "dense", None):
            try:
                kwargs: dict[str, Any] = {
                    "collection_name": self._collection,
                    "query": query_dense,
                    "query_filter": qfilter,
                    "limit": limit,
                    "with_payload": True,
                }
                if vector_name is not None:
                    kwargs["using"] = vector_name
                res = self._client.query_points(**kwargs)
                return list(getattr(res, "points", None) or [])
            except Exception as exc:
                first_exc = first_exc or exc
                last_exc = exc
                continue
        if raise_on_error and last_exc is not None:
            logger.warning("[QdrantEvidenceAdapter] all query variants failed: %s", first_exc)
            raise first_exc if first_exc is last_exc else last_exc from first_exc
        return []

    def _normalize_hits(
        self, hits: list[Any], *, require_licensed: bool
    ) -> list[EvidenceCandidate]:
        out: list[EvidenceCandidate] = []
        for h in hits:
            pl = dict(getattr(h, "payload", None) or {})
            text = str(pl.get("verbatim_text") or pl.get("text") or "").strip()
            if not text:
                continue
            source_url = str(pl.get("source_url") or "")
            video_id = str(pl.get("video_id") or "")
            source_type = str(pl.get("source_type") or ("video" if video_id else "document"))
            rights_status = str(pl.get("domain_rights_status") or "unverified")
            source_id = str(pl.get("source_asset_id") or "") or (
                make_source_id(source_url)
                if source_url
                else make_source_id(video_id or str(getattr(h, "id", "")))
            )

            if require_licensed and not source_is_authoritatively_licensed(
                source_url=source_url,
                video_id=video_id,
                domain_rights_status=rights_status,
                source_type=source_type,
                source_id=source_id,
            ):
                continue

            evidence_id = str(
                pl.get("source_span_id") or pl.get("evidence_id") or getattr(h, "id", "")
            )
            start_ms = (
                pl.get("start_ms") if pl.get("start_ms") is not None else pl.get("audio_start_ms")
            )
            end_ms = pl.get("end_ms") if pl.get("end_ms") is not None else pl.get("audio_end_ms")
            teacher_id = pl.get("guru_id") or pl.get("teacher_id")
            speaker_verified = bool(pl.get("speaker_verified", False))
            page_num = pl.get("page_number")
            if page_num is None and isinstance(pl.get("page_range"), str):
                head = pl["page_range"].split("-", 1)[0].strip()
                if head.isdigit():
                    page_num = int(head)

            out.append(
                EvidenceCandidate(
                    evidence_id=evidence_id,
                    source_id=source_id,
                    source_type=source_type,
                    source_title=str(pl.get("title") or pl.get("source_title") or ""),
                    source_url=source_url
                    or (f"https://www.youtube.com/watch?v={video_id}" if video_id else ""),
                    teacher_id=str(teacher_id) if teacher_id else None,
                    speaker_label=str(pl.get("speaker") or pl.get("speaker_id") or "") or None,
                    speaker_verified=speaker_verified,
                    text=text,
                    start_time=(float(start_ms) / 1000.0)
                    if isinstance(start_ms, (int, float))
                    else None,
                    end_time=(float(end_ms) / 1000.0) if isinstance(end_ms, (int, float)) else None,
                    page_number=int(page_num) if isinstance(page_num, int) else None,
                    chapter=str(pl.get("chapter") or pl.get("title") or "") or None,
                    language=str(pl.get("language") or "en"),
                    retrieval_source="qdrant",
                    retrieval_score=float(getattr(h, "score", 0.0) or 0.0),
                    source_version=str(
                        pl.get("source_release_version") or pl.get("source_version") or "1"
                    ),
                    verification_status="automated_candidate" if speaker_verified else "unverified",
                    rights_status=rights_status,
                    content_hash=str(
                        pl.get("source_text_hash")
                        or pl.get("content_checksum")
                        or content_sha256(text)
                    ),
                    surrounding_context=str(pl.get("parent_text") or "") or None,
                    concepts=[
                        str(x)
                        for x in (pl.get("topic_ids") or []) + (pl.get("entity_ids") or [])
                        if x
                    ],
                    provenance={
                        "collection": self._collection,
                        "point_id": str(getattr(h, "id", "")),
                        "parent_unit_id": pl.get("parent_unit_id") or pl.get("parent_id"),
                        "corpus_version": pl.get("corpus_version"),
                        "chunker_version": pl.get("chunker_version"),
                    },
                )
            )
        return out
