"""Tests for Release Provenance & Stage Telemetry (Phase 3).

Verifies:
1. ReleaseManifest immutability, getters, to_dict, and readiness validation (rejecting malformed manifests and secrets).
2. Every response path carries the release manifest (normal, guardrail, distress, cache, errors, fallbacks, streaming, ChatEngine).
3. StageRunner bounded and privacy-safe stage telemetry.
4. Cache and coalesce key scoping by release ID and policy version.
"""

from __future__ import annotations

import asyncio
from dataclasses import FrozenInstanceError
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.chat_engine import ChatChunk, ChatEngine, ChatResult
from app.dependencies import ServiceContainer
from app.orchestrator import _stream_done_metadata
from app.pipeline.pipeline_coordinator import PipelineCoordinator
from app.pipeline.result import PipelineResult
from app.pipeline.stages import PipelineContext, StageRunner
from app.pipeline.stages.base import Stage
from app.pipeline.stages.cache_stage import CacheCheckStage
from app.pipeline.stages.distress_stage import DistressStage
from app.pipeline.stages.doctrine_cache_stage import DoctrineCacheStage
from app.pipeline.stages.glue_stages import CasualShortCircuitStage, ResultAssemblyStage
from app.pipeline.stages.guardrail_stage import InputGuardrailStage
from app.release_manifest import (
    ReleaseManifest,
    ReleaseManifestError,
    build_release_manifest,
    get_release_manifest,
    set_release_manifest,
    validate_release_manifest,
)
from app.schemas import ChatRequest, ChatResponse
from services.serene_mind_engine import DistressAssessment, DistressLevel

# ---------------------------------------------------------------------------
# 1. ReleaseManifest Invariants & Readiness Validation Tests
# ---------------------------------------------------------------------------


def test_release_manifest_immutability():
    """Verify ReleaseManifest is frozen and cannot be mutated."""
    manifest = build_release_manifest()
    with pytest.raises(FrozenInstanceError):
        manifest.release_id = "mutated-id"  # type: ignore


def test_release_manifest_singleton_and_to_dict():
    """Verify singleton accessor and to_dict structure."""
    manifest = get_release_manifest()
    assert isinstance(manifest, ReleaseManifest)
    data = manifest.to_dict()

    expected_keys = {
        "release_id",
        "git_sha",
        "build_timestamp",
        "corpus_version",
        "embedding_model",
        "embedding_dim",
        "reranker_model",
        "policy_version",
        "schema_version",
    }
    assert expected_keys.issubset(data.keys())
    assert isinstance(data["release_id"], str) and data["release_id"]
    assert isinstance(data["embedding_dim"], int) and data["embedding_dim"] > 0
    assert not isinstance(data["embedding_dim"], bool)


def test_release_manifest_readiness_valid():
    """Verify a properly constructed manifest passes validation."""
    manifest = ReleaseManifest(
        release_id="rel-2026-08-v1",
        git_sha="0123456789abcdef0123456789abcdef01234567",
        build_timestamp="2026-08-17T12:00:00Z",
        corpus_version="1",
        embedding_model="BAAI/bge-m3",
        embedding_dim=1024,
        reranker_model="BAAI/bge-reranker-v2-m3",
        policy_version="gemini-flash-budget-v1",
        schema_version="1.0.0",
    )
    manifest.validate()
    validate_release_manifest(manifest)


@pytest.mark.parametrize(
    "field_override,value",
    [
        ("release_id", ""),
        ("release_id", "   "),
        ("git_sha", ""),
        ("build_timestamp", ""),
        ("corpus_version", ""),
        ("embedding_model", ""),
        ("reranker_model", ""),
        ("policy_version", ""),
        ("schema_version", ""),
    ],
)
def test_release_manifest_rejects_empty_string_fields(field_override, value):
    """Verify empty or whitespace string fields raise ReleaseManifestError."""
    base_kwargs = {
        "release_id": "rel-1",
        "git_sha": "abc1234",
        "build_timestamp": "2026-08-17T00:00:00Z",
        "corpus_version": "1",
        "embedding_model": "BAAI/bge-m3",
        "embedding_dim": 1024,
        "reranker_model": "BAAI/bge-reranker-v2-m3",
        "policy_version": "gemini-flash-budget-v1",
        "schema_version": "1.0.0",
    }
    base_kwargs[field_override] = value
    manifest = ReleaseManifest(**base_kwargs)
    with pytest.raises(
        ReleaseManifestError, match=f"'{field_override}' must be a non-empty string"
    ):
        manifest.validate()


