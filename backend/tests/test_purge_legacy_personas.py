"""Unit tests for purge_legacy_personas ops tool (Task 3c / MEM-004)."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.ops.purge_legacy_personas import (
    is_compiled_preference_format,
    run_purge,
    run_restore,
    select_target_records,
)

COMPILED_TEXT = """## Stated topics and interests
- meditation
- spiritual inquiry

## Explicit preferences
- short teachings

## Practices undertaken
- morning dhyana"""

LEGACY_LLM_TEXT = """### User Persona Overview
The seeker is in an intermediate state of inquiry. They enjoy meditation and seek deeper liberation.
Psychological profile: receptive to contemplation."""


def test_is_compiled_preference_format():
    assert is_compiled_preference_format(COMPILED_TEXT) is True
    assert is_compiled_preference_format(LEGACY_LLM_TEXT) is False
    assert is_compiled_preference_format("") is False


def test_select_target_records_selection_boundaries():
    records = [
        # Pre-cutoff legacy LLM record (target)
        {
            "id": "11111111-1111-1111-1111-111111111111",
            "user_id": "u1",
            "updated_at": "2026-11-05T12:00:00+00:00",
            "plaintext": LEGACY_LLM_TEXT,
        },
        # Pre-cutoff compiled record (protected)
        {
            "id": "22222222-2222-2222-2222-222222222222",
            "user_id": "u2",
            "updated_at": "2026-11-05T12:00:00+00:00",
            "plaintext": COMPILED_TEXT,
        },
        # Post-cutoff record (protected)
        {
            "id": "33333333-3333-3333-3333-333333333333",
            "user_id": "u3",
            "updated_at": "2026-11-07T00:00:00+00:00",
            "plaintext": COMPILED_TEXT,
        },
    ]

    targets = select_target_records(records)
    target_ids = [t["id"] for t in targets]

    assert target_ids == ["11111111-1111-1111-1111-111111111111"]


def test_run_purge_dry_run_default():
    records = [
        {
            "id": "11111111-1111-1111-1111-111111111111",
            "user_id": "u1",
            "updated_at": "2026-11-05T12:00:00+00:00",
            "plaintext": LEGACY_LLM_TEXT,
        }
    ]
    report = run_purge(records, apply=False)
    assert report["apply"] is False
    assert report["target_count"] == 1
    assert report["deleted_count"] == 0
    assert report["backup_created"] is False


def test_run_purge_refuses_apply_without_backup():
    records = [
        {
            "id": "11111111-1111-1111-1111-111111111111",
            "user_id": "u1",
            "updated_at": "2026-11-05T12:00:00+00:00",
            "plaintext": LEGACY_LLM_TEXT,
        }
    ]
    with pytest.raises(ValueError, match="--backup path is strictly required"):
        run_purge(records, apply=True, backup_path=None)


def test_run_purge_refuses_remote_without_allow_remote():
    records = [
        {
            "id": "11111111-1111-1111-1111-111111111111",
            "user_id": "u1",
            "updated_at": "2026-11-05T12:00:00+00:00",
            "plaintext": LEGACY_LLM_TEXT,
        }
    ]
    with pytest.raises(PermissionError, match="Remote/production mutation refused"):
        run_purge(
            records, apply=True, backup_path="/tmp/b.json", is_remote=True, allow_remote=False
        )


def test_run_purge_apply_and_restore(tmp_path):
    backup_file = str(tmp_path / "backup_personas.json")
    records = [
        {
            "id": "11111111-1111-1111-1111-111111111111",
            "user_id": "u1",
            "updated_at": "2026-11-05T12:00:00+00:00",
            "plaintext": LEGACY_LLM_TEXT,
        }
    ]
    report = run_purge(records, apply=True, backup_path=backup_file)
    assert report["apply"] is True
    assert report["deleted_count"] == 1
    assert report["backup_created"] is True
    assert Path(backup_file).is_file()

    restore_info = run_restore(backup_file)
    assert restore_info["status"] == "valid_backup"
    assert restore_info["record_count"] == 1
    assert restore_info["record_ids"] == ["11111111-1111-1111-1111-111111111111"]
