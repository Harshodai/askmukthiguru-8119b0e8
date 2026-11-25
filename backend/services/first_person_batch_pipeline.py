"""Modern first-person batch builder for the fp-context-v1 contract.

This module constructs validated, bounded ParentUnit/SourceSpan records, embeds
retrieval text, and delegates writes to FirstPersonContextStore. Speaker identity
is never inferred from titles or channel metadata. Rejected windows are recorded
before any Qdrant write; raw ASR text is preserved verbatim and never rewritten.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from hashlib import sha256
from typing import Any, Callable, Iterable, Mapping

from qdrant_client.http.models import SparseVector

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
from ingest.verbatim.asr_cleaner import asr_cleaner_flags
from ingest.verbatim.boundaries import boundary_defects
from services.qdrant.indexer import resolve_source_rights_status
from services.text_quality_filter import find_artifact

from services.guru_registry import shared_attribution

CORPUS_VERSION = "fp-context-resegment-v2"
CHUNKER_VERSION = "boundary_v1:sentence_closing_18-25s"
SHARED_GURU_ID = shared_attribution()[0] or "shared"
SHARED_SPEAKER_ID = "shared_unverified"
MIN_WINDOW_MS = 18_000
MAX_WINDOW_MS = 25_000
MAX_PARENT_DURATION_MS = 60_000
MAX_PARENT_SPANS = 4
MAX_PARENT_GAP_MS = 30_000


@dataclass(frozen=True)
class Window:
    start_ms: int
    end_ms: int
    text: str
    word_start: int
    word_end: int


def _ends_sentence(text: str) -> bool:
    return text.rstrip().endswith((".", "?", "!", "…"))


def build_sentence_closing_windows(
    segments: Iterable[Mapping[str, Any]],
    *,
    min_window_ms: int = MIN_WINDOW_MS,
    max_window_ms: int = MAX_WINDOW_MS,
) -> list[Window]:
    """Merge timestamped ASR segments, closing at sentence boundaries when possible.

    Interval overlap is preserved, and absent word indexes are assigned from the
    deterministic flattened segment order. Incomplete tail windows are returned
    for rejection/ledgering, never silently rounded up to a sentence.
    """
    normalized: list[dict[str, Any]] = []
    next_word = 0
    for segment in segments:
        text = str(segment.get("text") or "").strip()
        start = int(round(float(segment.get("start_ms", float(segment.get("start", 0)) * 1000))))
        end = int(round(float(segment.get("end_ms", float(segment.get("end", 0)) * 1000))))
        if not text or end <= start:
            continue
        words = segment.get("words") or []
        count = len(words) if words else len(text.split())
        word_start = int(segment.get("word_start", next_word))
        word_end = int(segment.get("word_end", word_start + count))
        next_word = max(next_word, word_end)
        normalized.append(
            {
                "start_ms": start,
                "end_ms": end,
                "text": text,
                "word_start": word_start,
                "word_end": word_end,
            }
        )
    normalized.sort(key=lambda item: (item["start_ms"], item["end_ms"], item["word_start"]))

    windows: list[Window] = []
    current: list[dict[str, Any]] = []
    for item in normalized:
        if not current:
            current = [item]
            continue
        proposed_end = max(current[-1]["end_ms"], item["end_ms"])
        current_start = current[0]["start_ms"]
        if proposed_end - current_start > max_window_ms:
            boundary = next(
                (i for i in range(len(current) - 1, -1, -1) if _ends_sentence(current[i]["text"])),
                None,
            )
            cut = boundary if boundary is not None else len(current) - 1
            windows.append(_make_window(current[: cut + 1]))
            current = current[cut + 1 :]
            if not current:
                current = [item]
            else:
                current.append(item)
            continue
        current.append(item)
        if item["end_ms"] - current_start >= min_window_ms and _ends_sentence(item["text"]):
            windows.append(_make_window(current))
            current = []
    if current:
        windows.append(_make_window(current))
    return [window for window in windows if window.end_ms > window.start_ms and window.text]


def _make_window(items: list[dict[str, Any]]) -> Window:
    return Window(
        start_ms=int(items[0]["start_ms"]),
        end_ms=max(int(item["end_ms"]) for item in items),
        text=" ".join(str(item["text"]).strip() for item in items).strip(),
        word_start=min(int(item["word_start"]) for item in items),
        word_end=max(int(item["word_end"]) for item in items),
    )


def _group_windows(windows: list[Window]) -> list[list[Window]]:
    """Make bounded chronological parents; never expand a whole video as one parent."""
    groups: list[list[Window]] = []
    current: list[Window] = []
    for window in windows:
        exceeds_duration = bool(current) and window.end_ms - current[0].start_ms > MAX_PARENT_DURATION_MS
        exceeds_count = len(current) >= MAX_PARENT_SPANS
        long_gap = bool(current) and window.start_ms - current[-1].end_ms > MAX_PARENT_GAP_MS
        if exceeds_duration or exceeds_count or long_gap:
            groups.append(current)
            current = []
        current.append(window)
    if current:
        groups.append(current)
    return groups


def _sparse_vector(value: Any) -> SparseVector:
    if isinstance(value, SparseVector):
        result = value
    elif isinstance(value, Mapping):
        if "indices" in value and "values" in value:
            result = SparseVector(
                indices=[int(x) for x in value["indices"]],
                values=[float(x) for x in value["values"]],
            )
        else:
            result = SparseVector(
                indices=[int(k) for k in value],
                values=[float(v) for v in value.values()],
            )
    else:
        indices = getattr(value, "indices", [])
        values = getattr(value, "values", [])
        if hasattr(indices, "tolist"):
            indices = indices.tolist()
        if hasattr(values, "tolist"):
            values = values.tolist()
        result = SparseVector(indices=[int(x) for x in indices], values=[float(x) for x in values])
    if len(result.indices) != len(result.values):
        raise ValueError("sparse embedding indices and values have different lengths")
    if any(not math.isfinite(float(value)) for value in result.values):
        raise ValueError("sparse embedding contains a non-finite value")
    return result


def _video_transcript_hash(segments: list[Mapping[str, Any]]) -> str:
    transcript = " ".join(str(segment.get("text") or "").strip() for segment in segments).strip()
    return sha256(transcript.encode("utf-8")).hexdigest()


def _persist_rejection(
    *,
    source_url: str,
    reason: str,
    chunk_index: int,
    matched_span: str,
    source_coordinates: str = "",
    point_id: str = "",
) -> bool:
    """Persist one rejected window through the guarded telemetry adapter."""
    try:
        from app.telemetry_db import _get_client

        client = _get_client()
        if client is None:
            return False
        row = {
            "source_url": source_url,
            "chunk_index": chunk_index,
            "gate_layer": "fp_context_batch_pipeline_tier_1",
            "gate_verdict": "rejected",
            "reason": reason,
            "gate_reason": f"{reason}; {source_coordinates}" if source_coordinates else reason,
            "matched_span": matched_span[:500],
            "point_id": point_id,
        }
        client.table("corpus_gate_rejections").insert([row]).execute()
        return True
    except Exception:
        return False


def build_context_records(
    *,
    video_id: str,
    segments: Iterable[Mapping[str, Any]],
    source_url: str | None = None,
    ingest_namespace: str | None = None,
    corpus_version: str = CORPUS_VERSION,
    asr_engine: str | None = None,
    asr_model_version: str | None = None,
    source_artifact_sha256: str | None = None,
    rights_resolver: Callable[..., str] = resolve_source_rights_status,
    rejection_persistor: Callable[..., bool] = _persist_rejection,
) -> tuple[list[ParentUnit], list[SourceSpan], int]:
    """Build bounded parent groups and ordered, unverified child spans for a video."""
    if ingest_namespace is not None and not ingest_namespace.strip():
        raise ValueError("ingest_namespace must be non-empty when supplied")
    raw = [dict(segment) for segment in segments]
    windows = build_sentence_closing_windows(raw)
    canonical_url = f"https://www.youtube.com/watch?v={video_id}"
    if source_url and source_url != canonical_url:
        canonical_url = f"https://www.youtube.com/watch?v={video_id}"
    rights = rights_resolver(source_url=canonical_url, video_id=video_id)
    if rights != "licensed":
        raise ValueError(f"source is not licensed in curated register: {video_id} ({rights})")
    if not windows:
        raise ValueError(f"no usable sentence-closing windows for {video_id}")

    transcript_hash = _video_transcript_hash(raw)
    accepted: list[Window] = []
    rejected_count = 0
    for index, window in enumerate(windows):
        defects = boundary_defects(window.text.split())
        reasons: list[str] = []
        duration_ms = window.end_ms - window.start_ms
        if duration_ms < MIN_WINDOW_MS or duration_ms > MAX_WINDOW_MS:
            reasons.append(f"window_duration_out_of_range:{duration_ms}ms")
        if not _ends_sentence(window.text):
            reasons.append("window_missing_sentence_terminator")
        if defects:
            reasons.append("boundary_defects:" + ",".join(defects))
        artifact = find_artifact(window.text)
        if artifact:
            reasons.append("text_artifact:" + str(artifact))
        flags = asr_cleaner_flags(window.text)
        if flags:
            reasons.append("asr_cleaner_flags:" + ",".join(flags))
        if reasons:
            reason = ";".join(reasons)
            if not rejection_persistor(
                source_url=canonical_url,
                reason=reason,
                chunk_index=index,
                matched_span=window.text,
                source_coordinates=(
                    f"start_ms={window.start_ms};end_ms={window.end_ms};"
                    f"word_start={window.word_start};word_end={window.word_end}"
                ),
                point_id="",
            ):
                raise RuntimeError(
                    f"rejected source window {video_id}#{index} could not be persisted; refusing Qdrant write"
                )
            rejected_count += 1
            continue
        accepted.append(window)

    if not accepted:
        raise ValueError(f"all ASR windows failed quality gates for {video_id}")

    parents: list[ParentUnit] = []
    spans: list[SourceSpan] = []
    global_index = 0
    for group in _group_windows(accepted):
        parent_id = make_parent_unit_id(
            guru_id=SHARED_GURU_ID,
            video_id=video_id,
            corpus_version=corpus_version,
            first_word_index=group[0].word_start,
            last_word_index=group[-1].word_end,
        )
        group_spans: list[SourceSpan] = []
        for window in group:
            span_id = make_source_span_id(
                guru_id=SHARED_GURU_ID,
                video_id=video_id,
                corpus_version=corpus_version,
                word_start=window.word_start,
                word_end=window.word_end,
                transcript_hash=transcript_hash,
            )
            group_spans.append(
                SourceSpan(
                    corpus_version=corpus_version,
                    guru_id=SHARED_GURU_ID,
                    video_id=video_id,
                    source_asset_id=video_id,
                    source_span_id=span_id,
                    parent_unit_id=parent_id,
                    turn_id=f"{video_id}:asr-window:{global_index}",
                    turn_index=global_index,
                    source_span_index=global_index,
                    start_ms=window.start_ms,
                    end_ms=window.end_ms,
                    word_start=window.word_start,
                    word_end=window.word_end,
                    speaker_id=SHARED_SPEAKER_ID,
                    speaker_role=SpeakerRole.UNKNOWN,
                    speaker_verified=False,
                    speaker_verification_status="pending_voice_check",
                    source_transcript_text=window.text,
                    verbatim_text=window.text,
                    transcript_hash=transcript_hash,
                    source_text_hash=clip_text_hash(window.text),
                    is_verbatim=True,
                    first_person_eligible=True,
                    chunker_version=CHUNKER_VERSION,
                    boundary_status=BoundaryStatus.VERIFIED,
                    completeness_status=CompletenessStatus.COMPLETE,
                    rights_cleared=True,
                    domain_rights_status=rights,
                    caption_status="auto_asr",
                    provenance_kind=ProvenanceKind.SPEECH_TURN_SPAN,
                    answer_role=AnswerRole.DIRECT,
                    source_url=canonical_url,
                    asr_engine=asr_engine,
                    asr_model_version=asr_model_version,
                    quality_status="auto_asr_candidate",
                    ingest_namespace=ingest_namespace,
                    source_artifact_sha256=source_artifact_sha256,
                )
            )
            global_index += 1

        group_spans = [
            span.model_copy(
                update={
                    "previous_span_id": group_spans[index - 1].source_span_id if index else None,
                    "next_span_id": (
                        group_spans[index + 1].source_span_id if index + 1 < len(group_spans) else None
                    ),
                }
            )
            for index, span in enumerate(group_spans)
        ]
        parent = ParentUnit(
            corpus_version=corpus_version,
            guru_id=SHARED_GURU_ID,
            video_id=video_id,
            parent_unit_id=parent_id,
            ordered_source_span_ids=tuple(span.source_span_id for span in group_spans),
            start_ms=min(span.start_ms for span in group_spans),
            end_ms=max(span.end_ms for span in group_spans),
            parent_text_hash=clip_text_hash(" ".join(span.verbatim_text for span in group_spans)),
            speaker_ids=(SHARED_SPEAKER_ID,),
            speaker_continuity=False,
            boundary_status=BoundaryStatus.VERIFIED,
            completeness_status=CompletenessStatus.COMPLETE,
            ingest_namespace=ingest_namespace,
        )
        parents.append(parent)
        spans.extend(group_spans)

    return parents, spans, rejected_count


def encode_vectors(embedding_service: Any, spans: Iterable[SourceSpan]) -> dict[str, dict[str, Any]]:
    span_list = list(spans)
    if not span_list:
        raise ValueError("cannot embed an empty span list")
    encoded = embedding_service.encode_batch([span.retrieval_text() for span in span_list])
    if not isinstance(encoded, Mapping):
        raise TypeError("encode_batch must return a mapping with dense and sparse vectors")
    dense = encoded.get("dense")
    sparse = encoded.get("sparse")
    if not isinstance(dense, (list, tuple)) or not isinstance(sparse, (list, tuple)):
        raise ValueError("encode_batch omitted dense or sparse vector rows")
    if len(dense) != len(span_list) or len(sparse) != len(span_list):
        raise ValueError("embedding row count does not match source span count")

    dense_rows: list[list[float]] = []
    expected_dim: int | None = None
    for row in dense:
        values = [float(value) for value in row]
        if not values or any(not math.isfinite(value) for value in values):
            raise ValueError("dense embedding is empty or contains a non-finite value")
        if expected_dim is None:
            expected_dim = len(values)
        elif len(values) != expected_dim:
            raise ValueError("dense embedding dimensions are inconsistent within the batch")
        dense_rows.append(values)

    return {
        span.source_span_id: {
            "passage_dense": dense_rows[index],
            "passage_sparse": _sparse_vector(sparse[index]),
        }
        for index, span in enumerate(span_list)
    }


def upsert_video(
    *,
    store: Any,
    embedding_service: Any,
    video_id: str,
    segments: Iterable[Mapping[str, Any]],
    source_url: str | None = None,
    ingest_namespace: str | None = None,
    asr_engine: str | None = None,
    asr_model_version: str | None = None,
    source_artifact_sha256: str | None = None,
    rights_resolver: Callable[..., str] = resolve_source_rights_status,
) -> dict[str, Any]:
    parents, spans, rejected_count = build_context_records(
        video_id=video_id,
        segments=segments,
        source_url=source_url,
        ingest_namespace=ingest_namespace,
        asr_engine=asr_engine,
        asr_model_version=asr_model_version,
        source_artifact_sha256=source_artifact_sha256,
        rights_resolver=rights_resolver,
    )
    vectors = encode_vectors(embedding_service, spans)
    store.ensure_indexes()
    spans_by_parent: dict[str, list[SourceSpan]] = {}
    for span in spans:
        spans_by_parent.setdefault(span.parent_unit_id, []).append(span)
    written = 0
    for parent in parents:
        children = spans_by_parent[parent.parent_unit_id]
        written += store.upsert(parent, children, vectors)
    return {
        "status": "ok",
        "video_id": video_id,
        "parent_units_indexed": len(parents),
        "spans_indexed": len(spans),
        "rejected_windows": rejected_count,
        "points_written": written,
        "source_url": spans[0].source_url,
    }
