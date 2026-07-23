"""
Unit tests for Guru Brain persona & tone alignment service.
"""

import pytest
from services.guru_brain.guru_brain_service import GuruBrainService, get_guru_brain_service
from services.guru_brain.guru_kg_service import GuruKGService
from services.guru_brain.tone_extractor import PersonaToneExemplar, SpeakerRole, ToneExtractor
from rag.nodes.guru_tone_adapter import GuruToneAdapterNode


class _FakeSession:
    def __init__(self, sink: list):
        self._sink = sink

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def run(self, cypher, **params):
        self._sink.append((cypher, params))
        return []


class _FakeDriver:
    def __init__(self, sink: list):
        self._sink = sink

    def session(self):
        return _FakeSession(self._sink)


def test_record_user_state_transition_connects_from_state():
    """s1 (from_state) must appear in a relationship, not sit orphaned."""
    calls: list = []
    svc = GuruKGService(neo4j_driver=_FakeDriver(calls))
    svc.record_user_state_transition("user_1", "anxiety", "peace", "breathing practice")
    assert len(calls) == 1
    cypher, params = calls[0]
    assert "MERGE (s1)-[:TRANSITIONS_TO]->(s2)" in cypher
    assert params["from_state"] == "anxiety"
    assert params["to_state"] == "peace"


def test_populate_ontology_arc_timestamps_each_merge_independently():
    """Each MERGE must own its ON CREATE SET — a shared trailing ON CREATE SET
    binds only to the last preceding MERGE, so pre-existing later nodes/edges
    (e.g. p, r5) would silently suppress timestamps on newly created earlier
    ones (e.g. d, r1)."""
    calls: list = []
    svc = GuruKGService(neo4j_driver=_FakeDriver(calls))
    svc.populate_ontology_arc(
        seeker_dilemma="fear of failure",
        limiting_belief="worth depends on outcomes",
        teaching="Present Moment Awareness",
        target_state="Beautiful State",
        practice_step="Observe the breath",
    )
    assert len(calls) == 1
    cypher, _ = calls[0]
    # 5 nodes (d,b,t,s,p) + 5 relationships (r1-r5) = 10 independent
    # ON CREATE SET clauses, each setting exactly one variable's property —
    # the bug was a single shared ON CREATE SET setting all of them at once,
    # gated only by whichever MERGE it happened to trail.
    on_create_lines = [l.strip() for l in cypher.strip().splitlines() if "ON CREATE SET" in l]
    assert len(on_create_lines) == 10
    for line in on_create_lines:
        assert line.count("=") == 1, f"expected exactly one assignment, got: {line}"


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



