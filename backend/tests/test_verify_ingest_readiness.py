# ponytail: unit tests for pre-flight ingestion readiness inspector
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# Ensure repository root is on sys.path
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.ops.verify_ingest_readiness import (
    IngestReadinessInspector,
)


@pytest.fixture
def test_env(tmp_path: Path):
    archive_dir = tmp_path / "audio_archive"
    archive_dir.mkdir(parents=True, exist_ok=True)
    manifest_file = archive_dir / "manifest.json"

    manifest_data = {
        "version": "1.0",
        "archive_root": str(archive_dir),
        "stats": {
            "total_targets": 515,
            "archived_count": 70,
            "missing_count": 445,
            "total_duration_hours": 8.89,
            "total_bytes": 1024647168,
        },
        "videos": {f"vid_{i}": {"status": "archived"} for i in range(70)},
    }
    manifest_file.write_text(json.dumps(manifest_data))

    targets_file = tmp_path / "targets.json"
    targets_data = {
        "targets_515": [{"video_id": f"vid_{i}", "rights_cleared": True} for i in range(515)]
    }
    targets_file.write_text(json.dumps(targets_data))

    return {
        "archive_dir": archive_dir,
        "targets_file": targets_file,
    }


def test_check_disk_space(test_env, monkeypatch):
    # ponytail: test disk space evaluation with mocked shutil.disk_usage
    inspector = IngestReadinessInspector(
        archive_root=test_env["archive_dir"],
        targets_file=test_env["targets_file"],
    )

    # 1. Healthy disk space (50 GB free)
    monkeypatch.setattr(
        "shutil.disk_usage",
        lambda p: MagicMock(free=50 * 1024**3, total=500 * 1024**3),
    )
    r1 = inspector.check_disk_space()
    assert r1.passed is True
    assert r1.status == "PASS"

    # 2. Warning disk space (8 GB free)
    monkeypatch.setattr(
        "shutil.disk_usage",
        lambda p: MagicMock(free=8 * 1024**3, total=500 * 1024**3),
    )
    r2 = inspector.check_disk_space(min_gb_required=10.0)
    assert r2.passed is True
    assert r2.status == "WARN"

    # 3. Failing disk space (3 GB free)
    monkeypatch.setattr(
        "shutil.disk_usage",
        lambda p: MagicMock(free=3 * 1024**3, total=500 * 1024**3),
    )
    r3 = inspector.check_disk_space()
    assert r3.passed is False
    assert r3.status == "FAIL"


def test_check_audio_archive(test_env):
    # ponytail: test manifest validation
    inspector = IngestReadinessInspector(
        archive_root=test_env["archive_dir"],
        targets_file=test_env["targets_file"],
    )
    r = inspector.check_audio_archive()
    assert r.passed is True
    assert r.status == "PASS"
    assert "70 archived" in r.message

    # Test missing manifest
    missing_inspector = IngestReadinessInspector(
        archive_root=test_env["archive_dir"] / "nonexistent",
        targets_file=test_env["targets_file"],
    )
    r_missing = missing_inspector.check_audio_archive()
    assert r_missing.passed is False
    assert r_missing.status == "FAIL"


def test_check_system_binaries(monkeypatch):
    # ponytail: test system binary detection
    inspector = IngestReadinessInspector()

    # Both found
    monkeypatch.setattr("shutil.which", lambda b: f"/usr/local/bin/{b}")
    r_pass = inspector.check_system_binaries()
    assert r_pass.passed is True
    assert r_pass.status == "PASS"

    # Missing ffmpeg
    def mock_which(b):
        return None if b == "ffmpeg" else f"/usr/local/bin/{b}"

    monkeypatch.setattr("shutil.which", mock_which)
    r_fail = inspector.check_system_binaries()
    assert r_fail.passed is False
    assert r_fail.status == "FAIL"
    assert "ffmpeg" in r_fail.message


def test_check_host_side_invariant(monkeypatch):
    # ponytail: verify detection of Docker container execution
    inspector = IngestReadinessInspector()

    # Host-side
    r_host = inspector.check_host_side_invariant()
    # In test runner environment, should pass unless run inside Docker
    assert isinstance(r_host.passed, bool)

    # Simulated Docker
    monkeypatch.setattr("pathlib.Path.is_file", lambda p: str(p) == "/.dockerenv")
    r_docker = inspector.check_host_side_invariant()
    assert r_docker.passed is False
    assert r_docker.status == "FAIL"
    assert "inside Docker container" in r_docker.message


def test_check_target_corpus(test_env):
    # ponytail: test targets_515 inventory validation
    inspector = IngestReadinessInspector(
        archive_root=test_env["archive_dir"],
        targets_file=test_env["targets_file"],
    )
    r = inspector.check_target_corpus()
    assert r.passed is True
    assert r.status == "PASS"
    assert "515" in r.message


def test_check_qdrant_status_mocked(monkeypatch):
    # ponytail: test Qdrant status inspection with mocked urllib
    inspector = IngestReadinessInspector()

    # Mock healthy response with indexes
    mock_payload = {
        "result": {
            "status": "green",
            "points_count": 144,
            "payload_schema": {
                "is_verbatim": {"data_type": "keyword"},
                "rights_cleared": {"data_type": "keyword"},
            },
        }
    }

    class MockResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def read(self):
            return json.dumps(mock_payload).encode("utf-8")

    monkeypatch.setattr("urllib.request.urlopen", lambda req, timeout=3.0: MockResponse())
    r = inspector.check_qdrant_status()
    assert r.passed is True
    assert r.status == "PASS"
    assert "144 points" in r.message


def test_inspect_all_and_dashboard(test_env, monkeypatch):
    # ponytail: verify end-to-end dashboard rendering
    inspector = IngestReadinessInspector(
        archive_root=test_env["archive_dir"],
        targets_file=test_env["targets_file"],
    )

    # Stub hardware & system checks
    monkeypatch.setattr("shutil.which", lambda b: f"/usr/local/bin/{b}")
    monkeypatch.setattr(
        "shutil.disk_usage",
        lambda p: MagicMock(free=50 * 1024**3, total=500 * 1024**3),
    )

    all_passed, results = inspector.inspect_all()
    dashboard = inspector.format_dashboard(all_passed)
    assert "ASKMUKTHIGURU INGESTION READINESS INSPECTOR" in dashboard
    assert len(results) == 10
