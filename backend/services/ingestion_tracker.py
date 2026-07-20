import json
import logging
import os
import time
from typing import Any, Optional

logger = logging.getLogger(__name__)


class IngestionTracker:
    """Base interface for ingestion tracking."""

    def update(
        self, url: str, message: str, percent: float, tags: Optional[list[str]] = None
    ) -> None:
        raise NotImplementedError  # pragma: no cover

    def get_all(self) -> dict[str, Any]:
        raise NotImplementedError  # pragma: no cover

    def mark_error(self, url: str, error_message: str) -> None:
        raise NotImplementedError  # pragma: no cover


class _InMemoryIngestionTracker(IngestionTracker):
    """Fallback tracker when Supabase is unavailable."""

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}

    def update(
        self, url: str, message: str, percent: float, tags: Optional[list[str]] = None
    ) -> None:
        self._data[url] = {
            "url": url,
            "message": message,
            "progress": percent,
            "updated_at": time.time(),
            "status": "processing" if percent < 1.0 else "success",
            "tags": tags or [],
        }

    def get_all(self) -> dict[str, Any]:
        return self._data.copy()

    def mark_error(
        self, url: str, error_message: str, tags: Optional[list[str]] = None
    ) -> None:
        self._data[url] = {
            "url": url,
            "message": error_message,
            "progress": 0.0,
            "updated_at": time.time(),
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
        self, url: str, message: str, percent: float, tags: Optional[list[str]] = None
    ) -> None:
        try:
            now = time.time()
            self._client.table("ingest_jobs").upsert(
                {
                    "source_url": url,
                    "message": message,
                    "progress_pct": int(percent * 100),
                    "status": "running" if percent < 1.0 else "completed",
                    "tags": json.dumps(tags or []),
                    "updated_at": now,
                },
                on_conflict="source_url",
            ).execute()
        except Exception as e:
            logger.warning(f"SupabaseIngestionTracker.update failed for {url}: {e}")

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
                    "tags": tags,
                }
            return result
        except Exception as e:
            logger.warning(f"SupabaseIngestionTracker.get_all failed: {e}")
            return {}

    def mark_error(
        self, url: str, error_message: str, tags: Optional[list[str]] = None
    ) -> None:
        try:
            now = time.time()
            self._client.table("ingest_jobs").upsert(
                {
                    "source_url": url,
                    "message": error_message,
                    "progress_pct": 0,
                    "status": "failed",
                    "tags": json.dumps(tags or []),
                    "updated_at": now,
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
            logger.warning(f"Failed to create SupabaseIngestionTracker: {e}. Falling back to in-memory.")
    return _InMemoryIngestionTracker()
