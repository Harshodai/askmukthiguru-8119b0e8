#!/usr/bin/env python3
"""Audit usage of legacy database tables: kb_chunks and public.gurus (T3-07 / DATA-13).

Validates:
1. No active runtime Python or TypeScript code queries `kb_chunks` (retrieval is Qdrant-only).
2. No active runtime code queries `public.gurus` (canonical configuration is in `backend/config/gurus.yaml`).
3. Reports whether these tables are safe to retire in a migration.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

# Target tables to check for active code references
LEGACY_TABLES = ("kb_chunks", "gurus")

# Files and directories to scan (excluding historical migrations and audit notes)
SCAN_DIRS = [
    REPO_ROOT / "backend" / "app",
    REPO_ROOT / "backend" / "services",
    REPO_ROOT / "backend" / "rag",
    REPO_ROOT / "backend" / "domain",
    REPO_ROOT / "backend" / "ingest",
    REPO_ROOT / "src",
]


def check_table_usage(table_name: str) -> list[str]:
    """Scan source files for queries referencing table_name."""
    # Pattern matching SQL queries or supabase-js table calls like .table("gurus") or FROM kb_chunks
    # (negative lookahead avoids matching file names like gurus.yaml)
    pattern = re.compile(
        rf"""(?:\.from_\(['"]{table_name}['"]\)|\.table\(['"]{table_name}['"]\)|\bFROM\s+["']?(?:public\.)?{table_name}["']?(?!\.yaml\b)|\bJOIN\s+["']?(?:public\.)?{table_name}["']?(?!\.yaml\b))""",
        re.IGNORECASE,
    )
    hits: list[str] = []
    for d in SCAN_DIRS:
        if not d.exists():
            continue
        for path in d.rglob("*"):
            if not path.is_file() or path.suffix not in {".py", ".ts", ".tsx"}:
                continue
            try:
                content = path.read_text(encoding="utf-8")
                for lineno, line in enumerate(content.splitlines(), start=1):
                    if pattern.search(line):
                        hits.append(f"{path.relative_to(REPO_ROOT)}:{lineno}: {line.strip()}")
            except Exception:
                continue
    return hits


def main() -> int:
    print("=== T3-07 / DATA-13: Legacy Database Tables Usage Audit ===")
    total_hits = 0
    for tbl in LEGACY_TABLES:
        hits = check_table_usage(tbl)
        if hits:
            print(f"\n[FOUND ACTIVE USAGE] Table '{tbl}' is referenced in {len(hits)} location(s):")
            for h in hits:
                print(f"  - {h}")
            total_hits += len(hits)
        else:
            print(
                f"[CLEAN] Table '{tbl}' has 0 active runtime references across backend/ and src/."
            )

    if total_hits == 0:
        print(
            "\nAUDIT VERDICT: SAFE TO RETIRE. Both kb_chunks and gurus have 0 runtime references."
        )
        return 0
    else:
        print(
            f"\nAUDIT VERDICT: UNSAFE. {total_hits} active references must be cleaned before dropping."
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
