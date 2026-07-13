"""Citation extractor — post-graph node that maps answer spans to source docs.

Produces structured citation objects {doc_id, quote, span_in_answer, confidence}
using simple n-gram Jaccard overlap between answer sentences and retrieved docs.
Wired after generate_answer and before format_final_answer.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Optional

from rag.states import GraphState

logger = logging.getLogger(__name__)


def _jaccard(a: str, b: str, n: int = 3) -> float:
    """N-gram Jaccard similarity between two strings."""
    def _grams(s: str) -> set:
        s = s.lower()
        return {s[i:i + n] for i in range(len(s) - n + 1)} if len(s) >= n else set()
    ga = _grams(a)
    gb = _grams(b)
    if not ga or not gb:
        return 0.0
    return len(ga & gb) / len(ga | gb)


def _is_youtube_video_id_title(title: str) -> bool:
    """Check if a title is just a YouTube video ID (11 chars, alphanumeric + _ -)."""
    if not title:
        return False
    return len(title) == 11 and all(c.isalnum() or c in '_-' for c in title)


def _is_youtube_url(source: str) -> bool:
    """Check if source is a YouTube URL."""
    if not source:
        return False
    return 'youtube.com' in source.lower() or 'youtu.be' in source.lower()


def extract_citations(state: GraphState) -> dict:
    """Map answer sentences to best-matching retrieved documents."""
    answer: str = state.get("answer") or state.get("final_answer") or ""  # type: ignore
    docs: list[dict] = state.get("documents", []) or []
    if not answer or not docs:
        return {"citations": []}

    # Split answer into sentences (crude but fast)
    import re
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", answer) if len(s.strip()) > 10]

    citations: list[dict] = []
    for sent in sentences:
        best_doc: Optional[dict] = None
        best_score = 0.0
        for doc in docs:
            text = doc.get("text", "")
            score = _jaccard(sent, text[:500])
            if score > best_score:
                best_score = score
                best_doc = doc
        if best_doc and best_score > 0.15:
            meta = best_doc.get("metadata", {}) or {}
            source = meta.get("source_url") or meta.get("source", "unknown")
            title = meta.get("title", "")

            # Skip citations from YouTube videos with video ID as title (metadata extraction failed)
            if _is_youtube_url(source) and _is_youtube_video_id_title(title):
                logger.debug(f"Skipping citation from YouTube video with ID-only title: {title}")
                continue

            # For YouTube videos, also verify title relevance to answer
            # to avoid citing videos that only match on incidental word overlap
            if _is_youtube_url(source) and title:
                title_relevance = _jaccard(sent, title)
                if title_relevance < 0.05:
                    logger.debug(f"Skipping YouTube citation - title '{title}' not relevant to answer (score: {title_relevance:.3f})")
                    continue

            citations.append({
                "doc_id": meta.get("source", "unknown"),
                "quote": sent[:200],
                "span_in_answer": sent,
                "confidence": round(best_score, 3),
                "source": meta.get("source", "Retrieved document"),
            })

    logger.info("Extracted %d citations from answer", len(citations))
    return {"citations": citations}


if __name__ == "__main__":  # ponytail: self-check
    st = {
        "answer": "The beautiful state is a state of connection and joy. It can be achieved through the Serene Mind practice.",
        "documents": [
            {"text": "The beautiful state is connection, joy, love.", "metadata": {"source": "okf"}},
            {"text": "Serene Mind is a three minute practice.", "metadata": {"source": "okf2"}},
        ],
    }
    result = extract_citations(st)
    print(f"citations: {len(result['citations'])}")
    assert len(result["citations"]) == 2
    print("citation_extractor OK")
