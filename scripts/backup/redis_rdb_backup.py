#!/usr/bin/env python3
"""Create and verify Redis RDB backups without modifying the running dataset.

The tool requests BGSAVE through redis-py, copies the configured RDB file from
the Docker container only after a confirmed new save, and writes a SHA-256
sidecar. It never performs FLUSHDB/FLUSHALL and has no automatic restore path.
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
from urllib.parse import urlparse

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_BACKUP_DIR = REPO_ROOT / "backups" / "redis"
DEFAULT_CONTAINER = "mukthiguru-redis"
RDB_HEADER = re.compile(rb"^REDIS\d{4}$")


class RedisBackupError(RuntimeError):
    """A Redis backup could not be proven complete and intact."""


def _build_redis_client(
    *,
    redis_url: str | None = None,
    host: str | None = None,
    port: int | None = None,
    db: int | None = None,
    password: str | None = None,
):
    try:
        import redis
    except ImportError as exc:
        raise RedisBackupError(
            "redis-py is required; run this tool with the backend virtual environment"
        ) from exc

    resolved_url = redis_url if redis_url is not None else os.environ.get("REDIS_URL", "")
    if resolved_url:
        parsed = urlparse(resolved_url)
        if parsed.scheme not in {"redis", "rediss"} or not parsed.hostname:
            raise RedisBackupError("REDIS_URL must be a redis:// or rediss:// URL with a host")
        client = redis.Redis.from_url(resolved_url, decode_responses=True, socket_timeout=10)
    else:
        client = redis.Redis(
            host=host or os.environ.get("REDIS_HOST", "127.0.0.1"),
            port=port or int(os.environ.get("REDIS_PORT", "6379")),
            db=db if db is not None else int(os.environ.get("REDIS_DB", "0")),
            password=password if password is not None else os.environ.get("REDIS_PASSWORD") or None,
            decode_responses=True,
            socket_timeout=10,
        )
    try:
        client.ping()
    except Exception as exc:
        raise RedisBackupError(f"Cannot connect to Redis: {exc}") from exc
    return client


def _docker_cp(container: str, source_path: str, destination: Path, timeout: int = 60) -> None:
    result = subprocess.run(
        ["docker", "cp", f"{container}:{source_path}", str(destination)],
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise RedisBackupError(f"docker cp failed: {detail}")


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
    redis_url: str | None = None,
    password: str | None = None,
    timeout: float = 180.0,
) -> Path:
    client = _build_redis_client(redis_url=redis_url, password=password)
    info_before = client.info("persistence")
    if int(info_before.get("rdb_bgsave_in_progress", 0)) == 1:
        raise RedisBackupError(
            "A Redis background save is already in progress; retry after it completes"
        )

    stats_before = client.info("stats")
    before_saves = int(stats_before.get("rdb_saves", 0))
    config = client.config_get("dir")
    directory = config.get("dir")
    if not isinstance(directory, str) or not directory:
        raise RedisBackupError("Redis CONFIG GET dir returned an empty/invalid value")
    config = client.config_get("dbfilename")
    filename = config.get("dbfilename")
    if not isinstance(filename, str) or not filename:
        raise RedisBackupError("Redis CONFIG GET dbfilename returned an empty/invalid value")
    if PurePosixPath(filename).name != filename:
        raise RedisBackupError(f"Redis dbfilename must be a simple filename, got {filename!r}")
    source_path = str(PurePosixPath(directory) / filename)

    response = client.bgsave()
    if response is not True:
        raise RedisBackupError(f"Redis did not acknowledge BGSAVE: {response!r}")

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        time.sleep(1)
        info = client.info("persistence")
        stats = client.info("stats")
        if int(info.get("rdb_bgsave_in_progress", 0)) == 1:
            continue
        if info.get("rdb_last_bgsave_status") != "ok":
            raise RedisBackupError(
                "Redis background save did not finish successfully: "
                f"{info.get('rdb_last_bgsave_status', 'unknown')}"
            )
        if int(stats.get("rdb_saves", 0)) > before_saves:
            break
    else:
        raise RedisBackupError("Timed out waiting for a confirmed new Redis BGSAVE")

    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    final_path = backup_dir / f"redis_{timestamp}.rdb"
    temp_path = backup_dir / f".{final_path.name}.tmp"

    try:
        _docker_cp(container, source_path, temp_path, timeout=int(timeout))
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
