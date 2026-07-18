"""
GraphRAG fusion — vector retrieval + knowledge-graph traversal, fused.

Sampriti Mitra's "Why Naive RAG Fails in Production": top-k vector stuffing
breaks on multi-hop questions and loses precision as the corpus grows. The
fix is to let the question traverse the knowledge graph (entity -> relation ->
entity) *in addition to* vector search, then fuse and rerank both channels.

This module is storage-agnostic: inject your vector search (Qdrant) and your
graph query (Neo4j) callables. It returns a single, fused, deduplicated,
provenance-tagged context block ready for the generation layer.

Design goals
------------
* Multi-hop: follow doctrine relations (LEADS_TO_STATE, IS_TECHNIQUE_FOR,
  EXPOUNDS, PART_OF) up to N hops from the entities the question touches.
* Fused: reciprocal-rank-fusion (RRF) of vector hits + graph-derived chunks.
* Grounded: every returned item carries provenance (source, hop, relation).
* Bounded: token budget enforced so context engineering stays tight
  (Tony Seale's "context rot" — pull the right subgraph, not the haystack).

Stdlib only; the two backends are injected async callables.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Optional

logger = logging.getLogger("graphrag")

# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

@dataclass
class ContextItem:
    text: str
    score: float
    channel: str                 # "vector" | "graph"
    provenance: dict = field(default_factory=dict)   # source, hop, relation, uri
    token_estimate: int = 0

    def __post_init__(self):
        if not self.token_estimate:
            self.token_estimate = max(1, len(self.text) // 4)


@dataclass
class FusedContext:
    items: list[ContextItem]
    total_tokens: int
    multi_hop: bool
    entities_touched: list[str]

    def to_prompt_block(self, *, max_items: Optional[int] = None) -> str:
        """Render as the KNOWLEDGE block for the generation prompt, with
        inline provenance markers the citation layer can later resolve."""
        items = self.items[:max_items] if max_items else self.items
        lines = []
        for i, it in enumerate(items, 1):
            src = it.provenance.get("source") or it.provenance.get("uri") or it.channel
            lines.append(f"[{i}] ({it.channel}, {src}) {it.text}")
        return "\n".join(lines)


# Injected backend signatures
VectorSearchFn = Callable[[str, int], Awaitable[list[dict]]]
#   -> [{"id","text","score","source"}]
EntityResolveFn = Callable[[str], Awaitable[list[str]]]
#   question -> [concept URIs it touches]
GraphTraverseFn = Callable[[list[str], int], Awaitable[list[dict]]]
#   (seed URIs, max_hops) -> [{"uri","text","relation","hop","source"}]


# ---------------------------------------------------------------------------
# Reciprocal Rank Fusion
# ---------------------------------------------------------------------------

def _rrf(rank: int, k: int = 60) -> float:
    return 1.0 / (k + rank)


def reciprocal_rank_fusion(
    vector_hits: list[dict],
    graph_hits: list[dict],
    *,
    rrf_k: int = 60,
) -> list[ContextItem]:
    """Fuse two ranked lists into one via RRF. Dedupes by normalized text."""
    scores: dict[str, float] = {}
    items: dict[str, ContextItem] = {}

    for rank, h in enumerate(vector_hits):
        key = _norm(h["text"])
        scores[key] = scores.get(key, 0.0) + _rrf(rank, rrf_k)
        items.setdefault(key, ContextItem(
            text=h["text"], score=0.0, channel="vector",
            provenance={"source": h.get("source"), "id": h.get("id")}))

    for rank, h in enumerate(graph_hits):
        key = _norm(h["text"])
        scores[key] = scores.get(key, 0.0) + _rrf(rank, rrf_k)
        if key in items:
            # seen in both channels -> boost & merge provenance
            items[key].provenance["graph"] = True
            items[key].provenance["hop"] = h.get("hop")
            scores[key] += 0.05  # dual-channel corroboration bonus
        else:
            items[key] = ContextItem(
                text=h["text"], score=0.0, channel="graph",
                provenance={"uri": h.get("uri"), "relation": h.get("relation"),
                            "hop": h.get("hop"), "source": h.get("source")})

    fused = list(items.values())
    for key, it in items.items():
        it.score = round(scores[key], 6)
    fused.sort(key=lambda x: x.score, reverse=True)
    return fused


def _norm(text: str) -> str:
    return " ".join(text.lower().split())[:256]


# ---------------------------------------------------------------------------
# Fusion engine
# ---------------------------------------------------------------------------

class GraphRAGFusion:
    def __init__(
        self,
        vector_search: VectorSearchFn,
        resolve_entities: EntityResolveFn,
        traverse_graph: GraphTraverseFn,
        *,
        max_hops: int = 2,
        token_budget: int = 4000,
        vector_top_k: int = 8,
        enable_graph: bool = True,
    ) -> None:
        self._vector = vector_search
        self._entities = resolve_entities
        self._graph = traverse_graph
        self.max_hops = max_hops
        self.token_budget = token_budget
        self.vector_top_k = vector_top_k
        self.enable_graph = enable_graph

    async def retrieve(self, question: str) -> FusedContext:
        """Run both channels concurrently, fuse, budget, return."""
        vector_task = asyncio.create_task(self._safe_vector(question))
        graph_task = asyncio.create_task(self._safe_graph(question))
        vector_hits, (graph_hits, entities) = await asyncio.gather(vector_task, graph_task)

        fused = reciprocal_rank_fusion(vector_hits, graph_hits)
        bounded = self._budget(fused)
        return FusedContext(
            items=bounded,
            total_tokens=sum(i.token_estimate for i in bounded),
            multi_hop=any(i.provenance.get("hop", 0) > 0 for i in bounded),
            entities_touched=entities,
        )

    # ---- channels ----

    async def _safe_vector(self, question: str) -> list[dict]:
        try:
            return await self._vector(question, self.vector_top_k)
        except Exception as exc:
            logger.warning("vector channel failed: %s", exc)
            return []

    async def _safe_graph(self, question: str) -> tuple[list[dict], list[str]]:
        if not self.enable_graph:
            return [], []
        try:
            entities = await self._entities(question)
            if not entities:
                return [], []
            hits = await self._graph(entities, self.max_hops)
            return hits, entities
        except Exception as exc:
            logger.warning("graph channel failed: %s", exc)
            return [], []

    # ---- budget ----

    def _budget(self, items: list[ContextItem]) -> list[ContextItem]:
        out, used = [], 0
        for it in items:
            if used + it.token_estimate > self.token_budget:
                continue
            out.append(it)
            used += it.token_estimate
        return out


# ---------------------------------------------------------------------------
# Wiring: adapted to this repo's actual services
# ---------------------------------------------------------------------------

async def wire_example():
    """Wire GraphRAGFusion to the repo's real Qdrant, Neo4j, and embedder."""

    async def vector_search(q: str, k: int):
        from rag.nodes import _services
        embedder = _services._embedder
        qdrant = _services._qdrant
        vec = await asyncio.to_thread(embedder.encode_single_full, q)
        hits = await asyncio.to_thread(
            qdrant.search,
            query_vector=vec["dense"],
            limit=k,
            sparse_vector=vec["sparse"],
            query=q,
        )
        return [{"id": h.get("id"), "text": h.get("text", ""),
                 "score": h.get("score", 0.0), "source": h.get("source", "")} for h in hits]

    async def resolve_entities(q: str) -> list[str]:
        from domain.spiritual_ontology import SEED_CONCEPTS
        ql = q.lower()
        return [c.uri for c in SEED_CONCEPTS
                if any(w in ql for w in c.label.lower().split())]

    async def traverse_graph(uris: list[str], max_hops: int):
        from app.dependencies import get_container
        cypher = """
        MATCH path = (c:Concept {uri: $uri})-[r*1..$hops]-(n)
        RETURN n.text AS text, n.uri AS uri, type(last(relationships(path))) AS relation,
               length(path) AS hop, n.source AS source
        LIMIT 40
        """
        rows = []
        driver = get_container().neo4j_driver
        if driver is None:
            return rows
        for u in uris:
            def _run(u=u):
                with driver.session() as session:
                    return list(session.run(cypher, {"uri": u, "hops": max_hops}))
            records = await asyncio.to_thread(_run)
            for record in records:
                rows.append({
                    "uri": record.get("uri"),
                    "text": record.get("text"),
                    "relation": record.get("relation"),
                    "hop": record.get("hop", 0),
                    "source": record.get("source"),
                })
        return rows

    return GraphRAGFusion(vector_search, resolve_entities, traverse_graph)


