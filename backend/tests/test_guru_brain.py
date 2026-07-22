"""
Unit tests for Guru Brain persona & tone alignment service.
"""

import pytest
from services.guru_brain.guru_brain_service import GuruBrainService, get_guru_brain_service
from services.guru_brain.tone_extractor import PersonaToneExemplar, SpeakerRole, ToneExtractor
from rag.nodes.guru_tone_adapter import GuruToneAdapterNode


def test_tone_extractor_phrasing_dna():
    extractor = ToneExtractor()
    sample_text = (
        "It is very important that we learn to live in a beautiful state, "
        "mastering the inner world before building our wealth. "
        "When you stay in the present moment, you connect to the divine."
    )
    phrases = extractor.extract_phrasing_dna(sample_text)
    assert "beautiful state" in phrases
    assert "inner world" in phrases
    assert "present moment" in phrases
    assert "connect to the divine" in phrases


@pytest.mark.asyncio
async def test_guru_brain_service_indexing_and_search():
    service = GuruBrainService(qdrant_service=None, embedding_service=None)

    exemplar = PersonaToneExemplar(
        id="test_1",
        guru_name="preethaji",
        speaker_role="preethaji",
        interviewer_name="Marie Forleo",
        seeker_question="How do I live in peace?",
        seeker_emotional_state="anxiety",
        guru_response="The only solution is to bring extraordinary quality of awareness in the present moment.",
        phrasing_dna=["present moment", "awareness"],
        teaching_concept="Living in the Present Moment",
        source_id="test_video",
    )

    indexed = await service.index_exemplars([exemplar])
    assert indexed == 1

    results = await service.search_tone_exemplars("present moment", guru_name="preethaji", limit=1)
    assert len(results) >= 1
    assert results[0].guru_name == "preethaji"

    formatted = service.format_persona_context(results)
    assert "GURU BRAIN PERSONA" in formatted
    assert "Sri Preethaji" in formatted


@pytest.mark.asyncio
async def test_guru_tone_adapter_node():
    service = GuruBrainService(qdrant_service=None, embedding_service=None)
    adapter = GuruToneAdapterNode(guru_brain_service=service, llm_service=None)

    draft = "To overcome stress, practice present moment awareness and witnessing."
    res = await adapter.transform_tone(
        user_query="How do I overcome stress?",
        factual_draft=draft,
        guru_name="preethaji",
    )
    final_ans = res.get("final_answer") if isinstance(res, dict) else res
    assert final_ans == draft



