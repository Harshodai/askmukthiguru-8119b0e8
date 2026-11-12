#!/usr/bin/env python3
"""Check that src/integrations/supabase/types.ts only names tables and RPC functions
that the repo's migrations create (NEW-LOV-04).

This is the weak form of "types.ts equals `supabase gen types`": it needs no live
project. It catches a Lovable edit that adds an RPC or table that no migration in
this repo defines. It cannot catch a wrong column type; that needs
`supabase gen types` against a database (owner step, UNPROVEN here).

Usage: supabase_types_lint.py            (exit 1 on a mismatch)
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TYPES = ROOT / "src" / "integrations" / "supabase" / "types.ts"
MIGRATIONS = ROOT / "supabase" / "migrations"
# Names in types.ts that no migration in this repo creates. Each was found on the
# day this guard was added. Shrink only: never add one to make the check pass.
KNOWN_UNDEFINED_FILE = ROOT / "scripts" / "guards" / "supabase_types_known_undefined.txt"


def _block(text: str, header: str) -> str:
    """The body of the first `header: {` block, found by brace matching."""
    start = text.index(header)
    depth = 0
    for i in range(text.index("{", start), len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return text[text.index("{", start) + 1 : i]
    raise ValueError(f"unbalanced braces after {header!r}")


def _top_level_names(body: str) -> set[str]:
    """Keys one level deep in a TS object literal body (tables, functions)."""
    names, depth = set(), 0
    for line in body.splitlines():
        stripped = line.strip()
        if depth == 0:
            m = re.match(r"^([A-Za-z_][\w]*)\s*:\s*\{", stripped)
            if m:
                names.add(m.group(1))
        depth += line.count("{") - line.count("}")
    return names


def types_names(text: str) -> tuple[set[str], set[str]]:
    public = _block(text, "public: {")
    tables = _top_level_names(_block(public, "Tables: {"))
    functions = _top_level_names(_block(public, "Functions: {"))
    return tables, functions


def migration_names(sql: str) -> tuple[set[str], set[str]]:
    flags = re.IGNORECASE
    tables = set(
        re.findall(
            r"create\s+table\s+(?:if\s+not\s+exists\s+)?(?:public\.)?\"?(\w+)\"?", sql, flags
        )
    )
    for _old, new in re.findall(
        r"alter\s+table\s+(?:only\s+)?(?:public\.)?\"?(\w+)\"?\s+rename\s+to\s+\"?(\w+)\"?",
        sql,
        flags,
    ):
        tables.add(new)
    functions = set(
        re.findall(
            r"create\s+(?:or\s+replace\s+)?function\s+(?:public\.)?\"?(\w+)\"?\s*\(", sql, flags
        )
    )
    return tables, functions


def undefined_names(types_text: str, sql: str) -> tuple[set[str], int, int]:
    """Names in types.ts that no migration creates, plus the table and RPC counts."""
    tables, functions = types_names(types_text)
    m_tables, m_functions = migration_names(sql)
    missing = {f"table:{t}" for t in tables - m_tables} | {
        f"rpc:{f}" for f in functions - m_functions
    }
    return missing, len(tables), len(functions)


def main() -> int:
    sql = "\n".join(
        p.read_text(encoding="utf-8", errors="ignore") for p in sorted(MIGRATIONS.glob("*.sql"))
    )
    missing, n_tables, n_functions = undefined_names(TYPES.read_text(encoding="utf-8"), sql)
    tables, functions = range(n_tables), range(n_functions)
    known = set()
    if KNOWN_UNDEFINED_FILE.exists():
        known = {
            ln.strip()
            for ln in KNOWN_UNDEFINED_FILE.read_text(encoding="utf-8").splitlines()
            if ln.strip() and not ln.startswith("#")
        }
    new = sorted(missing - known)
    stale = sorted(known - missing)
    for item in new:
        print(f"FAIL types.ts names {item} but no migration creates it")
    for item in stale:
        print(f"FAIL {item} is now defined; remove it from {KNOWN_UNDEFINED_FILE.name}")
    if not new and not stale:
        print(
            f"ok: {len(tables)} tables and {len(functions)} RPCs in types.ts; {len(missing)} known gaps"
        )
    return 1 if new or stale else 0


if __name__ == "__main__":
    sys.exit(main())
