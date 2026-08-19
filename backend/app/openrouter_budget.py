"""Redis-backed OpenRouter spend reservation guard.

Reservations intentionally use a conservative per-call ceiling. When OpenRouter
returns an actual cost, unused reservation is atomically refunded. Missing usage
keeps the reservation so unavailable accounting never turns into uncapped spend.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any


class OpenRouterBudgetExceeded(RuntimeError):
    """Raised before an LLM call when the controlled spend envelope is exhausted."""


class OpenRouterBudgetUnavailable(RuntimeError):
    """Raised when enabled spend enforcement cannot reach its shared store."""


_RESERVE = """
local day = tonumber(redis.call('GET', KEYS[1]) or '0')
local month = tonumber(redis.call('GET', KEYS[2]) or '0')
local amount = tonumber(ARGV[1])
if day + amount > tonumber(ARGV[2]) or month + amount > tonumber(ARGV[3]) then
  return {0, day, month}
end
redis.call('INCRBYFLOAT', KEYS[1], amount)
redis.call('EXPIRE', KEYS[1], ARGV[4])
redis.call('INCRBYFLOAT', KEYS[2], amount)
redis.call('EXPIRE', KEYS[2], ARGV[5])
return {1, day + amount, month + amount}
"""

_REFUND = """
local amount = tonumber(ARGV[1])
for index = 1, #KEYS do
  local current = tonumber(redis.call('GET', KEYS[index]) or '0')
  redis.call('SET', KEYS[index], math.max(0, current - amount), 'KEEPTTL')
end
return 1
"""


@dataclass
class BudgetReservation:
    guard: OpenRouterBudgetGuard | None
    amount_usd: float = 0.0

    async def settle(self, actual_cost_usd: float | None) -> None:
        """Refund unused known cost; unknown usage deliberately retains reserve."""
        if self.guard is None or actual_cost_usd is None:
            return
        refund = self.amount_usd - max(0.0, actual_cost_usd)
        if refund > 0:
            await self.guard.refund(refund)


class OpenRouterBudgetGuard:
    def __init__(
        self,
        *,
        enabled: bool,
        redis_url: str,
        daily_budget_usd: float,
        monthly_budget_usd: float,
        max_request_cost_usd: float,
        fail_closed: bool,
    ) -> None:
        self._enabled = enabled
        self._redis_url = redis_url
        self._daily_budget_usd = daily_budget_usd
        self._monthly_budget_usd = monthly_budget_usd
        self._max_request_cost_usd = max_request_cost_usd
        self._fail_closed = fail_closed
        self._client: Any = None

    @classmethod
    def from_settings(cls, settings: Any, policy: Any) -> OpenRouterBudgetGuard:
        return cls(
            enabled=bool(getattr(settings, "openrouter_budget_guard_enabled", False)),
            redis_url=settings.redis_url,
            daily_budget_usd=policy.daily_budget_usd,
            monthly_budget_usd=policy.monthly_budget_usd,
            max_request_cost_usd=float(getattr(settings, "openrouter_max_request_cost_usd", 0.03)),
            fail_closed=bool(getattr(settings, "openrouter_budget_fail_closed", True)),
        )

    @property
    def enabled(self) -> bool:
        return self._enabled

    async def _redis(self) -> Any:
        if self._client is None:
            import redis.asyncio as aioredis

            self._client = aioredis.from_url(self._redis_url, decode_responses=True)
        return self._client

    @staticmethod
    def _keys(now: datetime | None = None) -> tuple[str, str, int, int]:
        current = now or datetime.now(UTC)
        next_day = (current + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        if current.month == 12:
            next_month = current.replace(
                year=current.year + 1, month=1, day=1, hour=0, minute=0, second=0, microsecond=0
            )
        else:
            next_month = current.replace(
                month=current.month + 1, day=1, hour=0, minute=0, second=0, microsecond=0
            )
        day_key = f"askmukthiguru:openrouter-spend:day:{current:%Y-%m-%d}"
        month_key = f"askmukthiguru:openrouter-spend:month:{current:%Y-%m}"
        return (
            day_key,
            month_key,
            max(1, int((next_day - current).total_seconds())),
            max(1, int((next_month - current).total_seconds())),
        )

    async def reserve(self) -> BudgetReservation:
        if not self._enabled:
            return BudgetReservation(None)
        day_key, month_key, day_ttl, month_ttl = self._keys()
        try:
            client = await self._redis()
            result = await client.eval(
                _RESERVE,
                2,
                day_key,
                month_key,
                self._max_request_cost_usd,
                self._daily_budget_usd,
                self._monthly_budget_usd,
                day_ttl,
                month_ttl,
            )
        except Exception as exc:
            if self._fail_closed:
                raise OpenRouterBudgetUnavailable("OpenRouter budget ledger unavailable") from exc
            return BudgetReservation(None)
        if not result or int(result[0]) != 1:
            raise OpenRouterBudgetExceeded("OpenRouter daily or monthly spend limit reached")
        return BudgetReservation(self, self._max_request_cost_usd)

    async def refund(self, amount_usd: float) -> None:
        if not self._enabled or amount_usd <= 0:
            return
        day_key, month_key, _, _ = self._keys()
        try:
            client = await self._redis()
            await client.eval(_REFUND, 2, day_key, month_key, amount_usd)
        except Exception:
            # A failed refund remains conservative; the next request cannot bypass the cap.
            return
