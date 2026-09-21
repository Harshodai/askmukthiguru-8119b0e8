"""Regression tests for PLAN.md Phase A5 — the generation kill switch."""

from unittest.mock import MagicMock

import pytest

from app.pipeline.stages.kill_switch_stage import KillSwitchStage, is_generation_killed


@pytest.fixture(autouse=True)
def _reset_settings():
    from app.config import settings

    original_enabled = settings.generation_kill_switch_enabled
    original_locales = settings.generation_kill_switch_locales
    yield
    settings.generation_kill_switch_enabled = original_enabled
    settings.generation_kill_switch_locales = original_locales


def test_default_off():
    assert is_generation_killed("en") is False
    assert is_generation_killed(None) is False


def test_global_switch_kills_every_locale():
    from app.config import settings

    settings.generation_kill_switch_enabled = True
    assert is_generation_killed("en") is True
    assert is_generation_killed("hi") is True
    assert is_generation_killed(None) is True


def test_per_locale_switch_only_kills_listed_locales():
    from app.config import settings

    settings.generation_kill_switch_locales = "hi, te"
    assert is_generation_killed("hi") is True
    assert is_generation_killed("te") is True
    assert is_generation_killed("en") is False
    assert is_generation_killed("HI") is True  # case-insensitive


@pytest.mark.asyncio
async def test_stage_returns_none_when_off():
    stage = KillSwitchStage()
    ctx = MagicMock(preferred_lang="en")
    result = await stage.run(ctx)
    assert result is None


@pytest.mark.asyncio
async def test_stage_returns_static_response_with_helplines_when_on():
    from app.config import settings

    settings.generation_kill_switch_enabled = True
    stage = KillSwitchStage()
    ctx = MagicMock(preferred_lang="en", trace_id="t1", start_time=0.0)

    result = await stage.run(ctx)

    assert result is not None
    assert result.intent == "SYSTEM_KILL_SWITCH"
    assert result.model_used is None  # no model call
    assert result.verification == {
        "passed": True,
        "method": "kill_switch_static_response",
        "citations_verified": False,
    }
    # Must actually contain real helpline data, not just claim to.
    assert "112" in result.final_answer or "988" in result.final_answer


@pytest.mark.asyncio
async def test_stage_respects_per_locale_switch():
    from app.config import settings

    settings.generation_kill_switch_locales = "hi"
    stage = KillSwitchStage()

    killed_ctx = MagicMock(preferred_lang="hi", trace_id="t2", start_time=0.0)
    assert await stage.run(killed_ctx) is not None

    alive_ctx = MagicMock(preferred_lang="en", trace_id="t3", start_time=0.0)
    assert await stage.run(alive_ctx) is None
