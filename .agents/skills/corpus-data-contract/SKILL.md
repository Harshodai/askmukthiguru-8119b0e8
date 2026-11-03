---
name: corpus-data-contract
description: Defines the corpus data plane contract, payload fields, determinism, and serving invariants.
---

# Corpus Data Contract Skill

This skill defines the canonical data plane invariants, payload schema, deterministic ID schemes, and serving policies governing all vector points, chunks, and content releases across AskMukthiGuru.

## 1. Payload Schema & Contract Fields

Every point ingested or reindexed into a production Qdrant collection must satisfy the corpus data contract.

| Field | Type | Required | Description & Validation |
|-------|------|----------|--------------------------|
| `point_id` | `str` (UUID) | Yes | Deterministic UUID identifying the vector point. |
| `parent_id` | `str` (UUID) | Yes | Deterministic UUID pointing to the parent unit. |
| `parent_id_scheme` | `str` | Yes | Must be `"deterministic_v1"` (or `"legacy"` for pre-contract points). |
| `chunker_version` | `str` | Yes | Grammar: `<algorithm>_v<N>[:<params>]` or `"unknown_legacy"`. Never guess. |
| `embedding_model` | `str` | Yes | Pinned encoder name (e.g. `"BAAI/bge-m3"`). |
| `embedding_dimension` | `int` | Yes | Dimensions matching model (e.g. `1024`). |
| `source_url` | `str` | Yes | Canonical source identifier. |
| `source_release_version`| `int` | Yes | Release version mapped to `public.source_releases`. |
| `content_checksum` | `str` | Yes | SHA-256 hash of the verbatim content string. |
| `domain_rights_status` | `str` | Yes | Must be `"licensed"` or `"unverified"`. Never default to licensed. |
| `gate_verdict` | `str` | Yes | Quality gate verdict: `"pass"` or rejection code. |
| `asr_method` | `str` | Yes | ASR source (e.g. `"whisper_v3"`, `"parakeet_ctc"`, `"voted"`). |

## 2. Determinism & Idempotency Rules

1. **Deterministic UUIDs:**
   - `point_id` = `uuid5(NAMESPACE_URL, f"{source_url}:{chunk_index}:{content_checksum}")`
   - `parent_id` = `uuid5(NAMESPACE_URL, f"{source_url}:{parent_text_hash}")`
2. **No In-Place Backfill:**
   - Active collections are never backfilled in place. Upgrades use versioned collections (`corpus_vN`) and atomic alias swapping.
3. **Idempotent Ingestion:**
   - Re-running ingestion over identical transcripts generates byte-identical point payloads and identical vector IDs.

## 3. Serving Invariants

1. **Register → Stamp → Filter → Enforce:**
   - Rights originate in the independent register (`docs/rights/CONTENT-RIGHTS.md` / `source_releases`).
   - Ingest stamps the status onto Qdrant payloads.
   - Retrieval filters on `domain_rights_status == "licensed"`.
   - Gate enforces exclusion of revoked or unverified content.
2. **Chunker Version Integrity:**
   - `chunker_version` must declare the actual chunking class.
   - For legacy unversioned points, return `"unknown_legacy"`. Do not guess or backfill an unverified algorithm.
3. **Persist Quality Rejections:**
   - All quality gate rejections must be persisted to `corpus_gate_rejections` with reason, tier, and source coordinates.
4. **Verbatim Truth & Retrieval Only:**
   - Served answers must be verbatim quotes from verified speakers.
   - Default serving mode is `retrieval_only`. LLM-generated teaching prose is prohibited in production.

## 4. Observability & Health Standards

Operators and automated tasks must maintain:
- `qdrant_optimizer_status == 1` (ok).
- `qdrant_snapshot_age_hours < 24.0`.
- `qdrant_deleted_points_ratio < 0.20`.
- `corpus_lineage_completeness_ratio >= 0.95`.
- `corpus_drift_points_total == 0`.
