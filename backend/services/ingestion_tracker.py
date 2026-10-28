from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any, Optional

logger = logging.getLogger(__name__)


def _format_timestamp(ts: Any) -> str:
    """Convert ISO timestamp string, epoch float/int, or datetime to ISO 8601 string.

    If ts is None, returns current UTC time in ISO 8601 format.
    """
    if ts is None:
        return datetime.now(UTC).isoformat()
    if isinstance(ts, (int, float)):
        return datetime.fromtimestamp(ts, tz=UTC).isoformat()
    if isinstance(ts, datetime):
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=UTC)
        return ts.isoformat()
    if isinstance(ts, str):
        return ts
    return str(ts)


class IngestionTracker:
    """Base interface for ingestion tracking."""

    def update(
        self,
        url: str,
        message: str,
        percent: float,
        tags: Optional[list[str]] = None,
        heartbeat_at: Optional[Any] = None,
        updated_at: Optional[Any] = None,
        attempt: Optional[int] = None,
        source_identity: Optional[str] = None,
    ) -> None:
        raise NotImplementedError  # pragma: no cover

    def update_heartbeat(
        self,
        url: str,
        heartbeat_at: Optional[Any] = None,
        updated_at: Optional[Any] = None,
    ) -> None:
        raise NotImplementedError  # pragma: no cover

    def get_all(self) -> dict[str, Any]:
        raise NotImplementedError  # pragma: no cover

    def mark_error(
        self,
        url: str,
        error_message: str,
        tags: Optional[list[str]] = None,
        updated_at: Optional[Any] = None,
    ) -> None:
        raise NotImplementedError  # pragma: no cover


class _InMemoryIngestionTracker(IngestionTracker):
    """Fallback tracker when Supabase is unavailable."""

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}

    def update(
        self,
        url: str,
        message: str,
        percent: float,
        tags: Optional[list[str]] = None,
        heartbeat_at: Optional[Any] = None,
        updated_at: Optional[Any] = None,
        attempt: Optional[int] = None,
        source_identity: Optional[str] = None,
    ) -> None:
        now_iso = _format_timestamp(None)
        hb = _format_timestamp(heartbeat_at) if heartbeat_at is not None else now_iso
        up = _format_timestamp(updated_at) if updated_at is not None else now_iso
        entry: dict[str, Any] = {
            "url": url,
            "message": message,
            "progress": percent,
            "updated_at": up,
            "heartbeat_at": hb,
            "status": "processing" if percent < 1.0 else "success",
            "tags": tags or [],
        }
        if attempt is not None:
            entry["attempt"] = attempt
        if source_identity is not None:
            entry["source_identity"] = source_identity
        self._data[url] = entry

    def update_heartbeat(
        self,
        url: str,
        heartbeat_at: Optional[Any] = None,
        updated_at: Optional[Any] = None,
    ) -> None:
        now_iso = _format_timestamp(None)
        hb = _format_timestamp(heartbeat_at) if heartbeat_at is not None else now_iso
        up = _format_timestamp(updated_at) if updated_at is not None else now_iso
        if url in self._data:
            self._data[url]["heartbeat_at"] = hb
            self._data[url]["updated_at"] = up
        else:
            self._data[url] = {
                "url": url,
                "message": "",
                "progress": 0.0,
                "status": "processing",
                "heartbeat_at": hb,
                "updated_at": up,
                "tags": [],
            }

    def get_all(self) -> dict[str, Any]:
        return self._data.copy()

    def mark_error(
        self,
        url: str,
        error_message: str,
        tags: Optional[list[str]] = None,
        updated_at: Optional[Any] = None,
    ) -> None:
        up = _format_timestamp(updated_at) if updated_at is not None else _format_timestamp(None)
        self._data[url] = {
            "url": url,
            "message": error_message,
            "progress": 0.0,
            "updated_at": up,
            "status": "error",
            "tags": tags or [],
        }


