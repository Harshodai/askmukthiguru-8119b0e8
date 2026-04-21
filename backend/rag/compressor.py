"""
Mukthi Guru — Contextual Compression

Compresses retrieved documents by extracting only the most relevant
sentences using the CrossEncoder reranker. This concentrates the context
on precisely the evidence that addresses the user's question.

No extra model needed — reuses the existing CrossEncoder from EmbeddingService.
Runs in ~50ms for 40-50 sentences.
"""

import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)

# Minimum score threshold for a sentence to be considered relevant
_SENTENCE_THRESHOLD = 0.3


def _split_into_sentences(text: str) -> list[str]:
    """Split text into sentences using regex-based boundary detection."""
    # Split on sentence-ending punctuation followed by space or newline
    sentences = re.split(r'(?<=[.!?])\s+', text.strip())
    # Filter out very short fragments
    return [s.strip() for s in sentences if len(s.strip()) > 20]


def compress_documents(
    query: str,
    documents: list[dict],
    reranker,
    threshold: float = _SENTENCE_THRESHOLD,
    min_sentences: int = 2,
) -> list[dict]:
    """
    Compress documents by extracting only relevant sentences.

    For each document:
    1. Split into sentences
    2. Score each sentence against the query using the CrossEncoder
    3. Keep only sentences above the threshold
    4. Reassemble the compressed document

    Args:
        query: The user's question
        documents: List of document dicts with 'text' key
        reranker: CrossEncoder model (from EmbeddingService)
        threshold: Minimum relevance score for a sentence
        min_sentences: Keep at least this many sentences per doc

    Returns:
        List of compressed document dicts (same structure, shorter text)
    """
    if not documents:
        return []

    compressed = []
    total_original = 0
    total_compressed = 0

    for doc in documents:
        text = doc.get("text", "")
        sentences = _split_into_sentences(text)

        if len(sentences) <= min_sentences:
            # Too few sentences to compress — keep as-is
            compressed.append(doc)
            continue

        total_original += len(text)

        # Score each sentence against the query
        pairs = [(query, sent) for sent in sentences]
        try:
            scores = reranker.predict(pairs)
        except Exception as e:
            logger.warning(f"Compression scoring failed: {e}")
            compressed.append(doc)
            continue

        # Sort sentences by score and keep those above threshold
        scored = sorted(
            zip(sentences, scores),
            key=lambda x: x[1],
            reverse=True,
        )

        # Keep sentences above threshold, but ensure minimum count
        relevant = [s for s, score in scored if score >= threshold]
        if len(relevant) < min_sentences:
            relevant = [s for s, _ in scored[:min_sentences]]

        # Reconstruct in original order
        original_order = [
            s for s in sentences if s in relevant
        ]

        compressed_text = " ".join(original_order)
        total_compressed += len(compressed_text)

        compressed_doc = {**doc, "text": compressed_text}
        compressed.append(compressed_doc)

    if total_original > 0:
        ratio = total_compressed / total_original
        logger.info(
            f"Contextual compression: {total_original} → {total_compressed} chars "
            f"({ratio:.0%} of original)"
        )

    return compressed
