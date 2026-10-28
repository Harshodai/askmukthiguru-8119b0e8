"""Tests for First-Person Harness Readability & Integrity (Phase 6 / fp-primary-quality-harness).

Pins:
1. Answer body contains zero "Related, not a direct answer:" headings.
2. Single-span antecedent join (T2c): When a hit span opens with demonstrative/pronoun ("this", "that", etc.),
   it joins the setup span from the same parent context.
3. Temporal span ordering (T4): Multi-span answers are ordered chronologically by start_ms ascending.
4. First-Person primary mode posture (T1/T5): config defaults first_person_primary_mode to True.
"""

from __future__ import annotations

import pytest

from app.config import settings
from domain.first_person_context import (
    AnswerRole,
    BoundaryStatus,
    CompletenessStatus,
    ParentContext,
    ParentUnit,
    ProvenanceKind,
    SourceSpan,
    SpeakerRole,
    clip_text_hash,
    make_source_span_id,
)
from services.first_person_context_harness import (
    FirstPersonContextHarness,
    HarnessPolicy,
    _span_starts_with_antecedent,
)


def _make_span(
    n: int,
    text: str,
    parent_id: str = "p1",
    start_ms: int | None = None,
    answer_role: AnswerRole = AnswerRole.DIRECT,
) -> SourceSpan:
    hash_val = "b" * 64
    start = 1000 * n if start_ms is None else start_ms
    end = start + 800
    span_id = make_source_span_id(
        guru_id="krishnaji",
        video_id="v1",
        corpus_version="ctx-v1",
        word_start=n * 10,
        word_end=n * 10 + 5,
        transcript_hash=hash_val,
    )
    return SourceSpan(
        corpus_version="ctx-v1",
        guru_id="krishnaji",
        video_id="v1",
        source_asset_id="v1",
        source_span_id=span_id,
        parent_unit_id=parent_id,
        turn_id=f"t{n}",
        turn_index=n,
        source_span_index=n,
        start_ms=start,
        end_ms=end,
        word_start=n * 10,
        word_end=n * 10 + 5,
        speaker_id="krishnaji",
        speaker_role=SpeakerRole.GURU,
        speaker_verified=True,
        source_transcript_text=text,
        verbatim_text=text,
        transcript_hash=hash_val,
        source_text_hash=clip_text_hash(text),
        boundary_status=BoundaryStatus.VERIFIED,
        completeness_status=CompletenessStatus.COMPLETE,
        rights_cleared=True,
        caption_status="auto",
        provenance_kind=ProvenanceKind.SPEECH_TURN_SPAN,
        answer_role=answer_role,
        source_url="https://youtube.com/watch?v=v1",
    )


def test_fp_primary_mode_default_is_true() -> None:
    """Invariant: first_person_primary_mode must be True by default."""
    assert getattr(settings, "first_person_primary_mode", True) is True


def test_span_starts_with_antecedent_detection() -> None:
    """Verifies detection of demonstratives, pronouns, and lowercase mid-thought openers."""
    span_this = _make_span(0, "This truth can set us free.")
    span_that = _make_span(1, "That is the fundamental error of the mind.")
    span_it = _make_span(2, "It happens when you are unaware.")
    span_clean = _make_span(3, "When you look deeply into the nature of sorrow.")
    span_non_antecedent = _make_span(4, "Meditation is freedom from all psychological division.")

    assert _span_starts_with_antecedent(span_this) is True
    assert _span_starts_with_antecedent(span_that) is True
    assert _span_starts_with_antecedent(span_it) is True
    assert _span_starts_with_antecedent(span_clean) is True  # 'when' is an antecedent opener
    assert _span_starts_with_antecedent(span_non_antecedent) is False


