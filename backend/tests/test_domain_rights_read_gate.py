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

    def dense(_vector, _limit, search_filter, _params=None, grouping_keys=None, group_size=2):
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


def test_book_source_no_longer_blocked_after_rights_confirmed():
    """2026-09-23: superseded test. The Four Sacred Secrets was blocked
    2026-09-22 pending rights review; CONTENT-RIGHTS.md now records rights
    confirmed by the project owner (2026-09-23, human statement, not
    independently verified by any agent -- N9). The block was removed in
    services/qdrant/source_policy.py accordingly. This test locks the new,
    intentional behavior so a future change doesn't silently re-block a
    now-cleared source, or silently leave the module's blocklist mechanism
    broken for whatever gets added to it next.
    """
    from services.qdrant.source_policy import filter_blocked_sources, is_blocked_source

    book = {
        "source_url": "The_Four_Sacred_Secrets.pdf",
        "title": "The Four Sacred Secrets",
        "text": "now-cleared content, must be served",
    }
    reingested = {
        "source_url": "https://www.amazon.in/Four-Sacred-Secrets-Prosperity-Beautiful/dp/1846046319",
        "title": "The Four Sacred Secrets — The Third Life Journey: Become a Heartful Partner > What Is Connection?",
        "text": "talk to you about my mom and Krishnaji...",
    }
    allowed = {
        "source_url": "https://www.youtube.com/watch?v=example",
        "title": "A teaching on stillness",
        "text": "ordinary licensed teaching",
    }

    assert not is_blocked_source(book)
    assert not is_blocked_source(reingested)
    assert not is_blocked_source(allowed)
    kept, dropped = filter_blocked_sources([book, reingested, allowed])
    assert dropped == 0
    assert kept == [book, reingested, allowed]


def test_serve_only_registered_sources_gate():
    from services.qdrant.source_policy import filter_unregistered_sources, is_registered_source

    cleared = {"source_url": "https://example.org/a", "domain_rights_status": "cleared"}
    licensed_default = {"source_url": "https://example.org/b", "domain_rights_status": "licensed"}
    unconfirmed = {"source_url": "https://example.org/c"}

    assert is_registered_source(cleared)
    assert not is_registered_source(licensed_default)
    assert not is_registered_source(unconfirmed)

    kept, dropped = filter_unregistered_sources([cleared, licensed_default, unconfirmed])
    assert kept == [cleared]
    assert dropped == 2
