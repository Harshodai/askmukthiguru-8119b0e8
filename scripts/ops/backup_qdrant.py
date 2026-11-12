#!/usr/bin/env python3
"""
Mukthi Guru — Qdrant Backup & Verification Script
==================================================
Creates periodic Qdrant collection snapshots via REST API, stores them locally
with checksums, and verifies integrity by testing restore to a temp location.

Usage:
    python scripts/ops/backup_qdrant.py
    python scripts/ops/backup_qdrant.py --collection spiritual_wisdom_contextual --retention 7
    python scripts/ops/backup_qdrant.py --verify-only /path/to/snapshot.snapshot

Environment:
    QDRANT_URL        — Qdrant REST endpoint (default: http://localhost:6333)
    BACKUP_BASE_DIR   — Where snapshots are stored (default: ./backups/qdrant)
    QDRANT_WRITE_API_KEY / QDRANT_API_KEY
                      — Sent as the `api-key` header when set. The write key wins:
                        creating a snapshot needs it, and the backend never holds it.
    BACKUP_METRICS_DIR / PUSHGATEWAY_URL
                      — Where `backup_last_success_timestamp_seconds` goes after a
                        VERIFIED backup (see backup_metrics.py).

Serving collections: `--serving` backs up the collections the backend serves, read
from the same Settings the backend reads (first_person_collection and
first_person_context_collection). Do not pin a versioned name in cron.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import tarfile
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from backup_metrics import record_backup_success  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]

# ─── Configuration ───────────────────────────────────────────────────────────

QDRANT_URL = os.environ.get("QDRANT_URL", "http://localhost:6333")
BACKUP_BASE_DIR = Path(
    os.environ.get("BACKUP_BASE_DIR", Path(__file__).resolve().parents[2] / "backups" / "qdrant")
)
DEFAULT_COLLECTION = "spiritual_wisdom_contextual"
DEFAULT_RETENTION = 7  # keep last N backups


def _enforce_docker_path() -> None:
    """On macOS, ensure Docker CLI is on PATH."""
    docker_bin = "/Users/harshodaikolluru/.docker/bin"
    if os.path.isdir(docker_bin) and docker_bin not in os.environ.get("PATH", ""):
        os.environ["PATH"] = f"{docker_bin}:{os.environ.get('PATH', '')}"


def _auth_headers() -> dict[str, str]:
    """The Qdrant `api-key` header, when a key is set. Write key first."""
    key = os.environ.get("QDRANT_WRITE_API_KEY") or os.environ.get("QDRANT_API_KEY") or ""
    return {"api-key": key} if key else {}


def _open(target: str | urllib.request.Request, timeout: float):
    """The one place a request leaves this script, so every call carries the key."""
    req = target if isinstance(target, urllib.request.Request) else urllib.request.Request(target)
    for name, value in _auth_headers().items():
        req.add_header(name, value)
    return urllib.request.urlopen(req, timeout=timeout)  # nosec B310 -- operator backup tool, QDRANT_URL from env


def _sha256_file(path: Path) -> str:
    """Compute SHA256 checksum of a file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def _write_checksum(path: Path, checksum: str) -> None:
    """Write .sha256 sidecar file."""
    sidecar = path.with_suffix(path.suffix + ".sha256")
    sidecar.write_text(f"{checksum}  {path.name}\n", encoding="utf-8")
    print(f"  [+] Checksum written: {sidecar}")


def _read_checksum(path: Path) -> str | None:
    """Read checksum from sidecar file if it exists."""
    sidecar = path.with_suffix(path.suffix + ".sha256")
    if not sidecar.exists():
        return None
    parts = sidecar.read_text(encoding="utf-8").strip().split()
    return parts[0] if parts else None


def _snapshot_exists_locally(name: str, collection: str) -> Path | None:
    """Check if a snapshot with the given name already exists locally."""
    candidate = BACKUP_BASE_DIR / f"{collection}_{name}"
    if candidate.exists():
        return candidate
    return None


def _api_request(
    url: str,
    method: str = "GET",
    data: bytes | None = None,
    headers: dict | None = None,
) -> dict:
    """Make a JSON API request to Qdrant and return parsed response."""
    req = urllib.request.Request(url, method=method, data=data)
    if headers:
        for k, v in headers.items():
            req.add_header(k, v)
    else:
        req.add_header("Content-Type", "application/json")
    with _open(req, 120) as res:
        return json.loads(res.read().decode("utf-8"))


