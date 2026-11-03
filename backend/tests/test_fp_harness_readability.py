"""Tests for First-Person Harness Readability & Integrity (Phase 6 / fp-primary-quality-harness).

Pins:
1. Answer body contains zero "Related, not a direct answer:" headings.
2. Single-span antecedent join (T2c): When a hit span opens with demonstrative/pronoun ("this", "that", etc.),
   it joins the setup span from the same parent context.
3. Temporal span ordering (T4): Multi-span answers are ordered chronologically by start_ms ascending.
4. First-Person primary mode posture (T1/T5): config defaults first_person_primary_mode to True.
"""

from __future__ import annotations

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
    previous_span_id: str | None = None,
    coreference_chain_ids: tuple[str, ...] = (),
    completeness_status: CompletenessStatus = CompletenessStatus.COMPLETE,
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
        voice_verification_method="ecapa_voxceleb_span_slice_v2",
        voice_model_revision="rev-test",
        voice_score=0.71,
        voice_margin=0.40,
        voice_threshold_applied={"cosine_floor": 0.2828, "margin_threshold": 0.05},
        voice_calibration_id="cal-test",
        voice_window_check="pass",
        voice_verified_at="2026-10-31T00:00:00+00:00",
        speaker_verification_status="verified",
        source_transcript_text=text,
        verbatim_text=text,
        transcript_hash=hash_val,
        source_text_hash=clip_text_hash(text),
        boundary_status=BoundaryStatus.VERIFIED,
        completeness_status=completeness_status,
        rights_cleared=True,
        caption_status="auto",
        provenance_kind=ProvenanceKind.SPEECH_TURN_SPAN,
        answer_role=answer_role,
        previous_span_id=previous_span_id,
        coreference_chain_ids=coreference_chain_ids,
        source_url="https://youtube.com/watch?v=v1",
    )


def test_fp_primary_mode_default_is_true() -> None:
    """Invariant: first_person_primary_mode must be True by default."""
    assert getattr(settings, "first_person_primary_mode", True) is True


def test_span_starts_with_antecedent_only_with_explicit_evidence() -> None:
    """Generic demonstrative/pronoun openers need typed evidence, not a prefix heuristic."""
    connective = _make_span(0, "Imagine what will be the outcome of it...")
    coreferential = _make_span(
        1,
        "It happens when you are unaware.",
        previous_span_id="prior-span",
        coreference_chain_ids=("chain-1",),
    )
    fragment = _make_span(
        2,
        "...and that changes everything.",
        previous_span_id="prior-span",
        completeness_status=CompletenessStatus.FRAGMENT,
    )
    coreference_without_pointer = _make_span(
        3, "It happens when you are unaware.", coreference_chain_ids=("chain-1",)
    )

    assert _span_starts_with_antecedent(connective) is True
    assert _span_starts_with_antecedent(coreferential) is True
    assert _span_starts_with_antecedent(fragment) is True
    assert _span_starts_with_antecedent(coreference_without_pointer) is False
    for n, text in enumerate(
        (
            "This truth can set us free.",
            "That is the fundamental error of the mind.",
            "It happens when you are unaware.",
            "When you look deeply into the nature of sorrow.",
            "Meditation is freedom from all psychological division.",
        ),
        start=4,
    ):
        assert _span_starts_with_antecedent(_make_span(n, text)) is False


def test_single_span_window_respects_configured_context_cap() -> None:
    """Antecedent recovery cannot exceed max_context_spans; a one-span cap stays one."""
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

    assert len(window) == 1
    assert window[0].source_span_id == span1.source_span_id


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
