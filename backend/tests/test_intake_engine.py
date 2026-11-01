"""Unit test suite for Engine 1: Fast Intake, Safety Kernel & Unified Personalization."""

from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.intake import (
    FastSafetyKernel,
    FastShortCircuitCascade,
    ShortCircuitResult,
    UnifiedPersonalizationCoordinator,
    UnifiedUserPersonalizationContext,
)


# ===========================================================================
# 1. FastSafetyKernel Tests
# ===========================================================================


def test_safety_kernel_acute_crisis_detection():
    """Verify FastSafetyKernel catches acute self-harm needles within 2ms."""
    kernel = FastSafetyKernel()

    acute_queries = [
        "I want to end it all",
        "how do i stop wanting to die",
        "suicide is my only option",
        "I want to kill myself today",
        "ways to end it all",
        "is life worth living",
        "I'm thinking about cutting myself",
        "I want to overdose and sleep forever",
        "how to commit suicide safely",
        "planning to jump off a bridge tonight",
    ]

    for query in acute_queries:
        t0 = time.perf_counter()
        verdict = kernel.evaluate(query)
        latency_ms = (time.perf_counter() - t0) * 1000

        assert latency_ms < 2.0, f"Latency exceeded 2ms: {latency_ms:.3f}ms for query: {query}"
        assert verdict.is_crisis is True, f"Failed to detect crisis in: {query}"
        assert verdict.matched_pattern is not None
        assert verdict.helpline_response is not None
        assert "Tele-MANAS" in verdict.helpline_response
        assert "14416" in verdict.helpline_response
        assert "Vandrevala Foundation" in verdict.helpline_response
        assert "+91 9999 666 555" in verdict.helpline_response


def test_safety_kernel_obfuscated_crisis_detection():
    """Verify FastSafetyKernel detects spaced or punctuated obfuscated crisis phrases."""
    kernel = FastSafetyKernel()

    obfuscated_queries = [
        "s u i c i d e",
        "s-u-i-c-i-d-e",
        "k i l l   m y s e l f",
        "w-a-n-t-t-o-d-i-e",
        "e.n.d.i.t.a.l.l",
    ]

    for query in obfuscated_queries:
        t0 = time.perf_counter()
        verdict = kernel.evaluate(query)
        latency_ms = (time.perf_counter() - t0) * 1000

        assert latency_ms < 2.0, f"Obfuscated detection exceeded 2ms: {latency_ms:.3f}ms"
        assert verdict.is_crisis is True, f"Failed to detect obfuscated query: {query}"
        assert verdict.reason == "obfuscated_self_harm_preemption"
        assert verdict.helpline_response is not None


def test_safety_kernel_clean_queries_pass():
    """Verify normal doctrinal inquiries are not falsely flagged as crisis."""
    kernel = FastSafetyKernel()

    clean_queries = [
        "tell me about beautiful state",
        "how to meditate with soul sync",
        "what are the four sacred secrets?",
        "how do I deal with anger and anxiety at work?",
        "good morning guruji, what is oneness?",
        "can you explain the concept of living in presence?",
        "what is the difference between meditation and contemplation?",
    ]

    for query in clean_queries:
        t0 = time.perf_counter()
        verdict = kernel.evaluate(query)
        latency_ms = (time.perf_counter() - t0) * 1000

        assert latency_ms < 2.0
        assert verdict.is_crisis is False, f"False positive crisis on clean query: {query}"
        assert verdict.matched_pattern is None
        assert verdict.helpline_response is None


def test_safety_kernel_empty_and_edge_inputs():
    """Verify empty, whitespace, and non-string inputs are handled safely."""
    kernel = FastSafetyKernel()

    assert kernel.evaluate("").is_crisis is False
    assert kernel.evaluate("   ").is_crisis is False
    assert kernel.evaluate(None).is_crisis is False  # type: ignore


# ===========================================================================
# 2. FastShortCircuitCascade Tests
# ===========================================================================


def test_short_circuit_tier1_exact_cache():
    """Verify Tier 1 exact cache returns stored responses in <3ms."""
    cascade = FastShortCircuitCascade()

    # Pre-populate in-memory exact cache
    cascade.set_cache_entry("what is meditation?", "Meditation is quiet awareness.")

    t0 = time.perf_counter()
    result = cascade.evaluate("What is meditation? ")
    latency_ms = (time.perf_counter() - t0) * 1000

    assert latency_ms < 3.0
    assert result is not None
    assert result.tier == "exact_cache"
    assert result.response == "Meditation is quiet awareness."
    assert result.metadata["source"] == "memory"


def test_short_circuit_tier1_redis_mock():
    """Verify Tier 1 exact cache works with Redis client."""
    cascade = FastShortCircuitCascade()

    mock_redis = MagicMock()
    mock_redis.get.return_value = b"Cached answer from Redis"

    t0 = time.perf_counter()
    result = cascade.evaluate("How to find peace?", redis_client=mock_redis)
    latency_ms = (time.perf_counter() - t0) * 1000

    assert latency_ms < 3.0
    assert result is not None
    assert result.tier == "exact_cache"
    assert result.response == "Cached answer from Redis"
    assert result.metadata["source"] == "redis"


