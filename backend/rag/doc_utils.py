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
    immediately-repeated Markdown headings (the same heading line emitted
    2+ times in a row — an extraction/summarization retry artifact, not
    real structure; a document legitimately repeating a heading later after
    other content is untouched)."""
    text = _PLACEHOLDER_QUOTE_RE.sub("", text)
    lines = text.split("\n")
    deduped: list[str] = []
    prev_heading: str | None = None
    for line in lines:
        stripped = line.strip()
        if not stripped:
            deduped.append(line)
            continue  # blank lines don't break "immediately repeated" adjacency
        is_heading = bool(re.match(r"^#{1,6}\s+\S", stripped))
        if is_heading and stripped == prev_heading:
            continue  # drop the immediate repeat
        deduped.append(line)
        prev_heading = stripped if is_heading else None
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
    print("doc_utils self-check OK")