# ---------------------------------------------------------------------------
# Self-test with fakes
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    async def fake_vector(q, k):
        return [{"id": "v1", "text": "Breath awareness calms the mind.", "score": 0.9, "source": "doc:1"},
                {"id": "v2", "text": "Presence arises from stillness.", "score": 0.8, "source": "doc:2"}]

    async def fake_entities(q):
        return ["https://askmukthiguru.org/ontology/practice/breath-awareness"]

    async def fake_graph(uris, hops):
        return [{"uri": uris[0], "text": "Breath awareness leads to Presence.",
                 "relation": "LEADS_TO_STATE", "hop": 1, "source": "seed"},
                {"uri": "x", "text": "Breath awareness calms the mind.",
                 "relation": "RELATED", "hop": 1, "source": "seed"}]

    async def main():
        eng = GraphRAGFusion(fake_vector, fake_entities, fake_graph, token_budget=200)
        ctx = await eng.retrieve("How does breath awareness lead to presence?")
        assert ctx.multi_hop is True
        assert ctx.entities_touched
        assert any("calms the mind" in i.text for i in ctx.items)
        assert ctx.total_tokens <= 200
        print("graphrag fusion self-test OK —")
        print(f"  items={len(ctx.items)} multi_hop={ctx.multi_hop} tokens={ctx.total_tokens}")
        for i in ctx.items:
            print(f"  [{i.channel}] score={i.score} hop={i.provenance.get('hop')} :: {i.text[:45]}")

    import asyncio as _a
    _a.run(main())
