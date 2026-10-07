# ponytail: test suite for durable audio archive foundation
import json
import sys
from pathlib import Path

import pytest

# Ensure repository root is on sys.path
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.ops.audio_archive import (
    AudioArchive,
    compute_sha256,
    create_mock_wav,
    get_path,
    inspect_wav,
    migrate,
    run_self_check,
    stats,
    verify,
)


@pytest.fixture
def mock_env(tmp_path: Path):
    source_dir = tmp_path / "source"
    archive_dir = tmp_path / "archive"
    targets_file = tmp_path / "targets.json"
    source_dir.mkdir(parents=True, exist_ok=True)

    targets_data = {
        "targets_515": [
            {"video_id": "vid_target_1", "rights_cleared": True},
            {"video_id": "vid_target_2", "rights_cleared": True},
            {"video_id": "vid_target_3", "rights_cleared": True},
        ]
    }
    targets_file.write_text(json.dumps(targets_data))

    return {
        "source_dir": source_dir,
        "archive_dir": archive_dir,
        "targets_file": targets_file,
    }


def test_create_mock_wav_and_inspect(tmp_path: Path):
    # ponytail: verify mock wav generation and stdlib wave inspection
    wav_path = tmp_path / "sample.wav"
    create_mock_wav(wav_path, duration_s=1.5, sample_rate=16000, channels=1)

    assert wav_path.is_file()
    channels, sample_rate, duration_s = inspect_wav(wav_path)
    assert channels == 1
    assert sample_rate == 16000
    assert duration_s == 1.5

    digest = compute_sha256(wav_path)
    assert isinstance(digest, str)
    assert len(digest) == 64


def test_pre_registration_targets(mock_env):
    # ponytail: verify pre-registration of all targets as pending_download
    archive = AudioArchive(
        archive_root=mock_env["archive_dir"],
        source_dir=mock_env["source_dir"],
        targets_file=mock_env["targets_file"],
    )

    # Migrate with empty source dir
    manifest = archive.migrate()

    assert manifest["stats"]["total_targets"] == 3
    assert manifest["stats"]["archived_count"] == 0
    assert manifest["stats"]["missing_count"] == 3
    assert manifest["stats"]["total_duration_hours"] == 0.0
    assert manifest["stats"]["total_bytes"] == 0

    for tid in ["vid_target_1", "vid_target_2", "vid_target_3"]:
        assert tid in manifest["videos"]
        entry = manifest["videos"][tid]
        assert entry["video_id"] == tid
        assert entry["status"] == "pending_download"
        assert entry["filename"] is None
        assert entry["sha256"] is None
        assert entry["bytes"] is None
        assert entry["duration_s"] is None
        assert entry["rights_status"] == "cleared"
        assert entry["source_url"] == f"https://www.youtube.com/watch?v={tid}"
        assert entry["archived_at"] is None


