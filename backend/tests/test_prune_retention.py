"""Tests for scripts/ops/prune_retention.py — auto-purge expired conversations.

TDD-first. Verifies retention_days filtering, dry-run semantics, single-user scope,
and the forever retention (retention_days=0) skip. Uses the client-side fallback
path by forcing db.rpc to raise — this keeps tests deterministic without a live DB.
"""

from __future__ import annotations

import asyncio
import importlib.util
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock

# Load scripts/ops/prune_retention.py directly as a module — no __init__.py chain.
_REPO_ROOT = Path(__file__).resolve().parents[2]
_PRUNE_PATH = _REPO_ROOT / "scripts" / "ops" / "prune_retention.py"
_spec = importlib.util.spec_from_file_location("prune_retention_mod", _PRUNE_PATH)
_prune_mod = importlib.util.module_from_spec(_spec)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
# Pre-empt the lazy import in the script: stub the supabase client create import.
sys.modules.setdefault("prune_retention_mod", _prune_mod)
_spec.loader.exec_module(_prune_mod)
prune_retention = _prune_mod.prune_retention


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _make_row(row_id: str, retention_days: int, days_old: int) -> dict:
    created = datetime.now(UTC) - timedelta(days=days_old)
    return {
        "id": row_id,
        "user_id": "u-1",
        "retention_days": retention_days,
        "created_at": created.isoformat(),
    }


def _build_db_with_rows(rows: list[dict]) -> MagicMock:
    """Build a Supabase-client mock whose client-side fallback returns the provided rows."""
    db = MagicMock()
    db.rpc = MagicMock(side_effect=RuntimeError("no rpc — force client-side fallback"))

    # select("id, user_id, ...").execute() -> rows
    select_q = MagicMock()
    select_q.execute = MagicMock(return_value=MagicMock(data=rows))
    if rows and rows[0].get("user_id"):
        # Allow .eq("user_id", <uuid>) to chain.
        select_q.eq = MagicMock(return_value=select_q)

    table_q = MagicMock()
    table_q.select = MagicMock(return_value=select_q)
    table_q.delete = MagicMock(return_value=MagicMock(eq=MagicMock(return_value=MagicMock(execute=MagicMock(return_value=MagicMock(data=[{"id": "DELETED"}]))))))
    db.table = MagicMock(return_value=table_q)
    return db


def test_dry_run_does_not_delete():
    rows = [
        _make_row("c1", retention_days=30, days_old=100),  # expired
        _make_row("c2", retention_days=90, days_old=10),  # within retention
        _make_row("c3", retention_days=0, days_old=999),  # forever
    ]
    db = _build_db_with_rows(rows)
    counts = _run(prune_retention(db, user_id=None, dry_run=True))
    assert counts["purged_conversations"] == 1, counts
    # Dry-run path must NOT execute any delete.
    db.table.return_value.delete.assert_not_called()


def test_retention_days_zero_is_forever():
    rows = [_make_row("c3", retention_days=0, days_old=999)]
    db = _build_db_with_rows(rows)
    counts = _run(prune_retention(db, user_id=None, dry_run=False))
    assert counts["purged_conversations"] == 0


def test_expired_is_purged():
    rows = [_make_row("c1", retention_days=30, days_old=100)]
    db = _build_db_with_rows(rows)
    counts = _run(prune_retention(db, user_id=None, dry_run=False))
    assert counts["purged_conversations"] == 1, counts


def test_user_id_scope_passes_through():
    rows = []
    db = _build_db_with_rows(rows)
    # Spy on the select_q.eq sequence specifically for user_id.
    select_q = db.table.return_value.select.return_value
    _run(prune_retention(db, user_id="user-XYZ", dry_run=True))
    select_q.eq.assert_any_call("user_id", "user-XYZ")


if __name__ == "__main__":
    import pytest

    sys.exit(pytest.main([__file__, "-v"]))
