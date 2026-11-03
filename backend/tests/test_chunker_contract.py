"""Tests for Unified Chunker Protocol and Adapters (DE-1.1).

Verifies:
  - Unified Chunker protocol implementation across Boundary, Adaptive,
    Semantic, and Recursive adapters
  - Valid chunker_version strings stamped on each Chunk
  - Chunker Protocol runtime checkability
  - get_chunker factory strategy dispatch
"""

from __future__ import annotations

import pytest

from app.config import settings
from ingest.chunker_protocol import (
    AdaptiveChunkerAdapter,
    BoundaryChunkerAdapter,
    Chunk,
    Chunker,
    RecursiveChunkerAdapter,
    SemanticChunkerAdapter,
    get_chunker,
)

SAMPLE_TEXT = (
    "In stillness, the mind naturally settles into awareness. "
    "When you observe thoughts without judgment, inner freedom arises. "
    "Every disturbance carries a hidden invitation to awaken to truth. "
    "Peace is not something you acquire; it is what remains when resistance ends."
)


def test_chunker_protocol_runtime_checking():
    boundary = BoundaryChunkerAdapter()
    recursive = RecursiveChunkerAdapter()
    adaptive = AdaptiveChunkerAdapter()
    semantic = SemanticChunkerAdapter()

    assert isinstance(boundary, Chunker)
    assert isinstance(recursive, Chunker)
    assert isinstance(adaptive, Chunker)
    assert isinstance(semantic, Chunker)


def test_boundary_chunker_adapter_contract():
    chunker = get_chunker("boundary", target_size=1200, overlap_sentences=1)
    assert isinstance(chunker, BoundaryChunkerAdapter)
    assert chunker.chunker_version == "boundary_v1:1200/1"

    chunks = chunker.chunk(SAMPLE_TEXT, parent_index=3, metadata={"source": "test"})
    assert len(chunks) > 0
    for c in chunks:
        assert isinstance(c, Chunk)
        assert c.parent_index == 3
        assert c.chunker_version == "boundary_v1:1200/1"
        assert len(c.text) > 0
        assert c.metadata.get("source") == "test"
        assert isinstance(c.spans, list)


def test_recursive_chunker_adapter_contract():
    chunker = get_chunker("recursive", chunk_size=800, chunk_overlap=100)
    assert isinstance(chunker, RecursiveChunkerAdapter)
    assert chunker.chunker_version == "recursive_v1:800/100"

    chunks = chunker.chunk(SAMPLE_TEXT, parent_index=1)
    assert len(chunks) > 0
    for c in chunks:
        assert isinstance(c, Chunk)
        assert c.parent_index == 1
        assert c.chunker_version == "recursive_v1:800/100"
        assert len(c.text) > 0


def test_adaptive_chunker_adapter_contract():
    chunker = get_chunker("adaptive")
    assert isinstance(chunker, AdaptiveChunkerAdapter)
    assert chunker.chunker_version == "adaptive_v1"

    chunks = chunker.chunk(SAMPLE_TEXT, parent_index=2)
    assert len(chunks) > 0
    for c in chunks:
        assert isinstance(c, Chunk)
        assert c.parent_index == 2
        assert c.chunker_version == "adaptive_v1"
        assert len(c.text) > 0


def test_semantic_chunker_adapter_contract():
    chunker = get_chunker("semantic")
    assert isinstance(chunker, SemanticChunkerAdapter)
    assert chunker.chunker_version == "semantic_v1"

    chunks = chunker.chunk(SAMPLE_TEXT, parent_index=0)
    assert len(chunks) > 0
    for c in chunks:
        assert isinstance(c, Chunk)
        assert c.parent_index == 0
        assert c.chunker_version == "semantic_v1"
        assert len(c.text) > 0


def test_chunker_factory_strict_mode(monkeypatch):
    monkeypatch.setattr(settings, "chunker_contract_strict", True)
    with pytest.raises(ValueError, match="Unknown or unsupported chunker strategy"):
        get_chunker("invalid_nonexistent_chunker")


def test_empty_text_returns_empty_chunks():
    for strat in ("boundary", "adaptive", "semantic", "recursive"):
        chunker = get_chunker(strat)
        assert chunker.chunk("") == []
        assert chunker.chunk("   ") == []
