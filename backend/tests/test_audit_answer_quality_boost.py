"""Tests for Answer Quality Boost, Inline Citation Grounding Trap Remediation,
Memory-to-Verifier Bridge, Minimal Stitching Directives, and Dynamic Reranker Fallback.
"""

import pytest
from app.config import settings
from rag.nodes.generation import format_final_answer, context_engineer
from rag.nodes.reranking import grade_documents
from rag.nodes.utils import _verify_inline_citations
from services.citation_service import _check_grounding, resolve


# ---------------------------------------------------------------------------
# 1. Inline Citation Grounding Trap Remediation Tests
# ---------------------------------------------------------------------------

def test_check_grounding_verified_grounded_skips_paragraph_penalty():
    """When claim verification has confirmed all claims are grounded,
    paragraph marker absence in intro/conclusion must not fail citations_verified."""
    docs = [{"title": "Discourse 1", "source_url": "https://youtube.com/watch?v=abc"}]
    # Paragraph 1 is 33 words (> 25 words) and lacks any citation marker.
    # Paragraph 2 has the citation marker.
    answer = (
        "In the spiritual journey, we often find ourselves caught in repeated and exhausting loops of anxiety, "
        "distress, and painful self-doubt that trouble the human heart deeply and create unnecessary inner suffering every single day.\n\n"
        "According to Sri Preethaji, staying in anxiety is a curse you lay on yourself [^1].\n\n"
        "When awareness arises, inner peace can naturally emerge without forcing or struggle."
    )
    # Default unverified check fails because paragraph 1 (> 25 words) has no marker
    assert _check_grounding(answer, docs, claims_verified_grounded=False) is False

    # Verified claims check succeeds because all claims are verified and valid marker [^1] is present
    assert _check_grounding(answer, docs, claims_verified_grounded=True) is True
    assert _check_grounding(answer, docs, faithfulness_score=0.90, unsupported_count=0) is True


def test_check_grounding_verified_grounded_requires_at_least_one_marker():
    """Even if claims are verified grounded, an answer with NO citation markers at all
    for retrieved context must still return False (no uncited passes)."""
    docs = [{"title": "Discourse 1", "source_url": "https://youtube.com/watch?v=abc"}]
    answer = (
        "In the spiritual journey, we often find ourselves caught in repeated and exhausting loops of anxiety, "
        "distress, and painful self-doubt that trouble the human heart deeply and create unnecessary inner suffering every single day.\n\n"
        "According to Sri Preethaji, staying in anxiety is a curse you lay on yourself without peace.\n\n"
        "When awareness arises, inner peace can naturally emerge without forcing or struggle."
    )
    assert _check_grounding(answer, docs, claims_verified_grounded=True) is False
    assert _check_grounding(answer, docs, faithfulness_score=1.0, unsupported_count=0) is False


def test_check_grounding_unsupported_claims_fail_grounding():
    """When unsupported claims exist or faithfulness is low, paragraph marker check applies."""
    docs = [{"title": "Discourse 1", "source_url": "https://youtube.com/watch?v=abc"}]
    answer = (
        "In the spiritual journey, we often find ourselves caught in repeated and exhausting loops of anxiety, "
        "distress, and painful self-doubt that trouble the human heart deeply and create unnecessary inner suffering every single day.\n\n"
        "According to Sri Preethaji, staying in anxiety is a curse you lay on yourself [^1].\n\n"
        "When awareness arises, inner peace can naturally emerge without forcing or struggle."
    )
    # Low faithfulness score (< 0.70)
    assert _check_grounding(answer, docs, faithfulness_score=0.65, unsupported_count=0) is False
    # Unsupported claims exist
    assert _check_grounding(answer, docs, faithfulness_score=0.95, unsupported_count=1) is False