def test_antecedent_join_expands_single_span_window() -> None:
    """When a hit span begins with an antecedent opener and max_context_spans=1,

    the harness window includes the predecessor span to provide full context.
    """
    span0 = _make_span(0, "Suffering is self-centered activity.")
    span1 = _make_span(1, "This truth can set us free.")

    parent = ParentUnit(
        corpus_version="ctx-v1",
        guru_id="krishnaji",
        video_id="v1",
        parent_unit_id="p1",
        ordered_source_span_ids=(span0.source_span_id, span1.source_span_id),
        start_ms=0,
        end_ms=2000,
        parent_text_hash=clip_text_hash(f"{span0.verbatim_text} {span1.verbatim_text}"),
        speaker_ids=("krishnaji",),
        speaker_continuity=True,
        boundary_status=BoundaryStatus.VERIFIED,
        completeness_status=CompletenessStatus.COMPLETE,
    )

    ctx = ParentContext(
        parent=parent,
        spans=(span0, span1),
        hit_span_ids=(span1.source_span_id,),
    )

    policy = HarnessPolicy(max_context_spans=1)
    harness = FirstPersonContextHarness(policy=policy)
    window = harness._window(ctx)

    # Expanded to include predecessor span0
    assert len(window) == 2
    assert window[0].source_span_id == span0.source_span_id
    assert window[1].source_span_id == span1.source_span_id


def test_temporal_span_ordering_in_answer() -> None:
    """Spans returned out of chronological order are sorted by start_ms ascending."""
    span_late = _make_span(2, "Conclusion of the teaching.", start_ms=5000)
    span_mid = _make_span(1, "Deep explanation of the self.", start_ms=3000)
    span_early = _make_span(0, "Introduction and setup.", start_ms=1000)

    parent = ParentUnit(
        corpus_version="ctx-v1",
        guru_id="krishnaji",
        video_id="v1",
        parent_unit_id="p1",
        ordered_source_span_ids=(
            span_early.source_span_id,
            span_mid.source_span_id,
            span_late.source_span_id,
        ),
        start_ms=1000,
        end_ms=6000,
        parent_text_hash=clip_text_hash(
            f"{span_early.verbatim_text} {span_mid.verbatim_text} {span_late.verbatim_text}"
        ),
        speaker_ids=("krishnaji",),
        speaker_continuity=True,
        boundary_status=BoundaryStatus.VERIFIED,
        completeness_status=CompletenessStatus.COMPLETE,
    )

    # Context receives spans out of order: [late, early, mid]
    ctx = ParentContext(
        parent=parent,
        spans=(span_late, span_early, span_mid),
        hit_span_ids=(span_early.source_span_id,),
    )

    policy = HarnessPolicy(max_context_spans=3)
    harness = FirstPersonContextHarness(policy=policy)
    window = harness._window(ctx)

    # Ordered chronologically
    assert [s.start_ms for s in window] == [1000, 3000, 5000]


def test_answer_body_never_contains_ui_heading() -> None:
    """Verifies that served clips never contain 'Related, not a direct answer' in answer text."""
    span0 = _make_span(0, "When you look without the past, that observation is freedom.")
    parent = ParentUnit(
        corpus_version="ctx-v1",
        guru_id="krishnaji",
        video_id="v1",
        parent_unit_id="p1",
        ordered_source_span_ids=(span0.source_span_id,),
        start_ms=0,
        end_ms=1000,
        parent_text_hash=clip_text_hash(span0.verbatim_text),
        speaker_ids=("krishnaji",),
        speaker_continuity=True,
        boundary_status=BoundaryStatus.VERIFIED,
        completeness_status=CompletenessStatus.COMPLETE,
    )

    ctx = ParentContext(
        parent=parent,
        spans=(span0,),
        hit_span_ids=(span0.source_span_id,),
    )

    harness = FirstPersonContextHarness()
    decision = harness.decide(ctx, answerability="direct")
    assert decision.state.value == "SERVE"
    assert "Related, not a direct answer" not in decision.answer_text
    assert decision.answer_text == span0.verbatim_text