def test_build_release_manifest_whitespace_release_id_falls_back():
    """Whitespace-only release_id should fall back to the derived identifier."""
    manifest = build_release_manifest(
        release_id="   ",
        git_sha="abcdef0123456789abcdef0123456789abcdef01",
        corpus_version="7",
        policy_version="policy-x",
    )
    assert manifest.release_id == "rel-abcdef01-c7-ppolicy-x"


@pytest.mark.parametrize("invalid_dim", [0, -1, -1024, True, False, "1024", 1024.5])
def test_release_manifest_rejects_invalid_embedding_dim(invalid_dim):
    """Verify non-positive or non-integer embedding dimensions raise ReleaseManifestError."""
    manifest = ReleaseManifest(
        release_id="rel-1",
        git_sha="abc1234",
        build_timestamp="2026-08-17T00:00:00Z",
        corpus_version="1",
        embedding_model="BAAI/bge-m3",
        embedding_dim=invalid_dim,  # type: ignore
        reranker_model="BAAI/bge-reranker-v2-m3",
        policy_version="gemini-flash-budget-v1",
        schema_version="1.0.0",
    )
    with pytest.raises(ReleaseManifestError, match="must be a positive integer"):
        manifest.validate()


@pytest.mark.parametrize(
    "secret_value",
    [
        "sk-proj-1234567890abcdef1234567890",
        "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.abc",
        "ghp_1234567890abcdef1234567890abcdef",
        "-----BEGIN " + "RSA " + "PRIVATE KEY-----\nMIIEowIBAAKCAQEA0...",
        "password = 'super_secret_password_123'",
        "api_key='sk-1234567890abcdef'",
    ],
)
def test_release_manifest_rejects_secrets_and_tokens(secret_value):
    """Verify that any potential secret, private key, or credential is automatically rejected."""
    manifest = ReleaseManifest(
        release_id="rel-1",
        git_sha=secret_value,
        build_timestamp="2026-08-17T00:00:00Z",
        corpus_version="1",
        embedding_model="BAAI/bge-m3",
        embedding_dim=1024,
        reranker_model="BAAI/bge-reranker-v2-m3",
        policy_version="gemini-flash-budget-v1",
        schema_version="1.0.0",
    )
    with pytest.raises(ReleaseManifestError, match="contains potential secret"):
        manifest.validate()


# ---------------------------------------------------------------------------
# 2. Response Path Provenance Tests
# ---------------------------------------------------------------------------


def test_pipeline_result_with_latency_and_to_chat_response():
    """Verify PipelineResult preserves release_manifest through with_latency and to_chat_response."""
    manifest_dict = get_release_manifest().to_dict()
    res = PipelineResult(
        final_answer="Peace and stillness.",
        intent="CASUAL",
        release_manifest=manifest_dict,
    )
    assert res.release_manifest == manifest_dict

    updated = res.with_latency(120)
    assert updated.latency_ms == 120
    assert updated.release_manifest == manifest_dict

    chat_resp_dict = res.to_chat_response()
    assert chat_resp_dict["release_manifest"] == manifest_dict


def test_chat_response_schema_release_manifest():
    """Verify ChatResponse serializes only the public release_manifest projection."""
    manifest_dict = get_release_manifest().to_dict()
    resp = ChatResponse(
        response="Meditate on the breath.",
        release_manifest=manifest_dict,
    )
    assert resp.release_manifest is not None
    assert resp.release_manifest.release_id == manifest_dict["release_id"]
    assert resp.release_manifest.policy_version == manifest_dict["policy_version"]
    assert resp.release_manifest.schema_version == manifest_dict["schema_version"]
    dumped = resp.model_dump()
    assert dumped["release_manifest"] == {
        "release_id": manifest_dict["release_id"],
        "policy_version": manifest_dict["policy_version"],
        "schema_version": manifest_dict["schema_version"],
    }


