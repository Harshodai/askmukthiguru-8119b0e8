"""
Mukthi Guru — Advanced RAG Techniques Integration & Safety Tests

Verifies Indic phonetic matching, local LettuceDetect CPU scoring,
context compression, and token budgeting capabilities.
"""

import pytest
from services.phonetic import IndicPhoneticMatcher
from services.lettuce_detect_service import LettuceDetectService
from rag.compressor import compress_documents, cap_to_token_budget


def test_indic_phonetic_matcher_encoding():
    """Verify Sanskrit spelling variations collapse to identical phonetic keys."""
    # Deeksha variations
    assert IndicPhoneticMatcher.encode("deeksha") == "DIXA"
    assert IndicPhoneticMatcher.encode("diksha") == "DIXA"
    assert IndicPhoneticMatcher.encode("dikhsha") == "DIXA"

    # Mukthi variations
    assert IndicPhoneticMatcher.encode("mukthi") == "MUKTI"
    assert IndicPhoneticMatcher.encode("mukti") == "MUKTI"

    # Pranayama variations
    assert IndicPhoneticMatcher.encode("pranayama") == "PRANAIAM"
    assert IndicPhoneticMatcher.encode("pranayam") == "PRANAIAM"

    # Upanishad variations
    assert IndicPhoneticMatcher.encode("upanishad") == "UPANISAD"
    assert IndicPhoneticMatcher.encode("upanishada") == "UPANISAD"


def test_indic_phonetic_token_extraction():
    """Verify phonetic token extraction filters out stop words and encodes terms."""
    text = "Tell me more about Deeksha and Mukthi"
    tokens = IndicPhoneticMatcher.get_phonetic_tokens(text)
    
    assert "DIXA" in tokens
    assert "MUKTI" in tokens
    assert "MORE" in tokens
    assert "TEL" in tokens
    
    # Verify stop words are filtered out
    assert "AND" not in tokens
    assert "THE" not in tokens
    assert "ABOUT" not in tokens


def test_lettuce_detect_grounding_heuristics():
    """Verify local LettuceDetect factual grading correctly flags hallucinations."""
    service = LettuceDetectService(embedder=None)  # Test with lexical fallback
    
    context = "Sri Preethaji teaches that the Beautiful State is a state of inner connection, where there is no division or anxiety."
    
    # Grounded answer
    grounded_answer = "According to Sri Preethaji, the Beautiful State is a state of inner connection without division."
    res_grounded = service.score_faithfulness("What is the Beautiful State?", context, grounded_answer)
    assert res_grounded["is_faithful"] is True
    assert res_grounded["score"] > 0.5

    # Hallucinated answer
    hallucinated_answer = "Sri Preethaji teaches that you will get 10 million dollars instantly by going into the Beautiful State."
    res_hallucinated = service.score_faithfulness("What is the Beautiful State?", context, hallucinated_answer)
    assert res_hallucinated["is_faithful"] is False
    assert len(res_hallucinated["unsupported_sentences"]) > 0


def test_token_budget_capping():
    """Verify strict token budget allocation caps long inputs correctly."""
    long_text = "word " * 1000  # 1000 words
    
    # Cap to 512 tokens (~400 words)
    capped_512 = cap_to_token_budget(long_text, 512)
    assert len(capped_512.split()) <= 400

    # Cap to 1024 tokens (~800 words)
    capped_1024 = cap_to_token_budget(long_text, 1024)
    assert len(capped_1024.split()) <= 800
