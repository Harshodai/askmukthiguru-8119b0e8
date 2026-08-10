"""P1-DB-5 — telemetry retention for 8 tables + runbook coverage."""

import sys
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from scripts.ops.cleanup_inactive_user_data import TELEMETRY_RETENTION_DAYS, TELEMETRY_TABLES


def _import_cleanup_mod(patched_supabase):
    """Reimport the ops module so create_client resolves to the patch."""
    with patch("supabase.create_client", return_value=patched_supabase):
        for key in list(sys.modules):
            if key.startswith("scripts.ops"):
                del sys.modules[key]
        from scripts.ops import cleanup_inactive_user_data as cleanup_mod
        return cleanup_mod


@pytest.fixture(autouse=True)
def _mock_settings_env(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "http://localhost:54321")
    monkeypatch.setenv("SUPABASE_KEY", "test-key")


def _make_supabase(table_rows):
    """table_rows: dict table_name -> list of (id, created_at_iso, should_delete)."""
    supabase = MagicMock()

    def table_side(table_name):
        table_mock = MagicMock()
        rows = table_rows.get(table_name, [])

        def select_side(*args, **kwargs):
            select_mock = MagicMock()
            cutoff = (datetime.utcnow() - timedelta(days=TELEMETRY_RETENTION_DAYS)).isoformat()
            stale = [r for r in rows if r[1] < cutoff]
            execute = SimpleNamespace(count=len(stale), data=stale)
            select_mock.lt.return_value.execute.return_value = execute
            return select_mock

        def delete_side(*args, **kwargs):
            delete_mock = MagicMock()
            cutoff = (datetime.utcnow() - timedelta(days=TELEMETRY_RETENTION_DAYS)).isoformat()
            stale = [r for r in rows if r[1] < cutoff]
            execute = SimpleNamespace(count=len(stale), data=stale)
            delete_mock.lt.return_value.execute.return_value = execute
            return delete_mock

        table_mock.select.side_effect = select_side
        table_mock.delete.side_effect = delete_side
        return table_mock

    supabase.table.side_effect = table_side
    return supabase


def test_telemetry_retention_days_constant():
    """Retention constant is the documented 90 days."""
    assert TELEMETRY_RETENTION_DAYS == 90


def test_telemetry_tables_include_all_eight():
    """All eight telemetry tables are listed."""
    assert set(TELEMETRY_TABLES) == {
        "chat_queries",
        "chat_responses",
        "retrieval_events",
        "trace_spans",
        "trigger_events",
        "safety_events",
        "app_logs",
        "token_usage",
        "router_decisions",
    }


def test_stale_telemetry_purged(_mock_settings_env):
    """Rows older than retention are counted in dry-run."""
    stale_ts = (datetime.utcnow() - timedelta(days=TELEMETRY_RETENTION_DAYS + 1)).isoformat()
    recent_ts = (datetime.utcnow() - timedelta(days=1)).isoformat()

    table_rows = {
        "chat_queries": [("a", stale_ts, True), ("b", recent_ts, False)],
        "chat_responses": [("c", stale_ts, True)],
        "retrieval_events": [("d", stale_ts, True)],
        "trace_spans": [("e", stale_ts, True)],
        "trigger_events": [("f", stale_ts, True)],
        "safety_events": [("g", stale_ts, True)],
        "app_logs": [("h", stale_ts, True)],
        "token_usage": [("i", stale_ts, True)],
        "router_decisions": [("j", stale_ts, True)],
    }

    supabase = _make_supabase(table_rows)
    cleanup_mod = _import_cleanup_mod(supabase)

    purged = cleanup_mod.cleanup_telemetry_logs(dry_run=True)

    assert purged == 9


def test_recent_telemetry_kept(_mock_settings_env):
    """Rows inside the retention window are not counted."""
    recent_ts = (datetime.utcnow() - timedelta(days=1)).isoformat()
    table_rows = {table: [("x", recent_ts, False)] for table in TELEMETRY_TABLES}

    supabase = _make_supabase(table_rows)
    cleanup_mod = _import_cleanup_mod(supabase)

    purged = cleanup_mod.cleanup_telemetry_logs(dry_run=True)

    assert purged == 0
