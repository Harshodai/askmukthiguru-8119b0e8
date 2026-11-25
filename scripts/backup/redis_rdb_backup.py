#!/usr/bin/env python3
"""Create and verify Redis RDB backups without modifying the running dataset.

This tool copies the Redis server's configured RDB file only after a completed
BGSAVE. It never performs FLUSHDB/FLUSHALL and has no automatic restore command.
Restore must happen against a fresh, isolated Redis instance using the runbook.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_BACKUP_DIR = REPO_ROOT / "backups" / "redis"
DEFAULT_CONTAINER = "mukthiguru-redis"
RDB_HEADER = re.compile(rb"^REDIS\d{4}$")


class RedisBackupError(RuntimeError):
    """A Redis backup could not be proven complete and intact."""


def _docker(args: list[str], *, timeout: int = 60, check: bool = True) -> subprocess.CompletedProcess:
    command = ["docker", *args]
    result = subprocess.run(command, capture_output=True, text=True, timeout=timeout)
    if check and result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise RedisBackupError(
            f"Command failed ({result.returncode}): docker {' '.join(args[:4])}: {detail}"
        )
    return result


def _redis_cli(container: str, password: str, *args: str, timeout: int = 30) -> str:
    command = ["exec"]
    if password:
        command.extend(["-e", f"REDISCLI_AUTH={password}"])
    command.extend([container, "redis-cli", "--no-auth-warning", "--raw", *args])
    result = _docker(command, timeout=timeout)
    return result.stdout.strip()


def _parse_config_pair(output: str, key: str) -> str:
    rows = [line.strip() for line in output.splitlines() if line.strip()]
    if len(rows) < 2:
        raise RedisBackupError(f"Redis CONFIG GET {key} returned an unexpected response")
    if rows[0].lower() != key.lower():
        raise RedisBackupError(f"Redis CONFIG GET {key} returned {rows[0]!r}")
    value = rows[1]
    if not value:
        raise RedisBackupError(f"Redis CONFIG GET {key} returned an empty value")
    return value


def _parse_info(info: str) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for line in info.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, value = line.split(":", 1)
        parsed[key.strip()] = value.strip()
    return parsed


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def verify_rdb(path: Path, *, require_sidecar: bool = True) -> dict[str, Any]:
    if not path.is_file():
        raise RedisBackupError(f"RDB backup does not exist: {path}")
    size = path.stat().st_size
    if size < 9:
        raise RedisBackupError(f"RDB backup is too small to be valid: {size} bytes")
    with path.open("rb") as handle:
        header = handle.read(9)
    if not RDB_HEADER.fullmatch(header):
        raise RedisBackupError(f"Invalid Redis RDB signature/version header: {header!r}")

    checksum_path = Path(f"{path}.sha256")
    if require_sidecar and not checksum_path.is_file():
        raise RedisBackupError(f"SHA-256 sidecar missing: {checksum_path}")
    checksum = _sha256(path)
    if checksum_path.is_file():
        expected = checksum_path.read_text(encoding="utf-8").strip().split()
        if not expected or expected[0].lower() != checksum:
            raise RedisBackupError("Redis RDB SHA-256 verification failed")

    return {
        "path": str(path),
        "size_bytes": size,
        "rdb_version": header[5:].decode(),
        "sha256": checksum,
    }


def backup(
    *,
    container: str = DEFAULT_CONTAINER,
    backup_dir: Path = DEFAULT_BACKUP_DIR,
    password: str | None = None,
    timeout: float = 180.0,
) -> Path:
    password = password if password is not None else os.environ.get("REDIS_PASSWORD", "")
    info_before = _parse_info(_redis_cli(container, password, "INFO", "persistence"))
    if info_before.get("rdb_bgsave_in_progress") == "1":
        raise RedisBackupError(
            "A Redis background save is already in progress; retry after it completes"
        )

    before_last_save = int(info_before.get("rdb_last_save_time", "0"))
    directory = _parse_config_pair(
        _redis_cli(container, password, "CONFIG", "GET", "dir"), "dir"
    )
    filename = _parse_config_pair(
        _redis_cli(container, password, "CONFIG", "GET", "dbfilename"), "dbfilename"
    )
    if PurePosixPath(filename).name != filename:
        raise RedisBackupError(f"Redis dbfilename must be a simple filename, got {filename!r}")
    source_path = str(PurePosixPath(directory) / filename)

    response = _redis_cli(container, password, "BGSAVE")
    if not (
        response.startswith("Background saving started")
        or response.startswith("Background saving scheduled")
    ):
        raise RedisBackupError(f"Redis did not acknowledge BGSAVE: {response!r}")

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        time.sleep(1)
        info = _parse_info(_redis_cli(container, password, "INFO", "persistence"))
        if info.get("rdb_bgsave_in_progress") == "1":
            continue
        if info.get("rdb_last_bgsave_status") != "ok":
            raise RedisBackupError(
                "Redis background save did not finish successfully: "
                f"{info.get('rdb_last_bgsave_status', 'unknown')}"
            )
        if int(info.get("rdb_last_save_time", "0")) > before_last_save:
            break
    else:
        raise RedisBackupError("Timed out waiting for a confirmed Redis BGSAVE completion")

    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    final_path = backup_dir / f"redis_{timestamp}.rdb"
    temp_path = backup_dir / f".{final_path.name}.tmp"

    try:
        _docker(["cp", f"{container}:{source_path}", str(temp_path)], timeout=int(timeout))
        verify_rdb(temp_path, require_sidecar=False)
        checksum = _sha256(temp_path)
        os.replace(temp_path, final_path)
        sidecar = Path(f"{final_path}.sha256")
        tmp_sidecar = Path(f"{sidecar}.tmp")
        tmp_sidecar.write_text(
            f"{checksum}  {final_path.name}\n", encoding="utf-8"
        )
        os.replace(tmp_sidecar, sidecar)
        report = verify_rdb(final_path, require_sidecar=True)
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise

    print(
        f"Redis RDB backup verified: {final_path} "
        f"({report['size_bytes']} bytes, RDB {report['rdb_version']}, "
        f"SHA-256 {report['sha256']})"
    )
    return final_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    backup_parser = sub.add_parser("backup", help="Create a verified RDB backup")
    backup_parser.add_argument("--container", default=DEFAULT_CONTAINER)
    backup_parser.add_argument("--output-dir", type=Path, default=DEFAULT_BACKUP_DIR)
    backup_parser.add_argument("--timeout", type=float, default=180.0)

    verify_parser = sub.add_parser("verify", help="Verify an existing RDB and sidecar")
    verify_parser.add_argument("path", type=Path)

    args = parser.parse_args(argv)
    try:
        if args.command == "backup":
            backup(
                container=args.container,
                backup_dir=args.output_dir,
                timeout=args.timeout,
            )
        else:
            result = verify_rdb(args.path)
            print(
                f"Redis RDB verified: {result['path']} "
                f"({result['size_bytes']} bytes, RDB {result['rdb_version']}, "
                f"SHA-256 {result['sha256']})"
            )
        return 0
    except (RedisBackupError, OSError, subprocess.TimeoutExpired) as exc:
        print(f"Redis backup failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
