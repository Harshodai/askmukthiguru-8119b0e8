"""Decision-layer tests for the first-person context harness (phase D).

The harness owns one promise: whatever it returns as ``answer_text`` is exactly
the stored span text, in order, with citations that match span identity, text,
and audio offsets. Every gate is tested for both sides — pass and abstain.
"""

from __future__ import annotations

from domain.first_person_context import (
    AnswerRole,
    BoundaryStatus,
    CompletenessStatus,
    HarnessDecision,
    HarnessState,
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
    harness_enabled,
    policy_from_settings,
)

TEXT_ONE = "Suffering is a call to awaken."
TEXT_TWO = "It is not a punishment from existence."
HASH = "a" * 64


def span(n=0, text=None, **overrides):
    text = text or (TEXT_ONE if n == 0 else TEXT_TWO)
    word_start = overrides.pop("word_start", n * 10)
    word_end = overrides.pop("word_end", word_start + 6)
    parent_unit_id = overrides.pop("parent_unit_id", "parentA")
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
        "parent_unit_id": parent_unit_id,
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


def context(spans, **overrides):
    unique = []
    for s in spans:
        if s.source_span_id not in {u.source_span_id for u in unique}:
            unique.append(s)
    parent_kwargs = {
        "corpus_version": "ctx-v1",
        "guru_id": unique[0].guru_id,
        "video_id": unique[0].video_id,
        "parent_unit_id": unique[0].parent_unit_id,
        "ordered_source_span_ids": tuple(s.source_span_id for s in unique),
        "start_ms": unique[0].start_ms,
        "end_ms": unique[-1].end_ms,
        "parent_text_hash": clip_text_hash(" ".join(s.verbatim_text for s in unique)),
        "speaker_ids": ("krishnaji",),
        "speaker_continuity": True,
        "boundary_status": BoundaryStatus.VERIFIED,
        "completeness_status": CompletenessStatus.COMPLETE,
    }
    parent_kwargs.update(overrides)
    return ParentContext(
        parent=ParentUnit(**parent_kwargs),
        spans=tuple(unique),
        hit_span_ids=(unique[0].source_span_id,),
        score=0.9,
    )


def test_serves_single_span_when_answerable():
    harness = FirstPersonContextHarness()
    decision = harness.decide(context([span()]), answerability="yes")
    assert decision.decision is HarnessDecision.SERVE_SINGLE_SPAN
    assert decision.state is HarnessState.SERVE
    assert decision.answer_text == TEXT_ONE
    assert decision.answer_text_reconstructed
    assert decision.citations_verified
    assert decision.citations[0].start_ms == 0
    assert decision.citations[0].end_ms == 900
    assert decision.llm_used is False


def test_serves_parent_context_and_keeps_span_order():
    harness = FirstPersonContextHarness()
    decision = harness.decide(context([span(0), span(1)]), answerability="yes")
    assert decision.decision is HarnessDecision.SERVE_PARENT_CONTEXT
    assert decision.answer_text == f"{TEXT_ONE} {TEXT_TWO}"
    assert decision.source_span_ids == tuple(
        s.source_span_id for s in context([span(0), span(1)]).spans
    )
    assert len(decision.citations) == 2


def test_indeterminate_answerability_serves_related_not_direct():
    harness = FirstPersonContextHarness()
    decision = harness.decide(context([span()]), answerability="indeterminate")
    assert decision.decision is HarnessDecision.SERVE_RELATED_NOT_DIRECT
    assert decision.context_sufficiency == "sufficient"
    assert decision.answer_text == TEXT_ONE


def test_answerability_no_abstains():
    harness = FirstPersonContextHarness()
    decision = harness.decide(context([span()]), answerability="no")
    assert decision.decision is HarnessDecision.ABSTAIN
    assert decision.abstain_reason == "answerability_no"
    assert decision.answer_text is None
    assert decision.citations == ()


def test_unverified_speaker_abstains():
    harness = FirstPersonContextHarness()
    decision = harness.decide(context([span(speaker_verified=False)]), answerability="yes")
    assert decision.decision is HarnessDecision.ABSTAIN
    assert decision.abstain_reason == "speaker_unverified_or_not_guru"
    assert decision.gates["speaker"] is False


def test_host_role_never_served_as_guru_voice():
    harness = FirstPersonContextHarness()
    decision = harness.decide(context([span(speaker_role=SpeakerRole.HOST)]), answerability="yes")
    assert decision.decision is HarnessDecision.ABSTAIN
    assert decision.gates["speaker"] is False


def test_rights_gate_abstains():
    harness = FirstPersonContextHarness()
    decision = harness.decide(context([span(rights_cleared=False)]), answerability="yes")
    assert decision.decision is HarnessDecision.ABSTAIN
    assert decision.abstain_reason == "rights_not_cleared"


