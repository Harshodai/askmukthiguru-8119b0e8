"""Tests for the word-containment citation extractor.

_span_overlap replaced _jaccard in the F2 attribution fix (2026-09-16).
The function changed from n-gram Jaccard (union-based) to word-level
containment (sentence words found in doc text) because Jaccard's mathematical
ceiling prevented correct citations from passing the threshold on long chunks.
"""

from __future__ import annotations

import pytest

from rag.nodes.citation_extractor import _span_overlap, extract_citations


@pytest.mark.unit
def test_span_overlap_identical() -> None:
    # All sentence words appear in doc_text → 1.0
    assert _span_overlap("hello world test", "hello world test") == 1.0


@pytest.mark.unit
def test_span_overlap_disjoint() -> None:
    # No sentence content words (>2 chars, not stopwords) appear in doc → 0.0
    assert _span_overlap("elephant giraffe", "monday tuesday") == 0.0


@pytest.mark.unit
def test_span_overlap_empty_sentence() -> None:
    # Empty sentence → 0.0 (no content words to match)
    assert _span_overlap("", "test document") == 0.0


@pytest.mark.unit
def test_with_no_docs_returns_empty() -> None:
    state = {"answer": "Some answer.", "relevant_docs": []}
    result = extract_citations(state)
    assert result["citations"] == []


@pytest.mark.unit
def test_with_no_answer_returns_empty() -> None:
    state = {"answer": "", "relevant_docs": [{"text": "doc", "metadata": {}}]}
    result = extract_citations(state)
    assert result["citations"] == []


@pytest.mark.unit
def test_extracts_best_matching_doc() -> None:
    state = {
        "answer": "The beautiful state is a state of connection and joy.",
        "relevant_docs": [
            {
                "text": "The beautiful state is connection, joy, love.",
                "metadata": {"source": "okf"},
            },
            {
                "text": "Irrelevant document about something else entirely.",
                "metadata": {"source": "other"},
            },
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
        "relevant_docs": [
            {"text": "document about yes", "metadata": {"source": "doc"}},
        ],
    }
    result = extract_citations(state)
    assert result["citations"] == []


@pytest.mark.unit
def test_book_citation_canonicalized_to_amzn() -> None:
    from app.constants import BOOK_FOUR_SACRED_SECRETS_URL

    state = {
        "answer": "The four sacred secrets reveal the path to living in a beautiful state.",
        "relevant_docs": [
            {
                "text": "The four sacred secrets reveal the path to living in a beautiful state of inner joy and connection.",
                "url": "https://www.amazon.in/Four-Sacred-Secrets-Prosperity-Beautiful/dp/1846046319",
                "content_type": "book",
                "title": "The Four Sacred Secrets",
                "metadata": {"source_url": "https://www.amazon.in/Four-Sacred-Secrets-Prosperity-Beautiful/dp/1846046319"},
            }
        ],
    }
    result = extract_citations(state)
    citations = result["citations"]
    assert len(citations) == 1
    assert citations[0]["url"] == BOOK_FOUR_SACRED_SECRETS_URL
    assert citations[0]["source_url"] == BOOK_FOUR_SACRED_SECRETS_URL
    assert citations[0]["speaker_verified"] is True

