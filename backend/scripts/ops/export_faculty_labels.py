#!/usr/bin/env python3
"""Export faculty answer labels (public.faculty_answer_labels) to CSV.

Reads with the backend's service_role Supabase client (RLS owner-scoping
applies to reviewers, not to this export). Read-only: issues one paged SELECT
and never writes to the database.

Usage:
    python backend/scripts/ops/export_faculty_labels.py --out labels.csv
    python backend/scripts/ops/export_faculty_labels.py --since 2026-10-01 --out -

Exit code 0 = exported (possibly zero rows), 2 = Supabase unavailable / query
failed. A failed query is never reported as an empty export.
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections.abc import Iterable
from typing import Any, Optional, TextIO

TABLE = "faculty_answer_labels"
COLUMNS = [
    "created_at",
    "updated_at",
    "user_id",
    "trace_id",
    "request_id",
    "message_id",
    "model",
    "policy_id",
    "release_id",
    "faithful",
    "safe",
    "helpful",
    "note",
]
PAGE = 1000
# Spreadsheet formula injection: a reviewer note beginning with these would
# execute when the CSV is opened in Excel/Sheets.
_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def _cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "yes" if value else "no"
    text = str(value)
    return "'" + text if text.startswith(_FORMULA_PREFIXES) else text


def write_csv(rows: Iterable[dict[str, Any]], out: TextIO) -> int:
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(COLUMNS)
    n = 0
    for row in rows:
        writer.writerow([_cell(row.get(c)) for c in COLUMNS])
        n += 1
    return n


def fetch_labels(client: Any, since: Optional[str] = None) -> list[dict[str, Any]]:
    """Page through all labels, oldest first. Raises on query failure."""
    rows: list[dict[str, Any]] = []
    start = 0
    while True:
        q = client.table(TABLE).select(",".join(COLUMNS)).order("created_at")
        if since:
            q = q.gte("created_at", since)
        batch = q.range(start, start + PAGE - 1).execute().data or []
        rows.extend(batch)
        if len(batch) < PAGE:
            return rows
        start += PAGE


def main(argv: Optional[list[str]] = None, client: Any = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", default="-", help="CSV path, or - for stdout")
    ap.add_argument("--since", help="ISO date/time lower bound on created_at")
    args = ap.parse_args(argv)

    if client is None:
        from app.telemetry_db import _get_client

        client = _get_client()
    if not client:
        print("Supabase client unavailable; nothing exported.", file=sys.stderr)
        return 2
    try:
        rows = fetch_labels(client, args.since)
    except Exception as exc:  # noqa: BLE001 - report, never export a partial/empty file
        print(f"Query failed: {exc}", file=sys.stderr)
        return 2

    if args.out == "-":
        n = write_csv(rows, sys.stdout)
    else:
        with open(args.out, "w", newline="", encoding="utf-8") as fh:
            n = write_csv(rows, fh)
    print(f"Exported {n} label(s).", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
