"""
Unit 23 — Cost Attribution

Tracks and attributes token usage and compute costs per tenant, user, and session.
Supports self-hosted models (token volume tracking) and cloud APIs (token cost tracking).

Design:
  - ``CostTracker``: singleton that aggregates token/cost metrics
  - Per-tenant and per-user daily/monthly budgets with alerting
  - SQLite backend (same pattern as PromptStore — no extra infra)
  - Integrates with compliance logger for GDPR-safe attribution

Cost models:
  - Self-hosted Ollama: Cost = tokens × GPU_COMPUTE_RATE (configurable, default: 0)
    (Token volume tracking only, no real cost for self-hosted)
  - Sarvam Cloud API: Cost = tokens × SARVAM_COST_PER_TOKEN (from settings)
  - Krutrim API: Cost = tokens × KRUTRIM_COST_PER_TOKEN (from settings)

Schema::

  token_usage(
    id, tenant_id, user_id, session_id, model, provider,
    tokens_in, tokens_out, cost_usd, created_at, endpoint
  )

Usage::

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

    # Get usage report
    report = tracker.get_usage_report(tenant_id="default", days=30)
"""

from __future__ import annotations

import logging
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_DB_PATH = Path("data/cost_tracking.db")
_SCHEMA = """
CREATE TABLE IF NOT EXISTS token_usage (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id   TEXT    NOT NULL DEFAULT 'default',
    user_id     TEXT    NOT NULL DEFAULT '',
    session_id  TEXT    NOT NULL DEFAULT '',
    model       TEXT    NOT NULL DEFAULT '',
    provider    TEXT    NOT NULL DEFAULT 'ollama',
    tokens_in   INTEGER NOT NULL DEFAULT 0,
    tokens_out  INTEGER NOT NULL DEFAULT 0,
    cost_usd    REAL    NOT NULL DEFAULT 0.0,
    created_at  REAL    NOT NULL,
    endpoint    TEXT    DEFAULT '/api/chat'
);
CREATE INDEX IF NOT EXISTS idx_usage_tenant ON token_usage(tenant_id, created_at);
CREATE INDEX IF NOT EXISTS idx_usage_user ON token_usage(user_id, created_at);
"""

# Default cost rates (USD per 1000 tokens)
_COST_RATES: dict[str, float] = {
    "ollama": 0.0,        # Self-hosted: no direct cost
    "sarvam": 0.002,      # $0.002 per 1k tokens (estimate)
    "krutrim": 0.001,     # $0.001 per 1k tokens (estimate)
    "openai": 0.002,      # Fallback generic rate
}


def _calculate_cost(tokens_in: int, tokens_out: int, provider: str) -> float:
    """Calculate cost in USD based on provider and token counts."""
    rate = _COST_RATES.get(provider.lower(), 0.0)
    total_tokens = tokens_in + tokens_out
    return round((total_tokens / 1000) * rate, 8)