def test_manifest_schema_and_migration(mock_env):
    # ponytail: verify manifest schema and wav migration
    # Create 1 target wav and 1 non-target wav in source
    create_mock_wav(mock_env["source_dir"] / "vid_target_1.wav", duration_s=2.0)
    create_mock_wav(mock_env["source_dir"] / "vid_unplanned.wav", duration_s=3.0)

    archive = AudioArchive(
        archive_root=mock_env["archive_dir"],
        source_dir=mock_env["source_dir"],
        targets_file=mock_env["targets_file"],
    )

    manifest = archive.migrate()

    # Schema validation
    assert manifest["version"] == "1.0"
    assert "updated_at" in manifest
    assert manifest["archive_root"] == str(mock_env["archive_dir"].resolve())
    assert "stats" in manifest
    assert "videos" in manifest

    stats_obj = manifest["stats"]
    assert stats_obj["total_targets"] == 3
    assert stats_obj["archived_count"] == 2
    assert stats_obj["missing_count"] == 2  # vid_target_2 and vid_target_3 still pending
    assert stats_obj["total_duration_hours"] == round((2.0 + 3.0) / 3600.0, 2)
    assert stats_obj["total_bytes"] > 0

    # Archived entry validation
    target_entry = manifest["videos"]["vid_target_1"]
    assert target_entry["status"] == "archived"
    assert target_entry["filename"] == "vid_target_1.wav"
    assert target_entry["duration_s"] == 2.0
    assert target_entry["sample_rate"] == 16000
    assert target_entry["channels"] == 1
    assert len(target_entry["sha256"]) == 64
    assert target_entry["bytes"] > 0
    assert target_entry["archived_at"] is not None

    # Pending entry validation
    pending_entry = manifest["videos"]["vid_target_2"]
    assert pending_entry["status"] == "pending_download"
    assert pending_entry["filename"] is None

    # Unplanned entry validation
    unplanned_entry = manifest["videos"]["vid_unplanned"]
    assert unplanned_entry["status"] == "archived"
    assert unplanned_entry["filename"] == "vid_unplanned.wav"
    assert unplanned_entry["duration_s"] == 3.0

    # Check that wavs exist in archive wavs directory
    assert (mock_env["archive_dir"] / "wavs" / "vid_target_1.wav").is_file()
    assert (mock_env["archive_dir"] / "wavs" / "vid_unplanned.wav").is_file()

    # Idempotence: re-running migration preserves original archived_at
    orig_archived_at = target_entry["archived_at"]
    manifest_2 = archive.migrate()
    assert manifest_2["videos"]["vid_target_1"]["archived_at"] == orig_archived_at
    assert manifest_2["stats"]["archived_count"] == 2


def test_verify_passes_and_detects_tampering(mock_env):
    # ponytail: verify integrity checker passes on clean archive and catches tampering
    create_mock_wav(mock_env["source_dir"] / "vid_target_1.wav", duration_s=1.0)
    archive = AudioArchive(
        archive_root=mock_env["archive_dir"],
        source_dir=mock_env["source_dir"],
        targets_file=mock_env["targets_file"],
    )
    archive.migrate()

    # Clean verification passes
    passed, errors = archive.verify()
    assert passed is True
    assert len(errors) == 0

    # Tamper with file content
    archived_wav = mock_env["archive_dir"] / "wavs" / "vid_target_1.wav"
    with open(archived_wav, "r+b") as f:
        f.seek(50)
        f.write(b"\x12\x34\x56\x78")

    # Verification must fail and report checksum mismatch
    passed, errors = archive.verify()
    assert passed is False
    assert len(errors) == 1
    assert errors[0]["video_id"] == "vid_target_1"
    assert errors[0]["type"] == "checksum_mismatch"


def test_verify_detects_missing_file(mock_env):
    # ponytail: verify detection of deleted/missing archived file
    create_mock_wav(mock_env["source_dir"] / "vid_target_1.wav", duration_s=1.0)
    archive = AudioArchive(
        archive_root=mock_env["archive_dir"],
        source_dir=mock_env["source_dir"],
        targets_file=mock_env["targets_file"],
    )
    archive.migrate()

    archived_wav = mock_env["archive_dir"] / "wavs" / "vid_target_1.wav"
    archived_wav.unlink()

    passed, errors = archive.verify()
    assert passed is False
    assert len(errors) == 1
    assert errors[0]["video_id"] == "vid_target_1"
    assert errors[0]["type"] == "missing_file"


def test_verify_detects_corrupt_wav_header(mock_env):
    # ponytail: verify detection of corrupt WAV header
    create_mock_wav(mock_env["source_dir"] / "vid_target_1.wav", duration_s=1.0)
    archive = AudioArchive(
        archive_root=mock_env["archive_dir"],
        source_dir=mock_env["source_dir"],
        targets_file=mock_env["targets_file"],
    )
    archive.migrate()

    # Overwrite manifest hash with the hash of corrupted data so checksum check passes,
    # but wav header inspection fails
    archived_wav = mock_env["archive_dir"] / "wavs" / "vid_target_1.wav"
    garbage_bytes = b"NOT_A_WAV_FILE_HEADER_GARBAGE" * 10
    archived_wav.write_bytes(garbage_bytes)

    manifest = archive.load_manifest()
    manifest["videos"]["vid_target_1"]["sha256"] = compute_sha256(archived_wav)
    manifest["videos"]["vid_target_1"]["bytes"] = len(garbage_bytes)
    archive.save_manifest(manifest)

    passed, errors = archive.verify()
    assert passed is False
    assert len(errors) == 1
    assert errors[0]["video_id"] == "vid_target_1"
    assert errors[0]["type"] == "corrupt_wav"


