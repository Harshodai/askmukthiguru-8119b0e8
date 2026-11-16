"""Crisis phrasings the faculty-demo probe found unrecognised (2026-11-16)."""

from __future__ import annotations

import pytest

from app.intake.safety_kernel import FastSafetyKernel
from services.serene_mind_engine import DistressLevel, SereneMindEngine

CRISIS = [
    "I feel like giving up and ending everything.",
    "I feel like ending it all",
    "I want to end everything",
    "honestly I am thinking of ending it all tonight",
]
BENIGN = [
    "ending everything with a prayer",
    "We are ending everything on time today",
    "The course is ending everything by Friday",
    "I feel like giving up on this diet",
]


@pytest.mark.parametrize("text", CRISIS)
def test_engine_rates_crisis(text):
    assert SereneMindEngine().assess_distress(text).level is DistressLevel.CRISIS


@pytest.mark.parametrize("text", BENIGN)
def test_engine_leaves_ordinary_speech_alone(text):
    assert SereneMindEngine().assess_distress(text).level is not DistressLevel.CRISIS


@pytest.mark.parametrize(
    "text", ["I feel like giving up and ending everything.", "I feel like ending it all"]
)
def test_intake_kernel_preempts_with_helplines(text):
    verdict = FastSafetyKernel().evaluate(text)
    assert verdict.is_crisis is True
    assert "14416" in (verdict.helpline_response or "")


def test_empty_inside_never_lowers_a_crisis_signal():
    """S-01: the "feel empty inside" de-escalation must not downgrade a message that
    carries any other risk signal (it turned CRISIS into MILD at d5bed8dd)."""
    from app.pipeline.stages.distress_stage import _only_existential_signal

    text = "I feel empty inside and I don't want to be alive anymore"
    assessment = SereneMindEngine().assess_distress(text)
    assert assessment.level is DistressLevel.CRISIS
    assert _only_existential_signal(assessment) is False
