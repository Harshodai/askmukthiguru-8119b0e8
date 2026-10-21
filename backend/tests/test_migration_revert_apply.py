"""Contract tests for migration rollback documentation and safe CI behavior.

Rollback blocks are reviewed instructions, not an automatic down-migration
mechanism. The local-Supabase pre-launch gate is responsible for validating
the ordered forward migration chain against a schema-complete disposable DB.
"""

from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_WORKFLOW = _ROOT / ".github" / "workflows" / "migration-revert-check.yml"
_RUNBOOK = _ROOT / "docs" / "runbooks" / "MIGRATION_ROLLBACK.md"
_PRELAUNCH = _ROOT / ".github" / "workflows" / "prelaunch-gate.yml"


def _src() -> str:
    return _WORKFLOW.read_text(encoding="utf-8")


def test_revert_check_has_repository_rollback_contract():
    src = _src()
    assert "REVERT:" in src
    assert "MIGRATION_ROLLBACK.md" in src
    assert _RUNBOOK.exists()
    assert "never run automatically" in _RUNBOOK.read_text(encoding="utf-8")


def test_manual_rollback_blocks_are_never_executed_as_sql():
    src = _src()
    assert "psql -f /tmp/revert.sql" not in src
    assert "awk '/-- REVERT:/{flag=1" not in src


def test_forward_migrations_use_schema_complete_local_supabase_gate():
    src = _src()
    prelaunch = _PRELAUNCH.read_text(encoding="utf-8")
    assert "prelaunch-gate.yml" in src
    assert "supabase start" in prelaunch
    assert "local stack" in prelaunch.lower() or "local supabase" in prelaunch.lower()


def test_revert_check_fails_closed_and_checks_each_changed_file():
    src = _src()
    assert "set -euo pipefail" in src
    assert 'grep -q -- "-- REVERT:"' in src
    assert "continue-on-error" not in src
