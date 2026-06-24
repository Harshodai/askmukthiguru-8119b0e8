"""Qdrant utility helpers: point IDs, poison detection, sparse-vector conversion."""

from __future__ import annotations

import uuid
import logging

from qdrant_client.http.models import SparseVector

logger = logging.getLogger(__name__)

# Namespace for deterministic UUIDs (ingestion dedup)
_NAMESPACE_URL = uuid.UUID("6ba7b811-9dad-11d1-80b4-00c04fd430c8")  # UUID NAMESPACE_URL

# Sentinel tag that requires explicit opt-in on every search
_SKY_TAG = "sky"


class QdrantUtils:
    """Static-style helpers for Qdrant point IDs, poison detection, and sparse vectors."""

    @staticmethod
    def make_point_id(source_url: str, chunk_index: int, raptor_level: int = 0) -> str:
        """Generate a deterministic point ID for deduplication."""
        key = f"{source_url}:{chunk_index}:{raptor_level}"
        return str(uuid.uuid5(_NAMESPACE_URL, key))

    @staticmethod
    def is_poisoned_node(text: str) -> bool:
        """Check if a node contains template/parser leftover logs."""
        if not text:
            return False
        low = text.lower()
        poison_indicators = [
            "analyze the user's request",
            "deconstruct the request",
            "as a text correction expert",
            "as a spiritual teachings summarizer",
            "generate a short topic label",
            "3-6 words",
            "constraint:",
            'examples: "meditation and inner peace"',
            "specific teachings were not provided",
            "text correction expert for the 'mukthi guru'",
            "analyze the input",
            "each proposition on a new line",
            "the prompt asks me",
            "critique of a spiritual",
            "meta-commentary",
            "transcription errors",
            "transcription error",
            "misheard as",
            "the author questions",
            "the provided text is",
            "core task:",
            "decompose a spiritual",
            "decompose the following",
            "independent, self-contained propositions",
            "homophon",
            "let's check the other rules",
        ]
        return any(indicator in low for indicator in poison_indicators)

    @staticmethod
    def sparse_dict_to_vector(sparse_dict: dict) -> SparseVector:
        """Convert bge-m3 lexical_weights dict to Qdrant SparseVector."""
        if not sparse_dict:
            return SparseVector(indices=[], values=[])
        indices = [int(k) for k in sparse_dict.keys()]
        values = [float(v) for v in sparse_dict.values()]
        return SparseVector(indices=indices, values=values)

    @staticmethod
    def build_tag_conditions(knowledge_tags: list[str]) -> tuple[list, list]:
        """
        Build (must, must_not) tag filter conditions.

        - If tags are requested, the chunk must match at least one requested tag.
        - The 'sky' tag is always excluded unless it is explicitly in the request.
        """
        from qdrant_client.http.models import FieldCondition, MatchAny, MatchValue

        must: list = []
        must_not: list = []

        requested = list({t.strip().lower() for t in (knowledge_tags or []) if t and t.strip()})
        if requested:
            must.append(FieldCondition(key="tags", match=MatchAny(any=requested)))

        if _SKY_TAG not in requested:
            must_not.append(FieldCondition(key="tags", match=MatchValue(value=_SKY_TAG)))

        return must, must_not
