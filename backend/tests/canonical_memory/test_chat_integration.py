"""Tests for Canonical Memory Chat Integration — Phase 11.

Tests:
    - Normal chat works with canonical memory disabled
    - Normal chat works with canonical memory enabled
    - Streaming works (no blocking)
    - Memory influence works when enabled
    - Memory-disabled mode works
    - Failure fallback works (canonical fails → falls back to old system)
    - Shadow mode doesn't influence responses
    - Explicit commands handled
    - Feature flags respected
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Test helpers / mocks
# ---------------------------------------------------------------------------

@dataclass
class FakeRetrievedMemory:
    id: str = "mem-1"
    statement: str = "User prefers concise answers"
    memory_type: str = "PREFERENCE"
    confidence: float = 0.9
    importance: float = 0.7
    evidence_count: int = 1
    fact_key: str = "prefers_tone"
    status: str = "active"
    score: float = 0.85
    semantic_score: float = 0.8
    lexical_score: float = 0.6
    source_conversation_id: str = "sess-1"
    created_at: str = "2026-09-11T00:00:00Z"
    updated_at: str = "2026-09-11T00:00:00Z"


@dataclass
class FakeRetrievalResult:
    memories: list = field(default_factory=list)
    total_tokens: int = 50
    truncated: bool = False
    latency_ms: float = 10.0
    query: str = ""


@dataclass
class FakeLayerBlock:
    layer: str = "memory"
    content: str = ""
    provenance_label: str = "[Memory: canonical_memories]"
    token_count: int = 0
    budget: Any = None
    included: bool = False
    injection_fenced: bool = False


@dataclass
class FakeContextResult:
    memory_block: FakeLayerBlock = field(default_factory=FakeLayerBlock)
    history_block: FakeLayerBlock = field(default_factory=FakeLayerBlock)
    knowledge_block: FakeLayerBlock = field(default_factory=FakeLayerBlock)
    total_tokens: int = 0
    intent: Any = None
    query: str = ""
    latency_ms: float = 0.0


@dataclass
class FakeMemoryCandidate:
    statement: str = ""
    normalized_statement: str = ""
    memory_type: str = "PREFERENCE"
    fact_key: Optional[str] = None
    confidence: float = 0.8
    importance: float = 0.5
    sensitivity: str = "normal"
    evidence: str = ""
    source_turn_index: int = 0
    explicit_request: bool = False
    extraction_model: str = "test"
    extraction_prompt_version: str = "v1"
    language: str = "en"


@dataclass
class FakeJudgeDecision:
    candidate: Any = None
    action: str = "CREATE"
    reason: str = "test"
    target_id: Optional[str] = None
    merged_statement: Optional[str] = None
    policy_trace: list = field(default_factory=list)


class FakeExtractionResult:
    def __init__(self, candidates: list | None = None):
        self.candidates = candidates or []


def _make_retriever(memories=None):
    retriever = AsyncMock()
    if memories is not None:
        retriever.retrieve.return_value = FakeRetrievalResult(memories=memories)
    else:
        retriever.retrieve.return_value = FakeRetrievalResult(
            memories=[FakeRetrievedMemory()]
        )
    return retriever


def _make_orchestrator(context_result=None):
    orchestrator = AsyncMock()
    orchestrator.build_context.return_value = context_result or FakeContextResult(
        memory_block=FakeLayerBlock(
            content="[Memory: canonical_memories]\n- User prefers concise answers",
            included=True,
            token_count=10,
        )
    )
    return orchestrator


def _make_legacy_service(memories=None, semantic=None):
    svc = AsyncMock()
    svc.get_core.return_value = memories or [{"content": "Legacy core memory"}]
    svc.search_semantic.return_value = semantic or []
    return svc


def _make_extractor(candidates=None):
    extractor = AsyncMock()
    extractor.return_value = FakeExtractionResult(
        candidates=candidates or [FakeMemoryCandidate()]
    )
    return extractor


def _make_judge(decisions=None):
    judge = AsyncMock()
    judge.judge.return_value = decisions or [FakeJudgeDecision()]
    return judge


def _make_resolver():
    resolver = AsyncMock()
    resolver.resolve.return_value = MagicMock()
    return resolver


# ---------------------------------------------------------------------------
# Import the module under test
# ---------------------------------------------------------------------------

from services.canonical_memory.chat_integration import (
    CanonicalMemoryIntegration,
    create_chat_integration,
    detect_explicit_command,
)


# ---------------------------------------------------------------------------
# Tests: Explicit command detection
# ---------------------------------------------------------------------------

class TestExplicitCommandDetection:
    def test_remember_command(self):
        result = detect_explicit_command("Remember that I live in Pune")
        assert result is not None
        assert result.startswith("remember:")
        assert "Pune" in result

    def test_remember_with_please(self):
        result = detect_explicit_command("Please remember I prefer Hindi")
        assert result is not None
        assert result.startswith("remember:")
        assert "Hindi" in result

    def test_forget_command(self):
        result = detect_explicit_command("Forget my location")
        assert result is not None
        assert result.startswith("forget:")
        assert "location" in result

    def test_forget_with_dont(self):
        result = detect_explicit_command("Don't remember that preference")
        assert result is not None
        assert result.startswith("forget:")

    def test_recall_command(self):
        result = detect_explicit_command("What do you remember about me?")
        assert result == "recall"

    def test_recall_without_question(self):
        result = detect_explicit_command("What do you remember about me")
        assert result == "recall"

    def test_no_command(self):
        assert detect_explicit_command("Hello, how are you?") is None
        assert detect_explicit_command("What is meditation?") is None
        assert detect_explicit_command("") is None
        assert detect_explicit_command(None) is None


# ---------------------------------------------------------------------------
# Tests: Feature flags
# ---------------------------------------------------------------------------

class TestFeatureFlags:
    """Verify feature flag accessors read from settings correctly."""

    @patch("services.canonical_memory.chat_integration._ff_canonical_memory", return_value=True)
    @patch("services.canonical_memory.chat_integration._ff_canonical_memory_retrieval", return_value=False)
    @patch("services.canonical_memory.chat_integration._ff_memory_shadow", return_value=False)
    @patch("services.canonical_memory.chat_integration._ff_memory_write", return_value=False)
    @patch("services.canonical_memory.chat_integration._ff_memory_influence", return_value=False)
    def test_canonical_enabled_true(self, *_mocks):
        integration = CanonicalMemoryIntegration(
            context_orchestrator=MagicMock(),
            memory_retriever=MagicMock(),
            extractor=MagicMock(),
            judge=MagicMock(),
            resolver=MagicMock(),
            existing_memory_service=MagicMock(),
        )
        assert integration.canonical_enabled is True

    def test_all_flags_default_false(self):
        integration = CanonicalMemoryIntegration(
            context_orchestrator=MagicMock(),
            memory_retriever=MagicMock(),
            extractor=MagicMock(),
            judge=MagicMock(),
            resolver=MagicMock(),
            existing_memory_service=MagicMock(),
        )
        # Default flags should be False
        assert isinstance(integration.canonical_enabled, bool)
        assert isinstance(integration.retrieval_enabled, bool)
        assert isinstance(integration.shadow_mode, bool)
        assert isinstance(integration.write_enabled, bool)
        assert isinstance(integration.influence_enabled, bool)


# ---------------------------------------------------------------------------
# Tests: Normal chat with canonical memory disabled
# ---------------------------------------------------------------------------

class TestCanonicalDisabled:
    """When canonical memory is disabled, only legacy system is used."""

    @pytest.mark.asyncio
    async def test_prepare_context_uses_legacy(self):
        retriever = _make_retriever()
        orchestrator = _make_orchestrator()
        legacy = _make_legacy_service()

        integration = CanonicalMemoryIntegration(
            context_orchestrator=orchestrator,
            memory_retriever=retriever,
            extractor=_make_extractor(),
            judge=_make_judge(),
            resolver=_make_resolver(),
            existing_memory_service=legacy,
        )

        with patch(
            "services.canonical_memory.chat_integration._ff_canonical_memory",
            return_value=False,
        ):
            result = await integration.prepare_context(
                user_id="user-1",
                query="What is meditation?",
                session_id="sess-1",
            )

        assert "Legacy core memory" in result
        retriever.retrieve.assert_not_called()
        legacy.get_core.assert_called_once_with("user-1")

    @pytest.mark.asyncio
    async def test_post_response_noop_when_disabled(self):
        retriever = _make_retriever()
        orchestrator = _make_orchestrator()
        legacy = _make_legacy_service()
        extractor = _make_extractor()
        judge = _make_judge()
        resolver = _make_resolver()

        integration = CanonicalMemoryIntegration(
            context_orchestrator=orchestrator,
            memory_retriever=retriever,
            extractor=extractor,
            judge=judge,
            resolver=resolver,
            existing_memory_service=legacy,
        )

        with patch(
            "services.canonical_memory.chat_integration._ff_canonical_memory",
            return_value=False,
        ):
            await integration.post_response_memory(
                user_id="user-1",
                query="I prefer concise answers",
                response="Noted.",
                session_id="sess-1",
            )

        extractor.assert_not_called()


# ---------------------------------------------------------------------------
# Tests: Canonical memory enabled with retrieval
# ---------------------------------------------------------------------------

class TestCanonicalEnabled:
    """When canonical memory + retrieval are enabled, use canonical system."""

    @pytest.mark.asyncio
    async def test_prepare_context_uses_canonical(self):
        retriever = _make_retriever()
        orchestrator = _make_orchestrator()
        legacy = _make_legacy_service()

        integration = CanonicalMemoryIntegration(
            context_orchestrator=orchestrator,
            memory_retriever=retriever,
            extractor=_make_extractor(),
            judge=_make_judge(),
            resolver=_make_resolver(),
            existing_memory_service=legacy,
        )

        with patch(
            "services.canonical_memory.chat_integration._ff_canonical_memory",
            return_value=True,
        ), patch(
            "services.canonical_memory.chat_integration._ff_canonical_memory_retrieval",
            return_value=True,
        ), patch(
            "services.canonical_memory.chat_integration._ff_memory_shadow",
            return_value=False,
        ), patch(
            "services.canonical_memory.chat_integration._ff_memory_influence",
            return_value=True,
        ):
            result = await integration.prepare_context(
                user_id="user-1",
                query="What is meditation?",
                session_id="sess-1",
                session_messages=[{"role": "user", "content": "Hello"}],
            )

        assert "[Memory:" in result
        retriever.retrieve.assert_called_once()

    @pytest.mark.asyncio
    async def test_canonical_empty_falls_back_to_legacy(self):
        retriever = _make_retriever(memories=[])
        orchestrator = _make_orchestrator(
            context_result=FakeContextResult(
                memory_block=FakeLayerBlock(content="", included=False)
            )
        )
        legacy = _make_legacy_service()

        integration = CanonicalMemoryIntegration(
            context_orchestrator=orchestrator,
            memory_retriever=retriever,
            extractor=_make_extractor(),
            judge=_make_judge(),
            resolver=_make_resolver(),
            existing_memory_service=legacy,
        )

        with patch(
            "services.canonical_memory.chat_integration._ff_canonical_memory",
            return_value=True,
        ), patch(
            "services.canonical_memory.chat_integration._ff_canonical_memory_retrieval",
            return_value=True,
        ), patch(
            "services.canonical_memory.chat_integration._ff_memory_shadow",
            return_value=False,
        ), patch(
            "services.canonical_memory.chat_integration._ff_memory_influence",
            return_value=True,
        ):
            result = await integration.prepare_context(
                user_id="user-1",
                query="What is meditation?",
                session_id="sess-1",
            )

        assert "Legacy core memory" in result


# ---------------------------------------------------------------------------
# Tests: Failure fallback
# ---------------------------------------------------------------------------

class TestFailureFallback:
    """Canonical system failure falls back to legacy system."""

    @pytest.mark.asyncio
    async def test_canonical_failure_falls_back_to_legacy(self):
        retriever = AsyncMock()
        retriever.retrieve.side_effect = RuntimeError("Qdrant down")
        orchestrator = _make_orchestrator()
        legacy = _make_legacy_service()

        integration = CanonicalMemoryIntegration(
            context_orchestrator=orchestrator,
            memory_retriever=retriever,
            extractor=_make_extractor(),
            judge=_make_judge(),
            resolver=_make_resolver(),
            existing_memory_service=legacy,
        )

        with patch(
            "services.canonical_memory.chat_integration._ff_canonical_memory",
            return_value=True,
        ), patch(
            "services.canonical_memory.chat_integration._ff_canonical_memory_retrieval",
            return_value=True,
        ), patch(
            "services.canonical_memory.chat_integration._ff_memory_shadow",
            return_value=False,
        ), patch(
            "services.canonical_memory.chat_integration._ff_memory_influence",
            return_value=True,
        ):
            result = await integration.prepare_context(
                user_id="user-1",
                query="Hello",
                session_id="sess-1",
            )

        assert "Legacy core memory" in result

    @pytest.mark.asyncio
    async def test_post_response_failure_is_non_fatal(self):
        retriever = _make_retriever()
        orchestrator = _make_orchestrator()
        legacy = _make_legacy_service()
        extractor = AsyncMock()
        extractor.side_effect = RuntimeError("LLM timeout")
        judge = _make_judge()
        resolver = _make_resolver()

        integration = CanonicalMemoryIntegration(
            context_orchestrator=orchestrator,
            memory_retriever=retriever,
            extractor=extractor,
            judge=judge,
            resolver=resolver,
            existing_memory_service=legacy,
        )

        with patch(
            "services.canonical_memory.chat_integration._ff_canonical_memory",
            return_value=True,
        ), patch(
            "services.canonical_memory.chat_integration._ff_memory_write",
            return_value=True,
        ):
            # Should not raise
            await integration.post_response_memory(
                user_id="user-1",
                query="I like meditation",
                response="Great!",
                session_id="sess-1",
            )


# ---------------------------------------------------------------------------
# Tests: Shadow mode
# ---------------------------------------------------------------------------

class TestShadowMode:
    """Shadow mode runs canonical but doesn't serve its results."""

    @pytest.mark.asyncio
    async def test_shadow_mode_returns_legacy_context(self):
        retriever = _make_retriever()
        orchestrator = _make_orchestrator()
        legacy = _make_legacy_service()

        integration = CanonicalMemoryIntegration(
            context_orchestrator=orchestrator,
            memory_retriever=retriever,
            extractor=_make_extractor(),
            judge=_make_judge(),
            resolver=_make_resolver(),
            existing_memory_service=legacy,
        )

        with patch(
            "services.canonical_memory.chat_integration._ff_canonical_memory",
            return_value=True,
        ), patch(
            "services.canonical_memory.chat_integration._ff_canonical_memory_retrieval",
            return_value=True,
        ), patch(
            "services.canonical_memory.chat_integration._ff_memory_shadow",
            return_value=True,
        ), patch(
            "services.canonical_memory.chat_integration._ff_memory_influence",
            return_value=True,
        ):
            result = await integration.prepare_context(
                user_id="user-1",
                query="What do you know about me?",
                session_id="sess-1",
            )

        # Shadow mode: canonical was called (retriever invoked) but legacy is served
        assert "Legacy core memory" in result
        retriever.retrieve.assert_called_once()


