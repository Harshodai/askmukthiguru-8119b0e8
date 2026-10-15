"""Regression tests for issue LV-1: Distress route zero-synthesis invariant.

In HANDOFF_2026_10_14.md Section 12, query #11 ("How do I find peace when I feel lonely?")
routed to handle_distress and generated model prose claiming:
"Sri Preethaji & Sri Krishnaji teach us that Peace is..." with 3 speakerless citations.

This violated Root Invariant 21 ("the model speaks never as the founders themselves")
and the first-person invariants ("answers are the teacher's recorded clips, quoted
verbatim with speaker and timestamp, never text generated in the teacher's voice").

These tests verify:
1. MODERATE and MILD distress queries NEVER invoke ollama.generate to synthesize teachings.
2. Safe clinician-reviewed Serene Mind templates and breathing practices are returned.
3. Citations are empty ([]) when returning the Serene Mind template.
4. The response NEVER contains generated teaching claims like "Sri Preethaji teaches",
   "Sri Krishnaji teaches", "teach us that", etc.
5. SEVERE and CRISIS queries continue to carry the full 24/7 crisis support block (14416 / 988).
6. Every distress response ends with a human support line.
7. Verified verbatim clips from first-person route (if attached) are supported safely.
"""

from __future__ import annotations

import re
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from rag.nodes.intent import handle_distress
from rag.states import GraphState
from services.serene_mind_engine import DistressAssessment, DistressLevel, SereneMindEngine

_FORBIDDEN_TEACHING_PATTERNS = [
    re.compile(r"\bSri Preethaji\s+teaches\b", re.IGNORECASE),
    re.compile(r"\bSri Krishnaji\s+teaches\b", re.IGNORECASE),
    re.compile(r"\bteach(?:es)?\s+us\s+that\b", re.IGNORECASE),
    re.compile(r"\bSri Preethaji\s*&\s*Sri Krishnaji\s+teach\b", re.IGNORECASE),
    re.compile(r"\bteachings?\s+remind\s+us\s+that\b", re.IGNORECASE),
]


def _assert_no_generated_teachings(text: str) -> None:
    for pat in _FORBIDDEN_TEACHING_PATTERNS:
        assert not pat.search(text), f"Forbidden generated teaching claim found matching {pat.pattern}: {text}"


@pytest.mark.asyncio
async def test_moderate_distress_loneliness_query_returns_safe_template_no_generated_teachings():
    """Query #11 from HANDOFF_2026_10_14.md: 'How do I find peace when I feel lonely?'
    must return the safe Serene Mind template, breathing practice, zero citations, and
    never generate founder teaching prose."""
    mock_ollama = AsyncMock()
    mock_ollama.generate = AsyncMock(return_value="Sri Preethaji teaches us that peace is within.")

    engine = SereneMindEngine()
    state = GraphState(
        question="How do I find peace when I feel lonely?",
        chat_history=[],
        relevant_docs=[{"title": "Finding Peace", "text": "Inner peace is a practice."}],
    )

    with (
        patch("rag.nodes.intent._services._serene_mind", engine),
        patch("rag.nodes.intent._services._ollama", mock_ollama),
    ):
        result = await handle_distress(state, config={})

    # 1. LLM generate was NEVER called
    assert mock_ollama.generate.call_count == 0, "ollama.generate must not be called on distress path"

    final_answer = result.get("final_answer", "")
    assert final_answer, "final_answer must not be empty"

    # 2. Citations must be empty for template text
    assert result.get("citations") == [], "citations must be empty list for Serene Mind template"

    # 3. Contains Serene Mind breathing practice
    assert "breathing practice" in final_answer.lower() or "hand on your heart" in final_answer.lower()
    assert "serene mind" in final_answer.lower()

    # 4. Zero fabricated teaching claims
    _assert_no_generated_teachings(final_answer)

    # 5. Human support line guaranteed
    assert "14416" in final_answer or "988" in final_answer
    assert result.get("intent") == "DISTRESS"
    assert result.get("route_decision") == "distress"


@pytest.mark.asyncio
async def test_moderate_distress_empty_and_anxious_query():
    """'I feel so empty and anxious' routes to safe Serene Mind template."""
    mock_ollama = AsyncMock()
    engine = SereneMindEngine()
    state = GraphState(
        question="I feel so empty and anxious",
        chat_history=[],
        relevant_docs=[],
    )

    with (
        patch("rag.nodes.intent._services._serene_mind", engine),
        patch("rag.nodes.intent._services._ollama", mock_ollama),
    ):
        result = await handle_distress(state, config={})

    assert mock_ollama.generate.call_count == 0
    assert result.get("citations") == []

    final_answer = result.get("final_answer", "")
    assert "breathing practice" in final_answer.lower() or "hand on your heart" in final_answer.lower()
    _assert_no_generated_teachings(final_answer)
    assert "14416" in final_answer or "988" in final_answer


