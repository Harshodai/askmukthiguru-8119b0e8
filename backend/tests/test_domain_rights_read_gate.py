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


def test_quarantined_removed_book_source_is_not_served():
    from services.qdrant.source_policy import filter_blocked_sources, is_blocked_source

    blocked = {
        "source_url": "The_Four_Sacred_Secrets.pdf",
        "title": "The Four Sacred Secrets",
        "text": "legacy content must not reach user-facing retrieval",
    }
    allowed = {
        "source_url": "https://www.youtube.com/watch?v=example",
        "title": "A teaching on stillness",
        "text": "ordinary licensed teaching",
    }

    assert is_blocked_source(blocked)
    assert is_blocked_source(
        {"source_url": "https://legacy.example/files/The_Four_Sacred_Secrets.pdf?download=1#page=2"}
    )
    kept, dropped = filter_blocked_sources([blocked, allowed])
    assert dropped == 1
    assert kept == [allowed]


def test_book_reingested_under_amazon_url_is_also_blocked():
    """2026-09-22 rights audit: the scrubbed book re-entered Qdrant under an
    Amazon source_url (content_type=book, 1,199 live chunks), which the
    filename-identity check above never matched. Both re-entry vectors --
    the ASIN in source_url and the chapter-qualified title prefix -- must be
    caught, without blocking unrelated teachings that merely mention the
    book's name in passing (e.g. a chunk of body text).
    """
    from services.qdrant.source_policy import is_blocked_source

    reingested = {
        "source_url": "https://www.amazon.in/Four-Sacred-Secrets-Prosperity-Beautiful/dp/1846046319",
        "title": "The Four Sacred Secrets — The Third Life Journey: Become a Heartful Partner > What Is Connection?",
        "text": "talk to you about my mom and Krishnaji...",
    }
    assert is_blocked_source(reingested)
    assert is_blocked_source({"source_url": reingested["source_url"]})
    assert is_blocked_source({"title": reingested["title"]})

    unrelated = {
        "source_url": "https://www.youtube.com/watch?v=example",
        "title": "A teaching on stillness",
        "text": "In the book The Four Sacred Secrets, the gurus describe connection.",
    }
    assert not is_blocked_source(unrelated)


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
