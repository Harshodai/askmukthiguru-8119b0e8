"""Pins for the startup spend-cap posture line (open-work row T-E2, 2026-11-14).

On 2026-11-13 every first-person turn abstained because the app's own monthly cap (100) was below
its spend ledger (123.13). Nothing said so: the exception text is a provider-style sentence, so it
was read as an empty provider account. `log_budget_headroom` now reads the ledger once at startup
and names the cap and the setting before any user asks a question.

These are pure-function and source-level pins; no Redis instance is contacted.
"""

from __future__ import annotations

import logging
from pathlib import Path
from types import SimpleNamespace

from app.runtime_budget import (
    HEADROOM_WARN_FRACTION,
    budget_cap_warnings,
    log_budget_headroom,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def _settings(**over: object) -> SimpleNamespace:
    base = {
        "openrouter_budget_guard_enabled": True,
        "openrouter_daily_budget_usd": 100.0,
        "openrouter_monthly_budget_usd": 100.0,
        "redis_url": "redis://localhost:6379/0",
    }
    base.update(over)
    return SimpleNamespace(**base)


def test_a_reached_cap_is_reported_as_ours_not_the_provider() -> None:
    warnings = budget_cap_warnings(_settings(), spent_day=0.12, spent_month=123.13)
    assert len(warnings) == 1, warnings
    text = warnings[0]
    assert "model budget cap reached" in text
    assert "OPENROUTER_MONTHLY_BUDGET_USD" in text
    assert "123.13" in text and "100.00" in text
    # The misreading this row exists for: it must say whose limit it is.
    assert "not a provider balance problem" in text


def test_near_cap_is_reported_before_it_refuses() -> None:
    almost = 100.0 * HEADROOM_WARN_FRACTION
    warnings = budget_cap_warnings(
        _settings(openrouter_daily_budget_usd=10.0), spent_day=almost / 10, spent_month=1.0
    )
    assert warnings and "is at 70% of the $10.00 cap" in warnings[0]


def test_a_healthy_ledger_says_nothing() -> None:
    assert budget_cap_warnings(_settings(), spent_day=1.0, spent_month=20.0) == []


def test_an_unreadable_ledger_is_not_a_cap_breach() -> None:
    """`None` means unknown. Reporting it as a breach would be the same class of error as the
    provider-balance misreading, in the opposite direction."""
    assert budget_cap_warnings(_settings(), spent_day=None, spent_month=None) == []


def test_a_disabled_guard_says_nothing() -> None:
    assert (
        budget_cap_warnings(
            _settings(openrouter_budget_guard_enabled=False), spent_day=9e9, spent_month=9e9
        )
        == []
    )


def test_startup_calls_the_headroom_line(caplog) -> None:
    """Both directions: the line exists and is wired into the lifespan."""
    main_src = (REPO_ROOT / "backend" / "app" / "main.py").read_text(encoding="utf-8")
    assert "await log_budget_headroom(logger, settings)" in main_src

    # And it logs at WARNING when the ledger is over the cap (no Redis: stub the read).
    import asyncio

    from app import runtime_budget

    original = runtime_budget.read_spend_ledger

    async def _fake(_settings):  # type: ignore[no-untyped-def]
        return 0.12, 123.13

    runtime_budget.read_spend_ledger = _fake
    try:
        with caplog.at_level(logging.INFO, logger="budget-test"):
            asyncio.run(log_budget_headroom(logging.getLogger("budget-test"), _settings()))
    finally:
        runtime_budget.read_spend_ledger = original
    messages = [(r.levelno, r.getMessage()) for r in caplog.records]
    assert any(lvl == logging.WARNING and "Model budget posture" in msg for lvl, msg in messages)
    assert any("Model budget ledger" in msg for _, msg in messages)


def test_the_reader_uses_the_guards_own_key_derivation() -> None:
    """A reader that invents its own keys can disagree with the writer silently."""
    src = (REPO_ROOT / "backend" / "app" / "runtime_budget.py").read_text(encoding="utf-8")
    assert "OpenRouterBudgetGuard._keys()" in src


def test_the_reader_is_bounded_so_startup_never_hangs_on_redis() -> None:
    """A boot-time report must not inherit the client default of no socket timeout."""
    src = (REPO_ROOT / "backend" / "app" / "runtime_budget.py").read_text(encoding="utf-8")
    assert "socket_connect_timeout=" in src and "socket_timeout=" in src


def test_an_unreachable_ledger_returns_unknown_and_blocks_nothing() -> None:
    import asyncio

    from app.runtime_budget import read_spend_ledger

    async def _run() -> None:
        # Port 1 on loopback: refuses immediately, the shape of a dead Redis.
        day, month = await read_spend_ledger(_settings(redis_url="redis://127.0.0.1:1/0"))
        assert (day, month) == (None, None)

    asyncio.run(_run())
