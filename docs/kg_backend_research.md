# Knowledge Graph Backend Research — Neo4j vs FalkorDB vs Graphiti vs TypeDB

> **Task H1.2** — Source: `Knowledge Graph & RAG Research Findings (2026).md` (uncommitted research brief).
> **Scope**: Evaluate whether AskMukthiGuru should keep Neo4j (current KG backend) or migrate to an alternative graph engine, given the spiritual-Q&A workload: teacher-specific subgraphs, ontology expansion, concept relationships, and GraphRAG retrieval.

---

## 1. Executive Summary

AskMukthiGuru's current Knowledge Graph runs on **Neo4j 5.17** with the `apoc` and `n10s` (neosemantics) plugins, holding ~7,481 nodes across an ontology of Teachers, Concepts, and Practices. The graph backs three concrete features today:

1. **Concept-subgraph retrieval** for the KG visualizer (`GET /api/kg/subgraph` — 1-2 hop Cypher neighborhood, see `backend/app/api/kg.py:151`).
2. **Ontology seeding & constraints** — uniqueness on Teacher/Concept/Practice names (`backend/app/db/seed_ontology.py:33`).
3. **LightRAG co-schema** — dual-labelled nodes (`:base {entity_id}` from LightRAG + typed labels like `:Teacher`), enabling graph+vector hybrid retrieval.

The 2026 research brief (`Knowledge Graph & RAG Research Findings`) surveyed four candidate GraphRAG backends: **FalkorDB, Microsoft GraphRAG, LightRAG, Graphiti, and TypeGraph**. Of these, LightRAG is already partially integrated, and Microsoft GraphRAG is a pipeline (not a store), so it is out of scope for a backend swap.

**Recommendation: keep Neo4j as the primary KG store; adopt FalkorDB only as an optional low-latency read replica if query-p95 budgets break.** Rationale:

