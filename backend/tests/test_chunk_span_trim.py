"""Wave R-C — chunk-span trimming pre-fusion (Vespa/Perplexity steal).

Covers ``rag.nodes.retrieval._trim_chunk_spans``: over-long chunks are cut
to the query-relevant sentence span BEFORE fusion/rerank, short chunks pass
through byte-identical. Pure heuristics — no Qdrant, no LLM, no embeddings.
"""

from __future__ import annotations

import pytest

from rag.nodes.retrieval import _ADAPTIVE_PARENT_THRESHOLD, _trim_chunk_spans


def _long_chunk(keyword: str, filler_sentences: int = 60) -> str:
    filler = " ".join(
        f"The rivers flow gently through the quiet valley number {i}."
        for i in range(filler_sentences)
    )
    return (
        f"{filler} The seeker asks about stillness and meditation practice every day. "
        f"{keyword} " + filler
    )


def test_short_chunks_pass_through_byte_identical():
    """Served-text invariant: chunks under the threshold are untouched."""
    docs = [
        {"text": "What is the Beautiful State?", "score": 0.9},
        {"text": "A short teaching on breath awareness.", "score": 0.8},
    ]
    before = [dict(d) for d in docs]
    assert _trim_chunk_spans("What is the Beautiful State?", docs) == 0
    assert docs == before


def test_empty_and_missing_text_are_noops():
    assert _trim_chunk_spans("anything", []) == 0
    docs = [{"score": 0.5}, {"text": "", "score": 0.4}]
    assert _trim_chunk_spans("anything", docs) == 0
    assert docs == [{"score": 0.5}, {"text": "", "score": 0.4}]


def test_long_chunk_trimmed_to_query_span():
    """Over-long chunk is cut and keeps the query-relevant sentences."""
    text = _long_chunk("Beautiful State consciousness awakening.")
    assert len(text) > _ADAPTIVE_PARENT_THRESHOLD
    docs = [{"text": text, "score": 0.7, "source_url": "https://example.com/v?q=1"}]
    assert _trim_chunk_spans("What is the Beautiful State?", docs) == 1
    trimmed = docs[0]["text"]
    assert len(trimmed) < len(text)
    assert "Beautiful State" in trimmed
    # Non-text keys survive the trim.
    assert docs[0]["score"] == 0.7
    assert docs[0]["source_url"] == "https://example.com/v?q=1"


def test_trim_keeps_query_keywords_not_padding():
    """The kept window is query-anchored, not a head cut."""
    head = " ".join(f"Unrelated valley river sentence {i}." for i in range(80))
    tail = (
        "Meditation stillness practice quiets the restless mind completely. "
        "Awareness of breath brings the seeker home to presence."
    )
    text = head + " " + tail
    assert len(text) > _ADAPTIVE_PARENT_THRESHOLD
    docs = [{"text": text}]
    _trim_chunk_spans("How do I practice meditation stillness?", docs)
    assert "Meditation stillness" in docs[0]["text"]


def test_mixed_batch_trims_only_long_docs():
    short = {"text": "Brief teaching.", "score": 0.9}
    long_doc = {"text": _long_chunk("Beautiful State awakening stillness."), "score": 0.6}
    original_long = long_doc["text"]
    docs = [short, long_doc]
    assert _trim_chunk_spans("Tell me about the Beautiful State.", docs) == 1
    assert docs[0] == short
    assert len(docs[1]["text"]) < len(original_long)
    assert "Beautiful State" in docs[1]["text"]


if __name__ == "__main__":
    import sys

    sys.exit(pytest.main([__file__, "-v"]))
