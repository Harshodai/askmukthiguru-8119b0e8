"""
Property-based tests for RAG pipeline invariants.

Uses hypothesis to generate hundreds of random inputs and verify
that core RAG functions maintain their contracts regardless of input.

Run: pytest tests/test_rag_properties.py -v
"""

from __future__ import annotations

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

# ---- keyword_injection properties -------------------------------------------
from rag.nodes.keyword_injection import (
    DOCTRINE_CATEGORIES,
    classify_doctrine_query,
    inject_doctrine_keywords,
)


@given(st.text(min_size=0, max_size=500))
@settings(max_examples=200, suppress_health_check=[HealthCheck.too_slow])
def test_classify_always_returns_tuple(query: str) -> None:
    """classify_doctrine_query MUST always return a tuple regardless of input."""
    result = classify_doctrine_query(query)
    assert isinstance(result, tuple), f"Expected tuple, got {type(result)}"


@given(st.text(min_size=0, max_size=500))
@settings(max_examples=200, suppress_health_check=[HealthCheck.too_slow])
def test_classify_categories_are_known(query: str) -> None:
    """All returned categories must exist in DOCTRINE_CATEGORIES."""
    result = classify_doctrine_query(query)
    for cat in result:
        assert cat in DOCTRINE_CATEGORIES, f"Unknown category: {cat}"


@given(st.text(min_size=1, max_size=300))
@settings(max_examples=200, suppress_health_check=[HealthCheck.too_slow])
def test_inject_never_shorter_than_original(query: str) -> None:
    """Injecting keywords can only add or preserve length, never shorten."""
    result = inject_doctrine_keywords(query)
    assert len(result) >= len(query), (
        f"inject shortened query: {len(query)} -> {len(result)}"
    )


@given(st.text(min_size=1, max_size=300))
@settings(max_examples=200, suppress_health_check=[HealthCheck.too_slow])
def test_inject_preserves_original_query_as_prefix(query: str) -> None:
    """Original query must appear as a prefix in the injected result."""
    result = inject_doctrine_keywords(query)
    assert result.startswith(query), (
        f"Original query not preserved as prefix.\n"
        f"Query:  {query!r}\n"
        f"Result: {result!r}"
    )


# ---- RetrievedDoc properties ------------------------------------------------

from domain.retrieval_types import RetrievedDoc


@given(
    content=st.text(min_size=0, max_size=1000),
    score=st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
    source_url=st.text(min_size=0, max_size=200),
    doc_id=st.text(min_size=0, max_size=50),
)
@settings(max_examples=200, suppress_health_check=[HealthCheck.too_slow])
def test_retrieved_doc_round_trips_through_dict(
    content: str, score: float, source_url: str, doc_id: str
) -> None:
    """from_dict(to_dict(doc)) == doc (round-trip identity)."""
    doc = RetrievedDoc(
        content=content, score=score, source_url=source_url, doc_id=doc_id
    )
    reconstructed = RetrievedDoc.from_dict(doc.to_dict())
    assert reconstructed == doc, f"Round-trip failed: {doc!r} -> {reconstructed!r}"


@given(
    content=st.text(min_size=1, max_size=500),
    score=st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
)
@settings(max_examples=100)
def test_retrieved_doc_to_dict_has_legacy_keys(content: str, score: float) -> None:
    """to_dict() must include backward-compat 'text' and 'id' keys."""
    doc = RetrievedDoc(
        content=content, score=score, source_url="", doc_id="x"
    )
    d = doc.to_dict()
    assert "text" in d, "Legacy key 'text' missing from to_dict()"
    assert "id" in d, "Legacy key 'id' missing from to_dict()"
    assert d["text"] == content
    assert d["content"] == content


# ---- ConcurrentRetriever properties -----------------------------------------

import asyncio

from services.concurrent_retriever import ConcurrentRetriever


@given(st.text(min_size=1, max_size=100))
@settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
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
    test_classify_always_returns_tuple()
    test_inject_never_shorter_than_original()
    print("✅ All property invariants hold")
