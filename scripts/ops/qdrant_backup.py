#!/usr/bin/env python3
"""Qdrant collection snapshot backup — runs standalone (no FastAPI app required).

Creates a named snapshot of the configured collection via the Qdrant REST API,
downloads it to a local archive directory, and optionally uploads to S3.

Usage:
    python scripts/ops/qdrant_backup.py

Railway cron: 0 2 * * *   python scripts/ops/qdrant_backup.py

Environment variables (all optional — fall back to backend/.env):
    QDRANT_URL              Qdrant base URL (default: http://localhost:6333)
    QDRANT_API_KEY          Qdrant API key (optional, for cloud)
    QDRANT_COLLECTION       Collection name (default: spiritual_wisdom)
    BACKUP_DIR              Local directory to store snapshots (default: ./backups/qdrant)
    S3_BACKUP_BUCKET        S3 bucket name for upload (optional)
    S3_BACKUP_PREFIX        S3 key prefix (default: qdrant-snapshots)
    RETAIN_LOCAL_DAYS       Days to retain local snapshot files (default: 7)
    RETAIN_S3_DAYS          Days to retain S3 snapshots (default: 30)
"""

from __future__ import annotations

import logging
import os
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger("qdrant_backup")


def _load_dotenv() -> None:
    try:
        from dotenv import load_dotenv
        env_path = Path(__file__).parent.parent.parent / "backend" / ".env"
        if env_path.exists():
            load_dotenv(env_path, override=False)
    except ImportError:
        pass


_load_dotenv()

QDRANT_URL: str = os.environ.get("QDRANT_URL", "http://localhost:6333").rstrip("/")
QDRANT_API_KEY: str = os.environ.get("QDRANT_API_KEY", "")
COLLECTION: str = os.environ.get("QDRANT_COLLECTION", "spiritual_wisdom")
BACKUP_DIR: Path = Path(os.environ.get("BACKUP_DIR", "backups/qdrant"))
S3_BUCKET: str = os.environ.get("S3_BACKUP_BUCKET", "")
S3_PREFIX: str = os.environ.get("S3_BACKUP_PREFIX", "qdrant-snapshots")
def _parse_retention_days(env_name: str, default: int) -> int:
    """Parse a retention-days env var, requiring an int >= 1.

    Fail-closed: 0/negative would prune ALL backups on first run, and a
    non-integer cannot be trusted — both exit(1) before any deletion logic.
    """
    raw = os.environ.get(env_name, str(default))
    try:
        value = int(raw)
    except ValueError:
        logger.error("%s must be an integer, got %r", env_name, raw)
        sys.exit(1)
    if value < 1:
        logger.error(
            "%s must be >= 1 (0 or negative would prune all backups), got %r",
            env_name,
            raw,
        )
        sys.exit(1)
    return value


RETAIN_LOCAL_DAYS: int = _parse_retention_days("RETAIN_LOCAL_DAYS", 7)
RETAIN_S3_DAYS: int = _parse_retention_days("RETAIN_S3_DAYS", 30)


def _headers() -> dict[str, str]:
    h: dict[str, str] = {"Content-Type": "application/json"}
    if QDRANT_API_KEY:
        h["api-key"] = QDRANT_API_KEY
    return h


_LOOPBACK_HOSTS = {"localhost", "127.0.0.1", "::1", "0.0.0.0"}


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Refuse to follow any redirect — a 3xx could re-send the api-key header
    to a different host than the one whose scheme/host we validated."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise RuntimeError(
            f"redirect blocked ({code}) to {newurl} — refusing to follow "
            "(would leak api-key to an unvalidated host)"
        )


def _urlopen(req: urllib.request.Request, timeout: float):
    """Open a request, refusing plain-HTTP when credentialed and any 3xx redirect.

    Mirrors backend/scripts/verify_sarvam.py: when QDRANT_API_KEY is set, the
    URL must be https or an explicit loopback dev host (a misconfigured prod
    URL like http://qdrant.example.com would otherwise leak the api-key over
    plaintext), and redirects are never followed.
    """
    if QDRANT_API_KEY:
        parsed = urllib.parse.urlparse(req.full_url)
        host = parsed.hostname or ""
        if parsed.scheme != "https" and host not in _LOOPBACK_HOSTS:
            raise ValueError(
                "Credentialed Qdrant calls require https or a loopback dev "
                "address (localhost/127.0.0.1/::1/0.0.0.0); refusing "
                f"plain-HTTP request to {req.full_url!r}"
            )
    opener = urllib.request.build_opener(_NoRedirectHandler)
    return opener.open(req, timeout=timeout)  # nosec B310 (scheme validated + redirects refused)


