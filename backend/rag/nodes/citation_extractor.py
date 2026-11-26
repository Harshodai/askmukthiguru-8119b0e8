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
from app.constants import BOOK_FOUR_SACRED_SECRETS_URL, is_book_source
from rag.nodes.utils import log_metrics
from rag.states import GraphState
from services.guru_registry import requested_gurus

logger = logging.getLogger(__name__)

_TIMESTAMP_KEYS = (
    "timestamp_seconds",
    "start",
    "start_time",
    "timestamp",
    "start_sec",
    "start_seconds",
    "chunk_start",
    "chunk_start_sec",
    "chunk_start_seconds",
)
# Millisecond offsets: converted to seconds on read. Kept separate so a
# start_ms of 99000 surfaces as 99.0, never as a fabricated 99000s offset.
_TIMESTAMP_MS_KEYS = ("start_ms", "audio_start_ms", "chunk_start_ms")


def _resolve_speaker(doc: dict) -> Optional[str]:
    """Name a teacher when voice-verified, or author-verified (published books/summaries).

    Title/metadata-derived speaker and teacher_id labels contradict the voice
    census on about a third of points (L-TEACHER-TAG-1), and a wrongly named
    speaker is worse than none, so unverified docs get no speaker.
    Published book and concept summary chunks are authored doctrine and carry
    authentic teacher attribution.
    """
    meta = doc.get("metadata") or {}
    content_type = str(doc.get("content_type") or meta.get("content_type") or "").strip().lower()

    if content_type in ("book", "concept_summary", "summary"):
        from services.guru_registry import default_founders_label

        default_founders = default_founders_label()
        raw_speaker = str(doc.get("speaker") or meta.get("speaker") or default_founders).strip()
        if requested_gurus(raw_speaker):
            return raw_speaker
        return default_founders

    if doc.get("speaker_verified") is not True and meta.get("speaker_verified") is not True:
        return None
    raw_speaker = str(doc.get("speaker") or meta.get("speaker") or "").strip()
    if requested_gurus(raw_speaker):
        return raw_speaker
    return None


