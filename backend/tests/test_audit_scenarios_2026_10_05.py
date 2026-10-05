"""Manus ruthless audit 2026-10-05 — the four seeker scenarios.

Contract: docs/audits/manus-ruthless-audit-prompt-2026-10-05.md. The bridge
question-shape gate is tested in tests/test_first_person_bridge.py; this file
covers the rest of the change:

* B — a generated answer is labelled as the product's synthesis, and nothing
  else (fallbacks, abstentions, distress) is;
* C — a relationship-repair question always carries the safety boundary, even
  without the word "abuse", and nothing else does;
* D — retrieval term expansion pulls the teacher-grounded mechanism, and the
  Ekam geography keywords no longer hijack "the wisdom of Ekam".

Deterministic, no network, no models.
"""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.pipeline.stages.context import PipelineContext
from app.pipeline.stages.guardrail_stage import OutputGuardrailStage
from guardrails.lightweight_handler import (
    RELATIONSHIP_SAFETY_BOUNDARY,
    needs_relationship_safety_boundary,
)
from rag.nodes.generation import SYNTHESIS_LABEL, format_final_answer
from rag.nodes.keyword_injection import classify_doctrine_query, inject_doctrine_keywords
from rag.prompts import FALLBACK_RESPONSE
from rag.states import GraphState

SCENARIO_1 = (
    "What is the root cause of human suffering, and how do two states of being "
    "determine our daily life?"
)
SCENARIO_2 = "How can I heal from self-judgment and the inner wall of defense in my relationships?"
SCENARIO_3 = "Guide me in a meditation to calm the wandering mind and experience inner stillness."
SCENARIO_4 = (
    "How does the wisdom of Ekam view the difference between detachment and living "
    "in a beautiful state?"
)

_LONG_ANSWER = (
    "Meditation is the practice of resting attention on the breath. "
    "When the mind settles, stillness arises on its own. This is the "
    "first teaching of the sacred wisdom tradition."
)


def _state(**overrides) -> GraphState:
    base = dict(
        question="What is meditation?",
        answer=_LONG_ANSWER,
        citations=["https://doc.example/teaching"],
        relevant_docs=[{"title": "Doc One", "source_url": "https://doc.example/teaching"}],
        is_faithful=True,
        verification={"passed": True},
        confidence_score=8.0,
        intent="QUERY",
        query_tier="standard",
        retry_count=1,
    )
    base.update(overrides)
    return GraphState(**base)


# --------------------------------------------------------------------------- B


@pytest.mark.asyncio
async def test_generated_answer_carries_the_synthesis_label():
    result = await format_final_answer(_state())
    assert "Meditation is the practice" in result["final_answer"]
    assert result["final_answer"].rstrip().endswith(SYNTHESIS_LABEL)
    # The label is appended after verification; the verdict is unchanged.
    assert result["verification"]["passed"] is True
    assert result["verification"]["citations_verified"] is True


@pytest.mark.asyncio
async def test_fast_tier_generated_answer_carries_the_synthesis_label():
    state = _state(
        is_faithful=False,
        faithfulness_score=0.67,
        verification={"passed": False, "method": "lettuce_detect_fast_tier", "score": 0.67},
        query_tier="tier2_simple",
        retry_count=0,
    )
    result = await format_final_answer(state)
    assert result["final_answer"].count(SYNTHESIS_LABEL) == 1


@pytest.mark.asyncio
async def test_label_is_idempotent():
    result = await format_final_answer(_state(answer=f"{_LONG_ANSWER}\n\n{SYNTHESIS_LABEL}"))
    assert result["final_answer"].count(SYNTHESIS_LABEL) == 1


@pytest.mark.asyncio
async def test_fallback_is_not_labelled():
    state = _state(is_faithful=False, verification={"passed": False}, confidence_score=0.0)
    result = await format_final_answer(state)
    assert result["final_answer"] == FALLBACK_RESPONSE
    assert SYNTHESIS_LABEL not in result["final_answer"]


@pytest.mark.asyncio
async def test_abstention_is_not_labelled():
    state = _state(grounding_state="abstained", relevant_docs=[], citations=[])
    result = await format_final_answer(state)
    assert SYNTHESIS_LABEL not in result["final_answer"]


@pytest.mark.asyncio
@pytest.mark.parametrize("intent", ["DISTRESS", "CASUAL", "MEDITATION"])
async def test_non_teaching_intents_are_not_labelled(intent):
    result = await format_final_answer(_state(intent=intent))
    assert SYNTHESIS_LABEL not in result["final_answer"]


@pytest.mark.asyncio
async def test_custom_assistant_persona_is_not_labelled():
    result = await format_final_answer(_state(assistant_system_prompt="You are a poet."))
    assert SYNTHESIS_LABEL not in result["final_answer"]


