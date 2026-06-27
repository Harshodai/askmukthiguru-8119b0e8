#!/usr/bin/env python3
"""Memory profiling benchmarks using tracemalloc.

Usage:
    cd backend && python -m benchmarks.test_memory_profile
    # or with pytest:
    cd backend && python -m pytest benchmarks/test_memory_profile.py -v --benchmark
"""

from __future__ import annotations

import asyncio
import sys
import tracemalloc
from pathlib import Path

# Add parent directory for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

from rag.states import GraphState


@pytest.mark.benchmark
async def test_memory_profile_graph_execution():
    """Profile memory usage during a full graph execution simulation.

    Exercises the key pipeline data structures without a running backend:
    state dictionary, context assembly, and document formatting.
    """
    tracemalloc.start()

    try:
        # Build a representative GraphState simulating post-retrieval state
        sample_docs = [
            {
                "title": "Four Sacred Secrets",
                "text": "The first secret is spiritual vision — the ability to see beyond "
                        "the surface of life into the deeper truth of who you are. "
                        "When you cultivate spiritual vision, you begin to perceive the "
                        "unseen reality that underlies all of existence. This is the "
                        "foundation of the Four Sacred Secrets teachings." * 10,
                "source_url": "https://ekam.org/four-sacred-secrets",
                "chunk_index": i,
            }
            for i in range(15)  # 15 docs × ~260 chars ≈ ~4KB
        ]

        state: GraphState = {
            "question": "What is spiritual vision and how do I cultivate it?",
            "rewritten_query": "spiritual vision cultivation four sacred secrets",
            "relevant_docs": sample_docs,
            "citations": [d["source_url"] for d in sample_docs],
            "chat_history": [
                {"role": "user", "content": "Tell me about the Four Sacred Secrets"},
                {"role": "assistant", "content": "The Four Sacred Secrets are foundational teachings..."},
            ],
            "intent": "FACTUAL",
            "confidence_score": 8.0,
            "is_faithful": True,
            "memory_context": "User has practiced Soul Sync meditation for 3 months and has "
                              "completed the first two sacred secrets practices.",
            "detected_language": "en",
            "query_tier": "standard",
            "answer": "Spiritual vision is the capacity to see beyond appearances...",
            "context_layers": {
                "persona": "You are Mukthi Guru, a compassionate spiritual guide...",
                "knowledge": "Sample knowledge text for profiling purposes...",
                "user_state": "Intent: FACTUAL\nConversation Depth: 2 turns\n",
                "instructions": "Base your answer ONLY on the provided Knowledge...",
            },
        }

        # Simulate context assembly operations
        from rag.compressor import cap_to_token_budget

        knowledge_budget = 3072
        knowledge = "\n\n".join(
            f"[Source: {doc.get('title', 'Unknown')} | URL: {doc.get('source_url', 'N/A')}]\n{doc['text']}"
            for doc in state["relevant_docs"]
        )
        knowledge = cap_to_token_budget(knowledge, knowledge_budget)

        user_state = f"Intent: {state['intent']}\n"
        if state.get("memory_context"):
            user_state += f"Memory context present ({len(state['memory_context'])} chars)\n"

        # Snapshot memory after assembly
        snapshot = tracemalloc.take_snapshot()
        top_stats = snapshot.statistics("lineno")

        print("\n=== Top 10 Memory Allocations ===")
        for stat in top_stats[:10]:
            print(f"  {stat}")

        total_size = sum(stat.size for stat in top_stats)
        print(f"\nTotal tracked memory: {total_size / 1_000_000:.2f} MB")
        print(f"Knowledge string length: {len(knowledge)} chars")

        assert total_size < 500_000_000, (
            f"Memory usage too high: {total_size} bytes ({total_size / 1_000_000:.1f} MB)"
        )

    finally:
        tracemalloc.stop()


@pytest.mark.benchmark
async def test_memory_profile_conversation_history():
    """Profile memory overhead of accumulating conversation history.

    Ensures that long conversations (50+ turns) do not cause unbounded
    memory growth in the pipeline state.
    """
    tracemalloc.start()

    try:
        # Simulate a long conversation history
        history = []
        for i in range(50):
            history.append({"role": "user", "content": f"Question number {i + 1} about spiritual practices."})
            history.append({"role": "assistant", "content": f"This is a detailed answer to question {i + 1}. " * 20})

        state: GraphState = {
            "question": "What is next?",
            "rewritten_query": "next step in practice",
            "relevant_docs": [],
            "citations": [],
            "chat_history": history,
            "intent": "FACTUAL",
            "confidence_score": 7.0,
            "is_faithful": True,
            "detected_language": "en",
            "query_tier": "standard",
        }

        snapshot = tracemalloc.take_snapshot()
        top_stats = snapshot.statistics("lineno")

        print("\n=== Conversation History: Top 10 Memory Allocations ===")
        for stat in top_stats[:10]:
            print(f"  {stat}")

        total_size = sum(stat.size for stat in top_stats)
        print(f"\nTotal tracked memory (50-turn history): {total_size / 1_000_000:.2f} MB")

        assert total_size < 500_000_000, (
            f"Conversation history memory too high: {total_size / 1_000_000:.1f} MB"
        )

    finally:
        tracemalloc.stop()


if __name__ == "__main__":
    asyncio.run(test_memory_profile_graph_execution())
    asyncio.run(test_memory_profile_conversation_history())