def test_short_circuit_tier2_spiritual_greetings():
    """Verify Tier 2 catches greetings and conversational openers in <1ms."""
    cascade = FastShortCircuitCascade()

    greetings = [
        "Namaste",
        "Namaste Guruji",
        "Pranam Swamiji",
        "Hari Om",
        "Hari om ji",
        "Hello",
        "Good morning",
        "Good evening guruji",
        "Namaste, good morning!",
        "How are you doing?",
        "What's up",
    ]

    for g in greetings:
        t0 = time.perf_counter()
        result = cascade.evaluate(g)
        latency_ms = (time.perf_counter() - t0) * 1000

        assert latency_ms < 2.0, f"Greeting latency exceeded 2ms: {latency_ms:.3f}ms for: {g}"
        assert result is not None, f"Failed to short-circuit greeting: {g}"
        assert result.tier == "spiritual_greeting"
        assert "AskMukthiGuru" in result.response
        assert "Beautiful State" in result.response


def test_short_circuit_tier3_system_capabilities():
    """Verify Tier 3 catches help and capability inquiries in <2ms."""
    cascade = FastShortCircuitCascade()

    help_queries = [
        "What can you do?",
        "help",
        "Who are you?",
        "What is AskMukthiGuru?",
        "What are your capabilities",
        "Tell me about yourself",
    ]

    for q in help_queries:
        t0 = time.perf_counter()
        result = cascade.evaluate(q)
        latency_ms = (time.perf_counter() - t0) * 1000

        assert latency_ms < 3.0
        assert result is not None, f"Failed to short-circuit help query: {q}"
        assert result.tier == "system_capabilities"
        assert "Spiritual Teachings" in result.response
        assert "Soul Sync" in result.response


def test_short_circuit_tier4_canonical_glossary():
    """Verify Tier 4 provides curated definitions for core Ekam concepts in <5ms."""
    cascade = FastShortCircuitCascade()

    glossary_queries = [
        ("what is ekam?", "Ekam"),
        ("define beautiful state", "Beautiful State"),
        ("meaning of soul sync", "Soul Sync"),
        ("tell me about four sacred secrets", "The Four Sacred Secrets"),
        ("what are the 4 sacred secrets", "The Four Sacred Secrets"),
        ("serene mind", "Serene Mind"),
        ("limitless field", "Limitless Field"),
    ]

    for query, expected_snippet in glossary_queries:
        t0 = time.perf_counter()
        result = cascade.evaluate(query)
        latency_ms = (time.perf_counter() - t0) * 1000

        assert latency_ms < 5.0, f"Glossary latency exceeded 5ms: {latency_ms:.3f}ms for: {query}"
        assert result is not None, f"Failed to match glossary query: {query}"
        assert result.tier == "doctrinal_glossary"
        assert expected_snippet.lower() in result.response.lower()


def test_short_circuit_tier5_fallthrough_to_retrieval():
    """Verify complex doctrinal and personal inquiries fall through (return None)."""
    cascade = FastShortCircuitCascade()

    retrieval_queries = [
        "How do I deal with fear of the future?",
        "Why do I get irritated with my spouse during stressful times?",
        "What did Sri Krishnaji say about breaking free from mental addiction?",
        "Teach me a step by step technique to stop worrying about finances",
        "How does karma relate to consciousness in Ekam philosophy?",
    ]

    for q in retrieval_queries:
        result = cascade.evaluate(q)
        assert result is None, (
            f"Query should fall through to retrieval but got short-circuited: {q}"
        )


# ===========================================================================
# 3. UnifiedPersonalizationCoordinator Tests
# ===========================================================================


@pytest.mark.asyncio
async def test_personalization_anonymous_short_circuit():
    """Verify anonymous seekers return default context immediately in <1ms."""
    coordinator = UnifiedPersonalizationCoordinator()

    t0 = time.perf_counter()
    ctx = await coordinator.hydrate_context(user_id="anonymous")
    latency_ms = (time.perf_counter() - t0) * 1000

    assert latency_ms < 2.0
    assert ctx.user_id == "anonymous"
    assert ctx.guru_tone == "gentle"
    assert ctx.familiarity_level == "seeker"
    assert ctx.preferred_language == "en"
    assert ctx.sadhana_streak_days == 0
    assert ctx.last_practice is None
    assert ctx.active_memories == []
    assert ctx.is_mode_b_unlocked is False