def test_get_path_lookup_behavior(mock_env):
    # ponytail: test get_path lookup behavior for archived, pending, and unknown videos
    create_mock_wav(mock_env["source_dir"] / "vid_target_1.wav", duration_s=1.0)
    archive = AudioArchive(
        archive_root=mock_env["archive_dir"],
        source_dir=mock_env["source_dir"],
        targets_file=mock_env["targets_file"],
    )
    archive.migrate()

    # Archived video
    path1 = archive.get_path("vid_target_1")
    assert path1 is not None
    assert path1.is_file()
    assert path1.name == "vid_target_1.wav"

    # Pending video (registered but not downloaded)
    assert archive.get_path("vid_target_2") is None

    # Completely unknown video
    assert archive.get_path("vid_unknown") is None


def test_excluded_directories(mock_env):
    # ponytail: ensure virtualenvs, caches, and archive itself are excluded during scan
    venv_dir = mock_env["source_dir"] / "venv" / "lib"
    venv_dir.mkdir(parents=True, exist_ok=True)
    create_mock_wav(venv_dir / "vid_venv.wav", duration_s=1.0)

    pycache_dir = mock_env["source_dir"] / "__pycache__"
    pycache_dir.mkdir(parents=True, exist_ok=True)
    create_mock_wav(pycache_dir / "vid_cache.wav", duration_s=1.0)

    archive = AudioArchive(
        archive_root=mock_env["archive_dir"],
        source_dir=mock_env["source_dir"],
        targets_file=mock_env["targets_file"],
    )
    manifest = archive.migrate()

    assert "vid_venv" not in manifest["videos"]
    assert "vid_cache" not in manifest["videos"]
    assert not (mock_env["archive_dir"] / "wavs" / "vid_venv.wav").exists()


def test_convenience_functions_and_stats(mock_env):
    # ponytail: test module-level migrate, verify, stats, get_path convenience functions
    create_mock_wav(mock_env["source_dir"] / "vid_target_1.wav", duration_s=1.0)

    m = migrate(
        archive_root=mock_env["archive_dir"],
        source_dir=mock_env["source_dir"],
        targets_file=mock_env["targets_file"],
    )
    assert m["stats"]["archived_count"] == 1

    ok, errors = verify(archive_root=mock_env["archive_dir"])
    assert ok is True
    assert len(errors) == 0

    p = get_path("vid_target_1", archive_root=mock_env["archive_dir"])
    assert p is not None and p.name == "vid_target_1.wav"

    stats_output = stats(archive_root=mock_env["archive_dir"])
    assert "AskMukthiGuru Audio Archive Statistics" in stats_output
    assert "Archived Count:        1" in stats_output


def test_run_self_check():
    # ponytail: test the runnable self-check function
    assert run_self_check() is True


