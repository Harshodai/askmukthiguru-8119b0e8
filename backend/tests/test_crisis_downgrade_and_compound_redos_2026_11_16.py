"""Regression tests for two defects found 2026-11-16.

1. The existential carve-out in DistressStage lowered CRISIS messages to MILD.
2. _COMPOUND_QUESTION_RE was quadratic on the user's chat message.
"""

from __future__ import annotations

import itertools
import re
import time

import pytest

from app.pipeline.stages.distress_stage import (
    _only_existential_signal,
    classify_existential_vs_severe_distress,
)
from app.pipeline.stages.first_person_bridge import _COMPOUND_QUESTION_RE
from services.serene_mind_engine import DistressLevel, SereneMindEngine

assess_distress = SereneMindEngine().assess_distress


def _would_downgrade(message: str) -> bool:
    """Mirror of the DistressStage carve-out condition (no guardrail match)."""
    assessment = assess_distress(message)
    return (
        assessment.level is DistressLevel.SEVERE
        and _only_existential_signal(assessment)
        and classify_existential_vs_severe_distress(message) == "MILD_EXISTENTIAL"
    )


@pytest.mark.parametrize(
    "message",
    [
        "I feel empty inside and I am going to end it all tonight",
        "I feel empty inside, everyone would be better off without me",
        "I feel empty inside and I don't want to be here anymore",
    ],
)
def test_crisis_message_is_never_downgraded(message: str) -> None:
    assert assess_distress(message).level is DistressLevel.CRISIS
    assert not _would_downgrade(message)


def test_existential_burnout_still_downgrades() -> None:
    assert _would_downgrade("achieved success in my career but still feel empty inside")


def test_extra_signal_blocks_downgrade() -> None:
    class _Assessment:
        level = DistressLevel.SEVERE
        detected_signals = ["[en] empty inside", "[en] hopeless"]

    assert not _only_existential_signal(_Assessment())
    assert not _only_existential_signal(type("A", (), {"detected_signals": []})())


_OLD_COMPOUND_RE = re.compile(
    r"\bboth\s+\w[\w\s]*and\s+\w"
    r"|\w[\w\s]*\s+as\s+well\s+as\s+\w"
    r"|—[^—]{3,80}(?:and|&)[^—]{3,80}—"
    r"|,\s*[^,]+,\s*(?:and|&)\s*"
    r"|\w[\w\s]*,?\s+and\s+(?:also|why|how|what|can|at\s+what|help|do|did|does|is|are|will|would)\b",
    re.IGNORECASE,
)

_WORDS = ["both", "peace", "and", "how", "as", "well", "anger", ",", "what", "is", "?", "also", "—", "love"]


def test_compound_verdict_unchanged_on_short_queries() -> None:
    for length in range(1, 6):
        for combo in itertools.product(_WORDS, repeat=length):
            text = " ".join(combo)
            assert bool(_OLD_COMPOUND_RE.search(text)) == bool(_COMPOUND_QUESTION_RE.search(text)), text


@pytest.mark.parametrize("unit", ["and ", "both ", "x , ", "a  \t"])
def test_compound_pattern_is_fast_at_message_cap(unit: str) -> None:
    text = (unit * 10_000)[:10_000] + "x"
    start = time.perf_counter()
    _COMPOUND_QUESTION_RE.search(text)
    assert time.perf_counter() - start < 0.25
