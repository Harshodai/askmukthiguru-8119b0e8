"""Static contract for the forward-only faculty-reviewer RLS migration.

The local test environment does not run Supabase/PostgREST, so this guards the
policy text that a real migration applies. It complements the cross-user proof
for the original owner-scoped table.
"""

import re
from pathlib import Path

MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "supabase"
    / "migrations"
    / "20261122000000_faculty_labels_reviewer_role.sql"
)


def _sql() -> str:
    return MIGRATION.read_text(encoding="utf-8")


def test_every_faculty_label_policy_requires_trusted_reviewer_role_and_owner():
    sql = _sql()
    policies = re.findall(r"CREATE POLICY (\w+) ON public\.faculty_answer_labels(.*?);", sql, re.S)
    assert len(policies) == 4
    for name, body in policies:
        compact = " ".join(body.split())
        assert "TO authenticated" in compact, name
        assert "auth.uid() = user_id" in compact, name
        assert "auth.jwt() -> 'app_metadata' ->> 'role'" in compact, name
        assert "'faculty_reviewer'" in compact, name
        assert "user_metadata" not in compact, name


def test_migration_is_forward_only_and_does_not_weaken_service_role_export():
    sql = _sql()
    assert "DROP POLICY IF EXISTS" in sql
    assert "GRANT" not in sql
    assert "-- REVERT:" in sql


ADMIN_MIGRATION = MIGRATION.with_name("20261128120000_faculty_labels_admin_role.sql")


def test_admin_migration_allows_admin_or_reviewer_but_keeps_own_row_and_authenticated_only():
    sql = ADMIN_MIGRATION.read_text(encoding="utf-8")
    policies = re.findall(r"CREATE POLICY (\w+) ON public\.faculty_answer_labels(.*?);", sql, re.S)
    assert {n for n, _ in policies} == {
        "faculty_labels_select_own",
        "faculty_labels_insert_own",
        "faculty_labels_update_own",
        "faculty_labels_delete_own",
    }
    for name, body in policies:
        compact = " ".join(body.split())
        assert "TO authenticated" in compact, name  # anon is blocked
        assert "TO anon" not in compact and "TO public" not in compact, name
        # own-row scoping AND (reviewer claim OR admin); a plain user matches neither
        assert "auth.uid() = user_id AND (" in compact, name
        assert "auth.jwt() -> 'app_metadata' ->> 'role', '') = 'faculty_reviewer' OR" in compact, (
            name
        )
        assert "public.has_role(auth.uid(), 'admin'::public.app_role)" in compact, name
        assert "user_metadata" not in compact, name
    # every policy is replaced idempotently
    assert sql.count("DROP POLICY IF EXISTS") == 4
    assert "GRANT" not in sql
    assert "-- REVERT:" in sql


def test_admin_migration_sorts_after_every_other_migration():
    names = sorted(p.name for p in MIGRATION.parent.glob("*.sql"))
    assert names[-1] >= ADMIN_MIGRATION.name
    assert ADMIN_MIGRATION.name > MIGRATION.name