def test_hash_gate_abstains_on_mutated_text():
    harness = FirstPersonContextHarness()
    tampered = span().model_copy(update={"verbatim_text": TEXT_ONE + " (edited)"})
    decision = harness.decide(context([tampered]), answerability="yes")
    assert decision.decision is HarnessDecision.ABSTAIN
    assert decision.abstain_reason == "source_text_hash_mismatch"


def test_fragment_without_antecedent_abstains():
    harness = FirstPersonContextHarness()
    fragment = span(completeness_status=CompletenessStatus.FRAGMENT)
    decision = harness.decide(context([fragment]), answerability="yes")
    assert decision.decision is HarnessDecision.ABSTAIN
    assert decision.abstain_reason == "fragment_without_antecedent"


def test_fragment_with_adjacent_antecedent_is_servable():
    harness = FirstPersonContextHarness()
    first = span(0)
    second = span(1, completeness_status=CompletenessStatus.FRAGMENT)
    second = second.model_copy(update={"previous_span_id": first.source_span_id})
    decision = harness.decide(context([first, second]), answerability="yes")
    assert decision.decision is HarnessDecision.SERVE_PARENT_CONTEXT
    assert decision.gates["completeness"] is True


def test_cross_parent_contamination_abstains():
    harness = FirstPersonContextHarness()
    a = span(0)
    b = span(1, parent_unit_id="parentB")
    # ParentContext itself rejects this shape, so simulate a caller that built
    # the object without validation (e.g. a deserialized graph payload).
    contaminated = ParentContext.model_construct(
        parent=context([a]).parent,
        spans=(a, b),
        hit_span_ids=(a.source_span_id,),
        score=0.9,
    )
    decision = harness.decide(contaminated, answerability="yes")
    assert decision.decision is HarnessDecision.ABSTAIN
    assert decision.abstain_reason == "cross_parent_contamination"


def test_cross_guru_contamination_abstains():
    harness = FirstPersonContextHarness()
    decision = harness.decide(context([span()]), requested_teacher="preethaji", answerability="yes")
    assert decision.decision is HarnessDecision.ABSTAIN
    assert decision.abstain_reason == "cross_guru_contamination"


def test_coreference_without_antecedent_is_related_not_direct():
    harness = FirstPersonContextHarness()
    pronoun = span(coreference_chain_ids=("chain-1",))
    decision = harness.decide(context([pronoun]), answerability="yes")
    assert decision.decision is HarnessDecision.SERVE_RELATED_NOT_DIRECT
    assert decision.abstain_reason == "antecedent_missing"
    assert decision.context_sufficiency == "insufficient"


def test_coreference_with_antecedent_serves():
    harness = FirstPersonContextHarness()
    antecedent = span(
        0,
        text="The Greeks met suffering.",
        answer_role=AnswerRole.ANTECEDENT,
        coreference_chain_ids=("chain-1",),
    )
    pronoun = span(
        1,
        text="They emerged victorious.",
        coreference_chain_ids=("chain-1",),
    )
    pronoun = pronoun.model_copy(update={"previous_span_id": antecedent.source_span_id})
    decision = harness.decide(context([antecedent, pronoun]), answerability="yes")
    assert decision.decision is HarnessDecision.SERVE_PARENT_CONTEXT


def test_uncertain_boundary_is_related_not_direct():
    harness = FirstPersonContextHarness()
    decision = harness.decide(
        context([span(boundary_status=BoundaryStatus.UNCERTAIN)]), answerability="yes"
    )
    assert decision.decision is HarnessDecision.SERVE_RELATED_NOT_DIRECT
    assert decision.abstain_reason == "boundary_uncertain"


def test_answer_text_is_never_outside_the_spans():
    harness = FirstPersonContextHarness()
    decision = harness.decide(context([span(0), span(1)]), answerability="yes")
    for span_obj in context([span(0), span(1)]).spans:
        assert span_obj.verbatim_text in decision.answer_text


def test_answerability_no_wins_over_coreference_and_boundary_relaxation():
    harness = FirstPersonContextHarness()
    pronoun = span(
        coreference_chain_ids=("chain-1",),
        boundary_status=BoundaryStatus.UNCERTAIN,
    )
    decision = harness.decide(context([pronoun]), answerability="no")
    assert decision.decision is HarnessDecision.ABSTAIN
    assert decision.abstain_reason == "answerability_no"
    assert decision.answer_text is None
    assert decision.citations == ()


def test_related_text_with_unverified_citations_abstains(monkeypatch):
    harness = FirstPersonContextHarness()
    original = harness._citations

    def bad_citations(spans):
        cite = original(spans)[0]
        return (cite.model_copy(update={"text": "invented citation text"}),)

    monkeypatch.setattr(harness, "_citations", bad_citations)
    decision = harness.decide(
        context([span(boundary_status=BoundaryStatus.UNCERTAIN)]), answerability="yes"
    )
    assert decision.decision is HarnessDecision.ABSTAIN
    assert decision.abstain_reason == "citation_alignment_failed"
    assert decision.gates["citations_verified"] is False


