"""Unit tests for backend/scripts/verify_rls_policies.py."""

import json
import sys
from io import StringIO
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from scripts.verify_rls_policies import (
    PROBED_TABLES,
    _is_local_supabase,
    _is_permission_or_rls_error,
    _make_test_email,
    delete_rows,
    list_rls_tables,
    main,
    run_verification,
)


def _build_mock_supabase_client(leak_table: str | None = None) -> MagicMock:
    """Build a mock Supabase client where insertions succeed and Bob probes return empty (or leaked data)."""
    mock_client = MagicMock()
    mock_table = MagicMock()
    mock_client.table.return_value = mock_table

    mock_table.select.return_value = mock_table
    mock_table.update.return_value = mock_table
    mock_table.delete.return_value = mock_table
    mock_table.eq.return_value = mock_table
    mock_table.in_.return_value = mock_table

    # Default execute for Bob's query operations returns empty list (denied/RLS filtered)
    mock_table.execute.return_value = MagicMock(data=[])

    # Insert operations return seeded row IDs
    mock_insert_builder = MagicMock()
    mock_insert_builder.execute.return_value = MagicMock(
        data=[{"id": "test-id-1", "user_id": "alice-id", "assistant_id": "ast-id-1"}]
    )
    mock_table.insert.return_value = mock_insert_builder

    if leak_table:
        def table_side_effect(name: str) -> MagicMock:
            t = MagicMock()
            t.select.return_value = t
            t.update.return_value = t
            t.delete.return_value = t
            t.eq.return_value = t
            t.in_.return_value = t
            t.insert.return_value = mock_insert_builder
            if name == leak_table:
                # Return leaked data on query execute
                t.execute.return_value = MagicMock(data=[{"id": "leaked-id", "title": "Leaked"}])
            else:
                t.execute.return_value = MagicMock(data=[])
            return t

        mock_client.table.side_effect = table_side_effect

    return mock_client


def test_list_tables_cli_flag_output() -> None:
    """Test --list-tables CLI flag enumerates all RLS-bearing tables and exits 0."""
    stdout_buf = StringIO()
    with patch("sys.stdout", stdout_buf):
        exit_code = main(["--list-tables"])

    assert exit_code == 0
    raw_output = stdout_buf.getvalue()
    data = json.loads(raw_output)

    assert data.get("ok") is True
    assert isinstance(data.get("tables"), list)
    assert data.get("count") == len(data["tables"])

    # Must cover all 11 target probe tables
    for table in PROBED_TABLES:
        assert table in data["tables"], f"Expected {table} in RLS tables list"


def test_list_rls_tables_discovery_and_fallback(tmp_path: Path) -> None:
    """Test dynamic regex extraction from migration files plus fallback."""
    custom_mig_dir = tmp_path / "migrations"
    custom_mig_dir.mkdir()
    (custom_mig_dir / "20260101_sample.sql").write_text(
        """
        CREATE TABLE public.custom_secure_table (id uuid primary key);
        ALTER TABLE public.custom_secure_table ENABLE ROW LEVEL SECURITY;
        ALTER TABLE ONLY private_table ENABLE ROW LEVEL SECURITY;
        """,
        encoding="utf-8",
    )

    tables = list_rls_tables(custom_mig_dir)
    assert "custom_secure_table" in tables
    assert "private_table" in tables
    for table in PROBED_TABLES:
        assert table in tables


def test_is_local_supabase_helper() -> None:
    """Test local URL detection logic."""
    assert _is_local_supabase("http://localhost:54321") is True
    assert _is_local_supabase("http://127.0.0.1:54321") is True
    assert _is_local_supabase("http://[::1]:54321") is True
    assert _is_local_supabase("https://project.supabase.co") is False
    assert _is_local_supabase("https://api.askmukthiguru.com") is False


def test_make_test_email() -> None:
    """Test test email generation helper."""
    email1 = _make_test_email("alice")
    email2 = _make_test_email("alice")
    assert email1.startswith("alice-")
    assert email1.endswith("@gmail.com")
    assert email1 != email2


