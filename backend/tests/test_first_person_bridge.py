"""Task 2 — FirstPersonBridgeStage (app/pipeline/stages/first_person_bridge.py).

Covers the nine explicit sub-tasks of the plan
(`.claude/tasks/world_class_production_elevation_and_docker_redeploy.md` §Task 2):

  1. Eligibility exclusion — only first_person_v7 clip citations can render
     teacher voice; chat-corpus / OKF entries never do.
  2. Verbatim-only assembly — the served answer is the pipeline's own
     assertion-gated text, byte-for-byte; no generation in the stage.
  3. Citation contract — covered in tests/test_citation_contract.py.
  4. `_unquote_unverifiable_spans` interaction — the bridge returns before
     GraphStage, and clip text is present in the guard's context anyway.
  5. Translation policy — quotes never translated; glue only, fail-open.
  6. Safety ordering — after InputGuardrailStage + DistressStage.
  7. Cache contract — returns before CacheUpdateStage; cache keys are
     language-scoped.
  8. Degradation — exception / kill-switch-off => today's graph path.
  9. Release gate — validate_first_person_production_contract() still passes.

Everything runs against a mocked FirstPersonPipeline: no Qdrant, no Neo4j,
no LLM calls.
"""

from __future__ import annotations

import inspect
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.config import settings
from app.orchestrator_utils import _TRANSLATION_CACHE, cache_language_key
from app.pipeline.pipeline_coordinator import PipelineCoordinator
from app.pipeline.result import PipelineResult
from app.pipeline.stages import build_default_pipeline
from app.pipeline.stages import first_person_bridge as bridge_module
from app.pipeline.stages.context import PipelineContext
from app.pipeline.stages.first_person_bridge import FirstPersonBridgeStage
from app.pipeline.stages.stage_runner import StageRunner

_CLIP_TEXT = (
    "Suffering is resistance to what is, and the body holds every resistance "
    "it has ever met until you meet it with awareness."
)

_ANSWER = (
    "Sri Preethaji addresses this directly in her discourse on the nature of consciousness:\n\n"
    "**Sri Preethaji** · [The Nature of Consciousness]"
    "(https://www.youtube.com/watch?v=abc123&t=99s)\n\n"
    f"{_CLIP_TEXT}\n\n"
    "---\n\n"
    "*Where does resistance show up in the body right now?*\n\n"
    "*What remains when you stop fighting what is here?*"
)

# The exact stage-name chain the product had before Task 2 (kill-switch off).
_PRE_BRIDGE_CHAIN = [
    "kill_switch",
    "cache_check",
    "request_state",
    "input_guardrails",
    "circuit_breaker",
    "doctrine_cache",
    "casual_short_circuit",
    "distress_detection",
    "bounded_comparison_short_circuit",
    "langgraph",
    "meditation_gen",
    "translation",
    "tone_adapter",
    "output_guardrails",
    "memory_save",
    "cache_update",
    "result_assembly",
]


def _clip_citation(**overrides) -> dict:
    """FirstPersonPipeline._build_citation shape (sub-task 3 fixture)."""
    citation = {
        "point_id": "abc123@99s",
        "video_id": "abc123",
        "start_ms": 99_000,
        "end_ms": 129_000,
        "timestamp_seconds": 99,
        "speaker": "Sri Preethaji",
        "teacher_id": "preethaji",
        "transcript_hash": "0" * 64,
        "verbatim_text": _CLIP_TEXT,
        "text_snippet": _CLIP_TEXT,
        "source_url": "https://www.youtube.com/watch?v=abc123&t=99s",
        "video_url": "https://www.youtube.com/watch?v=abc123",
        "playback_start_seconds": 98.5,
        "playback_end_seconds": 129.5,
        "playback_url": "https://www.youtube.com/watch?v=abc123&t=98s",
        "confidence": 0.71,
        "is_verbatim": True,
        "provenance_kind": "speech_turn_clip",
        "caption_status": "auto_transcript",
    }
    citation.update(overrides)
    return citation


def _fp_result(
    *,
    answer: str = _ANSWER,
    citations: list | None = None,
    status: str = "success",
    is_direct: bool = True,
) -> SimpleNamespace:
    return SimpleNamespace(
        answer_text=answer,
        citations=[_clip_citation()] if citations is None else citations,
        status=status,
        is_direct_answer=is_direct,
        latency_ms=42.0,
        cached=False,
        error=None,
    )