def test_verify_inline_citations_verified_grounded():
    """_verify_inline_citations returns citations_verified=True when claims are grounded."""
    docs = [{"title": "Discourse 1", "source_url": "https://youtube.com/watch?v=abc"}]
    answer = (
        "In the spiritual journey, we often find ourselves caught in repeated and exhausting loops of anxiety, "
        "distress, and painful self-doubt that trouble the human heart deeply and create unnecessary inner suffering every single day.\n\n"
        "According to Sri Preethaji, staying in anxiety is a curse you lay on yourself [[CITE:1]].\n\n"
        "When awareness arises, inner peace can naturally emerge without forcing or struggle."
    )
    cleaned, verified, stripped = _verify_inline_citations(
        answer, docs, claims_verified_grounded=True
    )
    assert verified is True
    assert stripped == 0
    assert "[[CITE:1]]" in cleaned


@pytest.mark.asyncio
async def test_format_final_answer_preserves_verified_status_on_grounded_claims():
    """format_final_answer does NOT demote a 100% faithful answer to unverified related evidence
    purely because an introductory paragraph lacks an inline citation marker."""
    docs = [
        {
            "title": "Discourse on Anxiety",
            "source_url": "https://youtube.com/watch?v=abc12345",
            "text": "Staying in anxiety is a curse you lay on yourself.",
        }
    ]
    answer = (
        "When we explore the roots of fear and distress in human experience, the mind often creates immense suffering.\n\n"
        "Staying in anxiety is a curse you lay on yourself [[CITE:1]].\n\n"
        "Peace arises through non-resistance."
    )
    state = {
        "question": "How do I overcome anxiety?",
        "answer": answer,
        "relevant_docs": docs,
        "citations": [{"url": "https://youtube.com/watch?v=abc12345", "title": "Discourse on Anxiety"}],
        "is_faithful": True,
        "faithfulness_score": 1.0,
        "confidence_score": 8.5,
        "verification": {
            "passed": True,
            "method": "local_nli_claim_verification",
            "score": 1.0,
            "claims": [
                {"claim": "Staying in anxiety is a curse you lay on yourself.", "supported": True}
            ],
        },
        "intent": "QUERY",
    }
    result = await format_final_answer(state)
    assert result["verification"]["passed"] is True
    assert result["verification"]["citations_verified"] is True
    assert result["citations_verified"] is True
    assert "unverified related evidence" not in result["verification"].get("details", "")


