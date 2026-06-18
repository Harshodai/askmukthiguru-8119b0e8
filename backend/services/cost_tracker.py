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
from datetime import datetime, timezone
from typing import Optional

from app.config import get_settings

logger = logging.getLogger(__name__)

_COST_RATES: dict[str, float] = {
    "ollama": 0.0,
    "sarvam": 0.002,
    "krutrim": 0.001,
    "openai": 0.002,
}


def _calculate_cost(tokens_in: int, tokens_out: int, provider: str) -> float:
    rate = _COST_RATES.get(provider.lower(), 0.0)
    total_tokens = tokens_in + tokens_out
    return round((total_tokens / 1000) * rate, 8)


def _get_client():
    from app.telemetry_db import _get_client as _supa_client
    return _supa_client()


UTC = timezone.utc


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
        cost = cost_override if cost_override is not None else _calculate_cost(
            tokens_in, tokens_out, provider
        )
        client = _get_client()
        if not client:
            logger.warning("Supabase client unavailable — skipping cost record")
            return
        try:
            client.table("token_usage").insert({
                "tenant_id": tenant_id,
                "user_id": user_id,
                "session_id": session_id,
                "model": model,
                "provider": provider,
                "tokens_in": tokens_in,
                "tokens_out": tokens_out,
                "cost_usd": cost,
                "endpoint": endpoint,
            }).execute()
        except Exception as e:
            logger.error(f"Failed to record token usage: {e}")

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

        query = client.table("token_usage").select("*")
        query = query.gte("created_at", since.isoformat())
        if tenant_id:
            query = query.eq("tenant_id", tenant_id)
        if user_id:
            query = query.eq("user_id", user_id)

        try:
            rows = query.execute().data or []
        except Exception as e:
            logger.error(f"Failed to fetch usage report: {e}")
            rows = []

        total_in = sum(r.get("tokens_in", 0) or 0 for r in rows)
        total_out = sum(r.get("tokens_out", 0) or 0 for r in rows)
        total_cost = sum(float(r.get("cost_usd", 0) or 0) for r in rows)
        unique_users = len({r["user_id"] for r in rows if r.get("user_id")})
        unique_sessions = len({r["session_id"] for r in rows if r.get("session_id")})

        by_model: dict[str, dict] = {}
        for r in rows:
            m = r.get("model", "unknown")
            if m not in by_model:
                by_model[m] = {"tokens_in": 0, "tokens_out": 0, "cost_usd": 0.0, "calls": 0}
            by_model[m]["tokens_in"] += r.get("tokens_in", 0) or 0
            by_model[m]["tokens_out"] += r.get("tokens_out", 0) or 0
            by_model[m]["cost_usd"] += float(r.get("cost_usd", 0) or 0)
            by_model[m]["calls"] += 1

        by_provider: dict[str, dict] = {}
        for r in rows:
            p = r.get("provider", "unknown")
            if p not in by_provider:
                by_provider[p] = {"tokens_in": 0, "tokens_out": 0, "cost_usd": 0.0, "calls": 0}
            by_provider[p]["tokens_in"] += r.get("tokens_in", 0) or 0
            by_provider[p]["tokens_out"] += r.get("tokens_out", 0) or 0
            by_provider[p]["cost_usd"] += float(r.get("cost_usd", 0) or 0)
            by_provider[p]["calls"] += 1

        return UsageReport(
            tenant_id=tenant_id or "all",
            period_days=days,
            total_tokens_in=total_in,
            total_tokens_out=total_out,
            total_tokens=total_in + total_out,
            total_cost_usd=round(total_cost, 6),
            unique_users=unique_users,
            unique_sessions=unique_sessions,
            by_model=by_model,
            by_provider=by_provider,
        )

    def get_daily_usage(self, tenant_id: str, days: int = 7) -> list[dict]:
        client = _get_client()
        if not client:
            return []

        since = datetime.now(UTC) - __import__("datetime").timedelta(days=days)
        try:
            rows = (
                client.table("token_usage")
                .select("*")
                .eq("tenant_id", tenant_id)
                .gte("created_at", since.isoformat())
                .execute()
                .data or []
            )
        except Exception as e:
            logger.error(f"Failed to fetch daily usage: {e}")
            return []

        day_buckets: dict[str, dict] = {}
        for r in rows:
            raw = r.get("created_at")
            if not raw:
                continue
            day = raw[:10]
            if day not in day_buckets:
                day_buckets[day] = {"tokens": 0, "cost": 0.0, "calls": 0}
            day_buckets[day]["tokens"] += (r.get("tokens_in", 0) or 0) + (r.get("tokens_out", 0) or 0)
            day_buckets[day]["cost"] += float(r.get("cost_usd", 0) or 0)
            day_buckets[day]["calls"] += 1

        result = []
        for day, vals in sorted(day_buckets.items(), reverse=True):
            result.append({
                "date": day,
                "total_tokens": vals["tokens"],
                "cost_usd": round(vals["cost"], 6),
                "calls": vals["calls"],
            })
        return result


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

token_accumulator_var: ContextVar[Optional[TokenAccumulator]] = ContextVar("token_accumulator", default=None)
