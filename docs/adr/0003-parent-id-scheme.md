# ADR 0003: Parent-ID Scheme — deterministic_v1 vs Legacy & No-Backfill Rationale

- **Status:** Accepted
- **Date:** 2026-10-28
- **Deciders:** Data Engineering, Vector Store Architecture
- **Consulted:** Master Plan DE-1.2, D4, `backend/services/qdrant/indexer.py`

---

## Context
In hierarchical retrieval (RAPTOR, parent-child document expansion, first-person context windows), children chunks refer to their parent section via `parent_id`.
In early iterations, `parent_id` was generated using non-deterministic random UUIDs (`uuid4()`). This caused:
- Inability to verify idempotency on re-ingestion.
- Broken joins between knowledge graph nodes and vector points across re-runs.
- Flaky exact-cache lookups.

## Decision
1. **Deterministic Scheme (`deterministic_v1`):**
   - All parent IDs for newly ingested chunks are computed deterministically via namespace-based hashing:
     - `parent_id = uuid5(NAMESPACE_URL, f"{source_url}:{parent_text_hash}")`
   - Payloads explicitly carry `parent_id_scheme="deterministic_v1"`.
2. **Legacy Handling & No-Backfill Rationale (D4):**
   - Legacy points carry `parent_id_scheme="legacy"` or `None`.
   - **We explicitly do NOT backfill legacy collections in place.**
   - Rationale: Mutating IDs or parent pointers in an active Qdrant collection invalidates 24-hour exact-cache fingerprints, severs existing Neo4j/Memgraph relationship references, and risks silent collision during live query serving.
   - Migration to `deterministic_v1` is performed strictly via clean reindexing into a new versioned collection (`corpus_vN`).

## Consequences
- **Positive:** Idempotent ingestion pipelines; parent-child lookups are stable across runs; deterministic joining between Qdrant, Neo4j, and Supabase.
- **Negative:** Coexistence of legacy random parent IDs and `deterministic_v1` IDs in older collections until retirement.
