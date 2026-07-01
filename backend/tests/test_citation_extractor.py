"""Tests for the n-gram Jaccard citation extractor."""

from __future__ import annotations

import pytest

from rag.nodes.citation_extractor import _jaccard, extract_citations


@pytest.mark.unit
def test_jaccard_identical() -> None:
    assert _jaccard("hello world", "hello world") == 1.0


@pytest.mark.unit
def test_jaccard_disjoint() -> None:
    assert _jaccard("abc", "def") == 0.0


@pytest.mark.unit
def test_jaccard_empty() -> None:
    assert _jaccard("", "test") == 0.0


@pytest.mark.unit
def test_with_no_docs_returns_empty() -> None:
    state = {"answer": "Some answer.", "documents": []}
    result = extract_citations(state)
    assert result == {"citations": []}


@pytest.mark.unit
def test_with_no_answer_returns_empty() -> None:
    state = {"answer": "", "documents": [{"text": "doc", "metadata": {}}]}
    result = extract_citations(state)
    assert result == {"citations": []}


@pytest.mark.unit
def test_extracts_best_matching_doc() -> None:
    state = {
        "answer": "The beautiful state is a state of connection and joy.",
        "documents": [
            {"text": "The beautiful state is connection, joy, love.", "metadata": {"source": "okf"}},
            {"text": "Irrelevant document about something else entirely.", "metadata": {"source": "other"}},
        ],
    }
    result = extract_citations(state)
    citations = result["citations"]
    assert len(citations) == 1
    assert citations[0]["doc_id"] == "okf"
    assert citations[0]["confidence"] > 0.15


@pytest.mark.unit
def test_short_sentences_filtered() -> None:
    state = {
        "answer": "Yes.",
        "documents": [
            {"text": "document about yes", "metadata": {"source": "doc"}},
        ],
    }
    result = extract_citations(state)
    assert result["citations"] == []
