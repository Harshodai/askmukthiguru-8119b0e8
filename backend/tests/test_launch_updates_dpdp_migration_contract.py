"""Static contract for the launch-updates DPDP migration (erase, retention, throttles).

Parses the migration text, like test_memory_consent_migration_contract.py. It cannot prove
runtime behaviour; the owner applies the SQL to a branch/staging DB for that (UNPROVEN here).
"""

import re
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

ROOT = Path(__file__).resolve().parents[2]
MIGRATIONS = ROOT / "supabase" / "migrations"
NAME = "20261120120000_launch_updates_dpdp_controls.sql"
COMMENT_NAME = "20261120120100_comment_brain_keys_archive.sql"


@pytest.fixture(scope="module")
def sql() -> str:
    return (MIGRATIONS / NAME).read_text(encoding="utf-8")


def _fn(sql: str, name: str) -> str:
    start = sql.index(f"CREATE OR REPLACE FUNCTION public.{name}")
    return sql[start : sql.index("$$;", sql.index("$$", start) + 2)]


def test_sorts_after_the_applied_launch_migrations():
    applied = [p.name for p in MIGRATIONS.glob("20261120023*.sql")]
    assert applied and all(NAME > a for a in applied)
    assert COMMENT_NAME > NAME
    later = [p.name for p in MIGRATIONS.glob("*.sql") if p.name > COMMENT_NAME]
    assert not later


def test_no_rls_loosening_or_anon_table_privileges(sql):
    assert not re.search(r"DISABLE ROW LEVEL SECURITY", sql, re.I)
    assert not re.search(r"GRANT\s+(SELECT|UPDATE|DELETE|ALL)[^;]*waitlist_entries[^;]*\bTO\s+[^;]*anon", sql, re.I)
    assert not re.search(r"CREATE POLICY[^;]*waitlist_entries[^;]*FOR\s+(SELECT|ALL|UPDATE)", sql, re.I)
    assert "ALTER TABLE public.launch_signup_throttle ENABLE ROW LEVEL SECURITY" in sql
    assert "FROM PUBLIC, anon, authenticated" in sql.split("launch_signup_throttle FROM")[1][:60] or (
        "REVOKE ALL ON public.launch_signup_throttle FROM PUBLIC, anon, authenticated" in sql
    )


def test_admin_delete_policy_needs_admin_role_and_aal2(sql):
    policy = sql[sql.index('CREATE POLICY "Launch subscriber erase requires admin MFA"') :]
    policy = policy[: policy.index(";")]
    assert "FOR DELETE TO authenticated" in policy
    assert "'aal2'" in policy and "has_role" in policy and "'admin'" in policy
    assert "DROP POLICY IF EXISTS" in sql  # idempotent


def test_token_column_is_unique_and_server_generated(sql):
    assert "ADD COLUMN IF NOT EXISTS unsubscribe_token uuid NOT NULL DEFAULT pg_catalog.gen_random_uuid()" in sql
    assert "CREATE UNIQUE INDEX IF NOT EXISTS waitlist_entries_unsubscribe_token_key" in sql
    assert "NEW.unsubscribe_token := pg_catalog.gen_random_uuid()" in _fn(sql, "validate_launch_subscription")


@pytest.mark.parametrize(
    "name", ["erase_launch_subscription", "erase_launch_subscription_with_token"]
)
def test_erase_rpcs_are_definer_pinned_throttled_and_non_disclosing(sql, name):
    body = _fn(sql, name)
    assert "SECURITY DEFINER SET search_path = ''" in body
    assert "pg_advisory_xact_lock(811901119)" in body
    assert "launch_throttle_hit('erase-all'" in body
    assert "launch_client_key()" in body
    assert "RETURN 'accepted'" in body
    assert "DELETE FROM public.waitlist_entries WHERE email_key = v_email" in body
    assert re.search(rf"GRANT EXECUTE ON FUNCTION public\.{name}\([^)]*\) TO anon, authenticated", sql)
    assert re.search(rf"REVOKE ALL ON FUNCTION public\.{name}\([^)]*\) FROM PUBLIC", sql)


def test_token_erase_requires_the_token(sql):
    assert "AND unsubscribe_token = p_token" in _fn(sql, "erase_launch_subscription_with_token")


def test_purge_is_service_role_only_and_enforces_a_floor(sql):
    body = _fn(sql, "purge_expired_launch_subscribers")
    assert "p_months integer DEFAULT 12" in body
    assert "p_months < 1" in body
    assert "consented_at < now() - pg_catalog.make_interval(months => p_months)" in body
    assert "REVOKE ALL ON FUNCTION public.purge_expired_launch_subscribers(integer) FROM PUBLIC, anon, authenticated" in sql
    assert "GRANT EXECUTE ON FUNCTION public.purge_expired_launch_subscribers(integer) TO service_role" in sql
    assert not re.search(r"purge_expired_launch_subscribers\(integer\) TO [^;]*(anon|authenticated)", sql)


