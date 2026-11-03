import asyncio
from unittest.mock import AsyncMock


def test_openrouter_distress_provider_failure_is_not_intent_fallback():
    from services.openrouter_service import OpenRouterService

    service = OpenRouterService.__new__(OpenRouterService)
    service._generate_fast = AsyncMock(side_effect=RuntimeError("provider unavailable"))
    service.classify_intent = AsyncMock(side_effect=AssertionError("intent fallback must not run"))

    result = asyncio.run(service.classify_distress_structured("What is the beautiful state?"))

    assert result["is_distress"] is False
    assert result["confidence"] == 0.0
    assert "deterministic safety checks" in result["reason"]
    service.classify_intent.assert_not_awaited()


def test_circuit_open_provider_failure_is_not_a_safety_block():
    from app.pipeline.pipeline_coordinator import PipelineCoordinator

    coordinator = PipelineCoordinator.__new__(PipelineCoordinator)
    result = coordinator._circuit_open_result(False, 0.0)

    assert result.intent == "ERROR"
    assert result.route_decision == "error"
    assert result.blocked is False
    assert result.block_reason is None


def test_input_guardrails_precede_circuit_breaker():
    from app.pipeline.stages.pipeline_builder import build_default_pipeline

    names = [stage.name for stage in build_default_pipeline()]

    assert names.index("input_guardrails") < names.index("circuit_breaker")


def test_provider_error_is_exposed_as_system_error_grounding():
    from types import SimpleNamespace

    from app.grounding import grounding_state_for

    assert grounding_state_for(SimpleNamespace(intent="ERROR", blocked=False)) == "system_error"
    assert grounding_state_for(SimpleNamespace(intent="TIMEOUT", blocked=False)) == "system_error"


def test_failed_distress_check_says_indeterminate_not_just_not_distress():
    from services.openrouter_service import OpenRouterService

    service = OpenRouterService.__new__(OpenRouterService)
    service._generate_fast = AsyncMock(side_effect=RuntimeError("spend limit reached"))

    result = asyncio.run(service.classify_distress_structured("I feel a bit low"))

    assert result["is_distress"] is False  # a failure is still never a distress verdict
    assert result["indeterminate"] is True


def test_engine_tags_the_turn_when_the_llm_stage_could_not_run(monkeypatch):
    from types import SimpleNamespace

    from services.serene_mind_engine import LLM_STAGE2_UNAVAILABLE_SIGNAL, SereneMindEngine

    engine = SereneMindEngine()
    llm = SimpleNamespace(
        classify_distress_structured=AsyncMock(
            return_value={"is_distress": False, "confidence": 0.0, "indeterminate": True}
        )
    )
    container = SimpleNamespace(ollama=llm)
    monkeypatch.setattr("app.dependencies.get_container", lambda: container)

    # A MILD regex hit is what lets the LLM stage run at all ("I feel stressed" is already
    # MODERATE and skips it).
    assessment = asyncio.run(engine.async_assess_distress("I feel tired"))

    assert llm.classify_distress_structured.await_count == 1
    assert LLM_STAGE2_UNAVAILABLE_SIGNAL in assessment.detected_signals
    assert int(assessment.level) < 2  # a failed check never raises the level


def test_a_working_llm_stage_does_not_tag_the_turn(monkeypatch):
    from types import SimpleNamespace

    from services.serene_mind_engine import LLM_STAGE2_UNAVAILABLE_SIGNAL, SereneMindEngine

    engine = SereneMindEngine()
    llm = SimpleNamespace(
        classify_distress_structured=AsyncMock(
            return_value={"is_distress": False, "confidence": 0.9, "reason": "fine"}
        )
    )
    monkeypatch.setattr("app.dependencies.get_container", lambda: SimpleNamespace(ollama=llm))
    assessment = asyncio.run(engine.async_assess_distress("I feel tired"))
    assert llm.classify_distress_structured.await_count == 1
    assert LLM_STAGE2_UNAVAILABLE_SIGNAL not in assessment.detected_signals