@pytest.mark.asyncio
async def test_input_guardrail_block_attaches_manifest():
    """Verify InputGuardrailStage attaches release_manifest to the blocked PipelineResult."""
    stage = InputGuardrailStage()
    container = MagicMock(spec=ServiceContainer)
    container.guardrails = MagicMock()
    container.guardrails.check_input = AsyncMock(
        return_value={
            "blocked": True,
            "reason": "Harmful pattern detected",
            "response": "I cannot fulfill this.",
        }
    )

    ctx = PipelineContext(
        container=container,
        coordinator=MagicMock(),
        request=ChatRequest(user_message="Harmful prompt", messages=[]),
        user_msg="Harmful prompt",
        preferred_lang="en",
        state={"user_msg_en": "Harmful prompt"},
    )

    res = await stage.run(ctx)
    assert res is not None
    assert res.blocked is True
    assert res.release_manifest is not None
    assert res.release_manifest["release_id"] == get_release_manifest().release_id


@pytest.mark.asyncio
async def test_crisis_preemption_attaches_manifest():
    """Verify DistressStage crisis preemption attaches release_manifest."""
    stage = DistressStage()
    container = MagicMock(spec=ServiceContainer)
    ctx = PipelineContext(
        container=container,
        coordinator=MagicMock(),
        request=ChatRequest(user_message="I want to end my life", messages=[]),
        user_msg="I want to end my life",
        preferred_lang="en",
        state={"user_msg_en": "I want to end my life"},
    )
    assessment = DistressAssessment(
        level=DistressLevel.CRISIS,
        confidence=0.99,
        detected_signals=["self_harm"],
    )

    res = await stage._crisis_preemption_result(ctx, assessment)
    assert res.intent == "DISTRESS"
    assert res.release_manifest is not None
    assert res.release_manifest["release_id"] == get_release_manifest().release_id


@pytest.mark.asyncio
async def test_doctrine_cache_hit_attaches_manifest():
    """Verify DoctrineCacheStage attaches release_manifest on hit."""
    stage = DoctrineCacheStage()
    container = MagicMock(spec=ServiceContainer)
    mock_cache = MagicMock()
    mock_cache.lookup.return_value = "The Four Sacred Secrets lead to inner peace."
    container.doctrine_cache = mock_cache

    ctx = PipelineContext(
        container=container,
        coordinator=MagicMock(),
        request=ChatRequest(user_message="What are the four sacred secrets?", messages=[]),
        user_msg="What are the four sacred secrets?",
        preferred_lang="en",
        state={"user_msg_en": "What are the four sacred secrets?"},
    )

    with patch("app.pipeline.stages.doctrine_cache_stage.settings.doctrine_cache_enabled", True):
        res = await stage.run(ctx)
        assert res is not None
        assert res.cache_hit is True
        assert res.release_manifest is not None
        assert res.release_manifest["release_id"] == get_release_manifest().release_id


@pytest.mark.asyncio
async def test_cache_stage_hits_attach_manifest():
    """Verify CacheCheckStage attaches release_manifest on hot, vector, and semantic hits."""
    stage = CacheCheckStage()
    container = MagicMock(spec=ServiceContainer)
    container.guardrails = MagicMock()
    container.guardrails.check_output = AsyncMock(
        return_value={"blocked": False, "moderated_response": ""}
    )

    ctx = PipelineContext(
        container=container,
        coordinator=MagicMock(),
        request=ChatRequest(user_message="What is meditation?", messages=[]),
        user_msg="What is meditation?",
        preferred_lang="en",
        cache_key="test_cache_key",
        state={},
    )

    # 1. Hot cache hit
    with patch(
        "app.pipeline.stages.cache_stage.hot_cache.get",
        return_value=("Meditation is stillness.", ["http://ref1"], "QUERY"),
    ):
        res = await stage.run(ctx)
        assert res is not None
        assert res.cache_hit is True
        assert res.release_manifest is not None
        assert res.release_manifest["release_id"] == get_release_manifest().release_id

    # 2. Vector cache hit
    with (
        patch("app.pipeline.stages.cache_stage.hot_cache.get", return_value=None),
        patch("app.pipeline.stages.cache_stage.settings.hybrid_search_enabled", True),
    ):
        ctx.coordinator._check_vector_cache = AsyncMock(
            return_value=("Vector meditation answer.", ["http://ref2"], "QUERY")
        )
        res = await stage.run(ctx)
        assert res is not None
        assert res.cache_hit is True
        assert res.release_manifest is not None
        assert res.release_manifest["release_id"] == get_release_manifest().release_id

    # 3. Exact/Semantic cache hit
    with (
        patch("app.pipeline.stages.cache_stage.hot_cache.get", return_value=None),
        patch("app.pipeline.stages.cache_stage.settings.hybrid_search_enabled", False),
    ):
        container.exact_cache = MagicMock()
        container.exact_cache.get.return_value = {
            "response": "Exact cached answer.",
            "intent": "QUERY",
            "citations": [],
        }
        res = await stage.run(ctx)
        assert res is not None
        assert res.cache_hit is True
        assert res.release_manifest is not None
        assert res.release_manifest["release_id"] == get_release_manifest().release_id


