"""Admin video exclusion is enforced on the general-RAG lane and the media stream.

The first-person lane is covered by ``test_fp_video_decisions.py``. This file pins the
other consumers of the same decisions file (``services/qdrant/source_policy.py``,
``rag/retrieval/rights_gate.py``, ``GET /api/media/videos/{id}``) so that one admin click
removes a video from every lane and restoring it brings it back.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import ingest as ingest_api
from app.config import settings
from rag.retrieval.rights_gate import ContentRightsGate
from services import first_person_video_decisions as fvd
from services.first_person_video_decisions import VideoDecisionStore
from services.qdrant.source_policy import is_blocked_source

VID = "abcdefghijk"
OTHER = "lmnopqrstuv"


@pytest.fixture
def decisions_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "first_person_video_decisions_dir", str(tmp_path / "dec"))
    fvd._CACHE.clear()
    fvd._ERROR_LOG_AT.clear()
    yield tmp_path / "dec"
    fvd._CACHE.clear()


def _exclude(video_id: str = VID) -> None:
    VideoDecisionStore().set_decision(
        video_id, actor="admin-1", admin_approved=False, reason="excluded for test"
    )


def _allow(video_id: str = VID) -> None:
    VideoDecisionStore().set_decision(
        video_id, actor="admin-1", admin_approved=True, reason="restored for test"
    )


# ---------------------------------------------------------------- general RAG lane
def test_source_policy_blocks_and_restores_by_video_id(decisions_dir):
    doc = {"video_id": VID, "source_url": "https://example.org/x"}
    assert is_blocked_source(doc) is False
    _exclude()
    assert is_blocked_source(doc) is True
    assert is_blocked_source({"video_id": OTHER}) is False
    _allow()
    assert is_blocked_source(doc) is False


def test_source_policy_blocks_by_youtube_url_when_payload_has_no_video_id(decisions_dir):
    _exclude()
    assert is_blocked_source({"source_url": f"https://www.youtube.com/watch?v={VID}&t=5"}) is True
    assert is_blocked_source({"source": f"https://youtu.be/{VID}"}) is True


def test_source_policy_blocks_direct_video_urls(decisions_dir):
    direct = "0123456789a"
    _exclude(direct)
    assert is_blocked_source({"source_url": f"video:{direct}"}) is True
    assert is_blocked_source({"source_url": f"/api/media/videos/{direct}"}) is True


def test_source_policy_fails_closed_on_corrupt_decisions_file(decisions_dir):
    decisions_dir.mkdir(parents=True)
    (decisions_dir / fvd.DECISIONS_FILENAME).write_text("{not json", encoding="utf-8")
    assert is_blocked_source({"video_id": VID}) is True


def test_rights_gate_rejects_excluded_video_even_when_licensed(decisions_dir):
    chunk = {"id": "c1", "video_id": VID, "domain_rights_status": "licensed"}
    assert ContentRightsGate.validate_rights(chunk) is True
    _exclude()
    assert ContentRightsGate.validate_rights(chunk) is False
    _allow()
    assert ContentRightsGate.validate_rights(chunk) is True


def test_human_speaker_rejection_also_blocks(decisions_dir):
    VideoDecisionStore().set_decision(
        VID, actor="admin-1", human_speaker_check="rejected", reason="not the teacher"
    )
    assert is_blocked_source({"video_id": VID}) is True


# ---------------------------------------------------------------- media stream
@pytest.fixture
def media_client(tmp_path, monkeypatch, decisions_dir):
    video = tmp_path / f"{VID}.mp4"
    video.write_bytes(bytes(range(256)) * 4)  # 1024 bytes
    monkeypatch.setattr(ingest_api, "_resolve_video_file_path", lambda _vid: str(video))
    app = FastAPI()
    app.include_router(ingest_api.router, prefix="/api")
    return TestClient(app)


def test_media_stream_serves_partial_content(media_client):
    resp = media_client.get(f"/api/media/videos/{VID}", headers={"Range": "bytes=10-19"})
    assert resp.status_code == 206
    assert resp.headers["content-range"] == "bytes 10-19/1024"
    assert resp.content == bytes(range(10, 20))


def test_media_stream_suffix_range_and_416(media_client):
    tail = media_client.get(f"/api/media/videos/{VID}", headers={"Range": "bytes=-4"})
    assert tail.status_code == 206
    assert tail.headers["content-range"] == "bytes 1020-1023/1024"
    bad = media_client.get(f"/api/media/videos/{VID}", headers={"Range": "bytes=5000-"})
    assert bad.status_code == 416
    assert bad.headers["content-range"] == "bytes */1024"


def test_media_stream_returns_404_for_excluded_video_and_200_after_restore(media_client):
    assert media_client.get(f"/api/media/videos/{VID}").status_code == 200
    _exclude()
    assert media_client.get(f"/api/media/videos/{VID}").status_code == 404
    assert (
        media_client.get(f"/api/media/videos/{VID}", headers={"Range": "bytes=0-1"}).status_code
        == 404
    )
    _allow()
    assert media_client.get(f"/api/media/videos/{VID}").status_code == 200


@pytest.mark.parametrize(
    "header,size,expected",
    [
        ("bytes=0-", 100, (0, 99)),
        ("bytes=90-200", 100, (90, 99)),
        ("bytes=-30", 100, (70, 99)),
        ("bytes=-500", 100, (0, 99)),
        ("bytes=0-1,5-6", 100, None),  # multi-range: serve whole file
        ("items=0-1", 100, None),
        ("bytes=-", 100, None),
    ],
)
def test_parse_byte_range(header, size, expected):
    assert ingest_api._parse_byte_range(header, size) == expected


@pytest.mark.parametrize("header", ["bytes=100-", "bytes=50-10", "bytes=-0"])
def test_parse_byte_range_unsatisfiable(header):
    with pytest.raises(ValueError):
        ingest_api._parse_byte_range(header, 100)


# ---------------------------------------------------------------- upload route
class _FakeJobs:
    """Records the ingest_jobs rows the route writes."""

    def __init__(self):
        self.updates: list[dict] = []

    def table(self, _name):
        return self

    def insert(self, _row):
        return self

    def update(self, row):
        self.updates.append(row)
        return self

    def eq(self, *_a):
        return self

    def execute(self):
        from types import SimpleNamespace

        return SimpleNamespace(data=[{"id": "job-1"}])


@pytest.fixture
def upload_client(tmp_path, monkeypatch, decisions_dir):
    from types import SimpleNamespace

    from app.dependencies import get_container_async
    from services.auth_service import require_aal2
    from services.tenant_context import set_tenant_from_request

    jobs = _FakeJobs()
    container = SimpleNamespace(
        supabase_client=jobs,
        qdrant=object(),
        embedding=object(),
        settings=SimpleNamespace(qdrant_collection="spiritual_wisdom_contextual"),
        graph_db=None,
    )
    monkeypatch.setattr(ingest_api, "_video_storage_dir", lambda: str(tmp_path))
    monkeypatch.setattr(
        ingest_api.subprocess,
        "run",
        lambda *a, **k: __import__("types").SimpleNamespace(returncode=1),
    )

    app = FastAPI()
    app.include_router(ingest_api.router, prefix="/api")
    app.dependency_overrides[require_aal2] = lambda: {"id": "a", "is_superuser": True}
    app.dependency_overrides[get_container_async] = lambda: container
    app.dependency_overrides[set_tenant_from_request] = lambda: None
    return TestClient(app, raise_server_exceptions=False), jobs


def test_upload_failure_is_reported_and_never_queues_a_placeholder_chunk(
    upload_client, monkeypatch
):
    import ingest.video_pipeline as vp
    import tasks.ingest_tasks as tasks

    class _Boom:
        def __init__(self, *a, **k):
            pass

        async def ingest_video(self, _path):
            raise RuntimeError("whisper out of memory")

    queued: list = []
    monkeypatch.setattr(vp, "VideoPipeline", _Boom)
    monkeypatch.setattr(
        tasks.ingest_document_task, "apply_async", lambda *a, **k: queued.append((a, k))
    )

    client, jobs = upload_client
    resp = client.post(
        "/api/ingest/upload-video",
        files={"file": ("talk.mp4", b"not really a video", "video/mp4")},
        data={"title": "Talk", "speaker": "Sri Krishnaji"},
    )
    assert resp.status_code == 502
    assert "RuntimeError" in resp.json()["detail"]
    assert "out of memory" not in resp.text  # internal message is not echoed
    assert queued == []
    assert any(u.get("status") == "failed" for u in jobs.updates)


def test_video_id_pattern_ignores_longer_tokens(decisions_dir):
    from services.qdrant.source_policy import VIDEO_ID_IN_SOURCE

    assert VIDEO_ID_IN_SOURCE.search(f"https://youtu.be/{VID}?t=3").group(1) == VID
    assert VIDEO_ID_IN_SOURCE.search(f"https://www.youtube.com/watch?v={VID}&x=1").group(1) == VID
    assert VIDEO_ID_IN_SOURCE.search("https://x.org/videos/" + "a" * 64) is None
    assert VIDEO_ID_IN_SOURCE.search(f"https://x.org/?nv={VID}") is None
