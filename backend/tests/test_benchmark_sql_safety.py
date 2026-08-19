"""Tests for SQL parameterization and injection safety in benchmark tools."""

from __future__ import annotations

import pytest

from benchmarks.verify_custom_assistants import build_telemetry_check_command


@pytest.fixture
def base_config():
    return {
        "db_container": "test_supabase_db",
    }


SQL_INJECTION_STRINGS = [
    "' OR '1'='1",
    "'; DROP TABLE public.chat_queries; --",
    "' UNION SELECT password_hash FROM auth.users --",
    "admin'--",
    "' OR 1=1 --",
    "test'; VACUUM FULL; --",
    "test'; SELECT pg_sleep(10); --",
    'test" OR ""="',
    "'; DELETE FROM public.chat_queries WHERE '1'='1",
]


@pytest.mark.parametrize("injection", SQL_INJECTION_STRINGS)
def test_build_telemetry_check_command_sql_injection_safety(base_config, injection):
    """Ensure SQL queries are strictly parameterized and injection strings never leak into SQL command."""
    cmd = build_telemetry_check_command(base_config, injection)

    # Command structure verification
    assert isinstance(cmd, list)
    assert "docker" in cmd
    assert "psql" in cmd
    assert "-c" in cmd
    assert "-v" in cmd

    # Find the index of -c and verify the exact SQL query
    c_idx = cmd.index("-c")
    sql_arg = cmd[c_idx + 1]

    # The SQL query must use the parameterized psql variable :'slug'
    assert (
        sql_arg
        == "SELECT assistant_slug FROM public.chat_queries WHERE assistant_slug = :'slug' LIMIT 1;"
    )

    # The malicious injection string must NOT be present anywhere in the -c SQL text
    assert injection not in sql_arg

    # Find the -v parameter and verify it binds the variable safely
    v_idx = cmd.index("-v")
    var_arg = cmd[v_idx + 1]
    assert var_arg == f"slug={injection}"


def test_build_telemetry_check_command_normal_slug(base_config):
    """Verify command generation for standard assistant slug."""
    slug = "test-assistant-12345"
    cmd = build_telemetry_check_command(base_config, slug)

    assert cmd == [
        "docker",
        "exec",
        "-i",
        "test_supabase_db",
        "psql",
        "-U",
        "postgres",
        "-d",
        "postgres",
        "-v",
        "slug=test-assistant-12345",
        "-c",
        "SELECT assistant_slug FROM public.chat_queries WHERE assistant_slug = :'slug' LIMIT 1;",
    ]