- The workload is ontology-first (typed nodes, uniqueness constraints, OWL/RDFS inference via `n10s`). None of the alternatives match Neo4j's constraint + plugin maturity for this shape.
- Migration cost is non-trivial (re-rewrite `kg.py`, `seed_ontology.py`, and the LightRAG bridge) for a latency gain that is better bought with local embeddings + semantic caching first (the research brief's own §2).
- Graphiti and TypeDB target different workloads (temporal/episodic memory and schema-first type reasoning, respectively) — useful as *adjuncts*, not replacements.

The rest of this doc substantiates that call with per-engine architecture, strengths/weaknesses, suitability scoring, latency strategies, MS GraphRAG findings, migration cost estimate, and a phased adoption plan.

---

## 2. Comparison Matrix

| Dimension | **Neo4j 5.17 (current)** | **FalkorDB** | **Graphiti (Zep)** | **TypeDB / TypeGraph** |
|---|---|---|---|---|
| Architecture | JVM, native graph store, disk-backed with page cache | C++ in-memory, Redis-on-Rocks persistence, multi-tenant | Python service over Postgres + Neo4j/FalkorDB, temporal-aware | Schema-first typed-reasoning DB; TypeGraph adds LLM-friendly schema gen |
| Query language | Cypher (GQL-aligned) | Cypher-compatible (openCypher subset) | Python SDK + Cypher pass-through; bi-temporal edges | TypeQL (declarative, type-theoretic) — not Cypher |
| Schema model | Optional labels + constraints; OWL/RDFS via n10s | Property graph, label-based | Temporal property graph (episode-scoped facts) | Strongly typed, rule-inferencing, hypergraph-safe |
| Plugins | apoc, n10s (neosemantics), GDS | GraphRAG-first; fewer plugins | Built for agents, bi-temporal | Native reasoner, no external plugin needed |
| Latency profile | ~5-20 ms per Cypher hop on warm cache; JVM overhead | Sub-ms in-memory reads; built for GraphRAG real-time | Service-layer latency dominates; Postgres-backed | Query planning cost higher; designed for reasoning, not hot-path retrieval |
| Ecosystem maturity | Very high; LLM Graph Builder, GraphRAG integrations | Growing; Cypher portability helps | Niche but active (Zep memory) | Smaller community; strong in knowledge-graph reasoning niches |
| Multi-tenancy | DB-per-tenant or label partition | Native multi-tenant (one DB, many graphs) | Per-user episodic scoping | DB-per-type-system |
| Operational cost | JVM heap tuning, APOC maintenance | Simpler ops; less tuning surface | Postgres + graph store + service → 3 moving parts | TypeDB server + schema migrations |
| Fit for spiritual-Q&A workload | **High** — constraints, ontology, NL2Cypher tooling | **Medium-High** — fast reads, but loses n10s inference + APOC | **Low-Medium** — wrong shape (episodic, not encyclopaedic) | **Medium** — strong on ontology, weak on hot-path retrieval |

---

## 3. Per-Engine Deep Dive

### 3.1 Neo4j (current)

**Architecture.** Disk-backed native graph with a JVM page cache, Bolt protocol, Cypher query language. Plugins in use: `apoc` (procedures), `n10s`/neosemantics (OWL/RDFS import + inference). The current schema seeds Teachers (`:Teacher:person` / `:Teacher:organization`), Concepts (`:Concept`), and Practices (`:Practice`) with uniqueness constraints (`backend/app/db/seed_ontology.py:33-35`). LightRAG writes dual-labelled `:base {entity_id}` nodes so the graph is queryable both via LightRAG's entity_id and the typed ontology.

**Strengths for this use case**
- **Ontology fidelity.** Label-based typing + uniqueness constraints map cleanly to "one Teacher named Sadhguru, one Concept named Karma." `n10s.inference.nodesLabelled` enables RDFS/OWL inference at query time — essential for ontology expansion (e.g., "is Ekam a Practice or an Organization?").
- **Cypher tooling.** NL2Cypher patterns, the Neo4j LLM Knowledge Graph Builder, and GraphRAG-from-Neo4j tutorials are all directly reusable. The `kg.py` subgraph query is a 6-line Cypher block.
- **Teacher-specific subgraphs.** `teacher_id` property on Teacher nodes (`seed_ontology.py:48-76`) gives cheap partitioning; a Cypher `WHERE n.teacher_id = $tid` is a one-line filter.
- **Mature ops.** Docker image, backups, metrics, GDS for graph algorithms (PageRank, community detection) if concept-clustering is added later.

**Weaknesses**
- JVM warm-up and heap tuning add operational weight vs a C++ store.
- Read latency (~5-20 ms/hop on warm cache) is fine for current scale but could become the bottleneck at sub-second TTFT targets.
- APOC and n10s are "labs" plugins; version drift risk on Neo4j upgrades (n10s 5.x dropped SPARQL — `kg.py:4` already documents this).

**Suitability: 8/10.** The ontology + teacher-subgraph workload is Neo4j's sweet spot. The only real threat is raw retrieval latency.

### 3.2 FalkorDB

**Architecture.** C++ in-memory graph database with Redis-on-Rocks persistence, Cypher-compatible query language, built explicitly for GraphRAG and real-time analytics. Multi-tenant by design (one instance, many graph keys).

**Strengths**
- **Latency.** Sub-millisecond in-memory reads; the research brief's §2 explicitly names FalkorDB for hybrid search where "local vector search + local graph traversal avoids the overhead of multiple LLM calls during retrieval."
- **Cypher portability.** The `kg.py` subgraph Cypher is largely portable; `seed_ontology.py` MERGE/constraint statements would need light rewriting (FalkorDB supports `MERGE` and index-based uniqueness, not full Neo4j constraint syntax).
- **Multi-tenancy.** Teacher-specific subgraphs could map to separate graph keys — clean isolation per tradition (Sadhguru vs ISKCON vs Ekam).
- **Footprint.** Single C++ binary, no JVM — simpler Docker image, lower memory floor.

**Weaknesses**
- **No n10s equivalent.** OWL/RDFS inference at query time is gone. Ontology expansion would need to move into either (a) materialized labels at write time, or (b) a Python-side inference layer.
- **No APOC.** Procedures like `apoc.cypher.runFiles` (bulk load), `apoc.path.expand` (bounded traversal) — used implicitly by the ingestion pipeline — have no drop-in equivalent. Migration means rewriting those code paths.
- **Plugin ecosystem thinner.** GDS algorithms (PageRank, community detection) are not available; would need an external compute step.
- **Constraint maturity.** FalkorDB's uniqueness guarantees are index-based, not Neo4j-style schema constraints. Race-condition risk on concurrent `MERGE` of the same Concept.

**Suitability: 7/10.** Excellent for the *retrieval* hot path; loses ground on the *ontology* cold path. Best deployed as a read-side accelerator alongside Neo4j, not as a replacement.

### 3.3 Graphiti (by Zep)

**Architecture.** Python service layer that maintains a *temporal* knowledge graph over Postgres + a backing graph store (Neo4j or FalkorDB). Designed for agent long-term memory: facts are scoped to "episodes" with bi-temporal edges (valid-time + transaction-time).

**Strengths**
- **Temporal reasoning.** "Sadhguru taught X in 2018, revised it in 2023" is a first-class query. Relevant if AskMukthiGuru wants to model doctrinal evolution across teachers.
- **Agent-native.** Built for LLM agents that update the graph during conversations — fits the agentic-GraphRAG pattern in research brief §3 ("autonomous agents extract entities asynchronously during ingestion").
- **Bi-temporal edges.** Useful for citation provenance ("this concept relationship came from talk Y on date Z").

**Weaknesses**
- **Wrong primary shape.** AskMukthiGuru's KG is an *encyclopaedia* of eternal spiritual concepts (Karma, Dharma), not an *episodic* memory. Temporal scoping adds overhead with little benefit for 90% of queries ("what is Karma according to Sadhguru?").
- **Operational stack.** Postgres + graph store + Python service = three moving parts vs one Neo4j container.
- **No native Cypher inference.** Inherits the backing store's limitations (if FalkorDB-backed, loses n10s; if Neo4j-backed, no improvement).

**Suitability: 4/10.** A mismatch for the core workload. Worth considering *only* if a future feature tracks teacher-talk provenance over time — and even then, it would sit alongside the main ontology store, not replace it.

### 3.4 TypeDB / TypeGraph

**Architecture.** TypeDB is a strongly-typed, schema-first database with a declarative query language (TypeQL) and a native reasoner. TypeGraph is the newer LLM-oriented layer that generates typed schemas for graph construction. Relations are first-class citizens (not just edges), and the type system supports inheritance and role constraints.

**Strengths**
- **Ontology expressiveness.** TypeDB's type system is *exactly* what an ontology wants: "A `Teacher` is a subtype of `Person` or `Organization`; a `Teaches` relation has roles `teacher` and `concept`." This is far richer than Neo4j labels.
- **Native reasoning.** Inference is built-in, not a plugin. "Find all Practices taught by teachers in the Bhakti tradition" can be a single TypeQL rule, not a multi-hop Cypher + n10s dance.
- **Schema-first.** Reduces data-quality drift — the kind of issue flagged in `docs/DATA_QUALITY_AUDIT.md`. TypeDB rejects ill-typed writes at the DB layer.

**Weaknesses**
- **Not Cypher.** Every query in `kg.py`, `seed_ontology.py`, and the LightRAG bridge would be rewritten in TypeQL. NL2Cypher tooling (LangChain, LlamaIndex) does not apply; NL2TypeQL is far less mature.
- **Hot-path latency.** TypeDB's query planner is optimized for reasoning, not sub-ms retrieval. For a chat-bot's retrieval step, this is the wrong trade-off.
- **Ecosystem size.** Smaller community, fewer LLM integrations, fewer managed-hosting options. The research brief lists TypeGraph as a "newer tool" — early-stage risk.
- **No LightRAG bridge.** The current `:base {entity_id}` dual-labelling scheme is Neo4j-specific; moving to TypeDB means re-architecting the LightRAG integration.

**Suitability: 5/10.** Conceptually the *best fit* for the ontology, but operationally the *worst fit* for the retrieval hot path and the existing toolchain. Consider as a *secondary* reasoning store for complex doctrinal queries, not the primary retrieval store.

---

## 4. Latency & Retrieval Strategies (from research brief §2)

The research brief is explicit that the biggest latency wins are *not* a graph-engine swap. In priority order, per the brief:

1. **Local embedding models.** Pre-download `BAAI/bge-m3` or `intfloat/multilingual-e5-small` into the Docker image. Gold standard for sub-second TTFT. **Already partially in place** — see `embedding_service.py` in the source bundle.
2. **Quantization.** 4-bit/8-bit via vLLM or Ollama reduces memory and latency. Aligns with the existing Ollama host setup.
3. **Hybrid search.** Combine local vector search (Qdrant) with local graph traversal (Neo4j/FalkorDB) to avoid multiple LLM calls during retrieval. The current pipeline already does Qdrant + Neo4j; the research brief flags this as the right architecture.
4. **Semantic caching.** Qdrant or Redis caching of common queries + their graph/vector results. **Already in place** — GPTCache + Redis (see `AGENTS.md` "Cache Management" section).

**Implication for backend choice:** The latency bottleneck is *not* the graph engine. Swapping Neo4j → FalkorDB for a ~10-15 ms/hop saving is dominated by embedding + LLM-call latency (100s of ms each). **Invest in the brief's §2 strategies before considering a graph migration.**

---

## 5. Microsoft GraphRAG Findings

The research brief §1 lists Microsoft GraphRAG as "a modular data pipeline for extracting structured data from unstructured text. Excellent for complex reasoning but can be heavy on ingestion."

**Relevance to AskMukthiGuru:**
- MS GraphRAG is a **pipeline**, not a store. It produces community summaries and hierarchical clustering over a corpus, typically writing to Neo4j or a parquet store. It does not compete with Neo4j for the *backend* role.
- **Ingestion cost.** The brief's "heavy on ingestion" warning matches the repo's own experience: the ingestion pipeline maintains resumption checkpoints in `scripts/ingestion_state.json` (per `AGENTS.md`). MS GraphRAG's full-corpus community detection would require re-indexing when the ontology expands — at odds with the brief's §3 recommendation of *incremental updates*.
- **Where it fits:** As an *optional enrichment* step for concept-clustering (the GDS PageRank/community-detection use case noted in §3.1), run as a batch job writing results back to Neo4j. Not a replacement, not a daily hot-path component.

---

## 6. Recommendation

### Keep Neo4j as primary. Conditional FalkorDB read-replica.

**Primary store: Neo4j 5.17+ (no change).** The ontology, constraints, n10s inference, Cypher tooling, and LightRAG dual-labelling are all load-bearing. No alternative matches this combination. The migration cost (see §7) is not justified by the latency gap, which is better closed via local embeddings + quantization + caching.

**Conditional read replica: FalkorDB.** Adopt FalkorDB *only if* all of the following hold:
- P95 retrieval latency remains above the TTFT target *after* local embeddings, quantization, and semantic caching are in place.
- The hot-path query set is small and stable (the subgraph + concept-neighborhood queries in `kg.py`).
- The ontology expansion feature can tolerate materialized-label inference (write-time) instead of query-time `n10s` inference.

In that scenario, FalkorDB serves the read hot-path (sub-ms neighborhood queries) while Neo4j remains the source of truth for writes, constraints, and inference. Sync via a CDC stream (Neo4j → Kafka → FalkorDB) or periodic export. This is the standard CQRS-with-read-replica pattern; FalkorDB's Cypher compatibility makes the query port near-trivial.

**Do not adopt Graphiti or TypeDB as primary.** Graphiti's episodic model and TypeDB's TypeQL rewrite cost both fail the cost/benefit test for the core workload. Track them as candidates for *future adjunct features* (Graphiti for talk-provenance tracking; TypeDB for a doctrinal-reasoning service).

---

## 7. Migration Cost Estimate

Two scenarios, scoped to the code paths in `backend/app/api/kg.py` and `backend/app/db/seed_ontology.py` plus the LightRAG bridge in `backend/app/pipeline/stages/graph_stage.py` and `services/`.

### Scenario A: Neo4j → FalkorDB (full migration)

| Item | Effort | Risk |
|---|---|---|
| Rewrite `seed_ontology.py` constraint/MERGE syntax | 0.5 day | Low — FalkorDB supports MERGE + index uniqueness |
| Port `kg.py` subgraph Cypher | 0.5 day | Low — Cypher mostly portable |
| Replace `n10s.inference.nodesLabelled` with materialized-label write-time inference | 2-3 days | **High** — loses query-time inference; ontology expansion feature degrades or needs a Python-side reasoner |
| Replace APOC procedures in ingestion pipeline | 2-4 days | **Medium-High** — must audit every `apoc.*` call site |
| Re-architect LightRAG `:base` dual-labelling | 1-2 days | Medium — LightRAG's Neo4j writer is assumed; FalkorDB writer exists but needs validation |
| Re-ingest 7,481 nodes + edges | 0.5 day (run) + verification | Medium — data integrity check on constraints |
| Update Docker Compose, config, env vars, docs | 0.5 day | Low |
| **Total** | **~6-9 engineer-days** | **Medium-High** (n10s inference loss is the blocker) |

**Net risk:** The migration is feasible but *loses ontology inference capability*, which is a core feature for a spiritual knowledge graph where concept taxonomy (is Ekam a Practice or an Organization? is Bhakti a subtype of Yoga?) matters. This is the single strongest argument against a full migration.

### Scenario B: Neo4j primary + FalkorDB read replica (recommended if any migration)

| Item | Effort | Risk |
|---|---|---|
| Add FalkorDB container to docker-compose | 0.5 day | Low |
| Build Neo4j → FalkorDB sync (CDC or periodic export) | 2-3 days | Medium — CDC tooling maturity |
| Port read-only `kg.py` subgraph query to FalkorDB path | 0.5 day | Low |
| Routing layer: hot-path reads → FalkorDB, writes/ontology → Neo4j | 1 day | Medium — must avoid stale-read bugs |
| **Total** | **~4-5 engineer-days** | **Medium** (sync consistency is the only real risk) |

This preserves all Neo4j capabilities while buying the latency win on the read hot path. Only worth doing *after* the §4 latency strategies are exhausted.

---

## 8. Phased Adoption Plan

1. **Phase 0 (now): No backend change.** Exhaust the research brief's §2 latency strategies — confirm local embeddings, quantization, semantic caching are fully landed. Measure P95 retrieval latency. *Exit criterion: documented latency budget showing graph-read time is still the bottleneck.*
2. **Phase 1 (conditional): FalkorDB read replica.** Implement Scenario B only if Phase 0's exit criterion is met. Keep Neo4j as source of truth. *Exit criterion: P95 subgraph query < target TTFT, no stale-read incidents in 2-week soak.*
3. **Phase 2 (future, tracked): Graphiti for talk-provenance.** Only if a feature is added that needs "who taught what, when" temporal querying. Sits alongside Neo4j, not replacing it.
4. **Phase 3 (future, tracked): TypeDB for doctrinal reasoning.** Only if complex ontology reasoning (subtype queries, rule-based inference) outgrows n10s. Sits alongside Neo4j as a reasoning service, not the primary store.

---

## 9. References

- **Source research brief**: `Knowledge Graph & RAG Research Findings (2026).md` (uncommitted, in `~/Downloads/How to Enhance and Scale the AskMukthiGuru Repo_/`).
- **FalkorDB**: https://github.com/FalkorDB/FalkorDB
- **Microsoft GraphRAG**: https://microsoft.github.io/graphrag/
- **Zep Graphiti**: https://github.com/getzep/graphiti
- **Neo4j LLM Knowledge Graph Builder**: https://neo4j.com/blog/developer/knowledge-graph-extraction-challenges/
- **Current backend code**: `backend/app/api/kg.py`, `backend/app/db/seed_ontology.py`, `backend/app/pipeline/stages/graph_stage.py`.
- **Config**: `backend/app/config.py:146-149` (Neo4j URI/user/password), `backend/requirements.txt` (`neo4j>=5.17.0`).