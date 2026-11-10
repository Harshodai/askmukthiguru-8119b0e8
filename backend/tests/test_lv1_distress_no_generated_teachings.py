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
7. Only already-gated first-person pipeline results may add teaching below SEVERE; raw clip state is ignored.
8. SEVERE and CRISIS stay template-only even if a stale internal success result is present.
"""

from __future__ import annotations

import hashlib
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
        assert not pat.search(text), (
            f"Forbidden generated teaching claim found matching {pat.pattern}: {text}"
        )


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
    assert mock_ollama.generate.call_count == 0, (
        "ollama.generate must not be called on distress path"
    )

    final_answer = result.get("final_answer", "")
    assert final_answer, "final_answer must not be empty"

    # 2. Citations must be empty for template text
    assert result.get("citations") == [], "citations must be empty list for Serene Mind template"

    # 3. Contains Serene Mind breathing practice or grounding technique
    assert (
        "breathing practice" in final_answer.lower()
        or "hand on your heart" in final_answer.lower()
        or "grounding technique" in final_answer.lower()
        or "slow breath" in final_answer.lower()
    )
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
    assert (
        "breathing practice" in final_answer.lower()
        or "hand on your heart" in final_answer.lower()
        or "grounding technique" in final_answer.lower()
        or "slow breath" in final_answer.lower()
    )
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


@pytest.mark.parametrize(
    "clip_state_key", ["verified_clip", "first_person_clip", "personalize_clip"]
)
@pytest.mark.asyncio
async def test_raw_first_person_clip_state_is_not_served_without_gated_result(clip_state_key):
    """Raw clip state must not bypass the gated first-person pipeline on distress."""
    mock_ollama = AsyncMock()
    engine = SereneMindEngine()

    verbatim_teaching = "When you observe the movement of thought without identification, suffering begins to dissolve."
    clip = {
        "verbatim_text": verbatim_teaching,
        "transcript_hash": hashlib.sha256(verbatim_teaching.encode("utf-8")).hexdigest(),
        "speaker": "Sri Krishnaji",
        # A17: bare-name attribution requires a verified speaker; without
        # this flag the clip downgrades to "unverified clip" by design.
        "speaker_verified": True,
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
        **{clip_state_key: clip},
    )

    with (
        patch("rag.nodes.intent._services._serene_mind", engine),
        patch("rag.nodes.intent._services._ollama", mock_ollama),
    ):
        result = await handle_distress(state, config={})

    assert mock_ollama.generate.call_count == 0
    final_answer = result.get("final_answer", "")
    assert verbatim_teaching not in final_answer
    assert "Sri Krishnaji" not in final_answer
    assert result.get("citations") == []
    assert (
        "breathing practice" in final_answer.lower()
        or "hand on your heart" in final_answer.lower()
        or "grounding technique" in final_answer.lower()
        or "slow breath" in final_answer.lower()
    )
    assert "14416" in final_answer or "988" in final_answer
    _assert_no_generated_teachings(final_answer)


@pytest.mark.asyncio
async def test_hazardous_sentences_dropped_from_candidate_distress_text():
    """Verbatim promise: a clip carrying a hazardous sentence is omitted ENTIRELY --
    never edited sentence-by-sentence. The response is template-only with zero
    citations, preserving byte-for-byte equality for any served clip text."""
    mock_ollama = AsyncMock()
    engine = SereneMindEngine()

    hazardous_verbatim = (
        "Sometimes you reach rock bottom and feel like quitting life. "
        "But observation brings stillness."
    )
    from services.first_person_pipeline import FirstPersonPipelineResult

    hazardous_result = FirstPersonPipelineResult(
        answer_text=hazardous_verbatim,
        citations=[{"source_url": "https://www.youtube.com/watch?v=hazardous1"}],
        status="success",
        is_direct_answer=True,
        latency_ms=10.0,
    )

    state = GraphState(
        question="I feel so low",
        chat_history=[],
        relevant_docs=[],
        first_person_result=hazardous_result,
    )

    with (
        patch("rag.nodes.intent._services._serene_mind", engine),
        patch("rag.nodes.intent._services._ollama", mock_ollama),
    ):
        result = await handle_distress(state, config={})

    final_answer = result.get("final_answer", "")
    assert "rock bottom" not in final_answer.lower()
    assert "quitting life" not in final_answer.lower()
    # Entire clip omitted: even the clean sentence must NOT survive.
    assert "observation brings stillness" not in final_answer.lower()
    assert result.get("citations") == []


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
    assert (
        "breathing practice" in final_answer.lower()
        or "hand on your heart" in final_answer.lower()
        or "grounding technique" in final_answer.lower()
        or "slow breath" in final_answer.lower()
    )
    assert result.get("citations") == []


@pytest.mark.asyncio
async def test_pipeline_result_object_first_person_is_supported():
    """A verified, source-verbatim bridge PipelineResult remains supported."""
    from app.pipeline.result import PipelineResult
    from rag.meditation import get_distress_response

    mock_ollama = AsyncMock()
    engine = MagicMock()
    engine.async_assess_distress = AsyncMock(
        return_value=DistressAssessment(level=DistressLevel.MODERATE, confidence=0.7)
    )
    engine.get_response = MagicMock(return_value=get_distress_response())
    video_id = "dQw4w9WgXcQ"
    quote = "Observe what is."
    source_url = f"https://www.youtube.com/watch?v={video_id}&t=99s"

    fp_res = PipelineResult(
        final_answer=f"**Sri Krishnaji**\n\n{quote}\n\n{source_url}",
        citations=[
            {
                "source_title": "Observation",
                "source_url": source_url,
                "video_id": video_id,
                "start_ms": 99_000,
                "end_ms": 100_000,
                "timestamp_seconds": 99,
                "speaker": "Sri Krishnaji",
                "speaker_verified": True,
                "verbatim_text": quote,
                "is_verbatim": True,
            }
        ],
        intent="QUERY",
        trace_id="t1",
        latency_ms=10,
        model_used=None,
        model_provider=None,
        route_decision="first_person_bridge",
        citations_verified=True,
        verification={
            "passed": True,
            "method": "first_person_verbatim_clip_gate",
            "citations_verified": True,
            "direct": True,
        },
        route_metadata={"fp_served": True, "selected_variant": "verbatim_clip_bridge"},
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
    assert quote in final_answer
    assert len(result.get("citations", [])) == 1
    assert result["citations"][0]["speaker"] == "Sri Krishnaji"
    assert result["citations"][0]["verbatim_text"] == quote


@pytest.mark.parametrize("status", ["success", "weak_match"])
@pytest.mark.asyncio
async def test_gated_first_person_pipeline_result_is_supported(status):
    """The normal gated FirstPersonPipelineResult path remains additive on distress."""
    from rag.meditation import get_distress_response
    from services.first_person_pipeline import FirstPersonPipelineResult

    mock_ollama = AsyncMock()
    engine = MagicMock()
    engine.async_assess_distress = AsyncMock(
        return_value=DistressAssessment(level=DistressLevel.MODERATE, confidence=0.7)
    )
    engine.get_response = MagicMock(return_value=get_distress_response())
    gated_teaching = "Observe what is without turning away."
    video_id = "dQw4w9WgXcQ"
    source_url = f"https://www.youtube.com/watch?v={video_id}&t=99s"
    fp_res = FirstPersonPipelineResult(
        answer_text=gated_teaching,
        citations=[
            {
                "source_title": "Observation",
                "source_url": source_url,
                "video_id": video_id,
                "start_ms": 99_000,
                "end_ms": 100_000,
                "timestamp_seconds": 99,
                "speaker": "Sri Krishnaji",
                "speaker_verified": True,
                "verbatim_text": gated_teaching,
                "transcript_hash": hashlib.sha256(gated_teaching.encode()).hexdigest(),
                "is_verbatim": True,
            }
        ],
        status=status,
        is_direct_answer=status == "success",
        latency_ms=10.0,
        fp_served=True,
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
    assert gated_teaching in final_answer
    assert len(result.get("citations", [])) == 1
    assert result["citations"][0]["speaker"] == "Sri Krishnaji"
    assert result["citations"][0]["verbatim_text"] == gated_teaching
    assert result["citations"][0]["speaker_verified"] is True
    assert result["citations"][0]["source_url"] == source_url
    assert result["citations"][0]["video_id"] == video_id
    assert mock_ollama.generate.call_count == 0


@pytest.mark.parametrize("level", [DistressLevel.SEVERE, DistressLevel.CRISIS])
@pytest.mark.parametrize("candidate_kind", ["success", "weak_match", "bridge"])
@pytest.mark.asyncio
async def test_severe_or_crisis_ignores_gated_first_person_result(level, candidate_kind):
    """SEVERE/CRISIS stays template-only even if an internal success result leaks through."""
    from app.pipeline.result import PipelineResult
    from rag.meditation import get_distress_response
    from services.first_person_pipeline import FirstPersonPipelineResult

    mock_ollama = AsyncMock()
    engine = MagicMock()
    engine.async_assess_distress = AsyncMock(
        return_value=DistressAssessment(level=level, confidence=1.0)
    )
    engine.get_response = MagicMock(return_value=get_distress_response())

    video_id = "dQw4w9WgXcQ"
    gated_quote = "The movement of thought can be observed without identification."
    source_url = f"https://www.youtube.com/watch?v={video_id}&t=99s"
    answer_text = f"**Sri Krishnaji**\n\n{gated_quote}\n\n{source_url}"
    citation = {
        "source_title": "Observation",
        "source_url": source_url,
        "video_id": video_id,
        "start_ms": 99_000,
        "end_ms": 100_000,
        "timestamp_seconds": 99,
        "speaker": "Sri Krishnaji",
        "speaker_verified": True,
        "verbatim_text": gated_quote,
        "transcript_hash": hashlib.sha256(gated_quote.encode()).hexdigest(),
        "is_verbatim": True,
    }
    if candidate_kind == "bridge":
        fp_result = PipelineResult(
            final_answer=answer_text,
            citations=[citation],
            intent="QUERY",
            route_decision="first_person_bridge",
            citations_verified=True,
            verification={
                "passed": True,
                "method": "first_person_verbatim_clip_gate",
                "citations_verified": True,
                "direct": True,
            },
            route_metadata={"fp_served": True},
        )
    else:
        fp_result = FirstPersonPipelineResult(
            answer_text=answer_text,
            citations=[citation],
            status=candidate_kind,
            is_direct_answer=candidate_kind == "success",
            latency_ms=10.0,
            fp_served=True,
        )

    state = GraphState(
        question="I feel overwhelmed and unsafe.",
        chat_history=[],
        relevant_docs=[],
        first_person_result=fp_result,
    )
    with (
        patch("rag.nodes.intent._services._serene_mind", engine),
        patch("rag.nodes.intent._services._ollama", mock_ollama),
    ):
        result = await handle_distress(state, config={})

    final_answer = result.get("final_answer", "")
    assert gated_quote not in final_answer
    assert answer_text not in final_answer
    assert result.get("citations") == []
    assert "14416" in final_answer or "988" in final_answer
    assert mock_ollama.generate.call_count == 0


@pytest.mark.asyncio
async def test_verified_clip_without_speaker_falls_back_to_template_only():
    """Raw verified_clip state without a gated result is template-only."""
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
    assert "Live in the present moment with awareness." not in final_answer
    assert result.get("citations") == []
    assert (
        "breathing practice" in final_answer.lower()
        or "hand on your heart" in final_answer.lower()
        or "grounding technique" in final_answer.lower()
        or "slow breath" in final_answer.lower()
    )
    assert "14416" in final_answer or "988" in final_answer
    _assert_no_generated_teachings(final_answer)


if __name__ == "__main__":
    import sys

    import pytest

    sys.exit(pytest.main([__file__, "-q"]))
