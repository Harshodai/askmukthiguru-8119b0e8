"""Every application table must be readable by the backend's own role.

Postgres checks table GRANTS before RLS policies, so a table with correct
policies and no grant fails with 42501 regardless. A survey of a database built
purely from this migration set (2026-09-12) found 22 such tables — including
`user_roles`, which made every admin check log "Admin role check failed" and
silently fall through to non-admin, and `conversation_memories`, which made
personal memory silently never reach an answer.
"""

from pathlib import Path

MIGRATIONS = Path(__file__).resolve().parents[2] / "supabase" / "migrations"
GRANT_MIGRATIONS = [
    "20260912000001_grant_memory_tables_to_service_role.sql",
    "20260912000002_grant_remaining_tables_to_service_role.sql",
]


def test_grant_migrations_exist():
    for name in GRANT_MIGRATIONS:
        assert (MIGRATIONS / name).exists(), f"{name} is missing"


def test_security_critical_tables_are_granted():
    import re

    # Column alignment in the SQL means "table<spaces>TO service_role"; compare
    # on collapsed whitespace so formatting cannot hide a missing grant.
    sql = re.sub(r"\s+", " ", "\n".join((MIGRATIONS / n).read_text() for n in GRANT_MIGRATIONS))
    for table in ("user_roles", "profiles", "conversation_memories", "user_healing_progress"):
        assert f"public.{table} TO service_role" in sql, f"{table} still has no service_role grant"


def test_receipts_stay_append_only():
    """A consent or erasure receipt must not be rewritable by the server."""
    sql = (MIGRATIONS / GRANT_MIGRATIONS[0]).read_text()
    for line in sql.splitlines():
        if "memory_consent_receipts" in line or "memory_deletion_receipts" in line:
            if line.strip().startswith("GRANT"):
                assert "UPDATE" not in line and "DELETE" not in line, line