def _container(*, block_output: bool = False) -> MagicMock:
    container = MagicMock()
    container.guardrails = AsyncMock()
    container.guardrails.check_output.return_value = {
        "blocked": block_output,
        "reason": "phrase" if block_output else None,
    }
    container.embedding = AsyncMock()
    container.embedding.encode_single_full_async.return_value = {
        "dense": [0.0] * int(settings.embedding_dimension),
        "sparse": {},
    }
    container.serene_mind = None
    container.translation = None
    return container


def _ctx(
    container,
    *,
    msg: str = "how do I find inner peace?",
    lang: str = "en",
    is_indic: bool = False,
) -> PipelineContext:
    return PipelineContext(
        container=container,
        coordinator=MagicMock(),
        request=MagicMock(),
        user_msg=msg,
        preferred_lang=lang,
        is_indic=is_indic,
        trace_id="trace-bridge-test",
        start_time=time.time(),
        state={"user_msg_en": msg},
    )


@pytest.fixture(autouse=True)
def _bridge_gates(monkeypatch):
    """The stage's own gates on, and a clean glue-translation cache."""
    monkeypatch.setattr(settings, "first_person_chat_bridge_enabled", True)
    monkeypatch.setattr(settings, "first_person_route_enabled", True)
    monkeypatch.setattr(settings, "first_person_mode", "retrieval_only")
    _TRANSLATION_CACHE.clear()


@pytest.fixture
def fp_pipeline(monkeypatch):
    """Patch the stage's pipeline lookup with a mocked FirstPersonPipeline."""
    pipeline = MagicMock()
    pipeline.execute = MagicMock(return_value=_fp_result())
    monkeypatch.setattr(bridge_module, "_fp_pipeline", lambda container: pipeline)
    return pipeline


# ---------------------------------------------------------------------------
# Sub-task 1 — eligibility exclusion (voice-verified teacher voice only)
# ---------------------------------------------------------------------------


def test_stage_documents_the_chat_corpus_exclusion_rule():
    """The chat-corpus / OKF exclusion must be stated where it is enforced."""
    source = inspect.getsource(bridge_module)
    assert "spiritual_wisdom_contextual" in source
    assert "OKF summaries may NEVER render as teacher speech" in source


@pytest.mark.asyncio
async def test_non_clip_citations_are_dropped_at_the_bridge(fp_pipeline):
    """A chat-corpus chunk or OKF summary cannot ride along as teacher voice."""
    chat_chunk = {
        "source_url": "https://example.com/chunk-1",
        "text_snippet": "machine rewritten corpus text",
        "speaker": "Sri Krishnaji",
    }
    okf_entry = {
        "source_url": "https://example.com/okf-1",
        "text_snippet": "curated doctrine summary",
        "provenance_kind": "curated_okf",
    }
    fp_pipeline.execute.return_value = _fp_result(
        citations=[chat_chunk, okf_entry, _clip_citation()]
    )

    result = await FirstPersonBridgeStage().run(_ctx(_container()))

    assert result is not None
    assert [c["video_id"] for c in result.citations] == ["abc123"]
    assert all(c["is_verbatim"] is True for c in result.citations)


@pytest.mark.asyncio
async def test_answer_with_only_chat_or_okf_citations_is_not_served(fp_pipeline):
    fp_pipeline.execute.return_value = _fp_result(
        citations=[
            {"source_url": "https://example.com/chunk-1", "text_snippet": "rewritten"},
            {"source_url": "https://example.com/okf-1", "text_snippet": "doctrine"},
        ]
    )

    assert await FirstPersonBridgeStage().run(_ctx(_container())) is None


# ---------------------------------------------------------------------------
# Sub-task 2 — verbatim-only assembly (zero generation)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_assembled_answer_is_served_byte_identical(fp_pipeline):
    """The pipeline's assertion-gated text passes through untouched."""
    result = await FirstPersonBridgeStage().run(_ctx(_container()))

    assert result is not None
    assert result.final_answer == _ANSWER
    assert _CLIP_TEXT in result.final_answer
    assert result.model_used is None
    assert result.model_provider is None
    assert result.verification["method"] == "first_person_verbatim_clip_gate"
    assert result.verification["passed"] is True
    assert result.citations_verified is True
    assert result.faithfulness_score is None  # not computed — never fabricated