# ---------------------------------------------------------------------------
# 2. Memory-to-Verifier Evidence Bridge Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_personalize_stage_bridges_canonical_memories_to_verifier_evidence(monkeypatch):
    """PersonalizeStage formats hydrated canonical memories directly into
    state['canonical_memory_evidence'] and ctx.state['canonical_memory_evidence']."""
    import hashlib
    from unittest.mock import AsyncMock, MagicMock
    from app.pipeline.stages import personalize_stage as stage_module
    from app.pipeline.stages.personalize_stage import PersonalizeStage
    from app.schemas import ChatRequest
    from app.pipeline.stages.context import PipelineContext
    from services.personalization.models import (
        SecondBrainContext,
        UnifiedSeekerContext,
        SeekerProfileContext,
    )

    clip_text = "Stillness is not the absence of thought, but freedom from its grip."
    clip = {
        "point_id": "test-point-1",
        "video_id": "dQw4w9WgXcQ",
        "start_ms": 10_000,
        "end_ms": 20_000,
        "speaker": "Sri Preethaji",
        "teacher_id": "preethaji",
        "verbatim_text": clip_text,
        "source_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "title": "Synthetic test discourse",
        "is_verbatim": True,
        "first_person_eligible": True,
        "rights_cleared": True,
        "domain_rights_status": "licensed",
        "transcript_hash": hashlib.sha256(clip_text.encode("utf-8")).hexdigest(),
    }
    store = MagicMock()
    store.get_clip_by_video_and_start.return_value = clip
    monkeypatch.setattr(stage_module, "_store_for_request", lambda: store)
    monkeypatch.setattr(stage_module, "_passes_integrity_gate", lambda clip, **kw: True, raising=False)
    monkeypatch.setattr("services.first_person_pipeline._passes_integrity_gate", lambda clip, **kw: True)
    monkeypatch.setattr("services.first_person_pipeline.is_youtube_video_available", lambda vid: True)
    monkeypatch.setattr(
        "services.first_person_pipeline.source_is_authoritatively_licensed",
        lambda **kwargs: True,
    )

    req = ChatRequest(
        messages=[],
        user_message="Please personalize this teaching for me.",
        personalize_teaching={"video_id": "dQw4w9WgXcQ", "timestamp_seconds": 10},
    )
    ctx = PipelineContext(
        container=MagicMock(),
        coordinator=MagicMock(),
        request=req,
        user_msg="Please personalize this teaching for me.",
        preferred_lang="en",
        trace_id="trace-test-1",
        start_time=0.0,
        state={"user_msg_en": "Please personalize this teaching for me."},
        user_id="11111111-1111-4111-8111-111111111111",
        incognito=False,
        personalization_eligible=True,
        personal_context_confirmed=True,
    )

    mock_seeker_ctx = UnifiedSeekerContext(
        user_id="11111111-1111-4111-8111-111111111111",
        seeker_profile=SeekerProfileContext(user_id="11111111-1111-4111-8111-111111111111"),
        second_brain=SecondBrainContext(
            canonical_memories=[
                {"id": "m1", "statement": "Struggles with anger towards spouse"},
                {"id": "m2", "statement": "Practices Soul Sync meditation daily"},
            ]
        ),
    )

    monkeypatch.setattr(
        "services.personalization.UnifiedPersonalizationEngine.hydrate_seeker_context",
        AsyncMock(return_value=mock_seeker_ctx),
    )

    stage = PersonalizeStage()
    res = await stage.run(ctx)
    assert res is None  # Accepted and passes through to next stage

    assert "canonical_memory_evidence" in ctx.state
    evidence = ctx.state["canonical_memory_evidence"]
    assert "- Struggles with anger towards spouse" in evidence
    assert "- Practices Soul Sync meditation daily" in evidence


# ---------------------------------------------------------------------------
# 3. Dynamic Reranker Floor Fallback Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_grade_documents_dynamic_fallback_preserves_candidates(monkeypatch):
    """When top_score is below min_score (0.35) but >= fallback_floor (0.22),
    candidate documents are preserved for grading rather than rejected to []."""
    monkeypatch.setattr(settings, "rerank_min_score", 0.35)
    monkeypatch.setattr(settings, "rerank_fallback_floor", 0.22)

    state = {
        "question": "What is the spiritual perspective on right action in career?",
        "query_tier": "tier3_complex",
        "reranked_docs": [
            {"title": "Doc A", "source_url": "https://example.com/a", "rerank_score": 0.28, "text": "Action in a beautiful state."},
            {"title": "Doc B", "source_url": "https://example.com/b", "rerank_score": 0.24, "text": "Right action flows naturally."},
            {"title": "Doc C", "source_url": "https://example.com/c", "rerank_score": 0.10, "text": "Unrelated excerpt."},
        ],
        "intent": "QUERY",
    }
    result = await grade_documents(state)
    relevant = result.get("relevant_docs", [])
    assert len(relevant) == 2
    assert [d["title"] for d in relevant] == ["Doc A", "Doc B"]
    # Doc C (0.10 < 0.22) must be dropped
    assert all(doc["rerank_score"] >= 0.22 for doc in relevant)


@pytest.mark.asyncio
async def test_grade_documents_rejects_below_fallback_floor(monkeypatch):
    """When top_score is below fallback_floor (0.22), documents are rejected with relevant_docs: []."""
    monkeypatch.setattr(settings, "rerank_min_score", 0.35)
    monkeypatch.setattr(settings, "rerank_fallback_floor", 0.22)

    state = {
        "question": "Unrelated cold query",
        "query_tier": "tier3_complex",
        "reranked_docs": [
            {"title": "Doc A", "source_url": "https://example.com/a", "rerank_score": 0.15, "text": "Unrelated A"},
            {"title": "Doc B", "source_url": "https://example.com/b", "rerank_score": 0.12, "text": "Unrelated B"},
        ],
        "intent": "QUERY",
    }
    result = await grade_documents(state)
    assert result.get("relevant_docs") == []
    assert result.get("low_confidence_retrieval") is True


