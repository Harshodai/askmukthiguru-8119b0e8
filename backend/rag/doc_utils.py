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
    text = re.sub(r'\[Source:\s*[^\]]*?(?:Speaker:|Topic:)[^\]]*\]', '', text)
    text = re.sub(r'\[RAPTOR\s+Level:\s*\d+\s*\|\s*Topic:\s*[^\]]+\]', '', text)
    return text.strip()


if __name__ == "__main__":
    assert doc_text({"text": "a"}) == "a"
    assert doc_text({"content": "b"}) == "b"
    assert doc_text({"text": "", "content": "c"}) == "c"
    assert doc_text({}) == ""
    assert doc_text({"text": "[Source: foo | Speaker: bar]\nHello"}) == "Hello"
    assert doc_text({"text": "[RAPTOR Level: 2 | Topic: test]\nWorld"}) == "World"
    print("doc_text self-check OK")
