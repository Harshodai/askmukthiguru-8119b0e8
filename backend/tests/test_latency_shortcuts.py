from __future__ import annotations

import time
from unittest.mock import MagicMock

import pytest

from app.pipeline.stages import BoundedComparisonShortCircuitStage
from app.pipeline.stages.context import PipelineContext


@pytest.mark.asyncio
async def test_bounded_comparison_short_circuits_english_without_model() -> None:
    ctx = PipelineContext(
        container=MagicMock(),
        coordinator=MagicMock(),
        request=MagicMock(),
        user_msg="What is the difference between meditation and contemplation?",
        preferred_lang="en",
        trace_id="trace-test",
        start_time=time.time(),
        state={
            "user_msg_en": "What is the difference between meditation and contemplation?"
        },
    )

    result = await BoundedComparisonShortCircuitStage().run(ctx)

    assert result is not None
    assert result.route_decision == "bounded_comparison_short_circuit"
    assert result.intent == "COMPARATIVE"
    assert result.model_used is None
    assert result.citations == []
    assert result.verification["method"] == "limited_comparison_fallback"
    assert len(result.final_answer) > 200


@pytest.mark.asyncio
async def test_bounded_comparison_does_not_bypass_indic_translation() -> None:
    ctx = PipelineContext(
        container=MagicMock(),
        coordinator=MagicMock(),
        request=MagicMock(),
        user_msg="What is the difference between meditation and contemplation?",
        preferred_lang="hi",
        trace_id="trace-test",
        start_time=time.time(),
        state={
            "user_msg_en": "What is the difference between meditation and contemplation?"
        },
    )

    result = await BoundedComparisonShortCircuitStage().run(ctx)

    assert result is None


def test_telugu_refusal_marker_is_retried_when_evidence_exists() -> None:
    from rag.nodes.generation import _evidence_refusal_action

    action, answer = _evidence_refusal_action(
        "నేను ఈ అంశంపై నిర్దిష్ట బోధనలను కనుగొనలేకపోయాను.",
        [{"text": "శాంతి అనేది అంతర్గత ప్రశాంతత యొక్క స్థితి."}],
    )

    assert action == "retry"
    assert answer.startswith("నేను")


@pytest.mark.asyncio
async def test_query_translation_cache_suppresses_repeat_provider_call() -> None:
    from app.orchestrator_utils import _TRANSLATION_CACHE, _translate_cached

    class FakeTranslation:
        def __init__(self) -> None:
            self.calls = 0

        async def translate_text(self, **kwargs):
            self.calls += 1
            return "peace"

    _TRANSLATION_CACHE.clear()
    service = FakeTranslation()
    first = await _translate_cached(
        service,
        text="शांति क्या है?",
        source_lang="hi",
        target_lang="en",
        timeout=1.0,
    )
    second = await _translate_cached(
        service,
        text="शांति क्या है?",
        source_lang="hi",
        target_lang="en",
        timeout=1.0,
    )

    assert first == second == "peace"
    assert service.calls == 1
    _TRANSLATION_CACHE.clear()


def test_translation_cache_excludes_personal_or_url_like_text() -> None:
    from app.orchestrator_utils import _translation_cacheable

    assert not _translation_cacheable("contact me at seeker@example.com")
    assert not _translation_cacheable("https://example.com/private-note")
    assert not _translation_cacheable("call 9876543210 for details")
    assert _translation_cacheable("शांति क्या है?")
