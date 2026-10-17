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
        faculty_access_code=None,
        faculty_gate_disabled=False,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def test_dev_posture_has_no_problems():
    assert check_startup_posture(_cfg()) == []


def test_production_unnamed_environment_is_blocking():
    problems = check_startup_posture(_cfg(is_production=True, faculty_gate_disabled=True))
    assert any("ENVIRONMENT" in p for p in problems)


def test_production_silent_preview_gate_is_blocking():
    problems = check_startup_posture(_cfg(is_production=True, environment="production"))
    assert any("preview gate" in p for p in problems)


def test_production_named_and_gated_is_clean():
    assert (
        check_startup_posture(
            _cfg(
                is_production=True,
                environment="production",
                faculty_gate_disabled=True,
            )
        )
        == []
    )


def test_both_problems_reported_together():
    problems = check_startup_posture(_cfg(is_production=True))
    assert len(problems) == 2
    assert any("ENVIRONMENT" in p for p in problems)
    assert any("preview gate" in p for p in problems)


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
