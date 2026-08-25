from pathlib import Path

ROOT = Path(__file__).parents[2]
SCRIPTS = ROOT / "scripts" / "ops"
WORKFLOW = ROOT / ".github" / "workflows" / "staging-security-verification.yml"


def test_runtime_gate_is_staging_safe_and_fail_closed() -> None:
    source = (SCRIPTS / "verify_runtime_gate.sh").read_text(encoding="utf-8")

    assert 'BASE_URL="${STAGING_BASE_URL:?Set STAGING_BASE_URL' in source
    assert "Refusing non-HTTP(S) staging URL" in source
    assert "runtime_artifacts.readiness_ok" in source
    assert "missing-asset" in source
    assert "admin" in source
    assert "chat-malformed" in source


def test_red_team_requires_staging_and_explicit_synthetic_user_authorization() -> None:
    source = (SCRIPTS / "staging_red_team.sh").read_text(encoding="utf-8")

    assert 'STAGING_ENVIRONMENT:-' in source
    assert '!= "staging"' in source
    assert 'ALLOW_STAGING_SYNTHETIC_USERS:-' in source
    assert "verify_rls_policies.py" in source
    assert "verify_runtime_gate.sh" in source
    assert "PUT PATCH DELETE" in source


def test_migration_verifier_is_transaction_only_and_staging_guarded() -> None:
    source = (SCRIPTS / "verify_migration_rollback.sh").read_text(encoding="utf-8")

    assert 'STAGING_ENVIRONMENT:-' in source
    assert '!= "staging"' in source
    assert 'ALLOW_NONDESTRUCTIVE_DB_VERIFY:-' in source
    assert "BEGIN;" in source
    assert "ROLLBACK;" in source
    assert "20260825000002_restore_user_activity_table_grants.sql" in source
    assert "authenticated_sessions" in source
    assert "authenticated_profiles" in source
    assert "mutated_rows" in source
    assert "state changed after ROLLBACK" in source


def test_retrieval_gate_requires_strict_eval_and_protects_baseline() -> None:
    source = (SCRIPTS / "verify_retrieval_gate.sh").read_text(encoding="utf-8")

    assert 'REQUIRE_QDRANT_EVAL=1' in source
    assert 'QDRANT_API_KEY:?Set QDRANT_API_KEY' in source
    assert "UPDATE_QDRANT_BASELINE" in source
    assert "before_sha" in source
    assert "changed the baseline in read-only mode" in source


def test_rls_verifier_rejects_unspecified_remote_targets() -> None:
    source = (ROOT / "backend" / "scripts" / "verify_rls_policies.py").read_text(encoding="utf-8")

    assert "_is_local_supabase" in source
    assert 'STAGING_ENVIRONMENT == "staging"' in source
    assert "ALLOW_STAGING_SYNTHETIC_USERS" in source
    assert "refusing non-local RLS verification target" in source
    assert 'key = "user_id" if table == "user_profiles" else "id"' in source
    assert "cleanup_failures" in source


def test_workflow_is_staging_scoped_and_uploads_evidence() -> None:
    source = WORKFLOW.read_text(encoding="utf-8")

    assert "environment: staging" in source
    assert "STAGING_ENVIRONMENT: staging" in source
    assert "ALLOW_STAGING_SYNTHETIC_USERS: '1'" in source
    assert "verify_migration_rollback.sh" in source
    assert "staging_red_team.sh" in source
    assert "verify_retrieval_gate.sh" in source
    assert "actions/upload-artifact@v4" in source
    assert "production Supabase" not in source
