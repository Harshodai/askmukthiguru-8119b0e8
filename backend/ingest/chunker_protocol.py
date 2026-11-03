"""Unified Chunker Protocol and Adapters (DE-1.1).

Defines the core Chunk dataclass, Chunker Protocol, concrete adapters:
  - BoundaryChunkerAdapter (boundary_v1:<target_size>/<overlap_sentences>)
  - AdaptiveChunkerAdapter (adaptive_v1)
  - SemanticChunkerAdapter (semantic_v1)
  - RecursiveChunkerAdapter (recursive_v1:<chunk_size>/<chunk_overlap>)
and the get_chunker() factory helper.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from app.config import settings

logger = logging.getLogger(__name__)


@dataclass
class Chunk:
    """A discrete text chunk with indexing provenance."""

    text: str
    parent_index: int
    chunker_version: str
    spans: list[tuple[int, int]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class Chunker(Protocol):
    """Unified Protocol for text splitting strategies."""

    def chunk(self, text: str, *, parent_index: int = 0, **kwargs: Any) -> list[Chunk]:
        """Split text into Chunk objects with metadata and provenance."""
        ...


class BoundaryChunkerAdapter:
    """Adapter wrapping BoundaryChunker to conform to Chunker Protocol."""

    def __init__(
        self,
        target_size: int = 1200,
        overlap_sentences: int = 1,
        max_size: int = 1500,
        min_size: int = 80,
        **kwargs: Any,
    ) -> None:
        from ingest.boundary_chunker import BoundaryChunker

        self.target_size = target_size
        self.overlap_sentences = overlap_sentences
        self.max_size = max_size
        self.min_size = min_size
        self.chunker_version = f"boundary_v1:{target_size}/{overlap_sentences}"
        self._chunker = BoundaryChunker(
            target_size=target_size,
            overlap_sentences=overlap_sentences,
            max_size=max_size,
            min_size=min_size,
        )

    def chunk(self, text: str, *, parent_index: int = 0, **kwargs: Any) -> list[Chunk]:
        if not text or not text.strip():
            return []
        raw_chunks, bounds = self._chunker.chunk_with_spans(text)
        out: list[Chunk] = []
        meta = kwargs.get("metadata", {})
        for i, c in enumerate(raw_chunks):
            spans = [(bounds[i].start, bounds[i].end)] if i < len(bounds) else []
            out.append(
                Chunk(
                    text=c,
                    parent_index=parent_index,
                    chunker_version=self.chunker_version,
                    spans=spans,
                    metadata=meta.copy(),
                )
            )
        return out


class AdaptiveChunkerAdapter:
    """Adapter wrapping AdaptiveChunker to conform to Chunker Protocol."""

    def __init__(
        self,
        embedding_service: Any = None,
        chunk_size: int | None = None,
        chunk_overlap: int | None = None,
        min_chunk_chars: int = 200,
        max_chunk_chars: int = 1600,
        sample_chars: int = 8000,
        **kwargs: Any,
    ) -> None:
        from ingest.adaptive_chunking import AdaptiveChunker

        self._embedder = embedding_service
        self.chunk_size = chunk_size or getattr(settings, "rag_chunk_size", 1200)
        self.chunk_overlap = chunk_overlap or getattr(settings, "rag_chunk_overlap", 200)
        self.chunker_version = "adaptive_v1"
        self._chunker = AdaptiveChunker(
            embedding_service=self._embedder,
            chunk_size=self.chunk_size,
            chunk_overlap=self.chunk_overlap,
            min_chunk_chars=min_chunk_chars,
            max_chunk_chars=max_chunk_chars,
            sample_chars=sample_chars,
        )

    def chunk(self, text: str, *, parent_index: int = 0, **kwargs: Any) -> list[Chunk]:
        if not text or not text.strip():
            return []
        texts = self._chunker.chunk_document(text)
        meta = kwargs.get("metadata", {})
        return [
            Chunk(
                text=t,
                parent_index=parent_index,
                chunker_version=self.chunker_version,
                spans=[],
                metadata=meta.copy(),
            )
            for t in texts
        ]


class SemanticChunkerAdapter:
    """Adapter wrapping SemanticChunker to conform to Chunker Protocol."""

    def __init__(
        self,
        embedding_service: Any = None,
        min_chunk_chars: int = 300,
        max_chunk_chars: int = 1800,
        distance_percentile_threshold: float = 85.0,
        **kwargs: Any,
    ) -> None:
        from ingest.semantic_chunker import SemanticChunker

        self._embedder = embedding_service
        self.chunker_version = "semantic_v1"
        self._chunker = SemanticChunker(
            embedding_service=self._embedder,
            min_chunk_chars=min_chunk_chars,
            max_chunk_chars=max_chunk_chars,
            distance_percentile_threshold=distance_percentile_threshold,
        )

    def chunk(self, text: str, *, parent_index: int = 0, **kwargs: Any) -> list[Chunk]:
        if not text or not text.strip():
            return []
        texts = self._chunker.split(text)
        meta = kwargs.get("metadata", {})
        return [
            Chunk(
                text=t,
                parent_index=parent_index,
                chunker_version=self.chunker_version,
                spans=[],
                metadata=meta.copy(),
            )
            for t in texts
        ]


class RecursiveChunkerAdapter:
    """Adapter wrapping RecursiveCharacterTextSplitter to conform to Chunker Protocol."""

    def __init__(
        self,
        chunk_size: int = 1200,
        chunk_overlap: int = 200,
        separators: list[str] | None = None,
        **kwargs: Any,
    ) -> None:
        from langchain_text_splitters import RecursiveCharacterTextSplitter

        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.chunker_version = f"recursive_v1:{chunk_size}/{chunk_overlap}"
        self._splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            separators=separators or ["\n\n", "\n", ". ", " ", ""],
        )

    def chunk(self, text: str, *, parent_index: int = 0, **kwargs: Any) -> list[Chunk]:
        if not text or not text.strip():
            return []
        texts = self._splitter.split_text(text)
        meta = kwargs.get("metadata", {})
        return [
            Chunk(
                text=t,
                parent_index=parent_index,
                chunker_version=self.chunker_version,
                spans=[],
                metadata=meta.copy(),
            )
            for t in texts
        ]


def get_chunker(strategy: str = "boundary", **kwargs: Any) -> Chunker:
    """Factory helper to instantiate a Chunker adapter by strategy name."""
    strat = (strategy or "boundary").lower().strip()
    if strat in ("boundary", "boundary_v1", "boundary_chunker"):
        return BoundaryChunkerAdapter(**kwargs)
    if strat in ("adaptive", "adaptive_v1", "adaptive_chunker"):
        return AdaptiveChunkerAdapter(**kwargs)
    if strat in ("semantic", "semantic_v1", "semantic_chunker"):
        return SemanticChunkerAdapter(**kwargs)
    if strat in ("recursive", "recursive_v1", "recursive_chunker"):
        return RecursiveChunkerAdapter(**kwargs)
    if getattr(settings, "chunker_contract_strict", False):
        raise ValueError(f"Unknown or unsupported chunker strategy: {strategy!r}")
    return BoundaryChunkerAdapter(**kwargs)
