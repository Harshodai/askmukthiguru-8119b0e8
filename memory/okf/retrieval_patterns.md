# OKF: Retrieval & RAG Patterns

> **Source:** Backend RAG node audit + 2026 RAG best practices research
> **Domain:** Retrieval, Semantic Search, Memory Layer
> **Last updated:** 2026-07-04

## Retrieval Hierarchy (Fast → Deep)

```
Query → Semantic Router (embedding-based, zero-LLM)
      → Fast Graph (retrieval_fast): dense Qdrant search, top_k=5, no reranking
      → Standard Graph (retrieval): hybrid (dense + sparse) + cross-encoder reranking
      → Deep Graph (retrieval_deep): RAPTOR tree traversal + GraphRAG + Neo4j subgraph
```

## Hybrid Search Formula

```
score = α * dense_similarity + (1-α) * sparse_bm25_score
α = settings.rag_dense_weight (default: 0.7)
```
Sparse (BM25) weights improve recall for exact spiritual term matches (e.g., "Deeksha", "Oneness").

## RAPTOR (Recursive Abstractive Processing)

- Builds a **tree** of summaries from leaf chunks upward
- Level 0 = raw chunks, Level 1 = paragraph summaries, Level 2+ = topic summaries
- Retrieval: searches ALL levels, returns best match at any level
- Config: `raptor_parent_summaries_enabled=True`, `raptor_levels=3`
- **Never disable** for long-form spiritual content — it's what enables "zoom-out" answers

## LightRAG / GraphRAG

- **Entity extraction:** After every ingestion, LightRAG extracts entities + relations to Neo4j
- **Graph retrieval:** For "compare X and Y" or "relationship between..." queries
- **Implicit Teachings Connector:** Post-ingestion, connects new chunks to existing Neo4j concepts
  - Threshold: `CONCEPT_SIMILARITY_THRESHOLD` (from `app/constants.py`)
  - Relation types: `RELATED_TO`, `EXPANDS_ON`, `CONTRADICTS`

## Memory Layer (OKF)

The OKF (Omniscient Knowledge Framework) acts as the canonical spiritual knowledge layer:
- **Location:** `memory/okf/*.md` files
- **Auto-injection:** `rag_okf_injection_enabled=True` → OKF context prepended to every LLM call
- **Auto-extraction:** `rag_okf_auto_extract_enabled=True` → new teachings extracted post-ingestion
- **Priority:** OKF context ranks ABOVE vector search results in final answer generation

## Semantic Cache

- **L1:** GPTCache (semantic similarity) — hits when new query ≈ previous query
- **L2:** Redis (exact TTL cache) — hits on identical query strings
- **Invalidation:** On ingestion, `semantic_cache.invalidate_by_embedding(emb)` for all new chunks
- **Never disable** in production — critical for sub-100ms P50 latency

## P90/P99 Targets

| Mode | P50 | P90 | P99 |
|------|-----|-----|-----|
| Cache hit | < 50ms | < 100ms | < 200ms |
| Fast graph | < 500ms | < 1s | < 2s |
| Standard | < 2s | < 4s | < 8s |
| Deep | < 5s | < 10s | < 20s |

## Key Anti-Patterns

- **Never skip reranking** in Standard/Deep mode — raw embedding scores are unreliable for spiritual nuance
- **Never increase `rag_top_k` beyond 20** without increasing `context_window_total` — silent truncation
- **Never bypass `important_kwd_boost_enabled`** — doctrine keywords (Deeksha, Karma, etc.) must boost recall
- **Missing Neo4j** = graceful degradation — GraphRAG silently skipped but vector search still works

## Spiritual Ontology (Audit V2 Recommendation)

Planned Neo4j schema for cross-teacher reasoning:
```cypher
(Teacher)-[:EXPOUNDS]->(Concept)
(Concept)-[:CONTRASTS_WITH]->(Concept)
(Practice)-[:PRACTICE_FOR]->(Concept)
(Chunk)-[:RELATED_TO|EXPANDS_ON|CONTRADICTS]->(Entity)
```
