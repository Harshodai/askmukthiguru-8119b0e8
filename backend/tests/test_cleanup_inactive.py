"""P1-DB-2 — cleanup_stale_qdrant_memories uses profiles.last_active_at AND stale points."""

import sys
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


def _import_cleanup_mod(patched_qdrant_client, patched_supabase):
    """Reimport the ops module so its top-level QdrantClient/create_client bindings resolve to patches."""
    with patch("qdrant_client.QdrantClient", return_value=patched_qdrant_client), \
         patch("supabase.create_client", return_value=patched_supabase):
        # Only evict this module and its parent namespace — blanket-evicting
        # all scripts.ops.* corrupts other tests that hold references to
        # modules imported at collection time (e.g. hallucination_anomaly).
        sys.modules.pop("scripts.ops.cleanup_inactive_user_data", None)
        sys.modules.pop("scripts.ops", None)
        from scripts.ops import cleanup_inactive_user_data as cleanup_mod
        return cleanup_mod


@pytest.fixture(autouse=True)
def _mock_settings_env(monkeypatch):
    monkeypatch.setenv("QDRANT_URL", "http://localhost:6333")
    monkeypatch.setenv("SUPABASE_URL", "http://localhost:54321")
    monkeypatch.setenv("SUPABASE_KEY", "test-key")


def _make_point(pid, user_id, updated_at_iso):
    return SimpleNamespace(id=pid, payload={"user_id": user_id, "updated_at": updated_at_iso})


def _make_supabase(inactive_user_ids):
    supabase = MagicMock()
    execute = SimpleNamespace(data=[{"id": uid} for uid in inactive_user_ids])
    supabase.table.return_value.select.return_value.lt.return_value.order.return_value.range.return_value.execute.return_value = execute
    return supabase


def _make_qdrant(points_by_collection, next_offset=None):
    client = MagicMock()
    client.get_collections.return_value.collections = [
        SimpleNamespace(name=name) for name in points_by_collection
    ]

    def scroll(collection_name, limit=None, offset=None, with_payload=None, with_vectors=None, scroll_filter=None):
        # Simulate Qdrant DatetimeRange filter behavior: updated_at must be < cutoff.
        if scroll_filter is not None:
            cutoff = (datetime.utcnow() - timedelta(days=365)).isoformat()
            points = [
                p for p in points_by_collection.get(collection_name, [])
                if p.payload.get("updated_at", cutoff) < cutoff
            ]
            return points, next_offset
        return points_by_collection.get(collection_name, []), next_offset

    client.scroll.side_effect = scroll
    return client


def test_active_user_not_purged(_mock_settings_env):
    """Memory points for an active user (last_active_at >= cutoff) are kept."""
    uid = "11111111-1111-1111-1111-111111111111"
    stale_ts = (datetime.utcnow() - timedelta(days=400)).isoformat()

    qdrant_client = _make_qdrant({"memory_ephemeral": [_make_point("p1", uid, stale_ts)]})
    supabase = _make_supabase([])  # no inactive users
    cleanup_mod = _import_cleanup_mod(qdrant_client, supabase)

    purged = cleanup_mod.cleanup_stale_qdrant_memories(days_inactivity=365, dry_run=True)

    assert purged == 0
    assert qdrant_client.delete.called is False


def test_inactive_user_with_stale_memory_purged(_mock_settings_env):
    """A stale memory point belonging to an inactive user is purged."""
    uid = "22222222-2222-2222-2222-222222222222"
    stale_ts = (datetime.utcnow() - timedelta(days=400)).isoformat()

    qdrant_client = _make_qdrant({"memory_ephemeral": [_make_point("p1", uid, stale_ts)]})
    supabase = _make_supabase([uid])
    cleanup_mod = _import_cleanup_mod(qdrant_client, supabase)

    purged = cleanup_mod.cleanup_stale_qdrant_memories(days_inactivity=365, dry_run=True)

    assert purged == 1
    assert qdrant_client.delete.called is False  # dry_run


def test_inactive_user_with_fresh_memory_kept(_mock_settings_env):
    """A memory point updated inside the retention window is kept even for inactive user."""
    uid = "33333333-3333-3333-3333-333333333333"
    fresh_ts = (datetime.utcnow() - timedelta(days=30)).isoformat()

    qdrant_client = _make_qdrant({"memory_ephemeral": [_make_point("p1", uid, fresh_ts)]})
    supabase = _make_supabase([uid])
    cleanup_mod = _import_cleanup_mod(qdrant_client, supabase)

    purged = cleanup_mod.cleanup_stale_qdrant_memories(days_inactivity=365, dry_run=True)

    assert purged == 0
    # The filter must be applied: the point's updated_at is inside the window.
    scroll_calls = [c for c in qdrant_client.scroll.call_args_list if c.kwargs.get("scroll_filter")]
    assert len(scroll_calls) == 1