@pytest.mark.asyncio
async def test_mild_distress_returns_grounding_technique():
    """MILD distress returns grounding technique with empty citations and no LLM call."""
    mock_ollama = AsyncMock()
    mock_serene = MagicMock()
    mock_serene.async_assess_distress = AsyncMock(
        return_value=DistressAssessment(level=DistressLevel.MILD, confidence=0.6)
    )
    mock_serene.get_response = MagicMock(
        return_value=(
            "I sense you may be going through a challenging time. "
            "🌱 **Quick grounding technique**: Take a slow breath in for 4 counts, hold for 4, exhale for 6."
        )
    )

    state = GraphState(
        question="I am feeling a little stressed with work today",
        chat_history=[],
        relevant_docs=[{"title": "Stress and Living", "text": "Observe pressure."}],
    )

    with (
        patch("rag.nodes.intent._services._serene_mind", mock_serene),
        patch("rag.nodes.intent._services._ollama", mock_ollama),
    ):
        result = await handle_distress(state, config={})

    assert mock_ollama.generate.call_count == 0
    assert result.get("citations") == []

    final_answer = result.get("final_answer", "")
    assert "grounding technique" in final_answer.lower()
    _assert_no_generated_teachings(final_answer)
    assert "14416" in final_answer

@pytest.mark.asyncio
async def test_severe_distress_carries_24_7_crisis_support_block():
    """SEVERE distress carries the full 24/7 crisis support block with 14416."""
    mock_ollama = AsyncMock()
    mock_serene = MagicMock()
    mock_serene.async_assess_distress = AsyncMock(
        return_value=DistressAssessment(level=DistressLevel.SEVERE, confidence=0.9)
    )
    mock_serene.get_response = MagicMock(
        return_value="I feel the depth of your pain, and I want you to know — you are not alone."
    )

    state = GraphState(
        question="I feel so hopeless, I want to disappear",
        chat_history=[],
        relevant_docs=[],
    )

    with (
        patch("rag.nodes.intent._services._serene_mind", mock_serene),
        patch("rag.nodes.intent._services._ollama", mock_ollama),
    ):
        result = await handle_distress(state, config={})

    assert mock_ollama.generate.call_count == 0
    assert result.get("citations") == []

    final_answer = result.get("final_answer", "")
    assert "Crisis Support" in final_answer
    assert "14416" in final_answer
    _assert_no_generated_teachings(final_answer)


@pytest.mark.asyncio
async def test_crisis_distress_carries_24_7_crisis_support_block():
    """CRISIS distress queries carry the full 24/7 crisis support block with 14416 and 988."""
    mock_ollama = AsyncMock()
    engine = SereneMindEngine()

    state = GraphState(
        question="I want to end my life, nothing matters anymore",
        chat_history=[],
        relevant_docs=[],
    )

    with (
        patch("rag.nodes.intent._services._serene_mind", engine),
        patch("rag.nodes.intent._services._ollama", mock_ollama),
    ):
        result = await handle_distress(state, config={})

    assert mock_ollama.generate.call_count == 0
    assert result.get("citations") == []

    final_answer = result.get("final_answer", "")
    assert "Crisis Support" in final_answer or "Crisis Lifeline" in final_answer
    assert "14416" in final_answer
    _assert_no_generated_teachings(final_answer)


@pytest.mark.asyncio
async def test_attached_verified_first_person_clip_is_safely_rendered():
    """When a verified verbatim clip from the first-person route is attached, it is
    rendered alongside the safety boundary, with clip citations and no LLM synthesis."""
    mock_ollama = AsyncMock()
    engine = SereneMindEngine()

    verbatim_teaching = "When you observe the movement of thought without identification, suffering begins to dissolve."
    clip = {
        "verbatim_text": verbatim_teaching,
        "speaker": "Sri Krishnaji",
        "title": "Observing Thought",
        "source_url": "https://www.youtube.com/watch?v=mock_clip_id",
        "citations": [
            {
                "source_title": "Observing Thought",
                "source_url": "https://www.youtube.com/watch?v=mock_clip_id",
                "speaker": "Sri Krishnaji",
            }
        ],
    }

    state = GraphState(
        question="How do I find peace when I feel lonely?",
        chat_history=[],
        relevant_docs=[],
        first_person_clip=clip,
    )

    with (
        patch("rag.nodes.intent._services._serene_mind", engine),
        patch("rag.nodes.intent._services._ollama", mock_ollama),
    ):
        result = await handle_distress(state, config={})

    assert mock_ollama.generate.call_count == 0
    final_answer = result.get("final_answer", "")
    assert verbatim_teaching in final_answer
    assert "Sri Krishnaji" in final_answer
    assert len(result.get("citations", [])) == 1
    assert result["citations"][0]["speaker"] == "Sri Krishnaji"
    _assert_no_generated_teachings(final_answer)


