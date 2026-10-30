"""Retrieval Feedback Loop Service (Phase 6 / RAG-1).

Persists feedback signals (positive/negative) with query hash, source_url,
and point_id. Evaluates negative signals to suppress sources for repeated
matching queries if negative signals exceed ``retrieval_feedback_min_samples``
within TTL (``retrieval_feedback_ttl_days``).

Invariant:
- Suppression-only (never boosts or writes to Qdrant).
- Reversible and bounded by TTL.
- Off by default (gated by ``retrieval_feedback_enabled``).
- Graceful fallback to memory store if Supabase is unavailable.
"""

from __future__ import annotations

import hashlib
import logging
import threading
from datetime import UTC, datetime, timedelta
from typing import Any

from app.config import settings
from app.metrics import RETRIEVAL_FEEDBACK_SUPPRESSIONS_TOTAL

logger = logging.getLogger(__name__)


def hash_query(query: str) -> str:
    """Deterministic normalized sha256 hash of query string."""
    normalized = " ".join(query.strip().lower().split())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


class RetrievalFeedbackService:
    """Service managing retrieval feedback signals and source suppression."""

    def __init__(self, supabase_client: Any | None = None) -> None:
        self._supabase = supabase_client
        self._memory_signals: list[dict[str, Any]] = []
        self._use_fallback: bool = supabase_client is None

        if supabase_client is None:
            try:
                from app.telemetry_db import _get_client

                client = _get_client()
                if client is not None:
                    self._supabase = client
                    self._use_fallback = False
            except Exception as e:
                logger.debug("Supabase client unavailable, using in-memory feedback store: %s", e)
                self._use_fallback = True

    def record_feedback(
        self,
        query: str,
        source_url: str,
        signal: str,
        point_id: str | None = None,
        created_at: datetime | None = None,
    ) -> dict[str, Any]:
        """Record a feedback signal ('positive' or 'negative') for a query and source.

        A feedback write NEVER touches Qdrant.
        """
        signal_val = signal.lower().strip()
        if signal_val not in ("positive", "negative"):
            raise ValueError(
                f"Invalid feedback signal {signal!r}; must be 'positive' or 'negative'"
            )

        now = created_at or datetime.now(UTC)
        ttl_days = int(getattr(settings, "retrieval_feedback_ttl_days", 30))
        expires_at = now + timedelta(days=ttl_days)
        q_hash = hash_query(query)

        record = {
            "query_hash": q_hash,
            "source_url": str(source_url).strip(),
            "point_id": str(point_id).strip() if point_id else None,
            "signal": signal_val,
            "created_at": now.isoformat(),
            "expires_at": expires_at.isoformat(),
        }

        # Keep in memory store for immediate local visibility / fallback
        self._memory_signals.append(
            {
                **record,
                "created_at_dt": now,
                "expires_at_dt": expires_at,
            }
        )

        if self._supabase and not self._use_fallback:
            try:
                self._supabase.table("retrieval_feedback_signals").insert(record).execute()
            except Exception as exc:
                logger.warning("Failed to persist retrieval feedback to Supabase: %s", exc)

        logger.debug(
            "Recorded %s feedback for query_hash=%s, source_url=%s", signal_val, q_hash, source_url
        )
        return record

    def get_suppressed_sources(self, query: str) -> set[str]:
        """Return set of source_urls that should be suppressed for this query.

        Only active when ``retrieval_feedback_enabled`` is True.
        Suppresses a source if negative feedback count >= ``retrieval_feedback_min_samples``
        within the unexpired TTL window.
        """
        if not getattr(settings, "retrieval_feedback_enabled", False):
            return set()

        if not query or not query.strip():
            return set()

        q_hash = hash_query(query)
        now = datetime.now(UTC)
        min_samples = int(getattr(settings, "retrieval_feedback_min_samples", 3))

        neg_counts: dict[str, int] = {}

        if self._supabase and not self._use_fallback:
            try:
                res = (
                    self._supabase.table("retrieval_feedback_signals")
                    .select("source_url")
                    .eq("query_hash", q_hash)
                    .eq("signal", "negative")
                    .gt("expires_at", now.isoformat())
                    .execute()
                )
                rows = getattr(res, "data", []) or []
                for row in rows:
                    s_url = row.get("source_url")
                    if s_url:
                        neg_counts[s_url] = neg_counts.get(s_url, 0) + 1
            except Exception as exc:
                logger.warning(
                    "Error fetching retrieval feedback from Supabase: %s; falling back to memory",
                    exc,
                )
                neg_counts.clear()

        # Check memory store if fallback or Supabase empty/failed
        if not neg_counts:
            for s in self._memory_signals:
                if (
                    s.get("query_hash") == q_hash
                    and s.get("signal") == "negative"
                    and s.get("expires_at_dt", now) > now
                ):
                    s_url = s.get("source_url")
                    if s_url:
                        neg_counts[s_url] = neg_counts.get(s_url, 0) + 1

        suppressed = {
            source_url for source_url, count in neg_counts.items() if count >= min_samples
        }
        return suppressed

    def filter_suppressed(
        self, query: str, documents: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Filter out documents whose source_url is suppressed for the given query."""
        if not getattr(settings, "retrieval_feedback_enabled", False):
            return documents

        suppressed = self.get_suppressed_sources(query)
        if not suppressed:
            return documents

        kept: list[dict[str, Any]] = []
        suppressed_count = 0
        for doc in documents:
            source = doc.get("source_url") or doc.get("video_id") or ""
            if source in suppressed:
                suppressed_count += 1
                continue
            kept.append(doc)

        if suppressed_count > 0:
            RETRIEVAL_FEEDBACK_SUPPRESSIONS_TOTAL.inc(suppressed_count)
            logger.info(
                "Suppressed %d document(s) for query %r via retrieval feedback signals",
                suppressed_count,
                query[:40],
            )
        return kept


_SHARED_SERVICE: RetrievalFeedbackService | None = None
_SHARED_LOCK = threading.Lock()


def get_retrieval_feedback_service() -> RetrievalFeedbackService:
    """Process-wide service: one Supabase client lookup, one in-memory fallback store.

    A per-request instance re-resolved the client every call and, on the
    in-memory fallback, forgot every signal as soon as the request ended.
    """
    global _SHARED_SERVICE
    if _SHARED_SERVICE is None:
        with _SHARED_LOCK:
            if _SHARED_SERVICE is None:
                _SHARED_SERVICE = RetrievalFeedbackService()
    return _SHARED_SERVICE
