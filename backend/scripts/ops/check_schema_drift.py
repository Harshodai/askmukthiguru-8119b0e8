#!/usr/bin/env python3
"""Schema drift preflight (2026-11-19 never-again guard). Read-only; prints no secrets.

1. Migration versions: every ``supabase/migrations/<version>_*.sql`` must be applied and
   nothing applied may be missing from the repo (``--applied-versions FILE``, one version
   per line, e.g. from the Supabase ``list_migrations`` tool or
   ``select version from supabase_migrations.schema_migrations``).
2. Row models: every field a ``Dataclass(**row)`` / ``asdict(...)`` model writes must be a
   column of its table. Columns come from the migrations (``CREATE TABLE`` in version
   order, honouring ``IF NOT EXISTS``, plus ``ALTER TABLE ... ADD/DROP COLUMN``) or, with
   ``--live-columns FILE`` (JSON ``{table: [columns]}`` from information_schema), from the
   live database. Failure class: user_profiles gained ``tenant_id`` and ``UserProfile(**row)``
   raised on every fetch, silently serving an empty profile.

Exit 0 = no drift, 1 = drift, 2 = usage error.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import fields, is_dataclass
from pathlib import Path

_HERE = Path(__file__).resolve()
if (_HERE.parents[2] / "app").is_dir():
    _BACKEND = _HERE.parents[2]
    _REPO = _BACKEND.parent if (_BACKEND.parent / "supabase").is_dir() else _BACKEND
elif (_HERE.parents[2] / "backend" / "app").is_dir():
    _BACKEND = _HERE.parents[2] / "backend"
    _REPO = _HERE.parents[2]
else:
    _BACKEND = Path("/app")
    _REPO = Path("/app") if (Path("/app/supabase")).is_dir() else Path("/")
MIGRATIONS = _REPO / "supabase" / "migrations"

# Row model -> table it is written to. Add a model here when it round-trips a table.
ROW_MODELS = {"services.user_profile_service:UserProfile": "user_profiles"}

_CREATE_RE = re.compile(
    r"create\s+table\s+(if\s+not\s+exists\s+)?(?:public\.)?\"?(\w+)\"?\s*\((.*?)\);",
    re.IGNORECASE | re.DOTALL,
)
_ALTER_RE = re.compile(
    r"alter\s+table\s+(?:if\s+exists\s+)?(?:only\s+)?(?:public\.)?\"?(\w+)\"?\s+(.*?);",
    re.IGNORECASE | re.DOTALL,
)
_ADD_RE = re.compile(r"add\s+column\s+(?:if\s+not\s+exists\s+)?\"?(\w+)\"?", re.IGNORECASE)
_DROP_RE = re.compile(r"drop\s+column\s+(?:if\s+exists\s+)?\"?(\w+)\"?", re.IGNORECASE)
_NOT_COLUMN = {"constraint", "primary", "unique", "foreign", "check", "exclude", "like"}


def _strip_comments(sql: str) -> str:
    sql = re.sub(r"/\*.*?\*/", "", sql, flags=re.DOTALL)
    return re.sub(r"--[^\n]*", "", sql)


def _column_names(body: str) -> list[str]:
    cols, depth, cur = [], 0, ""
    for ch in body:  # split on top-level commas only
        depth += ch == "("
        depth -= ch == ")"
        if ch == "," and depth == 0:
            cols.append(cur)
            cur = ""
        else:
            cur += ch
    cols.append(cur)
    names = []
    for c in cols:
        first = c.strip().split(None, 1)[0].strip('"').lower() if c.strip() else ""
        if first and first not in _NOT_COLUMN:
            names.append(first)
    return names


def migration_columns(migrations_dir: Path = MIGRATIONS) -> dict[str, set[str]]:
    tables: dict[str, set[str]] = {}
    for path in sorted(migrations_dir.glob("*.sql")):
        sql = _strip_comments(path.read_text(encoding="utf-8"))
        events = [(m.start(), "create", m) for m in _CREATE_RE.finditer(sql)]
        events += [(m.start(), "alter", m) for m in _ALTER_RE.finditer(sql)]
        for _, kind, m in sorted(events, key=lambda e: e[0]):
            if kind == "create":
                table = m.group(2).lower()
                if m.group(1) and table in tables:
                    continue  # IF NOT EXISTS: the first definition wins
                tables[table] = set(_column_names(m.group(3)))
            else:
                table, action = m.group(1).lower(), m.group(2)
                tables.setdefault(table, set()).update(c.lower() for c in _ADD_RE.findall(action))
                tables[table].difference_update(c.lower() for c in _DROP_RE.findall(action))
    return tables


def version_drift(applied: set[str], migrations_dir: Path = MIGRATIONS) -> list[str]:
    repo = {p.name.split("_", 1)[0] for p in migrations_dir.glob("*.sql")}
    problems = [f"migration {v} is in the repo but not applied" for v in sorted(repo - applied)]
    problems += [f"migration {v} is applied but missing from the repo" for v in sorted(applied - repo)]
    return problems


def model_drift(columns: dict[str, set[str]], models: dict[str, str] = ROW_MODELS) -> list[str]:
    import importlib

    problems = []
    for ref, table in models.items():
        module, name = ref.split(":")
        model = getattr(importlib.import_module(module), name)
        if not is_dataclass(model):
            problems.append(f"{ref} is not a dataclass")
            continue
        missing = sorted({f.name for f in fields(model)} - columns.get(table, set()))
        if missing:
            problems.append(f"{ref} writes fields with no column in {table}: {missing}")
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--applied-versions", help="file: one applied migration version per line")
    parser.add_argument("--live-columns", help="file: JSON {table: [columns]} from the live DB")
    args = parser.parse_args(argv)
    problems: list[str] = []
    if args.applied_versions:
        applied = {
            line.strip()
            for line in Path(args.applied_versions).read_text().splitlines()
            if line.strip()
        }
        problems += version_drift(applied)
    if args.live_columns:
        live = json.loads(Path(args.live_columns).read_text())
        columns = {t.lower(): {c.lower() for c in cols} for t, cols in live.items()}
    else:
        columns = migration_columns()
    problems += model_drift(columns)
    for p in problems:
        print(f"DRIFT: {p}", file=sys.stderr)
    if not problems:
        print("No schema drift.")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.path.insert(0, str(_BACKEND))
    raise SystemExit(main())
