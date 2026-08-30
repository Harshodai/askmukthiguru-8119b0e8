"""Redis-backed LLM spend reservation guard for multi-provider workloads (Sarvam & OpenRouter).

Enforces pre-call token and dollar ceilings atomically using Redis Lua scripts.
When an API call completes with actual token/cost telemetry, any excess reservation is refunded.
If daily or monthly ceilings are exceeded, raises LLMBudgetExceeded before making the HTTP call.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

logger = logging.getLogger(__name__)


class LLMBudgetExceeded(RuntimeError):
    """Raised before an LLM call when provider spend ceiling is exhausted."""


class LLMBudgetUnavailable(RuntimeError):
    """Raised when spend enforcement cannot reach Redis in fail-closed mode."""


_RESERVE_SCRIPT = """
local day = tonumber(redis.call('GET', KEYS[1]) or '0')
local month = tonumber(redis.call('GET', KEYS[2]) or '0')
local amount = tonumber(ARGV[1])
local max_day = tonumber(ARGV[2])
local max_month = tonumber(ARGV[3])

if day + amount > max_day or month + amount > max_month then
  return {0, day, month}
end

redis.call('INCRBYFLOAT', KEYS[1], amount)
redis.call('EXPIRE', KEYS[1], ARGV[4])
redis.call('INCRBYFLOAT', KEYS[2], amount)
redis.call('EXPIRE', KEYS[2], ARGV[5])
return {1, day + amount, month + amount}
"""

_REFUND_SCRIPT = """
local amount = tonumber(ARGV[1])
for index = 1, #KEYS do
  local current = tonumber(redis.call('GET', KEYS[index]) or '0')
  redis.call('SET', KEYS[index], math.max(0, current - amount), 'KEEPTTL')
end
return 1
"""


@dataclass
class BudgetReservation:
    guard: LLMBudgetGuard | None
    amount_usd: float = 0.0

    async def settle(self, actual_cost_usd: float | None) -> None:
        """Refund unused known cost; unknown usage retains reserve to prevent unmetered spikes."""
        if self.guard is None or actual_cost_usd is None:
            return
        refund = self.amount_usd - max(0.0, actual_cost_usd)
        if refund > 0:
            await self.guard.refund(refund)


class LLMBudgetGuard:
    def __init__(
        self,
        *,
        provider: str = "default",
        enabled: bool = True,
        redis_url: str = "redis://localhost:6379/0",
        daily_budget_usd: float = 10.0,
        monthly_budget_usd: float = 100.0,
        max_request_cost_usd: float = 0.05,
        fail_closed: bool = False,
    ) -> None:
        self._provider = provider.lower().strip()
        self._enabled = enabled
        self._redis_url = redis_url
        self._daily_budget_usd = float(daily_budget_usd)
        self._monthly_budget_usd = float(monthly_budget_usd)
        self._max_request_cost_usd = float(max_request_cost_usd)
        self._fail_closed = fail_closed
        self._client: Any = None

    @classmethod
    def from_settings(cls, settings: Any, provider: str = "sarvam") -> LLMBudgetGuard:
        enabled_key = f"{provider}_budget_guard_enabled"
        daily_key = f"{provider}_daily_budget_usd"
        monthly_key = f"{provider}_monthly_budget_usd"
        max_cost_key = f"{provider}_max_request_cost_usd"

        return cls(
            provider=provider,
            enabled=bool(getattr(settings, enabled_key, getattr(settings, "llm_budget_guard_enabled", True))),
            redis_url=getattr(settings, "redis_url", "redis://localhost:6379/0"),
            daily_budget_usd=float(getattr(settings, daily_key, 10.0)),
            monthly_budget_usd=float(getattr(settings, monthly_key, 100.0)),
            max_request_cost_usd=float(getattr(settings, max_cost_key, 0.05)),
            fail_closed=bool(getattr(settings, "llm_budget_fail_closed", False)),
        )

    @property
    def enabled(self) -> bool:
        return self._enabled

    async def _redis(self) -> Any:
        if self._client is None:
            import redis.asyncio as aioredis
            self._client = aioredis.from_url(self._redis_url, decode_responses=True)
        return self._client

    def _keys(self, now: datetime | None = None) -> tuple[str, str, int, int]:
        ts = now or datetime.now(UTC)
        day_key = f"budget:{self._provider}:usd:{ts.strftime('%Y-%m-%d')}"
        month_key = f"budget:{self._provider}:usd:{ts.strftime('%Y-%m')}"
        
        # Calculate TTL
        next_day = (ts + timedelta(days=2)).replace(hour=0, minute=0, second=0, microsecond=0)
        day_ttl = max(60, int((next_day - ts).total_seconds()))
        next_month = (ts + timedelta(days=40)).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        month_ttl = max(60, int((next_month - ts).total_seconds()))
        return day_key, month_key, day_ttl, month_ttl

    async def reserve(self, estimated_cost_usd: float | None = None) -> BudgetReservation:
        """Reserve budget ceiling before making an LLM API call."""
        if not self._enabled:
            return BudgetReservation(guard=None, amount_usd=0.0)

        amount = max(0.0, float(estimated_cost_usd if estimated_cost_usd is not None else self._max_request_cost_usd))
        day_key, month_key, day_ttl, month_ttl = self._keys()

        try:
            r = await self._redis()
            res = await r.eval(
                _RESERVE_SCRIPT,
                2,
                day_key,
                month_key,
                str(amount),
                str(self._daily_budget_usd),
                str(self._monthly_budget_usd),
                str(day_ttl),
                str(month_ttl),
            )
            success = bool(res[0])
            day_total = float(res[1])
            month_total = float(res[2])

            if not success:
                logger.error(
                    f"LLM budget ceiling exceeded for provider {self._provider}: "
                    f"attempted={amount:.4f}, day={day_total:.4f}/{self._daily_budget_usd}, "
                    f"month={month_total:.4f}/{self._monthly_budget_usd}"
                )
                raise LLMBudgetExceeded(
                    f"Daily/monthly budget ceiling exceeded for {self._provider} "
                    f"(day={day_total:.2f}/{self._daily_budget_usd}, month={month_total:.2f}/{self._monthly_budget_usd})"
                )

            return BudgetReservation(guard=self, amount_usd=amount)
        except LLMBudgetExceeded:
            raise
        except Exception as exc:
            if self._fail_closed:
                logger.error(f"Budget guard fail-closed triggered for {self._provider}: {exc}")
                raise LLMBudgetUnavailable(f"Redis spend guard unreachable: {exc}") from exc
            logger.warning(f"Budget guard bypassed due to store error: {exc}")
            return BudgetReservation(guard=None, amount_usd=0.0)

    async def refund(self, refund_amount_usd: float) -> None:
        """Refund unused estimated cost when actual response usage is known."""
        if not self._enabled or refund_amount_usd <= 0:
            return
        day_key, month_key, _, _ = self._keys()
        try:
            r = await self._redis()
            await r.eval(_REFUND_SCRIPT, 2, day_key, month_key, str(refund_amount_usd))
        except Exception as exc:
            logger.warning(f"Failed to refund budget for {self._provider}: {exc}")
