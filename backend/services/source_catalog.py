"""
Corpus Source Catalog & Freshness SLI Service — DE-3.1, DE-3.2

Provides:
- Persistent catalog of ingested corpus sources (corpus_sources table).
- Tracking of last_ingested_at, last_checksum, active_release_id, and status.
- Freshness SLI calculations and Prometheus gauges for monitoring and alerting.
- Transparent fallback to in-memory store when Supabase is unavailable.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from prometheus_client import REGISTRY, Gauge

logger = logging.getLogger(__name__)


def _get_or_create_gauge(name: str, documentation: str, labelnames: tuple[str, ...]) -> Gauge:
    """Retrieve existing collector if already registered in REGISTRY, otherwise create it."""
    if hasattr(REGISTRY, "_names_to_collectors") and name in REGISTRY._names_to_collectors:
        collector = REGISTRY._names_to_collectors[name]
        if isinstance(collector, Gauge):
            return collector
    return Gauge(name, documentation, list(labelnames))


# DE-3.2 Freshness SLI Gauges
CORPUS_SOURCE_AGE_DAYS: Gauge = _get_or_create_gauge(
    "corpus_source_age_days",
    "Age of oldest source in days by corpus",
    ("corpus_id",),
)

CORPUS_STALE_SOURCES_TOTAL: Gauge = _get_or_create_gauge(
    "corpus_stale_sources_total",
    "Total count of stale corpus sources by corpus",
    ("corpus_id",),
)


def _parse_datetime(val: Any) -> datetime:
    """Parse datetime from str or datetime object into UTC datetime."""
    if isinstance(val, datetime):
        if val.tzinfo is None:
            return val.replace(tzinfo=UTC)
        return val.astimezone(UTC)
    if isinstance(val, str) and val.strip():
        val_clean = val.strip().replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(val_clean)
            if dt.tzinfo is None:
                return dt.replace(tzinfo=UTC)
            return dt.astimezone(UTC)
        except Exception:
            pass
    return datetime.now(UTC)


class SourceCatalogService:
    """Catalog manager for corpus sources and freshness SLI evaluation."""

    def __init__(self, supabase_client: Any | None = None) -> None:
        self._supabase = supabase_client
        self._memory_store: dict[str, dict[str, Any]] = {}
        self._use_fallback: bool = supabase_client is None

        if supabase_client is None:
            try:
                from app.telemetry_db import _get_client

                client = _get_client()
                if client is not None:
                    self._supabase = client
                    self._use_fallback = False
            except Exception as e:
                logger.debug("Supabase client unavailable, using in-memory store: %s", e)
                self._use_fallback = True

    def upsert_source(
        self,
        source_identity: str,
        source_url: str,
        corpus_id: str,
        checksum: str | None = None,
        active_release_id: str | None = None,
        status: str = "active",
        last_ingested_at: datetime | str | None = None,
    ) -> dict[str, Any]:
        """Record or update a corpus source in the catalog.

        Args:
            source_identity: Unique identity string for the source (e.g. youtube video ID, URL hash).
            source_url: Canonical URL of the source material.
            corpus_id: Corpus partition identifier (e.g. 'askmukthiguru').
            checksum: SHA256 content checksum of extracted text or audio.
            active_release_id: UUID of the active source release, if any.
            status: Status of source ('active', 'inactive', 'quarantined').
            last_ingested_at: Timestamp of ingestion (defaults to current UTC time).

        Returns:
            dict[str, Any]: The stored source catalog record.
        """
        now = datetime.now(UTC)
        now_iso = now.isoformat()

        if last_ingested_at is None:
            ingested_iso = now_iso
        elif isinstance(last_ingested_at, datetime):
            if last_ingested_at.tzinfo is None:
                ingested_iso = last_ingested_at.replace(tzinfo=UTC).isoformat()
            else:
                ingested_iso = last_ingested_at.astimezone(UTC).isoformat()
        else:
            ingested_iso = str(last_ingested_at)

        record: dict[str, Any] = {
            "source_identity": source_identity,
            "source_url": source_url,
            "corpus_id": corpus_id,
            "last_ingested_at": ingested_iso,
            "last_checksum": checksum,
            "active_release_id": active_release_id,
            "status": status,
            "updated_at": now_iso,
        }

        if self._supabase and not self._use_fallback:
            try:
                res = (
                    self._supabase.table("corpus_sources")
                    .upsert(record, on_conflict="source_identity")
                    .execute()
                )
                if res.data and len(res.data) > 0:
                    saved = dict(res.data[0])
                    self._memory_store[source_identity] = saved
                    return saved
            except Exception as exc:
                logger.warning(
                    "Failed to upsert source into Supabase (%s), using memory store: %s",
                    source_identity,
                    exc,
                )

        # In-memory store fallback
        existing = self._memory_store.get(source_identity, {})
        record["created_at"] = existing.get("created_at", now_iso)
        self._memory_store[source_identity] = record
        return dict(record)

    def get_source(self, source_identity: str) -> dict[str, Any] | None:
        """Fetch a source catalog record by its identity."""
        if self._supabase and not self._use_fallback:
            try:
                res = (
                    self._supabase.table("corpus_sources")
                    .select("*")
                    .eq("source_identity", source_identity)
                    .limit(1)
                    .execute()
                )
                if res.data and len(res.data) > 0:
                    return dict(res.data[0])
                return (
                    dict(self._memory_store[source_identity])
                    if source_identity in self._memory_store
                    else None
                )
            except Exception as exc:
                logger.warning("Supabase get_source failed: %s; using memory store", exc)

        if source_identity in self._memory_store:
            return dict(self._memory_store[source_identity])
        return None

    def list_sources(self, corpus_id: str) -> list[dict[str, Any]]:
        """List all sources registered under a given corpus_id."""
        if self._supabase and not self._use_fallback:
            try:
                res = (
                    self._supabase.table("corpus_sources")
                    .select("*")
                    .eq("corpus_id", corpus_id)
                    .execute()
                )
                data = res.data or []
                seen = {
                    row["source_identity"]: dict(row) for row in data if "source_identity" in row
                }
                for k, v in self._memory_store.items():
                    if v.get("corpus_id") == corpus_id and k not in seen:
                        seen[k] = dict(v)
                return list(seen.values())
            except Exception as exc:
                logger.warning("Supabase list_sources failed: %s; using memory store", exc)

        return [dict(s) for s in self._memory_store.values() if s.get("corpus_id") == corpus_id]

    def list_stale_sources(self, corpus_id: str, max_age_days: int = 30) -> list[dict[str, Any]]:
        """List sources older than max_age_days for a corpus, ordered oldest first."""
        sources = self.list_sources(corpus_id)
        now = datetime.now(UTC)
        stale: list[dict[str, Any]] = []

        for s in sources:
            ingested_at = _parse_datetime(s.get("last_ingested_at"))
            age_days = (now - ingested_at).total_seconds() / 86400.0
            if age_days > max_age_days:
                item = dict(s)
                item["age_days"] = round(age_days, 4)
                stale.append(item)

        stale.sort(key=lambda x: x["age_days"], reverse=True)
        return stale

    def get_source_stats(self, corpus_id: str, stale_threshold_days: int = 30) -> dict[str, Any]:
        """Compute summary statistics for all sources in the given corpus."""
        sources = self.list_sources(corpus_id)
        if not sources:
            return {
                "corpus_id": corpus_id,
                "count": 0,
                "active_count": 0,
                "stale_count": 0,
                "oldest_age_days": 0.0,
                "newest_age_days": 0.0,
            }

        now = datetime.now(UTC)
        ages: list[float] = []
        active_count = 0
        stale_count = 0

        for s in sources:
            if s.get("status") == "active":
                active_count += 1
            ingested_at = _parse_datetime(s.get("last_ingested_at"))
            age = max(0.0, (now - ingested_at).total_seconds() / 86400.0)
            ages.append(age)
            if age > stale_threshold_days:
                stale_count += 1

        return {
            "corpus_id": corpus_id,
            "count": len(sources),
            "active_count": active_count,
            "stale_count": stale_count,
            "oldest_age_days": round(max(ages), 4) if ages else 0.0,
            "newest_age_days": round(min(ages), 4) if ages else 0.0,
        }

    def calculate_freshness_sli(
        self,
        corpus_id: str = "askmukthiguru",
        stale_threshold_days: int = 30,
    ) -> dict[str, Any]:
        """Evaluate source freshness SLI, update Prometheus gauges, and return report."""
        stale_sources = self.list_stale_sources(
            corpus_id=corpus_id, max_age_days=stale_threshold_days
        )
        stats = self.get_source_stats(
            corpus_id=corpus_id, stale_threshold_days=stale_threshold_days
        )
        max_age_days = stats["oldest_age_days"]
        stale_count = len(stale_sources)

        # Update Prometheus Gauges
        CORPUS_SOURCE_AGE_DAYS.labels(corpus_id=corpus_id).set(max_age_days)
        CORPUS_STALE_SOURCES_TOTAL.labels(corpus_id=corpus_id).set(stale_count)

        return {
            "stale_sources": stale_sources,
            "max_age_days": max_age_days,
            "stale_count": stale_count,
            "total_sources": stats["count"],
        }


# Convenience alias matching the prompt specification
SourceCatalog = SourceCatalogService

_default_catalog_instance: SourceCatalogService | None = None


def get_source_catalog() -> SourceCatalogService:
    """Get the singleton default SourceCatalogService instance."""
    global _default_catalog_instance
    if _default_catalog_instance is None:
        _default_catalog_instance = SourceCatalogService()
    return _default_catalog_instance


def calculate_freshness_sli(
    corpus_id: str = "askmukthiguru",
    stale_threshold_days: int = 30,
    catalog: SourceCatalogService | None = None,
) -> dict[str, Any]:
    """Calculate freshness SLI and update metrics using default or supplied catalog."""
    cat = catalog or get_source_catalog()
    return cat.calculate_freshness_sli(
        corpus_id=corpus_id,
        stale_threshold_days=stale_threshold_days,
    )
