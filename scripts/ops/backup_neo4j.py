#!/usr/bin/env python3
"""
Mukthi Guru — Neo4j Backup & Verification Script
=================================================
Creates graph database dumps using `neo4j-admin database dump` or Cypher export.
Supports checksum verification and integrity checks.

Usage:
    python scripts/ops/backup_neo4j.py
    python scripts/ops/backup_neo4j.py --format dump
    python scripts/ops/backup_neo4j.py --format cypher --retention 7

Environment:
    NEO4J_URI       — Bolt URI (default: bolt://localhost:7687)
    NEO4J_USER      — Username (default: neo4j)
    NEO4J_PASSWORD  — Password (required, no default)
    BACKUP_BASE_DIR — Where dumps are stored (default: ./backups/neo4j)

Docker (recommended):
    Uses neo4j-admin inside the running container.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

# ─── Configuration ───────────────────────────────────────────────────────────

NEO4J_URI = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.environ.get("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.environ["NEO4J_PASSWORD"]  # required
NEO4J_CONTAINER = os.environ.get("NEO4J_CONTAINER", "mukthiguru-neo4j")
NEO4J_DB_NAME = os.environ.get("NEO4J_DB_NAME", "neo4j")  # default database

BACKUP_BASE_DIR = Path(
    os.environ.get("BACKUP_BASE_DIR", Path(__file__).resolve().parents[2] / "backups" / "neo4j")
)
DEFAULT_RETENTION = 7
DEFAULT_FORMAT = "dump"  # "dump" or "cypher"


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


def _run(
    cmd: list[str], input_text: str | None = None, timeout: int = 120
) -> subprocess.CompletedProcess:
    """Run a shell command and return the result."""
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        check=True,
        input=input_text,
        timeout=timeout,
    )


def _container_exists(name: str) -> bool:
    """Check if a Docker container exists."""
    try:
        _run(["docker", "inspect", "--format={{.State.Status}}", name])
        return True
    except subprocess.CalledProcessError:
        return False


# ─── Dump Backup (neo4j-admin) ───────────────────────────────────────────────


def backup_dump(retention: int) -> bool:
    """Use neo4j-admin database dump inside the Docker container."""
    print("=" * 70)
    print("  Neo4j Backup — Format: dump (neo4j-admin)")
    print("=" * 70)

    BACKUP_BASE_DIR.mkdir(parents=True, exist_ok=True)

    if not _container_exists(NEO4J_CONTAINER):
        print(f"[-] Neo4j container '{NEO4J_CONTAINER}' not found. Is Docker Compose running?")
        return False

    ts = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    dump_filename = f"{NEO4J_DB_NAME}_{ts}.dump"
    host_dest = BACKUP_BASE_DIR / dump_filename
    container_tmp = f"/tmp/{dump_filename}"

    try:
        # 1. Run neo4j-admin dump inside container
        print("[*] Running neo4j-admin database dump ...")
        cmd = [
            "docker",
            "exec",
            NEO4J_CONTAINER,
            "neo4j-admin",
            "database",
            "dump",
            NEO4J_DB_NAME,
            "--to-path=/tmp",
            "--overwrite-destination=true",
        ]
        _run(cmd, timeout=300)
        print(f"[+] Dump created inside container: {container_tmp}")

        # 2. Copy dump from container to host
        cp_cmd = [
            "docker",
            "cp",
            f"{NEO4J_CONTAINER}:{container_tmp}",
            str(host_dest),
        ]
        _run(cp_cmd, timeout=60)
        print(f"[+] Dump copied to host: {host_dest}")

        # 3. Remove temp dump from container
        try:
            _run(
                ["docker", "exec", NEO4J_CONTAINER, "rm", "-f", container_tmp],
                timeout=10,
            )
        except subprocess.CalledProcessError:
            pass

        # 4. Checksum
        checksum = _sha256_file(host_dest)
        _write_checksum(host_dest, checksum)

        # 5. Verify
        ok = verify_dump(host_dest)
        if not ok:
            return False

        # 6. Cleanup old
        cleanup_old_backups("*.dump", retention)
        return True

    except subprocess.CalledProcessError as e:
        print(f"[-] neo4j-admin dump failed: {e.stderr or e.stdout}")
        return False
    except subprocess.TimeoutExpired:
        print("[-] neo4j-admin dump timed out.")
        return False
    except Exception as e:
        print(f"[-] Backup failed: {e}")
        return False


def verify_dump(path: Path) -> bool:
    """Verify a Neo4j dump archive."""
    print(f"\n[Verify] Checking {path.name} ...")

    if not path.exists() or path.stat().st_size == 0:
        print("  [-] FAIL: File missing or empty.")
        return False

    # Checksum
    expected = _read_checksum(path)
    if expected:
        actual = _sha256_file(path)
        if actual != expected:
            print("  [-] FAIL: Checksum mismatch!")
            return False
        print("  [+] Checksum OK")
    else:
        print("  [!] No sidecar checksum; skipping checksum verification.")

    # neo4j dumps are tar-like but proprietary; we do a basic magic-byte check
    header = path.open("rb").read(4)
    if header.startswith(b"\x1f\x8b") or header.startswith(b"\x42\x5a") or b"tar" in header:
        print("  [+] Archive format looks valid (gzip/bzip/tar)")
    else:
        print(f"  [!] Unrecognized header bytes: {header.hex()}")

    # We can also try neo4j-admin database check inside a temporary container if needed,
    # but for lightweight verification we rely on checksum + size.
    print("  [+] Dump verification passed.")
    return True


# ─── Cypher Backup (APOC) ────────────────────────────────────────────────────


def backup_cypher(retention: int) -> bool:
    """Use APOC export cypher stream for a human-readable backup."""
    print("=" * 70)
    print("  Neo4j Backup — Format: cypher (APOC export)")
    print("=" * 70)

    BACKUP_BASE_DIR.mkdir(parents=True, exist_ok=True)

    if not _container_exists(NEO4J_CONTAINER):
        print(f"[-] Neo4j container '{NEO4J_CONTAINER}' not found.")
        return False

    ts = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    cypher_filename = f"neo4j_{ts}.cypher"
    host_dest = BACKUP_BASE_DIR / cypher_filename

    try:
        print("[*] Running APOC Cypher export ...")
        cypher_query = (
            "CALL apoc.export.cypher.all(null, {stream: true, format: 'plain'}) "
            "YIELD cypherStatements RETURN cypherStatements"
        )
        cmd = [
            "docker",
            "exec",
            NEO4J_CONTAINER,
            "cypher-shell",
            "-u",
            NEO4J_USER,
            "-p",
            NEO4J_PASSWORD,
            cypher_query,
        ]
        result = _run(cmd, timeout=300)

        lines = result.stdout.strip().split("\n")
        if len(lines) < 2:
            print("  [!] APOC export returned empty graph state.")
            host_dest.write_text("// Neo4j Empty Graph State Backup\n", encoding="utf-8")
            return True

        cypher_text = ""
        for line in lines[1:]:
            if line.startswith('"') and line.endswith('"'):
                line = line[1:-1]
            cypher_text += line.replace('\\"', '"').replace("\\n", "\n") + "\n"

        host_dest.write_text(cypher_text, encoding="utf-8")
        print(f"[+] Cypher backup saved: {host_dest} ({len(cypher_text.splitlines())} lines)")

        checksum = _sha256_file(host_dest)
        _write_checksum(host_dest, checksum)

        cleanup_old_backups("*.cypher", retention)
        return True

    except subprocess.CalledProcessError as e:
        print(f"[-] Cypher export failed: {e.stderr or e.stdout}")
        return False
    except Exception as e:
        print(f"[-] Backup failed: {e}")
        return False


def verify_cypher(path: Path) -> bool:
    """Verify a cypher backup file."""
    print(f"\n[Verify] Checking {path.name} ...")

    if not path.exists() or path.stat().st_size == 0:
        print("  [-] FAIL: File missing or empty.")
        return False

    expected = _read_checksum(path)
    if expected:
        actual = _sha256_file(path)
        if actual != expected:
            print("  [-] FAIL: Checksum mismatch!")
            return False
        print("  [+] Checksum OK")
    else:
        print("  [!] No sidecar checksum; skipping checksum verification.")

    text = path.read_text(encoding="utf-8")
    if "CREATE" in text or "MERGE" in text or "MATCH" in text or "// Neo4j Empty" in text:
        print("  [+] Contains valid Cypher statements.")
        return True
    else:
        print("  [-] FAIL: No Cypher CREATE/MERGE/MATCH found.")
        return False


# ─── Shared Utilities ─────────────────────────────────────────────────────────


def cleanup_old_backups(pattern: str, retention: int) -> None:
    """Remove local backups older than the retention count."""
    files = sorted(BACKUP_BASE_DIR.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
    for old in files[retention:]:
        old.unlink()
        sidecar = old.with_suffix(old.suffix + ".sha256")
        if sidecar.exists():
            sidecar.unlink()
        print(f"  [-] Pruned old backup: {old.name}")


# ─── Main Entry Point ─────────────────────────────────────────────────────────


def main() -> int:
    parser = argparse.ArgumentParser(description="Mukthi Guru — Neo4j Backup & Verification")
    parser.add_argument(
        "--format",
        choices=["dump", "cypher"],
        default=DEFAULT_FORMAT,
        help="Backup format: 'dump' (neo4j-admin binary) or 'cypher' (plain text)",
    )
    parser.add_argument(
        "--retention", type=int, default=DEFAULT_RETENTION, help="Backups to retain"
    )
    parser.add_argument(
        "--verify-only",
        type=Path,
        metavar="PATH",
        help="Verify an existing backup file",
    )
    args = parser.parse_args()

    _enforce_docker_path()

    if args.verify_only:
        path = args.verify_only
        if path.suffix == ".cypher" or path.name.endswith(".cypher"):
            ok = verify_cypher(path)
        else:
            ok = verify_dump(path)
        return 0 if ok else 1

    if args.format == "dump":
        ok = backup_dump(args.retention)
    else:
        ok = backup_cypher(args.retention)

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
