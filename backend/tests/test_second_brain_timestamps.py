from __future__ import annotations

from datetime import datetime, timezone

from services.second_brain.second_brain_service import _epoch_seconds


def test_epoch_seconds_accepts_postgres_timestamptz() -> None:
    actual = _epoch_seconds("2026-08-21T10:01:46.242Z")
    expected = datetime(2026, 8, 21, 10, 1, 46, 242000, tzinfo=timezone.utc).timestamp()
    assert abs(actual - expected) < 0.001


def test_epoch_seconds_preserves_legacy_numeric_value() -> None:
    assert _epoch_seconds(1787306506.0234158) == 1787306506.0234158
    assert _epoch_seconds("1787306506.0234158") == 1787306506.0234158


def test_epoch_seconds_fails_safe_for_invalid_database_value() -> None:
    assert _epoch_seconds("not-a-timestamp") == 0.0
    assert _epoch_seconds(None) == 0.0
