"""DATA-11 / T3-08: Tests for Supabase migration lint guard and schema snapshot."""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure repo root is on sys.path so scripts.guards can be imported
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.guards.migration_lint import (
    BASELINE_MIGRATION,
    audit_migrations_for_duplicates,
    diff_schema_snapshot,
    find_created_tables,
)


def test_find_created_tables():
    sql = """
    -- This is a comment: CREATE TABLE fake (id int);
    /* Block comment:
       CREATE TABLE another_fake (id int);
    */
    CREATE TABLE users (
        id uuid primary key
    );
    CREATE TABLE IF NOT EXISTS public.profiles (
        id uuid references users(id)
    );
    create table if not exists "audit_logs" (
        id int
    );
    """
    tables = find_created_tables(sql)
    assert tables == ["users", "profiles", "audit_logs"]


def test_no_duplicate_tables_after_baseline():
    migrations_dir = REPO_ROOT / "supabase" / "migrations"
    violations = audit_migrations_for_duplicates(migrations_dir, BASELINE_MIGRATION)
    assert violations == [], f"Found unexpected duplicate tables after baseline: {violations}"


def test_audit_flags_duplicate_after_baseline(tmp_path):
    # Migration 1: baseline
    m1 = tmp_path / "20261030000000_first.sql"
    m1.write_text("CREATE TABLE test_table (id int);", encoding="utf-8")

    # Migration 2: after baseline, duplicates test_table
    m2 = tmp_path / "20261101000000_second.sql"
    m2.write_text("CREATE TABLE IF NOT EXISTS test_table (id int, name text);", encoding="utf-8")

    violations = audit_migrations_for_duplicates(
        tmp_path, baseline_cutoff="20261030000000_first.sql"
    )
    assert len(violations) == 1
    assert violations[0].table_name == "test_table"
    assert violations[0].migration_file == "20261101000000_second.sql"
    assert violations[0].original_migration_file == "20261030000000_first.sql"


def test_diff_schema_snapshot(tmp_path):
    snap = tmp_path / "snap.sql"
    snap.write_text("CREATE TABLE alpha (id int);\n-- Comment", encoding="utf-8")

    dump_same = tmp_path / "dump_same.sql"
    dump_same.write_text("CREATE TABLE alpha (id int);\n", encoding="utf-8")

    diff = diff_schema_snapshot(snap, dump_same)
    assert diff == []

    dump_diff = tmp_path / "dump_diff.sql"
    dump_diff.write_text("CREATE TABLE beta (id int);\n", encoding="utf-8")

    diff2 = diff_schema_snapshot(snap, dump_diff)
    assert len(diff2) > 0


def test_schema_snapshot_tracked_and_valid():
    snapshot_path = REPO_ROOT / "supabase" / "schema_snapshot.sql"
    assert snapshot_path.is_file(), "supabase/schema_snapshot.sql must exist"
    assert snapshot_path.stat().st_size > 1000, "schema_snapshot.sql must not be empty"

    content = snapshot_path.read_text(encoding="utf-8")
    assert "source_releases" in content
    assert "conversations" in content
    assert "chat_messages" in content