def _resolve_timestamp(doc: dict) -> Optional[float]:
    """Second offset into the source, only when the payload actually carries
    one. Reads second-denominated keys (timestamp_seconds, start, start_time,
    timestamp, start_sec) and millisecond keys (start_ms, converted to
    seconds). Returns None when absent -- never a fabricated 0. A real 0.0
    offset is returned as-is: 0 is a valid, playable start."""
    meta = doc.get("metadata") or {}
    for key in _TIMESTAMP_KEYS:
        for source in (doc, meta):
            val = source.get(key)
            if val is None or isinstance(val, bool):
                continue
            try:
                return float(val)
            except (TypeError, ValueError):
                continue
    for key in _TIMESTAMP_MS_KEYS:
        for source in (doc, meta):
            val = source.get(key)
            if val is None or isinstance(val, bool):
                continue
            try:
                return float(val) / 1000.0
            except (TypeError, ValueError):
                continue
    return None


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

            ts_seconds = _resolve_timestamp(best_doc)
            clean_url = url
            if clean_url and ts_seconds is not None and ts_seconds > 0 and _is_youtube_url(clean_url):
                sec = int(ts_seconds)
                if "t=" not in clean_url:
                    clean_url = f"{clean_url}&t={sec}" if "?" in clean_url else f"{clean_url}?t={sec}"
            elif is_book_source(clean_url):
                clean_url = BOOK_FOUR_SACRED_SECRETS_URL

            c_type = str(best_doc.get("content_type") or meta.get("content_type") or "").strip().lower()
            if not clean_url and is_book_source(c_type):
                clean_url = BOOK_FOUR_SACRED_SECRETS_URL
            is_verified = bool(
                best_doc.get("speaker_verified") is True
                or meta.get("speaker_verified") is True
                or c_type in ("book", "concept_summary", "summary")
            )

            # Only true verbatim layer or published book text may be shown as the teacher's words
            text_snippet = None
            if best_doc.get("verbatim_text"):
                text_snippet = str(best_doc.get("verbatim_text")).strip() or None
            elif c_type in ("book", "concept_summary"):
                raw_snip = str(best_doc.get("text") or meta.get("text") or "").strip()
                cleaned_snip = re.sub(r"^\[Source:[^\]]+\]\s*", "", raw_snip)[:350]
                text_snippet = cleaned_snip or None

            citations.append(
                {
                    "doc_id": doc_identifier,
                    "source_url": clean_url,
                    "url": clean_url,
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
                    "speaker": _resolve_speaker(best_doc),
                    "speaker_verified": is_verified,
                    "timestamp_seconds": ts_seconds,
                    "text_snippet": text_snippet,
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
        enriched_established = []
        for item in established:
            if isinstance(item, str):
                url = item
                matched_doc = next(
                    (d for d in docs if (d.get("source_url") == url or d.get("url") == url)),
                    None,
                )
                if matched_doc:
                    ts_seconds = _resolve_timestamp(matched_doc)
                    clean_url = url
                    if clean_url and ts_seconds is not None and ts_seconds > 0 and _is_youtube_url(clean_url):
                        sec = int(ts_seconds)
                        if "t=" not in clean_url:
                            clean_url = f"{clean_url}&t={sec}" if "?" in clean_url else f"{clean_url}?t={sec}"
                    elif is_book_source(clean_url):
                        clean_url = BOOK_FOUR_SACRED_SECRETS_URL
                    d_meta = (
                        matched_doc.get("metadata", {})
                        if isinstance(matched_doc.get("metadata"), dict)
                        else {}
                    )
                    c_type = str(
                        matched_doc.get("content_type") or d_meta.get("content_type") or ""
                    ).strip().lower()
                    enriched_established.append({
                        "url": clean_url,
                        "source_url": clean_url,
                        "title": matched_doc.get("title") or d_meta.get("title") or "Spiritual Discourse",
                        "timestamp_seconds": ts_seconds,
                        "speaker": _resolve_speaker(matched_doc),
                        "speaker_verified": bool(
                            matched_doc.get("speaker_verified") is True
                            or d_meta.get("speaker_verified") is True
                            or c_type in ("book", "concept_summary", "summary")
                        ),
                        "chunk_provenance": matched_doc.get("chunk_provenance", ""),
                    })
                else:
                    enriched_established.append({"url": url})
            elif isinstance(item, dict):
                url = item.get("url") or item.get("source_url") or ""
                matched_doc = next(
                    (d for d in docs if (d.get("source_url") == url or d.get("url") == url)),
                    None,
                )
                if matched_doc:
                    ts_seconds = item.get("timestamp_seconds") or _resolve_timestamp(matched_doc)
                    clean_url = url
                    if clean_url and ts_seconds is not None and ts_seconds > 0 and _is_youtube_url(clean_url):
                        sec = int(ts_seconds)
                        if "t=" not in clean_url:
                            clean_url = f"{clean_url}&t={sec}" if "?" in clean_url else f"{clean_url}?t={sec}"
                    elif is_book_source(clean_url):
                        clean_url = BOOK_FOUR_SACRED_SECRETS_URL
                    d_meta = (
                        matched_doc.get("metadata", {})
                        if isinstance(matched_doc.get("metadata"), dict)
                        else {}
                    )
                    c_type = str(
                        matched_doc.get("content_type") or d_meta.get("content_type") or ""
                    ).strip().lower()
                    item["url"] = clean_url
                    item["source_url"] = clean_url
                    if not item.get("timestamp_seconds"):
                        item["timestamp_seconds"] = ts_seconds
                    if not item.get("speaker"):
                        item["speaker"] = _resolve_speaker(matched_doc)
                    if not item.get("speaker_verified"):
                        item["speaker_verified"] = bool(
                            matched_doc.get("speaker_verified") is True
                            or d_meta.get("speaker_verified") is True
                            or c_type in ("book", "concept_summary", "summary")
                        )
                    if not item.get("title"):
                        item["title"] = matched_doc.get("title") or d_meta.get("title") or "Spiritual Discourse"
                enriched_established.append(item)
            else:
                enriched_established.append(item)
        return {"citations": enriched_established}

    if not citations and docs and len(answer.strip()) >= 50:
        _lower_ans = answer.lower()
        _is_refusal = any(
            m in _lower_ans
            for m in (
                "cannot answer",
                "could not find",
                "unable to find",
                "don't have a verified",
                "ask me differently",
            )
        )
        if not _is_refusal:
            fallback_citations = []
            for d in docs[:2]:
                raw_url = d.get("source_url") or d.get("url") or ""
                title = str(d.get("title") or "Spiritual Discourse").strip()
                ts_seconds = _resolve_timestamp(d)
                clean_url = raw_url
                if clean_url and ts_seconds is not None and ts_seconds > 0 and _is_youtube_url(clean_url):
                    sec = int(ts_seconds)
                    if "t=" not in clean_url:
                        clean_url = f"{clean_url}&t={sec}" if "?" in clean_url else f"{clean_url}?t={sec}"
                elif is_book_source(clean_url):
                    clean_url = BOOK_FOUR_SACRED_SECRETS_URL

                d_meta = d.get("metadata", {}) if isinstance(d.get("metadata"), dict) else {}
                c_type = str(d.get("content_type") or d_meta.get("content_type") or "").strip().lower()
                if not clean_url and is_book_source(c_type):
                    clean_url = BOOK_FOUR_SACRED_SECRETS_URL

                is_verified = bool(
                    d.get("speaker_verified") is True
                    or d_meta.get("speaker_verified") is True
                    or c_type in ("book", "concept_summary", "summary")
                )

                text_snippet = None
                if d.get("verbatim_text"):
                    text_snippet = str(d.get("verbatim_text")).strip() or None
                elif c_type in ("book", "concept_summary"):
                    raw_snip = str(d.get("text") or d_meta.get("text") or "").strip()
                    cleaned_snip = re.sub(r"^\[Source:[^\]]+\]\s*", "", raw_snip)[:350]
                    text_snippet = cleaned_snip or None

                fallback_citations.append({
                    "doc_id": clean_url or title,
                    "source_url": clean_url,
                    "url": clean_url,
                    "title": title,
                    "quote": answer[:150],
                    "span_in_answer": answer[:150],
                    "confidence": 0.5,
                    "source": d_meta.get("source", "Retrieved document"),
                    "knowledge_source": d.get("knowledge_source", "qdrant"),
                    "chunk_provenance": d.get("chunk_provenance", ""),
                    "speaker": _resolve_speaker(d),
                    "speaker_verified": is_verified,
                    "timestamp_seconds": ts_seconds,
                    "text_snippet": text_snippet,
                })
            if fallback_citations:
                logger.info(
                    "Citation floor: fell back to top %d surviving doc(s) as citations",
                    len(fallback_citations),
                )
                return {"citations": fallback_citations}

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
