"""T7-02 characterization matrix: ``FirstPersonPipeline`` with the REAL LLM helpers.

Why this file exists
--------------------
The T7-01 matrix (``test_first_person_pipeline_golden.py``) replaces every LLM
helper with a sync lambda and pins speculative parallelism off, so it never
runs the code T7-02 converts to async: ``run_llm_coroutine``, the harness
parallel fan-out, the speculative gather, the answerability worker and its
join, and the timeout paths. These scenarios run those helpers for real
against a fake async ``llm_service`` whose reply depends only on the prompt.
No network, no Qdrant, no spend.

The goldens were recorded on the pre-T7-02 code (branch ``feature/t7-02``,
first commit) and must not be rewritten by the async conversion.

Recording / updating
--------------------
    cd backend && FP_GOLDEN_UPDATE=1 .venv/bin/pytest tests/test_first_person_pipeline_golden_llm.py -q
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest

import services.first_person_pipeline as fpp
from app.config import settings
from tests.test_first_person_pipeline_golden import (  # noqa: F401 - autouse fixture import
    PROFILE,
    SPAN_TEXT_ONE,
    UPDATE,
    _clip,
    _deterministic_settings,
    _make_context,
    _make_span,
    _new_pipeline,
    _normalize,
    _RecordingPipeline,
    _store_summary,
)

GOLDEN_DIR = Path(__file__).parent / "golden" / "first_person_pipeline_llm"

# The suite-wide conftest stubs of the answerability and relevance helpers
# must not apply: running the real helpers is the point of this matrix.
pytestmark = [pytest.mark.answerability_real, pytest.mark.relevance_real]

SPAN_TEXT_TWO = (
    "Every relationship becomes a mirror when you stop defending yourself; what you see "
    "in the other is the movement of your own inner state, waiting to be seen."
)

# Reply markers the fake scorer keys on: a fragment of the clip text decides
# the score, so each context's verdict is fixed by its own words.
SCORE_BY_FRAGMENT_DEFAULT = {"Suffering is not a punishment": "3", "Every relationship": "3"}


class FakeLLM:
    """Async ``generate`` whose reply is a pure function of the prompt.

    ``answer`` is the answerability reply. ``scores`` maps a clip-text fragment
    to the scorer reply for the one clip that contains it. ``delay_s`` delays
    every reply; ``raise_on`` raises for the named prompt kind.
    """

    def __init__(
        self,
        *,
        answer: str = "yes",
        scores: dict[str, str] | None = None,
        delay_s: float = 0.0,
        raise_on: str | None = None,
    ) -> None:
        self.answer = answer
        self.scores = dict(SCORE_BY_FRAGMENT_DEFAULT if scores is None else scores)
        self.delay_s = delay_s
        self.raise_on = raise_on
        self.calls: list[str] = []

    async def generate(self, *, system_prompt: str, user_prompt: str, **_kw: Any) -> str:
        kind = "answerability" if system_prompt == fpp._ANSWERABILITY_SYSTEM_PROMPT else "scorer"
        self.calls.append(kind)
        if self.delay_s:
            await asyncio.sleep(self.delay_s)
        if self.raise_on == kind:
            raise RuntimeError(f"fake {kind} provider error")
        if kind == "answerability":
            return self.answer
        for fragment, reply in self.scores.items():
            if fragment in user_prompt:
                return reply
        return "0"


@pytest.fixture(autouse=True)
def _llm_settings(monkeypatch):
    """The real helpers read these; pin them so the golden describes this code alone."""
    monkeypatch.setattr(settings, "first_person_relevance_model", "")
    monkeypatch.setattr(settings, "first_person_relevance_jev_enabled", False)
    monkeypatch.setattr(settings, "first_person_context_selector_enabled", False)
    monkeypatch.setattr(settings, "first_person_harness_parallel_enabled", True)
    # A loop remembered by another test module may be stopped; never schedule on it.
    monkeypatch.setattr(fpp, "_REQUEST_LOOP", None)


def _harness_pipeline(llm: FakeLLM, texts: list[str]) -> _RecordingPipeline:
    from unittest.mock import MagicMock

    contexts = []
    for i, text in enumerate(texts):
        span = _make_span(text).model_copy(update={"parent_unit_id": f"parent_{101 + i}"})
        contexts.append(_make_context(span))
    context_store = MagicMock()
    context_store.retrieve.return_value = contexts
    return _RecordingPipeline(
        store=MagicMock(),
        redis_client=MagicMock(get=MagicMock(return_value=None)),
        context_store=context_store,
        llm_service=llm,
        calibration_profile={"threshold": 0.45, "score_kind": "cosine", "claims": "conformance"},
    )


def _harness_on(monkeypatch, *, answerability: bool, relevance: bool = True) -> None:
    monkeypatch.setattr(settings, "first_person_context_harness_enabled", True)
    monkeypatch.setattr(settings, "first_person_answerability_check_enabled", answerability)
    monkeypatch.setattr(settings, "first_person_relevance_gate_enabled", relevance)


HARNESS_QUERY = {"query": "What is the nature of suffering?", "teacher_id": "krishnaji"}


def _scenario_harness_real_gates_serve(monkeypatch):
    _harness_on(monkeypatch, answerability=True)
    return _harness_pipeline(FakeLLM(), [SPAN_TEXT_ONE]), dict(HARNESS_QUERY)


def _scenario_harness_answerability_no(monkeypatch):
    _harness_on(monkeypatch, answerability=True)
    return _harness_pipeline(FakeLLM(answer="no"), [SPAN_TEXT_ONE]), dict(HARNESS_QUERY)


def _scenario_harness_parallel_first_indeterminate(monkeypatch):
    # ctx0 unparseable scorer reply -> indeterminate; ctx1 would pass. Must abstain.
    _harness_on(monkeypatch, answerability=False)
    llm = FakeLLM(scores={"Suffering is not a punishment": "maybe", "Every relationship": "3"})
    return _harness_pipeline(llm, [SPAN_TEXT_ONE, SPAN_TEXT_TWO]), dict(HARNESS_QUERY)


def _scenario_harness_parallel_first_below_min(monkeypatch):
    # ctx0 scored 0 (below min) -> skipped; ctx1 scored 3 -> served.
    _harness_on(monkeypatch, answerability=False)
    llm = FakeLLM(scores={"Suffering is not a punishment": "0", "Every relationship": "3"})
    return _harness_pipeline(llm, [SPAN_TEXT_ONE, SPAN_TEXT_TWO]), dict(HARNESS_QUERY)


def _scenario_harness_sequential_first_below_min(monkeypatch):
    _harness_on(monkeypatch, answerability=False)
    monkeypatch.setattr(settings, "first_person_harness_parallel_enabled", False)
    llm = FakeLLM(scores={"Suffering is not a punishment": "0", "Every relationship": "3"})
    return _harness_pipeline(llm, [SPAN_TEXT_ONE, SPAN_TEXT_TWO]), dict(HARNESS_QUERY)


def _scenario_harness_gate_timeout(monkeypatch):
    _harness_on(monkeypatch, answerability=True)
    monkeypatch.setattr(fpp, "_ANSWERABILITY_TIMEOUT_S", 0.05)
    return _harness_pipeline(FakeLLM(delay_s=0.4), [SPAN_TEXT_ONE]), dict(HARNESS_QUERY)


def _scenario_harness_scorer_timeout(monkeypatch):
    _harness_on(monkeypatch, answerability=False)
    monkeypatch.setattr(settings, "first_person_relevance_timeout_s", 0.05)
    return _harness_pipeline(FakeLLM(delay_s=0.4), [SPAN_TEXT_ONE]), dict(HARNESS_QUERY)


def _scenario_harness_scorer_provider_error(monkeypatch):
    _harness_on(monkeypatch, answerability=False)
    return _harness_pipeline(FakeLLM(raise_on="scorer"), [SPAN_TEXT_ONE]), dict(HARNESS_QUERY)


def _legacy_pipeline(llm: FakeLLM, **kwargs: Any) -> _RecordingPipeline:
    pipeline = _new_pipeline(llm_service=llm, **kwargs)
    pipeline._store.search_hybrid.return_value = [_clip()]
    return pipeline


LEGACY_QUERY = {"query": "What causes suffering?"}


def _scenario_legacy_speculative_gate_yes(monkeypatch):
    monkeypatch.setattr(settings, "first_person_speculative_parallelism_enabled", True)
    monkeypatch.setattr(settings, "first_person_answerability_check_enabled", True)
    return _legacy_pipeline(FakeLLM(), calibration_profile=PROFILE), dict(LEGACY_QUERY)


def _scenario_legacy_speculative_gate_error(monkeypatch):
    monkeypatch.setattr(settings, "first_person_speculative_parallelism_enabled", True)
    monkeypatch.setattr(settings, "first_person_answerability_check_enabled", True)
    llm = FakeLLM(raise_on="answerability")
    return _legacy_pipeline(llm, calibration_profile=PROFILE), dict(LEGACY_QUERY)


def _scenario_legacy_worker_gate_yes(monkeypatch):
    monkeypatch.setattr(settings, "first_person_answerability_check_enabled", True)
    return _legacy_pipeline(FakeLLM(), calibration_profile=PROFILE), dict(LEGACY_QUERY)


def _scenario_legacy_worker_gate_timeout(monkeypatch):
    monkeypatch.setattr(settings, "first_person_answerability_check_enabled", True)
    monkeypatch.setattr(fpp, "_ANSWERABILITY_TIMEOUT_S", 0.05)
    llm = FakeLLM(delay_s=0.4)
    return _legacy_pipeline(llm, calibration_profile=PROFILE), dict(LEGACY_QUERY)


def _scenario_legacy_real_scorer_serve(monkeypatch):
    monkeypatch.setattr(settings, "first_person_relevance_gate_enabled", True)
    llm = FakeLLM(scores={"Suffering arises from resistance": "3"})
    return _legacy_pipeline(llm, calibration_profile=PROFILE), dict(LEGACY_QUERY)


def _scenario_legacy_real_scorer_timeout(monkeypatch):
    monkeypatch.setattr(settings, "first_person_relevance_gate_enabled", True)
    monkeypatch.setattr(settings, "first_person_relevance_timeout_s", 0.05)
    llm = FakeLLM(delay_s=0.4, scores={"Suffering arises from resistance": "3"})
    return _legacy_pipeline(llm, calibration_profile=PROFILE), dict(LEGACY_QUERY)


SCENARIOS = {
    "harness_answerability_no": _scenario_harness_answerability_no,
    "harness_gate_timeout": _scenario_harness_gate_timeout,
    "harness_parallel_first_below_min": _scenario_harness_parallel_first_below_min,
    "harness_parallel_first_indeterminate": _scenario_harness_parallel_first_indeterminate,
    "harness_real_gates_serve": _scenario_harness_real_gates_serve,
    "harness_scorer_provider_error": _scenario_harness_scorer_provider_error,
    "harness_scorer_timeout": _scenario_harness_scorer_timeout,
    "harness_sequential_first_below_min": _scenario_harness_sequential_first_below_min,
    "legacy_real_scorer_serve": _scenario_legacy_real_scorer_serve,
    "legacy_real_scorer_timeout": _scenario_legacy_real_scorer_timeout,
    "legacy_speculative_gate_error": _scenario_legacy_speculative_gate_error,
    "legacy_speculative_gate_yes": _scenario_legacy_speculative_gate_yes,
    "legacy_worker_gate_timeout": _scenario_legacy_worker_gate_timeout,
    "legacy_worker_gate_yes": _scenario_legacy_worker_gate_yes,
}


# legacy_worker_gate_timeout: the worker's own budget and the join's wait are
# both _ANSWERABILITY_TIMEOUT_S, so whether the timed-out worker's estimated
# tokens land before the join gives up is a race by design ("a timed-out
# worker's tokens are dropped, not guessed"). Only that one count is unpinned.
RACY_TOKEN_CASES = frozenset({"legacy_worker_gate_timeout"})


def _observe(pipeline: _RecordingPipeline, result: Any, case: str = "") -> dict[str, Any]:
    llm = pipeline._llm_service
    events = [
        {**event, "llm_tokens": "racy"} if case in RACY_TOKEN_CASES else event
        for event in pipeline.events
    ]
    return {
        "result": _normalize(result.to_dict()),
        "events": _normalize(events),
        "store": _store_summary(pipeline),
        # Which LLM calls ran is behaviour (cost and ordering), so it is pinned;
        # sorted because parallel workers may finish in any order.
        "llm_calls": sorted(llm.calls) if isinstance(llm, FakeLLM) else [],
    }


def _check(case: str, observed: dict[str, Any]) -> None:
    golden_path = GOLDEN_DIR / f"{case}.json"
    if UPDATE:
        GOLDEN_DIR.mkdir(parents=True, exist_ok=True)
        golden_path.write_text(
            json.dumps(observed, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        pytest.skip(f"recorded {golden_path.name}")
    assert golden_path.is_file(), f"missing golden for {case!r}; record with FP_GOLDEN_UPDATE=1"
    expected = json.loads(golden_path.read_text(encoding="utf-8"))
    assert observed == expected, f"{case}: behaviour differs from the recorded golden"


@pytest.mark.parametrize("case", sorted(SCENARIOS))
def test_execute_with_real_llm_helpers_matches_golden(case: str, monkeypatch) -> None:
    pipeline, kwargs = SCENARIOS[case](monkeypatch)
    result = pipeline.execute(query_dense_vector=[1.0, 0.0], cache_bypass=True, **kwargs)
    _check(case, _observe(pipeline, result, case))