class SupabaseIngestionTracker(IngestionTracker):
    """Supabase-backed ingestion tracker using the ingest_jobs table."""

    def __init__(self, supabase_url: str, supabase_key: str) -> None:
        from supabase import create_client

        self._client = create_client(supabase_url, supabase_key)

    @staticmethod
    def _supabase_url_and_key() -> Optional[tuple[str, str]]:
        try:
            from app.config import settings

            if settings.supabase_url and settings.supabase_key:
                return settings.supabase_url, settings.supabase_key
        except Exception as e:
            logger.debug(f"SupabaseIngestionTracker: config unavailable ({e})")
        return None

    def update(
        self,
        url: str,
        message: str,
        percent: float,
        tags: Optional[list[str]] = None,
        heartbeat_at: Optional[Any] = None,
        updated_at: Optional[Any] = None,
        attempt: Optional[int] = None,
        source_identity: Optional[str] = None,
    ) -> None:
        try:
            now_iso = _format_timestamp(None)
            hb = _format_timestamp(heartbeat_at) if heartbeat_at is not None else now_iso
            up = _format_timestamp(updated_at) if updated_at is not None else now_iso
            payload: dict[str, Any] = {
                "source_url": url,
                "message": message,
                "progress_pct": int(percent * 100),
                "status": "running" if percent < 1.0 else "completed",
                "tags": json.dumps(tags or []),
                "updated_at": up,
                "heartbeat_at": hb,
            }
            if attempt is not None:
                payload["attempt"] = attempt
            if source_identity is not None:
                payload["source_identity"] = source_identity
            self._client.table("ingest_jobs").upsert(
                payload,
                on_conflict="source_url",
            ).execute()
        except Exception as e:
            logger.warning(f"SupabaseIngestionTracker.update failed for {url}: {e}")

    def update_heartbeat(
        self,
        url: str,
        heartbeat_at: Optional[Any] = None,
        updated_at: Optional[Any] = None,
    ) -> None:
        try:
            now_iso = _format_timestamp(None)
            hb = _format_timestamp(heartbeat_at) if heartbeat_at is not None else now_iso
            up = _format_timestamp(updated_at) if updated_at is not None else now_iso
            self._client.table("ingest_jobs").update(
                {
                    "heartbeat_at": hb,
                    "updated_at": up,
                }
            ).eq("source_url", url).execute()
        except Exception as e:
            logger.warning(f"SupabaseIngestionTracker.update_heartbeat failed for {url}: {e}")

    def get_all(self) -> dict[str, Any]:
        try:
            resp = (
                self._client.table("ingest_jobs")
                .select("*")
                .order("updated_at", desc=True)
                .limit(50)
                .execute()
            )
            result: dict[str, Any] = {}
            for row in resp.data or []:
                url = row.get("source_url") or row.get("url", "")
                if not url:
                    continue
                tags_raw = row.get("tags")
                if isinstance(tags_raw, str):
                    try:
                        tags = json.loads(tags_raw)
                    except Exception:
                        tags = []
                else:
                    tags = tags_raw or []
                result[url] = {
                    "url": url,
                    "message": row.get("message", ""),
                    "progress": (row.get("progress_pct", 0) or 0) / 100.0,
                    "status": row.get("status", "unknown"),
                    "updated_at": row.get("updated_at", ""),
                    "heartbeat_at": row.get("heartbeat_at", ""),
                    "attempt": row.get("attempt", 0),
                    "source_identity": row.get("source_identity", ""),
                    "tags": tags,
                }
            return result
        except Exception as e:
            logger.warning(f"SupabaseIngestionTracker.get_all failed: {e}")
            return {}

    def mark_error(
        self,
        url: str,
        error_message: str,
        tags: Optional[list[str]] = None,
        updated_at: Optional[Any] = None,
    ) -> None:
        try:
            up = (
                _format_timestamp(updated_at) if updated_at is not None else _format_timestamp(None)
            )
            self._client.table("ingest_jobs").upsert(
                {
                    "source_url": url,
                    "message": error_message,
                    "progress_pct": 0,
                    "status": "failed",
                    "tags": json.dumps(tags or []),
                    "updated_at": up,
                },
                on_conflict="source_url",
            ).execute()
        except Exception as e:
            logger.warning(f"SupabaseIngestionTracker.mark_error failed for {url}: {e}")


def build_tracker(
    supabase_url: Optional[str] = None, supabase_key: Optional[str] = None
) -> IngestionTracker:
    # Prefer explicit args; fall back to settings via _supabase_url_and_key()
    if not (supabase_url and supabase_key):
        creds = SupabaseIngestionTracker._supabase_url_and_key()
        if creds:
            supabase_url, supabase_key = creds
    url = supabase_url or ""
    key = supabase_key or ""
    if url and key:
        try:
            return SupabaseIngestionTracker(url, key)
        except Exception as e:
            logger.warning(
                f"Failed to create SupabaseIngestionTracker: {e}. Falling back to in-memory."
            )
    return _InMemoryIngestionTracker()
