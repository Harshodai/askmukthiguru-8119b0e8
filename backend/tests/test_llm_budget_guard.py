import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from services.llm_budget_guard import LLMBudgetGuard, LLMBudgetExceeded


@pytest.mark.asyncio
async def test_llm_budget_guard_exceeded_blocks_call():
    """Verify that exceeding daily/monthly budget raises LLMBudgetExceeded and blocks HTTP call."""
    guard = LLMBudgetGuard(
        provider="sarvam",
        enabled=True,
        redis_url="redis://localhost:6379/0",
        daily_budget_usd=1.0,
        monthly_budget_usd=10.0,
        max_request_cost_usd=0.05,
    )

    # Mock Redis eval returning {0, current_day_spend, current_month_spend} (ceiling hit)
    mock_redis = MagicMock()
    mock_redis.eval = AsyncMock(return_value=[0, 1.20, 5.00])
    guard._client = mock_redis

    with pytest.raises(LLMBudgetExceeded) as exc_info:
        await guard.reserve()

    assert "budget ceiling exceeded" in str(exc_info.value).lower()
    assert "sarvam" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_llm_budget_guard_settle_refund():
    """Verify that unused estimated cost is refunded atomically."""
    guard = LLMBudgetGuard(
        provider="sarvam",
        enabled=True,
        redis_url="redis://localhost:6379/0",
        daily_budget_usd=10.0,
        monthly_budget_usd=100.0,
        max_request_cost_usd=0.05,
    )

    mock_redis = MagicMock()
    mock_redis.eval = AsyncMock(return_value=[1, 0.05, 0.05])
    guard._client = mock_redis

    reservation = await guard.reserve(estimated_cost_usd=0.05)
    assert reservation.amount_usd == 0.05

    # Actual cost was $0.01 -> refund should be $0.04
    await reservation.settle(actual_cost_usd=0.01)
    
    assert mock_redis.eval.called
    refund_args = mock_redis.eval.call_args[0]
    assert float(refund_args[4]) == pytest.approx(0.04)