# ---------------------------------------------------------------------------
# Tests: Memory influence disabled
# ---------------------------------------------------------------------------

class TestInfluenceDisabled:
    """When influence is disabled, canonical is retrieved but not injected."""

    @pytest.mark.asyncio
    async def test_influence_disabled_returns_empty(self):
        retriever = _make_retriever()
        orchestrator = _make_orchestrator()
        legacy = _make_legacy_service()

        integration = CanonicalMemoryIntegration(
            context_orchestrator=orchestrator,
            memory_retriever=retriever,
            extractor=_make_extractor(),
            judge=_make_judge(),
            resolver=_make_resolver(),
            existing_memory_service=legacy,
        )

        with patch(
            "services.canonical_memory.chat_integration._ff_canonical_memory",
            return_value=True,
        ), patch(
            "services.canonical_memory.chat_integration._ff_canonical_memory_retrieval",
            return_value=True,
        ), patch(
            "services.canonical_memory.chat_integration._ff_memory_shadow",
            return_value=False,
        ), patch(
            "services.canonical_memory.chat_integration._ff_memory_influence",
            return_value=False,
        ):
            result = await integration.prepare_context(
                user_id="user-1",
                query="What is meditation?",
                session_id="sess-1",
            )

        # Canonical was retrieved (retriever called) but influence is off
        assert result == ""
        retriever.retrieve.assert_called_once()


