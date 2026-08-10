"""P1-DB-7 — user_brain_keys schema drift reconciliation.

The two user_brain_keys CREATE TABLE migrations (20260717191006_second_brain_
vault.sql and 20260718120001_second_brain_keys_table.sql) ship incompatible
column sets; whichever applies first wins and the other's columns are silently
lost. The reconciliation migration (20260804000005) unions both sets with
ADD COLUMN IF NOT EXISTS.

No live DB is available in CI, so the tests assert the migration text covers
every column the second-brain service reads/writes.
"""

from pathlib import Path

import pytest

MIGRATIONS_DIR = (
    Path(__file__).resolve().parents[2] / "supabase" / "migrations"
)
RECONCILE_MIGRATION = MIGRATIONS_DIR / "20260804000005_reconcile_user_brain_keys.sql"
VAULT_MIGRATION = MIGRATIONS_DIR / "20260717191006_second_brain_vault.sql"
KEYS_MIGRATION = MIGRATIONS_DIR / "20260718120001_second_brain_keys_table.sql"


@pytest.fixture(scope="module")
def reconcile_sql() -> str:
    assert RECONCILE_MIGRATION.exists(), f"missing {RECONCILE_MIGRATION}"
    return RECONCILE_MIGRATION.read_text()


def _union_column_set() -> set[str]:
    """Columns from BOTH source migrations — the full set the reconciliation
    must cover so neither migration's schema is silently lost."""
    columns: set[str] = set()
    for path in (VAULT_MIGRATION, KEYS_MIGRATION):
        assert path.exists(), f"missing {path}"
        for line in path.read_text().splitlines():
            stripped = line.strip().lower()
            if stripped.startswith(("user_id", "wrapped_dek", "wrap_mode", "kdf",
                                    "version", "kek", "dek_wrapped", "rotated_at",
                                    "created_at", "updated_at")):
                columns.add(stripped.split()[0])
    return columns


def test_union_source_columns(reconcile_sql):
    """Sanity: the two source migrations actually disagree (the bug)."""
    vault_cols = {line.strip().lower().split()[0]
                  for line in VAULT_MIGRATION.read_text().splitlines()
                  if line.strip().lower().startswith(("wrapped_dek", "wrap_mode", "kdf", "version"))}
    keys_cols = {line.strip().lower().split()[0]
                 for line in KEYS_MIGRATION.read_text().splitlines()
                 if line.strip().lower().startswith(("kek", "dek_wrapped", "updated_at"))}
    assert vault_cols.isdisjoint(keys_cols), "source migrations unexpectedly agree"
    assert "wrap_mode" in vault_cols and "kek" in keys_cols


def test_wrap_mode_present(reconcile_sql):
    """Mode A/B vault service needs wrap_mode (+ kdf, version) — the vault
    migration's column set must survive regardless of apply order."""
    lower = reconcile_sql.lower()
    for column in ("wrap_mode", "kdf", "version", "wrapped_dek"):
        assert f"add column if not exists {column}" in lower, (
            f"reconciliation migration missing {column}"
        )
    assert "user_brain_keys_wrap_mode_check" in reconcile_sql, (
        "wrap_mode CHECK constraint not re-added (drift guard)"
    )


def test_kek_present(reconcile_sql):
    """The keys migration's kek / dek_wrapped / updated_at column set must
    survive regardless of apply order. (The service itself uses wrapped_dek —
    covered in test_wrap_mode_present — but no column may be silently lost.)"""
    lower = reconcile_sql.lower()
    for column in ("kek", "dek_wrapped", "updated_at", "rotated_at", "created_at"):
        assert f"add column if not exists {column}" in lower, (
            f"reconciliation migration missing {column}"
        )


def test_reconciliation_covers_service_columns():
    """The service upserts wrapped_dek/wrap_mode/kdf/version (provision_vault,
    enable_session_unlock) and reads wrap_mode/kdf/wrapped_dek in unlock.
    Every column it touches must exist after the reconciliation migration."""
    service_file = (
        Path(__file__).resolve().parents[1]
        / "services" / "second_brain" / "second_brain_service.py"
    )
    service_src = service_file.read_text()
    required = {"wrapped_dek", "wrap_mode", "kdf", "version"}
    for column in required:
        assert f'"{column}"' in service_src or f"'{column}'" in service_src, (
            f"service no longer references {column}; schema expectations may be stale"
        )

    reconcile_sql = RECONCILE_MIGRATION.read_text().lower()
    for column in required:
        assert f"add column if not exists {column}" in reconcile_sql
