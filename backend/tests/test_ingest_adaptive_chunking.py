from unittest.mock import MagicMock

import numpy as np
import pytest

from app.config import settings
from ingest.adaptive_chunking import AdaptiveChunker


@pytest.fixture
def mock_embedder():
    """Deterministic embedder that returns unique unit vectors per input text."""
    embedder = MagicMock()

    def fake_encode(texts):
        dim = 8
        out = []
        for i, text in enumerate(texts):
            vec = np.zeros(dim, dtype=np.float32)
            vec[i % dim] = 1.0
            out.append(vec)
        return np.asarray(out, dtype=np.float32)

    embedder.encode.side_effect = fake_encode
    return embedder


@pytest.fixture
def chunker(mock_embedder, monkeypatch):
    monkeypatch.setattr(settings, "use_adaptive_chunking", True)
    monkeypatch.setattr(settings, "adaptive_chunking_min_chars", 5000)
    return AdaptiveChunker(
        embedding_service=mock_embedder,
        chunk_size=400,
        chunk_overlap=50,
        min_chunk_chars=200,
        max_chunk_chars=1600,
        sample_chars=8000,
    )


def test_chunk_document_empty_string(chunker):
    assert chunker.chunk_document("") == []
    assert chunker.chunk_document("   ") == []


def test_chunk_document_short_text_fallback(chunker):
    text = "This is a short document. It has two sentences."
    result = chunker.chunk_document(text)
    assert result
    assert " ".join(result) == text


def test_chunk_document_disabled_setting(chunker, monkeypatch):
    monkeypatch.setattr(settings, "use_adaptive_chunking", False)
    text = "Sentence one. " * 600
    result = chunker.chunk_document(text)
    assert result
    assert all(len(chunk) <= settings.rag_chunk_size for chunk in result)


def test_split_sentences(chunker):
    text = "First sentence. Second sentence! Third? And fourth."
    sentences = chunker._split_sentences(text)
    assert sentences == [
        "First sentence.",
        "Second sentence!",
        "Third?",
        "And fourth.",
    ]


def test_merge_tiny_chunks(chunker):
    # Design: first pair merges (<250), second pair merges (<250), pair boundary splits.
    chunks = [
        "This is a tiny chunk.",  # 22 chars
        "X" * 200,  # combined with first chunk = 222 < 250, merges
        "Y" * 240,  # combined with previous merged = 222 + 240 = 462 >= 250, splits
        "Small.",   # combined with Y chunk = 247 < 250, merges
    ]
    merged = chunker._merge_tiny_chunks(chunks, min_chars=250)
    assert len(merged) == 2
    assert merged[0] == chunks[0] + " " + chunks[1]
    assert merged[1] == chunks[2] + " " + chunks[3]


def test_pick_best_selects_highest_score(chunker, monkeypatch):
    scores = {"chunk a": 0.5, "chunk b1": 0.9, "chunk c": 0.7}

    def fake_score(chunks, _text):
        return scores.get(chunks[0], 0.0)

    monkeypatch.setattr(chunker, "_score", fake_score)
    candidates = {
        "a": ["chunk a"],
        "b": ["chunk b1", "chunk b2"],
        "c": ["chunk c"],
    }
    best_name, best_chunks = chunker._pick_best(candidates, "irrelevant")
    assert best_name == "b"
    assert best_chunks == candidates["b"]


def test_chunk_document_applies_winning_strategy(chunker, monkeypatch):
    text = "Sentence one. " * 600
    monkeypatch.setattr(chunker, "_pick_best", lambda _candidates, _sample: ("recursive_small", []))
    apply_spy = MagicMock(side_effect=chunker._apply_strategy)
    monkeypatch.setattr(chunker, "_apply_strategy", apply_spy)
    chunker.chunk_document(text)
    assert apply_spy.call_count == 1
    assert apply_spy.call_args[0][0] == "recursive_small"
