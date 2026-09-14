#!/usr/bin/env python3
"""Read-only readiness audit for a live Supabase project.

Every check here exists because the same gap was found on a database built
purely from this repo's migrations, and every one of them fails SILENTLY in
production:

  * `canonical_memory_events` missing  -> the memory row commits, the audit
    insert raises, POST /api/memory/canonical returns 500, and a seeker is told
    "Failed to save memory" about a memory that saved. A retry duplicates it.
  * table GRANTs missing for service_role -> Postgres checks grants BEFORE RLS,
    so correct policies do not help. `user_roles` denied means every admin check
    logs a warning and falls through to NON-ADMIN. `conversation_memories`
    denied means personal memory never reaches an answer.
  * the actor CHECK too narrow -> resolver/consolidator audit writes raise
    23514 inside a swallowing except: memories accumulate with no audit trail
    and the GDPR export under-reports them.
  * write GRANTs (INSERT/UPDATE/DELETE) missing for service_role -> reads can
    pass this audit while every write 42501s. The read-only grant sweep above
    would not have caught that; it is a separate privilege per SQL, not a
    consequence of SELECT working.

STRICTLY READ-ONLY: the audit itself issues nothing but SELECTs — checking
whether a write WOULD be allowed via has_table_privilege is not the same as
performing one. It never inserts, updates, or deletes a single row. It runs SELECTs against information_schema/pg_catalog via
PostgREST RPC or a direct connection and mutates nothing. Give it the SAME
credentials the backend uses, or it will report gaps the backend does not have.

Usage:
    export SUPABASE_DB_URL='postgresql://...'        # preferred: direct, read-only
    python backend/scripts/ops/audit_supabase_readiness.py
    python backend/scripts/ops/audit_supabase_readiness.py --json

Exit code 0 = ready, 1 = at least one FAIL, 2 = could not connect.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys

# Tables the backend's own role must be able to read. Derived from the 2026-09-12
# sweep that found 27 unreadable tables on a migrations-only database.
REQUIRED_READABLE = [
    "canonical_memories",
    "canonical_memory_events",
    "conversation_memories",
    "memory_consent_receipts",
    "memory_deletion_receipts",
    "memory_outbox",
    "user_roles",
    "profiles",
    "user_healing_progress",
    "chat_responses",
]

# Write verbs service_role actually issues against each table, one entry per
# table+verb pair actually called in backend/ (grep for .insert(/.update(/
# .upsert(/.delete( against each table's name, 2026-09-14). `profiles` and
# `user_healing_progress` are read from REQUIRED_READABLE above but no write
# call site exists in this codebase — profiles is populated by Supabase auth,
# not app code — so they are deliberately absent here rather than guessed at.
# canonical_memory_events is INSERT-only by design: it is an append-only
# ledger: an UPDATE/DELETE grant on it would be a privilege escalation, not a
# gap, so its absence is correct and this audit must not flag it.
REQUIRED_WRITES: dict[str, list[str]] = {
    "canonical_memories": ["INSERT", "UPDATE", "DELETE"],
    "canonical_memory_events": ["INSERT"],
    "conversation_memories": ["INSERT", "UPDATE"],
    "memory_consent_receipts": ["INSERT"],
    "memory_deletion_receipts": ["INSERT"],
    "memory_outbox": ["INSERT", "UPDATE", "DELETE"],
    "user_roles": ["INSERT", "UPDATE", "DELETE"],
    "chat_responses": ["INSERT", "UPDATE"],
}

# Writers of canonical_memory_events, verified in the source.
REQUIRED_ACTORS = ["user", "resolver", "consolidator"]

# Must have RLS on: these carry one seeker's private content.
REQUIRED_RLS = ["canonical_memories", "canonical_memory_events", "conversation_memories"]


def _sql_literal_list(values: list[str]) -> str:
    """Render a constant list as a SQL array literal.

    Every value here is a module-level constant in this file, never user input.
    Quotes are still escaped so a future edit cannot introduce an injection.
    """
    escaped = ", ".join("'" + v.replace("'", "''") + "'" for v in values)
    return "ARRAY[" + escaped + "]"


class _Runner:
    """Executes read-only SQL via psycopg when available, else the psql CLI.

    An operator auditing production should not have to install a driver first,
    and psql ships with Postgres.
    """

    def __init__(self, url: str) -> None:
        self._url = url
        self._conn = None
        try:
            import psycopg2  # type: ignore

            self._conn = psycopg2.connect(url)
        except ImportError:
            try:
                import psycopg  # type: ignore

                self._conn = psycopg.connect(url)
            except ImportError:
                self._conn = None
        except Exception as exc:  # noqa: BLE001 — never leak the URL
            print(f"Could not connect: {type(exc).__name__}", file=sys.stderr)
            raise SystemExit(2) from None

        if self._conn is None and not shutil.which("psql"):
            print(
                "Need either psycopg2/psycopg or the psql CLI to run this audit.",
                file=sys.stderr,
            )
            raise SystemExit(2)

    def rows(self, sql: str) -> list[list[str]]:
        if self._conn is not None:
            with self._conn.cursor() as cur:
                cur.execute(sql)
                return [[("" if v is None else str(v)) for v in r] for r in cur.fetchall()]
        proc = subprocess.run(
            ["psql", self._url, "-tAF", "\x1f", "-c", sql],
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            print(f"psql failed: {proc.stderr.strip()[:200]}", file=sys.stderr)
            raise SystemExit(2)
        out = []
        for line in proc.stdout.splitlines():
            if line.strip():
                out.append(line.split("\x1f"))
        return out

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()


def _connect() -> _Runner:
    url = os.environ.get("SUPABASE_DB_URL") or os.environ.get("DATABASE_URL")
    if not url:
        print(
            "SUPABASE_DB_URL (or DATABASE_URL) is required — a Postgres "
            "connection string for the project you want audited.",
            file=sys.stderr,
        )
        raise SystemExit(2)
    return _Runner(url)


def _q(cur, sql: str, args: tuple = ()) -> list[tuple]:
    cur.execute(sql, args)
    return cur.fetchall()


def audit() -> dict:
    findings: list[dict] = []

    def add(check: str, ok: bool, detail: str) -> None:
        findings.append({"check": check, "status": "PASS" if ok else "FAIL", "detail": detail})

    db = _connect()
    try:
        wanted = _sql_literal_list(REQUIRED_READABLE)

        # 1. Required tables exist.
        present = {
            r[0]
            for r in db.rows(
                "select table_name from information_schema.tables "
                f"where table_schema='public' and table_name = any({wanted})"
            )
        }
        for table in REQUIRED_READABLE:
            add(f"table:{table}", table in present, "exists" if table in present else "MISSING")

        # 2. service_role can read them (grants are checked before RLS).
        # has_table_privilege, NOT information_schema.role_table_grants: that view only
        # shows grants where the CONNECTING role is grantor, grantee, or a member of the
        # grantee, so a least-privilege reader sees zero service_role grants and the
        # audit reports a perfectly healthy database as entirely unreadable.
        readable = {
            r[0]
            for r in db.rows(
                "select t.table_name from information_schema.tables t "
                "where t.table_schema='public' "
                f"and t.table_name = any({wanted}) "
                "and has_table_privilege('service_role', "
                "    'public.' || quote_ident(t.table_name), 'SELECT')"
            )
        }
        for table in sorted(present):
            ok = table in readable
            add(
                f"grant:{table}",
                ok,
                "service_role SELECT" if ok else "NO service_role SELECT — reads fail with 42501",
            )

        # 3. service_role can perform the writes the code actually issues.
        # Read access passing tells you nothing about write access — they are
        # separate GRANTs in Postgres, so this is not redundant with step 2.
        write_pairs = [(t, v) for t, verbs in REQUIRED_WRITES.items() for v in verbs]
        writable = {
            (r[0], r[1])
            for r in db.rows(
                "select t.table_name, w.verb from information_schema.tables t "
                "cross join (values "
                + ", ".join(f"('{t}', '{v}')" for t, v in write_pairs)
                + ") as w(tbl, verb) "
                "where t.table_schema='public' and t.table_name = w.tbl "
                "and has_table_privilege('service_role', "
                "    'public.' || quote_ident(t.table_name), w.verb)"
            )
        }
        for table, verb in write_pairs:
            ok = (table, verb) in writable
            add(
                f"grant_write:{table}:{verb.lower()}",
                ok,
                f"service_role {verb}"
                if ok
                else f"NO service_role {verb} — writes fail with 42501",
            )

        # 4. Whole-schema sweep: anything else the server role cannot read.
        ungranted = [
            r[0]
            for r in db.rows(
                "select t.table_name from information_schema.tables t "
                "where t.table_schema='public' and t.table_type='BASE TABLE' "
                "and not has_table_privilege('service_role', "
                "    'public.' || quote_ident(t.table_name), 'SELECT') order by 1"
            )
        ]
        add(
            "grant:all_public_tables",
            not ungranted,
            "every public table readable by service_role"
            if not ungranted
            else f"{len(ungranted)} table(s) unreadable: {', '.join(ungranted[:12])}"
            + (" ..." if len(ungranted) > 12 else ""),
        )

        # 5. RLS on the private tables.
        rls = {
            r[0]: r[1]
            for r in db.rows(
                "select relname, relrowsecurity::text from pg_class "
                f"where relname = any({_sql_literal_list(REQUIRED_RLS)}) and relkind='r'"
            )
        }
        for table in REQUIRED_RLS:
            if table not in rls:
                add(f"rls:{table}", False, "table missing, cannot verify RLS")
            else:
                on = str(rls[table]).lower() in ("t", "true")
                add(f"rls:{table}", on, "enabled" if on else "DISABLED")

        # 6. The actor CHECK admits every writer.
        defn = db.rows(
            "select pg_get_constraintdef(oid) from pg_constraint "
            "where conname='canonical_memory_events_actor_check'"
        )
        if not defn:
            add("constraint:actor_check", False, "constraint absent — cannot verify audit writers")
        else:
            definition = defn[0][0]
            missing = [a for a in REQUIRED_ACTORS if f"'{a}'" not in definition]
            add(
                "constraint:actor_check",
                not missing,
                "admits all writers"
                if not missing
                else f"rejects {missing} — audit writes raise 23514 and are swallowed",
            )
    finally:
        db.close()

    fails = [f for f in findings if f["status"] == "FAIL"]
    return {"ready": not fails, "failures": len(fails), "findings": findings}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true", help="Machine-readable output.")
    args = ap.parse_args()

    report = audit()
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        for f in report["findings"]:
            mark = "ok  " if f["status"] == "PASS" else "FAIL"
            print(f"  [{mark}] {f['check']}: {f['detail']}")
        print()
        print("READY" if report["ready"] else f"NOT READY — {report['failures']} failure(s)")
    return 0 if report["ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
