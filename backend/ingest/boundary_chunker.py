"""
Mukthi Guru — Boundary-Aware Text Chunker

Splits transcripts into chunks that respect paragraph and sentence boundaries.
The goal is to avoid mid-sentence breaks while keeping overlap meaningful.

Design decisions:
- First split on paragraph boundaries (two+ newlines).
- If a paragraph is still too large, split on sentence boundaries.
- Overlap is measured in whole sentences, never partial words/sentences.
- No heavy dependencies (no NLTK/SpaCy); uses lightweight regex rules.

This is an opt-in chunking strategy. The existing RecursiveCharacterTextSplitter
remains the default in IngestionPipeline.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

logger = logging.getLogger(__name__)


# Abbreviations whose periods should not be treated as sentence terminators.
# Mixed case is handled by case-insensitive regex.
_ABBREVIATIONS = {
    "mr.", "mrs.", "ms.", "dr.", "prof.", "sr.", "jr.",
    "e.g.", "i.e.", "vs.", "etc.", "viz.", "inc.", "ltd.",
    "a.m.", "p.m.", "approx.", "ca.", "co.", "no.",
    "fig.", "et al.", "hon.", "st.", "ave.", "blvd.",
}


@dataclass(frozen=True)
class ChunkBounds:
    """Character offsets for a chunk within the original text."""

    start: int
    end: int


class BoundaryChunker:
    """
    Split text into sentence-boundary-respecting chunks.

    Args:
        target_size: Target chunk length in characters.
        overlap_sentences: Number of whole sentences to overlap between chunks.
        max_size: Hard upper bound on chunk length in characters.
        min_size: Chunks shorter than this are merged with neighbors when possible.
    """

    def __init__(
        self,
        target_size: int = 1200,
        overlap_sentences: int = 1,
        max_size: int = 1500,
        min_size: int = 80,
    ) -> None:
        if target_size <= 0:
            raise ValueError("target_size must be positive")
        if overlap_sentences < 0:
            raise ValueError("overlap_sentences must be non-negative")
        if max_size < target_size:
            raise ValueError("max_size must be >= target_size")

        self.target_size = target_size
        self.overlap_sentences = overlap_sentences
        self.max_size = max_size
        self.min_size = min_size

    def chunk(self, text: str) -> list[str]:
        """Return text split into boundary-respecting chunks."""
        if not text or not text.strip():
            return []

        paragraphs = self._split_paragraphs(text)
        sentences_by_paragraph = [
            self._split_sentences(p.strip()) for p in paragraphs if p.strip()
        ]

        # Flatten while remembering paragraph breaks for natural boundaries
        sentences: list[tuple[str, int, bool]] = []
        for para_sentences in sentences_by_paragraph:
            for i, sentence in enumerate(para_sentences):
                # Mark the first sentence of each paragraph so we can prefer to break there
                is_para_start = i == 0
                sentences.append((sentence, len(sentence), is_para_start))

        if not sentences:
            return []

        chunks: list[str] = []
        bounds: list[ChunkBounds] = []
        current_sentences: list[str] = []
        current_len = 0
        current_offset = 0

        for idx, (sentence, sent_len, is_para_start) in enumerate(sentences):
            # Start a new chunk at paragraph boundaries if current chunk already meets target
            if (
                current_len >= self.target_size
                and is_para_start
                and current_len + sent_len > self.max_size
            ):
                self._flush_chunk(
                    current_sentences,
                    current_len,
                    current_offset,
                    chunks,
                    bounds,
                )
                # Carry overlap sentences into next chunk
                overlap = current_sentences[-self.overlap_sentences :] if self.overlap_sentences else []
                current_sentences = list(overlap)
                current_len = sum(len(s) for s in current_sentences)
                current_offset = bounds[-1].start + len(" ".join(overlap)) if overlap else bounds[-1].start

            current_sentences.append(sentence)
            current_len += sent_len + (1 if current_len else 0)

            # Flush when we exceed max_size or naturally at a good boundary after target
            if current_len >= self.max_size:
                self._flush_chunk(
                    current_sentences,
                    current_len,
                    current_offset,
                    chunks,
                    bounds,
                )
                overlap = current_sentences[-self.overlap_sentences :] if self.overlap_sentences else []
                current_sentences = list(overlap)
                current_len = sum(len(s) for s in current_sentences)
                current_offset = bounds[-1].start + len(" ".join(overlap)) if overlap else bounds[-1].start

        if current_sentences:
            self._flush_chunk(
                current_sentences,
                current_len,
                current_offset,
                chunks,
                bounds,
                is_last=True,
            )

        # Merge trailing tiny chunks with the previous chunk if possible
        merged = self._merge_small_chunks(chunks, bounds)
        logger.debug(
            f"BoundaryChunker: {len(merged)} chunks from {len(sentences)} sentences"
        )
        return merged

    @staticmethod
    def _split_paragraphs(text: str) -> list[str]:
        """Split text on paragraph boundaries (blank lines)."""
        return re.split(r"\n\s*\n", text)

    @classmethod
    def _split_sentences(cls, text: str) -> list[str]:
        """
        Split a paragraph into sentences while protecting abbreviations and decimals.

        Returns a list of sentence strings (including their terminating punctuation).
        """
        if not text:
            return []

        # Protect abbreviations and decimal numbers by replacing their internal punctuation
        protected = text
        for abbr in _ABBREVIATIONS:
            pattern = re.escape(abbr)
            replacement = abbr.replace(".", "__DOT__").replace(",", "__COMMA__")
            protected = re.sub(
                rf"(?i){pattern}",
                replacement,
                protected,
            )

        # Protect decimal numbers (e.g., 3.14)
        protected = re.sub(r"(\d)\.\s*(\d)", r"\1__DOT__ \2", protected)
        protected = re.sub(r"(\d),(\d{3})", r"\1__COMMA__\2", protected)

        # Split on sentence-ending punctuation followed by whitespace or end-of-string.
        # Keep the punctuation attached to the sentence.
        parts = re.split(r"(?<=[.!?])(?=\s+|$)", protected)

        sentences: list[str] = []
        for part in parts:
            sentence = (
                part.replace("__DOT__", ".")
                .replace("__COMMA__", ",")
                .strip()
            )
            if sentence:
                sentences.append(sentence)

        return sentences

    @staticmethod
    def _flush_chunk(
        sentences: list[str],
        current_len: int,
        current_offset: int,
        chunks: list[str],
        bounds: list[ChunkBounds],
        is_last: bool = False,
    ) -> None:
        """Join sentences into a chunk and record its bounds."""
        text = " ".join(sentences)
        end_offset = current_offset + current_len
        # Avoid double-counting spaces at the end
        if sentences:
            end_offset = current_offset + len(text)
        chunks.append(text)
        bounds.append(ChunkBounds(start=current_offset, end=end_offset))

    @classmethod
    def _merge_small_chunks(
        cls, chunks: list[str], bounds: list[ChunkBounds]
    ) -> list[str]:
        """Merge trailing chunks that are shorter than min_size into the previous chunk."""
        if not chunks or len(chunks) < 2:
            return chunks

        merged: list[str] = [chunks[0]]
        for chunk in chunks[1:]:
            if len(chunk) < cls._default_min_size() and len(merged[-1]) + len(chunk) + 1 <= cls._default_max_size():
                merged[-1] = merged[-1] + " " + chunk
            else:
                merged.append(chunk)
        return merged

    @classmethod
    def _default_min_size(cls) -> int:
        return 80

    @classmethod
    def _default_max_size(cls) -> int:
        return 1500


def split_text_at_boundaries(
    text: str,
    target_size: int = 1200,
    overlap_sentences: int = 1,
    max_size: int = 1500,
    min_size: int = 80,
) -> list[str]:
    """Convenience function for boundary-aware chunking."""
    chunker = BoundaryChunker(
        target_size=target_size,
        overlap_sentences=overlap_sentences,
        max_size=max_size,
        min_size=min_size,
    )
    return chunker.chunk(text)


def chunk_with_contextual_headers(
    text: str,
    title: str = "",
    speaker: str = "",
    topic: str = "",
    target_size: int = 1200,
    overlap_sentences: int = 1,
) -> list[str]:
    """
    Convenience wrapper that prepends the standard contextual header to each chunk.
    """
    chunks = split_text_at_boundaries(
        text,
        target_size=target_size,
        overlap_sentences=overlap_sentences,
    )

    header_parts = []
    if title:
        header_parts.append(f"Source: {title}")
    if speaker and speaker != "Unknown":
        header_parts.append(f"Speaker: {speaker}")
    if topic and topic != "Spiritual":
        header_parts.append(f"Topic: {topic}")

    if not header_parts:
        return chunks

    header = f"[{' | '.join(header_parts)}]\n"
    return [header + chunk for chunk in chunks]
