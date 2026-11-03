# Data Plane & Storage Architecture

AskMukthiGuru separates concerns across specialized persistence engines to support both high-dimensional hybrid similarity search and deep relational doctrine exploration.

---

## Data Plane Documentation Pages

1. **[Qdrant Vector Database Reference](qdrant.md)** — Production and context collections (`spiritual_wisdom_contextual`, `first_person_v10`, `guru_tone_podcast`, `semantic_query_cache`), BGE-M3 multi-vector representation (1024d dense + lexical sparse + ColBERT), `fp-context-v1` payload schema, HNSW settings, and scalar quantization.
2. **[Neo4j Knowledge Graph & OKF](neo4j-graph.md)** — Graph ontology (`:Teacher`, `:Concept`, `:Practice`, `:Event`), the 20 OKF 5-node transformation arcs (`SeekerDilemma` $\rightarrow$ `RootLimitingBelief` $\leftarrow$ `GuruTeaching` $\rightarrow$ `BeautifulState` $\rightarrow$ `PracticeStep`), LightRAG dual-level entity/theme extraction, and multi-hop Cypher traversal.

---

## Data Model Topology

```
+---------------------------------------------------------------------------------------------------+
| Engine         | Container / Port   | Contents                                   | Role           |
+----------------+--------------------+--------------------------------------------+----------------+
| Qdrant         | qdrant:6333 / 6334 | `spiritual_wisdom_contextual` (12,904 pts) | Dense & Sparse |
|                |                    | `first_person_v10` (4,197 pts)             | Verbatim Spans |
|                |                    | `guru_tone_podcast` (157 pts)              | Tone Exemplars |
|                |                    | `semantic_query_cache`                     | Query Caching  |
+----------------+--------------------+--------------------------------------------+----------------+
| Neo4j          | neo4j:7474 / 7687  | 7,600+ Typed Doctrine Nodes                | Graph Traversal|
|                |                    | 103 OKF Transformation Subgraphs           | Multi-Hop Path |
|                |                    | LightRAG Dual-Level Entities               | Dual-Level KG  |
+----------------+--------------------+--------------------------------------------+----------------+
| Redis          | redis:6379         | L0 In-Memory / L1 Exact Answer Cache       | Low Latency    |
|                |                    | Celery Task Broker & Result Backend        | Message Queue  |
|                |                    | Ephemeral Rate Limiting Buckets            | Traffic Control|
+----------------+--------------------+--------------------------------------------+----------------+
| Supabase       | Cloud / Local 5432 | PostgreSQL 15 Database (RLS Enforced)      | Relational Auth|
|                |                    | User Profiles, Chat History, Telemetry Logs| Durable Record |
|                |                    | Ingestion Staging & OKF Curation Queue     | Data Pipeline  |
+----------------+--------------------+--------------------------------------------+----------------+
```
