"""The prod readiness audit must be able to FAIL.

A gate that cannot fail is not a gate — the nDCG baseline that sat vacuously at
0.0 for months is the cautionary example. These tests drive the audit with a
fake database and assert each check flips to FAIL when its gap is present.

The script itself is strictly read-only; nothing here touches a real database.
"""

import importlib.util
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "ops" / "audit_supabase_readiness.py"
_spec = importlib.util.spec_from_file_location("audit_supabase_readiness", _SCRIPT)
audit_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(audit_mod)


class FakeDB:
    """Answers the audit's queries from a declarative description of a schema."""

    def __init__(self, tables, granted, ungranted, rls, actor_def):
        self.tables, self.granted = tables, granted
        self.ungranted, self.rls, self.actor_def = ungranted, rls, actor_def

    def rows(self, sql: str):
        # Order matters: the sweep's predicate contains the grant check's, negated.
        if "not has_table_privilege" in sql:
            return [[t] for t in self.ungranted]
        if "has_table_privilege" in sql:
            return [[t] for t in self.granted]
        if "information_schema.tables" in sql:
            return [[t] for t in self.tables]
        if "pg_class" in sql:
            return [[t, "t" if on else "f"] for t, on in self.rls.items()]
        if "pg_constraint" in sql:
            return [[self.actor_def]] if self.actor_def else []
        raise AssertionError(f"unexpected query: {sql[:80]}")

    def close(self):
        pass


HEALTHY_ACTORS = "CHECK ((actor = ANY (ARRAY['user','system','admin','resolver','consolidator'])))"


def _run(monkeypatch, db):
    monkeypatch.setattr(audit_mod, "_connect", lambda: db)
    return audit_mod.audit()


def _healthy():
    tables = list(audit_mod.REQUIRED_READABLE)
    return FakeDB(
        tables=tables,
        granted=tables,
        ungranted=[],
        rls={t: True for t in audit_mod.REQUIRED_RLS},
        actor_def=HEALTHY_ACTORS,
    )


def test_healthy_schema_is_ready(monkeypatch):
    report = _run(monkeypatch, _healthy())
    assert report["ready"] is True, [f for f in report["findings"] if f["status"] == "FAIL"]


def test_missing_audit_table_fails(monkeypatch):
    db = _healthy()
    db.tables = [t for t in db.tables if t != "canonical_memory_events"]
    report = _run(monkeypatch, db)
    assert report["ready"] is False
    assert any(f["check"] == "table:canonical_memory_events" for f in report["findings"]
               if f["status"] == "FAIL")


def test_missing_service_role_grant_fails(monkeypatch):
    """The 27-table gap: grants are checked before RLS, so this is invisible."""
    db = _healthy()
    db.granted = [t for t in db.granted if t != "user_roles"]
    report = _run(monkeypatch, db)
    assert report["ready"] is False
    assert any(f["check"] == "grant:user_roles" for f in report["findings"]
               if f["status"] == "FAIL")


def test_schema_wide_ungranted_sweep_fails(monkeypatch):
    db = _healthy()
    db.ungranted = ["some_other_table", "and_another"]
    report = _run(monkeypatch, db)
    assert report["ready"] is False
    detail = next(f["detail"] for f in report["findings"] if f["check"] == "grant:all_public_tables")
    assert "some_other_table" in detail


def test_rls_disabled_fails(monkeypatch):
    db = _healthy()
    db.rls["canonical_memories"] = False
    report = _run(monkeypatch, db)
    assert report["ready"] is False


def test_narrow_actor_constraint_fails(monkeypatch):
    """The exact defect: resolver/consolidator rejected, audit silently lost."""
    db = _healthy()
    db.actor_def = "CHECK ((actor = ANY (ARRAY['user','system','admin'])))"
    report = _run(monkeypatch, db)
    assert report["ready"] is False
    detail = next(f["detail"] for f in report["findings"] if f["check"] == "constraint:actor_check")
    assert "resolver" in detail and "consolidator" in detail


def test_absent_actor_constraint_fails(monkeypatch):
    db = _healthy()
    db.actor_def = None
    report = _run(monkeypatch, db)
    assert report["ready"] is False


def test_sql_literal_list_escapes_quotes():
    assert audit_mod._sql_literal_list(["a'b"]) == "ARRAY['a''b']"


def test_grants_are_not_read_from_role_table_grants():
    """Regression: information_schema.role_table_grants reports a healthy prod as broken.

    That view only exposes grants where the CONNECTING role is the grantor, the
    grantee, or a member of the grantee. Supabase's SQL Editor connects as
    supabase_read_only_user, which is none of those for service_role, so the view
    returns nothing and the audit invents 78 unreadable tables against a database
    where service_role can in fact read all 78. Verified against production on
    2026-09-14. has_table_privilege asks the catalog and does not care who is
    connected, so it is the only correct source here.
    """
    for script in ("audit_supabase_readiness.py", "audit_supabase_readiness.sql"):
        body = (_SCRIPT.parent / script).read_text()
        code = "\n".join(
            line for line in body.splitlines() if not line.lstrip().startswith(("--", "#"))
        )
        assert "role_table_grants" not in code, (
            f"{script} reads role_table_grants; it is filtered to the connecting "
            "role and produces false FAILs. Use has_table_privilege."
        )
        assert "has_table_privilege" in code, f"{script} lost its privilege check"
