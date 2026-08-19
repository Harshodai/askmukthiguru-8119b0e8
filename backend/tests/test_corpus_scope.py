"""Cross-store tenant/corpus containment regressions."""

from __future__ import annotations

from unittest.mock import MagicMock

from qdrant_client.http.models import FieldCondition

from rag.corpus_scope import CorpusScope
from services.qdrant.searcher import QdrantSearcher


def test_qdrant_search_always_binds_tenant_and_corpus_scope() -> None:
    searcher = QdrantSearcher(MagicMock(), "teachings")
    observed: dict[str, object] = {}

    def dense(_vector, _limit, search_filter, _params=None):
        observed["filter"] = search_filter
        return []

    searcher._dense_search = dense  # type: ignore[method-assign]
    scope = CorpusScope(tenant_id="tenant-a", corpus_id="teacher-a", teacher_id="teacher-a")
    assert searcher.search([0.1, 0.2], scope=scope) == []

    conditions = observed["filter"].must
    values = {
        condition.key: condition.match.value
        for condition in conditions
        if isinstance(condition, FieldCondition)
    }
    assert values == {"tenant_id": "tenant-a", "corpus_id": "teacher-a", "teacher_id": "teacher-a"}


def test_scope_filters_do_not_allow_cross_tenant_substitution() -> None:
    tenant_a = CorpusScope(tenant_id="tenant-a", corpus_id="shared")
    tenant_b = CorpusScope(tenant_id="tenant-b", corpus_id="shared")
    assert tenant_a.to_qdrant_filter() != tenant_b.to_qdrant_filter()
    assert tenant_a.to_neo4j_params()["tenant_id"] != tenant_b.to_neo4j_params()["tenant_id"]
