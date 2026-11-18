"""Tier 2: Boundary Value Analysis & Corner Cases E2E Tests (25 Tests).

Requirement-driven opaque-box verification probing exact threshold limits across Features F1-F4:
- Span limit bounds: limit=2 on hit_index=2 (clamping), limit=1 single-hit, parent length bounds.
- Word count floors: 17 words (rejected) vs 18 words (accepted in context) vs 22 words vs 23 words (standalone floor).
- Hard standalone gates: trailing prepositions and dangling conjunctions rejected regardless of semantic scoring.
- ChatRequest validation: malformed video_id length/charset, negative timestamp, NaN/inf timestamp, unexpected prompt string.
- Privacy boundary: incognito refusal (personalize_declined_incognito), anonymous refusal (personalize_declined_anonymous), non-consenting refusal (personalize_declined_no_graph).
- Rate limiting: HTTP 429 with Retry-After header, exponential backoff pacing, max retry exhaustion.
"""

from __future__ import annotations

import asyncio
import math
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from app.pipeline.stages.context import PipelineContext
from app.pipeline.stages.personalize_stage import (
    PERSONALIZE_TEACHING_PROMPT,
    PersonalizeStage,
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
    RETRY_CAP_S,
    Pacer,
    request_with_retry,
    retry_wait,
)
from services.first_person_context_harness import (
    FirstPersonContextHarness,
    HarnessPolicy,
)
from services.first_person_evidence_policy import (
    _clip_length_problem,
    _context_standalone_problem,
    _ends_on_dangling_word,
    _standalone_problem,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
HASH = "b" * 64


# ===========================================================================
# Helpers for Synthetic Spans and Contexts
# ===========================================================================

def _make_span(n: int = 0, text: str = "Suffering dissolves in quiet awareness.", **overrides) -> SourceSpan:
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
        "parent_unit_id": overrides.get("parent_unit_id", "parent_002"),
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
        score=0.92,
    )


# ===========================================================================
# 1. Span Limit Boundary Value Analysis
# ===========================================================================

def test_bva_01_span_limit_edge_hit_index_2_clamped_to_limit():
    """BVA 1: limit=2 on hit_index=2 is strictly clamped to at most 2 spans."""
    spans = [_make_span(i, f"Teaching span {i} on meditation.") for i in range(5)]
    ctx = _make_context(spans, hit_index=2)

    harness = FirstPersonContextHarness(HarnessPolicy(max_context_spans=2))
    windowed = harness._window(ctx, span_limit=2)

    assert len(windowed) == 2


def test_bva_02_span_limit_edge_limit_1_returns_single_hit_span():
    """BVA 2: limit=1 on hit_index=2 strictly returns single hit span without predecessors."""
    spans = [_make_span(i, f"Teaching span {i} on stillness.") for i in range(5)]
    ctx = _make_context(spans, hit_index=2)

    harness = FirstPersonContextHarness(HarnessPolicy(max_context_spans=1))
    windowed = harness._window(ctx, span_limit=1)

    assert len(windowed) == 1
    assert windowed[0].source_span_index == 2
    assert windowed[0].source_span_id == ctx.hit_span_ids[0]


def test_bva_03_span_limit_edge_limit_exceeding_parent_spans():
    """BVA 3: limit=10 on 3-span parent returns exactly 3 spans bounded by parent count."""
    spans = [_make_span(i, f"Teaching chunk {i} on presence.") for i in range(3)]
    ctx = _make_context(spans, hit_index=1)

    harness = FirstPersonContextHarness(HarnessPolicy(max_context_spans=10))
    windowed = harness._window(ctx, span_limit=10)

    assert len(windowed) == 3
    assert [s.source_span_index for s in windowed] == [0, 1, 2]


# ===========================================================================
# 2. Word Count Floors Boundary Value Analysis
# ===========================================================================

def test_bva_04_word_floor_17_words_context_rejected():
    """BVA 4: 17-word span in context mode fails boundary check with too_short."""
    # Exactly 17 words:
    # 1:Awareness 2:sees 3:the 4:movement 5:of 6:thought 7:without 8:following 9:it,
    # 10:and 11:in 12:that 13:seeing 14:mind 15:grows 16:very 17:still.
    text_17 = (
        "Awareness sees the movement of thought without following it, and in that "
        "seeing mind grows very still."
    )
    words = text_17.split()
    assert len(words) == 17

    result = _context_standalone_problem([text_17], is_complete_thought=True, is_standalone=True)
    assert result == "too_short"


