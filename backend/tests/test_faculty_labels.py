"""Faculty answer labels: export script behaviour + static proof of the
migration's owner-scoped RLS (no Postgres is available in this environment,
so isolation is asserted on the policy text, not by running SQL)."""

import csv
import io
import re
import sys
from pathlib import Path
from unittest.mock import MagicMock

backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from scripts.ops import export_faculty_labels as exp  # noqa: E402

MIGRATION = (
    backend_dir.parent / "supabase" / "migrations" / "20261007000000_faculty_answer_labels.sql"
)


def _client(pages):
    """Mock client whose .range().execute() yields successive pages."""
    q = MagicMock()
    for m in ("select", "order", "gte"):
        getattr(q, m).return_value = q
    q.range.return_value = q
    q.execute.side_effect = [MagicMock(data=p) for p in pages]
    client = MagicMock()
    client.table.return_value = q
    return client, q


def _row(**kw):
    base = {c: None for c in exp.COLUMNS}
    base.update(
        created_at="2026-10-07T00:00:00Z",
        user_id="u1",
        trace_id="t1",
        faithful="yes",
        safe=True,
        helpful=5,
        model="m",
        policy_id="p",
    )
    base.update(kw)
    return base


def test_export_writes_header_and_rows(tmp_path):
    client, _ = _client([[_row(note="good"), _row(trace_id="t2", safe=False, faithful="no")]])
    out = tmp_path / "l.csv"
    assert exp.main(["--out", str(out)], client=client) == 0
    rows = list(csv.DictReader(out.open(encoding="utf-8")))
    assert [r["trace_id"] for r in rows] == ["t1", "t2"]
    assert rows[0]["safe"] == "yes" and rows[1]["safe"] == "no"
    assert rows[0]["policy_id"] == "p" and rows[0]["helpful"] == "5"


def test_export_neutralises_formula_injection_in_notes():
    buf = io.StringIO()
    exp.write_csv([_row(note='=HYPERLINK("http://x")')], buf)
    cell = list(csv.DictReader(io.StringIO(buf.getvalue())))[0]["note"]
    assert cell.startswith("'=")


def test_export_pages_and_applies_since():
    full = [_row(trace_id=f"t{i}") for i in range(exp.PAGE)]
    client, q = _client([full, [_row(trace_id="last")]])
    rows = exp.fetch_labels(client, since="2026-10-01")
    assert len(rows) == exp.PAGE + 1
    q.gte.assert_called_with("created_at", "2026-10-01")


def test_query_failure_is_not_an_empty_export(capsys):
    client, q = _client([])
    q.execute.side_effect = RuntimeError("boom")
    assert exp.main(["--out", "-"], client=client) == 2
    assert "Query failed" in capsys.readouterr().err


def test_unavailable_client_exits_2(monkeypatch):
    import app.telemetry_db as tdb

    monkeypatch.setattr(tdb, "_get_client", lambda: None)
    assert exp.main(["--out", "-"]) == 2


# ---- migration static proofs -------------------------------------------------


def _sql():
    return MIGRATION.read_text(encoding="utf-8")


def test_migration_has_revert_block():
    assert "-- REVERT:" in _sql()
    assert "DROP TABLE IF EXISTS public.faculty_answer_labels" in _sql()


def test_rls_enabled_and_every_policy_is_owner_scoped_so_user_b_cannot_read_user_a():
    sql = _sql()
    assert "ENABLE ROW LEVEL SECURITY" in sql
    policies = re.findall(r"CREATE POLICY (\w+) ON public\.faculty_answer_labels(.*?);", sql, re.S)
    assert len(policies) == 4
    for name, body in policies:
        assert "TO authenticated" in body, name
        # No permissive clause that could expose another reviewer's row.
        assert "USING (true)" not in body.replace("  ", " ").lower().replace("true", "true"), name
        assert "auth.uid() = user_id" in body, name
    select = [b for n, b in policies if "select" in n][0]
    assert "FOR SELECT" in select and "USING (auth.uid() = user_id)" in select
    for name, body in policies:
        if "insert" in name:
            assert "WITH CHECK (auth.uid() = user_id)" in body
        if "update" in name:
            assert "WITH CHECK (auth.uid() = user_id)" in body


def test_no_anon_or_public_grant_and_service_role_is_granted():
    sql = _sql()
    grants = re.findall(r"GRANT .*? TO (\w+);", sql)
    assert "service_role" in grants and "authenticated" in grants
    assert not {"anon", "public", "PUBLIC"} & set(grants)


def test_label_value_constraints_match_the_ui_contract():
    sql = _sql()
    assert (
        "faithful IN ('yes', 'partly', 'no')" in sql.replace("  ", " ")
        or "IN ('yes', 'partly', 'no')" in sql
    )
    assert "helpful" in sql and "BETWEEN 1 AND 5" in sql
    assert "trace_id IS NOT NULL OR request_id IS NOT NULL" in sql
