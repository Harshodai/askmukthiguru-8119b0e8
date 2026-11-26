"""Joint (question, clip) sufficiency judge: default-off, fail-to-abstain (invariant 19)."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

import services.first_person_pipeline as fpp
from app.config import settings
from tests.test_first_person_pipeline_golden_llm import (  # noqa: F401 - autouse fixture
    HARNESS_QUERY,
    SPAN_TEXT_ONE,
    SPAN_TEXT_TWO,
    FakeLLM,
    _deterministic_settings,
    _harness_on,
    _harness_pipeline,
    _llm_settings,
)

pytestmark = [pytest.mark.answerability_real, pytest.mark.relevance_real]


class JointLLM(FakeLLM):
    """FakeLLM plus a joint-sufficiency reply (str, or an exception class to raise)."""

    def __init__(self, joint: Any, **kw: Any) -> None:
        super().__init__(**kw)
        self.joint = joint

    async def generate(self, *, system_prompt: str, user_prompt: str, **kw: Any) -> str:
        if system_prompt == fpp._JOINT_SUFFICIENCY_SYSTEM_PROMPT:
            self.calls.append("joint")
            if isinstance(self.joint, type):
                raise self.joint("fake joint provider error")
            if self.joint == "SLOW":
                await asyncio.sleep(0.5)
            return str(self.joint)
        return await super().generate(system_prompt=system_prompt, user_prompt=user_prompt, **kw)


def _run(monkeypatch, joint: Any, *, flag: bool = True, texts=None, parallel: bool = True):
    _harness_on(monkeypatch, answerability=False)
    monkeypatch.setattr(settings, "first_person_joint_sufficiency_enabled", flag)
    monkeypatch.setattr(settings, "first_person_harness_parallel_enabled", parallel)
    llm = JointLLM(joint)
    pipeline = _harness_pipeline(llm, texts or [SPAN_TEXT_ONE])
    result = asyncio.run(pipeline.aexecute(query_dense_vector=[1.0, 0.0], cache_bypass=True, **HARNESS_QUERY))
    return llm, result


def test_flag_off_makes_no_extra_call(monkeypatch):
    llm, res = _run(monkeypatch, "INSUFFICIENT", flag=False)
    assert "joint" not in llm.calls
    assert res.citations


def test_sufficient_serves(monkeypatch):
    llm, res = _run(monkeypatch, "SUFFICIENT")
    assert llm.calls.count("joint") == 1
    assert res.citations and res.status in ("success", "weak_match")


def test_whitespace_and_case_tolerated(monkeypatch):
    _, res = _run(monkeypatch, "  sufficient\n")
    assert res.citations


@pytest.mark.parametrize("parallel", [True, False])
def test_insufficient_abstains(monkeypatch, parallel):
    _, res = _run(monkeypatch, "INSUFFICIENT", parallel=parallel)
    assert res.status == "abstained" and not res.citations
    assert res.abstain_reason == "joint_insufficient"


@pytest.mark.parametrize("reply", ["INSUFFICIENT.", "NOT SUFFICIENT", "garbage", "", "SUFFICIENT because", "yes"])
@pytest.mark.parametrize("parallel", [True, False])
def test_off_contract_reply_is_indeterminate_abstain(monkeypatch, reply, parallel):
    _, res = _run(monkeypatch, reply, parallel=parallel)
    assert res.status == "abstained" and not res.citations
    assert res.abstain_reason == "joint_sufficiency_indeterminate"


def test_provider_error_and_timeout_abstain(monkeypatch):
    _, res = _run(monkeypatch, RuntimeError)
    assert res.abstain_reason == "joint_sufficiency_indeterminate"
    monkeypatch.setattr(settings, "first_person_relevance_timeout_s", 0.05)
    _, res = _run(monkeypatch, "SLOW")
    assert res.abstain_reason == "joint_sufficiency_indeterminate"


@pytest.mark.asyncio
async def test_insufficient_never_parses_as_sufficient(monkeypatch):
    monkeypatch.setattr(settings, "first_person_relevance_model", "")
    for reply, want in [("INSUFFICIENT", "INSUFFICIENT"), ("SUFFICIENT", "SUFFICIENT"),
                        ("INSUFFICIENT.", "INDETERMINATE"), ("NOT SUFFICIENT", "INDETERMINATE")]:
        got = await fpp._joint_sufficiency_verdict("q", "q", "clip", JointLLM(reply), [])
        assert got == want


def test_legacy_fallthrough_cannot_serve_after_joint_abstain(monkeypatch):
    llm, res = _run(monkeypatch, "INSUFFICIENT", texts=[SPAN_TEXT_ONE, SPAN_TEXT_TWO])
    assert llm.calls.count("joint") == 2  # every context judged, none served
    assert res.status == "abstained" and res.abstain_reason == "joint_insufficient"


def test_second_context_served_when_first_insufficient(monkeypatch):
    class Alternating(JointLLM):
        async def generate(self, *, system_prompt, user_prompt, **kw):
            if system_prompt == fpp._JOINT_SUFFICIENCY_SYSTEM_PROMPT:
                self.calls.append("joint")
                return "SUFFICIENT" if "Every relationship" in user_prompt else "INSUFFICIENT"
            return await FakeLLM.generate(self, system_prompt=system_prompt, user_prompt=user_prompt, **kw)

    _harness_on(monkeypatch, answerability=False)
    monkeypatch.setattr(settings, "first_person_joint_sufficiency_enabled", True)
    res = asyncio.run(
        _harness_pipeline(Alternating("x"), [SPAN_TEXT_ONE, SPAN_TEXT_TWO]).aexecute(query_dense_vector=[1.0, 0.0], cache_bypass=True, **HARNESS_QUERY)
    )
    assert res.citations and "Every relationship" in res.answer_text


def test_fingerprint_only_changes_when_flag_on(monkeypatch):
    import inspect
    src = inspect.getsource(fpp)
    assert '"joint_sufficiency": _JOINT_SUFFICIENCY_PROMPT_VERSION' in src
    assert "if getattr(settings, \"first_person_joint_sufficiency_enabled\", False)" in src
