"""P1-DB-6 — anonymous guru_session_summaries orphan purge."""

import sys
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from scripts.ops.cleanup_inactive_user_data import cleanup_anonymous_session_summaries


def _import_cleanup_mod(patched_supabase):
    """Reimport the ops module so create_client resolves to the patch."""
    with patch("supabase.create_client", return_value=patched_supabase):
        # Evict this module and its parent namespace package so the reimport
        # gets a fresh module whose ``from supabase import create_client``
        # resolves to the patched function. Do NOT blanket-evict all
        # scripts.ops.* — that corrupts other tests (e.g. hallucination_anomaly)
        # which hold references to modules imported at collection time, causing
        # mock.patch to target a fresh re-imported instance while the test's
        # captured function still references the deleted original.
        sys.modules.pop("scripts.ops.cleanup_inactive_user_data", None)
        sys.modules.pop("scripts.ops", None)
        from scripts.ops import cleanup_inactive_user_data as cleanup_mod
        return cleanup_mod


@pytest.fixture(autouse=True)
def _mock_settings_env(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "http://localhost:54321")
    monkeypatch.setenv("SUPABASE_KEY", "test-key")


def _make_supabase(rows):
    """rows: list of (id, user_id, created_at_iso)."""
    supabase = MagicMock()

    def table_side(table_name):
        assert table_name == "guru_session_summaries"
        table_mock = MagicMock()

        def select_side(*args, **kwargs):
            assert args[0] == "id"
            select_mock = MagicMock()

            def is_side(*args, **kwargs):
                assert args[0] == "user_id"
                assert args[1] == "null"
                is_mock = MagicMock()

                def lt_side(*args, **kwargs):
                    cutoff = (datetime.utcnow() - timedelta(days=30)).isoformat()
                    stale = [
                        r for r in rows
                        if r[1] is None and r[2] < cutoff
                    ]
                    lt_mock = MagicMock()
                    lt_mock.execute.return_value = SimpleNamespace(
                        count=len(stale), data=stale
                    )
                    return lt_mock

                is_mock.lt.side_effect = lt_side
                return is_mock

            select_mock.is_.side_effect = is_side
            return select_mock

        table_mock.select.side_effect = select_side
        table_mock.delete.side_effect = select_side
        return table_mock

    supabase.table.side_effect = table_side
    return supabase


def test_anonymous_orphans_purged():
    """NULL-user_id summaries older than 30d are counted in dry-run."""
    stale_ts = (datetime.utcnow() - timedelta(days=31)).isoformat()
    recent_ts = (datetime.utcnow() - timedelta(days=2)).isoformat()
    rows = [
        ("a", None, stale_ts),
        ("b", None, recent_ts),
        ("c", "user-1", stale_ts),
    ]

    cleanup_mod = _import_cleanup_mod(_make_supabase(rows))
    purged = cleanup_mod.cleanup_anonymous_session_summaries(dry_run=True)

    # Only the NULL-user_id stale row counts; owned rows untouched.
    assert purged == 1


def test_recent_anonymous_kept():
    """NULL-user_id summaries inside the window are not counted."""
    recent_ts = (datetime.utcnow() - timedelta(days=2)).isoformat()
    rows = [("b", None, recent_ts)]

    cleanup_mod = _import_cleanup_mod(_make_supabase(rows))
    purged = cleanup_mod.cleanup_anonymous_session_summaries(dry_run=True)

    assert purged == 0