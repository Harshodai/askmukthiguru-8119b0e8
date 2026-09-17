"""F2 regression: an attributed claim must never ship without a source.

GURU_DEMO_READINESS F2 — "What is the Beautiful State?" returned a sentence
attributing doctrine to the living Gurus by name with `citations=[]`,
`source_count=0`, `grounding_state=abstained`, while the pipeline's own trace
showed two grounded citation URLs that `extract_citations` had thrown away.

Every assertion below runs the SHIPPED functions. Nothing here re-implements
the logic it guards — a test that recomputes the rule would pass with the
module deleted, which has already happened twice in this repo (checkpoint §8
defect class 7).
"""

from __future__ import annotations

import asyncio
import inspect

import pytest

from rag.nodes import citation_extractor as ce
from rag.nodes import generation as gen
from services.voice import register as voice_register

# The exact sentence measured live on 2026-09-16.
F2_SENTENCE = (
    "Sri Preethaji & Sri Krishnaji teach that this state is not dependent on "
    "external achievements but emerges from inner transformation."
)
GROUNDED = ["https://www.youtube.com/watch?v=nwQaU-agzFE"]


def _doc(text: str, url: str = GROUNDED[0]) -> dict:
    return {"text": text, "source_url": url, "title": "The Beautiful State"}


# --------------------------------------------------------------------------
# 1. The structural floor: attributed sentence + zero citations is impossible
# --------------------------------------------------------------------------


def test_f2_sentence_is_recognised_as_an_attributed_claim():
    assert voice_register.is_attributed_claim(F2_SENTENCE) is True


def test_doctrine_noun_state_is_not_mistaken_for_the_verb():
    # "states" as a verb is an attribution; "state" as a noun is the doctrine
    # itself and appears in nearly every answer. Deleting those would turn the
    # guard into a censor.
    assert not voice_register.is_attributed_claim(
        "The Beautiful State is a state of inner calm and connection."
    )


def test_strip_removes_the_attribution_and_keeps_the_rest():
    body = (
        "The Beautiful State is an inner condition of calm and connection. "
        "It does not depend on what is happening around you, and it remains "
        "available in any circumstance you find yourself in today."
    )
    kept, removed = voice_register.strip_unsourced_attributions(f"{body} {F2_SENTENCE}")
    assert removed == 1
    assert F2_SENTENCE not in kept
    assert kept.startswith("The Beautiful State is an inner condition")


def test_refusal_naming_the_teachers_is_left_intact():
    assert voice_register.strip_unsourced_attributions(voice_register.NO_TEACHING_FOUND) == (
        voice_register.NO_TEACHING_FOUND,
        0,
    )


def _run_terminal_node(state: dict) -> dict:
    return asyncio.run(gen.format_final_answer(state))


def test_terminal_node_cannot_ship_an_unsourced_attribution():
    """Drive the real format_final_answer through the abstention fast path.

    That path is the measured F2 case: it returns `citations: []` and passes
    the model's prose through untouched.
    """
    state = {
        "answer": F2_SENTENCE,
        "citations": [],
        "grounding_state": "abstained",
        "intent": "QUERY",
        "relevant_docs": [],
        "verification": {"passed": True, "method": "no_context_short_circuit"},
    }
    result = _run_terminal_node(state)

    assert result["citations"] == []
    assert F2_SENTENCE not in result["final_answer"], (
        "an attributed claim shipped with zero citations: " + result["final_answer"]
    )
    assert result.get("attribution_floor_removed") == 1


