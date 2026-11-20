"""Delete event audio/video once the event has ended (Celery Beat, hourly)."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from celery_config import celery_app

logger = logging.getLogger(__name__)

EVENT_MEDIA_BUCKET = "event-media"


def _parse(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def purge_ended_event_media(client: Any | None = None, now: datetime | None = None) -> int:
    """Remove the stored file of every event that has ended and clear its media columns.

    An event has ended at `ends_at`, or at `starts_at` when no end was set. Raises after
    the loop if any event failed, so a stuck file is visible and never silently kept.
    """
    if client is None:
        from supabase import create_client

        from app.config import settings

        client = create_client(
            settings.supabase_url, settings.supabase_service_key or settings.supabase_key
        )
    now = now or datetime.now(timezone.utc)

    rows = (
        client.table("upcoming_events")
        .select("id, media_path, starts_at, ends_at")
        .not_.is_("media_path", "null")
        .execute()
        .data
        or []
    )

    purged = 0
    failures: list[str] = []
    for row in rows:
        if _parse(row["ends_at"] or row["starts_at"]) > now:
            continue
        try:
            client.storage.from_(EVENT_MEDIA_BUCKET).remove([row["media_path"]])
            client.table("upcoming_events").update(
                {"media_path": None, "media_url": None, "media_type": None}
            ).eq("id", row["id"]).execute()
            purged += 1
        except Exception:
            logger.exception("Could not purge media for event %s", row["id"])
            failures.append(str(row["id"]))

    if failures:
        raise RuntimeError(f"Event media purge failed for {len(failures)} event(s): {failures}")
    logger.info("Event media purge finished: %d file(s) removed", purged)
    return purged


@celery_app.task(name="tasks.event_media_tasks.purge_ended_event_media")
def purge_ended_event_media_task() -> int:
    return purge_ended_event_media()


if __name__ == "__main__":

    class _Result:
        def __init__(self, data: list[dict[str, Any]]):
            self.data = data

    class _Query:
        def __init__(self, store: "_Fake"):
            self.store, self.not_ = store, self

        def select(self, *_a: Any) -> "_Query":
            return self

        def is_(self, *_a: Any) -> "_Query":
            return self

        def update(self, values: dict[str, Any]) -> "_Query":
            self.store.updates.append(values)
            return self

        def eq(self, *_a: Any) -> "_Query":
            return self

        def execute(self) -> _Result:
            return _Result(self.store.rows)

    class _Bucket:
        def __init__(self, store: "_Fake"):
            self.store = store

        def remove(self, paths: list[str]) -> None:
            self.store.removed.extend(paths)

    class _Storage:
        def __init__(self, store: "_Fake"):
            self.store = store

        def from_(self, _bucket: str) -> _Bucket:
            return _Bucket(self.store)

    class _Fake:
        def __init__(self, rows: list[dict[str, Any]]):
            self.rows, self.removed, self.updates = rows, [], []
            self.storage = _Storage(self)

        def table(self, _name: str) -> _Query:
            return _Query(self)

    fake = _Fake(
        [
            {"id": "a", "media_path": "old.mp4", "starts_at": "2026-01-01T10:00:00Z", "ends_at": None},
            {"id": "b", "media_path": "live.mp3", "starts_at": "2026-01-01T10:00:00Z", "ends_at": "2026-12-31T10:00:00Z"},
        ]
    )
    assert purge_ended_event_media(fake, datetime(2026, 6, 1, tzinfo=timezone.utc)) == 1
    assert fake.removed == ["old.mp4"] and len(fake.updates) == 1
    print("event_media_tasks self-check OK")