# ─── Core Backup Logic ────────────────────────────────────────────────────────


def create_snapshot(collection: str) -> str:
    """Trigger snapshot creation on Qdrant; return snapshot name."""
    url = f"{QDRANT_URL}/collections/{collection}/snapshots"
    resp = _api_request(url, method="POST")
    if resp.get("result") and resp["result"].get("name"):
        return resp["result"]["name"]
    raise RuntimeError(f"Snapshot creation failed: {resp}")


def download_snapshot(collection: str, snapshot_name: str, dest: Path) -> None:
    """Download a snapshot from Qdrant to local disk."""
    url = f"{QDRANT_URL}/collections/{collection}/snapshots/{snapshot_name}"
    print(f"  [*] Downloading {snapshot_name} ...")
    with _open(url, 600) as res, open(dest, "wb") as out:
        shutil.copyfileobj(res, out)
    size_mb = dest.stat().st_size / (1024 * 1024)
    print(f"  [+] Saved {dest} ({size_mb:.2f} MB)")


def list_remote_snapshots(collection: str) -> list[dict]:
    """List snapshots currently stored on Qdrant server."""
    url = f"{QDRANT_URL}/collections/{collection}/snapshots"
    try:
        resp = _api_request(url)
        return resp.get("result", [])
    except urllib.error.URLError as e:
        print(f"  [-] Cannot reach Qdrant at {QDRANT_URL}: {e}")
        return []