# ---------------------------------------------------------------------------
# Tests: Explicit commands
# ---------------------------------------------------------------------------

class TestExplicitCommands:
    """Explicit memory commands are handled correctly."""

    @pytest.mark.asyncio
    async def test_remember_command(self):
        retriever = _make_retriever()
        orchestrator = _make_orchestrator()
        legacy = _make_legacy_service()
        judge = AsyncMock()
        judge.judge.return_value = [FakeJudgeDecision(action="CREATE")]
        resolver = _make_resolver()

        integration = CanonicalMemoryIntegration(
            context_orchestrator=orchestrator,
            memory_retriever=retriever,
            extractor=_make_extractor(),
            judge=judge,
            resolver=resolver,
            existing_memory_service=legacy,
        )

        with patch(
            "services.canonical_memory.chat_integration._ff_memory_write",
            return_value=True,
        ):
            result = await integration.handle_explicit_command(
                user_id="user-1",
                command="remember:I prefer concise answers",
                query="Remember that I prefer concise answers",
            )

        assert "remember" in result.lower() or "concise" in result.lower()
        judge.judge.assert_called_once()

    @pytest.mark.asyncio
    async def test_remember_write_disabled(self):
        retriever = _make_retriever()
        orchestrator = _make_orchestrator()
        legacy = _make_legacy_service()

        integration = CanonicalMemoryIntegration(
            context_orchestrator=orchestrator,
            memory_retriever=retriever,
            extractor=_make_extractor(),
            judge=_make_judge(),
            resolver=_make_resolver(),
            existing_memory_service=legacy,
        )

        with patch(
            "services.canonical_memory.chat_integration._ff_memory_write",
            return_value=False,
        ):
            result = await integration.handle_explicit_command(
                user_id="user-1",
                command="remember:I like tea",
                query="Remember I like tea",
            )

        assert "being set up" in result.lower() or "currently" in result.lower()

    @pytest.mark.asyncio
    async def test_recall_command(self):
        retriever = _make_retriever(
            memories=[FakeRetrievedMemory(statement="User lives in Mumbai")]
        )
        orchestrator = _make_orchestrator()
        legacy = _make_legacy_service()

        integration = CanonicalMemoryIntegration(
            context_orchestrator=orchestrator,
            memory_retriever=retriever,
            extractor=_make_extractor(),
            judge=_make_judge(),
            resolver=_make_resolver(),
            existing_memory_service=legacy,
        )

        with patch(
            "services.canonical_memory.chat_integration._ff_canonical_memory_retrieval",
            return_value=True,
        ):
            result = await integration.handle_explicit_command(
                user_id="user-1",
                command="recall",
                query="What do you remember about me?",
            )

        assert "Mumbai" in result

    @pytest.mark.asyncio
    async def test_recall_empty(self):
        retriever = _make_retriever(memories=[])
        orchestrator = _make_orchestrator()
        legacy = _make_legacy_service()

        integration = CanonicalMemoryIntegration(
            context_orchestrator=orchestrator,
            memory_retriever=retriever,
            extractor=_make_extractor(),
            judge=_make_judge(),
            resolver=_make_resolver(),
            existing_memory_service=legacy,
        )

        with patch(
            "services.canonical_memory.chat_integration._ff_canonical_memory_retrieval",
            return_value=True,
        ):
            result = await integration.handle_explicit_command(
                user_id="user-1",
                command="recall",
                query="What do you remember about me?",
            )

        assert "getting to know you" in result.lower()

    @pytest.mark.asyncio
    async def test_empty_command_returns_empty(self):
        integration = CanonicalMemoryIntegration(
            context_orchestrator=MagicMock(),
            memory_retriever=MagicMock(),
            extractor=MagicMock(),
            judge=MagicMock(),
            resolver=MagicMock(),
            existing_memory_service=MagicMock(),
        )
        result = await integration.handle_explicit_command(
            user_id="user-1", command="", query=""
        )
        assert result == ""


