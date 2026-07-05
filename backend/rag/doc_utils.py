"""Shared document-dict accessors for graph nodes.

Retrieved documents come from several builders (Qdrant leaf chunks, LightRAG
graph context, web search, cross-teacher comparison docs) that disagree on the
body key ("text" vs "content").  Every consumer must go through doc_text() —
a bare doc["text"] KeyError inside a node wipes the CRAG state and sends the
query into the rewrite/fallback spiral.
"""

from __future__ import annotations


def doc_text(doc: dict) -> str:
    """Return the document body regardless of which builder produced it."""
    return doc.get("text") or doc.get("content") or ""


if __name__ == "__main__":
    assert doc_text({"text": "a"}) == "a"
    assert doc_text({"content": "b"}) == "b"
    assert doc_text({"text": "", "content": "c"}) == "c"
    assert doc_text({}) == ""
    print("doc_text self-check OK")
