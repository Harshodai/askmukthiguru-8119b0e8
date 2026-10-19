<!-- Archived verbatim from root CLAUDE.md on 2026-10-19 to cut per-session context cost. Not auto-loaded. Text is dated: verify against code and lessons.md before relying on any number. -->

# Archived from CLAUDE.md: database-and-graph

## Graph Database Architecture & Memgraph Migration Decision (2026-09-15)

- **Decision**: Migrate from Neo4j 5.x to **Memgraph (C++)** (`memgraph/memgraph-mage:latest`).
- **Context & Problem**: Neo4j was causing severe memory hikes/spikes (700MB to 1.5GB+ RAM idle/under load) due to JVM runtime overhead, a 512MB pagecache allocation, and Graph Data Science (GDS) native memory on an 8,750-node graph (~10MB raw data).
- **Alternative Survey & Rejection Rationale**:
  - *FalkorDB*: Rejected due to SSPLv1 license (not OSI open source), serialized writes per graph (chokes multi-worker video/LightRAG ingestion), lack of native LightRAG support, and experimental Bolt protocol.
  - *Kùzu / LadybugDB*: Rejected due to supply-chain risk (Kùzu was acquired by Apple in October 2025 and archived; LadybugDB is an early-stage community fork).
  - *Apache AGE*: Evaluated as a zero-container option inside PostgreSQL, but rejected due to lack of Bolt protocol and clumsy SQL-wrapped Cypher syntax (`SELECT * FROM cypher(...)`).
  - *Memgraph*: Selected as the optimal drop-in replacement.
- **Key Invariants & Guarantees**:
  1. **100% Bolt-Protocol Compatible**: Runs on port 7687 using the standard `neo4j` Python driver (`neo4j==6.2.0`). Existing queries across `cross_teacher_reasoning.py`, `memory_service_v2.py`, and `provenance_ontology_service.py` work without syntax rewrites.
  2. **LightRAG Native Support**: Uses `lightrag-hku`'s built-in `graph_storage="MemgraphStorage"` driven by `MEMGRAPH_URI` / `MEMGRAPH_USERNAME` / `MEMGRAPH_PASSWORD`.
  3. **Memory Footprint**: Measured at **570.6 MiB live resident memory / 1 GiB limit** (node/rel counts: 6,430 nodes / 4,188 rels). Still a significant reduction vs Neo4j JVM's ~700MB–1.5GB with zero JVM garbage collection pauses (matches AMK-F-009).
  4. **Graph Algorithms**: Replaces Neo4j GDS plugin with Memgraph's native MAGE library (`pagerank.get`, `community_detection.get`).
  5. **Backward Compatibility**: `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD` environment variables remain supported as aliases for `MEMGRAPH_*`.

### Transitioning Railway from Neo4j to Memgraph
In `deploy_railway.sh`, Neo4j was previously deployed using a template:
```bash
# Previously:
railway deploy --template neo4j
set_var NEO4J_URI "bolt://neo4j.railway.internal:7687"
```
Because Memgraph speaks the exact same openCypher Bolt protocol as Neo4j (`neo4j==6.2.0` Python driver):
- You simply deploy a Memgraph container on Railway using `memgraph/memgraph-mage:latest` with a persistent volume mounted to `/var/lib/memgraph`.
- Set `NEO4J_URI="bolt://memgraph.railway.internal:7687"` and `LIGHTRAG_GRAPH_STORAGE="MemgraphStorage"`.
- **Zero code changes are required on the backend**. The backend treats Memgraph as a drop-in, sub-millisecond Bolt database.
- **Scalability**: Single-node Memgraph easily scales to 100k+ nodes and 500k+ edges within a 1GB–2GB RAM container, operating 4.3x faster than Neo4j with zero GC pauses and cutting database hosting costs by >60%.
- **Decision Confirmed (2026-09-19)**: Neo4j is decommissioned in favor of Memgraph (C++) exclusively. Local Docker holds authoritative Memgraph data (6,430 nodes / 4,188 relationships). Bolt-based migration via `backend/scripts/ops/migrate_neo4j_to_memgraph.py` is tested and verified.

### Advanced Database Enhancements (Qdrant, Memgraph, LightRAG — 2026 Production Standard)

#### 1. Qdrant: 5 SOTA Upgrades
1. **Server-Side Universal Fusion (RRF & DBSF)**:
   - Uses Qdrant's Universal Query API (`client.query_points`) with multi-vector `models.Prefetch` sub-queries (dense 1024d + sparse lexical).
   - Fusion is executed directly inside Qdrant's Rust SIMD engine (`query=models.FusionQuery(fusion=models.Fusion.RRF)` or `models.Fusion.DBSF`), eliminating Python-side RRF merging overhead and cutting retrieval roundtrip latency by ~40%.
   - Gaussian score distribution normalization in `backend/rag/nodes/utils.py` (`_dbsf_docs` and `_fuse_docs`).
