"""P1-DB-11 — guru_memories pgvector HNSW parameter regression test.

The pgvector index for `public.guru_memories` must use the doctrine-matching
HNSW build parameters: m=32, ef_construction=200.
"""

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "supabase"
    / "migrations"
    / "20260618044620_58e0642d-38c0-469d-9bd5-b6e91fc32297.sql"
)


@pytest.fixture(scope="module")
def migration_sql() -> str:
    assert MIGRATION.exists(), f"missing {MIGRATION}"
    return MIGRATION.read_text().lower()


def test_guru_memories_hnsw_m_is_32(migration_sql: str) -> None:
    assert "m = 32" in migration_sql or "m=32" in migration_sql, (
        "guru_memories HNSW index must set m=32"
    )


def test_guru_memories_hnsw_ef_construction_is_200(migration_sql: str) -> None:
    assert "ef_construction = 200" in migration_sql or "ef_construction=200" in migration_sql, (
        "guru_memories HNSW index must set ef_construction=200"
    )


def test_guru_memories_embedding_idx_exists(migration_sql: str) -> None:
    assert "guru_memories_embedding_idx" in migration_sql, (
        "guru_memories HNSW index name must be present"
    )


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
