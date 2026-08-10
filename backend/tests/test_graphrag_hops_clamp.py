"""P1-BE-6: graph traversal hop count is clamped at the call boundary.

The GraphRAG Cypher uses a variable-length pattern (``r*1..$hops``) whose cost
grows super-linearly with the hop count. ``GraphRAGFusion.__init__`` now clamps
``max_hops`` to ``[1, MAX_HOPS]`` so an unbounded/config value can never turn
into a deep-traversal DoS.
"""

from services.graphrag_fusion import MAX_HOPS, GraphRAGFusion


async def _noop_vector(q, k):
    return []


async def _noop_entities(q):
    return []


async def _recording_graph(uris, hops):
    return [{"uri": uris[0], "text": "x", "relation": "RELATED", "hop": hops, "source": "seed"}]


def test_max_hops_clamped_at_upper_bound():
    eng = GraphRAGFusion(_noop_vector, _noop_entities, _recording_graph, max_hops=50)
    assert eng.max_hops == 3


def test_max_hops_accepts_in_range_value():
    eng = GraphRAGFusion(_noop_vector, _noop_entities, _recording_graph, max_hops=2)
    assert eng.max_hops == 2


def test_max_hops_rejects_below_one():
    eng = GraphRAGFusion(_noop_vector, _noop_entities, _recording_graph, max_hops=0)
    assert eng.max_hops == 1


def test_max_hops_rejects_non_numeric():
    eng = GraphRAGFusion(_noop_vector, _noop_entities, _recording_graph, max_hops="999")
    assert eng.max_hops == MAX_HOPS


def test_graph_channel_receives_clamped_hops():
    import asyncio

    seen = []

    async def recording_graph(uris, hops):
        seen.append(hops)
        return [{"uri": uris[0], "text": "x", "relation": "RELATED", "hop": hops, "source": "seed"}]

    async def entity(q):
        return ["https://askmukthiguru.org/ontology/practice/breath-awareness"]

    async def run():
        eng = GraphRAGFusion(_noop_vector, entity, recording_graph, max_hops=50)
        await eng.retrieve("breath")

    asyncio.run(run())
    assert seen and all(h == MAX_HOPS for h in seen), f"graph called with {seen}, expected {MAX_HOPS}"
