"""The pre-pipeline crisis pre-screen must catch everything DistressStage pre-empts (2026-10-08).

``has_crisis_keywords`` gates the cache read and chat.py's context-limit 409,
both of which run BEFORE DistressStage. It was a separate hand-written list and
missed 34 of 38 WP2 implicit-ideation cases, so a cached answer or a 409 could
reach a seeker in crisis. Rule: anything assess_distress puts at SEVERE+ also
trips the pre-screen.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from app.pipeline.stages.distress_stage import has_crisis_keywords

_PROBES = (
    Path(__file__).resolve().parents[2]
    / "evals/scenarios/tier3_crisis/005_implicit_ideation_multilingual.yaml"
)
_RISK = [
    pytest.param(t["user"], id=s["id"])
    for s in yaml.safe_load(_PROBES.read_text(encoding="utf-8"))["scenarios"]
    for t in s["turns"]
    if t.get("expect_min_level") in ("SEVERE", "CRISIS")
]


@pytest.mark.parametrize("msg", _RISK)
def test_prescreen_catches_severe_probe(msg):
    assert has_crisis_keywords(msg)


def test_plain_question_does_not_trip_prescreen():
    assert not has_crisis_keywords("What is the beautiful state?")
