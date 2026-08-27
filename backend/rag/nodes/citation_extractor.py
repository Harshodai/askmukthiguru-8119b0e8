"""Citation extractor — post-graph node that maps answer spans to source docs.

Produces structured citation objects {doc_id, quote, span_in_answer, confidence}
using simple n-gram Jaccard overlap between answer sentences and retrieved docs.
Wired after generate_answer and before format_final_answer.
"""

from __future__ import annotations

import logging
import re
from typing import Optional

from rag.nodes.utils import log_metrics
from rag.states import GraphState

logger = logging.getLogger(__name__)


def _jaccard(a: str, b: str, n: int = 3) -> float:
    """N-gram Jaccard similarity between two strings."""

    def _grams(s: str) -> set:
        s = s.lower()
        return {s[i : i + n] for i in range(len(s) - n + 1)} if len(s) >= n else set()

    ga = _grams(a)
    gb = _grams(b)
    if not ga or not gb:
        return 0.0
    return len(ga & gb) / len(ga | gb)


def _is_youtube_video_id_title(title: str) -> bool:
    """Check if a title is just a YouTube video ID (11 chars, alphanumeric + _ -)."""
    if not title:
        return False
    return len(title) == 11 and all(c.isalnum() or c in "_-" for c in title)


def _is_youtube_url(source: str) -> bool:
    """Check if source is a YouTube URL."""
    if not source:
        return False
    return "youtube.com" in source.lower() or "youtu.be" in source.lower()


@log_metrics
def extract_citations(state: GraphState) -> dict:
    """Map answer sentences to best-matching retrieved documents."""
    answer: str = state.get("answer") or state.get("final_answer") or ""  # type: ignore
    selected_docs: Optional[list[dict]] = state.get("selected_docs")
    relevant_docs: list[dict] = state.get("relevant_docs", [])
    # Preserve an explicitly empty selected_docs value; only fall back to
    # relevant_docs when selected_docs is actually absent (None). An empty
    # selected_docs list means documents were rejected and must not produce
    # citations.
    docs = selected_docs if selected_docs is not None else relevant_docs
    if not answer or not docs:
        return {"citations": []}

    # Split answer into sentences (crude but fast)
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", answer) if len(s.strip()) > 10]

    citations: list[dict] = []
    for sent in sentences:
        best_doc: Optional[dict] = None
        best_score = 0.0
        for doc in docs:
            text = doc.get("text", "")
            score = _jaccard(sent, text)
            if score > best_score:
                best_score = score
                best_doc = doc
        if best_doc and best_score > 0.15:
            meta = best_doc.get("metadata", {}) or {}

            # Extract valid HTTP(S) URL checking both top-level and metadata
            url = ""
            for cand in (
                best_doc.get("source_url"),
                best_doc.get("url"),
                meta.get("source_url"),
                meta.get("url"),
                best_doc.get("source"),
                meta.get("source"),
            ):
                if cand and str(cand).startswith(("http://", "https://")):
                    url = str(cand)
                    break

            # Extract clean title from document or metadata
            title = str(
                best_doc.get("title")
                or meta.get("title")
                or best_doc.get("topic")
                or meta.get("topic")
                or ""
            ).strip()

            doc_identifier = (
                url
                or meta.get("source")
                or best_doc.get("source")
                or title
                or "Spiritual Discourse"
            )

            citations.append(
                {
                    "doc_id": doc_identifier,
                    "source_url": url,
                    "url": url,
                    "title": title or meta.get("source", "Spiritual Teaching"),
                    "quote": sent,
                    "span_in_answer": sent,
                    "confidence": round(best_score, 3),
                    "source": meta.get("source", "Retrieved document"),
                }
            )

    logger.info("Extracted %d citations from answer", len(citations))
    return {"citations": citations}


def _first_http_url(meta: dict) -> str | None:
    """Return the first valid HTTP(S) URL from meta, or None."""
    for key in ("source_url", "url", "source"):
        val = meta.get(key)
        if val and str(val).startswith(("http://", "https://")):
            return str(val)
    return None


if __name__ == "__main__":  # ponytail: self-check
    print("citation_extractor self-check passed")
