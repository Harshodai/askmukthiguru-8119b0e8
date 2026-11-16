"""NEW-SEC-1 (OPS-001, OPS-002): integrity detection keyed to posture; assembly re-check.

OPS-001: ``guru_integrity_breach_total`` fired only when the bridge flag was
on, so the second line of defence was blind exactly when the first line (the
bridge) was switched off. The posture is "generated teaching not allowed"
(``fail_closed_active``), not the bridge flag.

OPS-002: a served clip whose text no longer matches its stored hash is refused
at assembly and counted in ``guru_served_integrity_failure_total{check}``.
"""

from __future__ import annotations

import pytest

import tests.test_first_person_bridge as _bridge_tests
from app.answer_contract import served_clip_integrity_failures
from app.config import settings
from app.pipeline.pipeline_coordinator import PipelineCoordinator
from app.pipeline.result import PipelineResult
from app.pipeline.stages.first_person_bridge import FirstPersonBridgeStage
from tests.test_first_person_bridge import _CLIP_TEXT, _clip_citation, _container, _ctx, _fp_result

_bridge_gates = _bridge_tests._bridge_gates
fp_pipeline = _bridge_tests.fp_pipeline


def _breaches() -> float:
    from app.metrics import INTEGRITY_BREACH_TOTAL

    return INTEGRITY_BREACH_TOTAL.labels(lane="teaching")._value.get()


def _served_failures(check: str) -> float:
    from app.metrics import SERVED_INTEGRITY_FAILURE_TOTAL

    return SERVED_INTEGRITY_FAILURE_TOTAL.labels(check=check)._value.get()


def _generated_teaching() -> PipelineResult:
    return PipelineResult(
        final_answer="generated prose",
        intent="QUERY",
        model_used="deepseek/deepseek-chat",
        route_decision="graph",
        citations=[{"point_id": "p1"}],
        citations_verified=True,
        verification={"passed": True, "method": "lettuce", "citations_verified": True},
    )


def test_breach_detector_fires_with_the_bridge_flag_off(monkeypatch):
    monkeypatch.setattr(settings, "first_person_chat_bridge_enabled", False)
    monkeypatch.setattr(settings, "first_person_llm_fallback_enabled", False)
    before = _breaches()

    PipelineCoordinator._emit_answer_outcome(_generated_teaching())

    assert _breaches() == before + 1


def test_breach_detector_silent_when_generation_is_allowed(monkeypatch):
    monkeypatch.setattr(settings, "first_person_chat_bridge_enabled", True)
    monkeypatch.setattr(settings, "first_person_llm_fallback_enabled", True)
    before = _breaches()

    PipelineCoordinator._emit_answer_outcome(_generated_teaching())

    assert _breaches() == before


def test_reassembly_check_flags_hash_and_substring():
    good = _clip_citation()
    assert served_clip_integrity_failures([good], _CLIP_TEXT) == []
    tampered = dict(good, verbatim_text=_CLIP_TEXT + " (edited)")
    assert "hash" in served_clip_integrity_failures([tampered], _CLIP_TEXT + " (edited)")
    assert served_clip_integrity_failures([good], "some other answer") == ["substring"]
    assert served_clip_integrity_failures([dict(good, transcript_hash="")], _CLIP_TEXT) == ["hash"]
    # v10: source_text_hash is the per-span field and wins over transcript_hash.
    v10 = dict(good, source_text_hash=good["transcript_hash"], transcript_hash="0" * 64)
    assert served_clip_integrity_failures([v10], _CLIP_TEXT) == []


@pytest.mark.asyncio
async def test_bridge_refuses_a_clip_that_fails_the_hash_at_assembly(fp_pipeline):
    tampered = _clip_citation(transcript_hash="0" * 64)
    fp_pipeline.execute.return_value = _fp_result(citations=[tampered])
    before = _served_failures("hash")

    result = await FirstPersonBridgeStage().run(_ctx(_container()))

    assert result.route_decision == "first_person_abstain"
    assert result.citations == []
    assert result.verification["passed"] is False
    assert result.route_metadata["abstain_reason"] == "served_integrity_failure"
    assert _served_failures("hash") == before + 1
