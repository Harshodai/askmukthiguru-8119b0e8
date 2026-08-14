"""
Unit 23 — Cost Attribution

Tracks and attributes token usage and compute costs per tenant, user, and session.
Supports self-hosted models (token volume tracking) and cloud APIs (token cost tracking).

Design:
  - CostTracker: singleton that aggregates token/cost metrics
  - Per-tenant and per-user daily/monthly budgets with alerting
  - Supabase backend (single operational DB — no more SQLite data loss)
  - Integrates with compliance logger for GDPR-safe attribution

Cost models:
  - Self-hosted Ollama: Cost = tokens GPU_COMPUTE_RATE (configurable, default: 0)
  - Sarvam Cloud API: Cost = tokens SARVAM_COST_PER_TOKEN (from settings)
  - Krutrim API: Cost = tokens KRUTRIM_COST_PER_TOKEN (from settings)

Schema (Supabase public.token_usage):
  id, tenant_id, user_id, session_id, model, provider,
  tokens_in, tokens_out, cost_usd, endpoint, created_at

Usage:
    from services.cost_tracker import get_cost_tracker

    tracker = get_cost_tracker()
    tracker.record(
        tenant_id="default",
        user_id="user-uuid",
        session_id="sess-123",
        model="gemma3:12b",
        provider="ollama",
        tokens_in=150,
        tokens_out=80,
        endpoint="/api/chat",
    )

    report = tracker.get_usage_report(tenant_id="default", days=30)
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from threading import Lock
from typing import Optional

from app.config import settings

logger = logging.getLogger(__name__)

_COST_RATES: dict[str, float] = {
    "ollama": 0.0,
    "sarvam": 0.002,
    "krutrim": 0.001,
    "openai": 0.002,
}
_COST_QUANT = Decimal("0.00000001")
_MONEY_QUANT = Decimal("0.000001")
_ZERO = Decimal("0")


def _non_negative_int(value: object) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _non_negative_decimal(value: object) -> Decimal:
    try:
        return max(_ZERO, Decimal(str(value or 0)))
    except (InvalidOperation, TypeError, ValueError):
        return _ZERO


def _rounded_float(value: Decimal, quantum: Decimal = _MONEY_QUANT) -> float:
    return float(value.quantize(quantum, rounding=ROUND_HALF_UP))


def _calculate_cost(tokens_in: int, tokens_out: int, provider: str) -> float:
    provider_key = (provider or "").lower()
    rate = _non_negative_decimal(_COST_RATES.get(provider_key, 0.0))
    total_tokens = _non_negative_int(tokens_in) + _non_negative_int(tokens_out)
    return _rounded_float(
        (Decimal(total_tokens) / Decimal(1000)) * rate,
        _COST_QUANT,
    )


def _get_client():
    from app.telemetry_db import _get_client as _supa_client
    return _supa_client()


UTC = UTC

# ponytail: process-local, once-per-hour gate on the budget check so `record()`
# doesn't run an extra Supabase query on every single call. Per-instance only —
# fine for a soft log alert, not a source of truth for enforcement.
_LAST_BUDGET_CHECK: dict[str, float] = {}
_BUDGET_CHECK_INTERVAL_SECONDS = 3600
# Retry a failed usage read after a short cooldown, not on every request.
_BUDGET_FAILURE_RETRY_SECONDS = 1.0
_BUDGET_CHECK_LOCK = Lock()


@dataclass
class UsageReport:
    tenant_id: str
    period_days: int
    total_tokens_in: int
    total_tokens_out: int
    total_tokens: int
    total_cost_usd: float
    unique_users: int
    unique_sessions: int
    by_model: dict[str, dict]
    by_provider: dict[str, dict]


class CostTracker:
    """Supabase-backed token usage and cost attribution tracker."""

    def record(
        self,
        *,
        tenant_id: str = "default",
        user_id: str = "",
        session_id: str = "",
        model: str = "",
        provider: str = "ollama",
        tokens_in: int = 0,
        tokens_out: int = 0,
        endpoint: str = "/api/chat",
        cost_override: Optional[float] = None,
    ) -> None:
        normalized_tenant = tenant_id or "default"
        normalized_tokens_in = _non_negative_int(tokens_in)
        normalized_tokens_out = _non_negative_int(tokens_out)
        if cost_override is None:
            cost = _calculate_cost(normalized_tokens_in, normalized_tokens_out, provider)
        else:
            cost = _rounded_float(_non_negative_decimal(cost_override), _COST_QUANT)

        client = _get_client()
        if not client:
            logger.warning("Supabase client unavailable — skipping cost record")
            return
        try:
            client.table("token_usage").insert({
                "tenant_id": normalized_tenant,
                "user_id": user_id or "",
                "session_id": session_id or "",
                "model": model or "",
                "provider": provider or "ollama",
                "tokens_in": normalized_tokens_in,
                "tokens_out": normalized_tokens_out,
                "cost_usd": cost,
                "endpoint": endpoint or "/api/chat",
            }).execute()
        except Exception as e:
            logger.error(f"Failed to record token usage: {e}")
            return
        self._maybe_check_budget(normalized_tenant)

    def _maybe_check_budget(self, tenant_id: str) -> None:
        tenant_key = tenant_id or "default"
        now = time.monotonic()
        with _BUDGET_CHECK_LOCK:
            last_check = _LAST_BUDGET_CHECK.get(tenant_key)
            if last_check is not None and now - last_check < _BUDGET_CHECK_INTERVAL_SECONDS:
                return
            _LAST_BUDGET_CHECK[tenant_key] = now

        try:
            today = self.get_daily_usage(tenant_key, days=1)
        except Exception as e:
            # Keep a short failure cooldown so a transient outage can recover
            # without turning every request into a Supabase retry storm.
            with _BUDGET_CHECK_LOCK:
                _LAST_BUDGET_CHECK[tenant_key] = (
                    now - _BUDGET_CHECK_INTERVAL_SECONDS + _BUDGET_FAILURE_RETRY_SECONDS
                )
            logger.error(f"Budget check failed to fetch daily usage: {e}")
            return
        if not today:
            return
        today_cost = _non_negative_decimal(today[0].get("cost_usd"))
        projected_monthly = today_cost * 30
        budget = _non_negative_decimal(settings.monthly_cost_budget_usd)
        if projected_monthly > budget:
            logger.warning(
                "Cost budget alert: tenant=%s today=$%.4f projected_monthly=$%.2f "
                "exceeds budget=$%.2f (~₹3,000/month envelope)",
                tenant_key, float(today_cost), float(projected_monthly), float(budget),
            )
            client = _get_client()
            if client:
                try:
                    client.table("alert_events").insert({
                        "value": float(projected_monthly),
                        "message": (
                            f"Cost budget alert: tenant={tenant_key} "
                            f"today=${float(today_cost):.4f} "
                            f"projected_monthly=${float(projected_monthly):.2f} "
                            f"exceeds budget=${float(budget):.2f}"
                        ),
                    }).execute()
                except Exception as e:
                    logger.error(f"Failed to write budget alert to alert_events: {e}")

    def get_usage_report(
        self,
        tenant_id: Optional[str] = None,
        user_id: Optional[str] = None,
        days: int = 30,
    ) -> UsageReport:
        client = _get_client()
        if not client:
            return UsageReport(
                tenant_id=tenant_id or "all", period_days=days,
                total_tokens_in=0, total_tokens_out=0, total_tokens=0,
                total_cost_usd=0.0, unique_users=0, unique_sessions=0,
                by_model={}, by_provider={},
            )

        since = datetime.now(UTC) - __import__("datetime").timedelta(days=days)
        query = client.table("token_usage").select(
            "user_id,session_id,model,provider,tokens_in,tokens_out,cost_usd"
        ).gte("created_at", since.isoformat())
        if tenant_id:
            query = query.eq("tenant_id", tenant_id)
        if user_id:
            query = query.eq("user_id", user_id)

        try:
            rows = query.execute().data or []
        except Exception as e:
            logger.error(f"Failed to fetch usage report: {e}")
            rows = []

        total_in = 0
        total_out = 0
        total_cost = _ZERO
        users: set[object] = set()
        sessions: set[object] = set()
        by_model: dict[str, dict[str, object]] = {}
        by_provider: dict[str, dict[str, object]] = {}

        for row in rows:
            tokens_in = _non_negative_int(row.get("tokens_in"))
            tokens_out = _non_negative_int(row.get("tokens_out"))
            cost = _non_negative_decimal(row.get("cost_usd"))
            total_in += tokens_in
            total_out += tokens_out
            total_cost += cost
            if row.get("user_id"):
                users.add(row["user_id"])
            if row.get("session_id"):
                sessions.add(row["session_id"])

            model = row.get("model") or "unknown"
            provider = row.get("provider") or "unknown"
            for bucket, key in ((by_model, model), (by_provider, provider)):
                if key not in bucket:
                    bucket[key] = {
                        "tokens_in": 0, "tokens_out": 0,
                        "cost_usd": _ZERO, "calls": 0,
                    }
                details = bucket[key]
                details["tokens_in"] += tokens_in
                details["tokens_out"] += tokens_out
                details["cost_usd"] += cost
                details["calls"] += 1

        def finalize(bucket: dict[str, dict[str, object]]) -> dict[str, dict]:
            return {
                key: {
                    "tokens_in": int(value["tokens_in"]),
                    "tokens_out": int(value["tokens_out"]),
                    "cost_usd": _rounded_float(value["cost_usd"]),
                    "calls": int(value["calls"]),
                }
                for key, value in bucket.items()
            }

        return UsageReport(
            tenant_id=tenant_id or "all",
            period_days=days,
            total_tokens_in=total_in,
            total_tokens_out=total_out,
            total_tokens=total_in + total_out,
            total_cost_usd=_rounded_float(total_cost),
            unique_users=len(users),
            unique_sessions=len(sessions),
            by_model=finalize(by_model),
            by_provider=finalize(by_provider),
        )

    def get_daily_usage(self, tenant_id: str, days: int = 7) -> list[dict]:
        client = _get_client()
        if not client:
            return []

        since = datetime.now(UTC) - __import__("datetime").timedelta(days=days)
        try:
            rows = (
                client.table("token_usage")
                .select("created_at,tokens_in,tokens_out,cost_usd")
                .eq("tenant_id", tenant_id)
                .gte("created_at", since.isoformat())
                .execute()
                .data or []
            )
        except Exception as e:
            logger.error(f"Failed to fetch daily usage: {e}")
            return []

        day_buckets: dict[str, dict[str, object]] = {}
        for row in rows:
            raw = row.get("created_at")
            if not raw:
                continue
            day = str(raw)[:10]
            bucket = day_buckets.setdefault(
                day, {"tokens": 0, "cost": _ZERO, "calls": 0}
            )
            bucket["tokens"] += _non_negative_int(row.get("tokens_in"))
            bucket["tokens"] += _non_negative_int(row.get("tokens_out"))
            bucket["cost"] += _non_negative_decimal(row.get("cost_usd"))
            bucket["calls"] += 1

        return [
            {
                "date": day,
                "total_tokens": int(values["tokens"]),
                "cost_usd": _rounded_float(values["cost"]),
                "calls": int(values["calls"]),
            }
            for day, values in sorted(day_buckets.items(), reverse=True)
        ]


# Singleton
_tracker: Optional[CostTracker] = None


def get_cost_tracker() -> CostTracker:
    global _tracker
    if _tracker is None:
        _tracker = CostTracker()
    return _tracker


# Token Accumulator & ContextVar for request-scoped token tracking
from contextvars import ContextVar


@dataclass
class TokenAccumulator:
    tokens_in: int = 0
    tokens_out: int = 0
    model: str = ""
    provider: str = ""
    # Provider-reported cost is kept separate from a model-rate fallback so
    # runtime metrics never label an estimate as actual provider spend.
    cost_usd: float = 0.0
    estimated_cost_usd: float = 0.0


token_accumulator_var: ContextVar[Optional[TokenAccumulator]] = ContextVar("token_accumulator", default=None)
