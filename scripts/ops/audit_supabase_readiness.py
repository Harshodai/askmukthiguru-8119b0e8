#!/usr/bin/env python3
"""Read-only audit of a live Supabase against the gaps found on 2026-09-12/13.

Run this against production YOURSELF. It needs credentials, and it is written so
that nobody else needs to see them: it reads them from the environment, never
prints them, never writes anything, and issues only `select ... limit 1`.

    export SUPABASE_URL='https://<project>.supabase.co'
    export SUPABASE_SERVICE_ROLE_KEY='<service role key>'
    python3 scripts/ops/audit_supabase_readiness.py

Exit codes: 0 = clean, 1 = gaps found, 2 = could not run.

WHY A BEHAVIOURAL PROBE, NOT A SCHEMA QUERY
-------------------------------------------
The two defects this looks for are both invisible to "does the table exist?":

  * `canonical_memory_events` was written by the API on every memory mutation
    and read by the GDPR export, but no migration ever created it. The memory
    row inserted, the audit insert raised, and the endpoint returned 500 — so a
    seeker was told "Failed to save memory" about a memory that HAD saved, and a
    retry duplicated it.
  * 27 tables had no GRANT for `service_role`. Postgres checks grants BEFORE RLS
    policies, so perfect RLS does not help a role with no table privilege.
    `user_roles` denied meant every admin check logged a warning and quietly fell
    through to non-admin; `conversation_memories` denied meant personal memory
    silently never reached an answer.

So this asks the database the same question the application asks, with the same
role, and classifies the answer. A 42501 means "the app cannot read this";
PGRST205 means "this table is not there at all".
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

# Tables the backend reads or writes with the service-role client. Grouped so the
# report says what breaks, not just which name failed.
TABLES: dict[str, list[str]] = {
    "canonical memory (read path + audit trail)": [
        "canonical_memories",
        "canonical_memory_events",
    ],
    "memory (legacy path, consent, erasure)": [
        "conversation_memories",
        "memory_outbox",
        "memory_consent_receipts",
        "memory_deletion_receipts",
        "memory_compaction_snapshots",
        "guru_memories",
        "guru_core_memory",
    ],
    "authorization (a denial here silently downgrades admins)": [
        "user_roles",
        "profiles",
        "user_profiles",
    ],
    "telemetry (an unreadable table makes hallucination alerting vacuous)": [
        "chat_responses",
        "trace_spans",
    ],
    "conversations": ["conversations", "chat_messages", "chat_sessions"],
    "product surfaces": [
        "user_healing_progress",
        "feedback_events",
        "ingest_jobs",
        "okf_review_queue",
        "study_notebooks",
        "user_episodes",
        "assistant_scope_metadata",
        "daily_teachings",
    ],
}

OK, MISSING, DENIED, OTHER = "ok", "missing", "denied", "other"


def _probe(base: str, key: str, table: str, timeout: float = 15.0) -> tuple[str, str]:
    """One `select ... limit 1` as the service role. Returns (status, detail)."""
    url = f"{base.rstrip('/')}/rest/v1/{table}?select=*&limit=1"
    req = urllib.request.Request(
        url,
        headers={
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            resp.read(256)
            return OK, ""
    except urllib.error.HTTPError as exc:
        try:
            body = json.loads(exc.read().decode() or "{}")
        except Exception:
            body = {}
        code = str(body.get("code") or "")
        message = str(body.get("message") or exc.reason or "")
        if code == "42501" or "permission denied" in message.lower():
            return DENIED, message
        if code == "PGRST205" or "could not find the table" in message.lower():
            return MISSING, message
        return OTHER, f"HTTP {exc.code} {code} {message}"[:200]
    except Exception as exc:  # network, DNS, TLS
        return OTHER, f"{type(exc).__name__}: {exc}"[:200]


def main() -> int:
    base = os.environ.get("SUPABASE_URL", "").strip()
    key = (
        os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
        or os.environ.get("SUPABASE_KEY")
        or ""
    ).strip()
    if not base or not key:
        print("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set.", file=sys.stderr)
        print("Nothing was read. No credentials are printed by this script.", file=sys.stderr)
        return 2

    # Identify the project without ever echoing the key.
    host = base.split("//")[-1].split("/")[0]
    print(f"Auditing {host} as service_role (read-only)\n")

    findings: dict[str, list[tuple[str, str, str]]] = {DENIED: [], MISSING: [], OTHER: []}
    for group, tables in TABLES.items():
        print(f"{group}")
        for table in tables:
            status, detail = _probe(base, key, table)
            mark = {OK: "  ok    ", MISSING: "  MISSING", DENIED: "  DENIED ", OTHER: "  ?      "}[status]
            print(f"{mark} {table}")
            if status != OK:
                findings[status].append((group, table, detail))
        print()

    denied, missing, other = findings[DENIED], findings[MISSING], findings[OTHER]
    print("=" * 72)
    if not (denied or missing):
        print("CLEAN — every audited table is readable by service_role.")
        if other:
            print(f"\n{len(other)} table(s) could not be classified (see below); treat as unknown.")
            for _g, t, d in other:
                print(f"  ? {t}: {d}")
        return 0

    if missing:
        print(f"\nMISSING TABLES ({len(missing)}) — the code writes or reads these, and they are not there.")
        print("Any endpoint touching one returns 500. Apply the migrations that create them.")
        for _g, t, d in missing:
            print(f"  - {t}")

    if denied:
        print(f"\nPERMISSION DENIED ({len(denied)}) — the table exists and service_role cannot read it.")
        print("Postgres checks GRANTS before RLS, so policies do not help here. These fail")
        print("QUIETLY: the app logs a warning and degrades (admins become non-admins,")
        print("personal memory never reaches an answer).")
        print("\nRemediation (review before running — this grants the SERVER role only;")
        print("RLS still governs what anon/authenticated can see):")
        for _g, t, _d in denied:
            print(f"  GRANT SELECT, INSERT, UPDATE, DELETE ON public.{t} TO service_role;")

    if other:
        print(f"\nUNCLASSIFIED ({len(other)}):")
        for _g, t, d in other:
            print(f"  ? {t}: {d}")

    print("\nRepo migrations that fix the known cases:")
    print("  supabase/migrations/20260912000000_create_canonical_memory_events.sql")
    print("  supabase/migrations/20260912000001_grant_memory_tables_to_service_role.sql")
    print("  supabase/migrations/20260912000002_grant_remaining_tables_to_service_role.sql")
    print("  supabase/migrations/20260913000000_grant_update_on_consent_receipts.sql")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