def test_stage_contains_no_text_generation_call():
    """No LLM generate/weave call exists in the bridge (selection-only)."""
    source = inspect.getsource(bridge_module)
    assert ".generate(" not in source
    assert ".weave(" not in source


@pytest.mark.asyncio
async def test_answer_without_its_clip_text_is_refused(fp_pipeline):
    """A paraphrased answer must never be served as teacher speech."""
    fp_pipeline.execute.return_value = _fp_result(
        answer="Sri Preethaji teaches that awareness dissolves all inner conflict."
    )

    assert await FirstPersonBridgeStage().run(_ctx(_container())) is None


def test_quote_weaver_gate_rejects_a_paraphrased_quote():
    """The gate the bridge inherits: quoted text must be an exact substring."""
    from services.quote_weaver import QuoteWeaverAssertionGate

    quoted_exact = (
        f'Listen: "{_CLIP_TEXT}"\n\n'
        "https://www.youtube.com/watch?v=abc123&t=99s\n\n"
        "---\n\n"
        "*What are you resisting?*\n"
    )
    quoted_paraphrase = quoted_exact.replace(
        _CLIP_TEXT, "suffering is basically just resistance, you know"
    )

    clips = [{"video_id": "abc123", "verbatim_text": _CLIP_TEXT}]
    valid, _reason = QuoteWeaverAssertionGate.validate(quoted_exact, clips, [])
    assert valid is True

    valid, reason = QuoteWeaverAssertionGate.validate(quoted_paraphrase, clips, [])
    assert valid is False
    assert "quote" in str(reason).lower()


# ---------------------------------------------------------------------------
# Sub-task 4 — _unquote_unverifiable_spans interaction
# ---------------------------------------------------------------------------


def test_bridge_returns_before_the_graph_quote_stripper():
    names = [s.name for s in build_default_pipeline()]
    # Plug-and-play cutover: the bridge is no longer a chain stage — it runs
    # inside the graph as the registry-dispatched first_person module and
    # routes to END before format_final_answer (_route_after_first_person).
    assert "first_person_bridge" not in names
    source = inspect.getsource(bridge_module)
    # The stage never invokes the graph's quote stripper itself.
    assert "_unquote_unverifiable_spans(" not in source


@pytest.mark.asyncio
async def test_clip_text_is_present_in_the_context_the_quote_guard_checks(fp_pipeline):
    """If any cleaning chain did run, the clip text it checks against is there.

    The guard demotes quotes absent from its docs list; bridged citations
    carry the verbatim text, so the served quote verifies against them.
    """
    from rag.nodes.generation import _unquote_unverifiable_spans

    result = await FirstPersonBridgeStage().run(_ctx(_container()))
    assert result is not None

    quoted_answer = f'The teaching is plain: "{_CLIP_TEXT}"'
    guard_docs = [{"text": c["verbatim_text"]} for c in result.citations]
    kept, removed = _unquote_unverifiable_spans(quoted_answer, guard_docs)
    assert removed == 0
    assert _CLIP_TEXT in kept

    # With an unrelated docs list the same guard would strip it — which is
    # exactly why the bridge returns before the graph's cleaning chain (an
    # empty docs list is a documented no-op for this helper).
    _kept, removed_without_docs = _unquote_unverifiable_spans(
        quoted_answer, [{"text": "an unrelated corpus passage about other things"}]
    )
    assert removed_without_docs == 1


# ---------------------------------------------------------------------------
# Sub-task 5 — translation policy (quotes never translated)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_hindi_preferring_user_gets_verbatim_quotes_and_localized_glue(fp_pipeline):
    container = _container()
    seen: list[str] = []

    async def _translate(*, text: str, source_lang: str, target_lang: str, **_kw):
        seen.append(text)
        assert source_lang == "en"
        assert target_lang == "hi"
        return f"HI({text})"

    container.translation = MagicMock()
    container.translation.translate_text = _translate

    result = await FirstPersonBridgeStage().run(_ctx(container, lang="hi", is_indic=True))

    assert result is not None
    # Quotes: verbatim, untranslated English teacher words.
    assert _CLIP_TEXT in result.final_answer
    assert f"HI({_CLIP_TEXT})" not in result.final_answer
    # Glue: localized.
    assert "HI(" in result.final_answer
    # The translator never received the teacher's words (or a link/speaker).
    assert seen, "glue must be translated for an Indic seeker"
    for fragment in seen:
        assert _CLIP_TEXT not in fragment
        assert "https://www.youtube.com" not in fragment
        assert "**Sri Preethaji**" not in fragment
    # The clip text still appears exactly once — never split by translation.
    assert result.final_answer.count(_CLIP_TEXT) == 1


