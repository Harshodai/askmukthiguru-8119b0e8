# ADR 0002: Chunker Protocol, Chunker Version Grammar & Proposition Chunking Retirement

- **Status:** Accepted
- **Date:** 2026-10-28
- **Deciders:** Data Engineering, NLP Core, RAG Evaluation Team
- **Consulted:** Master Plan DE-0.2, D3, `backend/ingest/chunker_protocol.py`

---

## Context
Previously, chunking strategies across the codebase had drifted:
- Multiple implementations fragmented across `book_ingest.py`, `contextual_reingest.py`, and `mass_first_person_ingest.py`.
- Chunk payload lacked machine-readable metadata identifying which chunker created it, making it impossible to evaluate or ablate chunking algorithms post-hoc.
- Proposition chunking (extracting atomic propositional statements using an LLM) was explored but demonstrated significant risks: high latency, LLM hallucination in propositions, severed discourse context, and substantial dollar costs without improving answer faithfulness.

## Decision
1. **Unified Chunker Protocol (`ChunkerProtocol`):**
   - Every chunker class must implement `ChunkerProtocol` defined in `backend/ingest/chunker_protocol.py`, exposing:
     - `chunk_text(text: str, metadata: dict) -> list[Chunk]`
     - `chunker_version: str` property stamped on every generated `Chunk`.
2. **Standard Chunker Version Grammar:**
   - Every chunker version string must follow a strict naming grammar:
     - `boundary_v1:<target_size>/<overlap_sentences>` (e.g. `boundary_v1:1200/1`)
     - `recursive_v1:<chunk_size>/<chunk_overlap>` (e.g. `recursive_v1:800/100`)
     - `adaptive_v1`
     - `semantic_v1`
     - `unknown_legacy`: Assigned to pre-contract points. Never guess or fabricate a version for legacy points.
3. **Retirement of Proposition Chunking (D3):**
   - Proposition-based LLM decomposition is permanently retired from the ingestion pipeline.
   - Text chunks retain intact verbatim sentences with contextual headers (`[Source: ... | Topic: ...]`).

## Consequences
- **Positive:** Full reproducibility; direct correlation between chunker algorithm and downstream retrieval metrics (MRR/NDCG); elimination of proposition hallucination risk.
- **Negative:** Older collections contain points stamped with `unknown_legacy` until migrated.
- **Invariants:** Every newly written point must carry a valid `chunker_version` from the grammar; `unknown_legacy` is honest and must not be masked.
