"""Tests for ingest job lifecycle, source catalog tracking, and stale job sweeper.

Verifies:
1. test_stuck_job_is_swept: Stale running/processing jobs whose heartbeat is older
   than timeout_minutes are detected and flipped to 'failed' with error message
   'stale_worker_heartbeat_timeout'.
2. Healthy jobs with recent heartbeats are never swept.
3. Terminal jobs (completed, failed) are never swept.
4. Heartbeat and updated_at support epoch, ISO string, and datetime formats.
5. Ingestion tracker lifecycle methods record attempt and source_identity.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from celery_config import update_job_progress
from services.ingestion_tracker import (
    _format_timestamp,
    _InMemoryIngestionTracker,
)
from tasks.ingest_tasks import sweep_stale_ingest_jobs


class FakeSupabaseTable:
    """In-memory simulation of Supabase PostgREST table for ingest_jobs."""

    def __init__(self, initial_rows: list[dict] | None = None) -> None:
        self.rows: list[dict] = [dict(r) for r in (initial_rows or [])]
        self._filter_in: tuple[str, list] | None = None
        self._filter_lt: tuple[str, str] | None = None
        self._pending_update: dict | None = None
        self._update_eq_col: str | None = None
        self._update_eq_val: str | None = None
        self.updates_executed: list[dict] = []

    def select(self, fields: str):
        return self

    def in_(self, col: str, values: list):
        self._filter_in = (col, values)
        return self

    def lt(self, col: str, val: str):
        self._filter_lt = (col, val)
        return self

    def update(self, data: dict):
        self._pending_update = dict(data)
        return self

    def eq(self, col: str, val: str):
        self._update_eq_col = col
        self._update_eq_val = val
        return self

    def execute(self):
        if self._pending_update is not None:
            # Execute update
            updated_any = False
            for r in self.rows:
                if self._update_eq_col and r.get(self._update_eq_col) == self._update_eq_val:
                    r.update(self._pending_update)
                    self.updates_executed.append(
                        {
                            "id": self._update_eq_val,
                            "updates": dict(self._pending_update),
                        }
                    )
                    updated_any = True
            self._pending_update = None
            return SimpleNamespace(data=self.rows if updated_any else [])

        # Execute select
        matched = []
        for r in self.rows:
            if self._filter_in:
                col, vals = self._filter_in
                if r.get(col) not in vals:
                    continue
            if self._filter_lt:
                col, cutoff = self._filter_lt
                val = r.get(col)
                if not val or val >= cutoff:
                    continue
            matched.append(dict(r))
        return SimpleNamespace(data=matched)


class FakeSupabaseClient:
    def __init__(self, table: FakeSupabaseTable) -> None:
        self._table = table

    def table(self, table_name: str):
        assert table_name == "ingest_jobs"
        return self._table


def test_stuck_job_is_swept():
    """Verify that stale running/processing jobs get swept to 'failed'."""
    now = datetime.now(UTC)
    stale_heartbeat_25m = (now - timedelta(minutes=25)).isoformat()
    stale_heartbeat_20m = (now - timedelta(minutes=20)).isoformat()
    fresh_heartbeat_3m = (now - timedelta(minutes=3)).isoformat()
    terminal_heartbeat_40m = (now - timedelta(minutes=40)).isoformat()

    stuck_running_id = str(uuid.uuid4())
    stuck_processing_id = str(uuid.uuid4())
    healthy_running_id = str(uuid.uuid4())
    completed_id = str(uuid.uuid4())

    initial_jobs = [
        {
            "id": stuck_running_id,
            "source_url": "https://youtube.com/watch?v=stuck1",
            "status": "running",
            "heartbeat_at": stale_heartbeat_25m,
            "started_at": stale_heartbeat_25m,
        },
        {
            "id": stuck_processing_id,
            "source_url": "https://youtube.com/watch?v=stuck2",
            "status": "processing",
            "heartbeat_at": stale_heartbeat_20m,
            "started_at": stale_heartbeat_20m,
        },
        {
            "id": healthy_running_id,
            "source_url": "https://youtube.com/watch?v=healthy",
            "status": "running",
            "heartbeat_at": fresh_heartbeat_3m,
            "started_at": fresh_heartbeat_3m,
        },
        {
            "id": completed_id,
            "source_url": "https://youtube.com/watch?v=done",
            "status": "completed",
            "heartbeat_at": terminal_heartbeat_40m,
            "started_at": terminal_heartbeat_40m,
        },
    ]

    fake_table = FakeSupabaseTable(initial_jobs)
    fake_client = FakeSupabaseClient(fake_table)

    swept_ids = sweep_stale_ingest_jobs(timeout_minutes=15, client=fake_client)

    # 1. Stuck jobs are returned in swept list
    assert stuck_running_id in swept_ids
    assert stuck_processing_id in swept_ids
    assert len(swept_ids) == 2

    # 2. Healthy and completed jobs were not swept
    assert healthy_running_id not in swept_ids
    assert completed_id not in swept_ids

    # 3. Check updated state of stuck jobs
    jobs_by_id = {j["id"]: j for j in fake_table.rows}
    assert jobs_by_id[stuck_running_id]["status"] == "failed"
    assert jobs_by_id[stuck_running_id]["error_message"] == "stale_worker_heartbeat_timeout"
    assert jobs_by_id[stuck_processing_id]["status"] == "failed"
    assert jobs_by_id[stuck_processing_id]["error_message"] == "stale_worker_heartbeat_timeout"

    # 4. Healthy running job and completed job are untouched
    assert jobs_by_id[healthy_running_id]["status"] == "running"
    assert jobs_by_id[completed_id]["status"] == "completed"


def test_stuck_job_is_swept_via_patch():
    """Verify sweep_stale_ingest_jobs resolves Supabase client via settings and creates updates."""
    now = datetime.now(UTC)
    stale_time = (now - timedelta(minutes=30)).isoformat()
    job_id = str(uuid.uuid4())

    fake_table = FakeSupabaseTable(
        [
            {
                "id": job_id,
                "source_url": "https://youtube.com/watch?v=stale",
                "status": "running",
                "heartbeat_at": stale_time,
            }
        ]
    )
    fake_client = FakeSupabaseClient(fake_table)

    with (
        patch("app.config.settings.supabase_url", "https://example.supabase.co"),
        patch("app.config.settings.supabase_key", "service-role-key"),
        patch("supabase.create_client", return_value=fake_client),
    ):
        swept = sweep_stale_ingest_jobs(timeout_minutes=15)
        assert swept == [job_id]
        assert fake_table.rows[0]["status"] == "failed"
        assert fake_table.rows[0]["error_message"] == "stale_worker_heartbeat_timeout"


def test_timestamp_formatting_helpers():
    """Verify _format_timestamp accepts ISO strings, epoch float/int, and datetime."""
    # 1. None -> current ISO
    res_none = _format_timestamp(None)
    assert "T" in res_none

    # 2. Epoch float / int
    epoch = 1700000000.0
    res_epoch = _format_timestamp(epoch)
    assert res_epoch.startswith("2023-11-14T22:13:20")

    # 3. ISO string
    iso_str = "2026-10-28T00:00:00+00:00"
    assert _format_timestamp(iso_str) == iso_str

    # 4. Datetime
    dt = datetime(2026, 10, 28, 12, 0, 0, tzinfo=UTC)
    assert _format_timestamp(dt) == "2026-10-28T12:00:00+00:00"


def test_update_job_progress_lifecycle():
    """Verify celery_config.update_job_progress updates heartbeat_at, updated_at, attempt."""
    mock_client = MagicMock()
    mock_table = MagicMock()
    mock_client.table.return_value = mock_table

    with (
        patch("app.config.settings.supabase_url", "https://example.supabase.co"),
        patch("app.config.settings.supabase_key", "service-role-key"),
        patch("supabase.create_client", return_value=mock_client),
    ):
        job_id = "job-123"
        epoch_now = 1730000000.5

        update_job_progress(
            job_id=job_id,
            status="running",
            progress_pct=25,
            heartbeat_at=epoch_now,
            updated_at=epoch_now,
            attempt=2,
            source_identity="video_v123",
        )

        mock_client.table.assert_called_with("ingest_jobs")
        update_call = mock_table.update.call_args[0][0]
        assert update_call["status"] == "running"
        assert update_call["progress_pct"] == 25
        assert update_call["attempt"] == 2
        assert update_call["source_identity"] == "video_v123"
        assert "heartbeat_at" in update_call
        assert "updated_at" in update_call
        # Heartbeat was converted from epoch to ISO string
        assert "T" in update_call["heartbeat_at"]


def test_in_memory_tracker_heartbeat_lifecycle():
    """Verify _InMemoryIngestionTracker tracks heartbeat_at and updated_at."""
    tracker = _InMemoryIngestionTracker()
    url = "https://youtube.com/watch?v=inmem"

    tracker.update(url, message="Parsing", percent=0.5, heartbeat_at=1730000000.0, attempt=1)
    data = tracker.get_all()
    assert url in data
    assert data[url]["status"] == "processing"
    assert data[url]["attempt"] == 1
    assert "T" in data[url]["heartbeat_at"]

    tracker.update_heartbeat(url, heartbeat_at=1730000100.0)
    data2 = tracker.get_all()
    assert "T" in data2[url]["heartbeat_at"]