def test_bva_05_word_floor_18_words_context_accepted():
    """BVA 5: 18-word span in context mode reaches the exact context floor and passes."""
    # Exactly 18 words (adding 'the'):
    text_18 = (
        "Awareness sees the movement of thought without following it, and in that "
        "seeing the mind grows very still."
    )
    words = text_18.split()
    assert len(words) == 18

    result = _context_standalone_problem([text_18], is_complete_thought=True, is_standalone=True)
    assert result is None


def test_bva_06_word_floor_22_words_standalone_single_clip_rejected():
    """BVA 6: 22-word clip in standalone single-clip mode fails boundary with too_short."""
    # Exactly 22 words:
    text_22 = (
        "When you observe your own inner state without resistance or judgment, "
        "a profound transformation happens deeply in your quiet and peaceful consciousness."
    )
    words = text_22.split()
    assert len(words) == 22

    result = _clip_length_problem(text_22, is_context=False)
    assert result == "too_short"


def test_bva_07_word_floor_23_words_standalone_single_clip_accepted():
    """BVA 7: 23-word clip in standalone single-clip mode meets 23-word floor and passes."""
    # Exactly 23 words:
    text_23 = (
        "When you observe your own inner state without resistance or judgment, "
        "a profound transformation happens deeply and naturally in your quiet peaceful consciousness."
    )
    words = text_23.split()
    assert len(words) == 23

    result = _clip_length_problem(text_23, is_context=False)
    assert result is None


def test_bva_08_word_ceiling_context_max_words_boundary():
    """BVA 8: Exactly 600 words passes ceiling; 601 words triggers too_long."""
    base = "peace and awareness are natural states of human mind "
    tokens = (base * 70).split()  # > 600 tokens

    text_600 = " ".join(tokens[:599]) + " peace."
    assert len(text_600.split()) == 600
    assert _context_standalone_problem([text_600], is_complete_thought=True, is_standalone=True) is None

    text_601 = " ".join(tokens[:600]) + " peace."
    assert len(text_601.split()) == 601
    assert _context_standalone_problem([text_601], is_complete_thought=True, is_standalone=True) == "too_long"


# ===========================================================================
# 3. Hard Standalone Gates (Syntax Invariants over Semantic Scores)
# ===========================================================================

def test_bva_09_hard_gate_trailing_preposition_rejected_even_if_semantically_verified():
    """BVA 9: Trailing prepositions ('with', 'to', 'of') rejected as ends_mid_sentence."""
    text_with = (
        "Awareness sees the movement of thought without following it, and in that "
        "seeing the mind grows very still with"
    )
    assert _ends_on_dangling_word(text_with) is True

    # Even with is_complete_thought=True and is_standalone=True, hard gate rejects
    result = _context_standalone_problem([text_with], is_complete_thought=True, is_standalone=True)
    assert result == "ends_mid_sentence"


def test_bva_10_hard_gate_dangling_conjunction_rejected_even_if_semantically_verified():
    """BVA 10: Trailing conjunctions ('and', 'or', 'but') rejected as ends_mid_sentence."""
    text_and = (
        "Awareness sees the movement of thought without following it, and in that "
        "seeing the mind grows very still and"
    )
    assert _ends_on_dangling_word(text_and) is True

    result = _context_standalone_problem([text_and], is_complete_thought=True, is_standalone=True)
    assert result == "ends_mid_sentence"


def test_bva_11_hard_gate_trailing_comma_semicolon_rejected():
    """BVA 11: Trailing comma or dash rejected as ends_mid_sentence despite semantic scores."""
    text_comma = (
        "Awareness sees the movement of thought without following it, and in that "
        "seeing the mind grows very still,"
    )
    result = _context_standalone_problem([text_comma], is_complete_thought=True, is_standalone=True)
    assert result == "ends_mid_sentence"


# ===========================================================================
# 4. ChatRequest Schema & Parameter Boundaries
# ===========================================================================

def test_bva_12_chat_request_validation_video_id_too_short():
    """BVA 12: video_id with 10 characters fails validation (exactly 11 required)."""
    with pytest.raises(ValidationError) as exc_info:
        PersonalizeTeachingRef(video_id="1234567890", timestamp_seconds=10.0)
    assert "video_id" in str(exc_info.value)