# ---------------------------------------------------------------------------
# 4. Strict Minimal Stitching & Polarity Inversion Directives
# ---------------------------------------------------------------------------

def test_system_prompt_contains_minimal_stitching_and_no_polarity_inversion():
    """GURU_SYSTEM_PROMPT must mandate STRICT MINIMAL STITCHING and NO POLARITY INVERSION."""
    from rag.prompts.system import GURU_SYSTEM_PROMPT
    assert "STRICT MINIMAL STITCHING" in GURU_SYSTEM_PROMPT
    assert "poison you drink" in GURU_SYSTEM_PROMPT
    assert "NO POLARITY INVERSION" in GURU_SYSTEM_PROMPT


@pytest.mark.asyncio
async def test_context_engineer_instructions_contain_minimal_stitching():
    """context_engineer instructions must mandate STRICT MINIMAL STITCHING and NO POLARITY INVERSION."""
    state = {
        "question": "How to handle relationship conflict?",
        "relevant_docs": [{"title": "Doc", "source_url": "https://example.com"}],
        "chat_history": [],
        "detected_language": "en",
    }
    result = await context_engineer(state)
    instructions = result["context_layers"]["instructions"]
    assert "STRICT MINIMAL STITCHING" in instructions
    assert "NO POLARITY INVERSION" in instructions


# ---------------------------------------------------------------------------
# 5. Robustness & Edge Case Attack Surface Tests
# ---------------------------------------------------------------------------

def test_check_grounding_rejects_out_of_range_markers_even_when_claims_verified_grounded():
    """When an answer contains citation markers that reference non-existent document IDs
    (e.g. [^99] when only 1 doc exists), _check_grounding and resolve must reject grounding,
    preventing hallucinated ghost citations from passing."""
    docs = [{"title": "Discourse 1", "source_url": "https://youtube.com/watch?v=abc"}]
    answer = (
        "In the spiritual journey, anxiety troubles the human heart deeply and creates suffering.\n\n"
        "According to Sri Preethaji, staying in anxiety is a curse you lay on yourself [^99].\n\n"
        "When awareness arises, inner peace can naturally emerge without forcing or struggle."
    )
    # Even with claims_verified_grounded=True, marker 99 is invalid for 1 doc
    assert _check_grounding(answer, docs, claims_verified_grounded=True) is False
    assert _check_grounding(answer, docs, faithfulness_score=1.0, unsupported_count=0) is False

    resolved = resolve(answer, docs, claims_verified_grounded=True)
    assert resolved.grounded is False
    assert resolved.references == []


@pytest.mark.asyncio
async def test_format_final_answer_rejects_out_of_range_markers_even_when_grounded():
    """format_final_answer must NOT preserve verified status if the citations in the answer
    only reference out-of-bounds document indices (e.g. [[CITE:99]] when len(docs)==1).
    The answer must be rejected and trigger a retry or fallback."""
    docs = [
        {
            "title": "Discourse on Anxiety",
            "source_url": "https://youtube.com/watch?v=abc12345",
            "text": "Staying in anxiety is a curse you lay on yourself.",
        }
    ]
    answer = (
        "When we explore the roots of fear and distress in human experience, the mind often creates suffering.\n\n"
        "Staying in anxiety is a curse you lay on yourself [[CITE:99]].\n\n"
        "Peace arises through non-resistance."
    )
    state = {
        "question": "How do I overcome anxiety?",
        "answer": answer,
        "relevant_docs": docs,
        "is_faithful": True,
        "faithfulness_score": 1.0,
        "verification": {"passed": True, "score": 1.0, "claims": []},
        "query_tier": "tier3_complex",
        "intent": "QUERY",
        "retry_count": 0,
    }
    result = await format_final_answer(state)
    # The answer was rejected: state verification was demoted to passed=False and citations_verified=False
    assert state["verification"]["citations_verified"] is False
    assert state["verification"]["passed"] is False
    assert result.get("_needs_retry") is True