@pytest.mark.asyncio
async def test_personalization_authenticated_hydration():
    """Verify authenticated user context hydrates parallel facets within SLA."""
    coordinator = UnifiedPersonalizationCoordinator()

    # Mock container components
    mock_container = MagicMock()

    # 1. Profile mock
    mock_profile = MagicMock()
    mock_profile.guru_tone = "poetic"
    mock_profile.spiritual_level = "practitioner"
    mock_profile.preferred_language = "hi"
    mock_container.user_profile.get_or_create_profile = AsyncMock(return_value=mock_profile)

    # 2. Retention/Streak mock
    mock_streak = MagicMock()
    mock_streak.current = 14
    mock_streak.last_practice = "soul_sync"
    mock_container.retention_service._load_state = AsyncMock(return_value=mock_streak)

    # 3. Second brain / PKG mock
    mock_vault = MagicMock()
    mock_item1 = MagicMock(text="User meditates every morning at 6 AM.")
    mock_item2 = MagicMock(text="User is preparing for Ekam Tapas retreat.")
    mock_container.second_brain.unlock = AsyncMock(return_value=mock_vault)
    mock_container.second_brain.personal_context = AsyncMock(return_value=[mock_item1, mock_item2])

    # 4. DPDP consent receipt mock
    mock_container.memory_outbox.active_consent = AsyncMock(return_value={"scope": "EXTRACTION"})

    t0 = time.perf_counter()
    ctx = await coordinator.hydrate_context(
        user_id="user_12345",
        x_brain_unlock="secret_passphrase",
        container=mock_container,
        timeout_ms=15,
    )
    latency_ms = (time.perf_counter() - t0) * 1000

    assert latency_ms < 15.0
    assert ctx.user_id == "user_12345"
    assert ctx.guru_tone == "poetic"
    assert ctx.familiarity_level == "practitioner"
    assert ctx.preferred_language == "hi"
    assert ctx.sadhana_streak_days == 14
    assert ctx.last_practice == "soul_sync"
    assert len(ctx.active_memories) == 2
    assert "retreat" in ctx.active_memories[1]
    assert ctx.is_mode_b_unlocked is True


@pytest.mark.asyncio
async def test_personalization_dpdp_consent_revocation():
    """Verify that when DPDP consent is missing, personal memories are withheld."""
    coordinator = UnifiedPersonalizationCoordinator()

    mock_container = MagicMock()
    mock_container.user_profile.get_or_create_profile = AsyncMock(return_value=None)
    mock_container.retention_service._load_state = AsyncMock(return_value=None)

    # DPDP consent returns None (consent revoked or missing)
    mock_container.memory_outbox.active_consent = AsyncMock(return_value=None)

    # Even if second_brain has items, they must NOT be returned without active consent
    mock_vault = MagicMock()
    mock_item = MagicMock(text="Sensitive reflection")
    mock_container.second_brain.unlock = AsyncMock(return_value=mock_vault)
    mock_container.second_brain.personal_context = AsyncMock(return_value=[mock_item])

    ctx = await coordinator.hydrate_context(
        user_id="user_unconsented",
        x_brain_unlock="passphrase",
        container=mock_container,
        timeout_ms=15,
    )

    assert ctx.active_memories == []


@pytest.mark.asyncio
async def test_personalization_timeout_graceful_degradation():
    """Verify coordinator degrades gracefully within timeout deadline if services hang."""
    coordinator = UnifiedPersonalizationCoordinator()

    mock_container = MagicMock()

    # Simulate hanging service
    async def _hanging_profile(*args, **kwargs):
        await asyncio.sleep(0.1)  # 100ms sleep, well beyond 15ms timeout
        return None

    mock_container.user_profile.get_or_create_profile = _hanging_profile
    mock_container.retention_service._load_state = AsyncMock(return_value=None)
    mock_container.second_brain = None

    t0 = time.perf_counter()
    ctx = await coordinator.hydrate_context(
        user_id="user_slow",
        container=mock_container,
        timeout_ms=15,
    )
    latency_ms = (time.perf_counter() - t0) * 1000

    # Must terminate near the timeout limit and return valid default context
    assert latency_ms < 30.0  # Safe margin for test runner overhead
    assert ctx.user_id == "user_slow"
    assert ctx.guru_tone == "gentle"
    assert ctx.familiarity_level == "seeker"


def test_kernel_catches_inflected_phrasings_and_skips_glued_prose():
    from app.intake.safety_kernel import get_safety_kernel

    kernel = get_safety_kernel()
    for text in (
        "I keep thinking about killing myself",
        "I don't want to live anymore",
        "no reason to live",
    ):
        assert kernel.evaluate(text).is_crisis, text
    for text in ("please send it all to me", "I want to diet this month", "take my lifetime pass"):
        assert not kernel.evaluate(text).is_crisis, text
    assert kernel.evaluate("s u i c i d e").is_crisis  # spaced-out obfuscation still caught
    assert get_safety_kernel() is kernel


def test_consent_store_missing_means_no_memories():
    import asyncio
    from types import SimpleNamespace

    from app.intake.personalization_coordinator import UnifiedPersonalizationCoordinator

    memories, unlocked = asyncio.run(
        UnifiedPersonalizationCoordinator()._fetch_memories("u1", None, SimpleNamespace())
    )
    assert (memories, unlocked) == ([], False)
