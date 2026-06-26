"""Regression tests for LettuceDetect faithfulness scoring."""

from __future__ import annotations

from services.lettuce_detect_service import LettuceDetectService


class _FakeEmbedder:
    """Returns deterministic embeddings so sentence/context similarity is controlled."""

    def __init__(self, sentence_score: float = 0.1, context_score: float = 0.9) -> None:
        self.sentence_score = sentence_score
        self.context_score = context_score

    def encode_single_full(self, text: str) -> dict:
        # Use a 2-D vector so normalization preserves the desired similarity ratio.
        return {"dense": [self.sentence_score, 1.0 - self.sentence_score]}

    def encode_batch(self, texts: list[str]) -> dict:
        return {"dense": [[self.context_score, 1.0 - self.context_score] for _ in texts]}


def test_empty_answer_returns_unfaithful():
    """Empty answer must be rejected (finding #45)."""
    svc = LettuceDetectService(embedder=None)
    result = svc.score_faithfulness("any question", "some context", "")
    assert result["is_faithful"] is False
    assert result["score"] == 0.0


def test_empty_context_returns_unfaithful():
    """Empty context must be rejected (finding #45)."""
    svc = LettuceDetectService(embedder=None)
    result = svc.score_faithfulness("any question", "", "an answer")
    assert result["is_faithful"] is False
    assert result["score"] == 0.0


def test_no_testable_sentences_returns_unfaithful():
    """Answers with only greeting/filler words and no real sentence must be rejected (finding #45)."""
    svc = LettuceDetectService(embedder=None)
    result = svc.score_faithfulness("any question", "some context", "namaste hello")
    assert result["is_faithful"] is False
    assert result["score"] == 0.0


def test_conversational_filler_does_not_autopass():
    """Greeting/filler sentences must be scored like any other sentence (finding #45)."""
    svc = LettuceDetectService(embedder=_FakeEmbedder(sentence_score=0.05, context_score=0.9))
    # "Namaste, thank you for your guidance." is filler + a slightly longer clause,
    # but the fake embedder makes every sentence score below the 0.22 threshold.
    result = svc.score_faithfulness("any question", "context paragraph one\n\ncontext paragraph two", "Namaste, thank you for your guidance.")
    assert result["is_faithful"] is False


def test_doctrine_term_does_not_autopass():
    """Doctrine keywords must not bypass a low faithfulness score (findings #1/#14)."""
    svc = LettuceDetectService(embedder=_FakeEmbedder(sentence_score=0.01, context_score=0.9))
    result = svc.score_faithfulness(
        "any question",
        "context paragraph one\n\ncontext paragraph two",
        "Meditation and deeksha will grant you instant enlightenment and a new car.",
    )
    assert result["is_faithful"] is False
    assert "meditation" in result["unsupported_sentences"][0].lower()


def test_high_similarity_returns_faithful():
    """Sentences with high context similarity pass."""
    svc = LettuceDetectService(embedder=_FakeEmbedder(sentence_score=0.95, context_score=0.95))
    result = svc.score_faithfulness(
        "any question",
        "context paragraph one\n\ncontext paragraph two",
        "This sentence is well grounded in the context.",
    )
    assert result["is_faithful"] is True


def test_no_embedder_falls_back_to_lexical():
    """When embedder is missing, lexical overlap fallback is used."""
    svc = LettuceDetectService(embedder=None)
    result = svc.score_faithfulness(
        "what is deeksha",
        "Deeksha is a sacred initiation transferring divine grace.",
        "Deeksha transfers divine grace through initiation.",
    )
    assert result["is_faithful"] is True
