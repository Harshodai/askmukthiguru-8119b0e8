"""Unit tests for the Redis RDB backup and verification helper."""

from __future__ import annotations

import hashlib
import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

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


def test_redis_url_client_does_not_put_password_in_command_line(monkeypatch):
    redis_module = SimpleNamespace(
        Redis=SimpleNamespace(
            from_url=MagicMock(return_value=SimpleNamespace(ping=MagicMock()))
        )
    )
    monkeypatch.setitem(sys.modules, "redis", redis_module)
    monkeypatch.setenv("REDIS_URL", "redis://:secret-value@127.0.0.1:6379/0")

    client = REDIS_BACKUP._build_redis_client()

    redis_module.Redis.from_url.assert_called_once()
    assert client is redis_module.Redis.from_url.return_value
    assert redis_module.Redis.from_url.call_args.args[0] == "redis://:secret-value@127.0.0.1:6379/0"


def test_config_url_rejects_invalid_scheme(monkeypatch):
    redis_module = SimpleNamespace(Redis=SimpleNamespace(from_url=MagicMock()))
    monkeypatch.setitem(sys.modules, "redis", redis_module)
    with pytest.raises(REDIS_BACKUP.RedisBackupError, match="redis://"):
        REDIS_BACKUP._build_redis_client(redis_url="http://localhost:6379")


def test_host_redis_client_uses_password_from_environment(monkeypatch):
    client = SimpleNamespace(ping=MagicMock())
    redis_module = SimpleNamespace(Redis=MagicMock(return_value=client))
    monkeypatch.setitem(sys.modules, "redis", redis_module)
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.setenv("REDIS_HOST", "127.0.0.1")
    monkeypatch.setenv("REDIS_PORT", "16379")
    monkeypatch.setenv("REDIS_PASSWORD", "host-secret")

    actual = REDIS_BACKUP._build_redis_client()

    assert actual is client
    redis_module.Redis.assert_called_once_with(
        host="127.0.0.1",
        port=16379,
        db=0,
        password="host-secret",
        decode_responses=True,
        socket_timeout=10,
    )
    client.ping.assert_called_once()


def test_backup_copies_only_after_confirmed_new_bgsave(monkeypatch, tmp_path):
    client = SimpleNamespace(
        ping=MagicMock(),
        info=MagicMock(
            side_effect=[
                {"rdb_bgsave_in_progress": 0, "rdb_saves": 10},
                {
                    "rdb_bgsave_in_progress": 0,
                    "rdb_last_bgsave_status": "ok",
                    "rdb_saves": 11,
                },
            ]
        ),
        config_get=MagicMock(side_effect=[{"dir": "/data"}, {"dbfilename": "dump.rdb"}]),
        bgsave=MagicMock(return_value="Background saving started"),
    )
    monkeypatch.setattr(REDIS_BACKUP, "_build_redis_client", lambda **_kwargs: client)
    monkeypatch.setattr(REDIS_BACKUP.time, "sleep", lambda _seconds: None)

    def copy_file(_container, _source, destination, timeout=60):
        Path(destination).write_bytes(b"REDIS0011payload")

    monkeypatch.setattr(REDIS_BACKUP, "_docker_cp", copy_file)
    path = REDIS_BACKUP.backup(backup_dir=tmp_path, timeout=5)

    assert path.exists()
    assert Path(f"{path}.sha256").exists()
    client.bgsave.assert_called_once()
    assert all(call.args == ("persistence",) for call in client.info.call_args_list)


def test_backup_fails_when_bgsave_not_acknowledged(monkeypatch, tmp_path):
    client = SimpleNamespace(
        ping=MagicMock(),
        info=MagicMock(
            side_effect=[
                {"rdb_bgsave_in_progress": 0},
                {"rdb_saves": 1},
            ]
        ),
        config_get=MagicMock(side_effect=[{"dir": "/data"}, {"dbfilename": "dump.rdb"}]),
        bgsave=MagicMock(return_value="ERR background save failed"),
    )
    monkeypatch.setattr(REDIS_BACKUP, "_build_redis_client", lambda **_kwargs: client)
    with pytest.raises(REDIS_BACKUP.RedisBackupError, match="did not acknowledge"):
        REDIS_BACKUP.backup(backup_dir=tmp_path, timeout=1)
