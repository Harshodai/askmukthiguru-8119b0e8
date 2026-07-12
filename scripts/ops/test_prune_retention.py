"""Tests for prune_retention.py — auto-purge expired conversations by retention_days.

TDD-first: written before the script wired the RPC path. Verifies retention_days
filtering, dry-run semantics, single-user scope, and the forever retention (0) skip.
"""

from __future__ import annotations

import asyncio
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

# Make `backend` importable when run from the repo root.
_REPO = Path(__file__).resolve().parents[2]
_BACKEND = _REPO / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _make_row(row_id: str, retention_days: int, days_old: int) -> dict:
    created = datetime.now(timezone.utc) - timedelta(days=days_old)
    return {
        "id": row_id,
        "user_id": "u-1",
        "retention_days": retention_days,
        "created_at": created.isoformat(),
    }


def test_dry_run_does_not_delete(monkeypatch):
    """Dry-run flag must compute deletions but execute no DELETE."""
    from scripts.ops.prune_retention import prune_retention

    db = MagicMock()
    # Force the RPC path to fail so the client-side fallback runs (deterministic, no DB required).
    db.rpc = MagicMock(side_effect=RuntimeError("no rpc"))
    q = MagicMock()
    select_q = MagicMock()
    q.select.return_value = select_q
    select_q.execute = MagicMock(
        return_value=MagicMock(
            data=[
                _make_row("c1", retention_days=30, days_old=100),  # expired
                _make_row("c2", retention_days=90, days_old=10),  # within retention
                _make_row("c3", retention_days=0, days_old=999),  # forever
            ]
        )
    )
    db.table = MagicMock(return_value=q)

    delete_q = MagicMock()
    delete_q.eq = MagicMock(return_value=delete_q)
    delete_q.execute = MagicMock(return_value=MagicMock(data=[{"id": "c1"}]))
    db.table.return_value.delete = MagicMock(return_value=delete_q)

    counts = _run(prune_retention(db, user_id=None, dry_run=True))
    assert counts["purged_conversations"] == 1, counts
    # In dry-run, no delete should fire on the table.
    db.table.return_value.delete.assert_not_called()


def test_retention_days_zero_is_forever(monkeypatch):
    """retention_days=0 means forever — never deleted."""
    from scripts.ops.prune_retention import prune_retention

    db = MagicMock()
    db.rpc = MagicMock(side_effect=RuntimeError("no rpc"))
    q = MagicMock()
    select_q = MagicMock()
    q.select.return_value = select_q
    select_q.execute = MagicMock(
        return_value=MagicMock(
            data=[
                _make_row("c3", retention_days=0, days_old=999),
            ]
        )
    )
    db.table = MagicMock(return_value=q)

    delete_q = MagicMock()
    delete_q.eq = MagicMock(return_value=delete_q)
    delete_q.execute = MagicMock(return_value=MagicMock(data=[{"id": "c3"}]))
    db.table.return_value.delete = MagicMock(return_value=delete_q)

    counts = _run(prune_retention(db, user_id=None, dry_run=False))
    assert counts["purged_conversations"] == 0
    db.table.return_value.delete.assert_not_called()


def test_expired_is_purged(monkeypatch):
    from scripts.ops.prune_retention import prune_retention

    db = MagicMock()
    db.rpc = MagicMock(side_effect=RuntimeError("no rpc"))
    q = MagicMock()
    select_q = MagicMock()
    q.select.return_value = select_q
    select_q.execute = MagicMock(
        return_value=MagicMock(data=[_make_row("c1", retention_days=30, days_old=100)])
    )
    db.table = MagicMock(return_value=q)

    delete_q = MagicMock()
    delete_q.eq = MagicMock(return_value=delete_q)
    delete_q.execute = MagicMock(return_value=MagicMock(data=[{"id": "c1"}]))
    db.table.return_value.delete = MagicMock(return_value=delete_q)

    counts = _run(prune_retention(db, user_id=None, dry_run=False))
    assert counts["purged_conversations"] == 1, counts
    delete_q.eq.assert_called_with("id", "c1")
    delete_q.execute.assert_called_once()


def test_user_id_scope_passes_through(monkeypatch):
    """user_id scope passed into the select query for the client-side fallback."""
    from scripts.ops.prune_retention import prune_retention

    db = MagicMock()
    db.rpc = MagicMock(side_effect=RuntimeError("no rpc"))
    q = MagicMock()
    select_q = MagicMock()
    q.select.return_value = select_q
    select_q.eq = MagicMock(return_value=select_q)
    select_q.execute = MagicMock(return_value=MagicMock(data=[]))
    db.table = MagicMock(return_value=q)

    _run(prune_retention(db, user_id="user-XYZ", dry_run=True))
    # The select_q chain must include user_id="user-XYZ".
    select_q.eq.assert_any_call("user_id", "user-XYZ")


if __name__ == "__main__":
    import sys, pytest
    sys.exit(pytest.main([__file__, "-v"]))