@pytest.mark.asyncio
async def test_instant_greeting_and_result_assembly_attach_manifest():
    """Verify InstantGreetingStage and ResultAssemblyStage attach release_manifest."""
    container = MagicMock(spec=ServiceContainer)
    coordinator = MagicMock()
    coordinator._build_retrieval_meta.return_value = None
    coordinator._build_trigger_events.return_value = []
    coordinator._build_safety_events.return_value = []
    coordinator._build_spans.return_value = []
    coordinator._build_response_data.return_value = {
        "faithfulness": 1.0,
        "hallucination_flag": False,
    }

    # Greeting
    greeting_stage = CasualShortCircuitStage()
    ctx_greeting = PipelineContext(
        container=container,
        coordinator=coordinator,
        request=ChatRequest(user_message="Hello", messages=[]),
        user_msg="Hello",
        preferred_lang="en",
        state={"user_msg_en": "hello"},
    )
    res_greeting = await greeting_stage.run(ctx_greeting)
    assert res_greeting is not None
    assert res_greeting.intent == "CASUAL"
    assert res_greeting.release_manifest is not None
    assert res_greeting.release_manifest["release_id"] == get_release_manifest().release_id

    # Result assembly
    assembly_stage = ResultAssemblyStage()
    ctx_assembly = PipelineContext(
        container=container,
        coordinator=coordinator,
        request=ChatRequest(user_message="Teach me", messages=[]),
        user_msg="Teach me",
        preferred_lang="en",
        final_answer="Here is the teaching.",
        intent="QUERY",
        incognito=True,  # skip compliance logger I/O in test
    )
    res_assembly = await assembly_stage.run(ctx_assembly)
    assert res_assembly is not None
    assert res_assembly.release_manifest is not None
    assert res_assembly.release_manifest["release_id"] == get_release_manifest().release_id


@pytest.mark.asyncio
async def test_coordinator_fallbacks_and_timeouts_attach_manifest():
    """Verify PipelineCoordinator attaches release_manifest on timeout and error fallbacks."""
    container = MagicMock(spec=ServiceContainer)
    coordinator = PipelineCoordinator(container)

    # Circuit breaker result helper
    circuit_res = coordinator._circuit_open_result(is_benchmark=False, start_time=0.0)
    assert circuit_res.release_manifest is not None
    assert circuit_res.release_manifest["release_id"] == get_release_manifest().release_id

    # Timeout fallback via execute
    with patch(
        "app.pipeline.pipeline_coordinator.StageRunner.run", side_effect=asyncio.TimeoutError
    ):
        res_timeout = await coordinator.execute(
            user_msg="Slow request",
            preferred_lang="en",
            chat_body=ChatRequest(user_message="Slow request", messages=[]),
        )
        assert res_timeout.intent == "TIMEOUT"
        assert res_timeout.release_manifest is not None
        assert res_timeout.release_manifest["release_id"] == get_release_manifest().release_id

    # Exception fallback via execute
    with patch(
        "app.pipeline.pipeline_coordinator.StageRunner.run", side_effect=RuntimeError("Boom")
    ):
        res_error = await coordinator.execute(
            user_msg="Crashing request",
            preferred_lang="en",
            chat_body=ChatRequest(user_message="Crashing request", messages=[]),
        )
        assert res_error.intent == "ERROR"
        assert res_error.release_manifest is not None
        assert res_error.release_manifest["release_id"] == get_release_manifest().release_id


