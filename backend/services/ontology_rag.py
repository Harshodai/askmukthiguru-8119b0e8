"""
Ontology-aware RAG retrieval (Task B2).

Enhances vector retrieval with ontological knowledge by expanding a
seeker's query into its spiritual-ontology neighbourhood (BFS over the
real Neo4j graph) and boosting retrieved documents that reference
multiple expanded concepts.

Tony Seale principle: "LLMs thrive on structure, not vibes." Structuring
retrieval around the formal ontology (domain/spiritual_ontology.py) gives
the LLM a reliable symbolic backbone for generation.

Real APIs (discovered, not imagined):
  - Neo4j driver: ``container.neo4j_driver`` (sync ``driver.session()``;
    nodes carry ``entity_id`` / ``name`` / ``description`` with labels
    ``Teacher`` / ``Concept`` / ``Practice`` / ``base``; relations include
    ``EXPOUNDS``). Never import seed_ontology.py.
  - EmbeddingService: ``await encode_single_async(text) -> list[float]``
    (dense 1024d) or ``encode_single_full_async`` for dense+sparse.
  - QdrantService: ``search(query_vector, limit, content_type=...,
    sparse_vector=..., raptor_level=..., **kwargs) -> list[dict]`` returning
    dicts with ``text`` / ``source_url`` / ``chunk_index`` / ``score`` /
    ``tags`` / ``topic`` / ``teacher_id`` (no ``concept_uri`` payload field,
    so concept overlap is measured against ``tags`` + text).

The ontology rerank boost is also exposed as an additive hook on
``RerankerService`` (``ontology_boost``) so the existing rerank pipeline
composes with ontology awareness rather than being replaced by it.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional

from domain.spiritual_ontology import ConceptType, SpiritualConcept

logger = logging.getLogger(__name__)


# Boost weights (analysis spec section 2.1).
_OVERLAP_BOOST = 0.1     # +0.1 per expanded concept referenced by the doc
_VALIDATED_BOOST = 0.05  # +0.05 for explicit ontology linkage

# BFS headroom (analysis spec: depth=2 default, LIMIT 10 per hop).
_DEFAULT_DEPTH = 2
_DEFAULT_HOP_LIMIT = 10
_CONFIDENCE_FLOOR = 0.5


class OntologyAwareRetriever:
    """Retrieve documents with ontological query expansion.

    Uses the formal spiritual ontology + the real Neo4j graph to expand a
    query into its concept neighbourhood, then reranks retrieved docs by
    ontological relevance (concept coverage + ontology validation).
    """

    def __init__(
        self,
        neo4j_driver: Any,
        embedding_service: Any,
        qdrant_service: Any,
        expansion_depth: int = _DEFAULT_DEPTH,
        hop_limit: int = _DEFAULT_HOP_LIMIT,
        confidence_floor: float = _CONFIDENCE_FLOOR,
    ) -> None:
        self.neo4j = neo4j_driver
        self.embeddings = embedding_service
        self.qdrant = qdrant_service
        self.expansion_depth = expansion_depth
        self.hop_limit = hop_limit
        self.confidence_floor = confidence_floor

    async def retrieve_with_ontology_expansion(
        self,
        query: str,
        top_k: int = 10,
        expansion_depth: Optional[int] = None,
    ) -> dict:
        """Retrieve documents with ontological query expansion.

        Steps:
          1. Embed the query (dense vector via the real EmbeddingService).
          2. Find matching concepts in the Neo4j graph by query-token overlap.
          3. BFS-expand the seed concepts via the ontology graph (depth N).
          4. Retrieve documents from Qdrant for the query vector.
          5. Deduplicate and rerank by ontological relevance.
        """
        depth = expansion_depth if expansion_depth is not None else self.expansion_depth

        query_embedding = await self.embeddings.encode_single_async(query)

        initial_concepts = await self._find_concepts_by_text(query)

        expanded_concepts = await self._expand_via_ontology(initial_concepts, depth=depth)

        docs = await self._retrieve_docs(query_embedding, top_k=max(top_k * 2, top_k))

        unique = self._deduplicate(docs)
        ranked = self._ontology_rerank(unique, expanded_concepts)

        return {
            "documents": ranked[:top_k],
            "concepts_used": [c.label for c in expanded_concepts],
            "expansion": {
                "initial": len(initial_concepts),
                "expanded": len(expanded_concepts),
            },
        }

    async def _find_concepts_by_text(self, query: str) -> list[SpiritualConcept]:
        """Find ontology concepts whose Neo4j name/entity_id match query tokens.

        The real Neo4j graph is not vector-indexed for this workload, so we
        match by case-insensitive CONTAINS against ``name``/``entity_id``.
        Returns at most ``hop_limit`` seed concepts to bound downstream work.
        """
        if self.neo4j is None:
            return []

        tokens = [t.strip().lower() for t in query.split() if len(t.strip()) > 2]
        if not tokens:
            return []

        cypher = """
        MATCH (n)
        WHERE any(tok IN $tokens WHERE toLower(coalesce(n.name, n.entity_id, '')) CONTAINS tok)
          AND (n:Concept OR n:Practice OR n:Teacher OR n:base)
        WITH n LIMIT $cap
        RETURN coalesce(n.entity_id, n.name) AS eid,
               n.name AS name,
               n.description AS description,
               labels(n) AS labels
        """

        def _run() -> list[SpiritualConcept]:
            out: list[SpiritualConcept] = []
            with self.neo4j.session() as session:
                result = session.run(cypher, tokens=tokens, cap=self.hop_limit)
                for rec in result:
                    eid = rec.get("eid") or rec.get("name")
                    if not eid:
                        continue
                    name = rec.get("name") or eid
                    labels = rec.get("labels") or []
                    out.append(
                        SpiritualConcept(
                            uri=f"neo4j://entity/{eid}",
                            label=name,
                            description=rec.get("description") or "",
                            concept_type=_label_to_concept_type(labels),
                            confidence=1.0,
                        )
                    )
            return out

        try:
            return await asyncio.to_thread(_run)
        except Exception as exc:  # noqa: BLE001
            logger.warning("ontology_rag: concept lookup failed: %s", exc)
            return []

    async def _expand_via_ontology(
        self,
        seed_concepts: list[SpiritualConcept],
        depth: int,
    ) -> list[SpiritualConcept]:
        """BFS-expand the seed set via the Neo4j graph (depth N, confidence>floor).

        Follows any relation type (``EXPOUNDS`` included) bidirectionally,
        keeping the highest-confidence neighbour of each hop up to
        ``hop_limit`` per expansion level to bound latency.
        """
        if depth <= 0 or not seed_concepts:
            return list(seed_concepts)

        seen_uris = {c.uri for c in seed_concepts}
        expanded = list(seed_concepts)
        frontier = list(seed_concepts)

        MAX_FRONTIER_WIDTH = 50
        MAX_TOTAL = 500

        for _hop in range(depth):
            if len(expanded) >= MAX_TOTAL:
                break
            next_frontier: list[SpiritualConcept] = []
            for concept in frontier:
                if len(next_frontier) >= MAX_FRONTIER_WIDTH:
                    break
                related = await self._get_related_concepts(concept.uri)
                for rel_concept, _relation, confidence in related:
                    if rel_concept.uri in seen_uris:
                        continue
                    if confidence <= self.confidence_floor:
                        continue
                    if len(expanded) >= MAX_TOTAL:
                        break
                    seen_uris.add(rel_concept.uri)
                    expanded.append(rel_concept)
                    next_frontier.append(rel_concept)
            if not next_frontier:
                break
            frontier = next_frontier

        return expanded

    async def _get_related_concepts(self, concept_uri: str) -> list[tuple]:
        """Get concepts related to ``concept_uri`` via the real Neo4j graph.

        The analysis imagined a ``Concept {uri}`` schema; the real graph keys
        nodes by ``entity_id`` / ``name`` (see kg.py). We therefore extract the
        entity_id from the URI suffix and match bidirectionally over any
        relation type, returning ``(SpiritualConcept, relation_type, confidence)``.
        """
        if self.neo4j is None:
            return []

        eid = concept_uri.rsplit("/", 1)[-1]
        if not eid:
            return []

        cypher = """
        MATCH (n)
        WHERE coalesce(n.entity_id, n.name) = $eid
        MATCH (n)-[r]-(m)
        WHERE coalesce(m.entity_id, m.name) IS NOT NULL
        WITH m, type(r) AS rel, coalesce(r.confidence, r.weight, 1.0) AS conf
        RETURN coalesce(m.entity_id, m.name) AS eid,
               m.name AS name,
               m.description AS description,
               labels(m) AS labels,
               rel AS relation,
               conf AS confidence
        ORDER BY confidence DESC
        LIMIT $cap
        """

        def _run() -> list[tuple]:
            out: list[tuple] = []
            with self.neo4j.session() as session:
                result = session.run(cypher, eid=eid, cap=self.hop_limit)
                for rec in result:
                    m_eid = rec.get("eid") or rec.get("name")
                    if not m_eid:
                        continue
                    concept = SpiritualConcept(
                        uri=f"neo4j://entity/{m_eid}",
                        label=rec.get("name") or m_eid,
                        description=rec.get("description") or "",
                        concept_type=_label_to_concept_type(rec.get("labels") or []),
                        confidence=float(rec.get("confidence") or 1.0),
                    )
                    out.append((concept, rec.get("relation") or "RELATED", float(rec.get("confidence") or 1.0)))
            return out

        try:
            return await asyncio.to_thread(_run)
        except Exception as exc:  # noqa: BLE001
            logger.warning("ontology_rag: related-concept lookup failed: %s", exc)
            return []

    async def _retrieve_docs(self, query_embedding: list[float], top_k: int) -> list[dict]:
        """Retrieve documents from Qdrant using the real search API.

        The real Qdrant payload has no ``concept_uri`` field, so we do a
        single hybrid search with the query vector and let
        ``_ontology_rerank`` apply the concept-coverage boost afterwards.
        """
        if self.qdrant is None:
            return []
        try:
            return await asyncio.to_thread(
                self.qdrant.search,
                query_embedding,
                top_k,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("ontology_rag: qdrant search failed: %s", exc)
            return []

    def _ontology_rerank(
        self,
        documents: list[dict],
        concepts: list[SpiritualConcept],
    ) -> list[dict]:
        """Rerank documents by ontological relevance (additive to base score).

        Boosts documents that:
          1. Reference multiple concepts from the expanded set (+0.1 / overlap).
          2. Carry explicit ontology validation (+0.05).
        Composes with the existing reranker: base ``rerank_score`` (if any)
        is preserved and the boost is added under ``ontology_boosted_score``.
        """
        concept_labels = {c.label.lower() for c in concepts if c.label}
        scored: list[dict] = []
        for doc in documents:
            base = float(doc.get("rerank_score", doc.get("score", 0.0)))
            text_low = (doc.get("text") or "").lower()
            tags_low = [str(t).lower() for t in (doc.get("tags") or [])]
            doc_concepts = {
                label for label in concept_labels
                if label and (label in text_low or label in tags_low)
            }
            overlap = len(doc_concepts)
            score = base + overlap * _OVERLAP_BOOST
            if doc.get("ontology_validated"):
                score += _VALIDATED_BOOST
            scored.append({
                **doc,
                "ontology_overlap": overlap,
                "ontology_boosted_score": score,
            })
        scored.sort(key=lambda d: d["ontology_boosted_score"], reverse=True)
        return scored

    def _deduplicate(self, documents: list[dict]) -> list[dict]:
        """Remove duplicate documents by stable identity (source_url + chunk_index)."""
        seen: set[str] = set()
        unique: list[dict] = []
        for doc in documents:
            doc_id = doc.get("id") or doc.get("doc_id")
            if doc_id is None:
                doc_id = f"{doc.get('source_url', '')}:{doc.get('chunk_index', '')}"
            if doc_id and doc_id not in seen:
                seen.add(doc_id)
                unique.append(doc)
        return unique


def _label_to_concept_type(labels: list[str]) -> ConceptType:
    """Map a Neo4j label set onto the ontology ConceptType enum (best-effort)."""
    label_set = {str(l).lower() for l in labels or []}
    if "practice" in label_set:
        return ConceptType.PRACTICE
    if "teacher" in label_set:
        return ConceptType.BEING
    if "text" in label_set:
        return ConceptType.TEXT
    if "tradition" in label_set:
        return ConceptType.TRADITION
    return ConceptType.PRINCIPLE


if __name__ == "__main__":
    # Self-check: construct the retriever with mock services matching the
    # real APIs (Neo4j sync driver, EmbeddingService.encode_single_async,
    # QdrantService.search) and run an ontology-expanded retrieval.

    class _MockNeo4jSession:
        def __init__(self, records: list[dict]) -> None:
            self._records = records

        def run(self, cypher, **params):
            return iter(self._records)

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    class _MockNeo4jDriver:
        # Seed concepts + one BFS hop returning a related concept.
        _seed_records = [
            {"eid": "breath_awareness", "name": "Breath Awareness",
             "description": "Observing the natural flow of breath.",
             "labels": ["Practice"]},
        ]
        _related_records = [
            {"eid": "presence", "name": "Presence",
             "description": "Being fully aware in the current moment.",
             "labels": ["base"], "relation": "EXPOUNDS", "confidence": 0.9},
        ]

        def session(self):
            # Distinguish seed-lookup vs related-lookup by the `cap` param is
            # ambiguous; branch on whether `tokens` (seed) or `eid` (related)
            # is present. We emulate by returning seed records only when
            # `tokens` is provided.
            def factory(*_args, **params):
                if "tokens" in params:
                    return iter(self._seed_records)
                if "eid" in params:
                    return iter(self._related_records)
                return iter([])
            # session.run(...) is the real call shape; return a session-like
            # object whose .run dispatches.
            class _S:
                def run(_self, cypher, **params):
                    return factory(cypher, **params)
                def __enter__(_self):
                    return _self
                def __exit__(_self, *exc):
                    return False
            return _S()

    class _MockEmbeddings:
        async def encode_single_async(self, text: str) -> list[float]:
            return [0.1] * 8

    class _MockQdrant:
        def search(self, query_vector, limit, **kwargs):
            return [
                {"id": "d1", "text": "Breath Awareness practice and Presence.",
                 "source_url": "u1", "chunk_index": 0, "score": 0.8,
                 "tags": ["breath awareness", "presence"]},
                {"id": "d2", "text": "Unrelated text.", "source_url": "u2",
                 "chunk_index": 0, "score": 0.5, "tags": []},
            ]

    async def _main() -> None:
        retriever = OntologyAwareRetriever(
            neo4j_driver=_MockNeo4jDriver(),
            embedding_service=_MockEmbeddings(),
            qdrant_service=_MockQdrant(),
        )
        result = await retriever.retrieve_with_ontology_expansion("breath awareness", top_k=5)
        docs = result["documents"]
        concepts_used = result["concepts_used"]
        print(f"docs returned: {len(docs)}")
        print(f"concepts_used: {concepts_used}")
        assert len(docs) >= 1, "expected at least one doc"
        assert "Breath Awareness" in concepts_used, "seed concept missing"
        assert "Presence" in concepts_used, "expanded concept missing"
        print("B2 OK")

    asyncio.run(_main())