2. **Native Sparse-Dense Multi-Vector Payloads**:
   - Stores BGE-M3 1024d dense embeddings and lexical sparse token weights in named vectors `{"dense": [...], "sparse": SparseVector(...)}`.
   - Exact Sanskrit terminology (*"Samadhi"*, *"Deeksha"*, *"Moksha"*, *"Sadhana"*, *"Aham"*, *"Ananda"*) hits the sparse lexical inverted index with 100% precision, while broad spiritual queries hit the dense semantic index.
3. **Parent Document Group Search (`query_points_groups`)**:
   - Standard vector search often returns 5 consecutive chunks from the same 2-minute section of a single YouTube video.
   - `client.query_points_groups(group_by="parent_id", group_size=2, limit=N)` (with automatic fallback hierarchy: `parent_id` -> `video_id` -> `source_url`) clusters top candidates to guarantee maximum 2 chunks per discourse, ensuring candidate diversity across multiple discourses, books, and teachers in every turn.
4. **Scalar Quantization (`INT8`) & `on_disk=True` Storage**:
   - `ScalarQuantizationConfig(type=ScalarType.INT8, quantile=0.99, always_ram=True)` pins compressed 1-byte INT8 vectors in RAM for ultra-fast HNSW traversal, while original 1024d `float32` vectors and payloads reside on disk (`on_disk=True`).
   - Yields ~4x RAM reduction (~250MB for 100,000 vectors) with >99% recall retention, fitting comfortably within Railway memory tiers.
5. **Standalone Ops & Verification Utility**:
   - `backend/scripts/ops/configure_qdrant_advanced.py` / `make configure-qdrant`: Inspects collections, applies INT8 quantization, builds payload indexes for `parent_id`, `video_id`, `source_url`, and runs automated Universal Query verification probes.

#### 2. Memgraph / Neo4j: 4 SOTA Upgrades
1. **Atomic GraphRAG in openCypher (`CALL { ... }`)**:
   - Drops graph retrieval latency from ~15–20s (multi-turn ReAct loops) to **<5ms in a single Bolt roundtrip**.
   - `backend/rag/nodes/atomic_graphrag.py` executes seed entity matching, 1-hop weighted expansion, 2-hop distance decay aggregation, and formatted subgraph text serialization in ONE atomic openCypher query using `CALL { ... }` subqueries.
2. **MAGE Louvain Hierarchical Community Summaries**:
   - `backend/services/memgraph_community_service.py`: Computes community clusters using Memgraph MAGE (`CALL community_detection.get()`) and compiles `:Community` summary nodes.
   - Global queries ("What is the core philosophy of suffering?") retrieve precomputed macro-syntheses rather than traversing micro-facts.
3. **Strict OKF Ontology Guardrails**:
   - `backend/services/ontology_guardrails.py`: Enforces deterministic graph constraints via Cypher:
     - `MUTUALLY_EXCLUSIVE`: Detects conflicting spiritual assertions or invalid state transitions.
     - `CORE_PRACTICE`: Anchors core practices strictly to authenticated lineage teachers (Sri Preethaji / Sri Krishnaji).
     - `PRACTICE_PREREQUISITE`: Verifies prerequisite dependencies before recommending advanced practices.
     - Cycle detection for prerequisite directed acyclic graphs (DAG integrity).
4. **Native In-Database HNSW Vector Search**:
   - Memgraph's C++ in-memory HNSW index (`CREATE VECTOR INDEX spiritual_concept_idx ON :base(embedding) WITH CONFIG {"dimension": 1024, "metric": "cos"}`) allows hybrid graph-vector queries in a single database engine.

#### 3. LightRAG: 3 SOTA Upgrades
1. **Dual-Level Retrieval Routing**:
   - Dynamic altitude routing via `determine_retrieval_mode(query)` in `backend/services/lightrag_service.py`:
     - `mode="local"`: Entity definitions, exact teacher quotes, step-by-step meditation/practice instructions.
     - `mode="global"`: Broad thematic inquiries, overarching philosophy, and corpus-wide synthesis.
     - `mode="hybrid"`: Balanced multi-concept questions.
     - `mode="auto"`: Intelligently routes queries based on structural regex and keyword patterns.