def test_stream_done_metadata_includes_manifest():
    """Verify _stream_done_metadata includes release_manifest."""
    manifest_dict = get_release_manifest().to_dict()
    res = PipelineResult(
        final_answer="Grounded answer.",
        intent="QUERY",
        release_manifest=manifest_dict,
    )
    meta = _stream_done_metadata(res)
    assert "release_manifest" in meta
    assert meta["release_manifest"] == manifest_dict


@pytest.mark.asyncio
async def test_chat_engine_batch_and_stream_emit_manifest():
    """Verify ChatEngine batch chat_advanced and streaming chat_advanced_stream emit release_manifest."""
    container = MagicMock(spec=ServiceContainer)
    engine = ChatEngine(container)
    manifest_dict = get_release_manifest().to_dict()

    fake_pipeline_result = PipelineResult(
        final_answer="Wisdom from the heart.",
        intent="QUERY",
        citations=["https://sacred.source/doc1"],
        release_manifest=manifest_dict,
    )

    mock_coordinator = MagicMock()
    mock_coordinator.execute = AsyncMock(return_value=fake_pipeline_result)
    engine._coordinator = mock_coordinator

    # 1. Batch API
    req = ChatRequest(user_message="Guide me", messages=[], incognito=True)
    batch_res = await engine.chat_advanced(req, user={"id": "u123"})
    assert isinstance(batch_res, ChatResult)
    assert batch_res.release_manifest == manifest_dict

    # 2. Streaming API
    mock_stream_coordinator = MagicMock()
    mock_stream_coordinator.coordinator = mock_coordinator
    engine._stream_coordinator = mock_stream_coordinator

    chunks: list[ChatChunk] = []
    async for chunk in engine.chat_advanced_stream(req, user={"id": "u123"}):
        chunks.append(chunk)

    assert len(chunks) > 0
    final_chunk = chunks[-1]
    assert final_chunk.is_final is True
    assert final_chunk.release_manifest == manifest_dict


# ---------------------------------------------------------------------------
# 3. StageRunner Stage Telemetry Tests
# ---------------------------------------------------------------------------


class _SuccessStage(Stage):
    name = "success_stage"

    async def run(self, ctx: PipelineContext) -> PipelineResult | None:
        ctx.last_stage_status = "success"
        return None


class _CustomStatusStage(Stage):
    name = "custom_status_stage"

    async def run(self, ctx: PipelineContext) -> PipelineResult | None:
        ctx.last_stage_status = "cached"
        return None


class _FailingStage(Stage):
    name = "failing_stage"

    async def run(self, ctx: PipelineContext) -> PipelineResult | None:
        raise ValueError("Invalid stage operation")


@pytest.mark.asyncio
async def test_stage_runner_records_bounded_telemetry():
    """Verify StageRunner records privacy-safe bounded telemetry for every stage."""
    ctx = PipelineContext(
        container=MagicMock(),
        coordinator=MagicMock(),
        request=ChatRequest(user_message="Hello", messages=[]),
        user_msg="Hello",
        preferred_lang="en",
    )

    stages = [_SuccessStage(), _CustomStatusStage()]
    await StageRunner.run(stages, ctx)

    assert len(ctx.stage_telemetry) == 2
    rec1 = ctx.stage_telemetry[0]
    assert rec1["stage"] == "success_stage"
    assert rec1["status"] == "success"
    assert rec1["duration_ms"] >= 0.0
    assert rec1["error_code"] is None
    assert rec1["release_id"] == get_release_manifest().release_id

    rec2 = ctx.stage_telemetry[1]
    assert rec2["stage"] == "custom_status_stage"
    assert rec2["status"] == "cached"
    assert rec2["duration_ms"] >= 0.0
    assert rec2["error_code"] is None


@pytest.mark.asyncio
async def test_stage_runner_records_bounded_error_code():
    """Verify failing stages record bounded error_code without sensitive details."""
    ctx = PipelineContext(
        container=MagicMock(),
        coordinator=MagicMock(),
        request=ChatRequest(user_message="Secret password prompt", messages=[]),
        user_msg="Secret password prompt",
        preferred_lang="en",
    )

    stages = [_SuccessStage(), _FailingStage()]
    with pytest.raises(ValueError):
        await StageRunner.run(stages, ctx)

    assert len(ctx.stage_telemetry) == 2
    err_rec = ctx.stage_telemetry[1]
    assert err_rec["stage"] == "failing_stage"
    assert err_rec["status"] == "error"
    assert err_rec["error_code"] == "ValueError"
    assert err_rec["duration_ms"] >= 0.0
    assert err_rec["release_id"] == get_release_manifest().release_id
    # Assert privacy: no prompt or sensitive words in telemetry
    assert "password" not in str(err_rec)