def test_is_permission_or_rls_error() -> None:
    """Test classification of expected security rejections vs unexpected errors."""
    assert _is_permission_or_rls_error(Exception("42501 permission denied for table")) is True
    assert _is_permission_or_rls_error(Exception("new row violates row-level security policy")) is True
    assert _is_permission_or_rls_error(Exception("PGRST301 JWT expired")) is True
    assert _is_permission_or_rls_error(Exception("HTTP 401 Unauthorized")) is True
    assert _is_permission_or_rls_error(Exception("HTTP 403 Forbidden")) is True
    assert _is_permission_or_rls_error(Exception("HTTP 500 Internal Server Error")) is False
    assert _is_permission_or_rls_error(Exception("Connection refused")) is False


def test_delete_rows_primary_key_selection() -> None:
    """Test delete_rows selects correct primary key per table type."""
    mock_client = MagicMock()
    mock_table = MagicMock()
    mock_delete = MagicMock()
    mock_in = MagicMock()

    mock_client.table.return_value = mock_table
    mock_table.delete.return_value = mock_delete
    mock_delete.in_.return_value = mock_in
    mock_in.execute.return_value = MagicMock()

    with patch("scripts.verify_rls_policies.create_client", return_value=mock_client):
        # user_profiles uses user_id
        delete_rows("user_profiles", ["uid-1"])
        mock_delete.in_.assert_called_with("user_id", ["uid-1"])

        # user_streaks uses user_id
        delete_rows("user_streaks", ["uid-2"])
        mock_delete.in_.assert_called_with("user_id", ["uid-2"])

        # assistant_scope_metadata uses assistant_id
        delete_rows("assistant_scope_metadata", ["ast-1"])
        mock_delete.in_.assert_called_with("assistant_id", ["ast-1"])

        # conversations uses id
        delete_rows("conversations", ["conv-1"])
        mock_delete.in_.assert_called_with("id", ["conv-1"])


def test_run_verification_success_mocked() -> None:
    """Test run_verification executes all 11 tables (33 probe assertions) and cleans up."""
    mock_client = _build_mock_supabase_client()

    with (
        patch("scripts.verify_rls_policies.create_user", side_effect=["alice-id", "bob-id"]),
        patch("scripts.verify_rls_policies.sign_in", side_effect=["alice-tok", "bob-tok"]),
        patch("scripts.verify_rls_policies.client_for_token", return_value=mock_client),
        patch("scripts.verify_rls_policies.create_client", return_value=mock_client),
        patch("scripts.verify_rls_policies.delete_user") as mock_del_user,
        patch("scripts.verify_rls_policies.delete_rows") as mock_del_rows,
    ):
        report = run_verification()

    assert report["ok"] is True
    assert report["failures"] == 0
    assert report["cleanup_failures"] == 0
    assert report["tests"] == len(PROBED_TABLES) * 3
    assert report["tables"] == PROBED_TABLES

    # Guaranteed cleanup checks
    assert mock_del_user.call_count == 2
    assert mock_del_rows.call_count >= 1


def test_run_verification_leak_detection_mocked() -> None:
    """Test run_verification flags cross-user leak when Bob reads Alice's row."""
    mock_client = _build_mock_supabase_client(leak_table="study_notebooks")

    with (
        patch("scripts.verify_rls_policies.create_user", side_effect=["alice-id", "bob-id"]),
        patch("scripts.verify_rls_policies.sign_in", side_effect=["alice-tok", "bob-tok"]),
        patch("scripts.verify_rls_policies.client_for_token", return_value=mock_client),
        patch("scripts.verify_rls_policies.create_client", return_value=mock_client),
        patch("scripts.verify_rls_policies.delete_user") as mock_del_user,
        patch("scripts.verify_rls_policies.delete_rows") as mock_del_rows,
    ):
        report = run_verification()

    assert report["ok"] is False
    assert report["failures"] >= 1
    leaks = [f for f in report["details"] if f.get("table") == "study_notebooks"]
    assert len(leaks) >= 1

    # Cleanup must still run even on failure
    assert mock_del_user.call_count == 2
    assert mock_del_rows.call_count >= 1