def test_cli_main_commands(mock_env, monkeypatch, capsys):
    # ponytail: test CLI entry points for migrate, verify, stats, and get-path
    from scripts.ops.audio_archive import main

    create_mock_wav(mock_env["source_dir"] / "vid_cli.wav", duration_s=1.0)

    # 1. Test migrate command
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "audio_archive.py",
            "migrate",
            "--archive-dir",
            str(mock_env["archive_dir"]),
            "--source-dir",
            str(mock_env["source_dir"]),
            "--targets-file",
            str(mock_env["targets_file"]),
        ],
    )
    with pytest.raises(SystemExit) as excinfo:
        main()
    assert excinfo.value.code == 0
    captured = capsys.readouterr()
    assert "Migration completed successfully!" in captured.out

    # 2. Test verify command
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "audio_archive.py",
            "verify",
            "--archive-dir",
            str(mock_env["archive_dir"]),
        ],
    )
    with pytest.raises(SystemExit) as excinfo:
        main()
    assert excinfo.value.code == 0
    captured = capsys.readouterr()
    assert "passed verification" in captured.out

    # 3. Test stats command
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "audio_archive.py",
            "stats",
            "--archive-dir",
            str(mock_env["archive_dir"]),
        ],
    )
    with pytest.raises(SystemExit) as excinfo:
        main()
    assert excinfo.value.code == 0
    captured = capsys.readouterr()
    assert "AskMukthiGuru Audio Archive Statistics" in captured.out

    # 4. Test get-path command (success)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "audio_archive.py",
            "get-path",
            "vid_cli",
            "--archive-dir",
            str(mock_env["archive_dir"]),
        ],
    )
    with pytest.raises(SystemExit) as excinfo:
        main()
    assert excinfo.value.code == 0
    captured = capsys.readouterr()
    assert captured.out.strip().endswith("vid_cli.wav")

    # 5. Test get-path command (missing)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "audio_archive.py",
            "get-path",
            "nonexistent_vid",
            "--archive-dir",
            str(mock_env["archive_dir"]),
        ],
    )
    with pytest.raises(SystemExit) as excinfo:
        main()
    assert excinfo.value.code == 1


def test_download_pending_mocked(mock_env, monkeypatch):
    # ponytail: test download_pending with mocked yt-dlp subprocess
    archive = AudioArchive(
        archive_root=mock_env["archive_dir"],
        source_dir=mock_env["source_dir"],
        targets_file=mock_env["targets_file"],
    )
    archive.migrate()

    def mock_run(cmd, capture_output=True, text=True, timeout=600):
        out_tmpl = cmd[cmd.index("-o") + 1]
        vid = Path(out_tmpl).stem
        wav_file = mock_env["archive_dir"] / "wavs" / f"{vid}.wav"
        create_mock_wav(wav_file, duration_s=4.0)

        class MockCompletedProcess:
            returncode = 0
            stdout = "Downloaded successfully"
            stderr = ""

        return MockCompletedProcess()

    monkeypatch.setattr("subprocess.run", mock_run)

    results = archive.download_pending(limit=2)
    assert results["total_candidates"] == 2
    assert results["succeeded"] == 2
    assert results["failed"] == 0

    manifest = archive.load_manifest()
    assert manifest["videos"]["vid_target_1"]["status"] == "archived"
    assert manifest["videos"]["vid_target_2"]["status"] == "archived"
    assert manifest["videos"]["vid_target_3"]["status"] == "pending_download"
    assert manifest["stats"]["archived_count"] == 2
    assert manifest["stats"]["missing_count"] == 1


def test_download_pending_partitioning(mock_env, monkeypatch):
    # ponytail: verify distributed worker partitioning
    archive = AudioArchive(
        archive_root=mock_env["archive_dir"],
        source_dir=mock_env["source_dir"],
        targets_file=mock_env["targets_file"],
    )
    archive.migrate()

    def mock_run(cmd, capture_output=True, text=True, timeout=600):
        out_tmpl = cmd[cmd.index("-o") + 1]
        vid = Path(out_tmpl).stem
        wav_file = mock_env["archive_dir"] / "wavs" / f"{vid}.wav"
        create_mock_wav(wav_file, duration_s=1.0)

        class MockCompletedProcess:
            returncode = 0
            stdout = "Downloaded successfully"
            stderr = ""

        return MockCompletedProcess()

    monkeypatch.setattr("subprocess.run", mock_run)

    # Worker 0 and Worker 1 partition all pending targets disjointly
    res0 = archive.download_pending(worker_id=0, num_workers=2)
    res1 = archive.download_pending(worker_id=1, num_workers=2)
    assert res0["total_candidates"] + res1["total_candidates"] == 3
    assert res0["total_candidates"] >= 1
    assert res1["total_candidates"] >= 1
    assert res0["succeeded"] + res1["succeeded"] == 3


