"""Live test verifying the serve-time source_policy block sets are empty.

2026-09-25: superseded. This file previously asserted a narrow serve-time
quarantine for "The Four Sacred Secrets" (ASIN 1846046319 / title prefix).
CONTENT-RIGHTS.md now records rights confirmed by the project owner
(2026-09-23, human statement, not independently verified by any agent -- N9),
and services/qdrant/source_policy.py's block sets were reverted to empty
accordingly (see that file's own 2026-09-23 comment). This test now locks
the owner's decision: book sources are NOT blocked, the block sets are
empty, and both book and YouTube content pass through retrieval unblocked.
"""

from unittest.mock import MagicMock

import pytest

import rag.nodes as nodes
from app.config import settings
from rag.nodes import _services
from services.qdrant.source_policy import (
    _BLOCKED_SOURCE_IDENTITIES,
    _BLOCKED_SOURCE_URL_SUBSTRINGS,
    _BLOCKED_TITLE_PREFIXES,
    filter_blocked_sources,
    is_blocked_source,
)


def test_block_sets_are_empty_per_owner_rights_confirmation():
    """Locks the 2026-09-23 owner decision so a future change doesn't
    silently re-introduce a quarantine for a now-cleared source."""
    assert _BLOCKED_SOURCE_IDENTITIES == frozenset()
    assert _BLOCKED_SOURCE_URL_SUBSTRINGS == frozenset()
    assert _BLOCKED_TITLE_PREFIXES == ()


@pytest.mark.asyncio
async def test_book_and_youtube_sources_both_pass_through_unblocked(monkeypatch):
    monkeypatch.setattr(settings, "serve_only_registered_sources", False)
    monkeypatch.setattr(settings, "rag_okf_injection_enabled", False)
    monkeypatch.setattr(settings, "semantic_cache_enabled", False)
    monkeypatch.setattr(settings, "retrieval_score_delta_enabled", False)
    monkeypatch.setattr(settings, "rag_skip_retrieval_expansions", True)

    mock_container = MagicMock()
    mock_container.neo4j_driver = None
    monkeypatch.setattr("app.dependencies.get_container", lambda: mock_container)

    mock_embedder = MagicMock()
    mock_embedder.encode_single_full.return_value = {"dense": [0.1] * 1024, "sparse": {"1": 0.5}}
    mock_embedder.encode_batch.return_value = {"dense": [[0.1] * 1024], "sparse": [{"1": 0.5}]}
    mock_embedder.instruction = ""

    book_chunk = {
        "text": "The Second Sacred Secret of Inner Truth teaches self-awareness without judgment.",
        "source_url": "https://www.amazon.in/Four-Sacred-Secrets-Prosperity-Beautiful/dp/1846046319",
        "title": "The Four Sacred Secrets — The Second Sacred Secret: Inner Truth",
        "score": 0.95,
        "content_type": "book",
        "domain_rights_status": "licensed",
    }
    youtube_chunk = {
        "text": "Sri Krishnaji teaches that in a beautiful state, consciousness expands.",
        "source_url": "https://www.youtube.com/watch?v=3ITFXvYIPqg",
        "title": "The Power of a Beautiful State — Sri Krishnaji",
        "score": 0.92,
        "content_type": "video_enhanced",
        "domain_rights_status": "licensed",
    }

    # Unit-level source_policy: neither source is blocked.
    assert is_blocked_source(book_chunk) is False
    assert is_blocked_source(youtube_chunk) is False
    kept, dropped = filter_blocked_sources([book_chunk, youtube_chunk])
    assert dropped == 0
    assert kept == [book_chunk, youtube_chunk]

    # Retrieval-level: a query surfacing book content is served, not quarantined.
    mock_qdrant_book = MagicMock()
    mock_qdrant_book.search = MagicMock(return_value=[book_chunk])

    monkeypatch.setattr(_services, "_embedder", mock_embedder)
    monkeypatch.setattr(_services, "_qdrant", mock_qdrant_book)
    monkeypatch.setattr(_services, "_lightrag", MagicMock())

    book_query_state = {
        "question": "What is the Second Sacred Secret from the book?",
        "chat_history": [],
        "rewritten_query": None,
        "sub_queries": [],
        "selected_clusters": [],
        "hyde_text": None,
        "intent": "FACTUAL",
    }

    retrieval_res_book = await nodes.retrieve_documents(book_query_state)
    assert "error" not in retrieval_res_book
    assert len(retrieval_res_book["documents"]) == 1
    assert retrieval_res_book["documents"][0]["source_url"] == book_chunk["source_url"]

    # YouTube content continues to pass through unblocked as before.
    mock_qdrant_yt = MagicMock()
    mock_qdrant_yt.search = MagicMock(return_value=[youtube_chunk])
    monkeypatch.setattr(_services, "_qdrant", mock_qdrant_yt)

    yt_query_state = {
        "question": "What is a beautiful state according to Sri Krishnaji?",
        "chat_history": [],
        "rewritten_query": None,
        "sub_queries": [],
        "selected_clusters": [],
        "hyde_text": None,
        "intent": "FACTUAL",
    }

    retrieval_res_yt = await nodes.retrieve_documents(yt_query_state)
    assert "error" not in retrieval_res_yt
    assert len(retrieval_res_yt["documents"]) == 1
    assert (
        retrieval_res_yt["documents"][0]["source_url"]
        == "https://www.youtube.com/watch?v=3ITFXvYIPqg"
    )