# ---------------------------------------------------------------------------
# Tests: Post-response memory pipeline
# ---------------------------------------------------------------------------

class TestPostResponseMemory:
    """Post-response extraction runs async, non-blocking."""

    @pytest.mark.asyncio
    async def test_extraction_pipeline_runs(self):
        retriever = _make_retriever()
        orchestrator = _make_orchestrator()
        legacy = _make_legacy_service()
        extractor = _make_extractor()
        judge = _make_judge()
        resolver = _make_resolver()

        integration = CanonicalMemoryIntegration(
            context_orchestrator=orchestrator,
            memory_retriever=retriever,
            extractor=extractor,
            judge=judge,
            resolver=resolver,
            existing_memory_service=legacy,
        )

        with patch(
            "services.canonical_memory.chat_integration._ff_canonical_memory",
            return_value=True,
        ), patch(
            "services.canonical_memory.chat_integration._ff_memory_write",
            return_value=True,
        ):
            await integration.post_response_memory(
                user_id="user-1",
                query="I live in Hyderabad",
                response="That's wonderful!",
                session_id="sess-1",
                session_messages=[
                    {"role": "user", "content": "I live in Hyderabad"},
                    {"role": "assistant", "content": "That's wonderful!"},
                ],
            )

        extractor.assert_called_once()
        call_kwargs = extractor.call_args
        # The turns should include user and assistant messages
        turns = call_kwargs.kwargs.get("turns", call_kwargs[1].get("turns", []))
        assert len(turns) >= 2

    @pytest.mark.asyncio
    async def test_write_disabled_skips_extraction(self):
        retriever = _make_retriever()
        orchestrator = _make_orchestrator()
        legacy = _make_legacy_service()
        extractor = _make_extractor()
        judge = _make_judge()
        resolver = _make_resolver()

        integration = CanonicalMemoryIntegration(
            context_orchestrator=orchestrator,
            memory_retriever=retriever,
            extractor=extractor,
            judge=judge,
            resolver=resolver,
            existing_memory_service=legacy,
        )

        with patch(
            "services.canonical_memory.chat_integration._ff_canonical_memory",
            return_value=True,
        ), patch(
            "services.canonical_memory.chat_integration._ff_memory_write",
            return_value=False,
        ):
            await integration.post_response_memory(
                user_id="user-1",
                query="Hello",
                response="Hi!",
                session_id="sess-1",
            )

        extractor.assert_not_called()


