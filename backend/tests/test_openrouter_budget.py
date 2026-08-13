import pytest

from app.openrouter_budget import (
    OpenRouterBudgetExceeded,
    OpenRouterBudgetGuard,
    OpenRouterBudgetUnavailable,
)


class _Redis:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    async def eval(self, *args):
        self.calls.append(args)
        return self.responses.pop(0)


@pytest.mark.asyncio
async def test_disabled_budget_guard_never_requires_redis():
    guard = OpenRouterBudgetGuard(
        enabled=False,
        redis_url="redis://unused",
        daily_budget_usd=0.25,
        monthly_budget_usd=6.0,
        max_request_cost_usd=0.03,
        fail_closed=True,
    )

    reservation = await guard.reserve()
    assert reservation.guard is None


@pytest.mark.asyncio
async def test_budget_guard_reserves_and_refunds_known_unused_cost():
    guard = OpenRouterBudgetGuard(
        enabled=True,
        redis_url="redis://unused",
        daily_budget_usd=0.25,
        monthly_budget_usd=6.0,
        max_request_cost_usd=0.03,
        fail_closed=True,
    )
    fake = _Redis([[1, 0.03, 0.03], 1])
    guard._client = fake

    reservation = await guard.reserve()
    await reservation.settle(0.01)

    assert reservation.amount_usd == pytest.approx(0.03)
    assert len(fake.calls) == 2
    assert fake.calls[1][-1] == pytest.approx(0.02)


@pytest.mark.asyncio
async def test_budget_guard_rejects_when_ledger_denies_reservation():
    guard = OpenRouterBudgetGuard(
        enabled=True,
        redis_url="redis://unused",
        daily_budget_usd=0.25,
        monthly_budget_usd=6.0,
        max_request_cost_usd=0.03,
        fail_closed=True,
    )
    guard._client = _Redis([[0, 0.25, 1.50]])

    with pytest.raises(OpenRouterBudgetExceeded):
        await guard.reserve()


@pytest.mark.asyncio
async def test_budget_guard_fails_closed_when_shared_ledger_is_unavailable():
    guard = OpenRouterBudgetGuard(
        enabled=True,
        redis_url="redis://unused",
        daily_budget_usd=0.25,
        monthly_budget_usd=6.0,
        max_request_cost_usd=0.03,
        fail_closed=True,
    )

    class _BrokenRedis:
        async def eval(self, *args):
            raise ConnectionError("redis unavailable")

    guard._client = _BrokenRedis()
    with pytest.raises(OpenRouterBudgetUnavailable):
        await guard.reserve()
