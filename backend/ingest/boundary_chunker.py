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


def _slice_on_word_boundary(text: str, max_size: int) -> list[str]:
    """Slice ``text`` into pieces of at most ``max_size`` chars, preferring to
    break at whitespace rather than mid-word.

    Used for punctuation-free runs (raw OCR/ASR text) where sentence/word
    splitting can't rely on punctuation. Looks back up to 50 chars from the
    hard cut point for the nearest space; falls back to a raw character cut
    only when no whitespace is found in that window (still guarantees every
    piece is <= max_size — this only ever moves the cut point EARLIER).
    """
    if len(text) <= max_size:
        return [text]

    pieces: list[str] = []
    i = 0
    n = len(text)
    lookback_window = 50
    while i < n:
        end = min(i + max_size, n)
        if end < n:
            lookback_start = max(i, end - lookback_window)
            space_at = text.rfind(" ", lookback_start, end)
            if space_at > i:
                end = space_at + 1
        pieces.append(text[i:end])
        i = end
    return pieces


# Abbreviations whose periods should not be treated as sentence terminators.
# Mixed case is handled by case-insensitive regex.
_ABBREVIATIONS = {
    "mr.",
    "mrs.",
    "ms.",
    "dr.",
    "prof.",
    "sr.",
    "jr.",
    "e.g.",
    "i.e.",
    "vs.",
    "etc.",
    "viz.",
    "inc.",
    "ltd.",
    "a.m.",
    "p.m.",
    "approx.",
    "ca.",
    "co.",
    "no.",
    "fig.",
    "et al.",
    "hon.",
    "st.",
    "ave.",
    "blvd.",
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
        sentences_by_paragraph = [self._split_sentences(p.strip()) for p in paragraphs if p.strip()]

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

        for _idx, (sentence, sent_len, is_para_start) in enumerate(sentences):
            # A sentence that is itself longer than max_size must be sliced into
            # pieces before accumulation, otherwise a single append can exceed
            # the hard limit and a later flush will never recover.
            if sent_len > self.max_size:
                slices = self._split_long_sentence(sentence)
                for piece in slices:
                    piece_len = len(piece)
                    # Flush current accumulation if adding this piece would cross max_size.
                    # Long-sentence pieces are not eligible for overlap; carrying overlap
                    # from prior sentences is safe because those pieces are already <= max_size.
                    if (
                        current_len
                        and current_len + piece_len + (1 if current_len else 0) > self.max_size
                    ):
                        self._flush_chunk(
                            current_sentences,
                            current_len,
                            current_offset,
                            chunks,
                            bounds,
                        )
                        current_sentences = []
                        current_len = 0
                        current_offset = bounds[-1].end if bounds else current_offset

                    current_sentences.append(piece)
                    current_len += piece_len + (1 if current_len else 0)

                    if current_len >= self.max_size:
                        self._flush_chunk(
                            current_sentences,
                            current_len,
                            current_offset,
                            chunks,
                            bounds,
                        )
                        current_sentences = []
                        current_len = 0
                        current_offset = bounds[-1].end if bounds else current_offset
                continue

            # Flush before adding a normal sentence if it would push us over max_size.
            # This prevents joining a just-flushed max_size chunk with its overlap
            # and the next sentence into an oversized result.
            if current_len and current_len + sent_len + (1 if current_len else 0) > self.max_size:
                self._flush_chunk(
                    current_sentences,
                    current_len,
                    current_offset,
                    chunks,
                    bounds,
                )
                current_sentences, current_len, current_offset = self._carry_overlap(
                    current_sentences, bounds
                )

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
                current_sentences, current_len, current_offset = self._carry_overlap(
                    current_sentences, bounds
                )

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
                current_sentences, current_len, current_offset = self._carry_overlap(
                    current_sentences, bounds
                )

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
        logger.debug(f"BoundaryChunker: {len(merged)} chunks from {len(sentences)} sentences")
        return merged

    @staticmethod
    def _split_paragraphs(text: str) -> list[str]:
        """Split text on paragraph boundaries (blank lines)."""
        return re.split(r"\n\s*\n", text)

    def _split_sentences(self, text: str) -> list[str]:
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
            sentence = part.replace("__DOT__", ".").replace("__COMMA__", ",").strip()
            if sentence:
                sentences.extend(self._split_oversized_fallback(sentence))

        return sentences

    def _split_oversized_fallback(self, sentence: str) -> list[str]:
        """
        A "sentence" with no punctuation to split on (raw OCR/ASR text, run-on
        transcript) can be arbitrarily long and would otherwise become a single
        oversized chunk. Fall back to word-boundary-aware slicing so every
        produced piece is <= max_size.
        """
        return _slice_on_word_boundary(sentence, self.max_size)

    def _carry_overlap(
        self, current_sentences: list[str], bounds: list[ChunkBounds]
    ) -> tuple[list[str], int, int]:
        """Carry the last `overlap_sentences` into the next chunk, bounded.

        The raw `current_sentences[-overlap_sentences:]` slice was never
        checked against max_size -- if overlap sentences happen to be large,
        the very next append (before this new chunk's own max_size check
        fires) can push the chunk over the limit. Drops overlap sentences
        from the front of the carried slice, one at a time, until what's
        carried leaves at least half of max_size free for the next sentence.
        """
        just_flushed = bounds[-1] if bounds else None
        overlap = (
            list(current_sentences[-self.overlap_sentences :]) if self.overlap_sentences else []
        )
        budget = self.max_size // 2
        while overlap and (sum(len(s) for s in overlap) + len(overlap) - 1) > budget:
            overlap.pop(0)
        current_len = sum(len(s) for s in overlap) + (len(overlap) - 1 if overlap else 0)
        current_offset = (
            just_flushed.start + len(" ".join(overlap))
            if overlap and just_flushed
            else (just_flushed.start if just_flushed else 0)
        )
        return overlap, current_len, current_offset

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

    def _merge_small_chunks(self, chunks: list[str], bounds: list[ChunkBounds]) -> list[str]:
        """Merge trailing chunks that are shorter than min_size into the previous chunk."""
        if not chunks or len(chunks) < 2:
            return chunks

        merged: list[str] = [chunks[0]]
        for chunk in chunks[1:]:
            if len(chunk) < self.min_size and len(merged[-1]) + len(chunk) + 1 <= self.max_size:
                merged[-1] = merged[-1] + " " + chunk
            else:
                merged.append(chunk)
        return merged

    def _split_long_sentence(self, sentence: str) -> list[str]:
        """Slice a sentence longer than max_size into <=max_size pieces, preferring
        word boundaries (production-audit finding F1: raw character slicing could
        split an entity/doctrine-term reference mid-word with no overlap to
        recover it, breaking LightRAG's per-chunk entity extraction)."""
        return _slice_on_word_boundary(sentence, self.max_size)


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
