"""DS-12: fail-closed startup checks as small separate functions.

Each unsafe configuration has a test proving startup stops. The lifespan
wire itself is proven by test_lifespan_stops_on_unsafe_posture (the check
raises before any init work runs).
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import FastAPI

from app.main import check_startup_posture, lifespan


def _cfg(**overrides):
    base = dict(
        is_production=False,
        environment="local",
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def test_dev_posture_has_no_problems():
    assert check_startup_posture(_cfg()) == []


def test_production_unnamed_environment_is_blocking():
    problems = check_startup_posture(_cfg(is_production=True))
    assert any("ENVIRONMENT" in p for p in problems)


def test_production_named_and_gated_is_clean():
    assert (
        check_startup_posture(
            _cfg(
                is_production=True,
                environment="production",
            )
        )
        == []
    )


@pytest.mark.asyncio
async def test_lifespan_stops_on_unsafe_posture_before_init(monkeypatch):
    """The lifespan wire: an unsafe posture raises before init_telemetry_db."""
    import app.main as main_mod

    monkeypatch.setattr(main_mod, "check_startup_posture", lambda s: ["ENVIRONMENT unnamed (test)"])

    async def _must_not_run():
        raise AssertionError("init ran despite unsafe posture")

    monkeypatch.setattr(main_mod, "init_telemetry_db", _must_not_run)
    with pytest.raises(RuntimeError, match="ENVIRONMENT unnamed"):
        async with lifespan(FastAPI()):
            pass  # pragma: no cover


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))


# NEW-AI-3 (AI-013): the relevance scorer model must be named in production.
# An empty value silently uses the provider default generation model, which is
# not the measured scorer (lessons: the default model rated same-theme clips
# 3/3, so precision was poor).


def _fp_cfg(**overrides):
    values = dict(
        is_production=True,
        environment="production",
        first_person_route_enabled=True,
        first_person_relevance_gate_enabled=True,
        first_person_relevance_model="anthropic/claude-haiku-5.5",
    )
    values.update(overrides)
    return _cfg(**values)


def test_production_requires_relevance_scorer_model():
    problems = check_startup_posture(_fp_cfg(first_person_relevance_model=""))
    assert any("FIRST_PERSON_RELEVANCE_MODEL" in p for p in problems)
    assert check_startup_posture(_fp_cfg()) == []


def test_blank_relevance_model_counts_as_empty():
    problems = check_startup_posture(_fp_cfg(first_person_relevance_model="   "))
    assert any("FIRST_PERSON_RELEVANCE_MODEL" in p for p in problems)


def test_relevance_model_not_required_when_route_or_gate_is_off():
    off_route = check_startup_posture(
        _fp_cfg(first_person_relevance_model="", first_person_route_enabled=False)
    )
    off_gate = check_startup_posture(
        _fp_cfg(first_person_relevance_model="", first_person_relevance_gate_enabled=False)
    )
    assert off_route == [] and off_gate == []


def test_relevance_model_not_required_outside_production():
    local = _cfg(
        first_person_route_enabled=True,
        first_person_relevance_gate_enabled=True,
        first_person_relevance_model="",
    )
    assert check_startup_posture(local) == []
