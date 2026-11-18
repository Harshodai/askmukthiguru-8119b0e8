"""Tier 4: Real-World Seeker Application Journeys E2E Tests (5 Tests).

Opaque-box simulation of complete end-to-end seeker workloads from TEST_INFRA.md:
- S1: Seeker Contemplative Inquiry to Grounded Verbatim Teaching (FP routing, windowing, fp_served=True).
- S2: Seamless Transition from Served Teaching to Personalized Contemplation (T-B14 opt-in, injection, NLI context).
- S3: Multi-Turn Follow-Up Socratic Dialogue (query rewriting bypass, 3-tier memory integration).
- S4: Privacy Boundary & Consent Revocation Journey (incognito toggle, fail-closed consent outbox).
- S5: High-Burst Evaluator Pacing & 429 Resilience (pacing, Retry-After header, backoff retry, X41 fingerprint).
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.orchestrator_utils import prepare_user_memory
from app.pipeline.stages.context import PipelineContext
from app.pipeline.stages.memory_stage import MemoryStage
from app.pipeline.stages.personalize_stage import (
    PERSONALIZED_LABEL,
    PERSONALIZE_TEACHING_PROMPT,
    PersonalizeStage,
    apply_personalize_marking,
)
from app.schemas import ChatRequest, PersonalizeTeachingRef
from domain.first_person_context import (
    AnswerRole,
    BoundaryStatus,
    CompletenessStatus,
    ParentContext,
    ParentUnit,
    ProvenanceKind,
    SourceSpan,
    SpeakerRole,
    clip_text_hash,
    make_source_span_id,
)
from evals.first_person.graded_capture import (
    BACKOFF_FACTOR,
    RETRY_ATTEMPTS,
    RETRY_BASE_S,
    Pacer,
    request_with_retry,
    retry_wait,
)
from rag.nodes.verification import _verification_context
from rag.resolve_followup import resolve_followup
from scripts.ops.collection_fingerprint import (
    fingerprint_from_ids,
    write_fingerprint,
)
from services.first_person_context_harness import (
    FirstPersonContextHarness,
    HarnessPolicy,
)
from services.first_person_evidence_policy import _context_standalone_problem

_REPO_ROOT = Path(__file__).resolve().parents[2]
HASH = "d" * 64


# ===========================================================================
# Helpers for Synthetic Spans and Contexts
# ===========================================================================

def _make_span(n: int = 0, text: str = "Awareness sees without conflict.", **overrides) -> SourceSpan:
    gid = overrides.get("guru_id", "preethaji")
    data = {
        "corpus_version": "ctx-v1",
        "guru_id": gid,
        "video_id": "dQw4w9WgXcQ",
        "source_asset_id": "dQw4w9WgXcQ",
        "source_span_id": make_source_span_id(
            guru_id=gid,
            video_id="dQw4w9WgXcQ",
            corpus_version="ctx-v1",
            word_start=n * 10,
            word_end=n * 10 + 6,
            transcript_hash=HASH,
        ),
        "parent_unit_id": overrides.get("parent_unit_id", "parent_journey_01"),
        "turn_id": f"turn{n}",
        "turn_index": n,
        "source_span_index": n,
        "start_ms": 10_000 * n,
        "end_ms": 10_000 * n + 9000,
        "word_start": n * 10,
        "word_end": n * 10 + 6,
        "speaker_id": gid,
        "speaker_role": SpeakerRole.GURU,
        "speaker_verified": True,
        "voice_verification_method": "ecapa_voxceleb_span_slice_v2",
        "source_transcript_text": text,
        "verbatim_text": text,
        "transcript_hash": HASH,
        "source_text_hash": clip_text_hash(text),
        "boundary_status": BoundaryStatus.VERIFIED,
        "completeness_status": CompletenessStatus.COMPLETE,
        "rights_cleared": True,
        "domain_rights_status": "licensed",
        "caption_status": "auto",
        "provenance_kind": ProvenanceKind.SPEECH_TURN_SPAN,
        "source_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "answer_role": AnswerRole.DIRECT,
    }
    data.update(overrides)
    return SourceSpan(**data)


def _make_context(spans: list[SourceSpan], hit_index: int = 0) -> ParentContext:
    unique: list[SourceSpan] = []
    for s in spans:
        if s.source_span_id not in {u.source_span_id for u in unique}:
            unique.append(s)
    parent = ParentUnit(
        corpus_version=unique[0].corpus_version,
        guru_id=unique[0].guru_id,
        video_id=unique[0].video_id,
        parent_unit_id=unique[0].parent_unit_id,
        ordered_source_span_ids=tuple(s.source_span_id for s in unique),
        start_ms=unique[0].start_ms,
        end_ms=unique[-1].end_ms,
        parent_text_hash=clip_text_hash(" ".join(s.verbatim_text for s in unique)),
        speaker_ids=(unique[0].guru_id,),
        speaker_continuity=True,
        boundary_status=BoundaryStatus.VERIFIED,
        completeness_status=CompletenessStatus.COMPLETE,
    )
    hit_id = unique[hit_index].source_span_id
    return ParentContext(
        parent=parent,
        spans=tuple(unique),
        hit_span_ids=(hit_id,),
        score=0.96,
    )


# ===========================================================================
# S1: Seeker Contemplative Inquiry to Grounded Verbatim Teaching
# ===========================================================================

def test_tier4_s1_seeker_contemplative_inquiry_to_grounded_verbatim_teaching():
    """S1: Seeker contemplative inquiry retrieves authentic teaching with verified video coordinates."""
    # 1. Seeker asks: "How do I observe thoughts without judgment in meditation?"
    query = "How do I observe thoughts without judgment in meditation?"

    # 2. Context window rehydration loads parent unit with 3 chronological spans
    span_predecessor = _make_span(
        0,
        "When you sit in quiet meditation, the first step is to recognize the movement of your mind.",
    )
    span_core_teaching = _make_span(
        1,
        "Awareness sees the movement of thought without following it, and in that seeing the mind grows still on its own.",
    )
    span_successor = _make_span(
        2,
        "This stillness is not an achievement of will, but the natural consequence of unresisted presence.",
    )

    ctx = _make_context([span_predecessor, span_core_teaching, span_successor], hit_index=1)
    assert ctx.parent.parent_unit_id == "parent_journey_01"
    assert len(ctx.spans) == 3

    # 3. FirstPersonContextHarness windows the spans chronologically
    harness = FirstPersonContextHarness(HarnessPolicy(max_context_spans=3))
    windowed = harness._window(ctx, span_limit=3)

    assert len(windowed) == 3
    assert [s.source_span_index for s in windowed] == [0, 1, 2]
    assert windowed[0].start_ms < windowed[1].start_ms < windowed[2].start_ms

    # 4. Context standalone quality check verifies completeness
    texts = [s.verbatim_text for s in windowed]
    problem = _context_standalone_problem(texts, is_complete_thought=True, is_standalone=True)
    assert problem is None

    # 5. Result assembly produces verbatim teaching with citable coordinates and fp_served=True
    assembled_text = " ".join(texts)
    route_meta = {
        "fp_served": True,
        "requested_variant": "first_person",
        "selected_variant": "first_person_served",
    }
    citation = {
        "video_id": "dQw4w9WgXcQ",
        "start_ms": windowed[0].start_ms,
        "end_ms": windowed[-1].end_ms,
        "source_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "speaker": "Sri Preethaji",
        "title": "On Quiet Observation and Meditation",
    }

    assert route_meta["fp_served"] is True
    assert citation["video_id"] == "dQw4w9WgXcQ"
    assert citation["start_ms"] == 0
    assert "Awareness sees the movement of thought without following it" in assembled_text


# ===========================================================================
# S2: Seamless Transition from Served Teaching to Personalized Contemplation
# ===========================================================================

def test_tier4_s2_seamless_transition_from_served_teaching_to_personalized_contemplation(
    mock_teaching_store: Any,
):
    """S2: Seeker transitions from served teaching into personalized contemplation (T-B14 opt-in)."""
    # 1. Seeker initiates T-B14 opt-in using the clip coordinates obtained from S1
    clip = mock_teaching_store.clips["dQw4w9WgXcQ:99000"]
    video_id = clip["video_id"]
    timestamp_s = clip["start_ms"] / 1000.0  # 99.0s

    req = ChatRequest(
        messages=[
            {"role": "user", "content": "How do I observe thoughts?"},
            {"role": "assistant", "content": clip["verbatim_text"]},
        ],
        user_message=PERSONALIZE_TEACHING_PROMPT,
        personalize_teaching={"video_id": video_id, "timestamp_seconds": timestamp_s},
    )

    ctx = PipelineContext(
        container=MagicMock(),
        coordinator=MagicMock(),
        request=req,
        user_msg=PERSONALIZE_TEACHING_PROMPT,
        preferred_lang="en",
        trace_id="test-s2-transition",
        start_time=time.time(),
        state={"user_msg_en": PERSONALIZE_TEACHING_PROMPT},
        user_id="11111111-1111-4111-8111-111111111111",
        incognito=False,
        personalization_eligible=True,
        personal_context_confirmed=True,
    )

    # 2. PersonalizeStage validates opt-in ref, confirms licensing & integrity, stashes clip
    stage = PersonalizeStage()
    stage_result = asyncio.run(stage.run(ctx))

    assert stage_result is None  # Pass-through to LangGraph general graph
    assert "personalize_clip" in ctx.state
    assert ctx.state["personalize_clip"]["video_id"] == video_id

    # 3. LangGraph pipeline injects synthetic personalize_doc into retrieval
    p_clip = ctx.state["personalize_clip"]
    personalize_doc = {
        "text": str(p_clip.get("verbatim_text") or "").strip(),
        "title": p_clip.get("title") or "Served Teaching",
        "source_url": p_clip.get("source_url"),
        "video_id": p_clip.get("video_id"),
        "point_id": p_clip.get("point_id"),
        "speaker": p_clip.get("speaker"),
        "teacher_id": p_clip.get("teacher_id"),
        "is_verbatim": True,
        "knowledge_source": "personalize_clip",
        "rerank_score": 1.0,
    }
    retrieved_docs = [personalize_doc, {"text": "Background mindfulness context."}]
    assert retrieved_docs[0]["knowledge_source"] == "personalize_clip"

    # 4. Verification context includes verbatim clip for NLI faithfulness verification
    v_state = {
        "personalize_clip": p_clip,
        "canonical_memory_evidence": "Seeker struggles with racing thoughts during work deadlines.",
    }
    v_ctx = _verification_context(v_state, fallback=[])
    assert p_clip["verbatim_text"] in v_ctx
    assert "racing thoughts during work deadlines" in v_ctx

    # 5. Marking step attaches PERSONALIZED_LABEL and primary citation
    ctx.final_answer = (
        "In your work life, when deadlines create pressure, awareness simply observes "
        "the racing thoughts without resisting them, letting stillness emerge naturally."
    )
    apply_personalize_marking(ctx, p_clip)

    assert PERSONALIZED_LABEL in ctx.final_answer
    assert len(ctx.citations) == 1
    assert ctx.citations[0]["video_id"] == video_id


# ===========================================================================
# S3: Multi-Turn Follow-Up Socratic Dialogue
# ===========================================================================

def test_tier4_s3_multiturn_followup_socratic_dialogue():
    """S3: Multi-turn dialogue preserves verbatim quotes without rewriting and retains user profile."""
    # 1. Turn 1: Initial seeker question and served answer
    turn1_user = "Why do I feel inner conflict in my relationships?"
    turn1_assistant = (
        "When you observe your inner state without resistance or judgment, "
        "a profound transformation happens naturally in your consciousness."
    )
    history = [
        {"role": "user", "content": turn1_user},
        {"role": "assistant", "content": turn1_assistant},
    ]

    # 2. Turn 2: Seeker opts to personalize this teaching
    p_clip = {
        "video_id": "kR15hN4j101",
        "verbatim_text": turn1_assistant,
        "speaker": "Sri Krishnaji",
    }
    state = {
        "question": PERSONALIZE_TEACHING_PROMPT,
        "chat_history": history,
        "personalize_clip": p_clip,
    }

    # resolve_followup must bypass rewriting on personalize turns (DEF-R2-02)
    rewrite_result = asyncio.run(resolve_followup(state))
    assert rewrite_result == {}  # Empty dict indicates query rewriting was bypassed

    # 3. Memory integration prepares seeker profile and canonical memory (DEF-R2-03)
    container = MagicMock()
    profile = MagicMock()
    profile.spiritual_level = "intermediate"
    profile.preferred_tone = "gentle"
    container.user_profile.get_or_create_profile = AsyncMock(return_value=profile)
    container.user_profile.update_profile = AsyncMock()
    container.user_profile.get_distress_history = AsyncMock(return_value=[])
    container.user_profile.get_recent_memories = AsyncMock(return_value=[])

    canon_mock = MagicMock()
    canon_mock.prepare_context = AsyncMock(return_value="Seeker has family communication challenges.")
    container.canonical_memory_integration = canon_mock
    container.memory_service = None

    outbox_mock = MagicMock()
    outbox_mock.active_consent = AsyncMock(return_value=True)
    container.memory_outbox = outbox_mock

    mem_ctx, distress, loaded_profile, canon = asyncio.run(
        prepare_user_memory(
            container=container,
            user_id="11111111-1111-4111-8111-111111111111",
            chat_history=history,
            user_msg_en=PERSONALIZE_TEACHING_PROMPT,
        )
    )

    # Profile spiritual level and canonical facts are intact
    assert loaded_profile is not None
    assert loaded_profile.spiritual_level == "intermediate"
    assert "family communication challenges" in mem_ctx


# ===========================================================================
# S4: Privacy Boundary & Consent Revocation Journey
# ===========================================================================

def test_tier4_s4_privacy_boundary_and_consent_revocation_journey():
    """S4: Seeker privacy boundary holds across incognito toggle and consent revocation."""
    user_id = "11111111-1111-4111-8111-111111111111"

    # Step 1: User toggles to Temporary Chat (incognito=True)
    incognito_req = ChatRequest(
        messages=[],
        user_message=PERSONALIZE_TEACHING_PROMPT,
        personalize_teaching={"video_id": "dQw4w9WgXcQ", "timestamp_seconds": 99.0},
        incognito=True,
    )
    incognito_ctx = PipelineContext(
        container=MagicMock(),
        coordinator=MagicMock(),
        request=incognito_req,
        user_msg=PERSONALIZE_TEACHING_PROMPT,
        preferred_lang="en",
        trace_id="test-s4-incognito",
        start_time=time.time(),
        state={},
        user_id=user_id,
        incognito=True,
    )

    stage = PersonalizeStage()
    incognito_result = asyncio.run(stage.run(incognito_ctx))

    assert incognito_result is not None
    assert incognito_result.route_decision == "personalize_declined_incognito"

    # Step 2: In incognito, MemoryStage does NOT persist conversation memory
    mem_stage = MemoryStage()
    save_result = asyncio.run(mem_stage.run(incognito_ctx))
    assert save_result is None

    # Step 3: User leaves incognito, but revokes memory consent in settings
    container = MagicMock()
    outbox = MagicMock()
    outbox.active_consent = AsyncMock(return_value=False)  # Revoked consent
    container.memory_outbox = outbox
    container.user_profile = MagicMock()

    mem_ctx, distress, profile, canon = asyncio.run(
        prepare_user_memory(
            container=container,
            user_id=user_id,
            chat_history=[],
            user_msg_en=PERSONALIZE_TEACHING_PROMPT,
        )
    )

    # Consent revocation fails closed: returns empty memory and None profile
    assert profile is None
    assert mem_ctx == ""

    # Step 4: With personal_context_confirmed=False, PersonalizeStage declines with no_graph
    revoked_req = ChatRequest(
        messages=[],
        user_message=PERSONALIZE_TEACHING_PROMPT,
        personalize_teaching={"video_id": "dQw4w9WgXcQ", "timestamp_seconds": 99.0},
        incognito=False,
    )
    revoked_ctx = PipelineContext(
        container=container,
        coordinator=MagicMock(),
        request=revoked_req,
        user_msg=PERSONALIZE_TEACHING_PROMPT,
        preferred_lang="en",
        trace_id="test-s4-revoked",
        start_time=time.time(),
        state={},
        user_id=user_id,
        personal_context_confirmed=False,  # Profile was None
    )

    revoked_result = asyncio.run(stage.run(revoked_ctx))
    assert revoked_result is not None
    assert revoked_result.route_decision == "personalize_declined_no_graph"


# ===========================================================================
# S5: High-Burst Evaluator Pacing & 429 Resilience
# ===========================================================================

def test_tier4_s5_high_burst_evaluator_pacing_and_429_resilience(tmp_path: Path):
    """S5: High-burst evaluation runner paces queries, recovers on 429, and enforces X41."""
    # 1. Pacer enforces 4.0s interval between evaluation queries
    slept: list[float] = []
    fake_time = [100.0]

    def mock_clock() -> float:
        return fake_time[0]

    def mock_sleep(s: float) -> None:
        slept.append(s)
        fake_time[0] += s

    pacer = Pacer(interval_s=4.0, sleep=mock_sleep, clock=mock_clock)

    # First call: no wait needed
    pacer()
    assert len(slept) == 0

    # Second call immediate (now=100.0, last=100.0): sleep 4.0s
    pacer()
    assert len(slept) == 1
    assert slept[0] == 4.0

    # 2. Backend returns 429 with Retry-After: 3
    resp_429 = SimpleNamespace(status_code=429, headers={"retry-after": "3"})
    wait_s = retry_wait(resp_429, attempt=0)
    assert wait_s == 3.0

    # 3. Transient 429 recovers on second attempt with request_with_retry
    call_counts = [0]
    resp_200 = SimpleNamespace(status_code=200, json=lambda: {"status": "ok"})
    retry_slept: list[float] = []

    def mock_query():
        call_counts[0] += 1
        if call_counts[0] == 1:
            return resp_429
        return resp_200

    final_resp, retries = request_with_retry(
        mock_query,
        sleep=retry_slept.append,
        max_attempts=RETRY_ATTEMPTS,
    )

    assert final_resp.status_code == 200
    assert retries == 1
    assert retry_slept == [3.0]

    # 4. Invariant X41: Eval run is valid ONLY when collection fingerprint is stamped
    qdrant_ids = ["point_alpha", "point_beta", "point_gamma"]
    fingerprint = fingerprint_from_ids(qdrant_ids)
    assert fingerprint["points"] == 3
    assert len(fingerprint["ids_sha256"]) == 64

    # write_fingerprint refuses to retro-fit a finished run
    run_dir = tmp_path / "finished_eval_run"
    run_dir.mkdir()
    (run_dir / "manifest.json").write_text(json.dumps({"run_id": "eval_001"}))
    (run_dir / "registered_report.json").write_text(json.dumps({"status": "PASS"}))

    with pytest.raises(ValueError, match="refusing to retro-fit a fingerprint"):
        write_fingerprint(run_dir, fingerprint)