def _get(path: str) -> dict:
    import json, urllib.request
    req = urllib.request.Request(f"{QDRANT_URL}{path}", headers=_headers(), method="GET")
    with _urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def _post(path: str, body: bytes = b"{}") -> dict:
    import json, urllib.request
    req = urllib.request.Request(f"{QDRANT_URL}{path}", data=body, headers=_headers(), method="POST")
    with _urlopen(req, timeout=300) as resp:
        return json.loads(resp.read())


def _delete_req(path: str) -> dict:
    import json, urllib.request
    req = urllib.request.Request(f"{QDRANT_URL}{path}", headers=_headers(), method="DELETE")
    with _urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def _download_file(url: str, dest: Path) -> None:
    import urllib.request
    req = urllib.request.Request(url, headers=_headers(), method="GET")
    total = 0
    with _urlopen(req, timeout=600) as resp, open(dest, "wb") as f:
        while chunk := resp.read(1024 * 1024):
            f.write(chunk)
            total += len(chunk)
    logger.info("Downloaded %.1f MB -> %s", total / 1_048_576, dest)


def verify_collection() -> int:
    info = _get(f"/collections/{COLLECTION}")
    count: int = info["result"]["points_count"]
    logger.info("Collection '%s': %d points", COLLECTION, count)
    return count


def create_snapshot() -> str:
    logger.info("Creating snapshot for collection '%s'...", COLLECTION)
    resp = _post(f"/collections/{COLLECTION}/snapshots")
    name: str = resp["result"]["name"]
    logger.info("Snapshot created: %s", name)
    return name


def _validate_snapshot_name(snapshot_name: str) -> None:
    """Reject snapshot names that are not a bare filename.

    Shared by download and delete paths so a name containing path separators
    can never traverse the Qdrant snapshot REST path.
    """
    if (
        not snapshot_name
        or snapshot_name.startswith("/")
        or os.path.isabs(snapshot_name)
        or "/" in snapshot_name
        or "\\" in snapshot_name
        or snapshot_name in (".", "..")
    ):
        raise ValueError(
            "Snapshot name must be a bare filename without path separators "
            f"(no '/', no '\\\\', not absolute); got {snapshot_name!r}"
        )


def download_snapshot(snapshot_name: str, dest_dir: Path) -> Path:
    _validate_snapshot_name(snapshot_name)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / snapshot_name
    if dest.exists():
        dest.unlink()
    encoded_name = urllib.parse.quote(snapshot_name, safe="")
    url = f"{QDRANT_URL}/collections/{COLLECTION}/snapshots/{encoded_name}"
    logger.info("Downloading snapshot from %s ...", url)
    t0 = time.monotonic()
    _download_file(url, dest)
    elapsed = time.monotonic() - t0
    size_mb = dest.stat().st_size / 1_048_576
    logger.info("Download complete in %.1fs -- %.1f MB at %s", elapsed, size_mb, dest)
    return dest


def delete_remote_snapshot(snapshot_name: str) -> None:
    try:
        _validate_snapshot_name(snapshot_name)
        encoded_name = urllib.parse.quote(snapshot_name, safe="")
        _delete_req(f"/collections/{COLLECTION}/snapshots/{encoded_name}")
        logger.info("Deleted remote snapshot: %s", snapshot_name)
    except Exception as exc:
        logger.warning("Could not delete remote snapshot '%s': %s", snapshot_name, exc)


def prune_local(backup_dir: Path, retain_days: int) -> None:
    cutoff = time.time() - retain_days * 86400
    removed = 0
    for f in backup_dir.glob("*.snapshot"):
        if f.stat().st_mtime < cutoff:
            f.unlink()
            logger.info("Pruned local snapshot: %s", f.name)
            removed += 1
    if removed:
        logger.info("Pruned %d old local snapshot(s)", removed)