@dataclass
class UsageReport:
    """Aggregated usage report for a tenant or user."""

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
    """SQLite-backed token usage and cost attribution tracker.

    Thread-safe: WAL mode + one connection per operation.
    """

    def __init__(self, db_path: Path = _DB_PATH) -> None:
        self._db_path = db_path
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _init_db(self) -> None:
        with self._conn() as conn:
            conn.executescript(_SCHEMA)

    # ---- Recording ----

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
        """Record a token usage event.

        Args:
            tenant_id: Tenant for multi-tenant attribution.
            user_id: Authenticated user UUID.
            session_id: Request session ID.
            model: Model name (e.g., "gemma3:12b").
            provider: Provider name ("ollama", "sarvam", "krutrim").
            tokens_in: Input/prompt tokens (estimated).
            tokens_out: Output/completion tokens (estimated).
            endpoint: API endpoint that triggered this call.
            cost_override: If provided, use this cost instead of computing.
        """
        cost = cost_override if cost_override is not None else _calculate_cost(
            tokens_in, tokens_out, provider
        )
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO token_usage
                    (tenant_id, user_id, session_id, model, provider,
                     tokens_in, tokens_out, cost_usd, created_at, endpoint)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (tenant_id, user_id, session_id, model, provider,
                 tokens_in, tokens_out, cost, time.time(), endpoint),
            )

    # ---- Reporting ----

    def get_usage_report(
        self,
        tenant_id: Optional[str] = None,
        user_id: Optional[str] = None,
        days: int = 30,
    ) -> UsageReport:
        """Return aggregated usage report for a tenant or user.

        Args:
            tenant_id: Filter by tenant ID (None = all tenants).
            user_id: Filter by user ID (None = all users).
            days: Number of days to aggregate.

        Returns:
            UsageReport with totals, breakdowns by model and provider.
        """
        since = time.time() - (days * 86400)
        conditions = ["created_at >= ?"]
        params: list = [since]

        if tenant_id:
            conditions.append("tenant_id = ?")
            params.append(tenant_id)
        if user_id:
            conditions.append("user_id = ?")
            params.append(user_id)

        where = " AND ".join(conditions)

        with self._conn() as conn:
            # Totals
            row = conn.execute(
                f"""
                SELECT
                    SUM(tokens_in) AS total_in,
                    SUM(tokens_out) AS total_out,
                    SUM(cost_usd) AS total_cost,
                    COUNT(DISTINCT user_id) AS unique_users,
                    COUNT(DISTINCT session_id) AS unique_sessions
                FROM token_usage WHERE {where}
                """,
                params,
            ).fetchone()

            # By model
            model_rows = conn.execute(
                f"""
                SELECT model,
                    SUM(tokens_in) AS tokens_in,
                    SUM(tokens_out) AS tokens_out,
                    SUM(cost_usd) AS cost_usd,
                    COUNT(*) AS calls
                FROM token_usage WHERE {where}
                GROUP BY model ORDER BY tokens_in + tokens_out DESC
                """,
                params,
            ).fetchall()

            # By provider
            provider_rows = conn.execute(
                f"""
                SELECT provider,
                    SUM(tokens_in) AS tokens_in,
                    SUM(tokens_out) AS tokens_out,
                    SUM(cost_usd) AS cost_usd,
                    COUNT(*) AS calls
                FROM token_usage WHERE {where}
                GROUP BY provider ORDER BY cost_usd DESC
                """,
                params,
            ).fetchall()

        total_in = int(row["total_in"] or 0)
        total_out = int(row["total_out"] or 0)

        return UsageReport(
            tenant_id=tenant_id or "all",
            period_days=days,
            total_tokens_in=total_in,
            total_tokens_out=total_out,
            total_tokens=total_in + total_out,
            total_cost_usd=round(float(row["total_cost"] or 0.0), 6),
            unique_users=int(row["unique_users"] or 0),
            unique_sessions=int(row["unique_sessions"] or 0),
            by_model={
                r["model"]: {
                    "tokens_in": r["tokens_in"],
                    "tokens_out": r["tokens_out"],
                    "cost_usd": round(float(r["cost_usd"] or 0), 6),
                    "calls": r["calls"],
                }
                for r in model_rows
            },
            by_provider={
                r["provider"]: {
                    "tokens_in": r["tokens_in"],
                    "tokens_out": r["tokens_out"],
                    "cost_usd": round(float(r["cost_usd"] or 0), 6),
                    "calls": r["calls"],
                }
                for r in provider_rows
            },
        )

    def get_daily_usage(self, tenant_id: str, days: int = 7) -> list[dict]:
        """Return day-by-day token usage for a tenant."""
        since = time.time() - (days * 86400)
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT
                    DATE(created_at, 'unixepoch') AS day,
                    SUM(tokens_in + tokens_out) AS total_tokens,
                    SUM(cost_usd) AS total_cost,
                    COUNT(*) AS calls
                FROM token_usage
                WHERE tenant_id = ? AND created_at >= ?
                GROUP BY day
                ORDER BY day DESC
                """,
                (tenant_id, since),
            ).fetchall()
        return [
            {
                "date": r["day"],
                "total_tokens": r["total_tokens"],
                "cost_usd": round(float(r["total_cost"] or 0), 6),
                "calls": r["calls"],
            }
            for r in rows
        ]


# -----------------------------------------------------------------------
# Singleton
# -----------------------------------------------------------------------
_tracker: Optional[CostTracker] = None


def get_cost_tracker() -> CostTracker:
    """Return the global CostTracker singleton."""
    global _tracker
    if _tracker is None:
        _tracker = CostTracker()
    return _tracker


# -----------------------------------------------------------------------
# Token Accumulator & ContextVar for request-scoped token tracking
# -----------------------------------------------------------------------
from contextvars import ContextVar


@dataclass
class TokenAccumulator:
    tokens_in: int = 0
    tokens_out: int = 0
    model: str = ""
    provider: str = ""

token_accumulator_var: ContextVar[Optional[TokenAccumulator]] = ContextVar("token_accumulator", default=None)