def test_bva_13_chat_request_validation_video_id_too_long():
    """BVA 13: video_id with 12 characters fails validation."""
    with pytest.raises(ValidationError) as exc_info:
        PersonalizeTeachingRef(video_id="123456789012", timestamp_seconds=10.0)
    assert "video_id" in str(exc_info.value)


def test_bva_14_chat_request_validation_video_id_invalid_characters():
    """BVA 14: video_id with non-base64url characters fails regex validation."""
    with pytest.raises(ValidationError) as exc_info:
        PersonalizeTeachingRef(video_id="dQw4w9WgXc!", timestamp_seconds=10.0)
    assert "video_id" in str(exc_info.value)


def test_bva_15_chat_request_validation_negative_timestamp():
    """BVA 15: timestamp_seconds < 0.0 raises validation error (ge=0.0)."""
    with pytest.raises(ValidationError) as exc_info:
        PersonalizeTeachingRef(video_id="dQw4w9WgXcQ", timestamp_seconds=-0.5)
    assert "timestamp_seconds" in str(exc_info.value)


def test_bva_16_chat_request_validation_zero_timestamp_accepted():
    """BVA 16: timestamp_seconds == 0.0 is valid boundary value."""
    ref = PersonalizeTeachingRef(video_id="dQw4w9WgXcQ", timestamp_seconds=0.0)
    assert ref.timestamp_seconds == 0.0
    assert ref.video_id == "dQw4w9WgXcQ"


def test_bva_17_chat_request_validation_nan_timestamp_rejected():
    """BVA 17: timestamp_seconds=NaN raises validation error (allow_inf_nan=False)."""
    with pytest.raises(ValidationError) as exc_info:
        PersonalizeTeachingRef(video_id="dQw4w9WgXcQ", timestamp_seconds=float("nan"))
    assert "timestamp_seconds" in str(exc_info.value)


def test_bva_18_chat_request_validation_inf_timestamp_rejected():
    """BVA 18: timestamp_seconds=Infinity raises validation error (allow_inf_nan=False)."""
    with pytest.raises(ValidationError) as exc_info:
        PersonalizeTeachingRef(video_id="dQw4w9WgXcQ", timestamp_seconds=float("inf"))
    assert "timestamp_seconds" in str(exc_info.value)


def test_bva_19_chat_request_unexpected_prompt_declined():
    """BVA 19: Unexpected user prompt string declines with personalize_declined_unexpected_prompt."""
    req = ChatRequest(
        messages=[],
        user_message="What did the guru teach about love?",
        personalize_teaching={"video_id": "dQw4w9WgXcQ", "timestamp_seconds": 99.0},
    )
    ctx = PipelineContext(
        container=MagicMock(),
        coordinator=MagicMock(),
        request=req,
        user_msg="What did the guru teach about love?",
        preferred_lang="en",
        trace_id="test-prompt-mismatch",
        start_time=time.time(),
        state={},
        user_id="11111111-1111-4111-8111-111111111111",
        incognito=False,
        personalization_eligible=True,
        personal_context_confirmed=True,
    )

    stage = PersonalizeStage()
    result = asyncio.run(stage.run(ctx))

    assert result is not None
    assert result.route_decision == "personalize_declined_unexpected_prompt"
    assert result.route_metadata["decline_reason"] == "unexpected_prompt"


# ===========================================================================
# 5. Privacy Boundary Value Analysis
# ===========================================================================

def test_bva_20_privacy_boundary_incognito_refusal():
    """BVA 20: Incognito chat declines personalization with personalize_declined_incognito."""
    req = ChatRequest(
        messages=[],
        user_message=PERSONALIZE_TEACHING_PROMPT,
        personalize_teaching={"video_id": "dQw4w9WgXcQ", "timestamp_seconds": 99.0},
        incognito=True,
    )
    ctx = PipelineContext(
        container=MagicMock(),
        coordinator=MagicMock(),
        request=req,
        user_msg=PERSONALIZE_TEACHING_PROMPT,
        preferred_lang="en",
        trace_id="test-incognito-gate",
        start_time=time.time(),
        state={},
        user_id="11111111-1111-4111-8111-111111111111",
        incognito=True,
        personalization_eligible=True,
        personal_context_confirmed=True,
    )

    stage = PersonalizeStage()
    result = asyncio.run(stage.run(ctx))

    assert result is not None
    assert result.route_decision == "personalize_declined_incognito"
    assert result.route_metadata["decline_reason"] == "incognito"


