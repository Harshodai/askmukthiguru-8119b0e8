"""
Mukthi Guru — Retrieval Domain Types

Typed, slots-optimised structs for the RAG retrieval pipeline hot-path.

``slots=True`` eliminates ``__dict__`` per instance (~50 bytes each) and
speeds up attribute access. ``frozen=True`` makes instances hashable and
safe to cache in LRU caches.

Backward compatibility: ``to_dict()`` mirrors the previous plain-dict shape
so existing code using ``doc["content"]`` can migrate incrementally.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True, frozen=True)
class RetrievedDoc:
    """Single retrieved document with relevance metadata.

    Migration guide (Q2 — dict-style access):
        Old: doc["content"], doc["score"]
        New: doc.content,    doc.score
        Compat: doc.to_dict()["content"]  # temporary bridge
    """

    content: str
    score: float
    source_url: str
    doc_id: str
    collection: str = "default"
    doc_type: str = "text"

    def to_dict(self) -> dict:
        """Backward-compatibility shim — mirrors old plain-dict schema.

        Use only during migration. Prefer attribute access (doc.content) for
        new code; it is faster and type-safe.
        """
        return {
            "content": self.content,
            "score": self.score,
            "source_url": self.source_url,
            "doc_id": self.doc_id,
            "collection": self.collection,
            "doc_type": self.doc_type,
            # Legacy aliases used in some nodes
            "text": self.content,
            "id": self.doc_id,
        }

    @classmethod
    def from_dict(cls, d: dict) -> RetrievedDoc:
        """Construct from legacy dict format (for incremental migration)."""
        return cls(
            content=d.get("content") or d.get("text", ""),
            score=float(d.get("score", 0.0)),
            source_url=d.get("source_url", ""),
            doc_id=d.get("doc_id") or d.get("id", ""),
            collection=d.get("collection", "default"),
            doc_type=d.get("doc_type", "text"),
        )


@dataclass(slots=True)
class RetrievalBatch:
    """Container for a batch of retrieved documents with aggregate metrics."""

    docs: list[RetrievedDoc] = field(default_factory=list)
    query: str = ""
    latency_ms: float = 0.0
    source: str = "vector"  # "vector" | "graph" | "hybrid"

    @property
    def top_score(self) -> float:
        """Highest relevance score in the batch."""
        return max((d.score for d in self.docs), default=0.0)

    @property
    def count(self) -> int:
        return len(self.docs)

    def to_legacy_list(self) -> list[dict]:
        """Convert to list of dicts for nodes still expecting plain dicts."""
        return [d.to_dict() for d in self.docs]


if __name__ == "__main__":
    # Quick self-check (Ponytail principle)
    doc = RetrievedDoc(
        content="Deeksha is the Oneness Blessing",
        score=0.92,
        source_url="https://ekam.org",
        doc_id="doc-001",
    )
    assert doc.content == "Deeksha is the Oneness Blessing"
    assert doc.to_dict()["text"] == doc.content
    assert RetrievedDoc.from_dict(doc.to_dict()) == doc
    print(f"✅ RetrievedDoc OK — slots={doc.__slots__}")
