"""P0-3: _okf_match must reuse the shared pipeline embedder, not instantiate EmbeddingService per call."""

from unittest.mock import MagicMock, patch

import rag.nodes.retrieval as retrieval_mod


def _seed_okf(monkeypatch):
    monkeypatch.setattr(
        retrieval_mod,
        "_OKF_CACHE",
        [
            {
                "title": "karma",
                "body": "law of cause and effect",
                "embedding": [1.0] + [0.0] * 1023,
            },
        ],
    )


def test_okf_match_reuses_shared_embedder(monkeypatch):
    """Calling _okf_match twice must NOT instantiate EmbeddingService either time."""
    _seed_okf(monkeypatch)

    shared = MagicMock()
    shared.encode.return_value = [[0.5] * 1024]
    monkeypatch.setattr(retrieval_mod._services, "_embedder", shared)

    with patch("services.embedding_service.EmbeddingService") as MockEmbeddingService:
        # If _okf_match falls back to EmbeddingService(), this constructor would be called.
        MockEmbeddingService.return_value = MagicMock(encode=MagicMock(return_value=[[0.5] * 1024]))
        retrieval_mod._okf_match("what is karma", limit=1)
        retrieval_mod._okf_match("what is dharma", limit=1)
        assert MockEmbeddingService.call_count == 0, (
            "EmbeddingService was instantiated — shared embedder not reused"
        )

    assert shared.encode.call_count == 2


def test_okf_match_uses_same_embedder_identity(monkeypatch):
    """The embedder used by _okf_match must be the exact object on _services._embedder."""
    _seed_okf(monkeypatch)

    shared = MagicMock()
    shared.encode.return_value = [[0.5] * 1024]
    monkeypatch.setattr(retrieval_mod._services, "_embedder", shared)

    retrieval_mod._okf_match("karma", limit=1)
    assert shared.encode.called


def test_extract_okf_wikilinks():
    """Verify regex extraction of Obsidian/Anthropic-style [[wikilinks]]."""
    from rag.nodes.retrieval import extract_okf_wikilinks

    assert extract_okf_wikilinks("") == []
    assert extract_okf_wikilinks("No links here.") == []

    text = """
    ## Related Concepts
    - **Beautiful State** ([[sri-preethaji/beautiful_state]]): Core teaching.
    - **Serene Mind** ([[sri-krishnaji/serene_mind_practice|Serene Mind]]): Daily practice.
    - Duplicated: [[sri-preethaji/beautiful_state]]
    """
    links = extract_okf_wikilinks(text)
    assert links == ["sri-preethaji/beautiful_state", "sri-krishnaji/serene_mind_practice"]


def test_traverse_okf_wikilinks(monkeypatch):
    """Verify 1-hop traversal across OKF knowledge wiki links."""
    from rag.nodes.retrieval import traverse_okf_wikilinks

    mock_entries = [
        {
            "path": "memory/okf/sri-preethaji/beautiful_state.md",
            "title": "Beautiful State",
            "body": "Teaching on beautiful state. See also [[shared/the_truth_of_suffering]].",
            "resource": "https://youtube.com/watch?v=111",
            "teacher": "sri-preethaji",
            "type": "teaching",
        },
        {
            "path": "memory/okf/shared/the_truth_of_suffering.md",
            "title": "Truth of Suffering",
            "body": "Understanding suffering. Connected to [[sri-preethaji/beautiful_state]].",
            "resource": "https://youtube.com/watch?v=222",
            "teacher": "both",
            "type": "teaching",
        },
    ]
    monkeypatch.setattr(retrieval_mod, "_OKF_CACHE", mock_entries)

    parent_doc = {
        "title": "Beautiful State",
        "score": 0.85,
        "metadata": {
            "related_concepts": ["shared/the_truth_of_suffering"],
            "wiki_id": "beautiful_state",
        },
    }

    # Query asks about suffering
    expanded = traverse_okf_wikilinks(
        matched_docs=[parent_doc],
        query="How does the beautiful state help overcome suffering?",
        max_expanded_docs=2,
    )

    assert len(expanded) == 1
    exp = expanded[0]
    assert exp["title"] == "Truth of Suffering"
    assert exp["knowledge_source"] == "okf_wikilink_traversal"
    assert exp["metadata"]["traversed_from"] == "Beautiful State"
    assert exp["metadata"]["related_concepts"] == ["sri-preethaji/beautiful_state"]
    assert exp["score"] > 0.75


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-q"]))
