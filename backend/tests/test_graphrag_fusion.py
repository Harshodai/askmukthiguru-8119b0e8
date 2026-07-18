"""Tests for GraphRAG Fusion service."""

from __future__ import annotations

import pytest

from services.graphrag_fusion import (
    ContextItem,
    FusedContext,
    GraphRAGFusion,
    reciprocal_rank_fusion,
)


def test_rrf_fusion_basic():
    """Vector hits + graph hits -> RRF list with correct ordering."""
    vector = [
        {"text": "Alpha state quiets the mind.", "id": "v1", "source": "doc:1"},
        {"text": "Stillness arises from surrender.", "id": "v2", "source": "doc:2"},
    ]
    graph = [
        {"text": "Surrender leads to inner peace.", "uri": "x", "relation": "LEADS_TO_STATE", "hop": 1, "source": "seed"},
    ]

    fused = reciprocal_rank_fusion(vector, graph, rrf_k=60)
    assert len(fused) == 3, f"Expected 3 items, got {len(fused)}"
    # scores are purely RRF-derived; sorted desc
    assert fused[0].score >= fused[-1].score
    channels = {i.channel for i in fused}
    assert channels == {"vector", "graph"}, f"Expected both channels, got {channels}"


def test_multi_hop_detection():
    """Graph hit with hop > 0 -> multi_hop=True."""
    async def run():
        async def fake_vector(q, k):
            return []

        async def fake_entities(q):
            return ["https://askmukthiguru.org/ontology/practice/breath-awareness"]

        async def fake_graph(uris, hops):
            return [{"uri": uris[0], "text": "Leads to stillness.",
                     "relation": "LEADS_TO_STATE", "hop": 2, "source": "seed"}]

        eng = GraphRAGFusion(fake_vector, fake_entities, fake_graph, max_hops=2, token_budget=999)
        ctx = await eng.retrieve("How does breath lead to stillness?")
        assert ctx.multi_hop is True
        assert ctx.entities_touched == ["https://askmukthiguru.org/ontology/practice/breath-awareness"]
        return ctx

    ctx = _run_async(run())
    assert ctx.multi_hop is True
    assert any(i.provenance.get("hop") == 2 for i in ctx.items)


def test_token_budget():
    """5 items totalling 1000 tokens, budget=400 -> exactly 4 items returned."""
    texts = [
        "A" * 400,
        "B" * 400,
        "C" * 400,
        "D" * 400,
        "E" * 400,
    ]
    async def run():
        async def fake_vector(q, k):
            return [{"text": t, "id": f"v{i}", "source": "doc"} for i, t in enumerate(texts)]

        async def fake_entities(q):
            return []

        async def fake_graph(uris, hops):
            return []

        eng = GraphRAGFusion(fake_vector, fake_entities, fake_graph, token_budget=400)
        ctx = await eng.retrieve("test")
        return ctx

    ctx = _run_async(run())
    assert len(ctx.items) == 4, f"Expected 4 items within 400 budget, got {len(ctx.items)}"
    assert ctx.total_tokens <= 400


def test_dual_channel_corroboration_boost():
    """Same text in vector + graph -> score boosted above solo-channel items."""
    async def run():
        async def fake_vector(q, k):
            return [{"text": "Breath awareness calms the mind.", "id": "v1", "score": 0.9, "source": "doc:1"}]

        async def fake_entities(q):
            return ["https://askmukthiguru.org/ontology/practice/breath-awareness"]

        async def fake_graph(uris, hops):
            return [{"uri": uris[0], "text": "Breath awareness calms the mind.",
                     "relation": "RELATED", "hop": 1, "source": "seed"}]

        eng = GraphRAGFusion(fake_vector, fake_entities, fake_graph, token_budget=999)
        ctx = await eng.retrieve("test")
        return ctx

    ctx = _run_async(run())
    assert len(ctx.items) >= 1
    top = ctx.items[0]
    assert "calms the mind" in top.text
    assert top.provenance.get("graph") is True


def test_self_test():
    """Run the module's self-test entry point."""
    import subprocess
    import sys
    result = subprocess.run(
        [sys.executable, "-m", "services.graphrag_fusion"],
        capture_output=True, text=True, cwd="backend",
        timeout=30,
    )
    assert result.returncode == 0, f"stdout: {result.stdout}, stderr: {result.stderr}"
    assert "graphrag fusion self-test OK" in result.stdout


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run_async(coro):
    import asyncio
    return asyncio.run(coro)
