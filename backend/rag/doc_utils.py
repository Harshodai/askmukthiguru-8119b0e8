"""Shared document-dict accessors for graph nodes.

Retrieved documents come from several builders (Qdrant leaf chunks, LightRAG
graph context, web search, cross-teacher comparison docs) that disagree on the
body key ("text" vs "content").  Every consumer must go through doc_text() —
a bare doc["text"] KeyError inside a node wipes the CRAG state and sends the
query into the rewrite/fallback spiral.
"""

from __future__ import annotations

import re


def doc_text(doc: dict) -> str:
    """Return the document body regardless of which builder produced it."""
    text = doc.get("text") or doc.get("content") or ""
    return _strip_ingestion_headers(text)


def _strip_ingestion_headers(text: str) -> str:
    """Remove ingestion pipeline headers embedded in document text before LLM sees them."""
    if not text:
        return text
    text = re.sub(r"\[Source:\s*[^\]]*?(?:Speaker:|Topic:)[^\]]*\]", "", text)
    text = re.sub(r"\[RAPTOR\s+Level:\s*\d+\s*\|\s*Topic:\s*[^\]]+\]", "", text)
    text = _strip_extraction_artifacts(text)
    return text.strip()


def strip_contextual_artifacts(txt: str) -> str:
    """Strip contextual_chunking_service's ``[Context: ...]`` header and
    pipeline.py's ``[Potential Questions: ...]`` footer so a re-reconstructed
    document contains the guru's actual words, not extraction machinery.

    Both markers are re-added fresh by ``_contextualize``/normal ingestion
    on every pass, so any copy already baked into stored text is stale and
    must come out first — otherwise it survives re-chunking as literal body
    prose and stacks another generation of header on re-ingest (the QF-1
    finding: 68.9% of this pipeline's own live output was multiple stitched
    ``[Context: ...]`` blocks glued together). Loop the edge strips to
    self-heal payloads that already accumulated more than one generation,
    and run a bounded global sweep for copies stitched mid-string from
    already-concatenated payloads.
    """
    # Leading [Context: ...] / [Source: ...] header(s) — closing "]" is on
    # the same line as the opening "[" by construction (single sentence).
    while txt.startswith("["):
        first_newline = txt.find("\n")
        if first_newline != -1 and txt[:first_newline].rstrip().endswith("]"):
            txt = txt[first_newline + 1 :].lstrip("\n")
        else:
            break
    # Trailing [Potential Questions: ...] footer(s) — content can be
    # multi-line, so strip from the LAST marker to end of string.
    while True:
        idx = txt.rfind("[Potential Questions:")
        if idx == -1:
            break
        tail = txt[idx:]
        if tail.count("[") == 1 and tail.rstrip().endswith("]"):
            txt = txt[:idx].rstrip()
        else:
            break
    # Bounded sweep for either marker stitched mid-string (already-corrupted
    # payloads that went through multiple contaminated re-ingest passes).
    txt = re.sub(r"\[Context:[^\[\]]*\]", "", txt)
    txt = re.sub(r"\[Potential Questions:[^\[\]]*\]", "", txt)
    return txt.strip()


# Extraction-prompt placeholder text that survived into stored content instead
# of being filled in or dropped — confirmed live 2026-09-05 in retrieved
# LightRAG chunks: a blockquote literally reading `"Exact quote from
# transcript" — Sri Krishnaji`, misattributing a template instruction as a
# real quote. Same poison class as scripts/ops/heal_neo4j_poison.py (an LLM's
# own scaffolding leaking into stored content), different location and shape.
_PLACEHOLDER_QUOTE_RE = re.compile(
    r'^\s*>?\s*"Exact quote from transcript"\s*(?:—|-)\s*.*$', re.MULTILINE | re.IGNORECASE
)