def test_context_window_is_centered_on_the_first_hit_span():
    spans = [
        span(index, text=f"Teaching sentence number {index} stands alone.") for index in range(5)
    ]
    ctx = context(spans).model_copy(update={"hit_span_ids": (spans[3].source_span_id,)})
    decision = FirstPersonContextHarness().decide(ctx, answerability="yes")
    assert decision.source_span_ids == tuple(s.source_span_id for s in spans[2:5])


def test_context_window_falls_back_to_the_parent_head_without_a_hit():
    spans = [
        span(index, text=f"Teaching sentence number {index} stands alone.") for index in range(5)
    ]
    ctx = context(spans).model_copy(update={"hit_span_ids": ()})
    decision = FirstPersonContextHarness().decide(ctx, answerability="yes")
    assert decision.source_span_ids == tuple(s.source_span_id for s in spans[:3])


def test_context_window_is_bounded_by_policy():
    harness = FirstPersonContextHarness(HarnessPolicy(max_context_spans=1))
    decision = harness.decide(context([span(0), span(1)]), answerability="yes")
    assert decision.decision is HarnessDecision.SERVE_SINGLE_SPAN
    assert decision.answer_text == TEXT_ONE


def test_empty_context_abstains():
    harness = FirstPersonContextHarness()
    base = context([span()])
    empty = ParentContext(
        parent=base.parent, spans=(base.spans[0],), hit_span_ids=(base.spans[0].source_span_id,)
    )
    decision = harness.decide(empty.model_copy(update={"spans": ()}), answerability="yes")
    assert decision.decision is HarnessDecision.ABSTAIN
    assert decision.abstain_reason == "no_spans"


# --- phase-D wiring seam: settings are the single source of policy -----------


def test_harness_enabled_reads_the_settings_flag(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "first_person_context_harness_enabled", False)
    assert harness_enabled() is False
    monkeypatch.setattr(settings, "first_person_context_harness_enabled", True)
    assert harness_enabled() is True


def test_policy_from_settings_bounds_and_pins_max_spans(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "first_person_context_max_spans", 5)
    assert policy_from_settings().max_context_spans == 5
    # A misconfigured non-positive value must never disable the bound.
    monkeypatch.setattr(settings, "first_person_context_max_spans", 0)
    assert policy_from_settings().max_context_spans == 1


def test_contained_span_is_not_read_out_twice():
    long_text = f"{TEXT_ONE} {TEXT_TWO}"
    outer = span(0, text=long_text, end_ms=5000)
    inner = span(1, text=TEXT_TWO, start_ms=1000, end_ms=2000)
    decision = FirstPersonContextHarness().decide(context([outer, inner]), answerability="yes")
    assert decision.decision is HarnessDecision.SERVE_SINGLE_SPAN
    assert decision.answer_text == long_text
    assert decision.source_span_ids == (outer.source_span_id,)


def test_identical_text_spans_collapse_to_the_earlier_one():
    first = span(0)
    twin = span(1, text=TEXT_ONE, start_ms=4000, end_ms=4900)
    decision = FirstPersonContextHarness().decide(context([first, twin]), answerability="yes")
    assert decision.answer_text == TEXT_ONE
    assert decision.source_span_ids == (first.source_span_id,)


def test_distinct_spans_are_both_kept():
    decision = FirstPersonContextHarness().decide(context([span(0), span(1)]), answerability="yes")
    assert decision.answer_text == f"{TEXT_ONE} {TEXT_TWO}"
    assert len(decision.source_span_ids) == 2


def test_question_only_clip_abstains():
    text = (
        "How do we find a balance in a crazed world? "
        "How do you get over this feeling of being overwhelmed in everyday life?"
    )
    decision = FirstPersonContextHarness().decide(
        context([span(0, text=text)]), answerability="yes"
    )
    assert decision.decision is HarnessDecision.ABSTAIN
    assert decision.abstain_reason == "question_only_clip"
    assert decision.answer_text in (None, "")


def test_teaching_that_ends_on_a_question_is_still_served():
    text = f"{TEXT_ONE} So what is a Beautiful State?"
    decision = FirstPersonContextHarness().decide(
        context([span(0, text=text)]), answerability="yes"
    )
    assert decision.decision is HarnessDecision.SERVE_SINGLE_SPAN


def test_unpunctuated_text_is_never_judged_question_only():
    text = "how do we find a balance in a crazed world"
    decision = FirstPersonContextHarness().decide(
        context([span(0, text=text)]), answerability="yes"
    )
    assert decision.decision is HarnessDecision.SERVE_SINGLE_SPAN