def test_bva_21_privacy_boundary_anonymous_user_refusal():
    """BVA 21: Anonymous / unauthenticated user declines with personalize_declined_anonymous."""
    req = ChatRequest(
        messages=[],
        user_message=PERSONALIZE_TEACHING_PROMPT,
        personalize_teaching={"video_id": "dQw4w9WgXcQ", "timestamp_seconds": 99.0},
    )
    ctx = PipelineContext(
        container=MagicMock(),
        coordinator=MagicMock(),
        request=req,
        user_msg=PERSONALIZE_TEACHING_PROMPT,
        preferred_lang="en",
        trace_id="test-anon-gate",
        start_time=time.time(),
        state={},
        user_id=None,  # Anonymous
        incognito=False,
        personalization_eligible=False,
        personal_context_confirmed=False,
    )

    stage = PersonalizeStage()
    result = asyncio.run(stage.run(ctx))

    assert result is not None
    assert result.route_decision == "personalize_declined_anonymous"
    assert result.route_metadata["decline_reason"] == "anonymous"


def test_bva_22_privacy_boundary_non_consenting_no_graph_refusal():
    """BVA 22: User without confirmed personal knowledge graph declines with personalize_declined_no_graph."""
    req = ChatRequest(
        messages=[],
        user_message=PERSONALIZE_TEACHING_PROMPT,
        personalize_teaching={"video_id": "dQw4w9WgXcQ", "timestamp_seconds": 99.0},
    )
    ctx = PipelineContext(
        container=MagicMock(),
        coordinator=MagicMock(),
        request=req,
        user_msg=PERSONALIZE_TEACHING_PROMPT,
        preferred_lang="en",
        trace_id="test-no-graph-gate",
        start_time=time.time(),
        state={},
        user_id="11111111-1111-4111-8111-111111111111",
        incognito=False,
        personalization_eligible=True,
        personal_context_confirmed=False,  # No personal knowledge map
    )

    stage = PersonalizeStage()
    result = asyncio.run(stage.run(ctx))

    assert result is not None
    assert result.route_decision == "personalize_declined_no_graph"
    assert result.route_metadata["decline_reason"] == "no_graph"


# ===========================================================================
# 6. Rate Limiting Boundary Value Analysis
# ===========================================================================

def test_bva_23_rate_limit_429_retry_after_header_parsing():
    """BVA 23: HTTP 429 with Retry-After header extracts and enforces exact wait seconds."""
    resp = SimpleNamespace(status_code=429, headers={"retry-after": "14"})
    wait = retry_wait(resp, attempt=0)
    assert wait == 14.0

    resp_float = SimpleNamespace(status_code=429, headers={"retry-after": "3.5"})
    wait_float = retry_wait(resp_float, attempt=0)
    assert wait_float == 3.5


def test_bva_24_rate_limit_exponential_backoff_pacing():
    """BVA 24: HTTP 429 without Retry-After header follows exponential backoff capped at 60s."""
    resp = SimpleNamespace(status_code=429, headers={})

    # attempt 0: 5.0 * (2.0 ** 0) = 5.0s
    assert retry_wait(resp, attempt=0) == 5.0
    # attempt 1: 5.0 * (2.0 ** 1) = 10.0s
    assert retry_wait(resp, attempt=1) == 10.0
    # attempt 2: 5.0 * (2.0 ** 2) = 20.0s
    assert retry_wait(resp, attempt=2) == 20.0
    # attempt 3: 5.0 * (2.0 ** 3) = 40.0s
    assert retry_wait(resp, attempt=3) == 40.0
    # attempt 4: 5.0 * (2.0 ** 4) = 80.0s -> Capped at 60.0s
    assert retry_wait(resp, attempt=4) == RETRY_CAP_S


def test_bva_25_rate_limit_max_retry_exhaustion():
    """BVA 25: request_with_retry exhausts max_attempts without crashing, returning last response."""
    slept: list[float] = []
    resp_429 = SimpleNamespace(status_code=429, headers={"retry-after": "1.0"})

    last_resp, retries_used = request_with_retry(
        lambda: resp_429,
        sleep=slept.append,
        max_attempts=RETRY_ATTEMPTS,
    )

    assert last_resp.status_code == 429
    assert retries_used == RETRY_ATTEMPTS - 1
    assert len(slept) == RETRY_ATTEMPTS - 1
    assert all(w == 1.0 for w in slept)
