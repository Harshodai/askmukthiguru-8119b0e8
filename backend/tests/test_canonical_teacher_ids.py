"""T3-07 / DATA-13 / GURU-013: Canonical teacher IDs and cross-store normalization.

Verifies:
1. canonical_guru_id resolves legacy store vocabularies (sri-krishnaji, sri_krishnaji, etc.) to registry IDs.
2. resolve_guru_id recognizes shared founder scopes (preethaji_krishnaji).
3. FirstPersonContextStore.retrieve normalizes teacher filters to canonical IDs.
4. FirstPersonStore.search_hybrid normalizes teacher filters to canonical IDs.
5. Legacy Postgres tables audit confirms 0 runtime code dependencies.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from scripts.ops.check_legacy_guru_tables import check_table_usage
from services.first_person_context_store import FirstPersonContextStore
from services.first_person_store import FirstPersonStore
from services.guru_registry import (
    canonical_guru_id,
    resolve_guru_id,
)


def test_canonical_guru_id_resolution():
    """canonical_guru_id maps all historical store vocabularies to gurus.yaml IDs."""
    # Krishnaji variants
    assert canonical_guru_id("krishnaji") == "krishnaji"
    assert canonical_guru_id("sri-krishnaji") == "krishnaji"
    assert canonical_guru_id("sri_krishnaji") == "krishnaji"
    assert canonical_guru_id("Sri Krishnaji") == "krishnaji"
    assert canonical_guru_id("KRISHNAJI") == "krishnaji"

    # Preethaji variants
    assert canonical_guru_id("preethaji") == "preethaji"
    assert canonical_guru_id("sri-preethaji") == "preethaji"
    assert canonical_guru_id("sri_preethaji") == "preethaji"
    assert canonical_guru_id("Sri Preethaji") == "preethaji"
    assert canonical_guru_id("PREETHAJI") == "preethaji"

    # Shared scope variants
    assert canonical_guru_id("preethaji_krishnaji") == "preethaji_krishnaji"
    assert canonical_guru_id("krishnaji_preethaji") == "preethaji_krishnaji"
    assert canonical_guru_id("both") == "preethaji_krishnaji"
    assert canonical_guru_id("shared") == "preethaji_krishnaji"

    # Organization / unknown
    assert canonical_guru_id("ekam") == "ekam"
    assert canonical_guru_id("unknown_teacher_id") is None
    assert canonical_guru_id(None) is None


def test_resolve_guru_id_shared_scope():
    """resolve_guru_id recognizes the shared attribution pair."""
    assert resolve_guru_id("preethaji_krishnaji") == "preethaji_krishnaji"
    assert resolve_guru_id("krishnaji_preethaji") == "preethaji_krishnaji"


def test_first_person_context_store_normalizes_filter():
    """Context store normalizes teacher filter argument before building Qdrant condition."""
    mock_qdrant = MagicMock()
    mock_qdrant.query_points_groups.return_value = MagicMock(groups=[])
    store = FirstPersonContextStore(mock_qdrant, collection="test_col")

    # Call with non-canonical teacher id 'sri-krishnaji'
    store.retrieve(
        query_dense=[0.1] * 1024,
        guru_id="sri-krishnaji",
    )

    assert mock_qdrant.query_points_groups.called
    kwargs = mock_qdrant.query_points_groups.call_args[1]
    query_filter = kwargs["query_filter"]
    guru_condition = next(c for c in query_filter.must if c.key == "guru_id")
    # Must be resolved to canonical 'krishnaji', not raw 'sri-krishnaji'
    assert guru_condition.match.value == "krishnaji"


def test_first_person_store_search_hybrid_normalizes_filter():
    """Legacy/hybrid store normalizes teacher_id before building RRF prefetch filter."""
    mock_qdrant = MagicMock()
    mock_qdrant.query_points.return_value = MagicMock(points=[])
    store = FirstPersonStore(client=mock_qdrant, collection="test_col")

    store.search_hybrid(
        query_dense_vector=[0.1] * 1024,
        teacher_id="sri-preethaji",
    )

    assert mock_qdrant.query_points.called
    kwargs = mock_qdrant.query_points.call_args[1]
    prefetch = kwargs["prefetch"][0]
    teacher_condition = next(c for c in prefetch.filter.must if c.key == "teacher_id")
    # Must be resolved to canonical 'preethaji', not raw 'sri-preethaji'
    assert teacher_condition.match.value == "preethaji"


def test_legacy_guru_tables_have_zero_code_references():
    """Postgres kb_chunks and gurus tables have 0 active runtime references."""
    for tbl in ("kb_chunks", "gurus"):
        hits = check_table_usage(tbl)
        assert hits == [], f"Table {tbl} has unexpected active references: {hits}"
