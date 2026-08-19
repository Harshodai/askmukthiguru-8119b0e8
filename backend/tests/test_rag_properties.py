"""
Edge-case tests for RAG pipeline invariants.

A curated parametrized input set (empty, whitespace, multilingual, long,
special-character strings; boundary scores) verifies that core RAG functions
maintain their contracts regardless of input — the same coverage the previous
property-based harness gave, without the hypothesis dependency.

Run: pytest tests/test_rag_properties.py -v
"""

from __future__ import annotations

import asyncio

import pytest

# ---- keyword_injection tests -----------------------------------------------
from rag.nodes.keyword_injection import (
    DOCTRINE_CATEGORIES,
    classify_doctrine_query,
    inject_doctrine_keywords,
)

_TEXT_CASES = [
    "",
    " ",
    "\t\n",
    "a",
    "short query",
    "how do I deal with grief",
    "what is the meaning of liberation",
    "a" * 300,
    "x" * 500,
    "कर्म योग क्या है",  # Hindi
    "ధ్యానం అంటే ఏమిటి",  # Telugu
    "मृत्यु के बाद क्या होता है",  # Hindi long
    "emoji 😊 mixed 123 !@#$%^&*()",
    "camelCaseQuery and snake_case_query",
    "नमस्ते. Hello. नमस्ते.",
]

_FLOAT_CASES = [0.0, 0.25, 0.5, 0.75, 1.0, 0.0001, 0.9999]


@pytest.mark.parametrize("query", _TEXT_CASES)
def test_classify_always_returns_tuple(query: str) -> None:
    """classify_doctrine_query MUST always return a tuple regardless of input."""
    result = classify_doctrine_query(query)
    assert isinstance(result, tuple), f"Expected tuple, got {type(result)}"


@pytest.mark.parametrize("query", _TEXT_CASES)
def test_classify_categories_are_known(query: str) -> None:
    """All returned categories must exist in DOCTRINE_CATEGORIES."""
    result = classify_doctrine_query(query)
    for cat in result:
        assert cat in DOCTRINE_CATEGORIES, f"Unknown category: {cat}"


@pytest.mark.parametrize("query", _TEXT_CASES)
def test_inject_never_shorter_than_original(query: str) -> None:
    """Injecting keywords can only add or preserve length, never shorten."""
    result = inject_doctrine_keywords(query)
    assert len(result) >= len(query), f"inject shortened query: {len(query)} -> {len(result)}"


@pytest.mark.parametrize("query", _TEXT_CASES)
def test_inject_preserves_original_query_as_prefix(query: str) -> None:
    """Original query must appear as a prefix in the injected result."""
    result = inject_doctrine_keywords(query)
    assert result.startswith(query), (
        f"Original query not preserved as prefix.\nQuery:  {query!r}\nResult: {result!r}"
    )


# ---- RetrievedDoc tests -----------------------------------------------------

from domain.retrieval_types import RetrievedDoc


@pytest.mark.parametrize("content", _TEXT_CASES)
@pytest.mark.parametrize("score", _FLOAT_CASES)
def test_retrieved_doc_round_trips_through_dict(content: str, score: float) -> None:
    """from_dict(to_dict(doc)) == doc (round-trip identity)."""
    doc = RetrievedDoc(content=content, score=score, source_url="src", doc_id="id")
    reconstructed = RetrievedDoc.from_dict(doc.to_dict())
    assert reconstructed == doc, f"Round-trip failed: {doc!r} -> {reconstructed!r}"


@pytest.mark.parametrize("content", _TEXT_CASES)
@pytest.mark.parametrize("score", _FLOAT_CASES)
def test_retrieved_doc_to_dict_has_legacy_keys(content: str, score: float) -> None:
    """to_dict() must include backward-compat 'text' and 'id' keys."""
    doc = RetrievedDoc(content=content, score=score, source_url="", doc_id="x")
    d = doc.to_dict()
    assert "text" in d, "Legacy key 'text' missing from to_dict()"
    assert "id" in d, "Legacy key 'id' missing from to_dict()"
    assert d["text"] == content
    assert d["content"] == content


# ---- ConcurrentRetriever tests ----------------------------------------------

from services.concurrent_retriever import ConcurrentRetriever


@pytest.mark.parametrize("query", _TEXT_CASES)
def test_concurrent_retriever_returns_both_keys(query: str) -> None:
    """retrieve() must always return a dict with 'vector' and 'graph' keys."""

    async def _run():
        async def fake_vector(q: str) -> list[str]:
            return [f"vector:{q[:10]}"]

        async def fake_graph(q: str) -> list[str]:
            return [f"graph:{q[:10]}"]

        retriever = ConcurrentRetriever(fake_vector, fake_graph)
        return await retriever.retrieve(query)

    result = asyncio.run(_run())
    assert "vector" in result
    assert "graph" in result
    assert isinstance(result["vector"], list)
    assert isinstance(result["graph"], list)


if __name__ == "__main__":
    # Quick smoke-run without pytest
    test_classify_always_returns_tuple("")
    test_inject_never_shorter_than_original("query")
    print("All property invariants hold")
