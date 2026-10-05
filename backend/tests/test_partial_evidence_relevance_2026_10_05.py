"""The excerpt fallback ("let me give you theirs directly") showed the wrong text.

Live probes, 2026-10-04/05:
- A Hindi question about anger got an OKF entry's markdown headings plus
  "Did you know that self-harm is the leading cause of death..." -- the first
  360 characters of the top doc, unrelated to anger.
- "What is the capital of France?" got an Ekam excerpt labelled grounded,
  although the cross-encoder scored every doc below ``rerank_min_score``.
- An LLM-written summary was offered as the teachers' own words.
"""

from app.config import settings
from rag.nodes.generation import (
    _grounded_partial_answer,
    _partial_evidence_kwargs,
    _source_kind_label,
)

URL = "https://www.youtube.com/watch?v=abc123"


def _doc(text, **extra):
    return {"text": text, "title": "On Anger", "source_url": URL, **extra}


def _body(answer):
    return answer.split("\n", 1)[1]


def test_markdown_headings_and_repeated_title_are_not_quoted():
    doc = _doc(
        "On Anger\n# On Anger\n## Verbatim Discourse Excerpts\n"
        "When anger rises, simply observe it without judging yourself."
    )
    answer, _ = _grounded_partial_answer([doc], question="How do I handle anger?")
    assert "#" not in answer
    assert "Verbatim Discourse Excerpts" not in answer
    assert "On Anger When anger" not in answer
    assert "When anger rises, simply observe it" in answer


def test_okf_notes_and_machine_summaries_are_never_offered_as_their_words():
    okf = _doc("Summary\nBased on the provided transcripts, anger is...", knowledge_source="okf")
    summary = _doc(
        "The host welcomes Sri Krishnaji and they discuss anger.",
        chunk_provenance="machine_summary",
    )
    raptor = _doc("An overview of anger across talks.", raptor_level=1)
    assert _grounded_partial_answer([okf, summary, raptor], question="anger") is None


def test_unsolicited_self_harm_passage_is_skipped():
    harm = _doc(
        "Did you know that self-harm is the leading cause of death for people aged 15 to 44?"
    )
    anger = _doc("Anger is a suffering state. Observe it and it loses its grip.")
    answer, citations = _grounded_partial_answer([harm, anger], question="How to control anger?")
    assert "self-harm" not in answer
    assert "loses its grip" in answer


def test_self_harm_passage_allowed_when_the_seeker_raised_it():
    harm = _doc("When a person thinks of suicide, connection is the balm that heals.")
    result = _grounded_partial_answer([harm], question="Why do people think about suicide?")
    assert result is not None and "suicide" in result[0]


def test_window_most_relevant_to_the_question_is_chosen():
    filler = "Namaste and welcome to everyone joining from many countries today. " * 6
    doc = _doc(filler + "Jealousy arises when you compare yourself to another person.")
    answer, _ = _grounded_partial_answer([doc], question="Why do I feel jealousy?")
    assert "Jealousy arises" in answer


def test_no_question_keeps_the_opening_window():
    doc = _doc("First sentence here. " + "More words follow in this teaching. " * 20)
    answer, _ = _grounded_partial_answer([doc])
    assert _body(answer).lstrip().startswith("First sentence here.")


def test_require_overlap_drops_unrelated_docs():
    ekam = _doc("Ekam is a place for world peace in Andhra Pradesh.")
    assert (
        _grounded_partial_answer(
            [ekam], question="What is the capital of France?", require_overlap=True
        )
        is None
    )
    # Graded-relevant callers are not held to lexical overlap (paraphrase).
    assert _grounded_partial_answer([ekam], question="What is the capital of France?")


def test_untranslated_indic_question_is_not_judged_lexically():
    doc = _doc("Anger is a suffering state.")
    assert _grounded_partial_answer([doc], question="मुझे गुस्सा क्यों आता है?", require_overlap=True)


def test_rerank_floor_drops_low_scoring_docs():
    low = _doc("Ekam is a place for world peace.", rerank_score=0.05)
    assert (
        _grounded_partial_answer([low], question="capital of France", min_rerank_score=0.35) is None
    )
    high = _doc("Anger is a suffering state.", rerank_score=0.9)
    assert _grounded_partial_answer([low, high], question="anger", min_rerank_score=0.35)


def test_rerank_floor_only_applies_when_a_cross_encoder_scored_the_docs():
    reranked = _partial_evidence_kwargs(
        {"question": "q", "evaluation_trace": {"rerank_bypassed": False}}
    )
    assert reranked["min_rerank_score"] == float(settings.rerank_min_score)
    bypassed = _partial_evidence_kwargs(
        {"question": "q", "evaluation_trace": {"rerank_bypassed": True}}
    )
    assert bypassed["min_rerank_score"] is None
    assert _partial_evidence_kwargs({})["min_rerank_score"] is None


def test_okf_is_labelled_as_notes_not_verbatim_for_the_model():
    label = _source_kind_label({"knowledge_source": "okf", "chunk_provenance": "polished_speech"})
    assert "VERBATIM" not in label
    assert "not a transcript" in label