@pytest.mark.asyncio
async def test_glue_translation_timeout_fails_open_with_quotes_intact(fp_pipeline):
    container = _container()

    async def _timeout(*, text: str, source_lang: str, target_lang: str, **_kw):
        raise TimeoutError("translation budget exhausted")

    container.translation = MagicMock()
    container.translation.translate_text = _timeout

    result = await FirstPersonBridgeStage().run(_ctx(container, lang="hi", is_indic=True))

    assert result is not None
    assert _CLIP_TEXT in result.final_answer
    assert "Sri Preethaji addresses this directly" in result.final_answer


@pytest.mark.asyncio
async def test_english_preferring_user_never_triggers_translation(fp_pipeline):
    container = _container()
    container.translation = MagicMock()
    container.translation.translate_text = AsyncMock()

    result = await FirstPersonBridgeStage().run(_ctx(container, lang="en", is_indic=False))

    assert result is not None
    container.translation.translate_text.assert_not_called()


# ---------------------------------------------------------------------------
# Sub-task 6 — safety ordering (bridge after guardrails + distress)
# ---------------------------------------------------------------------------


def test_bridge_is_ordered_after_input_guardrail_and_distress():
    names = [s.name for s in build_default_pipeline()]
    assert names.index("input_guardrails") < names.index("distress_detection")
    assert names.index("distress_detection") < names.index("langgraph")
    # Cutover: first-person runs INSIDE the langgraph stage (registry module),
    # reached only after the whole outer safety lane — no chain entry of its own.
    assert "first_person_bridge" not in names


@pytest.mark.asyncio
async def test_acute_self_harm_query_never_reaches_the_bridge(monkeypatch):
    """DISTRESS preempts: zero citations, bridge never invoked, no graph run."""
    from app.pipeline.stages.distress_stage import DistressStage
    from services.serene_mind_engine import DistressAssessment, DistressLevel

    distress = DistressStage()
    distress._detect_distress = AsyncMock(
        return_value=DistressAssessment(
            level=DistressLevel.CRISIS,
            confidence=0.99,
            detected_signals=["suicide"],
            recommended_response_type="crisis",
        )
    )
    distress._maybe_trigger_proactive_serene_mind = AsyncMock()

    bridge_ran = AsyncMock(return_value=None)
    monkeypatch.setattr(FirstPersonBridgeStage, "_bridge", bridge_ran)

    called: list[str] = []

    class _Sentinel:
        name = "langgraph"

        async def run(self, _ctx):
            called.append("graph")
            return None

    ctx = SimpleNamespace(
        state={"user_msg_en": "I want to kill myself tonight", "distress_history": []},
        user_msg="I want to kill myself tonight",
        preferred_lang="en",
        trace_id="trace-distress",
        start_time=time.time(),
        routing_chain=[],
        route_metadata={},
    )

    result = await StageRunner.run(
        [distress, FirstPersonBridgeStage(), _Sentinel()], ctx, coordinator=None
    )

    assert result is not None
    assert result.intent == "DISTRESS"
    assert result.citations == []
    assert result.route_decision == "crisis_preempted"
    bridge_ran.assert_not_awaited()
    assert called == []  # graph never ran either


# ---------------------------------------------------------------------------
# Sub-task 7 — cache contract
# ---------------------------------------------------------------------------


def test_bridge_returns_before_cache_update():
    import importlib

    names = [s.name for s in build_default_pipeline()]
    # Cutover: the bridge is in-graph; its PipelineResult short-circuits the
    # chain at GraphStage, so cache_update still never runs for FP answers.
    assert "first_person_bridge" not in names
    graph_stage_src = inspect.getsource(importlib.import_module("app.pipeline.stages.graph_stage"))
    assert "isinstance(result, PipelineResult)" in graph_stage_src


