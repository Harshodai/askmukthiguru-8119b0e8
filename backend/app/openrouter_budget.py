"""Redis-backed OpenRouter spend reservation guard.

Reservations intentionally use a conservative per-call ceiling. When OpenRouter
returns an actual cost, unused reservation is atomically refunded. Missing usage
keeps the reservation so unavailable accounting never turns into uncapped spend.

A provider that never reports cost (a self-hosted OpenAI-compatible endpoint) can
declare ``fixed_cost_usd`` instead (2026-11-28): the guard then reserves and settles
at that amount, so a free endpoint (0.0) never moves the shared spend ledger and a
metered one is billed its declared price. ``None`` (the default, and what OpenRouter
uses) keeps the behaviour above unchanged.

When Redis is unreachable and ``fail_closed`` is set, reservations fall back to an
in-process ledger capped at ``LOCAL_FALLBACK_FRACTION`` of the daily and monthly
budgets, instead of refusing every call. Spend stays capped, never open.
ponytail: the cap is per process, so N replicas can spend N x 10% while Redis is
down; a shared fallback store is the upgrade if that ceiling matters.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from app.metrics import BUDGET_DENIED_TOTAL, BUDGET_RESERVATION_KEPT_USD_TOTAL

logger = logging.getLogger(__name__)

LOCAL_FALLBACK_FRACTION = 0.1


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
    local: bool = False
    settled: bool = False

    async def finalize(
        self,
        *,
        request_sent: bool,
        response_arrived: bool = False,
        response_cost_usd: float | None = None,
    ) -> None:
        """Settle a reservation no success path settled, by what actually happened.

        Never sent (cancelled before the POST, or a failure before it): refund in full.
        A response arrived: settle at the cost it reported, if it reported one.
        Sent but no response (timeout, cancel mid-flight): keep the reservation, because
        the provider may still bill the call.
        Cancelled and failed calls used to keep the full reservation (about $0.03 each), which
        over-counted and exhausted the daily cap mid-run (2026-10-31).
        """
        if self.settled:
            return
        if not request_sent:
            await self.settle(0.0)
        elif response_arrived and (
            response_cost_usd is not None or self._declared_cost() is not None
        ):
            await self.settle(response_cost_usd)
        else:
            self.settled = True
            if response_arrived:
                self._note_kept("cost_unreported")
            else:
                self._note_kept("no_response")

    def _note_kept(self, reason: str) -> None:
        """SYS-014: count and log a reservation that stays against the cap."""
        if self.guard is None or self.amount_usd <= 0:
            return
        try:
            BUDGET_RESERVATION_KEPT_USD_TOTAL.labels(reason=reason).inc(self.amount_usd)
            logger.info(
                "OpenRouter reservation kept (%s): $%.4f stays against the daily and "
                "monthly caps because no actual cost was reported",
                reason,
                self.amount_usd,
            )
        except (
            ValueError,
            KeyError,
            TypeError,
        ):  # pragma: no cover - a metric must not break a call
            logger.debug("budget kept-reservation metric failed", exc_info=True)

    def _declared_cost(self) -> float | None:
        return None if self.guard is None else getattr(self.guard, "fixed_cost_usd", None)

    async def settle(self, actual_cost_usd: float | None) -> None:
        """Refund unused known cost; unknown usage retains reserve unless the guard
        declares a fixed per-call cost (then that cost is the actual)."""
        self.settled = True
        if self.guard is None:
            return
        if actual_cost_usd is None:
            actual_cost_usd = self._declared_cost()
        if actual_cost_usd is None:
            self._note_kept("cost_unreported")
            return
        refund = self.amount_usd - max(0.0, actual_cost_usd)
        if refund > 0:
            if self.local:
                self.guard.refund_local(refund)
            else:
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
        fixed_cost_usd: float | None = None,
    ) -> None:
        self._enabled = enabled
        self._redis_url = redis_url
        self._daily_budget_usd = daily_budget_usd
        self._monthly_budget_usd = monthly_budget_usd
        self._max_request_cost_usd = max_request_cost_usd
        self._fail_closed = fail_closed
        if fixed_cost_usd is not None and fixed_cost_usd < 0:
            raise ValueError("fixed_cost_usd must be >= 0 or None")
        self.fixed_cost_usd = fixed_cost_usd
        self._client: Any = None
        self._local_spend: dict[str, float] = {}

    @classmethod
    def from_settings(
        cls, settings: Any, policy: Any, *, fixed_cost_usd: float | None = None
    ) -> OpenRouterBudgetGuard:
        return cls(
            fixed_cost_usd=fixed_cost_usd,
            enabled=bool(getattr(settings, "openrouter_budget_guard_enabled", False)),
            redis_url=settings.redis_url,
            daily_budget_usd=policy.daily_budget_usd,
            monthly_budget_usd=policy.monthly_budget_usd,
            max_request_cost_usd=float(getattr(settings, "openrouter_max_request_cost_usd", 0.03)),
            fail_closed=True,
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

    def _amount(self) -> float:
        """Per-call reservation: the declared fixed cost, else the conservative ceiling."""
        return self._max_request_cost_usd if self.fixed_cost_usd is None else self.fixed_cost_usd

    async def reserve(self) -> BudgetReservation:
        if not self._enabled:
            return BudgetReservation(None)
        if self.fixed_cost_usd == 0.0:
            # Declared free (self-hosted): nothing to reserve, so the shared ledger,
            # Redis and the local fallback are never touched.
            return BudgetReservation(None)
        day_key, month_key, day_ttl, month_ttl = self._keys()
        try:
            client = await self._redis()
            result = await client.eval(
                _RESERVE,
                2,
                day_key,
                month_key,
                self._amount(),
                self._daily_budget_usd,
                self._monthly_budget_usd,
                day_ttl,
                month_ttl,
            )
        except Exception as exc:
            if self._fail_closed:
                return self._reserve_local(day_key, month_key, exc)
            return BudgetReservation(None)
        if not result or int(result[0]) != 1:
            BUDGET_DENIED_TOTAL.labels(reason="limit").inc()
            raise OpenRouterBudgetExceeded("OpenRouter daily or monthly spend limit reached")
        return BudgetReservation(self, self._amount())

    def _reserve_local(self, day_key: str, month_key: str, cause: Exception) -> BudgetReservation:
        """Reserve against the in-process ledger at a fraction of the real caps."""
        amount = self._amount()
        day = self._local_spend.get(day_key, 0.0)
        month = self._local_spend.get(month_key, 0.0)
        if (
            day + amount > self._daily_budget_usd * LOCAL_FALLBACK_FRACTION
            or month + amount > self._monthly_budget_usd * LOCAL_FALLBACK_FRACTION
        ):
            BUDGET_DENIED_TOTAL.labels(reason="ledger_unavailable").inc()
            raise OpenRouterBudgetUnavailable(
                "OpenRouter budget ledger unavailable and in-process fallback cap reached"
            ) from cause
        # Only the current day/month keys matter; older ones are dropped here.
        self._local_spend = {day_key: day + amount, month_key: month + amount}
        return BudgetReservation(self, amount, local=True)

    def refund_local(self, amount_usd: float) -> None:
        for key, spent in self._local_spend.items():
            self._local_spend[key] = max(0.0, spent - amount_usd)

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
