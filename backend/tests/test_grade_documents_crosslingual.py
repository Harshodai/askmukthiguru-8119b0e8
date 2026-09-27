"""Test cross-lingual and Indic document grading protection in grade_documents (CRAG)."""

from unittest.mock import AsyncMock, MagicMock
import pytest

import rag.nodes as nodes
from rag.nodes.reranking import grade_documents


def _doc(score: float, text: str = "teaching text") -> dict:
    return {"text": text, "rerank_score": score, "source_url": "https://youtu.be/kannada_test"}


@pytest.fixture
def mock_services():
    mock_ollama = AsyncMock()
    # Explicit spec ensures hasattr(embedder, "_reranker") is False, preventing compressor network attempts
    mock_embedder = MagicMock(spec=["encode_batch", "encode_single", "dimension"])
    nodes.init_services(
        ollama=mock_ollama, embedder=mock_embedder, qdrant=MagicMock(), lightrag=MagicMock()
    )
    yield mock_ollama


@pytest.mark.asyncio
async def test_kannada_golden_028_doctrine_document_preserved(mock_services, monkeypatch):
    """golden_028 (Kannada) query must NOT drop documents containing 'Four Sacred Secrets'

    even when the LLM relevance grader falsely rejects the cross-lingual match.
    """
    from app.config import settings

    monkeypatch.setattr(settings, "crag_skip_confidence", 0.75)
    # Simulate LLM falsely rejecting cross-lingual English docs for Kannada question
    mock_services.grade_relevance.return_value = [
        {"relevant": False, "reason": "Language mismatch / no match"},
        {"relevant": False, "reason": "Language mismatch / no match"},
    ]

    state = {
        "query_tier": "standard",
        "question": "ನಾಲ್ಕು ಪವಿತ್ರ ರಹಸ್ಯಗಳು ಎಂದರೇನು?",  # "What are the Four Sacred Secrets?" in Kannada
        "detected_language": "kn",
        "reranked_docs": [
            _doc(0.55, "Sri Preethaji speaks on the Four Sacred Secrets to end inner suffering."),
            _doc(0.30, "General cooking recipe unrelated to spirituality."),
        ],
    }

    result = await grade_documents(state)
    relevant = result["relevant_docs"]

    # The sacred doctrine document MUST be preserved
    assert len(relevant) >= 1
    assert any("Four Sacred Secrets" in doc["text"] for doc in relevant)
    assert any("Cross-lingual" in r for r in result.get("grading_reasons", []))


def _state(question: str, lang: str, docs: list[dict]) -> dict:
    return {
        "query_tier": "standard",
        "question": question,
        "detected_language": lang,
        "reranked_docs": docs,
    }


@pytest.mark.asyncio
async def test_doctrine_keyword_alone_does_not_rescue_unrelated_indic_query(mock_services, monkeypatch):
    """False-positive guard: a low-scoring doc that merely mentions a doctrine term

    must stay rejected. "Beautiful state" appears across most of the corpus, so a
    keyword rule would accept off-topic docs for any Indic question.
    """
    from app.config import settings

    monkeypatch.setattr(settings, "crag_skip_confidence", 0.75)
    mock_services.grade_relevance.return_value = [{"relevant": False, "reason": "off topic"}]
    state = _state(
        "ನನ್ನ ಕಾರಿನ ಟೈರ್ ಬದಲಾಯಿಸುವುದು ಹೇಗೆ?",  # "How do I change my car tyre?" (Kannada)
        "kn",
        [_doc(0.12, "When you live in a beautiful state, relationships heal.")],
    )

    result = await grade_documents(state)

    assert not any("Cross-lingual" in r for r in result.get("grading_reasons", []))
    assert all(d["rerank_score"] != 0.12 for d in result.get("relevant_docs", []))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "question, lang",
    [
        ("चार पवित्र रहस्य क्या हैं?", "hi"),  # Hindi
        ("నాలుగు పవిత్ర రహస్యాలు ఏమిటి?", "te"),  # Telugu
        ("Four sacred secrets kya hain?", "hi"),  # Hinglish, Latin script
    ],
)
async def test_high_rerank_score_rescues_indic_and_hinglish(mock_services, monkeypatch, question, lang):
    from app.config import settings

    monkeypatch.setattr(settings, "crag_skip_confidence", 0.75)
    mock_services.grade_relevance.return_value = [{"relevant": False, "reason": "language mismatch"}]

    result = await grade_documents(_state(question, lang, [_doc(0.55, "The Four Sacred Secrets are...")]))

    assert any("Cross-lingual" in r for r in result.get("grading_reasons", []))


@pytest.mark.asyncio
async def test_english_query_is_never_rescued(mock_services, monkeypatch):
    """The rescue is cross-lingual only; an English "no" from the grader stands."""
    from app.config import settings

    monkeypatch.setattr(settings, "crag_skip_confidence", 0.75)
    mock_services.grade_relevance.return_value = [{"relevant": False, "reason": "off topic"}]

    result = await grade_documents(_state("How do I change a car tyre?", "en", [_doc(0.55, "Beautiful state...")]))

    assert not any("Cross-lingual" in r for r in result.get("grading_reasons", []))
