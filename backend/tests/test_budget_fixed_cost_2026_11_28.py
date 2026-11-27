"""Fixed per-call cost for providers that report no usage.cost (2026-11-28).

None (default, OpenRouter) keeps the reservation when cost is unreported; a declared
fixed cost settles at that cost; 0.0 (self-hosted) never touches the shared ledger.
"""

from __future__ import annotations

import pytest

from app.openrouter_budget import OpenRouterBudgetGuard


class _Redis:
    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []

    async def eval(self, *args):
        self.calls.append(args)
        return self.replies.pop(0)


def _guard(fixed=None, **over):
    values = dict(
        enabled=True,
        redis_url="redis://unused",
        daily_budget_usd=10.0,
        monthly_budget_usd=40.0,
        max_request_cost_usd=0.03,
        fail_closed=True,
        fixed_cost_usd=fixed,
    )
    values.update(over)
    return OpenRouterBudgetGuard(**values)


@pytest.mark.asyncio
async def test_default_unreported_cost_keeps_full_reservation():
    guard = _guard()
    guard._client = _Redis([[1, 0.03, 0.03]])
    res = await guard.reserve()
    await res.settle(None)
    assert res.amount_usd == pytest.approx(0.03)
    assert len(guard._client.calls) == 1  # no refund


@pytest.mark.asyncio
async def test_default_finalize_with_response_but_no_cost_keeps_reservation():
    guard = _guard()
    guard._client = _Redis([[1, 0.03, 0.03]])
    res = await guard.reserve()
    await res.finalize(request_sent=True, response_arrived=True, response_cost_usd=None)
    assert len(guard._client.calls) == 1


@pytest.mark.asyncio
async def test_free_provider_never_touches_the_ledger():
    guard = _guard(fixed=0.0)
    guard._client = _Redis([])  # any eval would pop from an empty list and fail
    res = await guard.reserve()
    await res.finalize(request_sent=True, response_arrived=True, response_cost_usd=None)
    assert res.guard is None
    assert guard._client.calls == []


@pytest.mark.asyncio
async def test_free_provider_reserve_survives_exhausted_ledger_and_down_redis():
    guard = _guard(fixed=0.0)

    class _Down:
        async def eval(self, *a):
            raise OSError("redis down")

    guard._client = _Down()
    assert (await guard.reserve()).guard is None


@pytest.mark.asyncio
async def test_metered_provider_reserves_and_settles_at_declared_cost():
    guard = _guard(fixed=0.002)
    guard._client = _Redis([[1, 0.002, 0.002]])
    res = await guard.reserve()
    assert res.amount_usd == pytest.approx(0.002)
    assert guard._client.calls[0][4] == 0.002  # amount sent to the reserve script
    await res.finalize(request_sent=True, response_arrived=True, response_cost_usd=None)
    assert len(guard._client.calls) == 1  # reserved == declared: nothing to refund
    assert res.settled is True


@pytest.mark.asyncio
async def test_reported_cost_still_wins_over_declared_cost():
    guard = _guard(fixed=0.01)
    guard._client = _Redis([[1, 0.01, 0.01], 1])
    res = await guard.reserve()
    await res.settle(0.004)
    assert guard._client.calls[1][-1] == pytest.approx(0.006)


def test_negative_fixed_cost_is_rejected():
    with pytest.raises(ValueError):
        _guard(fixed=-0.1)


def test_from_settings_defaults_to_no_fixed_cost():
    from types import SimpleNamespace

    settings = SimpleNamespace(redis_url="redis://x")
    policy = SimpleNamespace(daily_budget_usd=10.0, monthly_budget_usd=40.0)
    assert OpenRouterBudgetGuard.from_settings(settings, policy).fixed_cost_usd is None
    assert (
        OpenRouterBudgetGuard.from_settings(settings, policy, fixed_cost_usd=0.0).fixed_cost_usd
        == 0.0
    )