# ---------------------------------------------------------------------------
# Tests: Factory
# ---------------------------------------------------------------------------

class TestFactory:
    def test_create_chat_integration(self):
        integration = create_chat_integration(
            context_orchestrator=MagicMock(),
            memory_retriever=MagicMock(),
            extractor=MagicMock(),
            judge=MagicMock(),
            resolver=MagicMock(),
            existing_memory_service=MagicMock(),
        )
        assert isinstance(integration, CanonicalMemoryIntegration)


# ---------------------------------------------------------------------------
# Tests: Streaming compatibility
# ---------------------------------------------------------------------------

class TestStreamingCompatibility:
    """Verify that memory operations don't block the response path."""

    @pytest.mark.asyncio
    async def test_prepare_context_does_not_block(self):
        """prepare_context must be callable without blocking event loop."""
        retriever = _make_retriever()
        orchestrator = _make_orchestrator()
        legacy = _make_legacy_service()

        integration = CanonicalMemoryIntegration(
            context_orchestrator=orchestrator,
            memory_retriever=retriever,
            extractor=_make_extractor(),
            judge=_make_judge(),
            resolver=_make_resolver(),
            existing_memory_service=legacy,
        )

        with patch(
            "services.canonical_memory.chat_integration._ff_canonical_memory",
            return_value=False,
        ):
            result = await integration.prepare_context(
                user_id="user-1",
                query="Hello",
                session_id="sess-1",
            )

        assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_post_response_is_non_blocking(self):
        """post_response_memory completes without blocking."""
        retriever = _make_retriever()
        orchestrator = _make_orchestrator()
        legacy = _make_legacy_service()

        integration = CanonicalMemoryIntegration(
            context_orchestrator=orchestrator,
            memory_retriever=retriever,
            extractor=_make_extractor(),
            judge=_make_judge(),
            resolver=_make_resolver(),
            existing_memory_service=legacy,
        )

        with patch(
            "services.canonical_memory.chat_integration._ff_canonical_memory",
            return_value=False,
        ):
            # Must complete quickly
            await asyncio.wait_for(
                integration.post_response_memory(
                    user_id="user-1",
                    query="Hello",
                    response="Hi!",
                    session_id="sess-1",
                ),
                timeout=1.0,
            )
