#!/usr/bin/env python3
"""
Mukthi Guru — Qdrant Backup & Verification Script
==================================================
Creates periodic Qdrant collection snapshots via REST API, stores them locally
with checksums, and verifies integrity by testing restore to a temp location.

Usage:
    python scripts/ops/backup_qdrant.py
    python scripts/ops/backup_qdrant.py --collection spiritual_wisdom --retention 7
    python scripts/ops/backup_qdrant.py --verify-only /path/to/snapshot.snapshot

Environment:
    QDRANT_URL        — Qdrant REST endpoint (default: http://localhost:6333)
    BACKUP_BASE_DIR   — Where snapshots are stored (default: ./backups/qdrant)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tarfile
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

# ─── Configuration ───────────────────────────────────────────────────────────

QDRANT_URL = os.environ.get("QDRANT_URL", "http://localhost:6333")
BACKUP_BASE_DIR = Path(
    os.environ.get("BACKUP_BASE_DIR", Path(__file__).resolve().parents[2] / "backups" / "qdrant")
)
DEFAULT_COLLECTION = "spiritual_wisdom"
DEFAULT_RETENTION = 7  # keep last N backups


def _enforce_docker_path() -> None:
    """On macOS, ensure Docker CLI is on PATH."""
    docker_bin = "/Users/harshodaikolluru/.docker/bin"
    if os.path.isdir(docker_bin) and docker_bin not in os.environ.get("PATH", ""):
        os.environ["PATH"] = f"{docker_bin}:{os.environ.get('PATH', '')}"


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
    with urllib.request.urlopen(req, timeout=120) as res:
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
    urllib.request.urlretrieve(url, dest)
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


def verify_snapshot(path: Path) -> bool:
    """
    Verify a snapshot archive:
      1. File is non-empty.
      2. Checksum matches sidecar (if present).
      3. Archive can be opened and contains expected metadata.
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
        _create_temp_collection(temp_collection)
        if _restore_to_temp(path, temp_collection):
            print("  [+] Test-restore OK")
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


def _create_temp_collection(name: str) -> None:
    """Create a minimal temporary collection for verification."""
    url = f"{QDRANT_URL}/collections/{name}"
    payload = json.dumps({"vectors": {"size": 1024, "distance": "Cosine"}}).encode("utf-8")
    req = urllib.request.Request(
        url, data=payload, headers={"Content-Type": "application/json"}, method="PUT"
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as res:
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
        with urllib.request.urlopen(req, timeout=30):
            pass
    except Exception:
        pass


def _restore_to_temp(path: Path, collection: str) -> bool:
    """Upload snapshot to a temp collection and check status."""
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
    with urllib.request.urlopen(req, timeout=300) as res:
        resp = json.loads(res.read().decode())
        return resp.get("result", {}).get("status") == "ok" or resp.get("status") == "ok"


# ─── Main Entry Point ─────────────────────────────────────────────────────────


def backup(collection: str, retention: int) -> bool:
    """Run full backup pipeline for a Qdrant collection."""
    print("=" * 70)
    print(f"  Qdrant Backup — Collection: {collection}")
    print("=" * 70)

    BACKUP_BASE_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    dest = BACKUP_BASE_DIR / f"{collection}_{ts}.snapshot"

    try:
        print(f"[*] Creating remote snapshot for '{collection}' ...")
        snapshot_name = create_snapshot(collection)
        print(f"[+] Remote snapshot created: {snapshot_name}")

        download_snapshot(collection, snapshot_name, dest)

        checksum = _sha256_file(dest)
        _write_checksum(dest, checksum)

        ok = verify_snapshot(dest)
        if ok:
            print(f"\n[✅] Backup verified: {dest}")
        else:
            print(f"\n[❌] Backup verification FAILED: {dest}")
            return False

        cleanup_old_backups(collection, retention)
        return True

    except urllib.error.URLError as e:
        print(f"[-] Cannot connect to Qdrant at {QDRANT_URL}: {e}")
        return False
    except Exception as e:
        print(f"[-] Backup failed: {e}")
        return False


def main() -> int:
    parser = argparse.ArgumentParser(description="Mukthi Guru — Qdrant Backup & Verification")
    parser.add_argument("--collection", default=DEFAULT_COLLECTION, help="Qdrant collection name")
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
    args = parser.parse_args()

    _enforce_docker_path()

    if args.verify_only:
        ok = verify_snapshot(args.verify_only)
        return 0 if ok else 1

    ok = backup(args.collection, args.retention)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
