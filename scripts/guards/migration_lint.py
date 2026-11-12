#!/usr/bin/env python3
"""Supabase schema and migration linter guard (DATA-11 / T3-08).

Ensures:
1. No migration past the squashed baseline introduces a duplicate ``CREATE TABLE``
   for an already-defined table.
2. Committed ``supabase/schema_snapshot.sql`` exists and is valid.
3. In CI, verifies that a clean database migration matches the committed snapshot.
"""

from __future__ import annotations

import argparse
import difflib
import re
import sys
from pathlib import Path
from typing import NamedTuple

# Baseline cutoff: all migrations up to this file are part of the historical baseline.
# Any migration named after this cutoff MUST NOT recreate an existing table.
BASELINE_MIGRATION = "20261030140000_guru_memories_source_conversation.sql"

CREATE_TABLE_RE = re.compile(
    r"create\s+table(?:\s+if\s+not\s+exists)?\s+(?:public\.)?[\"']?([a-zA-Z0-9_]+)[\"']?",
    re.IGNORECASE,
)


class DuplicateTableViolation(NamedTuple):
    table_name: str
    migration_file: str
    original_migration_file: str


def find_created_tables(sql_content: str) -> list[str]:
    """Extract table names created in SQL content."""
    # Strip single-line comments (-- ...) and block comments (/* ... */)
    cleaned = re.sub(r"--.*$", "", sql_content, flags=re.MULTILINE)
    cleaned = re.sub(r"/\*.*?\*/", "", cleaned, flags=re.DOTALL)
    tables: list[str] = []
    for match in CREATE_TABLE_RE.finditer(cleaned):
        tbl = match.group(1).lower()
        if tbl not in tables:
            tables.append(tbl)
    return tables


def audit_migrations_for_duplicates(
    migrations_dir: Path,
    baseline_cutoff: str = BASELINE_MIGRATION,
) -> list[DuplicateTableViolation]:
    """Scan migrations directory for duplicate CREATE TABLE statements after baseline.

    Returns a list of DuplicateTableViolation for any new duplicate creations.
    """
    if not migrations_dir.is_dir():
        raise FileNotFoundError(f"Migrations directory not found: {migrations_dir}")

    migration_files = sorted(migrations_dir.glob("*.sql"))
    known_tables: dict[str, str] = {}
    violations: list[DuplicateTableViolation] = []

    for path in migration_files:
        content = path.read_text(encoding="utf-8")
        created = find_created_tables(content)
        is_post_baseline = path.name > baseline_cutoff

        for tbl in created:
            if tbl in known_tables and is_post_baseline:
                violations.append(
                    DuplicateTableViolation(
                        table_name=tbl,
                        migration_file=path.name,
                        original_migration_file=known_tables[tbl],
                    )
                )
            elif tbl not in known_tables:
                known_tables[tbl] = path.name

    return violations


def normalize_schema_sql(sql_content: str) -> str:
    """Normalize SQL schema dump for comparison, ignoring comments, blank lines, and trivial headers."""
    lines: list[str] = []
    for line in sql_content.splitlines():
        line_clean = line.strip()
        if not line_clean:
            continue
        if line_clean.startswith("--") or line_clean.startswith("/*"):
            continue
        # Ignore session settings that vary by pg_dump version
        if line_clean.startswith("SET ") or line_clean.startswith("SELECT pg_catalog."):
            continue
        lines.append(line_clean)
    return "\n".join(lines)


def diff_schema_snapshot(snapshot_path: Path, current_dump_path: Path) -> list[str]:
    """Compute unified diff between committed schema snapshot and clean current dump."""
    if not snapshot_path.is_file():
        return [f"Committed snapshot file missing: {snapshot_path}"]
    if not current_dump_path.is_file():
        return [f"Current dump file missing: {current_dump_path}"]

    norm_snap = normalize_schema_sql(snapshot_path.read_text(encoding="utf-8")).splitlines()
    norm_dump = normalize_schema_sql(current_dump_path.read_text(encoding="utf-8")).splitlines()

    diff = list(
        difflib.unified_diff(
            norm_snap,
            norm_dump,
            fromfile=str(snapshot_path),
            tofile=str(current_dump_path),
            lineterm="",
        )
    )
    return diff


def main() -> int:
    parser = argparse.ArgumentParser(description="Supabase schema and migration linter guard")
    parser.add_argument(
        "--migrations-dir",
        type=Path,
        default=Path("supabase/migrations"),
        help="Path to supabase/migrations directory",
    )
    parser.add_argument(
        "--snapshot-file",
        type=Path,
        default=Path("supabase/schema_snapshot.sql"),
        help="Path to supabase/schema_snapshot.sql",
    )
    parser.add_argument(
        "--dump-file",
        type=Path,
        default=None,
        help="Path to clean schema dump to diff against snapshot",
    )
    parser.add_argument(
        "--baseline-cutoff",
        type=str,
        default=BASELINE_MIGRATION,
        help="Latest historical migration in the baseline",
    )
    args = parser.parse_args()

    # 1. Audit migration duplicates
    violations = audit_migrations_for_duplicates(args.migrations_dir, args.baseline_cutoff)
    if violations:
        print(
            f"FAILED: Found {len(violations)} duplicate CREATE TABLE statement(s) after baseline:"
        )
        for v in violations:
            print(
                f"  - Table '{v.table_name}' in {v.migration_file} was already created in {v.original_migration_file}"
            )
        return 1

    # 2. Check snapshot existence
    if not args.snapshot_file.is_file():
        print(f"FAILED: Schema snapshot file not found: {args.snapshot_file}")
        return 1

    if args.snapshot_file.stat().st_size == 0:
        print(f"FAILED: Schema snapshot file is empty: {args.snapshot_file}")
        return 1

    # 3. Diff against dump file if provided
    if args.dump_file:
        diff = diff_schema_snapshot(args.snapshot_file, args.dump_file)
        if diff:
            print(f"FAILED: Schema snapshot diff detected against {args.dump_file}:")
            for line in diff[:50]:
                print(f"  {line}")
            if len(diff) > 50:
                print(f"  ... ({len(diff) - 50} more diff lines)")
            return 1

    print("SUCCESS: Migration duplicate check passed and schema snapshot is valid.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