def test_terminal_node_keeps_attribution_when_sources_are_present():
    """The guard must not fire on the product's intended voice.

    Option A (checkpoint §3) is third person WITH attributed quotes, so an
    attributed sentence backed by citations is correct output, not a defect.
    Drives the normal accepted path, not the abstention fast path.
    """
    body = (
        "The Beautiful State is an inner condition of calm and connection that "
        "does not depend on your circumstances. " + F2_SENTENCE
    )
    state = {
        "answer": body,
        "citations": list(GROUNDED),
        "intent": "QUERY",
        "query_tier": "standard",
        "is_faithful": True,
        "faithfulness_score": 0.9,
        "confidence_score": 9.0,
        "citations_verified": True,
        "relevant_docs": [_doc(_CHUNK)],
        "verification": {"passed": True, "method": "pipeline_verified", "citations_verified": True},
    }
    result = _run_terminal_node(state)
    assert result["citations"], "sourced answer lost its citations"
    assert "attribution_floor_removed" not in result
    assert "Sri Preethaji" in result["final_answer"]


def test_guard_wraps_the_terminal_node_itself():
    """Pin the wiring, not just the helper.

    If the decorator is removed from `format_final_answer`, this fails even
    though every helper test above still passes.
    """
    source = inspect.getsource(gen)
    assert "@_enforce_attribution_floor\nasync def format_final_answer" in source


# --------------------------------------------------------------------------
# 2. The citation floor: extract_citations must never downgrade to []
# --------------------------------------------------------------------------


def test_extract_citations_preserves_established_citations_on_zero_matches():
    """A faithful paraphrase that matches nothing must not empty the list."""
    state = {
        "answer": "Something entirely unrelated to the retrieved teaching text.",
        "relevant_docs": [_doc("deeksha soul sync ekam festival oneness blessing")],
        "citations": list(GROUNDED),
    }
    out = ce.extract_citations(state)
    assert out["citations"] == GROUNDED


def test_extract_citations_does_not_invent_sources_when_nothing_was_retrieved():
    state = {"answer": F2_SENTENCE, "relevant_docs": [], "citations": list(GROUNDED)}
    assert ce.extract_citations(state)["citations"] == []


def test_extract_citations_respects_explicitly_rejected_documents():
    state = {
        "answer": F2_SENTENCE,
        "selected_docs": [],
        "relevant_docs": [_doc("beautiful state")],
        "citations": list(GROUNDED),
    }
    assert ce.extract_citations(state)["citations"] == []


# --------------------------------------------------------------------------
# 3. The metric: a faithful paraphrase must be able to pass it
# --------------------------------------------------------------------------

# Shape and lengths taken from the 8 documents actually retrieved for
# "What is the Beautiful State?" on 2026-09-16 (491-1625 chars).
_CHUNK = (
    "The beautiful state is not something you achieve through external "
    "accomplishment. It emerges from an inner transformation, a shift in the "
    "way consciousness moves within you. When you are dependent on outer "
    "achievements for your sense of worth, you remain in the suffering state. "
    "Inner transformation is what makes the beautiful state available to you "
    "in any circumstance. " * 4
)


def test_faithful_paraphrase_clears_the_floor():
    from app.config import settings

    score = ce._span_overlap(F2_SENTENCE, _CHUNK)
    assert score >= settings.citation_span_overlap_floor, score


def test_off_domain_sentence_does_not_clear_the_floor():
    from app.config import settings

    score = ce._span_overlap(
        "The capital of France is Paris and the Eiffel Tower was completed in 1889.",
        _CHUNK,
    )
    assert score < settings.citation_span_overlap_floor, score


def test_metric_is_not_length_penalised():
    """The defect the old Jaccard had: score collapsing as the chunk grows.

    Containment of the same sentence must be unchanged when the chunk is
    concatenated with itself; Jaccard was roughly halved by that.
    """
    short = ce._span_overlap(F2_SENTENCE, _CHUNK)
    long = ce._span_overlap(F2_SENTENCE, _CHUNK + " " + _CHUNK + " " + _CHUNK)
    assert short == pytest.approx(long)


def test_extractor_emits_a_citation_for_a_faithful_paraphrase():
    """End to end through the shipped node, not through the metric alone."""
    state = {
        "answer": F2_SENTENCE,
        "relevant_docs": [_doc(_CHUNK)],
        "citations": [],
    }
    citations = ce.extract_citations(state)["citations"]
    assert citations, "a faithful paraphrase produced no citation"
    assert citations[0]["url"] == GROUNDED[0]
