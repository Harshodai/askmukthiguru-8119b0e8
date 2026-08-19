"""Automated Unit Tests for Deterministic Prompt Caching and Prefix Overlap.

Verifies that canonical document sorting produces 100% byte-for-byte identical prompt
prefixes regardless of retrieval score ordering or dynamic state changes.
"""

from __future__ import annotations

import pytest

from app.telemetry.prompt_cache_telemetry import (
    compute_prompt_prefix_hash,
    get_prompt_cache_stats,
    record_prompt_cache_event,
)
from rag.doc_utils import doc_hash, sort_docs_canonically
from rag.nodes.generation import context_engineer


def test_canonical_document_sorting_determinism():
    """Verify that doc list permutations produce identical canonical sorted order."""
    doc_a = {"title": "Doc A", "text": "First sacred teaching on soul sync."}
    doc_b = {"title": "Doc B", "text": "Second sacred teaching on beautiful state."}
    doc_c = {"title": "Doc C", "text": "Third sacred teaching on Deeksha practice."}

    perm_1 = [doc_a, doc_b, doc_c]
    perm_2 = [doc_c, doc_a, doc_b]
    perm_3 = [doc_b, doc_c, doc_a]

    s1 = sort_docs_canonically(perm_1)
    s2 = sort_docs_canonically(perm_2)
    s3 = sort_docs_canonically(perm_3)

    hashes_s1 = [doc_hash(d) for d in s1]
    hashes_s2 = [doc_hash(d) for d in s2]
    hashes_s3 = [doc_hash(d) for d in s3]

    assert hashes_s1 == hashes_s2 == hashes_s3, "Canonical document sorting is not deterministic!"


@pytest.mark.asyncio
async def test_context_engineer_prefix_cache_stability():
    """Verify context_engineer output produces stable knowledge text across doc order permutations."""
    doc_1 = {"title": "Deeksha Overview", "text": "Deeksha is the transfer of divine energy."}
    doc_2 = {"title": "Soul Sync Practice", "text": "Soul Sync consists of 6 intentional stages."}

    state_order_a = {
        "intent": "FACTUAL",
        "question": "Explain Deeksha and Soul Sync",
        "relevant_docs": [doc_1, doc_2],
        "query_tier": "standard",
    }
    state_order_b = {
        "intent": "FACTUAL",
        "question": "Explain Deeksha and Soul Sync",
        "relevant_docs": [doc_2, doc_1],
        "query_tier": "standard",
    }

    res_a = await context_engineer(state_order_a)
    res_b = await context_engineer(state_order_b)

    knowledge_a = res_a["context_layers"]["knowledge"]
    knowledge_b = res_b["context_layers"]["knowledge"]

    assert knowledge_a == knowledge_b, (
        "Context engineer produced different knowledge blocks for identical doc sets!"
    )


@pytest.mark.asyncio
async def test_context_engineer_keeps_most_relevant_doc_when_over_budget():
    """When retrieved docs exceed the tier's knowledge budget, the surviving
    content must be chosen by relevance (rerank_score), not by whichever doc
    happens to sort first/last in the cache-friendly hash order. Regression
    test for the blind-tail-truncation bug: sort_docs_canonically sorts by
    SHA256 hash (deliberately, for prompt-cache hit rate), which has no
    relationship to relevance — truncating that hash-ordered blob could
    silently drop the single most relevant doc."""
    # fast/tier2_simple budget is 1536 tokens (~6144 chars at the cap_to_token_budget
    # word-based estimate) — three ~2500-char docs comfortably exceed it together.
    filler_low = "irrelevant tangential content " * 90  # ~2700 chars
    filler_mid = "somewhat related background material " * 90  # ~3400 chars
    filler_high = "the single most directly relevant teaching passage " * 90  # ~4700 chars

    doc_low = {"title": "Low", "text": filler_low, "rerank_score": 0.1}
    doc_mid = {"title": "Mid", "text": filler_mid, "rerank_score": 0.5}
    doc_high = {"title": "High", "text": filler_high, "rerank_score": 0.95}

    state = {
        "intent": "FACTUAL",
        "question": "What is the core teaching?",
        "relevant_docs": [doc_low, doc_mid, doc_high],
        "query_tier": "fast",
    }

    result = await context_engineer(state)
    knowledge = result["context_layers"]["knowledge"]

    assert "most directly relevant" in knowledge, (
        "Highest-relevance doc must survive budget selection"
    )


def test_prompt_cache_telemetry_tracking():
    """Test telemetry module tracking cache events correctly."""
    prefix_h = compute_prompt_prefix_hash("System persona", "Sorted knowledge block")

    event_1 = record_prompt_cache_event(
        "vllm", prefix_h, cached_tokens=100, total_tokens=150, ttft_ms=30.0
    )
    assert event_1["is_hit"] is True

    stats = get_prompt_cache_stats()
    assert stats["total_requests"] >= 1
    assert stats["cache_hits"] >= 1
