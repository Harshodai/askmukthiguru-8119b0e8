"""Contract tests for fp-context-v1 (phase B of the context harness plan).

These tests are intentionally model-level only: no Qdrant, no LLM, no network.
They pin the properties the plan makes load-bearing — deterministic identity,
fail-closed payloads, parent/child agreement, and servable-only-for-approved
annotations.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from domain.first_person_context import (
    AnnotationStatus,
    AnswerRole,
    BoundaryStatus,
    CitationSpan,
    CompletenessStatus,
    ContextEdge,
    EdgeStatus,
    EdgeType,
    EntityAnnotation,
    LinkType,
    ParentContext,
    ParentUnit,
    ProvenanceKind,
    SourceSpan,
    SpeakerRole,
    clip_text_hash,
    make_edge_id,
    make_parent_unit_id,
    make_source_span_id,
)

TEXT = "Suffering is a call to awaken, not a punishment."
HASH = "a" * 64


def span(**overrides):
    n = overrides.pop("n", 0)
    text = overrides.pop("verbatim_text", TEXT)
    word_start = overrides.pop("word_start", n * 10)
    word_end = overrides.pop("word_end", word_start + 6)
    data = {
        "corpus_version": "ctx-v1",
        "guru_id": "krishnaji",
        "video_id": "vidA",
        "source_asset_id": "vidA",
        "source_span_id": make_source_span_id(
            guru_id="krishnaji",
            video_id="vidA",
            corpus_version="ctx-v1",
            word_start=word_start,
            word_end=word_end,
            transcript_hash=HASH,
        ),
        "parent_unit_id": "parentA",
        "turn_id": f"turn{n}",
        "turn_index": n,
        "source_span_index": n,
        "start_ms": 1000 * n,
        "end_ms": 1000 * n + 900,
        "word_start": word_start,
        "word_end": word_end,
        "speaker_id": "krishnaji",
        "speaker_role": SpeakerRole.GURU,
        "speaker_verified": True,
        "source_transcript_text": text,
        "verbatim_text": text,
        "transcript_hash": HASH,
        "source_text_hash": clip_text_hash(text),
        "boundary_status": BoundaryStatus.VERIFIED,
        "completeness_status": CompletenessStatus.COMPLETE,
        "rights_cleared": True,
        "caption_status": "auto",
        "provenance_kind": ProvenanceKind.SPEECH_TURN_SPAN,
        "source_url": "https://www.youtube.com/watch?v=vidA",
        "answer_role": AnswerRole.DIRECT,
    }
    data.update(overrides)
    return SourceSpan(**data)


def parent(spans, **overrides):
    data = {
        "corpus_version": "ctx-v1",
        "guru_id": "krishnaji",
        "video_id": "vidA",
        "parent_unit_id": "parentA",
        "ordered_source_span_ids": tuple(s.source_span_id for s in spans),
        "start_ms": spans[0].start_ms,
        "end_ms": spans[-1].end_ms,
        "parent_text_hash": clip_text_hash(" ".join(s.verbatim_text for s in spans)),
        "speaker_ids": ("krishnaji",),
        "speaker_continuity": True,
        "boundary_status": BoundaryStatus.VERIFIED,
        "completeness_status": CompletenessStatus.COMPLETE,
    }
    data.update(overrides)
    return ParentUnit(**data)


def test_ids_are_deterministic_and_position_sensitive():
    kwargs = dict(
        guru_id="krishnaji",
        video_id="vidA",
        corpus_version="ctx-v1",
        word_start=0,
        word_end=6,
        transcript_hash=HASH,
    )
    assert make_source_span_id(**kwargs) == make_source_span_id(**kwargs)
    moved = dict(kwargs, word_start=6, word_end=12)
    assert make_source_span_id(**kwargs) != make_source_span_id(**moved)
    other_teacher = dict(kwargs, guru_id="preethaji")
    assert make_source_span_id(**kwargs) != make_source_span_id(**other_teacher)

    parent_id = make_parent_unit_id(
        guru_id="krishnaji",
        video_id="vidA",
        corpus_version="ctx-v1",
        first_word_index=0,
        last_word_index=12,
    )
    assert len(parent_id) == 64

    edge_id = make_edge_id(
        corpus_version="ctx-v1", from_span_id="a", to_span_id="b", edge_type="next"
    )
    assert edge_id == make_edge_id(
        corpus_version="ctx-v1", from_span_id="a", to_span_id="b", edge_type="next"
    )


def test_span_rejects_wrong_deterministic_id():
    with pytest.raises(ValidationError, match="deterministic id"):
        span(source_span_id="0" * 64)


def test_span_rejects_unknown_field():
    with pytest.raises(ValidationError):
        span(provider_generated_summary="the guru says everything is fine")


def test_span_rejects_text_hash_mismatch():
    with pytest.raises(ValidationError, match="source_text_hash"):
        span(source_text_hash="b" * 64)


def test_span_rejects_inverted_audio_and_word_ranges():
    with pytest.raises(ValidationError, match="end_ms"):
        span(start_ms=5000, end_ms=5000)
    with pytest.raises(ValidationError, match="word_end"):
        span(word_start=10, word_end=10)


def test_span_requires_boolean_verbatim():
    with pytest.raises(ValidationError):
        span(is_verbatim=False)


def test_payload_round_trip_is_strict():
    s = span()
    payload = s.to_payload()
    assert payload["record_type"] == "retrieval_child"
    payload.pop("record_type")
    assert SourceSpan.model_validate(payload) == s


def test_retrieval_text_keeps_verbatim_as_the_record():
    s = span()
    text = s.retrieval_text("Context: on suffering")
    assert text.endswith(s.verbatim_text)
    assert s.verbatim_text == TEXT


def test_parent_rejects_duplicate_spans_and_inverted_window():
    s = span()
    with pytest.raises(ValidationError, match="must not repeat"):
        parent([s], ordered_source_span_ids=(s.source_span_id, s.source_span_id))
    with pytest.raises(ValidationError, match="end_ms"):
        parent([s], start_ms=5000, end_ms=4000)


def test_context_edge_must_connect_distinct_spans():
    with pytest.raises(ValidationError, match="distinct"):
        ContextEdge(
            edge_id="e1",
            guru_id="krishnaji",
            video_id="vidA",
            from_span_id="s1",
            to_span_id="s1",
            edge_type=EdgeType.NEXT,
            status=EdgeStatus.CANDIDATE,
            confidence=0.5,
            created_by="test",
            annotation_version="v1",
        )


def test_only_deterministic_or_reviewed_edges_are_servable():
    for status, expected in (
        (EdgeStatus.DETERMINISTIC, True),
        (EdgeStatus.REVIEWED, True),
        (EdgeStatus.CANDIDATE, False),
    ):
        edge = ContextEdge(
            edge_id=make_edge_id(
                corpus_version="ctx-v1",
                from_span_id="s1",
                to_span_id="s2",
                edge_type="next",
            ),
            guru_id="krishnaji",
            video_id="vidA",
            from_span_id="s1",
            to_span_id="s2",
            edge_type=EdgeType.NEXT,
            status=status,
            confidence=0.9,
            created_by="test",
            annotation_version="v1",
        )
        assert edge.is_servable is expected


def test_annotations_only_servable_when_approved():
    base = dict(
        annotation_id="a1",
        guru_id="krishnaji",
        video_id="vidA",
        span_id="s1",
        surface_form="the Greeks",
        entity_id="entity:greeks",
        link_type=LinkType.NAME,
        confidence=0.8,
        created_by="test",
        annotation_version="v1",
    )
    assert EntityAnnotation(status=AnnotationStatus.APPROVED, **base).is_servable
    assert not EntityAnnotation(status=AnnotationStatus.CANDIDATE, **base).is_servable


def test_parent_context_rejects_foreign_span():
    a = span()
    b = span(n=1, parent_unit_id="parentB")
    with pytest.raises(ValidationError, match="parent unit"):
        ParentContext(
            parent=parent([a]),
            spans=(a, b),
            hit_span_ids=(a.source_span_id,),
        )


def test_parent_context_rejects_unknown_hit_id():
    a = span()
    with pytest.raises(ValidationError, match="hit_span_ids"):
        ParentContext(
            parent=parent([a]),
            spans=(a,),
            hit_span_ids=("not-a-span",),
        )


def test_citation_span_has_no_free_text_field():
    with pytest.raises(ValidationError):
        CitationSpan(
            source_span_id="s1",
            video_id="vidA",
            guru_id="krishnaji",
            text="an invented paraphrase",
            start_ms=0,
            end_ms=10,
            source_url="https://example.invalid",
            attribution_style="guru",
        )
