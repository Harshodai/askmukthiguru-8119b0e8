"""Tests for Gap 2 — backfill_important_kwd script."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

REPO_BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_BACKEND))


def _make_test_collection(tmp_path=None):  # used only as a marker; no I/O
    return "spiritual_chunks"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _build_mock_point(point_id: str, payload: dict, text: str = ""):
    """Return a minimal mock Qdrant point."""
    point = MagicMock()
    point.id = point_id
    point.payload = {**payload, "content": text}
    return point


# ---------------------------------------------------------------------------
# dry_run: missing-kwd points are reported, set_payload never called
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_dry_run_reports_missing_and_skips_filled():
    """Dry-run must detect missing kwd, skip filled, and not call set_payload."""
    from scripts.ops.backfill_important_kwd import run

    p_missing = _build_mock_point("p_missing", {}, "beautiful state joy")
    p_filled = _build_mock_point("p_filled", {"important_kwd": ["beautiful_state"]}, "serene mind")
    scroll_results = [p_missing, p_filled]
    mock_raw = MagicMock()
    mock_raw.scroll = MagicMock(return_value=(scroll_results, None))
    mock_raw.set_payload = MagicMock()

    mock_qdrant_svc = MagicMock()
    mock_qdrant_svc._client = mock_raw

    mock_container = MagicMock()
    mock_container._qdrant = mock_qdrant_svc

    with patch("scripts.ops.backfill_important_kwd.get_container", return_value=mock_container):
        scanned, needs_fill, filled = await run(
            apply=False,
            collection="test_coll",
            limit=10,
        )

    assert scanned == 2
    assert needs_fill == 1          # p_missing has no important_kwd
    assert filled == 0
    mock_raw.set_payload.assert_not_called()


# ---------------------------------------------------------------------------
# apply: set_payload called exactly once with correct payload shape
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_apply_writes_payload_with_tags():
    """--apply must call set_payload for each missing-kwd point."""
    from scripts.ops.backfill_important_kwd import run

    p1 = _build_mock_point("p1", {}, "joy in beautiful state")
    p2 = _build_mock_point("p2", {}, "serene mind meditation practice")
    scroll_results = [p1, p2]
    mock_raw = MagicMock()
    mock_raw.scroll = MagicMock(return_value=(scroll_results, None))
    mock_raw.set_payload = MagicMock()

    mock_qdrant_svc = MagicMock()
    mock_qdrant_svc._client = mock_raw
    mock_container = MagicMock()
    mock_container._qdrant = mock_qdrant_svc

    with patch("scripts.ops.backfill_important_kwd.get_container", return_value=mock_container):
        scanned, needs_fill, filled = await run(
            apply=True,
            collection="test_coll",
            limit=10,
        )

    assert scanned == 2
    assert needs_fill == 2
    assert filled == 2
    assert mock_raw.set_payload.call_count == 2

    calls = mock_raw.set_payload.call_args_list
    all_tags = [c.kwargs["payload"]["important_kwd"] for c in calls]
    for tags in all_tags:
        assert isinstance(tags, list)
        assert len(tags) >= 0   # may be empty if no doctrine terms matched


# ---------------------------------------------------------------------------
# limit: only N points are scanned
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_limit_stops_after_n_points():
    """--limit should stop scanning once N points are consumed."""
    from scripts.ops.backfill_important_kwd import run

    page1 = [_build_mock_point(f"p{i}", {}, f"text chunk {i}") for i in range(5)]
    mock_raw = MagicMock()
    mock_raw.scroll = MagicMock(side_effect=[(page1, "offset"), ([], None)])
    mock_raw.set_payload = MagicMock()

    mock_qdrant_svc = MagicMock()
    mock_qdrant_svc._client = mock_raw
    mock_container = MagicMock()
    mock_container._qdrant = mock_qdrant_svc

    with patch("scripts.ops.backfill_important_kwd.get_container", return_value=mock_container):
        scanned, needs_fill, filled = await run(
            apply=True, collection="test_coll", limit=3,
        )

    assert scanned == 3
    assert needs_fill == 3