def cleanup_old_backups(collection: str, retention: int) -> None:
    """Remove local backups older than the retention count."""
    pattern = f"{collection}_*.snapshot"
    files = sorted(BACKUP_BASE_DIR.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
    for old in files[retention:]:
        old.unlink()
        sidecar = old.with_suffix(old.suffix + ".sha256")
        if sidecar.exists():
            sidecar.unlink()
        print(f"  [-] Pruned old backup: {old.name}")


# ─── Verification Logic ───────────────────────────────────────────────────────


def verify_snapshot(
    path: Path, expected_points: int | None = None, source_collection: str | None = None
) -> bool:
    """
    Verify a snapshot archive:
      1. File is non-empty.
      2. Checksum matches sidecar (if present).
      3. Archive can be opened and contains expected metadata.
      4. Test-restore into a throwaway collection returns the expected point count.
    """
    print(f"\n[Verify] Checking {path.name} ...")

    if not path.exists() or path.stat().st_size == 0:
        print("  [-] FAIL: File missing or empty.")
        return False

    # 1. Checksum verification
    expected = _read_checksum(path)
    if expected:
        actual = _sha256_file(path)
        if actual != expected:
            print(f"  [-] FAIL: Checksum mismatch! Expected {expected}, got {actual}")
            return False
        print("  [+] Checksum OK")
    else:
        print("  [!] No sidecar checksum; skipping checksum verification.")

    # 2. Archive integrity (Qdrant snapshots are .tar.gz or .tar)
    try:
        with tarfile.open(path, "r:*") as tf:
            names = tf.getnames()
            if not names:
                print("  [-] FAIL: Archive is empty.")
                return False
            # Qdrant snapshots contain a segment directory and config.json
            has_config = any(
                n.endswith("config.json") or n.endswith("snapshot_metadata.json") for n in names
            )
            if not has_config:
                print(
                    f"  [-] FAIL: Archive missing expected metadata files. Names: {names[:5]} ..."
                )
                return False
            print(f"  [+] Archive OK ({len(names)} entries)")
    except tarfile.TarError as e:
        print(f"  [-] FAIL: Not a valid tar archive: {e}")
        return False

    # 3. Optional: test restore to temp collection (lightweight — just uploads and checks status)
    print("  [*] Running test-restore to temporary collection ...")
    temp_collection = f"_verify_{int(time.time())}"
    try:
        # Create empty temp collection first (copy basic config from original if needed)
        _create_temp_collection(temp_collection, source_collection=source_collection)
        if _restore_to_temp(path, temp_collection):
            print("  [+] Test-restore OK")
            if expected_points is not None:
                restored = _collection_points(temp_collection)
                if restored == expected_points:
                    print(f"  [+] Point count matches: {restored}")
                else:
                    print(f"  [-] FAIL: Expected {expected_points} points, restored {restored}.")
                    _drop_collection(temp_collection)
                    return False
            _drop_collection(temp_collection)
            return True
        else:
            print("  [-] FAIL: Test-restore failed.")
            _drop_collection(temp_collection)
            return False
    except Exception as e:
        print(f"  [-] FAIL: Test-restore exception: {e}")
        _drop_collection(temp_collection)
        return False


def _create_temp_collection(name: str, source_collection: str | None = None) -> None:
    """Create a minimal temporary collection for verification.

    Mirrors the source collection's vector config when known — a snapshot
    restore is rejected if the temp collection does not match the snapshot's
    own vector layout (multi-vector dense+sparse collections in particular).
    """
    url = f"{QDRANT_URL}/collections/{name}"
    if source_collection:
        try:
            src_url = f"{QDRANT_URL}/collections/{source_collection}"
            with _open(src_url, 30) as res:
                src = json.loads(res.read().decode()).get("result", {})
            params = src.get("config", {}).get("params", {})
            body = {
                "vectors": params.get("vectors", {"size": 1024, "distance": "Cosine"}),
                "sparse_vectors": params.get("sparse_vectors"),
                "quantization_config": src.get("config", {}).get("quantization_config"),
                "on_disk_payload": params.get("on_disk_payload"),
            }
            payload = json.dumps({k: v for k, v in body.items() if v is not None}).encode("utf-8")
        except Exception as e:
            print(f"  [!] Could not mirror source collection config ({e}); using defaults.")
            payload = json.dumps({"vectors": {"size": 1024, "distance": "Cosine"}}).encode("utf-8")
    else:
        payload = json.dumps({"vectors": {"size": 1024, "distance": "Cosine"}}).encode("utf-8")
    req = urllib.request.Request(
        url, data=payload, headers={"Content-Type": "application/json"}, method="PUT"
    )
    try:
        with _open(req, 30):
            pass
    except urllib.error.HTTPError as e:
        if e.code == 409:
            pass  # already exists
        else:
            raise


def _drop_collection(name: str) -> None:
    """Drop a collection."""
    url = f"{QDRANT_URL}/collections/{name}"
    req = urllib.request.Request(url, method="DELETE")
    try:
        with _open(req, 30):
            pass
    except (urllib.error.URLError, OSError):
        pass


def _restore_to_temp(path: Path, collection: str) -> bool:
    """Upload snapshot to a temp collection and wait until the restore completes.

    Qdrant's upload endpoint responds immediately with ``{"result": true}`` while
    the restore runs asynchronously; verification must poll the collection status
    until it is ready and then confirm the point count matches the source.
    """
    url = f"{QDRANT_URL}/collections/{collection}/snapshots/upload?priority=snapshot"
    boundary = b"----WebKitFormBoundaryMukthiGuruBackup"
    with open(path, "rb") as f:
        snapshot_bytes = f.read()
    body = (
        b"--" + boundary + b"\r\n"
        b'Content-Disposition: form-data; name="snapshot"; filename="'
        + path.name.encode()
        + b'"'
        + b"\r\n"
        b"Content-Type: application/octet-stream\r\n\r\n" + snapshot_bytes + b"\r\n"
        b"--" + boundary + b"--\r\n"
    )
    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "Content-Type": f"multipart/form-data; boundary={boundary.decode()}",
            "Content-Length": str(len(body)),
        },
        method="POST",
    )
    with _open(req, 300) as res:
        resp = json.loads(res.read().decode())
        if not resp.get("result", False):
            print(f"  [-] FAIL: snapshot upload rejected: {resp}")
            return False
    for _ in range(60):
        status = _collection_status(collection)
        if status == "green":
            return True
        if status == "grey":
            print("  [-] FAIL: restore errored (collection turned grey).")
            return False
        time.sleep(2)
    print("  [-] FAIL: restore did not complete within 120s.")
    return False


def _collection_status(collection: str) -> str:
    """Return the status ('green'/'grey'/'yellow') of a collection."""
    url = f"{QDRANT_URL}/collections/{collection}"
    with _open(url, 30) as res:
        resp = json.loads(res.read().decode())
        return resp.get("result", {}).get("status", "unknown")


def _collection_points(collection: str) -> int:
    """Return the number of points in a collection."""
    url = f"{QDRANT_URL}/collections/{collection}"
    with _open(url, 30) as res:
        resp = json.loads(res.read().decode())
        return int(resp.get("result", {}).get("points_count", 0))


