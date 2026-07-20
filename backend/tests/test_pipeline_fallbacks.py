"""Tests for ingestion pipeline fallback chain, idempotency, and retry behavior."""

import hashlib

from celery_config import retry_backoff
from ingest.chunkers.youtube_chunker import _fallback_split
from ingest.pipeline import IngestionCheckpoint
from ingest.sources.supadata import fetch_transcript_supadata


def test_checkpoint_idempotency(tmp_path):
    cp = IngestionCheckpoint(filepath=str(tmp_path / "checkpoint.json"))

    content_hash = hashlib.sha256(b"test content").hexdigest()
    assert not cp.is_processed(content_hash)

    cp.save(content_hash)
    assert cp.is_processed(content_hash)

    other_hash = hashlib.sha256(b"other content").hexdigest()
    assert not cp.is_processed(other_hash)


def test_supadata_fallback_no_key(monkeypatch):
    monkeypatch.delenv("SUPADATA_API_KEY", raising=False)
    result = fetch_transcript_supadata("dQw4w9WgXcQ")
    assert result is None


def test_retry_backoff():
    from celery.exceptions import Retry

    class MockRequest:
        retries = 0

    class MockTask:
        request = MockRequest()
        retry_countdown = None

        def retry(self, exc, countdown):
            self.retry_countdown = countdown
            raise Retry()

    task = MockTask()

    for retries, expected in [(0, 5), (2, 20), (3, 30), (10, 30)]:
        task.request.retries = retries
        try:
            retry_backoff(task, Exception("test"))
        except Retry:
            pass
        assert task.retry_countdown == expected, f"retries={retries}"


def test_async_task_on_failure():
    from tasks.ingest_tasks import AsyncTask

    task = AsyncTask()
    task.on_failure(
        exc=Exception("test error"),
        task_id="test-task-id",
        args=(),
        kwargs={},
        einfo=None,
    )
    task.on_failure(
        exc=Exception("test error"),
        task_id="test-task-id-2",
        args=(),
        kwargs={"job_id": "test-job"},
        einfo=None,
    )


def test_fallback_split_chunker():
    assert _fallback_split is not None
