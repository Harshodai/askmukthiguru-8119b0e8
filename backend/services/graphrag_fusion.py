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

# Deep variable-length traversals (r*1..N) grow super-linearly — a caller or
# config mistake (or a hostile request field) must never escalate into a
# graph-traversal DoS, so the hop count is clamped at the call boundary.
MAX_HOPS = 3

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
        max_concurrency: int = 4,
        per_traversal_timeout: float = 5.0,
        total_timeout: float = 10.0,
        semaphore: Optional[asyncio.Semaphore] = None,
    ) -> None:
        self._vector = vector_search
        self._entities = resolve_entities
        self._graph = traverse_graph
        # Clamp at the call boundary: unbounded $hops in the Cypher
        # variable-length pattern (r*1..$hops) makes traversal cost grow
        # super-linearly with the hop count (P1-BE-6).
        self.max_hops = min(max(int(max_hops), 1), MAX_HOPS)
        self.token_budget = token_budget
        self.vector_top_k = vector_top_k
        self.enable_graph = enable_graph
        self.max_concurrency = max(1, int(max_concurrency))
        self.per_traversal_timeout = float(per_traversal_timeout)
        self.total_timeout = float(total_timeout)
        self._injected_semaphore = semaphore
        # Lazily-created semaphores keyed by id(running loop): asyncio.Semaphore
        # is bound to the loop it was created on, so a shared semaphore built on
        # loop A raises RuntimeError when acquired from loop B. One per loop.
        self._semaphores: dict[int, asyncio.Semaphore] = {}

    def _get_semaphore(self) -> asyncio.Semaphore:
        if self._injected_semaphore is not None:
            return self._injected_semaphore
        key = id(asyncio.get_running_loop())
        sem = self._semaphores.get(key)
        if sem is None:
            sem = asyncio.Semaphore(self.max_concurrency)
            self._semaphores[key] = sem
        return sem

    async def retrieve(self, question: str) -> FusedContext:
        """Run both channels concurrently, fuse, budget, return with concurrency bounds & deadlines.

        The ``total_timeout`` deadline starts when ``retrieve`` is entered, so a
        busy concurrency pool cannot push a retrieval past its deadline: slot
        acquisition is bounded by the remaining time, and a retrieval that
        cannot acquire a slot in time degrades to an empty context instead of
        hanging. Once the slot is acquired, behavior is unchanged.
        """
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self.total_timeout
        sem = self._get_semaphore()

        try:
            await asyncio.wait_for(
                sem.acquire(),
                timeout=max(0.0, deadline - loop.time()),
            )
        except asyncio.TimeoutError:
            logger.warning(
                "GraphRAG retrieval deadline (%.1fs) expired while waiting for a concurrency slot",
                self.total_timeout,
            )
            return FusedContext(items=[], total_tokens=0, multi_hop=False, entities_touched=[])

        try:
            vector_task = asyncio.create_task(self._safe_vector(question))
            graph_task = asyncio.create_task(self._safe_graph(question))
            vector_hits: list[dict] = []
            graph_hits: list[dict] = []
            entities: list[str] = []

            try:
                vector_hits, (graph_hits, entities) = await asyncio.wait_for(
                    asyncio.gather(vector_task, graph_task),
                    timeout=max(0.0, deadline - loop.time()),
                )
            except asyncio.TimeoutError:
                logger.warning(
                    "GraphRAG retrieval aggregate deadline (%.1fs) exceeded, cancelling outstanding subtasks",
                    self.total_timeout,
                )
                # Cancel outstanding subtasks if aggregate deadline expires
                for task in (vector_task, graph_task):
                    if not task.done():
                        task.cancel()

                # Safe partial result or documented degraded path on timeout rather than hanging
                if vector_task.done() and not vector_task.cancelled():
                    try:
                        vector_hits = vector_task.result()
                    except Exception as exc:
                        logger.debug("vector task error during partial recovery: %s", exc)
                        vector_hits = []

                if graph_task.done() and not graph_task.cancelled():
                    try:
                        res = graph_task.result()
                        if isinstance(res, tuple) and len(res) == 2:
                            graph_hits, entities = res
                    except Exception as exc:
                        logger.debug("graph task error during partial recovery: %s", exc)
                        graph_hits, entities = [], []

            fused = reciprocal_rank_fusion(vector_hits, graph_hits)
            bounded = self._budget(fused)
            return FusedContext(
                items=bounded,
                total_tokens=sum(i.token_estimate for i in bounded),
                multi_hop=any(i.provenance.get("hop", 0) > 0 for i in bounded),
                entities_touched=entities,
            )
        finally:
            sem.release()

    # ---- channels ----

    async def _safe_vector(self, question: str) -> list[dict]:
        try:
            return await asyncio.wait_for(
                self._vector(question, self.vector_top_k),
                timeout=self.per_traversal_timeout,
            )
        except asyncio.TimeoutError:
            logger.warning("vector channel timed out after %.1fs", self.per_traversal_timeout)
            return []
        except Exception as exc:
            logger.warning("vector channel failed: %s", exc)
            return []

    async def _safe_graph(self, question: str) -> tuple[list[dict], list[str]]:
        if not self.enable_graph:
            return [], []
        try:
            entities = await asyncio.wait_for(
                self._entities(question),
                timeout=self.per_traversal_timeout,
            )
            if not entities:
                return [], []
            hits = await asyncio.wait_for(
                self._graph(entities, self.max_hops),
                timeout=self.per_traversal_timeout,
            )
            return hits, entities
        except asyncio.TimeoutError:
            logger.warning("graph channel timed out after %.1fs", self.per_traversal_timeout)
            return [], []
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