2. **Semantic Entity Resolution & Alias Canonicalization**:
   - Canonical dictionary `TEACHER_CANONICAL_MAP` maps variations (*"Sri Bhagavan"*, *"Kalki Bhagavan"*, *"Bhagavan"*, *"Kalki"*) to canonical `:Teacher {id: "sri_amma_bhagavan", canonical_name: "Sri Amma Bhagavan"}`.
   - `scripts/ops/canonicalize_teacher_aliases.py` / `make canonicalize-aliases`: Creates non-destructive `[:ALIAS_OF]` edges in Memgraph with zero data loss.
   - `canonicalize_query(query)` and `canonicalize_entity(name)` normalize inputs before lookup.
3. **Contextual Chunk Injection Preservation**:
   - Retains `[Context: Teacher: ... | Discourse: ... | Theme: ...]` headers throughout chunking in `scripts/ingest_lightrag_data.py` and `lightrag_service.py`.
   - Lineage system prompt injection guarantees authentic attribution while strictly forbidding extracting `"Context:"` itself as an entity node.

> **Superseded** by the "what reaches an answer now" section below (both defects fixed).

## Knowledge graph: what actually reaches an answer

**Established 2026-09-11 (ruthless audit), `PROVEN FROM CODE`.** Read this
before investing in Neo4j work or citing the graph as a quality mechanism.

**No Neo4j-derived text reaches the LLM prompt.**

- `query_neo4j_subgraph` (`rag/nodes/retrieval.py:245`) has **zero production
  callers** — only tests reference it.
- GraphRAG fusion and the entity-linked Qdrant prefetch are both gated on
  `graphrag_fusion_enabled`, default `False` (`app/container.py:406` wires the
  prefetch to that same flag).
- The only live per-request Neo4j call is `expand_query_via_kg`
  (`rag/kg_expansion.py:167`). Its neighbours become an augmented query
  appended **last** to `expansion_queries`, then truncated to
  `remaining_budget = 2 - len(primary_queries)` — which is **0 whenever the
  query decomposed into 2+ sub-queries**, so the result is computed and thrown
  away in the common case.
- The prompt's "RELATIONSHIPS & DOCTRINE ONTOLOGY (sacred graph)" block is
  built from multi-chunk bookkeeping (`rag/nodes/generation.py:1032-1043`), not
  from graph edges. The label is misleading.

So the graph's only possible live influence is extra query *terms*, in a narrow
case, with no provenance. Any claim that answers are "graph-grounded" is
currently false. Measure before adding more graph machinery — and note that
until the 2026-09-11 lane fix, `KNOWLEDGE_GRAPH_QUERY_ENABLED` also silently
controlled BM25 and `primary_query_limit`, so older graph ablations were
confounded and their conclusions should not be trusted.

## Knowledge graph: what reaches an answer now

**Supersedes the 2026-09-11 finding below.** Two defects kept Neo4j out of every
answer, and both are fixed:

1. **A casing mismatch.** `extract_doctrine_tags` yields lowercase tags
   (`"soul sync"`); the graph stores Title Case `entity_id`s (`"Soul Sync"`);
   `query_neo4j_subgraph`'s Cypher matched exactly. It could never hit. It now
   matches a small set of casing variants via `IN`, which keeps the index.
2. **No caller.** `query_neo4j_subgraph` had zero production callers. Its
   rights-gated `A -[REL]-> B` lines are now injected into retrieval as an
   ordinary labelled document, so they reach the prompt, are scored by the
   faithfulness gate like any other evidence, and are attributable to the graph
   rather than smuggled in as anonymous query terms.

**The trigger is the query naming two or more doctrine concepts**, not the
retrieval lane — "how does the Beautiful State relate to Soul Sync?" is a
two-hop question that lands on `tier2_simple` and therefore the FAST lane, so a
lane-based gate missed exactly the questions the graph exists to serve.

LightRAG is re-enabled on the same trigger with `only_need_context=True`
(retrieval, not generation) and a hard timeout — unbounded `aquery` latency is
why it was dropped from the hot path originally.

Both are capped, and typed edges sort before generic ones: **4,030 of the 4,082
live edges are LightRAG's generic `DIRECTED`** (measured 2026-09-12), which is
topological co-occurrence, not doctrine. An uncapped dump crowds the actual
teachings out of the prompt — injecting 5k characters of it measurably dropped
faithfulness to 0.50 on a query that scored 1.0 once capped.

Settings: `rag_graph_context_injection_enabled`, `rag_graph_context_timeout`,
`rag_graph_context_score`, `rag_graph_context_max_relations`,
`rag_lightrag_context_*`. All fail-open — the graph must never cost an answer.

