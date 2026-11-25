"""Unit tests for the Redis RDB backup and verification helper."""

from __future__ import annotations

import hashlib
import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "backup" / "redis_rdb_backup.py"
SPEC = importlib.util.spec_from_file_location("redis_rdb_backup_under_test", SCRIPT)
assert SPEC and SPEC.loader
REDIS_BACKUP = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = REDIS_BACKUP
SPEC.loader.exec_module(REDIS_BACKUP)


def make_rdb(path: Path, payload: bytes = b"test-payload") -> Path:
    path.write_bytes(b"REDIS0011" + payload)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    Path(f"{path}.sha256").write_text(f"{digest}  {path.name}\n", encoding="utf-8")
    return path


def test_verify_rdb_validates_signature_and_sidecar(tmp_path):
    path = make_rdb(tmp_path / "dump.rdb")
    result = REDIS_BACKUP.verify_rdb(path)
    assert result["rdb_version"] == "0011"
    assert result["size_bytes"] == path.stat().st_size


def test_verify_rdb_rejects_invalid_signature(tmp_path):
    path = tmp_path / "dump.rdb"
    path.write_bytes(b"NOTRDB000" + b"payload")
    Path(f"{path}.sha256").write_text("invalid\n")
    with pytest.raises(REDIS_BACKUP.RedisBackupError, match="signature"):
        REDIS_BACKUP.verify_rdb(path)


def test_verify_rdb_rejects_missing_sidecar(tmp_path):
    path = tmp_path / "dump.rdb"
    path.write_bytes(b"REDIS0011payload")
    with pytest.raises(REDIS_BACKUP.RedisBackupError, match="sidecar missing"):
        REDIS_BACKUP.verify_rdb(path)


def test_verify_rdb_rejects_checksum_mismatch(tmp_path):
    path = tmp_path / "dump.rdb"
    path.write_bytes(b"REDIS0011payload")
    Path(f"{path}.sha256").write_text(f"{'0' * 64}  {path.name}\n")
    with pytest.raises(REDIS_BACKUP.RedisBackupError, match="SHA-256"):
        REDIS_BACKUP.verify_rdb(path)


def test_parse_config_pair_requires_expected_key():
    assert REDIS_BACKUP._parse_config_pair("dir\n/data\n", "dir") == "/data"
    with pytest.raises(REDIS_BACKUP.RedisBackupError, match="unexpected"):
        REDIS_BACKUP._parse_config_pair("dbfilename\ndump.rdb\n", "dir")


def test_parse_info_extracts_fields_and_ignores_section_headers():
    result = REDIS_BACKUP._parse_info(
        "# Persistence\nrdb_bgsave_in_progress:0\nrdb_last_bgsave_status:ok\n"
    )
    assert result == {
        "rdb_bgsave_in_progress": "0",
        "rdb_last_bgsave_status": "ok",
    }


def test_backup_uses_write_key_from_environment(monkeypatch, tmp_path):
    monkeypatch.setenv("REDIS_PASSWORD", "redis-test-password")
    with patch.object(
        REDIS_BACKUP,
        "_redis_cli",
        side_effect=[
            "# Persistence\nrdb_bgsave_in_progress:0\nrdb_last_save_time:100\n",
            "dir\n/data\n",
            "dbfilename\ndump.rdb\n",
            "Background saving started",
            "# Persistence\nrdb_bgsave_in_progress:0\nrdb_last_save_time:102\nrdb_last_bgsave_status:ok\n",
        ],
    ) as cli, patch.object(REDIS_BACKUP.time, "sleep"), patch.object(
        REDIS_BACKUP, "_docker"
    ) as docker:
        def copy_file(args, **kwargs):
            dest = Path(args[1])
            dest.write_bytes(b"REDIS0011payload")
            return SimpleNamespace(returncode=0)

        docker.side_effect = copy_file
        path = REDIS_BACKUP.backup(backup_dir=tmp_path, timeout=5)
        assert path.exists()
        assert Path(f"{path}.sha256").exists()
        assert cli.call_args_list[0].args[0] == REDIS_BACKUP.DEFAULT_CONTAINER
        assert cli.call_args_list[0].args[1] == "redis-test-password"
        assert docker.call_args.args[0][:2] == [
            "cp",
            f"{REDIS_BACKUP.DEFAULT_CONTAINER}:/data/dump.rdb",
        ]


def test_backup_fails_when_bgsave_is_unsuccessful(monkeypatch, tmp_path):
    monkeypatch.setenv("REDIS_PASSWORD", "redis-test-password")
    with patch.object(
        REDIS_BACKUP,
        "_redis_cli",
        side_effect=[
            "# Persistence\nrdb_bgsave_in_progress:0\nrdb_last_save_time:100\n",
            "dir\n/data\n",
            "dbfilename\ndump.rdb\n",
            "ERR background save failed",
        ],
    ):
        with pytest.raises(REDIS_BACKUP.RedisBackupError, match="did not acknowledge"):
            REDIS_BACKUP.backup(backup_dir=tmp_path, timeout=1)
