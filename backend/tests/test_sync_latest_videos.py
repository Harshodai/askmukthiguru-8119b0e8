# ponytail: unit tests for sync_latest_videos
import json
import sys
from pathlib import Path

import pytest

# Ensure repository root is on sys.path
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# D1 full-suite fix (2026-10-03): patch THIS module object, not the dotted
# string. Other tests evict/re-import "scripts.ops*" from sys.modules mid-run
# (test_retention_cron, test_cleanup_inactive), so monkeypatch's string
# resolver can land on a fresh module object while TargetSynchronizer below
# keeps running the object imported here — the mock silently misses and the
# real yt-dlp channel scan runs inside the test. Binding to the same object
# the code under test uses is immune to sys.modules churn.
import scripts.ops.sync_latest_videos as _sync_module
from scripts.ops.sync_latest_videos import (
    TargetSynchronizer,
    fetch_channel_videos,
    filter_qualifying_videos,
)


@pytest.fixture
def sync_env(tmp_path: Path):
    archive_dir = tmp_path / "audio_archive"
    archive_dir.mkdir(parents=True, exist_ok=True)
    manifest_file = archive_dir / "manifest.json"

    manifest_data = {
        "version": "1.0",
        "archive_root": str(archive_dir),
        "stats": {
            "total_targets": 2,
            "archived_count": 1,
            "missing_count": 1,
            "total_duration_hours": 0.5,
            "total_bytes": 50000000,
        },
        "videos": {
            "existing_vid_1": {"status": "archived", "duration_s": 1800.0, "bytes": 50000000},
            "existing_vid_2": {"status": "pending_download", "duration_s": 600.0},
        },
    }
    manifest_file.write_text(json.dumps(manifest_data))

    targets_file = tmp_path / "targets.json"
    targets_data = {
        "targets_515": [
            {"video_id": "existing_vid_1", "rights_cleared": True},
            {"video_id": "existing_vid_2", "rights_cleared": True},
        ],
        "summary": {"total_targets": 2},
    }
    targets_file.write_text(json.dumps(targets_data))

    return {
        "archive_dir": archive_dir,
        "manifest_file": manifest_file,
        "targets_file": targets_file,
    }


def test_filter_qualifying_videos():
    # ponytail: verify filtering of shorts and existing video IDs
    discovered = [
        {"video_id": "existing_1", "duration_s": 500.0, "title": "Existing Long"},
        {"video_id": "short_1", "duration_s": 45.0, "title": "Short Clip"},
        {"video_id": "new_discourse_1", "duration_s": 300.0, "title": "New Discourse"},
        {"video_id": "new_discourse_2", "duration_s": 1200.0, "title": "Deep Meditation"},
    ]
    existing = {"existing_1"}

    qualifying = filter_qualifying_videos(discovered, existing, min_duration_s=90.0)
    assert len(qualifying) == 2
    assert qualifying[0]["video_id"] == "new_discourse_1"
    assert qualifying[1]["video_id"] == "new_discourse_2"


def test_fetch_channel_videos_mocked(monkeypatch):
    # ponytail: test parsing of yt-dlp flat playlist output
    mock_stdout = (
        "vid123\t450.5\tSoul Sync Meditation\t20260901\nvid456\t30.0\tTeaser Short\t20260902\n"
    )

    class MockCompletedProcess:
        returncode = 0
        stdout = mock_stdout
        stderr = ""

    monkeypatch.setattr("subprocess.run", lambda *args, **kwargs: MockCompletedProcess())

    videos = fetch_channel_videos("https://mock.channel", limit=10)
    assert len(videos) == 2
    assert videos[0]["video_id"] == "vid123"
    assert videos[0]["duration_s"] == 450.5
    assert videos[0]["title"] == "Soul Sync Meditation"
    assert videos[1]["duration_s"] == 30.0


def test_sync_dry_run_leaves_files_untouched(sync_env, monkeypatch):
    # ponytail: verify dry-run does not write to disk
    mock_videos = [
        {
            "video_id": "new_vid_1",
            "duration_s": 400.0,
            "title": "New Teaching",
            "upload_date": "20260915",
        },
    ]
    monkeypatch.setattr(_sync_module, "fetch_channel_videos", lambda *a, **k: mock_videos)

    syncer = TargetSynchronizer(
        targets_file=sync_env["targets_file"],
        archive_dir=sync_env["archive_dir"],
    )

    res = syncer.sync(dry_run=True)
    assert res["applied"] is False
    assert res["qualifying_count"] == 1

    # Targets file should remain unchanged
    data = json.loads(sync_env["targets_file"].read_text())
    assert len(data["targets_515"]) == 2


def test_sync_apply_updates_targets_and_manifest(sync_env, monkeypatch):
    # ponytail: verify apply mode updates targets and manifest and creates backups
    mock_videos = [
        {
            "video_id": "new_vid_1",
            "duration_s": 600.0,
            "title": "New Teaching",
            "upload_date": "20260915",
        },
        {
            "video_id": "existing_vid_1",
            "duration_s": 1800.0,
            "title": "Existing",
            "upload_date": "20260901",
        },
    ]
    monkeypatch.setattr(_sync_module, "fetch_channel_videos", lambda *a, **k: mock_videos)

    syncer = TargetSynchronizer(
        targets_file=sync_env["targets_file"],
        archive_dir=sync_env["archive_dir"],
    )

    res = syncer.sync(dry_run=False)
    assert res["applied"] is True
    assert res["qualifying_count"] == 1

    # Verify targets.json
    t_data = json.loads(sync_env["targets_file"].read_text())
    assert len(t_data["targets_515"]) == 3
    new_entry = [t for t in t_data["targets_515"] if t["video_id"] == "new_vid_1"][0]
    assert new_entry["rights_cleared"] is True
    assert new_entry["status"] == "to_asr"

    # Verify manifest.json
    m_data = json.loads(sync_env["manifest_file"].read_text())
    assert "new_vid_1" in m_data["videos"]
    assert m_data["videos"]["new_vid_1"]["status"] == "pending_download"
    assert m_data["stats"]["total_targets"] == 3
    assert m_data["stats"]["missing_count"] == 2  # existing_vid_2 + new_vid_1
    assert m_data["stats"]["archived_count"] == 1

    # Verify backups created
    backups = list((sync_env["archive_dir"] / "backups").glob("*.bak"))
    assert len(backups) >= 1