@pytest.mark.asyncio
async def test_stage_runner_stops_at_the_bridge_so_cache_update_never_runs(fp_pipeline):
    from app.pipeline.stages.base import Stage

    ran: list[str] = []

    class _Recorder(Stage):
        name = "cache_update"

        async def run(self, _ctx):
            ran.append("cache_update")
            return None

    result = await StageRunner.run(
        [FirstPersonBridgeStage(), _Recorder()], _ctx(_container()), coordinator=None
    )

    assert result is not None
    assert result.route_decision == "first_person_bridge"
    assert ran == []  # bridge results are never written to the shared cache


def test_cache_key_is_language_scoped():
    """A bridge answer must never be replayed under another language's key."""
    fake_self = SimpleNamespace(_is_standalone_question=lambda _msg: True)
    message = "what is inner peace"
    key_en = PipelineCoordinator._build_context_aware_cache_key(fake_self, message, "en")
    key_hi = PipelineCoordinator._build_context_aware_cache_key(fake_self, message, "hi")

    assert key_en != key_hi
    assert cache_language_key(message, "en") in key_en
    assert cache_language_key(message, "hi") in key_hi


def test_cache_check_lookups_are_language_prefixed():
    """CacheCheckStage's own semantic key carries the preferred language."""
    from app.pipeline.stages import cache_stage

    source = " ".join(inspect.getsource(cache_stage.CacheCheckStage).split())
    assert "preferred_lang or 'en'" in source


# ---------------------------------------------------------------------------
# Sub-task 8 — failure / degradation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_bridge_exception_falls_through_to_graph(monkeypatch):
    def _boom(_container):
        raise RuntimeError("calibration profile missing")

    monkeypatch.setattr(bridge_module, "_fp_pipeline", _boom)

    called: list[str] = []

    class _Sentinel:
        name = "langgraph"

        async def run(self, _ctx):
            called.append("graph")
            return PipelineResult(final_answer="graph answer", route_decision="query")

    result = await StageRunner.run(
        [FirstPersonBridgeStage(), _Sentinel()], _ctx(_container()), coordinator=None
    )

    assert called == ["graph"]
    assert result is not None
    assert result.final_answer == "graph answer"


@pytest.mark.asyncio
async def test_embedding_failure_falls_through_to_graph():
    container = _container()
    container.embedding.encode_single_full_async = AsyncMock(side_effect=RuntimeError("down"))

    assert await FirstPersonBridgeStage().run(_ctx(container)) is None


@pytest.mark.parametrize(
    ("status", "is_direct"),
    [
        ("abstained", False),
        ("weak_match", False),
        ("error", False),
        ("crisis_redirect", False),
        ("success", False),  # below the calibrated profile threshold
    ],
)
@pytest.mark.asyncio
async def test_non_direct_outcomes_fall_through_to_graph(fp_pipeline, status, is_direct):
    fp_pipeline.execute.return_value = _fp_result(status=status, is_direct=is_direct)

    assert await FirstPersonBridgeStage().run(_ctx(_container())) is None


@pytest.mark.asyncio
async def test_output_rail_block_falls_through_to_graph(fp_pipeline):
    """Decision: a blocked bridge answer is never served — GraphStage runs."""
    assert await FirstPersonBridgeStage().run(_ctx(_container(block_output=True))) is None


@pytest.mark.asyncio
async def test_kill_switch_off_restores_exact_current_behavior(monkeypatch, fp_pipeline):
    monkeypatch.setattr(settings, "first_person_chat_bridge_enabled", False)

    # The stage is not even constructed...
    names = [s.name for s in build_default_pipeline()]
    assert "first_person_bridge" not in names
    assert names == _PRE_BRIDGE_CHAIN
    # ...and a directly-constructed stage does nothing either.
    assert await FirstPersonBridgeStage().run(_ctx(_container())) is None
    fp_pipeline.execute.assert_not_called()


@pytest.mark.asyncio
async def test_route_flag_off_means_no_bridge(monkeypatch, fp_pipeline):
    """The bridge never becomes a second, ungated first-person path."""
    monkeypatch.setattr(settings, "first_person_route_enabled", False)

    assert await FirstPersonBridgeStage().run(_ctx(_container())) is None
    fp_pipeline.execute.assert_not_called()


