"""Canonical memory extraction pipeline — Phase 3 + Phase 9 of Adaptive Memory System.

This package provides isolated, stateless extraction of MemoryCandidate[] from
bounded conversation windows. The extractor MUST NOT write directly to any store.

Phase 9 adds history_separator: strict boundary enforcement between History,
Memory, and Knowledge layers, ensuring transient conversation info never becomes
durable memory unintentionally.

Usage:
    from services.canonical_memory.extractor import extract_memory_candidates
    result = await extract_memory_candidates(turns, user_id="...", language_hint="en")

    from services.canonical_memory.history_separator import (
        classify_conversation_turn,
        build_history_context,
        validate_separation,
    )
    classification = classify_conversation_turn(user_msg, asst_resp)
    history_ctx = build_history_context(session_messages, max_tokens=1024)
    is_valid = validate_separation(memory_context, history_context)
"""

from services.canonical_memory.models import ExtractionResult, MemoryCandidate, MemoryType
from services.canonical_memory.extractor import extract_memory_candidates
from services.canonical_memory.history_separator import (
    TurnClassification,
    classify_conversation_turn,
    is_transient,
    build_history_context,
    validate_separation,
)

__all__ = [
    "MemoryType",
    "MemoryCandidate",
    "ExtractionResult",
    "extract_memory_candidates",
    "TurnClassification",
    "classify_conversation_turn",
    "is_transient",
    "build_history_context",
    "validate_separation",
]