# ---------------------------------------------------------------------------
# 4. Cache Key Scoping Tests
# ---------------------------------------------------------------------------


def test_cache_keys_scoped_by_release_and_policy_version():
    """Verify that changing release_id or policy_version produces different cache keys."""
    container = MagicMock(spec=ServiceContainer)
    coordinator = PipelineCoordinator(container)

    # Initial manifest
    m1 = ReleaseManifest(
        release_id="rel-2026-08-17-A",
        git_sha="0000000000000000000000000000000000000001",
        build_timestamp="2026-08-17T00:00:00Z",
        corpus_version="1",
        embedding_model="BAAI/bge-m3",
        embedding_dim=1024,
        reranker_model="BAAI/bge-reranker-v2-m3",
        policy_version="policy-v1",
        schema_version="1.0.0",
    )
    set_release_manifest(m1)
    k1 = coordinator._build_context_aware_cache_key("What is the golden orb?", "en")

    assert ":rel:rel-2026-08-17-A:" in k1
    assert ":pol:policy-v1" in k1

    # Updated release_id
    m2 = ReleaseManifest(
        release_id="rel-2026-08-17-B",
        git_sha="0000000000000000000000000000000000000002",
        build_timestamp="2026-08-17T00:00:00Z",
        corpus_version="1",
        embedding_model="BAAI/bge-m3",
        embedding_dim=1024,
        reranker_model="BAAI/bge-reranker-v2-m3",
        policy_version="policy-v1",
        schema_version="1.0.0",
    )
    set_release_manifest(m2)
    k2 = coordinator._build_context_aware_cache_key("What is the golden orb?", "en")

    assert ":rel:rel-2026-08-17-B:" in k2
    assert k1 != k2

    # Updated policy_version
    m3 = ReleaseManifest(
        release_id="rel-2026-08-17-A",
        git_sha="0000000000000000000000000000000000000001",
        build_timestamp="2026-08-17T00:00:00Z",
        corpus_version="1",
        embedding_model="BAAI/bge-m3",
        embedding_dim=1024,
        reranker_model="BAAI/bge-reranker-v2-m3",
        policy_version="policy-v2-tightened",
        schema_version="1.0.0",
    )
    set_release_manifest(m3)
    k3 = coordinator._build_context_aware_cache_key("What is the golden orb?", "en")

    assert ":pol:policy-v2-tightened" in k3
    assert k1 != k3

    # Reset manifest singleton
    set_release_manifest(None)


def test_chat_engine_coalesce_key_scoped_by_release_id():
    """Verify ChatEngine coalesce keys vary with release_id."""
    engine = ChatEngine(MagicMock(spec=ServiceContainer))

    m1 = ReleaseManifest(
        release_id="rel-A",
        git_sha="1111111111111111111111111111111111111111",
        build_timestamp="2026-08-17T00:00:00Z",
        corpus_version="1",
        embedding_model="BAAI/bge-m3",
        embedding_dim=1024,
        reranker_model="BAAI/bge-reranker-v2-m3",
        policy_version="pol-1",
        schema_version="1.0.0",
    )
    set_release_manifest(m1)
    k1 = engine._build_coalesce_key("What is meditation?", "user_1", "sess_1", None, "en")

    m2 = ReleaseManifest(
        release_id="rel-B",
        git_sha="2222222222222222222222222222222222222222",
        build_timestamp="2026-08-17T00:00:00Z",
        corpus_version="1",
        embedding_model="BAAI/bge-m3",
        embedding_dim=1024,
        reranker_model="BAAI/bge-reranker-v2-m3",
        policy_version="pol-1",
        schema_version="1.0.0",
    )
    set_release_manifest(m2)
    k2 = engine._build_coalesce_key("What is meditation?", "user_1", "sess_1", None, "en")

    assert "rag:v3:rel-A:pol-1:" in k1
    assert "rag:v3:rel-B:pol-1:" in k2
    assert k1 != k2

    set_release_manifest(None)