# ─── Main Entry Point ─────────────────────────────────────────────────────────


def resolve_serving_collections(cfg=None) -> list[str]:
    """Collections the backend serves, from the Settings the backend reads.

    NEW-OPS-4: cron used to pin `first_person_v7`, so a promotion to v10 left the
    nightly job backing up a collection nobody serves. The names now come from
    `first_person_collection` and `first_person_context_collection`. Fails closed
    (SystemExit) when no name resolves, so a broken setup is loud, not a no-op.
    """
    if cfg is None:
        sys.path.insert(0, str(REPO_ROOT / "backend"))
        try:
            from app.config import settings as cfg  # type: ignore[no-redef]
        except ImportError as exc:
            raise SystemExit(
                f"--serving needs the backend environment (app.config): {exc}. "
                "Run it from the backend virtualenv, or pass --collection NAME."
            ) from exc
    names: list[str] = []
    for attr in ("first_person_collection", "first_person_context_collection"):
        name = str(getattr(cfg, attr, "") or "").strip()
        if name and name not in names:
            names.append(name)
    if not names:
        raise SystemExit("No serving collection resolved from Settings; nothing to back up.")
    return names


def _quarantine_failed(path: Path) -> None:
    """Keep a failed artefact for inspection, out of the retention glob."""
    failed = path.with_name(path.name + ".failed")
    try:
        path.replace(failed)
        sidecar = path.with_suffix(path.suffix + ".sha256")
        if sidecar.exists():
            sidecar.unlink()
        print(f"  [!] Failed artefact kept as {failed.name}")
    except OSError as exc:
        print(f"  [!] Could not set the failed artefact aside: {exc}")


def backup(collection: str, retention: int) -> bool:
    """Run full backup pipeline for a Qdrant collection.

    The success timestamp is written only after `verify_snapshot` passes.
    """
    print("=" * 70)
    print(f"  Qdrant Backup — Collection: {collection}")
    print("=" * 70)

    BACKUP_BASE_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    dest = BACKUP_BASE_DIR / f"{collection}_{ts}.snapshot"

    try:
        source_points = _collection_points(collection)
        print(f"[*] Creating remote snapshot for '{collection}' ...")
        snapshot_name = create_snapshot(collection)
        print(f"[+] Remote snapshot created: {snapshot_name}")

        download_snapshot(collection, snapshot_name, dest)

        checksum = _sha256_file(dest)
        _write_checksum(dest, checksum)

        ok = verify_snapshot(dest, expected_points=source_points, source_collection=collection)
        if not ok:
            print(f"\n[❌] Backup verification FAILED: {dest}")
            _quarantine_failed(dest)
            return False
        print(f"\n[✅] Backup verified: {dest}")

        record_backup_success("qdrant", collection)
        cleanup_old_backups(collection, retention)
        return True

    except (RuntimeError, OSError, ValueError, tarfile.TarError) as e:
        # URLError and HTTPError are OSError; a bad JSON reply is ValueError.
        print(f"[-] Backup failed: {e}")
        if dest.exists():
            _quarantine_failed(dest)
        return False


def main() -> int:
    parser = argparse.ArgumentParser(description="Mukthi Guru — Qdrant Backup & Verification")
    parser.add_argument("--collection", default=DEFAULT_COLLECTION, help="Qdrant collection name")
    parser.add_argument(
        "--serving",
        action="store_true",
        help="Back up the collections the backend serves (read from Settings); "
        "overrides --collection",
    )
    parser.add_argument(
        "--retention",
        type=int,
        default=DEFAULT_RETENTION,
        help="Number of backups to retain",
    )
    parser.add_argument(
        "--verify-only",
        type=Path,
        metavar="PATH",
        help="Verify an existing snapshot file",
    )
    parser.add_argument(
        "--expect-points",
        type=int,
        metavar="N",
        help="Expected point count after restore (with --verify-only)",
    )
    parser.add_argument(
        "--source-collection",
        metavar="NAME",
        help="Source collection whose vector config the verify temp collection should mirror",
    )
    args = parser.parse_args()

    _enforce_docker_path()

    if args.verify_only:
        ok = verify_snapshot(
            args.verify_only,
            expected_points=args.expect_points,
            source_collection=args.source_collection,
        )
        return 0 if ok else 1

    names = resolve_serving_collections() if args.serving else [args.collection]
    results = [backup(name, args.retention) for name in names]
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
