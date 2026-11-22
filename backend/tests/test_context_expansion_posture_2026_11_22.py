"""Read-only context-expansion posture diagnostic (2026-11-22 follow-up plan).

The additive retrieval expansions are documented as off (AGENTS.md first-person
serving invariant 3, the `app/config.py` comments, `backend/.env.example`) while the
code default and `backend/.env` currently say on. The plan forbids silently choosing
a side: the effective posture must be named and fingerprinted before any follow-up
quality measurement. These tests pin the *diagnostic*, not a production posture —
the owner decision is still open.
"""

from __future__ import annotations

import logging
from types import SimpleNamespace

import pytest

from app import runtime_budget
from app.config import settings

_DOCUMENTED_FLAGS = (
    "first_person_enrichment_window_enabled",
    "first_person_graph_expansion_enabled",
    "first_person_okf_expansion_enabled",
    "first_person_cross_video_diversity_enabled",
    "first_person_teaching_unit_graph_enabled",
)


def _fake(**overrides):
    values = {name: False for name in _DOCUMENTED_FLAGS}
    values.update(overrides)
    return SimpleNamespace(**values)


def test_posture_reports_every_documented_flag_as_off_by_default():
    rows = runtime_budget.expansion_posture(_fake())
    assert [row["name"] for row in rows] == list(_DOCUMENTED_FLAGS)
    assert all(row["documented_default"] is False for row in rows)
    assert all(row["effective"] is False for row in rows)


def test_posture_reads_the_effective_value_not_the_documented_one():
    rows = runtime_budget.expansion_posture(_fake(first_person_okf_expansion_enabled=True))
    by_name = {row["name"]: row for row in rows}
    assert by_name["first_person_okf_expansion_enabled"]["effective"] is True
    assert by_name["first_person_okf_expansion_enabled"]["documented_default"] is False


def test_warning_names_each_flag_that_contradicts_the_documented_posture():
    warnings = runtime_budget.expansion_posture_warnings(
        _fake(first_person_enrichment_window_enabled=True)
    )
    assert len(warnings) == 1
    assert "FIRST_PERSON_ENRICHMENT_WINDOW_ENABLED" in warnings[0]
    assert "invariant 3" in warnings[0]


def test_no_warning_when_the_documented_posture_holds():
    assert runtime_budget.expansion_posture_warnings(_fake()) == []


def test_fingerprint_is_stable_and_changes_when_a_flag_flips():
    first = runtime_budget.expansion_posture_fingerprint(_fake())
    assert first == runtime_budget.expansion_posture_fingerprint(_fake())
    flipped = runtime_budget.expansion_posture_fingerprint(
        _fake(first_person_graph_expansion_enabled=True)
    )
    assert flipped != first
    assert len(first) == 12 and all(c in "0123456789abcdef" for c in first)


def test_diagnostic_is_read_only():
    """Reading the posture must not mutate the live settings object."""
    before = {name: getattr(settings, name) for name in _DOCUMENTED_FLAGS}
    runtime_budget.expansion_posture(settings)
    runtime_budget.expansion_posture_fingerprint(settings)
    assert {name: getattr(settings, name) for name in _DOCUMENTED_FLAGS} == before


def test_log_runtime_budget_reports_the_posture_and_never_raises(caplog):
    with caplog.at_level(logging.INFO):
        runtime_budget.log_runtime_budget(logging.getLogger("test.posture"), settings)
    assert "Context expansion posture:" in caplog.text
    assert "fingerprint=" in caplog.text


@pytest.mark.parametrize("name", _DOCUMENTED_FLAGS)
def test_flag_is_declared_in_settings(name):
    """Every documented flag is a real Settings field, so the diagnostic cannot go stale."""
    assert name in type(settings).model_fields