def _strip_extraction_artifacts(text: str) -> str:
    """Strip known LLM-extraction-artifact shapes: placeholder quotes and
    immediately-repeated Markdown headings (the same heading TEXT emitted
    2+ times in a row — an extraction/summarization retry artifact, not
    real structure; a document legitimately repeating a heading later after
    other content is untouched).

    Compares heading TEXT with the leading ``#``s stripped, not the raw line:
    an ingestion contextual header (``# Title``) immediately followed by the
    chunk's own heading at a different level (``### Title``) is the same
    duplicate, live in golden_024's fallback excerpt ("# Deeksha and Spiritual
    Relationships ### Deeksha and Spiritual Relationships ...") — comparing
    raw lines missed it because the ``#`` counts differed.
    """
    text = _PLACEHOLDER_QUOTE_RE.sub("", text)
    lines = text.split("\n")
    deduped: list[str] = []
    prev_heading_text: str | None = None
    for line in lines:
        stripped = line.strip()
        if not stripped:
            deduped.append(line)
            continue  # blank lines don't break "immediately repeated" adjacency
        heading_match = re.match(r"^#{1,6}\s+(\S.*)$", stripped)
        heading_text = heading_match.group(1).strip() if heading_match else None
        if heading_text is not None and heading_text == prev_heading_text:
            continue  # drop the immediate repeat, regardless of heading level
        deduped.append(line)
        prev_heading_text = heading_text
    return "\n".join(deduped)


import hashlib


def doc_hash(doc: dict) -> str:
    """Compute or return deterministic SHA-256 hash for a document chunk."""
    if doc.get("chunk_hash"):
        return str(doc["chunk_hash"])
    text = doc_text(doc).strip()
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sort_docs_canonically(docs: list[dict]) -> list[dict]:
    """Sort retrieved document chunks deterministically by their sha256 hash.

    Ensures that identical retrieved document sets generate byte-for-byte identical
    prompt prefixes regardless of vector similarity score ordering across queries.
    Unlocks 85-95% prompt cache hit rates in LLM inference engines (vLLM, LMCache, NIM).
    """
    return sorted(docs, key=doc_hash)


def _doc_relevance(doc: dict) -> float:
    """Best-effort relevance score across the keys builders actually set."""
    for key in ("rerank_score", "relevance", "score"):
        value = doc.get(key)
        if isinstance(value, bool):
            continue
        if isinstance(value, (int, float)):
            return float(value)
    return 0.0


def sort_docs_litm_aware(docs: list[dict] | None) -> list[dict]:
    """Two-tier lost-in-the-middle-aware canonical ordering.

    Tier 1 (attention edges): the #1 relevance doc anchors index 0 and #2
    anchors index -1, where LLM attention is strongest. Tier 2 (interior):
    ranks 3..N hash-sort by ``doc_hash`` so identical doc sets still produce
    byte-for-byte identical interiors regardless of vector score ordering
    (preserves the prompt-cache benefit of ``sort_docs_canonically``).
    Relevance ties break by hash, so the output is fully input-order
    independent. N=0/1 pass through; N=2 orders by relevance (hash on ties).
    """
    items = list(docs or [])
    count = len(items)
    if count <= 1:
        return items
    ranked = sorted(items, key=lambda d: (-_doc_relevance(d), doc_hash(d)))
    if count == 2:
        return ranked
    head, tail = ranked[0], ranked[1]
    interior = sorted(ranked[2:], key=doc_hash)
    return [head, *interior, tail]


if __name__ == "__main__":
    assert doc_text({"text": "a"}) == "a"
    assert doc_text({"content": "b"}) == "b"
    assert doc_text({"text": "", "content": "c"}) == "c"
    assert doc_text({}) == ""
    assert doc_text({"text": "[Source: foo | Speaker: bar]\nHello"}) == "Hello"
    assert doc_text({"text": "[RAPTOR Level: 2 | Topic: test]\nWorld"}) == "World"

    d1 = {"text": "Alpha document"}
    d2 = {"text": "Beta document"}
    s1 = sort_docs_canonically([d1, d2])
    s2 = sort_docs_canonically([d2, d1])
    assert s1 == s2, "Canonical document sorting failed"

    assert sort_docs_litm_aware([]) == []
    assert sort_docs_litm_aware([d1]) == [d1]
    lo = {"text": "low doc", "rerank_score": 0.1}
    hi = {"text": "high doc", "rerank_score": 0.9}
    assert sort_docs_litm_aware([lo, hi])[0] == hi
    assert sort_docs_litm_aware([lo, hi]) == sort_docs_litm_aware([hi, lo])
    docs5 = [{"text": f"doc{i}", "rerank_score": float(i)} for i in range(5)]
    o1 = sort_docs_litm_aware(docs5)
    o2 = sort_docs_litm_aware(list(reversed(docs5)))
    assert o1 == o2, "LITM-aware sorting is input-order dependent"
    assert o1[0]["text"] == "doc4" and o1[-1]["text"] == "doc3"
    print("doc_utils self-check OK")