def test_pg_cron_schedule_is_guarded_by_extension_presence(sql):
    block = sql[sql.index("DO $$", sql.index("purge_expired_launch_subscribers(integer) TO service_role")) :]
    assert "extname = 'pg_cron'" in block.split("cron.schedule")[0]
    assert "cron.schedule('purge-launch-subscribers'" in block


def test_every_existing_signup_protection_is_preserved(sql):
    body = _fn(sql, "validate_launch_subscription")
    for needle in (
        "NEW.consent_to_contact IS DISTINCT FROM true",
        "'guide_ai_spiritual_companion'",
        "'guide_suffering'",
        "length(NEW.email) > 254",
        "NEW.name := NULL",
        "pg_advisory_xact_lock(811901119)",
        ">= 100 THEN RAISE EXCEPTION 'Signup temporarily busy'",
        "IF EXISTS (SELECT 1 FROM public.waitlist_entries WHERE lower(btrim(email))=NEW.email) THEN RETURN NULL",
    ):
        assert needle in body, needle
    assert "SECURITY DEFINER SET search_path = ''" in body
    # per-source and per-client buckets sit between the global ceiling and the dedupe return
    order = [body.index(s) for s in (">= 100 THEN", "'signup-src:'", "'signup-client:'", "RETURN NULL")]
    assert order == sorted(order)


def test_client_key_falls_back_safely_and_hashes_the_ip(sql):
    body = _fn(sql, "launch_client_key")
    assert "current_setting('request.headers', true)" in body
    assert "x-forwarded-for" in body
    assert "EXCEPTION WHEN others THEN" in body and "RETURN NULL" in body
    assert "sha256" in body  # no raw IP is stored
    assert "REVOKE ALL ON FUNCTION public.launch_client_key() FROM PUBLIC, anon, authenticated" in sql


def test_throttle_helper_is_internal_only(sql):
    assert "REVOKE ALL ON FUNCTION public.launch_throttle_hit(text, integer) FROM PUBLIC, anon, authenticated" in sql
    assert not re.search(r"launch_throttle_hit\(text, integer\) TO", sql)


def test_idempotent_ddl(sql):
    assert "CREATE TABLE IF NOT EXISTS public.launch_signup_throttle" in sql
    assert "DROP TRIGGER IF EXISTS validate_launch_subscription" in sql
    assert not re.search(r"CREATE TABLE (?!IF NOT EXISTS)", sql)
    assert not re.search(r"\bDROP TABLE\b", sql)


def test_archive_comment_migration_is_guarded_and_never_drops():
    text = (MIGRATIONS / COMMENT_NAME).read_text(encoding="utf-8")
    assert "to_regclass('public.user_brain_keys_archive_20261119') IS NOT NULL" in text
    assert (
        "'Vault-key backup from 2026-11-19 BRAIN_KEK work; retain until owner decision; do not drop'"
        in text
    )
    assert not re.search(r"\bDROP\s+(TABLE|SCHEMA|COLUMN)\b|\bDELETE\b|\bTRUNCATE\b", text, re.I)


def test_rls_verifier_probes_the_new_functions_and_twin_is_identical():
    verifier = (ROOT / "backend" / "scripts" / "verify_rls_policies.py").read_bytes()
    for name in (
        b"erase_launch_subscription_with_token",
        b"erase_launch_subscription",
        b"purge_expired_launch_subscribers",
        b"launch_signup_throttle",
    ):
        assert name in verifier
    assert verifier == (ROOT / "scripts" / "verify_rls_policies.py").read_bytes()


def test_retention_task_calls_the_purge_rpc_with_twelve_months():
    from tasks.retention_tasks import LAUNCH_SUBSCRIBER_RETENTION_MONTHS, purge_launch_subscribers

    client = MagicMock()
    client.rpc.return_value.execute.return_value.data = 7
    assert purge_launch_subscribers(client=client) == 7
    client.rpc.assert_called_once_with("purge_expired_launch_subscribers", {"p_months": 12})
    assert LAUNCH_SUBSCRIBER_RETENTION_MONTHS == 12


def test_cleanup_task_runs_launch_purge_and_survives_its_failure():
    from tasks.retention_tasks import cleanup_retention_data

    base = [
        patch("scripts.ops.cleanup_inactive_user_data.cleanup_telemetry_logs", return_value=0),
        patch("services.compliance_logger.cleanup_compliance_audit_files", return_value=0),
        patch("scripts.ops.cleanup_inactive_user_data.cleanup_staging_quality_queue", return_value=0),
    ]
    for p in base:
        p.start()
    try:
        with patch("tasks.retention_tasks.purge_launch_subscribers", return_value=3) as purge:
            assert cleanup_retention_data(days_retention=90)["launch_subscribers_purged"] == 3
            purge.assert_called_once_with()
        with patch("tasks.retention_tasks.purge_launch_subscribers", side_effect=RuntimeError("x")):
            assert cleanup_retention_data(days_retention=90)["launch_subscribers_purged"] == 0
    finally:
        for p in base:
            p.stop()