def test_label_never_claims_teacher_voice():
    lowered = SYNTHESIS_LABEL.lower()
    assert "not a direct quote" in lowered
    assert "preethaji" not in lowered and "krishnaji" not in lowered


# --------------------------------------------------------------------------- C


@pytest.mark.parametrize(
    "question",
    [
        SCENARIO_2,
        "How do I repair my relationship with my father?",
        "Should I apologize to my wife after our fight?",
        "My friend and I keep having conflict, how do we heal?",
    ],
)
def test_relationship_repair_questions_need_the_boundary(question):
    assert needs_relationship_safety_boundary(question)


@pytest.mark.parametrize(
    "question",
    [
        SCENARIO_1,
        SCENARIO_3,
        SCENARIO_4,
        "What is the Beautiful State?",
        "How can I heal my anger?",
    ],
)
def test_other_questions_do_not_get_the_boundary(question):
    assert not needs_relationship_safety_boundary(question)


def test_boundary_covers_safety_contact_and_help():
    text = RELATIONSHIP_SAFETY_BOUNDARY.lower()
    assert "hurts, threatens or controls" in text
    assert "safety comes first" in text
    assert "do not owe them contact" in text and "apology" in text
    assert "counsellor" in text and "helpline" in text
    assert "abuse" not in text  # the trigger and the text never depend on the word


def _output_ctx(question: str, answer: str, *, is_indic: bool = False) -> PipelineContext:
    container = MagicMock()
    container.guardrails.check_output = AsyncMock(
        return_value={"blocked": False, "reason": "", "moderated_response": ""}
    )
    container.translation.translate_text = AsyncMock(return_value="[hi] boundary")
    ctx = PipelineContext(
        container=container,
        coordinator=MagicMock(),
        request=MagicMock(),
        user_msg=question,
        preferred_lang="hi" if is_indic else "en",
        is_indic=is_indic,
        trace_id="trace-audit",
        start_time=time.time(),
        state={"user_msg_en": question},
    )
    ctx.final_answer = answer
    return ctx


@pytest.mark.asyncio
async def test_relationship_repair_answer_carries_the_boundary():
    ctx = _output_ctx(SCENARIO_2, "Notice the defensive state first.")
    assert await OutputGuardrailStage().run(ctx) is None
    assert ctx.final_answer.startswith("Notice the defensive state first.")
    assert ctx.final_answer.rstrip().endswith(RELATIONSHIP_SAFETY_BOUNDARY)


@pytest.mark.asyncio
async def test_non_relationship_answer_does_not_get_the_boundary():
    ctx = _output_ctx("What is the Beautiful State?", "It is a state of calm.")
    await OutputGuardrailStage().run(ctx)
    assert ctx.final_answer == "It is a state of calm."


@pytest.mark.asyncio
async def test_indic_seeker_gets_the_translated_boundary():
    ctx = _output_ctx(SCENARIO_2, "उत्तर", is_indic=True)
    await OutputGuardrailStage().run(ctx)
    assert ctx.final_answer.endswith("[hi] boundary")


@pytest.mark.asyncio
async def test_blocked_answer_is_replaced_not_appended():
    ctx = _output_ctx(SCENARIO_2, "bad answer")
    ctx.container.guardrails.check_output = AsyncMock(
        return_value={"blocked": True, "reason": "x", "moderated_response": "moderated"}
    )
    await OutputGuardrailStage().run(ctx)
    assert ctx.final_answer == "moderated"


# --------------------------------------------------------------------------- D


def test_root_cause_of_suffering_expands_to_separation():
    injected = inject_doctrine_keywords(SCENARIO_1)
    assert injected.startswith(SCENARIO_1)
    for term in ("separation", "disconnection", "self-obsession"):
        assert term in injected


def test_root_cause_without_suffering_does_not_expand():
    assert "root_cause_of_suffering" not in classify_doctrine_query(
        "what is the root cause of my back pain"
    )


def test_detachment_expands_to_attachment_and_drops_ekam_geography():
    injected = inject_doctrine_keywords(SCENARIO_4)
    for term in ("attachment", "clinging", "pleasurable states"):
        assert term in injected
    for noise in ("varadaiahpalem", "tirupati", "andhra pradesh"):
        assert noise not in injected


def test_where_is_ekam_still_gets_geography():
    assert "tirupati" in inject_doctrine_keywords("Where is Ekam?")


def test_self_judgment_expands_to_inner_observation():
    injected = inject_doctrine_keywords(SCENARIO_2)
    for term in ("witness", "inner state", "judgment"):
        assert term in injected[len(SCENARIO_2) :]