# ---------------------------------------------------------------------------
# Ask-1 — FP-primary: general LLM fallback switch (first_person_llm_fallback_enabled)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fallback_off_weak_match_abstains_instead_of_generating(fp_pipeline, monkeypatch):
    """Owner switch: no verbatim match + LLM fallback off => honest static
    abstain, never a fall-through to the generating graph."""
    monkeypatch.setattr(settings, "first_person_llm_fallback_enabled", False)
    fp_pipeline.execute.return_value = _fp_result(status="weak_match", is_direct=False)

    result = await FirstPersonBridgeStage().run(_ctx(_container()))

    assert result is not None
    assert result.route_decision == "first_person_abstain"
    assert result.citations == []
    assert result.model_used is None
    assert result.model_provider is None
    assert result.verification["method"] == "first_person_no_match_abstain"
    assert "verified verbatim teaching" in result.final_answer
    assert result.route_metadata["llm_fallback_enabled"] is False
    assert result.route_metadata["decline_status"] == "weak_match"


@pytest.mark.parametrize("status", ["abstained", "success"])  # success = below threshold
@pytest.mark.asyncio
async def test_fallback_off_other_declines_also_abstain(fp_pipeline, monkeypatch, status):
    monkeypatch.setattr(settings, "first_person_llm_fallback_enabled", False)
    fp_pipeline.execute.return_value = _fp_result(status=status, is_direct=False)

    result = await FirstPersonBridgeStage().run(_ctx(_container()))

    assert result is not None
    assert result.route_decision == "first_person_abstain"


@pytest.mark.asyncio
async def test_fallback_off_store_error_gets_unavailable_message(fp_pipeline, monkeypatch):
    monkeypatch.setattr(settings, "first_person_llm_fallback_enabled", False)
    fp_pipeline.execute.return_value = _fp_result(status="error", is_direct=False)

    result = await FirstPersonBridgeStage().run(_ctx(_container()))

    assert result is not None
    assert result.verification["method"] == "first_person_store_unavailable"
    assert "teaching library" in result.final_answer


@pytest.mark.asyncio
async def test_crisis_redirect_always_falls_through_even_with_fallback_off(
    fp_pipeline, monkeypatch
):
    """Safety carve-out: crisis must keep flowing to distress handling."""
    monkeypatch.setattr(settings, "first_person_llm_fallback_enabled", False)
    fp_pipeline.execute.return_value = _fp_result(status="crisis_redirect", is_direct=False)

    assert await FirstPersonBridgeStage().run(_ctx(_container())) is None


@pytest.mark.asyncio
async def test_imperative_meditation_falls_through_with_fallback_off(fp_pipeline, monkeypatch):
    """Product carve-out: the graph's meditation guide stays reachable."""
    monkeypatch.setattr(settings, "first_person_llm_fallback_enabled", False)
    fp_pipeline.execute.return_value = _fp_result(status="abstained", is_direct=False)

    result = await FirstPersonBridgeStage().run(_ctx(_container(), msg="Start the meditation"))

    assert result is None


@pytest.mark.asyncio
async def test_fallback_off_does_not_affect_a_direct_serve(fp_pipeline, monkeypatch):
    """FP-primary: a verbatim serve is unaffected by the fallback switch."""
    monkeypatch.setattr(settings, "first_person_llm_fallback_enabled", False)

    result = await FirstPersonBridgeStage().run(_ctx(_container()))

    assert result is not None
    assert result.route_decision == "first_person_bridge"
    assert _CLIP_TEXT in result.final_answer


def test_fallback_flag_defaults_to_on_and_is_declared():
    """Default = today's fall-through behavior; the flag must be a declared setting."""
    from app.config import Settings

    assert "first_person_llm_fallback_enabled" in Settings.model_fields
    assert Settings.model_fields["first_person_llm_fallback_enabled"].default is True


# ---------------------------------------------------------------------------
# Sub-task 9 — release gate
# ---------------------------------------------------------------------------


def test_release_gate_still_passes_and_is_still_called_at_boot():
    from app.release_manifest import get_release_manifest
    from services.first_person_release import validate_first_person_production_contract

    # Dev/test config must pass (the gate only hardens in production).
    validate_first_person_production_contract(settings, get_release_manifest())

    main_source = (Path(__file__).resolve().parents[1] / "app" / "main.py").read_text(
        encoding="utf-8"
    )
    assert "validate_first_person_production_contract(" in main_source
    # The new flag is not part of the release contract: killing the bridge
    # cannot make an otherwise-safe first-person release unsafe.
    assert "first_person_chat_bridge_enabled" not in main_source


if __name__ == "__main__":
    import sys

    sys.exit(pytest.main([__file__, "-v"]))
