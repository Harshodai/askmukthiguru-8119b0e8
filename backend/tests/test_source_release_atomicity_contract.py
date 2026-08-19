from pathlib import Path

MIGRATION = (
    Path(__file__).parents[2]
    / "supabase/migrations/20260814080000_harden_source_release_atomicity.sql"
)


def test_source_release_atomicity_migration_has_idempotency_and_single_active_indexes():
    sql = MIGRATION.read_text()
    assert "uq_source_releases_identity_checksum" in sql
    assert "corpus_id, source_identity, content_checksum" in sql
    assert "uq_source_releases_one_active" in sql
    assert "WHERE status = 'active'" in sql
    assert "intentionally fails" in sql