def _normalized_prefix(raw: str) -> str:
    """Normalize an S3 key prefix to always end with '/', or '' when empty."""
    stripped = raw.strip().rstrip("/")
    return f"{stripped}/" if stripped else ""


def upload_to_s3(local_path: Path, bucket: str, prefix: str) -> str:
    import boto3  # type: ignore[import]
    s3 = boto3.client("s3")
    # prefix is pre-normalized by main() (always ends with '/'), so the same
    # value used for listing (prune_s3) is used verbatim for keys — no stripping
    # here that could diverge from the prefix prune_s3 paginates with.
    key = f"{prefix}{local_path.name}"
    logger.info("Uploading %s -> s3://%s/%s ...", local_path.name, bucket, key)
    t0 = time.monotonic()
    s3.upload_file(str(local_path), bucket, key)
    logger.info("Upload complete in %.1fs", time.monotonic() - t0)
    return f"s3://{bucket}/{key}"


def prune_s3(bucket: str, prefix: str, retain_days: int) -> None:
    try:
        import boto3
        s3 = boto3.client("s3")
        cutoff = datetime.now(tz=timezone.utc) - timedelta(days=retain_days)
        paginator = s3.get_paginator("list_objects_v2")
        removed = 0
        for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
            for obj in page.get("Contents", []):
                if obj["LastModified"] < cutoff:
                    s3.delete_object(Bucket=bucket, Key=obj["Key"])
                    logger.info("Pruned S3 object: %s", obj["Key"])
                    removed += 1
        if removed:
            logger.info("Pruned %d old S3 snapshot(s)", removed)
    except Exception as exc:
        logger.warning("S3 pruning failed (non-fatal): %s", exc)


def main() -> int:
    logger.info("=== Qdrant Backup -- %s ===", datetime.now(tz=timezone.utc).isoformat())
    logger.info("Target: %s/%s", QDRANT_URL, COLLECTION)

    # Normalize ONCE here; both upload_to_s3 and prune_s3 receive this exact
    # prefix (always trailing '/'), so S3 listing can never match sibling
    # prefixes or, when empty, the entire bucket.
    s3_prefix = _normalized_prefix(S3_PREFIX)

    try:
        count = verify_collection()
    except Exception as exc:
        logger.error("Cannot reach Qdrant collection '%s': %s", COLLECTION, exc)
        return 1

    if count == 0:
        logger.warning("Collection has 0 points -- skipping backup.")
        return 0

    try:
        snapshot_name = create_snapshot()
    except Exception as exc:
        logger.error("Snapshot creation failed: %s", exc)
        return 1

    try:
        local_path = download_snapshot(snapshot_name, BACKUP_DIR)
    except Exception as exc:
        logger.error("Snapshot download failed: %s", exc)
        delete_remote_snapshot(snapshot_name)
        return 1

    delete_remote_snapshot(snapshot_name)

    if S3_BUCKET:
        if not s3_prefix:
            # Empty/root prefix: uploads would land at the bucket root and
            # prune_s3 would list the ENTIRE bucket. Fail soft — log an error,
            # skip S3 entirely, and keep the local backup running. Never prune
            # with an empty prefix.
            logger.error(
                "S3_BACKUP_PREFIX resolves to an empty prefix (%r) — refusing "
                "S3 upload/prune (a bucket-root prefix could match every "
                "object). Skipping S3 backup; continuing with local backup.",
                S3_PREFIX,
            )
        else:
            try:
                s3_uri = upload_to_s3(local_path, S3_BUCKET, s3_prefix)
                logger.info("Backed up to S3: %s", s3_uri)
                prune_s3(S3_BUCKET, s3_prefix, RETAIN_S3_DAYS)
            except ImportError:
                logger.warning("boto3 not installed -- skipping S3 upload.")
            except Exception as exc:
                logger.error("S3 upload failed: %s", exc)
    else:
        logger.info("S3_BACKUP_BUCKET not set -- local copy only at %s", local_path)

    prune_local(BACKUP_DIR, RETAIN_LOCAL_DAYS)

    size_mb = local_path.stat().st_size / 1_048_576
    logger.info(
        "=== Backup complete -- %s (%.1f MB, %d points) ===",
        snapshot_name, size_mb, count,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
