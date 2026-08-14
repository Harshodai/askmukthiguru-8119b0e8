from unittest.mock import MagicMock

from qdrant_client.http.models import FieldCondition

from rag.corpus_scope import CorpusScope
from services.qdrant.searcher import QdrantSearcher


def test_scope_can_require_explicit_licensed_domain():
    scope = CorpusScope(
        tenant_id="tenant-a",
        corpus_id="askmukthiguru",
        teacher_id="ekam",
        required_rights_status="licensed",
    )
    payload_filter = scope.to_qdrant_filter()
    assert {item["key"]: item["match"]["value"] for item in payload_filter["must"]} == {
        "tenant_id": "tenant-a",
        "corpus_id": "askmukthiguru",
        "teacher_id": "ekam",
        "domain_rights_status": "licensed",
    }
    assert scope.to_neo4j_params()["required_rights_status"] == "licensed"


def test_qdrant_search_adds_rights_filter_and_returns_provenance_fields():
    client = MagicMock()
    searcher = QdrantSearcher(client, "teachings")
    observed = {}

    def dense(_vector, _limit, search_filter, _params=None):
        observed["filter"] = search_filter
        return []

    searcher._dense_search = dense
    scope = CorpusScope(
        tenant_id="tenant-a",
        corpus_id="askmukthiguru",
        required_rights_status="licensed",
    )
    assert searcher.search([0.1, 0.2], scope=scope) == []
    values = {
        condition.key: condition.match.value
        for condition in observed["filter"].must
        if isinstance(condition, FieldCondition)
    }
    assert values["domain_rights_status"] == "licensed"
