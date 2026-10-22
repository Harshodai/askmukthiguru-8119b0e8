"""Static contract tests for consent SQL that cannot be proven by Python mocks alone.

These intentionally pin migration ordering, latest-event semantics, and the
shared lock between consent mutations and durable-memory writes. A stale SQL
policy can re-open memory writes even while the Python consent reader is correct.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MIGRATIONS = ROOT / "supabase" / "migrations"
HISTORY_NAME = "20261021000000_memory_consent_history_and_outbox_binding.sql"
GUARD_NAME = "20261021000100_require_active_memory_consent.sql"


def test_consent_migrations_have_distinct_ordered_versions():
    history_version = HISTORY_NAME.split("_", 1)[0]
    guard_version = GUARD_NAME.split("_", 1)[0]

    assert history_version != guard_version
    assert history_version < guard_version
    assert (MIGRATIONS / HISTORY_NAME).is_file()
    assert (MIGRATIONS / GUARD_NAME).is_file()


def test_rls_consent_function_checks_the_latest_receipt_not_any_historical_grant():
    sql = (MIGRATIONS / GUARD_NAME).read_text(encoding="utf-8")
    start = sql.index("CREATE OR REPLACE FUNCTION public.has_active_memory_consent")
    end = sql.index("REVOKE ALL ON FUNCTION public.has_active_memory_consent", start)
    function_sql = sql[start:end]

    assert "ORDER BY receipt.event_sequence DESC" in function_sql
    assert "LIMIT 1" in function_sql
    assert "COALESCE((" in function_sql
    assert "AND EXISTS (" not in function_sql


def test_receipt_events_and_memory_writes_share_a_transaction_lock():
    sql = (MIGRATIONS / GUARD_NAME).read_text(encoding="utf-8")
    assert "CREATE TRIGGER serialize_memory_consent_receipt_mutation" in sql
    assert "BEFORE INSERT OR UPDATE OR DELETE ON public.memory_consent_receipts" in sql
    assert "pg_advisory_xact_lock" in sql
    assert "pg_get_serial_sequence(" in sql
    guard_start = sql.index("CREATE OR REPLACE FUNCTION public.enforce_active_memory_consent_before_write")
    guard_end = sql.index("$memory_consent_write$;", guard_start) + len("$memory_consent_write$;")
    write_guard = sql[guard_start:guard_end]
    assert "ORDER BY receipt.event_sequence DESC" in write_guard
    assert "IF NOT COALESCE(v_active, FALSE)" in write_guard



def test_legacy_memory_rpcs_are_tenant_scoped_and_backend_only():
    sql = (MIGRATIONS / "20261021000200_tenant_scope_legacy_memory.sql").read_text(
        encoding="utf-8"
    )

    assert "p_tenant_id text" in sql
    assert "AND memory.tenant_id = p_tenant_id" in sql
    assert "AND tenant_id = p_tenant_id" in sql
    assert "SET search_path = ''" in sql
    assert "REVOKE ALL ON FUNCTION public.match_user_memories_by_user" in sql
    assert "REVOKE ALL ON FUNCTION public.regenerate_summaries(uuid, text)" in sql
    assert "REVOKE ALL ON FUNCTION public.create_compaction_snapshot(uuid, text, jsonb)" in sql
    assert "GRANT EXECUTE ON FUNCTION public.match_user_memories_by_user" in sql
    assert "GRANT EXECUTE ON FUNCTION public.regenerate_summaries(uuid, text) TO service_role" in sql
    assert "GRANT EXECUTE ON FUNCTION public.create_compaction_snapshot(uuid, text, jsonb)" in sql


def test_compaction_snapshot_is_consent_gated_and_tenant_local():
    sql = (MIGRATIONS / "20261021000200_tenant_scope_legacy_memory.sql").read_text(
        encoding="utf-8"
    )
    start = sql.index("CREATE FUNCTION public.create_compaction_snapshot")
    end = sql.index("$compaction_snapshot$;", start) + len("$compaction_snapshot$;")
    function_sql = sql[start:end]

    assert "p_tenant_id" in function_sql
    assert "pg_advisory_xact_lock" in function_sql
    assert "FROM public.memory_consent_receipts" in function_sql
    assert "ORDER BY receipt.event_sequence DESC" in function_sql
    assert "snapshot.tenant_id = p_tenant_id" in function_sql
    assert "LIMIT 3" in function_sql


def test_legacy_core_and_session_uniqueness_are_tenant_local():
    sql = (MIGRATIONS / "20261021000200_tenant_scope_legacy_memory.sql").read_text(
        encoding="utf-8"
    )

    assert "DROP CONSTRAINT IF EXISTS guru_core_memory_user_id_key" in sql
    assert "guru_core_memory_user_tenant_uidx" in sql
    assert "DROP CONSTRAINT IF EXISTS guru_session_summaries_user_session_unique" in sql
    assert "guru_session_summaries_user_tenant_session_uidx" in sql

def test_consent_trigger_supports_text_and_legacy_uuid_tenant_columns():
    sql = (MIGRATIONS / GUARD_NAME).read_text(encoding="utf-8")
    guard_start = sql.index(
        "CREATE OR REPLACE FUNCTION public.enforce_active_memory_consent_before_write"
    )
    guard_end = sql.index("$memory_consent_write$;", guard_start) + len(
        "$memory_consent_write$;"
    )
    write_guard = sql[guard_start:guard_end]

    # Existing tables use both text tenant IDs and UUID tenant IDs. Do not cast
    # NEW.tenant_id directly or install a text default on a UUID column.
    assert "to_jsonb(NEW)->>'tenant_id'" in write_guard
    assert "v_tenant_id text" in write_guard
    assert "receipt.tenant_id = v_tenant_id" in write_guard
    assert "00000000-0000-0000-0000-000000000000" in write_guard
    trigger_block = sql[sql.index("DO $memory_consent_trigger$"):]
    assert "information_schema.columns" in trigger_block
    assert "tenant_data_type = 'uuid'" in trigger_block
    assert "Unsupported tenant_id type" in trigger_block


def test_revoked_user_can_soft_delete_canonical_memory_without_editing_its_content():
    sql = (MIGRATIONS / GUARD_NAME).read_text(encoding="utf-8")

    # RLS validates the new row, while the trigger compares OLD and NEW. A
    # status='deleted' result alone must never allow rewriting the memory text.
    assert "IF memory_table = 'canonical_memories' THEN" in sql
    assert "public.has_active_memory_consent(user_id, tenant_id) OR status = ''deleted''" in sql
    assert "to_jsonb(NEW) - ARRAY['status', 'updated_at', 'version']" in sql
    assert "(to_jsonb(OLD) - ARRAY['status', 'updated_at', 'version'])" in sql
    assert "NEW.user_id IS NOT DISTINCT FROM OLD.user_id" in sql
    assert "NEW.tenant_id IS NOT DISTINCT FROM OLD.tenant_id" in sql


def test_deleted_canonical_row_can_write_only_its_matching_delete_audit_after_revocation():
    sql = (MIGRATIONS / GUARD_NAME).read_text(encoding="utf-8")
    guard_start = sql.index(
        "CREATE OR REPLACE FUNCTION public.enforce_active_memory_consent_before_write"
    )
    guard_end = sql.index("$memory_consent_write$;", guard_start) + len(
        "$memory_consent_write$;"
    )
    write_guard = sql[guard_start:guard_end]

    assert "TG_TABLE_NAME = 'canonical_memory_events'" in write_guard
    assert "NEW.event_type = 'DELETED'" in write_guard
    assert "memory.id = NEW.memory_id" in write_guard
    assert "memory.user_id = NEW.user_id" in write_guard
    assert "memory.tenant_id = v_tenant_id" in write_guard
    assert "memory.status = 'deleted'" in write_guard
