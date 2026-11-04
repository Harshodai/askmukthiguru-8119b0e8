"""Decision-layer tests for the first-person context harness (phase D).

The harness owns one promise: whatever it returns as ``answer_text`` is exactly
the stored span text, in order, with citations that match span identity, text,
and audio offsets. Every gate is tested for both sides — pass and abstain.
"""

from __future__ import annotations

import pytest

from domain.first_person_context import (
    _VALIDATED_EDGE_ISSUE_TOKEN,
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
    ValidatedCrossParentEdge,
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


@pytest.fixture(autouse=True)
def _synthetic_registry(monkeypatch):
    monkeypatch.setattr(
        "services.first_person_context_harness.source_is_authoritatively_licensed",
        lambda **kwargs: kwargs.get("domain_rights_status") == "licensed",
    )


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
        "voice_verification_method": "ecapa_voxceleb_span_slice_v2",
        "voice_model_revision": "synthetic-model-rev",
        "voice_score": 0.91,
        "voice_margin": 0.22,
        "voice_threshold_applied": {"cosine_floor": 0.75, "margin_threshold": 0.15},
        "voice_calibration_id": "synthetic-calibration-v1",
        "voice_window_check": "pass",
        "voice_verified_at": "2026-11-02T00:00:00Z",
        "speaker_verification_status": "verified",
        "source_transcript_text": text,
        "verbatim_text": text,
        "transcript_hash": HASH,
        "source_text_hash": clip_text_hash(text),
        "boundary_status": BoundaryStatus.VERIFIED,
        "completeness_status": CompletenessStatus.COMPLETE,
        "rights_cleared": True,
        "domain_rights_status": "licensed",
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


def test_canonical_rights_gate_abstains_when_legacy_boolean_is_true():
    harness = FirstPersonContextHarness()
    decision = harness.decide(
        context([span(rights_cleared=True, domain_rights_status="unverified")]),
        answerability="yes",
    )
    assert decision.decision is HarnessDecision.ABSTAIN
    assert decision.abstain_reason == "rights_not_cleared"


def test_missing_legacy_rights_status_defaults_unverified_and_abstains():
    payload = span().to_payload()
    payload.pop("record_type")
    payload.pop("domain_rights_status")
    legacy_span = SourceSpan.model_validate(payload)

    decision = FirstPersonContextHarness().decide(context([legacy_span]), answerability="yes")

    assert legacy_span.domain_rights_status == "unverified"
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


def test_uncertain_span_abstains_even_when_fragment_antecedent_relaxation_is_enabled():
    harness = FirstPersonContextHarness(HarnessPolicy(allow_fragment_with_antecedent=True))
    uncertain = span(completeness_status=CompletenessStatus.UNCERTAIN)

    decision = harness.decide(context([uncertain]), answerability="yes")

    assert decision.decision is HarnessDecision.ABSTAIN
    assert decision.abstain_reason == "fragment_without_antecedent"
    assert decision.gates["completeness"] is False


def test_uncertain_parent_unit_abstains_even_when_children_are_complete():
    harness = FirstPersonContextHarness(HarnessPolicy(allow_fragment_with_antecedent=True))

    decision = harness.decide(
        context([span()], completeness_status=CompletenessStatus.UNCERTAIN),
        answerability="yes",
    )

    assert decision.decision is HarnessDecision.ABSTAIN
    assert decision.abstain_reason == "fragment_without_antecedent"
    assert decision.gates["completeness"] is False


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


def test_trailing_question_only_span_is_dropped_from_the_answer():
    spans = [span(0), span(1, text="What is the Beautiful State really about?")]
    decision = FirstPersonContextHarness().decide(context(spans), answerability="yes")
    assert decision.decision is not HarnessDecision.ABSTAIN
    assert decision.answer_text == TEXT_ONE
    assert decision.source_span_ids == (spans[0].source_span_id,)


def test_trimmed_hit_span_abstains_rather_than_serving_unrelated_preceding_span():
    s0 = span(0)
    s1 = span(1, text="What is the Beautiful State really about?")
    ctx = context([s0, s1], ordered_source_span_ids=(s0.source_span_id, s1.source_span_id))
    ctx = ParentContext(
        parent=ctx.parent,
        spans=ctx.spans,
        hit_span_ids=(s1.source_span_id,),
        score=0.9,
    )
    decision = FirstPersonContextHarness().decide(ctx, answerability="yes")
    assert decision.decision is HarnessDecision.ABSTAIN
    assert decision.abstain_reason == "retrieved_hit_trimmed"


def test_bounded_abstain_reason_preserves_retrieved_hit_trimmed():
    from services.first_person_context_harness import _bounded_abstain_reason

    assert _bounded_abstain_reason("retrieved_hit_trimmed") == "retrieved_hit_trimmed"
    assert _bounded_abstain_reason("unknown_custom_reason") == "other"


def _decide(*texts):
    spans = [span(i, text=t) for i, t in enumerate(texts)]
    return FirstPersonContextHarness().decide(context(spans), answerability="yes")


def test_event_bound_span_abstains_not_standalone():
    d = _decide("Today, I want you to hold the intention that I bless you.")
    assert d.abstain_reason == "not_standalone"


def test_orphan_first_span_abstains_but_later_pronoun_span_is_fine():
    assert _decide("It refuses to drink that water.").abstain_reason == "not_standalone"
    ok = _decide(TEXT_ONE, TEXT_TWO)  # second span starts with "It"; antecedent span included
    assert ok.abstain_reason is None


def test_context_harness_rejects_dangling_question_tail():
    text = (
        "Suffering is a call to awaken. It is a moment of quiet attention that lets us "
        "observe the mind without choosing and notice its movement carefully. But how can we?"
    )
    decision = FirstPersonContextHarness().decide(
        context([span(0, text=text)]), answerability="yes"
    )
    assert decision.decision is HarnessDecision.ABSTAIN
    assert decision.abstain_reason == "not_standalone"


def test_context_harness_excludes_unsolicited_self_harm_context():
    text = (
        "When a person is experiencing suicidal thoughts, it is important to reach out to a "
        "qualified professional and stay close to someone who can offer immediate care."
    )
    decision = FirstPersonContextHarness().decide(
        context([span(0, text=text)]),
        query="How can I find inner peace?",
        answerability="yes",
    )
    assert decision.decision is HarnessDecision.ABSTAIN
    assert decision.abstain_reason == "unsolicited_self_harm_reference"
    assert HarnessState.CONTEXTUAL_SAFETY_GATE in decision.state_path


# ---------------------------------------------------------------------------
# T2c / T4 pins (plan fp-primary-quality-harness-2026-10-27)
# ---------------------------------------------------------------------------


def test_single_span_window_never_expands_past_the_strict_bound():
    """A one-span policy cannot be widened by an antecedent heuristic."""
    setup = span(0, text="Suffering is a call to awaken.")
    opener = span(1, text="This truth can set us free.")
    ctx = context([setup, opener]).model_copy(update={"hit_span_ids": (opener.source_span_id,)})

    decision = FirstPersonContextHarness(HarnessPolicy(max_context_spans=1)).decide(
        ctx, answerability="yes"
    )

    assert decision.source_span_ids == (opener.source_span_id,)
    assert decision.decision is HarnessDecision.SERVE_SINGLE_SPAN
    assert decision.answer_text == opener.verbatim_text
    assert decision.answer_text_reconstructed


def test_single_span_window_stays_single_when_no_antecedent_opener():
    """The widening is conditional: a self-contained hit is not padded."""
    setup = span(0, text="Suffering is a call to awaken.")
    standalone = span(1, text="Awareness meets it without resistance.")
    ctx = context([setup, standalone]).model_copy(
        update={"hit_span_ids": (standalone.source_span_id,)}
    )

    decision = FirstPersonContextHarness(HarnessPolicy(max_context_spans=1)).decide(
        ctx, answerability="yes"
    )

    assert decision.source_span_ids == (standalone.source_span_id,)
    assert decision.decision is HarnessDecision.SERVE_SINGLE_SPAN


def test_window_is_chronological_when_spans_arrive_out_of_order():
    """T4: a multi-span answer is always in ``start_ms`` order, regardless of the
    order retrieval or a selector handed the spans over."""
    first = span(0, text="Suffering is a call to awaken.")
    second = span(1, text="It is not a punishment from existence.")
    third = span(2, text="Awareness meets it without resistance.")
    shuffled = context([first, second, third]).model_copy(
        update={
            "spans": (third, first, second),
            "hit_span_ids": (second.source_span_id,),
        }
    )

    decision = FirstPersonContextHarness().decide(shuffled, answerability="yes")

    assert decision.source_span_ids == (
        first.source_span_id,
        second.source_span_id,
        third.source_span_id,
    )
    assert decision.decision is HarnessDecision.SERVE_PARENT_CONTEXT
    assert decision.answer_text.startswith(first.verbatim_text)
    assert decision.answer_text.endswith(third.verbatim_text)


def test_word_budget_trims_a_long_window_without_dropping_the_hit():
    """T2c: a word budget, not just a span count. Text is never edited, and the
    hit survives while a legal alternative exists."""
    long_text = " ".join(
        ["the river of awareness moves through every form without clinging to any of them"] * 25
    )
    first = span(0, text=long_text)
    hit = span(1, text="This truth can set us free.")
    third = span(2, text=long_text)
    ctx = context([first, hit, third]).model_copy(update={"hit_span_ids": (hit.source_span_id,)})

    decision = FirstPersonContextHarness(
        HarnessPolicy(max_context_spans=3, max_context_words=400)
    ).decide(ctx, answerability="yes")

    served = decision.answer_text
    assert hit.verbatim_text in served
    assert len(served.split()) <= 400 + len(hit.verbatim_text.split())
    assert decision.answer_text_reconstructed


def test_word_budget_is_not_applied_below_the_limit():
    first = span(0, text="Suffering is a call to awaken.")
    second = span(1, text="It is not a punishment from existence.")
    ctx = context([first, second])

    decision = FirstPersonContextHarness(
        HarnessPolicy(max_context_spans=3, max_context_words=600)
    ).decide(ctx, answerability="yes")

    assert decision.source_span_ids == (first.source_span_id, second.source_span_id)


GARBAGE_MIXED = (
    "کہ Ift my addiction isn't even physicalyфصل and then the rest of this long sentence"
)
GARBAGE_LOOP = "तुई अवेखन अवाँँँँँँ"


def test_mixed_script_garbage_is_refused_even_with_every_label_true():
    """D1: nine live v10 spans were ASR garbage carrying every positive label.

    The refusal must come from the text itself: no quality blocklist or
    allowlist is configured here, so nothing but the text gate can stop it.
    """
    harness = FirstPersonContextHarness()
    decision = harness.decide(context([span(text=GARBAGE_MIXED)]), answerability="yes")
    assert decision.decision is HarnessDecision.ABSTAIN
    assert decision.abstain_reason == "asr_script_garbage"
    assert decision.answer_text is None
    assert decision.citations == ()


def test_combining_mark_loop_is_refused_even_with_every_label_true():
    harness = FirstPersonContextHarness()
    decision = harness.decide(context([span(text=GARBAGE_LOOP)]), answerability="yes")
    assert decision.decision is HarnessDecision.ABSTAIN
    assert decision.abstain_reason == "asr_script_garbage"


def test_clean_english_span_still_serves_after_the_text_gate():
    harness = FirstPersonContextHarness()
    decision = harness.decide(context([span()]), answerability="yes")
    assert decision.decision is HarnessDecision.SERVE_SINGLE_SPAN


def test_serve_gate_refuses_a_wholly_devanagari_span_in_the_english_corpus():
    harness = FirstPersonContextHarness()
    text = "और वागशी है, तो वोगशी है. तुटिट ठीटने भी इलिटकी"
    decision = harness.decide(context([span(text=text)]), answerability="yes")
    assert decision.decision is HarnessDecision.ABSTAIN
    assert decision.abstain_reason == "asr_script_garbage"


def test_serve_gate_refuses_two_stray_arabic_letters_in_a_latin_span():
    harness = FirstPersonContextHarness()
    text = (
        "Only these are destroying you slowly. Every addiction damages the brain. "
        "I want you to know,every addiction chips away at your self world. "
        "د Database because youد my poems every addiction makes hard."
    )
    decision = harness.decide(context([span(text=text)]), answerability="yes")
    assert decision.decision is HarnessDecision.ABSTAIN
    assert decision.abstain_reason == "asr_script_garbage"


def test_legacy_payload_without_a_language_still_parses():
    """The language field is optional: every v10 payload built before it exists must parse."""
    payload = span().model_dump(mode="json")
    payload.pop("language", None)
    assert SourceSpan.model_validate(payload).language is None


def test_missing_speaker_provenance_is_refused_even_when_verified_flag_is_true():
    s = span(0, voice_verification_method=None)
    decision = FirstPersonContextHarness().decide(context([s]), answerability="yes")
    assert decision.decision is HarnessDecision.ABSTAIN
    assert decision.abstain_reason == "speaker_unverified_or_not_guru"


def test_unknown_speaker_provenance_method_is_refused():
    s = span(0, voice_verification_method="unregistered_method")
    decision = FirstPersonContextHarness().decide(context([s]), answerability="yes")
    assert decision.decision is HarnessDecision.ABSTAIN
    assert decision.abstain_reason == "speaker_unverified_or_not_guru"


def test_voice_method_requirement_withholds_a_bare_flag_and_serves_a_verified_one():
    policy = HarnessPolicy(require_voice_method=True)
    bare = span(0, voice_verification_method=None)
    abstained = FirstPersonContextHarness(policy).decide(context([bare]), answerability="yes")
    assert abstained.decision is HarnessDecision.ABSTAIN
    assert abstained.abstain_reason == "speaker_unverified_or_not_guru"

    verified = span(0, voice_verification_method="ecapa_voxceleb_span_slice_v2")
    served = FirstPersonContextHarness(policy).decide(context([verified]), answerability="yes")
    assert served.decision is HarnessDecision.SERVE_SINGLE_SPAN


def test_policy_from_settings_reads_the_voice_method_flag(monkeypatch):
    from app.config import settings
    from services.first_person_context_harness import policy_from_settings

    monkeypatch.setattr(settings, "first_person_require_voice_method", True)
    assert policy_from_settings().require_voice_method is True
    monkeypatch.setattr(settings, "first_person_require_voice_method", False)
    assert policy_from_settings().require_voice_method is False


def _cross_parent_harness_pair(**opener_overrides):
    predecessor = span(
        0,
        text="The river of awareness moves without resistance.",
        parent_unit_id="previous-parent",
        start_ms=1000,
        end_ms=1900,
        word_start=0,
        word_end=6,
    )
    opener = span(
        1,
        text="Imagine what will be the outcome of it, when attention remains clear.",
        parent_unit_id="current-parent",
        start_ms=2000,
        end_ms=2900,
        word_start=10,
        word_end=16,
        previous_span_id=predecessor.source_span_id,
        **opener_overrides,
    )
    predecessor = predecessor.model_copy(update={"next_span_id": opener.source_span_id})
    return predecessor, opener


def _cross_parent_edge(predecessor, opener):
    return ValidatedCrossParentEdge._issue(
        predecessor,
        opener,
        predecessor_parent_end_ms=predecessor.end_ms,
        opener_parent_start_ms=opener.start_ms,
        issue_token=_VALIDATED_EDGE_ISSUE_TOKEN,
    )


def test_validated_cross_parent_predecessor_is_gated_and_reconstructed_before_serve():
    predecessor, opener = _cross_parent_harness_pair()
    decision = FirstPersonContextHarness().decide(
        context([opener]),
        answerability="yes",
        validated_predecessor=_cross_parent_edge(predecessor, opener),
    )

    assert decision.decision is HarnessDecision.SERVE_PARENT_CONTEXT
    assert decision.source_span_ids == (predecessor.source_span_id, opener.source_span_id)
    assert decision.answer_text == f"{predecessor.verbatim_text} {opener.verbatim_text}"
    assert decision.gates["speaker"] is True
    assert decision.gates["rights"] is True
    assert decision.gates["contextual_safety"] is True


def test_validated_cross_parent_predecessor_allows_indices_reset_at_parent_boundary():
    predecessor, opener = _cross_parent_harness_pair()
    predecessor = predecessor.model_copy(update={"source_span_index": 0})
    opener = opener.model_copy(update={"source_span_index": 0})
    decision = FirstPersonContextHarness().decide(
        context([opener]),
        answerability="yes",
        validated_predecessor=_cross_parent_edge(predecessor, opener),
    )

    assert decision.decision is HarnessDecision.SERVE_PARENT_CONTEXT
    assert decision.source_span_ids == (predecessor.source_span_id, opener.source_span_id)
    assert decision.answer_text == f"{predecessor.verbatim_text} {opener.verbatim_text}"


def test_cross_parent_predecessor_refuses_when_the_strict_cap_has_no_reserved_slot():
    predecessor, opener = _cross_parent_harness_pair()
    decision = FirstPersonContextHarness(HarnessPolicy(max_context_spans=1)).decide(
        context([opener]),
        answerability="yes",
        validated_predecessor=_cross_parent_edge(predecessor, opener),
    )

    assert decision.decision is HarnessDecision.ABSTAIN
    assert decision.abstain_reason == "context_span_limit"


def test_cross_parent_combined_body_runs_one_contextual_safety_gate(monkeypatch):
    predecessor, opener = _cross_parent_harness_pair()
    calls: list[str] = []

    class Safety:
        def __init__(self, may_serve):
            self.may_serve = may_serve
            self.reason_codes = ("violent_relationship_context",) if not may_serve else ()

    def assess(_query, body, retrieval_query=""):
        calls.append(body)
        return Safety(body == predecessor.verbatim_text or body == opener.verbatim_text)

    monkeypatch.setattr(
        "services.first_person_context_harness.first_person_evidence_policy.assess_contextual_safety",
        assess,
    )
    decision = FirstPersonContextHarness().decide(
        context([opener]),
        answerability="yes",
        validated_predecessor=_cross_parent_edge(predecessor, opener),
    )

    assert decision.decision is HarnessDecision.ABSTAIN
    assert decision.abstain_reason == "violent_relationship_context"
    assert calls[-1] == f"{predecessor.verbatim_text} {opener.verbatim_text}"


def test_raw_predecessor_source_span_is_not_a_validated_edge():
    predecessor, opener = _cross_parent_harness_pair()
    decision = FirstPersonContextHarness().decide(
        context([opener]), answerability="yes", validated_predecessor=predecessor
    )
    assert decision.decision is HarnessDecision.ABSTAIN
    assert decision.abstain_reason == "antecedent_missing"


def test_selector_cannot_drop_or_move_the_opener_while_retaining_predecessor():
    predecessor, opener = _cross_parent_harness_pair()
    later = span(
        2,
        text="Awareness can remain open without effort.",
        parent_unit_id="current-parent",
        start_ms=3000,
        end_ms=3900,
        word_start=20,
        word_end=26,
    )
    ctx = context([opener, later]).model_copy(update={"hit_span_ids": (opener.source_span_id,)})
    decision = FirstPersonContextHarness().decide(
        ctx,
        answerability="yes",
        selected_span_ids=(later.source_span_id,),
        validated_predecessor=_cross_parent_edge(predecessor, opener),
    )
    assert decision.decision is HarnessDecision.SERVE_PARENT_CONTEXT
    assert decision.source_span_ids == (
        predecessor.source_span_id,
        opener.source_span_id,
        later.source_span_id,
    )


def test_antecedent_opener_hit_need_not_be_first_ranked_hit():
    predecessor, opener = _cross_parent_harness_pair()
    later = span(
        2,
        text="Awareness can remain open without effort.",
        parent_unit_id="current-parent",
        start_ms=3000,
        end_ms=3900,
        word_start=20,
        word_end=26,
    )
    ctx = context([opener, later]).model_copy(
        update={"hit_span_ids": (later.source_span_id, opener.source_span_id)}
    )
    decision = FirstPersonContextHarness().decide(
        ctx,
        answerability="yes",
        validated_predecessor=_cross_parent_edge(predecessor, opener),
    )

    assert decision.decision is HarnessDecision.SERVE_PARENT_CONTEXT
    assert decision.source_span_ids[:2] == (
        predecessor.source_span_id,
        opener.source_span_id,
    )


def test_same_parent_non_first_hit_keeps_its_bounded_predecessor():
    predecessor = span(
        0,
        text="The river of awareness moves without resistance.",
    )
    opener = span(
        1,
        text="Imagine what will be the outcome of it, when attention remains clear.",
        previous_span_id=predecessor.source_span_id,
    )
    predecessor = predecessor.model_copy(update={"next_span_id": opener.source_span_id})
    later = span(2, text="Awareness can remain open without effort.")
    ctx = context([predecessor, opener, later]).model_copy(
        update={"hit_span_ids": (opener.source_span_id,)}
    )

    decision = FirstPersonContextHarness(HarnessPolicy(max_context_spans=2)).decide(
        ctx, answerability="yes"
    )

    assert decision.decision is HarnessDecision.SERVE_PARENT_CONTEXT
    assert decision.source_span_ids == (predecessor.source_span_id, opener.source_span_id)
    assert decision.answer_text == f"{predecessor.verbatim_text} {opener.verbatim_text}"


def test_cross_parent_overlapping_span_cannot_deduplicate_the_validated_opener():
    predecessor, opener = _cross_parent_harness_pair()
    overlapping = span(
        2,
        text="The river of awareness moves without resistance, and attention remains clear.",
        parent_unit_id="current-parent",
        start_ms=1500,
        end_ms=3500,
        word_start=8,
        word_end=20,
    )
    ctx = context([opener, overlapping]).model_copy(
        update={"hit_span_ids": (opener.source_span_id,)}
    )

    decision = FirstPersonContextHarness().decide(
        ctx,
        answerability="yes",
        validated_predecessor=_cross_parent_edge(predecessor, opener),
    )

    assert decision.decision is HarnessDecision.ABSTAIN
    assert decision.abstain_reason == "antecedent_missing"


def test_cross_parent_opener_removed_by_question_trim_abstains():
    predecessor = span(
        0,
        text="The river of awareness moves without resistance.",
        parent_unit_id="previous-parent",
        start_ms=1000,
        end_ms=1900,
        word_start=0,
        word_end=6,
    )
    opener = span(
        1,
        text="Imagine what will be the outcome of it?",
        parent_unit_id="current-parent",
        start_ms=2000,
        end_ms=2900,
        word_start=10,
        word_end=16,
        previous_span_id=predecessor.source_span_id,
    )
    predecessor = predecessor.model_copy(update={"next_span_id": opener.source_span_id})

    decision = FirstPersonContextHarness().decide(
        context([opener]),
        answerability="yes",
        validated_predecessor=_cross_parent_edge(predecessor, opener),
    )

    assert decision.decision is HarnessDecision.ABSTAIN
    assert decision.abstain_reason == "antecedent_missing"


def test_ordinary_when_that_it_they_openers_do_not_activate_cross_parent_recovery():
    from services.first_person_context_harness import _span_starts_with_antecedent

    for text in (
        "When attention is steady, the mind becomes quiet.",
        "That is a complete teaching about presence and suffering.",
        "It is a complete teaching about presence and suffering.",
        "They are the witnesses of their own attention and presence.",
    ):
        candidate = span(1, text=text, parent_unit_id="current-parent", previous_span_id="missing")
        assert not _span_starts_with_antecedent(candidate)
