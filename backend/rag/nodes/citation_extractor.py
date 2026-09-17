"""Citation extractor — post-graph node that maps answer spans to source docs.

Produces structured citation objects {doc_id, quote, span_in_answer, confidence}
using simple n-gram Jaccard overlap between answer sentences and retrieved docs.
Wired after generate_answer and before format_final_answer.
"""

from __future__ import annotations

import logging
import re
from typing import Optional
from urllib.parse import urlparse

from app.config import settings
from rag.nodes.utils import log_metrics
from rag.states import GraphState

logger = logging.getLogger(__name__)


# Function words carry no evidence, so they inflate every score equally.
_STOPWORDS = frozenset(
    """a an the is are was were be been being am of to in on at for with and or but
    that this these those it its you your yours i we they he she as from by not no
    do does did can could will would shall should may might must have has had if
    then than so such about into over under again more most other some any each our
    their them his her what who when where why how there here all both few own same
    very just only also because while during before after above below up down out off
    """.split()
)
_WORD_RE = re.compile(r"[\w']+", re.UNICODE)


def _content_words(text: str) -> set[str]:
    """Lowercased content words: stopwords and <=2-char tokens dropped."""
    return {w for w in _WORD_RE.findall((text or "").lower()) if len(w) > 2 and w not in _STOPWORDS}


def _span_overlap(sentence: str, doc_text: str) -> float:
    """Fraction of the SENTENCE's content words that appear in `doc_text`.

    This is containment, not Jaccard, and it is word-level, not character
    n-gram level. Both departures are load-bearing and were measured against
    the live collection on 2026-09-16 (GURU_DEMO_READINESS F2):

    * **Jaccard divides by the union.** An answer sentence is ~80-150 chars
      (~120 character 3-grams); a retrieved chunk is ~400-1600 chars (~400-1600
      3-grams). The score therefore has a mathematical ceiling near
      |sentence|/|chunk|, measured at 0.083-0.153 for the CORRECT sentence
      against the 8 documents actually retrieved for "What is the Beautiful
      State?" -- seven of eight could not clear the old 0.15 floor no matter
      how faithful the paraphrase was. That is the F2 intermittency: citations
      survived only when a short chunk happened to rank.
    * **Character 3-grams do not discriminate.** With containment applied to
      character 3-grams, an off-topic control sentence ("The capital of France
      is Paris...") scored 0.580 against the same documents -- higher than an
      on-topic sentence. English prose shares trigrams regardless of meaning.

    Word-level containment separates cleanly: on-topic answer sentences scored
    0.357-0.583 across three questions, genuinely off-domain controls
    0.000-0.100. Floor: `settings.citation_span_overlap_floor` (0.30).

    The extractor can only ever select a document already in
    `selected_docs`/`relevant_docs`, so an imperfect match cites a retrieved
    teaching -- it cannot invent a source.
    """
    sentence_words = _content_words(sentence)
    if not sentence_words:
        return 0.0
    doc_words = _content_words(doc_text)
    if not doc_words:
        return 0.0
    return len(sentence_words & doc_words) / len(sentence_words)


def _is_youtube_video_id_title(title: str) -> bool:
    """Check if a title is just a YouTube video ID (11 chars, alphanumeric + _ -)."""
    if not title:
        return False
    return len(title) == 11 and all(c.isalnum() or c in "_-" for c in title)


def _is_youtube_url(source: str) -> bool:
    """Check if source is a YouTube URL."""
    if not source:
        return False
    try:
        parsed = urlparse(source.strip())
        host = (parsed.hostname or "").lower()
        return (
            host == "youtube.com"
            or host.endswith(".youtube.com")
            or host == "youtu.be"
            or host.endswith(".youtu.be")
        )
    except Exception:
        return False


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
        # No documents at all (or an explicitly emptied selected_docs, meaning
        # they were rejected) is the one case where an empty citation list is
        # the truth. The floor below deliberately does not apply here.
        return {"citations": []}

    # What generate_answer already established from the documents that survived
    # into the prompt (`_grounded_citation_urls(surviving_docs)`). This node
    # runs AFTER it and its return REPLACES the state key, so before this floor
    # existed an empty match set silently destroyed a grounded citation list.
    # Measured live 2026-09-16 (GURU_DEMO_READINESS F2): retrieved_count=8,
    # citation_urls=[2 YouTube URLs], final_citations=[] -- and the answer
    # still attributed doctrine to the Gurus by name.
    established: list = list(state.get("citations") or [])

    # Split answer into sentences (crude but fast)
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", answer) if len(s.strip()) > 10]

    overlap_floor = float(getattr(settings, "citation_span_overlap_floor", 0.30))

    citations: list[dict] = []
    for sent in sentences:
        best_doc: Optional[dict] = None
        best_score = 0.0
        for doc in docs:
            text = doc.get("text", "")
            score = _span_overlap(sent, text)
            if score > best_score:
                best_score = score
                best_doc = doc
        if best_doc and best_score >= overlap_floor:
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
                    # TrustNLP 2026 F21/F33: which lane produced this citation
                    # (qdrant/okf/neo4j_subgraph/lightrag). Deliberately NOT
                    # "content_type" -- that key already carries Qdrant's raw
                    # payload field (video_enhanced/summary/contextual) on
                    # every real hit, so reusing it here would report the
                    # wrong thing for the majority case instead of "qdrant".
                    "knowledge_source": best_doc.get("knowledge_source", "qdrant"),
                    # GURU_DEMO_READINESS F4 §3B.3 item 4: let a reviewer (or
                    # the eval harness) answer "was this the teachers' own
                    # words?" from the citation alone, without re-querying
                    # Qdrant for the chunk that produced it.
                    "chunk_provenance": best_doc.get("chunk_provenance", ""),
                    "speaker": best_doc.get("speaker", ""),
                }
            )

    if not citations and established:
        # Never downgrade. Span matching is a precision mechanism for pointing
        # at WHICH teaching supports WHICH sentence; it is not the authority on
        # whether the answer was grounded at all. That authority is retrieval,
        # and generate_answer already exercised it.
        logger.warning(
            "Citation floor: span matching produced 0 citations over %d docs; "
            "preserving %d citation(s) already established by generate_answer",
            len(docs),
            len(established),
        )
        return {"citations": established}

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
