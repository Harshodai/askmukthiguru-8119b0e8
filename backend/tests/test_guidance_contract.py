"""Regressions for the typed, safety-aware guidance presentation contract."""
from __future__ import annotations

import json
from types import SimpleNamespace

from app.coalescer import RedisCoalescer
from app.pipeline.result import ActionStep, GuidancePlan, PipelineResult, TeachingAttribution
from app.pipeline.stages.glue_stages import _guidance_plan


def context(response_type: str = ""):
    return SimpleNamespace(
        assessment=SimpleNamespace(recommended_response_type=response_type),
        preferred_lang="hi",
    )


def test_guidance_plan_uses_only_structured_practice_and_follow_up_fields():
    plan = _guidance_plan(
        context(),
        {
            "daily_practice_card": {
                "title": "Notice one breath",
                "practice": "Pause gently and notice one complete breath.",
            },
            "follow_up_suggestions": ["What changes when you pause before reacting?"],
        },
        [{"source_url": "https://example.org/approved-teaching"}],
    )

    assert plan is not None
    assert plan.language == "hi"
    assert plan.action_step is not None
    assert plan.action_step.title == "Notice one breath"
    assert plan.action_step.instruction == "Pause gently and notice one complete breath."
    assert plan.reflection_prompt == "What changes when you pause before reacting?"
    assert plan.attribution.source_backed is True
    assert plan.attribution.teacher_name is None
    assert "I am" not in plan.attribution.label


def test_crisis_or_severe_response_never_gets_a_guidance_plan():
    assert _guidance_plan(context("crisis"), {}, []) is None
    assert _guidance_plan(context("severe"), {}, []) is None


def test_coalescer_round_trip_preserves_nested_guidance_types():
    guidance = GuidancePlan(
        response_mode="balanced_guidance",
        language="en",
        attribution=TeachingAttribution(
            label="Guidance inspired by retrieved teachings",
            source_backed=True,
        ),
        action_step=ActionStep(
            title="Pause",
            instruction="Take one gentle breath.",
        ),
        reflection_prompt="What is present now?",
    )
    result = PipelineResult(final_answer="Namaste", guidance_plan=guidance)

    assert result.with_latency(42).guidance_plan == guidance
    assert result.to_chat_response()["guidance_plan"]["action_step"]["title"] == "Pause"
    payload = json.loads(RedisCoalescer._serialize_result(result))
    round_trip = RedisCoalescer._deserialize_result(payload)

    assert isinstance(round_trip.guidance_plan, GuidancePlan)
    assert isinstance(round_trip.guidance_plan.attribution, TeachingAttribution)
    assert isinstance(round_trip.guidance_plan.action_step, ActionStep)
    assert round_trip.guidance_plan == guidance


def test_stream_done_metadata_serializes_guidance_and_evidence():
    from app.orchestrator import _stream_done_metadata
    from app.pipeline.result import AnswerEvidence

    result = PipelineResult(
        final_answer="Namaste",
        answer_evidence=AnswerEvidence(
            corpus_id="askmukthiguru",
            release_version=2,
            model_policy_id="gemini-flash-budget-v1",
            evidence_support_label="Teaching-supported",
            source_count=1,
            top_source_score=0.91,
        ),
        guidance_plan=GuidancePlan(
            response_mode="balanced_guidance",
            language="en",
            attribution=TeachingAttribution(
                label="Guidance inspired by retrieved teachings",
                source_backed=True,
            ),
        ),
    )

    metadata = _stream_done_metadata(result)
    assert metadata["answer_evidence"]["release_version"] == 2
    assert metadata["guidance_plan"]["attribution"]["source_backed"] is True
