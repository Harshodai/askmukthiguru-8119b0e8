"""NEW-OPS-8 / NEW-LOAD-4 (SYS-014): make the spend guard's cost visible.

When the provider does not report `usage.cost`, each call keeps the full
reservation (default $0.03). The default $10 daily cap then allows about 111
full-path requests a day. These tests pin the two signals that show it:

- `guru_budget_denied_total{reason}`: a call refused before it was sent.
- `guru_budget_reservation_kept_usd_total{reason}`: dollars held against the cap
  because no cost was reported, or the request was sent and no reply arrived.
"""

from __future__ import annotations

import logging

import pytest

from app.metrics import BUDGET_DENIED_TOTAL, BUDGET_RESERVATION_KEPT_USD_TOTAL
from app.openrouter_budget import (
    OpenRouterBudgetExceeded,
    OpenRouterBudgetGuard,
    OpenRouterBudgetUnavailable,
)


class _Redis:
    def __init__(self, responses=None, raises=None):
        self.responses = list(responses or [])
        self.raises = raises

    async def eval(self, *args):
        if self.raises:
            raise self.raises
        return self.responses.pop(0)


def _guard(**kw):
    values = dict(
        enabled=True,
        redis_url="redis://unused",
        daily_budget_usd=10.0,
        monthly_budget_usd=40.0,
        max_request_cost_usd=0.03,
        fail_closed=True,
    )
    values.update(kw)
    return OpenRouterBudgetGuard(**values)


def _val(counter, **labels):
    return counter.labels(**labels)._value.get()


@pytest.mark.asyncio
async def test_limit_denial_is_counted():
    guard = _guard()
    guard._client = _Redis([[0, 10.0, 12.0]])
    before = _val(BUDGET_DENIED_TOTAL, reason="limit")
    with pytest.raises(OpenRouterBudgetExceeded):
        await guard.reserve()
    assert _val(BUDGET_DENIED_TOTAL, reason="limit") == before + 1


@pytest.mark.asyncio
async def test_ledger_unavailable_denial_is_counted():
    guard = _guard(daily_budget_usd=0.2, monthly_budget_usd=0.2)  # fallback cap 0.02 < 0.03
    guard._client = _Redis(raises=ConnectionError("redis down"))
    before = _val(BUDGET_DENIED_TOTAL, reason="ledger_unavailable")
    with pytest.raises(OpenRouterBudgetUnavailable):
        await guard.reserve()
    assert _val(BUDGET_DENIED_TOTAL, reason="ledger_unavailable") == before + 1


@pytest.mark.asyncio
async def test_unreported_cost_keeps_reservation_and_is_logged(caplog):
    guard = _guard()
    guard._client = _Redis([[1, 0.03, 0.03]])
    reservation = await guard.reserve()
    before = _val(BUDGET_RESERVATION_KEPT_USD_TOTAL, reason="cost_unreported")
    with caplog.at_level(logging.INFO, logger="app.openrouter_budget"):
        await reservation.settle(None)
    assert _val(BUDGET_RESERVATION_KEPT_USD_TOTAL, reason="cost_unreported") == pytest.approx(
        before + 0.03
    )
    assert any("unreported" in r.getMessage().lower() for r in caplog.records)


@pytest.mark.asyncio
async def test_reported_cost_does_not_count_as_kept():
    guard = _guard()
    guard._client = _Redis([[1, 0.03, 0.03], 1])
    reservation = await guard.reserve()
    before = _val(BUDGET_RESERVATION_KEPT_USD_TOTAL, reason="cost_unreported")
    await reservation.settle(0.01)
    assert _val(BUDGET_RESERVATION_KEPT_USD_TOTAL, reason="cost_unreported") == before


@pytest.mark.asyncio
async def test_sent_without_reply_keeps_reservation_and_is_counted():
    guard = _guard()
    guard._client = _Redis([[1, 0.03, 0.03]])
    reservation = await guard.reserve()
    before = _val(BUDGET_RESERVATION_KEPT_USD_TOTAL, reason="no_response")
    await reservation.finalize(request_sent=True, response_arrived=False)
    assert _val(BUDGET_RESERVATION_KEPT_USD_TOTAL, reason="no_response") == pytest.approx(
        before + 0.03
    )


@pytest.mark.asyncio
async def test_never_sent_is_refunded_and_not_counted_as_kept():
    guard = _guard()
    guard._client = _Redis([[1, 0.03, 0.03], 1])
    reservation = await guard.reserve()
    before_a = _val(BUDGET_RESERVATION_KEPT_USD_TOTAL, reason="no_response")
    before_b = _val(BUDGET_RESERVATION_KEPT_USD_TOTAL, reason="cost_unreported")
    await reservation.finalize(request_sent=False)
    assert _val(BUDGET_RESERVATION_KEPT_USD_TOTAL, reason="no_response") == before_a
    assert _val(BUDGET_RESERVATION_KEPT_USD_TOTAL, reason="cost_unreported") == before_b


def test_daily_cap_headroom_is_stated_once():
    """SYS-014: $10 / $0.03 = 333 calls, about 111 full-path requests (3 calls each)."""
    from app.config import Settings

    daily = Settings.model_fields["openrouter_daily_budget_usd"].default
    reserve = Settings.model_fields["openrouter_max_request_cost_usd"].default
    assert daily == 10.0 and reserve == 0.03
    assert int(daily / reserve) == 333
