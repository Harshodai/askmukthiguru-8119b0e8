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
    from app.api.first_person import _require_admin

    app.dependency_overrides[_require_admin] = lambda: {"id": "admin", "is_superuser": True}
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(_require_admin, None)


def test_ingest_routes_reject_anonymous_callers():
    """Regression: enqueue/status were unauthenticated (anyone could queue ingestion
    into any Qdrant collection with rights_cleared=True)."""
    client = TestClient(app)
    r = client.post(
        "/api/first-person/ingest/video",
        json={
            "video_url": "https://youtu.be/dQw4w9WgXcQ",
            "collection": "x",
            "rights_cleared": True,
        },
    )
    assert r.status_code in (401, 403)
    assert client.get("/api/first-person/ingest/status/fp_ingest_abc").status_code in (401, 403)


def test_extract_youtube_video_id_variants():
    assert extract_youtube_video_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    assert extract_youtube_video_id("https://youtu.be/dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    assert extract_youtube_video_id("https://www.youtube.com/embed/dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    assert extract_youtube_video_id("https://www.youtube.com/shorts/dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    assert extract_youtube_video_id("dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    assert extract_youtube_video_id("https://not-youtube.com/video") is None
    assert extract_youtube_video_id("https://evil.com/watch?v=dQw4w9WgXcQ") is None
    assert extract_youtube_video_id("https://youtube.com.evil.com/watch?v=dQw4w9WgXcQ") is None
    assert extract_youtube_video_id("https://youtube.com@evil.com/watch?v=dQw4w9WgXcQ") is None
    assert extract_youtube_video_id("http://youtube.com/watch?v=dQw4w9WgXcQ") is None
    assert extract_youtube_video_id("https://www.youtube.com:8443/watch?v=dQw4w9WgXcQ") is None
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


def test_api_enqueue_succeeds_when_wired(test_client, monkeypatch):
    mock_apply_async = MagicMock()
    monkeypatch.setattr(
        "tasks.ingest_tasks.ingest_first_person_video_task.apply_async", mock_apply_async
    )
    mock_redis = MagicMock()
    monkeypatch.setattr("app.api.first_person._build_redis_client", lambda: mock_redis)

    response = test_client.post(
        "/api/first-person/ingest/video",
        json={
            "video_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "teacher_id": "preethaji",
            "rights_cleared": True,
        },
    )

    assert response.status_code == 202
    data = response.json()
    assert data["status"] == "queued"
    assert "job_id" in data
    mock_apply_async.assert_called_once()
    mock_redis.hset.assert_called_once()


def test_api_ingest_requires_explicit_rights_attestation(test_client, monkeypatch):
    mock_apply_async = MagicMock()
    monkeypatch.setattr(
        "tasks.ingest_tasks.ingest_first_person_video_task.apply_async", mock_apply_async
    )

    missing = test_client.post(
        "/api/first-person/ingest/video",
        json={"video_url": "https://youtu.be/dQw4w9WgXcQ"},
    )
    denied = test_client.post(
        "/api/first-person/ingest/video",
        json={"video_url": "https://youtu.be/dQw4w9WgXcQ", "rights_cleared": False},
    )
    assert missing.status_code == 422
    assert denied.status_code == 403

    disallowed_collection = test_client.post(
        "/api/first-person/ingest/video",
        json={
            "video_url": "https://youtu.be/dQw4w9WgXcQ",
            "rights_cleared": True,
            "collection": "attacker_controlled_collection",
        },
    )
    assert disallowed_collection.status_code == 403
    mock_apply_async.assert_not_called()


def test_api_enqueue_video_ingest_invalid_url(test_client):
    resp = test_client.post(
        "/api/first-person/ingest/video",
        json={"video_url": "https://vimeo.com/12345", "rights_cleared": True},
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
            "rights_cleared": True,
        }
    ).get()

    assert result["status"] == "success"
    assert result["job_id"] == "test_job_1"
    assert mock_execute.called
    assert mock_container.exact_cache.invalidate_all.called
    assert mock_container.semantic_cache.invalidate_all.called


def test_execute_first_person_video_ingestion_executes_pipeline(monkeypatch, tmp_path):
    progress_stages = []

    def on_prog(stage, pct):
        progress_stages.append((stage, pct))

    test_wav = tmp_path / "dQw4w9WgXcQ.wav"
    test_wav.write_bytes(b"RIFF" + b"\x00" * 2000)

    monkeypatch.setattr(
        "ingest.audio_transcriber.download_audio_stream",
        lambda url, target_dir: test_wav,
    )
    def _fake_run(*args, **kwargs):
        cmd = args[0] if args else []
        if cmd and len(cmd) > 0 and str(cmd[-1]).endswith(".wav"):
            from pathlib import Path

            Path(cmd[-1]).write_bytes(b"RIFF" + b"\x00" * 2000)
        return MagicMock(returncode=0)

    monkeypatch.setattr("subprocess.run", _fake_run)

    from ingest.video_pipeline import VideoIngestResult

    mock_pipeline = MagicMock()

    async def _mock_ingest(*args, **kwargs):
        return VideoIngestResult(
            chunks_ingested=5,
            duration_seconds=120.0,
            transcript_preview="Spiritual wisdom teaching...",
            status="success",
            point_ids=["pt1", "pt2", "pt3", "pt4", "pt5"],
        )

    mock_pipeline.ingest_video = _mock_ingest

    monkeypatch.setattr(
        "ingest.video_pipeline.VideoPipeline",
        lambda *args, **kwargs: mock_pipeline,
    )

    fake_redis = MagicMock()
    result = execute_first_person_video_ingestion(
        video_url="https://youtu.be/dQw4w9WgXcQ",
        job_id="00000000-0000-0000-0000-000000000001",
        rights_cleared=True,
        redis_client=fake_redis,
        on_progress=on_prog,
    )

    assert result["status"] == "success"
    assert result["clips_indexed"] == 5
    assert (FPJobStage.COMPLETED, 100) in progress_stages


def test_execute_first_person_video_ingestion_requires_rights_clearance():
    with pytest.raises(PermissionError, match="Explicit rights clearance"):
        execute_first_person_video_ingestion(
            video_url="https://youtu.be/dQw4w9WgXcQ",
            job_id="missing-rights",
        )
