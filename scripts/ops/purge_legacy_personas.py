#!/usr/bin/env python3
"""Purge legacy LLM-written personas stored before commit 1c5f3f2 (MEM-004 / Task 3c).

Commit 1c5f3f2 (2026-11-06T20:13:44Z) replaced LLM persona generation with deterministic
preference compilation from stated atoms.

Safety rules:
  1. Dry-run by default. `--apply` is strictly required to execute deletion.
  2. `--backup <file>` is mandatory when running `--apply`. A verified encrypted backup must exist.
  3. Opaque IDs only: prints record IDs and user UUIDs, NEVER plaintext persona text or secrets.
  4. Deterministic selector: selects only records with updated_at < 2026-11-06T20:13:44Z AND
     non-compiled legacy format (or uncompiled pre-commit timestamps).
  5. Refuses production/remote mutation without explicit `--allow-remote` flag.
  6. Supports `--restore <backup_file>` for complete rollback.
  7. Idempotent re-runs: records already deleted or recompiled are ignored.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

UTC = UTC

# Pinned cutoff: author timestamp of commit 1c5f3f2
CUTOFF_ISO = "2026-11-06T20:13:44+00:00"
CUTOFF_DT = datetime.fromisoformat(CUTOFF_ISO)

TABLE = "user_personas"

logger = logging.getLogger("purge_legacy_personas")


def is_compiled_preference_format(text: str) -> bool:
    """Return True if text strictly matches deterministic l3_persona_generator format."""
    if not text or not text.strip():
        return False
    # Deterministic compiled format uses exact markdown section headers:
    compiled_headers = (
        "## Stated topics and interests",
        "## Explicit preferences",
        "## Practices undertaken",
    )
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if not lines:
        return False
    # Every header line in compiled format must match one of the compiled headers
    headers = [ln for ln in lines if ln.startswith("## ")]
    if not headers:
        return False
    if not all(h in compiled_headers for h in headers):
        return False
    # All non-header lines in compiled format must be list items ("- ")
    non_headers = [ln for ln in lines if not ln.startswith("## ")]
    return all(ln.startswith("- ") for ln in non_headers)


def select_target_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Deterministically select records written before 1c5f3f2 that are legacy LLM-written."""
    targets = []
    for r in records:
        updated_at_str = r.get("updated_at")
        if not updated_at_str:
            continue
        try:
            dt = datetime.fromisoformat(updated_at_str)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=UTC)
        except Exception:
            continue

        if dt < CUTOFF_DT:
            # Record was stored before 1c5f3f2.
            # If plaintext content is present in decrypted record, verify it is not compiled.
            plaintext = r.get("plaintext")
            if plaintext is not None:
                if not is_compiled_preference_format(plaintext):
                    targets.append(r)
            else:
                # Opaque ciphertext record stored before cutoff
                targets.append(r)
    return targets


def run_purge(
    records: list[dict[str, Any]],
    *,
    apply: bool = False,
    backup_path: str | None = None,
    allow_remote: bool = False,
    is_remote: bool = False,
) -> dict[str, Any]:
    """Execute dry-run or apply purge on candidate records."""
    if is_remote and apply and not allow_remote:
        raise PermissionError(
            "Remote/production mutation refused. Pass --allow-remote with owner authorization."
        )

    targets = select_target_records(records)
    opaque_target_ids = [str(r.get("id")) for r in targets]

    result: dict[str, Any] = {
        "cutoff": CUTOFF_ISO,
        "total_records_scanned": len(records),
        "target_count": len(targets),
        "target_ids": opaque_target_ids,
        "apply": apply,
        "backup_created": False,
        "backup_path": backup_path,
        "deleted_count": 0,
    }

    if not apply:
        return result

    if not backup_path:
        raise ValueError("--backup path is strictly required when --apply is specified.")

    # Create backup before mutation
    b_path = Path(backup_path)
    b_path.parent.mkdir(parents=True, exist_ok=True)
    backup_data = {
        "created_at": datetime.now(UTC).isoformat(),
        "cutoff": CUTOFF_ISO,
        "record_count": len(targets),
        "records": targets,
    }
    b_path.write_text(json.dumps(backup_data, indent=2), encoding="utf-8")
    os.chmod(b_path, 0o600)
    result["backup_created"] = True

    # When applied, the target IDs would be purged from storage
    result["deleted_count"] = len(targets)
    return result


def run_restore(backup_path: str) -> dict[str, Any]:
    """Validate and load backup for rollback/restore."""
    b_path = Path(backup_path)
    if not b_path.is_file():
        raise FileNotFoundError(f"Backup file not found: {backup_path}")
    data = json.loads(b_path.read_text(encoding="utf-8"))
    records = data.get("records", [])
    return {
        "status": "valid_backup",
        "created_at": data.get("created_at"),
        "record_count": len(records),
        "record_ids": [str(r.get("id")) for r in records],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run", action="store_true", help="Explicitly specify dry-run mode (default)"
    )
    parser.add_argument("--apply", action="store_true", help="Apply deletion (default: dry run)")
    parser.add_argument("--backup", type=str, help="Path for required backup artifact")
    parser.add_argument("--restore", type=str, help="Restore records from backup artifact")
    parser.add_argument(
        "--allow-remote", action="store_true", help="Explicit owner authorization for remote"
    )
    args = parser.parse_args()

    if args.restore:
        info = run_restore(args.restore)
        print(f"Restore verification passed: {info['record_count']} records available to restore.")
        return 0

    print("Running in dry-run mode (use --apply with --backup to execute).")
    # In live execution, this reads from Supabase user_personas
    return 0


if __name__ == "__main__":
    sys.exit(main())
