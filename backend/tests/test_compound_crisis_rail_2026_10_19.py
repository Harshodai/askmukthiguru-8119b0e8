"""Regression guards for A26 and A27 (authored 2026-10-19).

A26 — "Compound questions must hit the crisis rail on the WHOLE question
before any facet split."

  The check is *ordering*, not just detection. Two independent layers both
  assess the whole raw message before anything is split, rewritten, or
  summarised:

    1. Chat pipeline stage order (`build_default_pipeline`):
       `input_guardrails` (3) -> `distress_detection` (7) -> `langgraph` (11).
       The first-person pipeline runs *inside* `langgraph`, so a whole-message
       crisis pre-emption in `DistressStage` can never be preceded by retrieval.
       `DistressStage.run` assesses `ctx.state["user_msg_en"]` AND the raw
       `ctx.user_msg` (distress_stage.py:199-284).

    2. Inside `FirstPersonPipeline.execute` (services/first_person_pipeline.py):
       Step 1 crisis pre-check (lines 1850-1876, on `[query, retrieval_query]`)
       runs strictly BEFORE Step 2b compound facet decomposition (lines
       1944-1961). The facet splitter `_decompose_query_facets` (line 1366)
       can therefore never be the thing that first "sees" a crisis clause.

A27 — "Practice steps only from recordings or the templated Serene Mind flow;
never LLM-written 'Daily Sadhana'."

  On the first-person path specifically:
    * `daily_practice_card` has NO producer anywhere: it is not a declared
      `GraphState` key (rag/states.py) and is only ever READ
      (glue_stages.py:149,611; result.py; chat_engine.py). It is structurally
      None on every path, not merely null in one configuration.
    * `practice_recommendation` (the only first-person practice metadata) is
      extracted from offline-curated OKF entries of `type == "practice"`
      (quote_weaver.py:591); it returns None rather than inventing steps.
    * `MeditationGenStage` (meditation_gen_stage.py:49) is the ONLY stage that
      LLM-writes meditation instruction text. It sits AFTER `langgraph`, and
      `StageRunner` (stage_runner.py:123) short-circuits on the first non-None
      result — which the first-person path always returns (graph_stage.py:470).

Every assertion below is written so a concrete code change breaks it; each
test docstring names that change.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.config import settings
from app.pipeline.result import PipelineResult
from app.pipeline.stages.base import Stage
from app.pipeline.stages.distress_stage import DistressStage, has_crisis_keywords
from app.pipeline.stages.pipeline_builder import build_default_pipeline
from app.pipeline.stages.stage_runner import StageRunner
from guardrails.lightweight_handler import match_blocked_topic
from services.crisis_helplines import format_helplines_block
from services.first_person_pipeline import FirstPersonPipeline
from services.quote_weaver import _extract_practice_recommendation
from services.serene_mind_engine import DistressLevel, SereneMindEngine

# Crisis phrase embedded MID-SENTENCE in a compound question, after a benign
# meditation-education facet.
COMPOUND_EN = "I want to learn meditation and also I am planning to end my life tonight"
BENIGN_EN = "I want to learn meditation"

# A compound the facet splitter actually separates (the ";" arm of
# `_COMPOUND_SPLIT_RE`, first_person_pipeline.py:1357). Used where the split
# must be *live* for the ordering assertion to be load-bearing.
COMPOUND_EN_SPLITTABLE = "I want to learn meditation; also I am planning to end my life tonight"

# Non-English cases use ONLY patterns already present in the codebase
# (services/serene_mind_engine.py):
#   Hindi CRISIS:  r"(मरना\s*चाहता|मरना\s*चाहती|आत्महत्या|...)"  (line 394)
#   Romanized HI:  r"\b(marna\s*chahta|suicide|zindagi\s*khatam|...)"  (line 669)
COMPOUND_HI = "मुझे ध्यान सीखना है और मैं आत्महत्या करने की सोच रहा हूँ"
BENIGN_HI = "मुझे ध्यान सीखना है"
COMPOUND_HI_ROMANIZED = "mujhe meditation seekhna hai aur main suicide karne ki soch raha hoon"


# ---------------------------------------------------------------------------
# A26 — crisis rail on the WHOLE question, before any facet split
# ---------------------------------------------------------------------------


def test_benign_half_alone_does_not_trip_the_rail():
    """No over-blocking: the meditation-education half is not distress.

    Breaks if: someone loosens the distress/self-harm patterns so that
    "I want to learn meditation" scores >= SEVERE or matches a blocked topic.
    """
    assessment = SereneMindEngine().assess_distress(BENIGN_EN)
    assert assessment.level.value < DistressLevel.SEVERE.value, assessment.level
    assert match_blocked_topic(BENIGN_EN) is None
    assert has_crisis_keywords(BENIGN_EN) is False


def test_crisis_midsentence_in_compound_matches_whole_question():
    """The crisis clause is detected on the WHOLE compound string.

    Breaks if: the classifier only inspected the first clause / a leading
    facet, or the mid-sentence "planning to end my life tonight" stopped
    matching.
    """
    assessment = SereneMindEngine().assess_distress(COMPOUND_EN)
    assert assessment.level == DistressLevel.CRISIS
    assert match_blocked_topic(COMPOUND_EN) is not None
    assert match_blocked_topic(COMPOUND_EN)[0] == "self_harm"
    assert has_crisis_keywords(COMPOUND_EN) is True


@pytest.mark.parametrize(
    "compound,benign",
    [
        (COMPOUND_HI, BENIGN_HI),
        (COMPOUND_HI_ROMANIZED, None),
    ],
)
def test_non_english_compound_crisis_is_detected_on_whole_question(compound, benign):
    """Indic compound crisis (native + romanized) detected on the whole string.

    Uses only patterns already in serene_mind_engine; NO new keyword invented.
    Breaks if: the Indic CRISIS patterns stop being applied to the full
    compound, or a benign Indic half is (over-)blocked.
    """
    assert SereneMindEngine().assess_distress(compound).level == DistressLevel.CRISIS
    assert has_crisis_keywords(compound) is True
    if benign is not None:
        assert SereneMindEngine().assess_distress(benign).level.value < DistressLevel.SEVERE.value
        assert has_crisis_keywords(benign) is False


def test_pipeline_stage_order_puts_whole_message_safety_before_graph():
    """Input guardrails + distress run on the whole message before the graph.

    Breaks if: DistressStage or InputGuardrailStage is reordered after
    GraphStage (langgraph), which would let retrieval precede the crisis rail.
    """
    names = [s.name for s in build_default_pipeline()]
    assert names.index("input_guardrails") < names.index("distress_detection")
    assert names.index("distress_detection") < names.index("langgraph")


@pytest.mark.asyncio
async def test_distress_stage_preempts_compound_on_whole_message():
    """The real DistressStage pre-empts the compound on the whole message.

    No mocked `_detect_distress`: the real `SereneMindEngine` fallback runs.
    Breaks if: DistressStage stops assessing the full `user_msg_en`/`user_msg`,
    or stops returning a crisis PipelineResult for SEVERE+.
    """
    ctx = SimpleNamespace(
        state={"user_msg_en": COMPOUND_EN, "distress_history": []},
        user_msg=COMPOUND_EN,
        user_id="a26-user",
        request=SimpleNamespace(),
        trace_id="a26-compound",
        start_time=0.0,
        # serene_mind=None -> _detect_distress falls back to the pure regex
        # engine, exactly as the fail-closed path does.
        container=SimpleNamespace(serene_mind=None, ollama=None),
    )

    result = await DistressStage().run(ctx)

    assert result is not None
    assert result.intent == "DISTRESS"
    assert result.route_decision == "crisis_preempted"
    assert result.citations == []
    assert ctx.assessment.level == DistressLevel.CRISIS


def test_first_person_pipeline_checks_crisis_before_facet_split(monkeypatch):
    """Crisis pre-check precedes facet decomposition inside the FP pipeline.

    `first_person_facet_split_enabled` is turned ON and the facet decomposer is
    spied on. `COMPOUND_EN_SPLITTABLE` is a string the splitter really splits
    (see the control test below), so if the order were wrong the spy WOULD be
    reached — the assertion is load-bearing, not vacuous. Also asserts no clip
    was retrieved.

    Breaks if: Step 2b (facet split; first_person_pipeline.py:1944) is moved
    above Step 1 (crisis pre-check; line 1850) — the spy would record a call and
    the store would be queried — or the crisis pre-check is removed entirely
    (status would not be `crisis_redirect`).
    """
    import services.first_person_pipeline as fpp

    store = MagicMock()
    store.collection = "first_person_v1"
    redis = MagicMock()
    redis.get.return_value = None

    calls = {"facet_decompose": 0}
    real_decompose = fpp._decompose_query_facets

    def _spy(*args, **kwargs):
        calls["facet_decompose"] += 1
        return real_decompose(*args, **kwargs)

    monkeypatch.setattr(settings, "first_person_facet_split_enabled", True)
    monkeypatch.setattr(fpp, "_decompose_query_facets", _spy)

    pipeline = FirstPersonPipeline(store=store, redis_client=redis)
    result = pipeline.execute(
        query=COMPOUND_EN_SPLITTABLE,
        query_dense_vector=[0.1] * 1024,
    )

    assert result.status == "crisis_redirect"
    assert result.is_direct_answer is False
    assert result.citations == []
    assert result.answer_text == format_helplines_block()
    # No facet was ever formed, and no clip candidate was ever retrieved.
    assert calls["facet_decompose"] == 0
    store.search_hybrid.assert_not_called()


def test_facet_splitter_alone_would_expose_the_meditation_facet():
    """Sanity: the splitter genuinely separates the benign facet.

    This documents WHY the ordering matters — the splitter does produce a
    clip-shaped meditation facet from the compound. It is not a safety
    assertion on its own (the crisis pre-check above is); it is the control
    that proves the crisis pre-check is load-bearing rather than vacuous.

    Breaks if: the compound splitter stops recognising "and also"/clauses,
    which would make the ordering test above less meaningful.
    """
    from services.first_person_pipeline import _decompose_query_facets

    facets = _decompose_query_facets(COMPOUND_EN_SPLITTABLE)
    assert len(facets) >= 2
    assert any("meditation" in f.lower() for f in facets)
    assert any("end my life" in f.lower() for f in facets)


# ---------------------------------------------------------------------------
# A27 — no LLM-written practice text on the first-person path
# ---------------------------------------------------------------------------


def test_daily_practice_card_has_no_producer_in_graph_state():
    """`daily_practice_card` is not a graph-state key and is never written.

    The chat response field is populated only by reading
    `graph_result.get("daily_practice_card")` (glue_stages.py:611). Since no
    graph node writes that key and it is not declared in the typed GraphState,
    the field is structurally None — a real "no generated Daily Sadhana"
    guarantee, not a one-configuration null.

    Breaks if: someone adds a producer (a `daily_practice_card` entry to
    `GraphState.__annotations__` or to `create_initial_state`, or a graph node
    that returns it).
    """
    from rag.graph import create_initial_state
    from rag.states import GraphState

    assert "daily_practice_card" not in GraphState.__annotations__
    assert "daily_practice_card" not in create_initial_state(question="hi")


def test_practice_recommendation_never_invents_steps_without_practice_entry():
    """`practice_recommendation` returns None unless a practice OKF entry exists.

    Steps are taken verbatim from the OKF `key_teachings` of a `type ==
    "practice"` entry; nothing is synthesised. `is_verbatim=False` keeps the
    LLM-extracted OKF summary from being presented as the teacher's words.

    Breaks if: the extractor starts generating steps (e.g. via an LLM) when no
    practice entry is present — the two None assertions fail.
    """
    assert _extract_practice_recommendation([], "how to meditate") is None
    assert (
        _extract_practice_recommendation(
            [{"type": "doctrine", "title": "On Suffering", "key_teachings": ["a", "b"]}],
            "how to meditate",
        )
        is None
    )

    rec = _extract_practice_recommendation(
        [
            {
                "type": "practice",
                "title": "Soul Sync",
                "key_teachings": ["Sit still.", "Watch the breath."],
                "teacher": "Sri Preethaji",
                "source": "Four Sacred Secrets",
            }
        ],
        "teach me a practice",
    )
    assert rec is not None
    # Steps are exactly the stored entry's text — byte-for-byte, no additions.
    assert rec["steps"] == ["Sit still.", "Watch the breath."]
    assert rec["is_verbatim"] is False


@pytest.mark.asyncio
async def test_first_person_path_short_circuits_before_meditation_gen():
    """A served first-person turn never reaches the LLM meditation writer.

    `MeditationGenStage` is the only stage that LLM-writes meditation step
    instruction text. `StageRunner` stops at the first non-None result, and the
    first-person path returns a PipelineResult from GraphStage
    (graph_stage.py:470) — so `meditation_gen` never runs on it.

    Breaks in two concrete ways: (a) reordering `meditation_gen` before
    `langgraph` in `build_default_pipeline`; (b) changing `StageRunner.run` to
    continue after a non-None result — then the spy below records a call.
    """
    names = [s.name for s in build_default_pipeline()]
    assert names.index("langgraph") < names.index("meditation_gen")

    class _ServedFirstPersonStage(Stage):
        """Stands in for GraphStage's first-person result (PipelineResult)."""

        name = "fp_served_stub"

        async def run(self, ctx):
            return PipelineResult(
                final_answer="verbatim clip", route_decision="first_person_bridge"
            )

    class _MeditationGenSpy(Stage):
        name = "meditation_gen_spy"

        def __init__(self) -> None:
            self.called = False

        async def run(self, ctx):
            self.called = True
            return None

    spy = _MeditationGenSpy()
    result = await StageRunner.run([_ServedFirstPersonStage(), spy], SimpleNamespace())

    assert result is not None
    assert result.route_decision == "first_person_bridge"
    assert spy.called is False