def test_download_bot_detection_circuit_breaker(mock_env, monkeypatch):
    # ponytail: verify that 429/bot-detection halts immediately
    archive = AudioArchive(
        archive_root=mock_env["archive_dir"],
        source_dir=mock_env["source_dir"],
        targets_file=mock_env["targets_file"],
    )
    archive.migrate()

    def mock_run(cmd, capture_output=True, text=True, timeout=600):
        class MockCompletedProcess:
            returncode = 1
            stdout = ""
            stderr = "ERROR: [youtube] HTTP Error 429: Too Many Requests"

        return MockCompletedProcess()

    monkeypatch.setattr("subprocess.run", mock_run)

    results = archive.download_pending(limit=3)
    assert results["failed"] == 1
    assert any("Rate limit (429)" in err.get("error", "") for err in results["errors"])


def test_download_concurrent_worker_dedup(mock_env, monkeypatch):
    # ponytail: verify that videos already archived by another concurrent worker are never downloaded twice
    archive = AudioArchive(
        archive_root=mock_env["archive_dir"],
        source_dir=mock_env["source_dir"],
        targets_file=mock_env["targets_file"],
    )
    archive.migrate()

    download_calls = []

    def mock_run(cmd, capture_output=True, text=True, timeout=600):
        out_tmpl = cmd[cmd.index("-o") + 1]
        vid = Path(out_tmpl).stem
        download_calls.append(vid)
        wav_file = mock_env["archive_dir"] / "wavs" / f"{vid}.wav"
        create_mock_wav(wav_file, duration_s=1.0)

        class MockCompletedProcess:
            returncode = 0
            stdout = "Downloaded successfully"
            stderr = ""

        return MockCompletedProcess()

    monkeypatch.setattr("subprocess.run", mock_run)

    # First run downloads target
    res1 = archive.download_pending(limit=1)
    assert res1["succeeded"] == 1
    assert len(download_calls) == 1
    first_vid = download_calls[0]

    # Second worker attempts to download the exact same video
    # Because it is already marked "archived" in manifest, candidates count is 0
    res2 = archive.download_pending(video_ids=[first_vid])
    assert res2["total_candidates"] == 0
    # Crucial assertion: yt-dlp was NOT called a second time
    assert len(download_calls) == 1


def test_download_exponential_retry_and_cooldown(mock_env, monkeypatch):
    # ponytail: verify exponential backoff, retry cooldown, and retries exhausted transitions
    archive = AudioArchive(
        archive_root=mock_env["archive_dir"],
        source_dir=mock_env["source_dir"],
        targets_file=mock_env["targets_file"],
    )
    archive.migrate()

    should_fail = True

    def mock_run(cmd, capture_output=True, text=True, timeout=600):
        out_tmpl = cmd[cmd.index("-o") + 1]
        vid = Path(out_tmpl).stem
        if should_fail:

            class MockFailedProcess:
                returncode = 1
                stdout = ""
                stderr = "ERROR: connection reset by peer"

            return MockFailedProcess()
        else:
            wav_file = mock_env["archive_dir"] / "wavs" / f"{vid}.wav"
            create_mock_wav(wav_file, duration_s=1.0)

            class MockSuccessProcess:
                returncode = 0
                stdout = "Downloaded successfully"
                stderr = ""

            return MockSuccessProcess()

    monkeypatch.setattr("subprocess.run", mock_run)

    # 1. First attempt fails
    res1 = archive.download_pending(limit=1, max_retries=2, retry_cooldown_base_s=60.0)
    assert res1["failed"] == 1
    manifest = archive.load_manifest()
    # Check entry has retry_count 1 and retry_after
    failed_entries = [v for v in manifest["videos"].values() if v.get("retry_count") == 1]
    assert len(failed_entries) == 1
    entry = failed_entries[0]
    vid = entry["video_id"]
    assert entry["status"] == "pending_download"
    assert entry["retry_after"] is not None

    # 2. Immediate second call finds 0 candidates due to active cooldown
    res2 = archive.download_pending(video_ids=[vid], max_retries=2)
    assert res2["total_candidates"] == 0

    # 3. Simulate cooldown expiration and success
    entry["retry_after"] = None
    archive.save_manifest(manifest)
    should_fail = False

    res3 = archive.download_pending(video_ids=[vid], max_retries=2)
    assert res3["succeeded"] == 1
    manifest_after = archive.load_manifest()
    assert manifest_after["videos"][vid]["status"] == "archived"
