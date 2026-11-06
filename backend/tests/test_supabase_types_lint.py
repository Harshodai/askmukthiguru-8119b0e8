"""NEW-LOV-04: src/integrations/supabase/types.ts may only name tables and RPCs that
this repo's migrations create. Static; no Supabase project is contacted. A full
`supabase gen types` comparison stays an owner step (UNPROVEN)."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "guards" / "supabase_types_lint.py"


def _load():
    spec = importlib.util.spec_from_file_location("supabase_types_lint", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


TYPES_TS = """
export type Database = {
  public: {
    Tables: {
      profiles: {
        Row: { id: string }
      }
      ghost_table: {
        Row: { id: string }
      }
    }
    Functions: {
      real_rpc: {
        Args: { a: string }
        Returns: string
      }
      invented_rpc: {
        Args: Record<PropertyKey, never>
        Returns: number
      }
    }
  }
}
"""

SQL = """
CREATE TABLE IF NOT EXISTS public.profiles (id uuid);
create or replace function public.real_rpc(a text) returns text as $$ select a $$ language sql;
"""


def test_names_not_created_by_any_migration_are_reported():
    lint = _load()
    missing, n_tables, n_functions = lint.undefined_names(TYPES_TS, SQL)
    assert missing == {"table:ghost_table", "rpc:invented_rpc"}
    assert (n_tables, n_functions) == (2, 2)


def test_a_clean_pair_reports_nothing():
    lint = _load()
    sql = (
        SQL
        + "create table ghost_table (id int); create function invented_rpc() returns int as $$ select 1 $$ language sql;"
    )
    assert lint.undefined_names(TYPES_TS, sql)[0] == set()


def test_the_repository_types_file_matches_its_migrations():
    result = subprocess.run(
        [sys.executable, str(SCRIPT)], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "tables" in result.stdout


def test_the_workflow_runs_the_lint():
    text = (REPO_ROOT / ".github" / "workflows" / "supabase-schema-snapshot.yml").read_text(
        encoding="utf-8"
    )
    assert "scripts/guards/supabase_types_lint.py" in text
    assert "src/integrations/supabase/types.ts" in text