@pytest.mark.asyncio
async def test_format_final_answer_does_not_preserve_verified_when_verification_passed_is_false():
    """If verification explicitly failed (passed: False), format_final_answer must never
    treat claims as grounded or preserve verified status."""
    docs = [
        {
            "title": "Discourse on Anxiety",
            "source_url": "https://youtube.com/watch?v=abc12345",
            "text": "Staying in anxiety is a curse you lay on yourself.",
        }
    ]
    answer = (
        "When we explore the roots of fear and distress in human experience, the mind often creates suffering.\n\n"
        "Staying in anxiety is a curse you lay on yourself [[CITE:1]].\n\n"
        "Peace arises through non-resistance."
    )
    state = {
        "question": "How do I overcome anxiety?",
        "answer": answer,
        "relevant_docs": docs,
        "is_faithful": False,
        "faithfulness_score": 0.40,
        "verification": {"passed": False, "score": 0.40, "claims": [{"claim": "xyz", "supported": False}]},
        "query_tier": "tier3_complex",
        "intent": "QUERY",
        "retry_count": 0,
    }
    result = await format_final_answer(state)
    assert state["verification"]["passed"] is False
    assert result.get("_needs_retry") is True


@pytest.mark.asyncio
async def test_grade_documents_handles_none_rerank_score_without_type_error(monkeypatch):
    """When reranked_docs contains documents with rerank_score: None, grade_documents
    must safely treat them as 0.0 rather than crashing with TypeError."""
    monkeypatch.setattr(settings, "rerank_min_score", 0.35)
    monkeypatch.setattr(settings, "rerank_fallback_floor", 0.22)

    state = {
        "question": "What is the spiritual perspective on right action in career?",
        "query_tier": "tier3_complex",
        "reranked_docs": [
            {"title": "Doc A", "source_url": "https://example.com/a", "rerank_score": 0.28, "text": "Action in a beautiful state."},
            {"title": "Doc B", "source_url": "https://example.com/b", "rerank_score": None, "text": "Unscored excerpt."},
            {"title": "Doc C", "source_url": "https://example.com/c", "text": "Missing key excerpt."},
        ],
        "intent": "QUERY",
    }
    # Must not raise TypeError: '>=' not supported between instances of 'NoneType' and 'float'
    result = await grade_documents(state)
    relevant = result.get("relevant_docs", [])
    assert len(relevant) == 1
    assert relevant[0]["title"] == "Doc A"


def test_verify_inline_citations_bare_numeric_brackets():
    """Bare [1] numeric markers are recognized and preserved without premature False exit."""
    docs = [
        {"title": "Doc 1", "source_url": "https://example.com/1", "text": "Peace is within you."},
        {"title": "Doc 2", "source_url": "https://example.com/2", "text": "Living in a beautiful state."},
    ]
    answer = (
        "Peace is within you [1].\n\n"
        "Living in a beautiful state transforms your actions [2]."
    )
    cleaned, verified, stripped = _verify_inline_citations(
        answer,
        docs,
        claims_verified_grounded=True,
        faithfulness_score=1.0,
        unsupported_count=0,
    )
    assert verified is True
    assert stripped == 0


def test_check_grounding_bare_numeric_brackets():
    """_check_grounding recognizes bare [1] numeric markers."""
    docs = [{"title": "Doc 1"}]
    answer = "Staying in peace transforms life [1]."
    assert _check_grounding(answer, docs, claims_verified_grounded=True) is True
    assert _check_grounding(answer, docs, faithfulness_score=1.0, unsupported_count=0) is True


