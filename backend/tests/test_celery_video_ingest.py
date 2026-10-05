"""Unit and integration tests for distributed First-Person video ingestion via Celery."""

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.main import app
from services.first_person_ingest_service import (
    FPJobStage,
    FPJobStatus,
    execute_first_person_video_ingestion,
    extract_youtube_video_id,
    get_fp_job_progress,
    record_fp_job_progress,
)
from tasks.ingest_tasks import ingest_first_person_video_task


@pytest.fixture
def test_client():
    return TestClient(app)


def test_extract_youtube_video_id_variants():
    assert extract_youtube_video_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    assert extract_youtube_video_id("https://youtu.be/dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    assert extract_youtube_video_id("https://www.youtube.com/embed/dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    assert extract_youtube_video_id("https://www.youtube.com/shorts/dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    assert extract_youtube_video_id("dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    assert extract_youtube_video_id("https://not-youtube.com/video") is None
    assert extract_youtube_video_id("") is None


def test_record_and_get_job_progress_mock_redis():
    storage = {}

    class FakeRedis:
        def hset(self, key, mapping):
            storage[key] = {k: str(v).encode("utf-8") for k, v in mapping.items()}

        def hgetall(self, key):
            return storage.get(key, {})

        def expire(self, key, ttl):
            pass

    fake_redis = FakeRedis()
    job_id = "fp_test_12345"

    record_fp_job_progress(
        redis_client=fake_redis,
        job_id=job_id,
        status=FPJobStatus.RUNNING,
        progress_pct=65,
        stage=FPJobStage.ALIGNING,
        clips_indexed=12,
        video_url="https://youtu.be/dQw4w9WgXcQ",
    )

    progress = get_fp_job_progress(fake_redis, job_id)
    assert progress is not None
    assert progress["job_id"] == job_id
    assert progress["status"] == "running"
    assert progress["stage"] == "aligning"
    assert progress["progress_pct"] == 65
    assert progress["clips_indexed"] == 12


def test_api_enqueue_video_ingest_success(test_client, monkeypatch):
    mock_apply_async = MagicMock()
    monkeypatch.setattr(
        "tasks.ingest_tasks.ingest_first_person_video_task.apply_async", mock_apply_async
    )

    # Mock Redis client so test doesn't depend on live Redis
    mock_redis = MagicMock()
    mock_redis.hgetall.return_value = {}
    monkeypatch.setattr("app.api.first_person._build_redis_client", lambda: mock_redis)

    payload = {
        "video_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "teacher_id": "preethaji",
        "rights_cleared": True,
    }
    resp = test_client.post("/api/first-person/ingest/video", json=payload)
    assert resp.status_code == 202
    data = resp.json()
    assert data["status"] == "queued"
    assert data["job_id"].startswith("fp_ingest_")
    assert data["video_url"] == payload["video_url"]

    # Verify task was dispatched to Celery 'ingestion' queue
    assert mock_apply_async.called
    call_kwargs = mock_apply_async.call_args.kwargs
    assert call_kwargs["queue"] == "ingestion"
    assert call_kwargs["kwargs"]["video_url"] == payload["video_url"]


def test_api_enqueue_video_ingest_invalid_url(test_client):
    resp = test_client.post(
        "/api/first-person/ingest/video",
        json={"video_url": "https://vimeo.com/12345"},
    )
    assert resp.status_code == 400
    assert "Invalid YouTube URL" in resp.json()["detail"]


def test_api_get_ingest_status_not_found(test_client, monkeypatch):
    mock_redis = MagicMock()
    mock_redis.hgetall.return_value = {}
    monkeypatch.setattr("app.api.first_person._build_redis_client", lambda: mock_redis)

    resp = test_client.get("/api/first-person/ingest/status/non_existent_job")
    assert resp.status_code == 404
    assert "not found" in resp.json()["detail"]


def test_api_get_ingest_status_success(test_client, monkeypatch):
    mock_redis = MagicMock()
    mock_redis.hgetall.return_value = {
        b"job_id": b"fp_ingest_abc123",
        b"video_url": b"https://youtu.be/dQw4w9WgXcQ",
        b"status": b"running",
        b"stage": b"speaker_verification",
        b"progress_pct": b"80",
        b"clips_indexed": b"24",
    }
    monkeypatch.setattr("app.api.first_person._build_redis_client", lambda: mock_redis)

    resp = test_client.get("/api/first-person/ingest/status/fp_ingest_abc123")
    assert resp.status_code == 200
    data = resp.json()
    assert data["job_id"] == "fp_ingest_abc123"
    assert data["status"] == "running"
    assert data["stage"] == "speaker_verification"
    assert data["progress_pct"] == 80
    assert data["clips_indexed"] == 24


def test_celery_task_execution_lifecycle(monkeypatch):
    mock_execute = MagicMock(
        return_value={
            "status": "success",
            "job_id": "test_job_1",
            "video_id": "dQw4w9WgXcQ",
            "chunks_indexed": 15,
        }
    )
    monkeypatch.setattr(
        "services.first_person_ingest_service.execute_first_person_video_ingestion",
        mock_execute,
    )

    mock_container = MagicMock()
    monkeypatch.setattr("app.dependencies.get_container", lambda: mock_container)

    # Execute Celery task directly
    result = ingest_first_person_video_task.apply(
        kwargs={
            "video_url": "https://youtu.be/dQw4w9WgXcQ",
            "job_id": "test_job_1",
            "teacher_id": "both",
        }
    ).get()

    assert result["status"] == "success"
    assert result["job_id"] == "test_job_1"
    assert mock_execute.called
    assert mock_container.exact_cache.invalidate_all.called
    assert mock_container.semantic_cache.invalidate_all.called


def test_execute_first_person_video_ingestion_stage_transitions():
    progress_stages = []

    def on_prog(stage, pct):
        progress_stages.append((stage, pct))

    result = execute_first_person_video_ingestion(
        video_url="https://youtu.be/dQw4w9WgXcQ",
        job_id="test_stages_job",
        on_progress=on_prog,
    )

    assert result["status"] == "success"
    stages_hit = [s[0] for s in progress_stages]
    assert FPJobStage.DOWNLOADING in stages_hit
    assert FPJobStage.TRANSCRIBING_WHISPER in stages_hit
    assert FPJobStage.TRANSCRIBING_PARAKEET in stages_hit
    assert FPJobStage.ALIGNING in stages_hit
    assert FPJobStage.SPEAKER_VERIFICATION in stages_hit
    assert FPJobStage.SLICING_CLIPS in stages_hit
    assert FPJobStage.INDEXING in stages_hit
    assert FPJobStage.COMPLETED in stages_hit
