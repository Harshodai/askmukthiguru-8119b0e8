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


class _BrokenRedis:
    async def eval(self, *args):
        raise ConnectionError("redis unavailable")


def _guard(daily=10.0, monthly=100.0, fail_closed=True):
    return OpenRouterBudgetGuard(
        enabled=True,
        redis_url="redis://unused",
        daily_budget_usd=daily,
        monthly_budget_usd=monthly,
        max_request_cost_usd=0.03,
        fail_closed=fail_closed,
    )


@pytest.mark.asyncio
async def test_redis_down_degrades_to_capped_in_process_ledger():
    guard = _guard()
    guard._client = _BrokenRedis()
    reservation = await guard.reserve()
    assert reservation.local is True and reservation.amount_usd == pytest.approx(0.03)
    await reservation.settle(0.01)  # known cost refunds the local ledger
    assert max(guard._local_spend.values()) == pytest.approx(0.01)


@pytest.mark.asyncio
async def test_redis_down_never_fails_open_past_the_fallback_cap():
    # 10% of $0.30/day = $0.03: exactly one reservation, then refuse.
    guard = _guard(daily=0.30, monthly=6.0)
    guard._client = _BrokenRedis()
    await guard.reserve()
    with pytest.raises(OpenRouterBudgetUnavailable):
        await guard.reserve()


@pytest.mark.asyncio
async def test_small_budget_refuses_when_fallback_cap_is_below_one_call():
    guard = _guard(daily=0.25, monthly=6.0)
    guard._client = _BrokenRedis()
    with pytest.raises(OpenRouterBudgetUnavailable):
        await guard.reserve()


@pytest.mark.asyncio
async def test_redis_up_uses_shared_ledger_not_local():
    guard = _guard()
    guard._client = _Redis([[1, 0.03, 0.03]])
    reservation = await guard.reserve()
    assert reservation.local is False and guard._local_spend == {}


@pytest.mark.asyncio
async def test_redis_recovery_returns_to_shared_ledger():
    guard = _guard()
    guard._client = _BrokenRedis()
    assert (await guard.reserve()).local is True
    guard._client = _Redis([[1, 0.03, 0.03]])
    assert (await guard.reserve()).local is False


@pytest.mark.asyncio
async def test_fail_open_mode_is_unchanged_when_redis_down():
    guard = _guard(fail_closed=False)
    guard._client = _BrokenRedis()
    assert (await guard.reserve()).guard is None