@pytest.mark.asyncio
async def test_hazardous_sentences_dropped_from_candidate_distress_text():
    """Defense-in-depth: sentences discussing quitting life, death, or rock bottom
    are dropped even if present in candidate text."""
    mock_ollama = AsyncMock()
    engine = SereneMindEngine()

    hazardous_clip = {
        "verbatim_text": "Sometimes you reach rock bottom and feel like quitting life. But observation brings stillness.",
        "speaker": "Sri Krishnaji",
    }

    state = GraphState(
        question="I feel so low",
        chat_history=[],
        relevant_docs=[],
        first_person_clip=hazardous_clip,
    )

    with (
        patch("rag.nodes.intent._services._serene_mind", engine),
        patch("rag.nodes.intent._services._ollama", mock_ollama),
    ):
        result = await handle_distress(state, config={})

    final_answer = result.get("final_answer", "")
    assert "rock bottom" not in final_answer.lower()
    assert "quitting life" not in final_answer.lower()
    assert "observation brings stillness" in final_answer.lower()


@pytest.mark.asyncio
async def test_abstained_first_person_result_does_not_pollute_distress_template():
    """If first_person_pipeline abstained, its technical abstain string must NOT
    be appended to the compassionate Serene Mind template."""
    from services.first_person_pipeline import FirstPersonPipelineResult

    mock_ollama = AsyncMock()
    engine = SereneMindEngine()

    abstained_fp = FirstPersonPipelineResult(
        answer_text="No verified first-person discourse found for this question.",
        citations=[],
        status="abstained",
        is_direct_answer=False,
        latency_ms=10.0,
        abstain_reason="no_verified_clips",
    )

    state = GraphState(
        question="I feel so sad and lonely",
        chat_history=[],
        relevant_docs=[],
        first_person_result=abstained_fp,
    )

    with (
        patch("rag.nodes.intent._services._serene_mind", engine),
        patch("rag.nodes.intent._services._ollama", mock_ollama),
    ):
        result = await handle_distress(state, config={})

    final_answer = result.get("final_answer", "")
    assert "no verified first-person discourse found" not in final_answer.lower()
    assert "breathing practice" in final_answer.lower() or "hand on your heart" in final_answer.lower()
    assert result.get("citations") == []


@pytest.mark.asyncio
async def test_pipeline_result_object_first_person_is_supported():
    """PipelineResult object with final_answer is supported when successful."""
    from app.pipeline.result import PipelineResult

    mock_ollama = AsyncMock()
    engine = SereneMindEngine()

    fp_res = PipelineResult(
        final_answer="Here is a teaching: Observe what is.",
        citations=[{"source_title": "Observation", "source_url": "https://youtu.be/123", "speaker": "Sri Krishnaji"}],
        intent="QUERY",
        trace_id="t1",
        latency_ms=10,
        route_decision="first_person_bridge",
    )

    state = GraphState(
        question="How to be with sadness?",
        chat_history=[],
        relevant_docs=[],
        first_person_result=fp_res,
    )

    with (
        patch("rag.nodes.intent._services._serene_mind", engine),
        patch("rag.nodes.intent._services._ollama", mock_ollama),
    ):
        result = await handle_distress(state, config={})

    final_answer = result.get("final_answer", "")
    assert "Observe what is" in final_answer
    assert len(result.get("citations", [])) == 1
    assert result["citations"][0]["speaker"] == "Sri Krishnaji"


@pytest.mark.asyncio
async def test_verified_clip_default_speaker_propagates_to_citation():
    """If verified_clip lacks speaker, speaker fallback propagates consistently to citation."""
    mock_ollama = AsyncMock()
    engine = SereneMindEngine()

    clip_no_speaker = {
        "verbatim_text": "Live in the present moment with awareness.",
        "url": "https://youtu.be/abc",
    }

    state = GraphState(
        question="I feel anxious",
        chat_history=[],
        relevant_docs=[],
        verified_clip=clip_no_speaker,
    )

    with (
        patch("rag.nodes.intent._services._serene_mind", engine),
        patch("rag.nodes.intent._services._ollama", mock_ollama),
    ):
        result = await handle_distress(state, config={})

    final_answer = result.get("final_answer", "")
    assert "recorded teaching from Sri Preethaji & Sri Krishnaji" in final_answer
    citations = result.get("citations", [])
    assert len(citations) == 1
    assert citations[0]["speaker"] == "Sri Preethaji & Sri Krishnaji"
