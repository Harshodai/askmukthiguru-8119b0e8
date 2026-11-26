"""Schema drift guard: migrations vs applied versions, row models vs table columns."""

from __future__ import annotations

from scripts.ops import check_schema_drift as drift


def _write(tmp_path, name, sql):
    (tmp_path / name).write_text(sql, encoding="utf-8")


def test_if_not_exists_keeps_the_first_definition_and_alter_adds(tmp_path):
    _write(
        tmp_path,
        "001_a.sql",
        "CREATE TABLE IF NOT EXISTS public.t (id uuid PRIMARY KEY, a text, CONSTRAINT c CHECK (a <> ''));",
    )
    _write(
        tmp_path,
        "002_b.sql",
        "-- other shape\nCREATE TABLE IF NOT EXISTS public.t (zzz int);\nALTER TABLE public.t ADD COLUMN IF NOT EXISTS tenant_id text;",
    )
    _write(tmp_path, "003_c.sql", "ALTER TABLE t DROP COLUMN a;")
    assert drift.migration_columns(tmp_path) == {"t": {"id", "tenant_id"}}


def test_version_drift_both_directions(tmp_path):
    _write(tmp_path, "20260101000000_x.sql", "select 1;")
    _write(tmp_path, "20260102000000_y.sql", "select 1;")
    problems = drift.version_drift({"20260101000000", "20269999000000"}, tmp_path)
    assert problems == [
        "migration 20260102000000 is in the repo but not applied",
        "migration 20269999000000 is applied but missing from the repo",
    ]


def test_model_field_without_a_column_is_drift():
    cols = {"user_profiles": {"user_id", "created_at"}}
    (problem,) = drift.model_drift(cols)
    assert "preferred_language" in problem


def test_repo_migrations_cover_every_row_model_field():
    """The real migrations define every column the registered row models write."""
    assert drift.model_drift(drift.migration_columns()) == []
