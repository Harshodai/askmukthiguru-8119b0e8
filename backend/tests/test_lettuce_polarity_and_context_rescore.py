"""Unit tests for LettuceDetect polarity exemption and ContextStore dense rescoring."""

from types import SimpleNamespace
from unittest.mock import MagicMock

from qdrant_client.http.models import FieldCondition, Filter, MatchValue

from services.first_person_context_store import FirstPersonContextStore
from services.lettuce_detect_service import _detect_contradiction


def test_detect_contradiction_allows_independent_of_phrasing():
    claim = "A beautiful state does not depend on external achievements or wealth."
    context = (
        "The beautiful state is an inner state of joy that is independent of external achievements "
        "or wealth and conditions."
    )
    contradicted, reason = _detect_contradiction(claim, context)
    assert contradicted is False, f"Unexpected contradiction: {reason}"


def test_detect_contradiction_allows_not_from_but_from_and_cannot_replace():
    ctx_not_but = (
        "Lasting happiness and freedom from suffering come not from external achievements "
        'but from cultivating an inner "Beautiful State" of joy, peace.'
    )
    contradicted1, r1 = _detect_contradiction(
        "The Beautiful State is an inner condition of joy and peace.", ctx_not_but
    )
    assert contradicted1 is False, r1

    ctx_sustain = (
        "This external pursuit of happiness is contrasted with the deeper, sustainable "
        "well-being found in cultivating inner affection, self-awareness."
    )
    contradicted2, r2 = _detect_contradiction(
        "While sensory inputs provide momentary delight, they cannot replace the sustainable "
        "well-being found in cultivating inner affection and self-awareness.",
        ctx_sustain,
    )
    assert contradicted2 is False, r2


def test_context_store_hybrid_rescores_dense_similarity_above_noisy_rrf():
    client = MagicMock()
    q_vec = [1.0, 0.0, 0.0, 0.0]

    # Hit 0 returned first by RRF due to sparse BM25 noise, but poor dense similarity (0.0)
    noisy_rrf_group = SimpleNamespace(
        id="parent_sparse_noise",
        hits=[
            SimpleNamespace(
                id="s_noise",
                score=0.95,
                payload={"source_span_id": "s_noise"},
                vector={"passage_dense": [0.0, 1.0, 0.0, 0.0]},
            )
        ],
    )
    # Hit 1 returned lower by RRF, but strong semantic dense match (1.0)
    semantic_dense_group = SimpleNamespace(
        id="parent_semantic_best",
        hits=[
            SimpleNamespace(
                id="s_best",
                score=0.45,
                payload={"source_span_id": "s_best"},
                vector={"passage_dense": [1.0, 0.0, 0.0, 0.0]},
            )
        ],
    )
    client.query_points_groups.return_value = SimpleNamespace(
        groups=[noisy_rrf_group, semantic_dense_group]
    )

    store = FirstPersonContextStore(client, collection="first_person_v13_shadow")
    groups = store._query_groups(
        q_vec,
        query_sparse={"indices": [1, 2], "values": [0.8, 0.6]},
        query_filter=Filter(
            must=[FieldCondition(key="record_type", match=MatchValue(value="source_span"))]
        ),
        limit_parents=4,
        spans_per_parent=2,
    )

    assert [g[0] for g in groups] == ["parent_semantic_best", "parent_sparse_noise"]
