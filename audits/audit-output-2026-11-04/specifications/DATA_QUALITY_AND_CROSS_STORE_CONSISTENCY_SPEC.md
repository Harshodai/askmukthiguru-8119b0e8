# Data quality and cross-store consistency specification

## 0. Header

| Field | Value |
|---|---|
| Purpose | Define, for every datastore the code uses, its authority, identity, integrity, lifecycle and propagation rules. Define the lineage from source to answer citation. Define exact checks, split into static (CI on fixtures) and live (owner's stores). |
| Status | **partial.** Static checks C-S1 to C-S8 are implementation-ready on fixtures. Live checks need the owner's Qdrant, Redis, Postgres and Memgraph. The source registry (ADR-007) is not built. |
| Date / head | 2026-11-05 / `c9b42d3e` on `feature/audit-strengthen-rag-qdrant` |
| Brief parts | 6.1, 6.4, Final Addition B |
| Decisions it depends on | D-05, D-08, D-14, D-15; ADR-004, ADR-005, ADR-007 (see `decision-log.md` §2) |
| Companions | `INGESTION_AND_CONTENT_PROCESSING_SPEC.md` (stages, state machine, takedown); `../FINAL_QDRANT_LIVE_VALIDATION_CHECKLIST.md` (owner-run order). Check names R-1 to R-18 are in `22`. |
| Status source | `FINAL_PENDING_WORK_REGISTER.md` (DATA-15 and DATA-16 Partial; DATA-03, DATA-05, DATA-11 Closed). |

## 1. Existing coverage and exactly what it lacks

| Existing | Covers | Lacks (added here) |
|---|---|---|
| `06` §2-§5 | Store inventory (S-1 to S-19), per-store assessment table, consistency matrix | A uniform 15-field contract per store; lineage with the link ID at every hop; reconciliation and recovery rules. |
| `22` R-1 to R-18 | Live read-only checks with queries | Static fixture equivalents; SQL checks; Redis checks; pass criteria tied to a store contract; a check for the rights stamp (DATA-20). |
| `22a` | Acceptance criteria and test plan | Data-specific test cases (§7). |
| `FINAL_PENDING_WORK_REGISTER.md` | Status | Defects in landed code (see ingestion spec §2.2, DATA-20 to DATA-27). |

## 2. Current state (verified at `c9b42d3e`)

| Fact | Evidence |
|---|---|
| Which collection serves depends on two flags and one name. `first_person_active_collection` defaults to `first_person_v10`. `first_person_context_harness_enabled` and `first_person_context_terminal_enabled` default `False`. | `backend/app/config.py:205`, `:282`, `:298` |
| The legacy slot `first_person_collection` is filled with `first_person_v8` unless both harness flags are on. The context slot is always filled with the active name. | `backend/app/config.py:41`, `:2309-2326` |
| `.env.example` and compose both default the active name to `first_person_v10`. | `backend/.env.example:207-213`; `backend/docker-compose.yml:311` |
| The serving contract declares v1 to v11. v8 is `first-person-legacy-clip-v1`. v10 and v11 are `fp-context-v1`, corpus version `fp-context-transcript-v1`. No entry sets `collection_digest` or `approved_corpus_version`. | `backend/config/first_person_serving_contract.json` (read with `python3`) |
| Qdrant publishes only on `127.0.0.1`. The API key is `QDRANT_WRITE_API_KEY` or `QDRANT_API_KEY`, default empty. A read-only key variable exists. The backend reads the read-only key first. | `backend/docker-compose.yml:156`, `:162-163`, `:302-303`; `backend/app/config.py:711-717` |
| Chat corpus point ID: from `source_url`, `chunk_index`, `raptor_level`. | `backend/services/qdrant/utils.py:23-35` [per `06`, not re-read] |
| Stored citations: `chat_messages.citations text[]`. | `supabase/migrations/20260506064449_*.sql:34-42` [per `06`] |
| `reconcile_orphans.py`, `cross_store_audit.py`, `audit_lineage_completeness.py`, `launch_gate_qdrant_integrity.py`, `restore_drill.py`, `ensure_fp_payload_indexes.py` exist. `restore_drill.py` resolves the first-person collection from `settings.first_person_collection`, so it drills v8 unless the environment overrides it. | `backend/scripts/ops/*.py` (headers read); `restore_drill.py:102-111` |
| The nightly "audit" runs pytest on fixtures. It never contacts Qdrant. | `.github/workflows/nightly-audit.yml:43-46` |

## 3. Datastore contracts

Each table gives the 15 required fields. "Static" means checkable in CI on a fixture. "Live" means it needs the owner's store. A claim from `06` that I did not re-read is marked [per 06].

### 3.1 Qdrant `first_person_v10` (and v11 candidate), schema `fp-context-v1`

| Field | Value |
|---|---|
| Source of truth | Host transcripts + audio + speaker verdicts + rights register, via the builder. Qdrant is derived. |
| Schema | Two record types by `record_type`: `retrieval_child` (`SourceSpan`) and `parent` (`ParentUnit`). Vectors `passage_dense` (1024), `passage_sparse`. `extra="forbid"`. Key child fields: `source_span_id`, `parent_unit_id`, `video_id`, `guru_id`, `start_ms`, `end_ms`, `word_start`, `word_end`, `verbatim_text`, `source_text_hash`, `span_text_sha256`, `transcript_hash`, `video_transcript_sha256`, `speaker_verified`, `voice_verification_method`, `rights_cleared`, `domain_rights_status`, `boundary_status`, `completeness_status`, `corpus_version`, `embedding_model`, `embedding_revision`, `language`. (`backend/domain/first_person_context.py:166-345`) |
| Unique IDs | `source_span_id` = sha256 of `guru_id|video_id|corpus_version|word_start|word_end|transcript hash`; point = `uuid5(_POINT_NAMESPACE, source_span_id)` (`first_person_context_store.py:250-256`). |
| Relationships | Child -> parent (`parent_unit_id`); child -> previous or next child (`previous_span_id`, `next_span_id`); child -> video (`video_id`) -> register asset (`video_id`). |
| Version | `corpus_version` (in the ID), `schema_version` (v1 or v2), collection name. |
| Duplicate detection | Same `source_text_hash` within one `video_id`; contained interval (§5 C-L9); same `video_id` under two `corpus_version` values. |
| Orphan detection | Child whose `parent_unit_id` has no parent point; parent with `ordered_source_span_ids` missing children; `video_id` absent from the audio manifest or the register (C-L10). |
| Integrity constraints | Model validators: `source_text_hash == sha256(verbatim_text)`; `span_text_sha256` equals the same; v2 requires both new hashes; span ID recomputes (`first_person_context.py:298-330`). Write guards: speaker provenance (`first_person_context_store.py:173-252`, `:402-420`). Serve-time hash gate on `source_text_hash`. |
| Stale data | Spans from a superseded transcript; `speaker_verified=True` set by a later writer without evidence (v11 incident, `06` DATA-06); `domain_rights_status` stamped before a rights change. |
| Lifecycle | candidate -> approved -> serving -> rollback-only -> deleted. A new version is a new collection (invariant 4). |
| Update propagation | No in-place edits. A correction is a new candidate collection, then a contract change. Exact-cache replays revalidate against the current payload (`first_person_context_store.py:1283-1349`). |
| Deletion propagation | Delete by `video_id` filter in this collection. Not automated today (DATA-07, Open). The video block stops serving at once. |
| Reconciliation | Compare per-video expected-ID manifest to scrolled IDs; compare span IDs to `span_index` (future); daily digest compare (C-L11). |
| Recovery | Snapshot restore into a scratch collection (checklist V-3), or rebuild from the source bundle (blocked by D-08). |
| Validation | C-S1 to C-S4 (static); C-L1 to C-L11 (live). |

### 3.2 Qdrant `first_person_v8` and older (v1 to v9), schema `first-person-legacy-clip-v1`

| Field | Value |
|---|---|
| Source of truth | Host builder `build_first_person_index.py` output (clips). |
| Schema | Vectors `passage_dense`, `question_dense` (only with a real question), `passage_sparse`. Payload: `video_id`, `start_ms`, `end_ms`, `speaker`, `transcript_hash` (clip hash), `group_id`, `source_url`, `teacher_id`, `teacher_ids`, `provenance_kind`, `quality_status`, `first_person_eligible`, `is_verbatim`, `verbatim_text`, `domain_rights_status`, optional `speaker_verified`, `voice_verification_method`. (`first_person_store.py:480-545`) |
| Unique IDs | `uuid5(FIRST_PERSON_NAMESPACE, f"{transcript_hash}:{start_ms}:{end_ms}")` (`:106-112`). `video_id` is not in the ID. |
| Relationships | Clip -> video (`video_id`, `group_id`); clip -> register asset. No parent link. |
| Version | Collection name only. Contract `corpus_version` is `legacy-clip-store`. |
| Duplicate detection | Within a batch: same `(canonical video_id, cleaned text)` is dropped (`:420-480`). Across batches: contained or jittered spans give distinct IDs (comment at `:87-96`). Live: same `video_id` and `transcript_hash` with overlapping intervals. |
| Orphan detection | Points whose `video_id` is not in the register or the manifest; stale orphans from older builds (v7: 1,484 of 3,236, root `CLAUDE.md` invariant 23, `[DOC-CLAIM]`). |
| Integrity constraints | `validate_clip_entry`: hash is 64 hex and equals `sha256(verbatim_text)`; speaker in allowlist; timing order; promise-clip block (`:172-236`). Write-time recompute of the point ID and dimension check; read-back sample (`:548-595`). |
| Stale data | Clips from before a re-clean; unverified speakers; `domain_rights_status` older than a register change. |
| Lifecycle | Rollback target only when the v10-only posture is on; the serving slot otherwise (default flags). |
| Update propagation | Builder diffs IDs and deletes stale ones (`build_first_person_index.py:677-783`). Legacy `points_servable` does not compare text (`first_person_store.py:601-636`). |
| Deletion propagation | Delete by `video_id`. Not automated. |
| Reconciliation | Compare expected and stored ID sets per run. |
| Recovery | Snapshot (`first_person_v7` snapshot named in root `CLAUDE.md` invariant 23); rebuild blocked by D-08. |
| Validation | C-S5; C-L1 to C-L8. |

### 3.3 Qdrant chat corpus `spiritual_wisdom_contextual` (legacy `spiritual_wisdom`)

| Field | Value |
|---|---|
| Source of truth | YouTube captions and web or PDF text, via the online `IngestionPipeline` [per 06]. |
| Schema | Vectors `dense` (1024) and `sparse`; payload includes `source_url`, `video_id`, `teacher_id`, `provenance`, `raptor_level`, `content_type`. INT8 quantisation [per 06]. |
| Unique IDs | `make_point_id(source_url, chunk_index, raptor_level)` (`services/qdrant/utils.py:23-35`). |
| Relationships | Chunk -> `source_url` -> `corpus_sources.source_identity`; RAPTOR summary -> children. |
| Version | `source_releases.release_version` per source; collection alias swap (`qdrant_aliases.py`) [per 06]. |
| Duplicate detection | More than one `source_url` per `video_id` (R-9). |
| Orphan detection | Chunks whose source has no `corpus_sources` row; `reconcile_orphans.py` (expected IDs vs stored IDs per source). |
| Integrity constraints | Quality gate at the door (`ingest/quality_gate.py`). `replace_source_url` two-phase replace (`indexer.py:217-222`). Scripts bypass it (DATA-10, owner decision pending). |
| Stale data | Tail chunks after a source shrinks; URL-variant duplicates; `teacher_id` mixed values (only 4,337 of 12,904 `ekam`, `[DOC-CLAIM]`). |
| Lifecycle | Active only for non-teaching turns; on the retirement path in ADR-005 for teacher content (`09`/`17`). |
| Update propagation | Replace by source; three answer caches cleared after ingest (`pipeline.py:3583-3620`). |
| Deletion propagation | `delete_by_source` (`indexer.py:735`). Partial. |
| Reconciliation | `reconcile_orphans.py`; `cross_store_audit.py` (anti-entropy across stores). |
| Recovery | Nightly cron backup, not installed on the owner's host (root `CLAUDE.md`, `[DOC-CLAIM]`). |
| Validation | C-L12 (R-9), C-S6. |

### 3.4 LightRAG stores (`lightrag_vdb_*` in Qdrant; `data/lightrag` files)

| Field | Value |
|---|---|
| Source of truth | LightRAG, fed by `ainsert(clean_text)` with no file path (`pipeline.py:1270`). |
| Schema | LightRAG internal (entities, relationships, chunks; KV and doc status files). |
| Unique IDs | LightRAG content hash [per 06]. |
| Relationships | None to a source (DATA-08). |
| Version | None. |
| Duplicate detection | Not measured. |
| Orphan detection | `cross_store_audit.py` compares LightRAG, Memgraph, Qdrant and the working directory. |
| Integrity constraints | None at write. Artifact gate `find_artifact` can sample chunks (R-18). |
| Stale data | 41.4% of chunks contaminated (`lessons.md:6295`, `[DOC-CLAIM]`). |
| Lifecycle | To be frozen (T3-11, D-05). |
| Update propagation | None by source. |
| Deletion propagation | None by source (cannot trace). |
| Reconciliation | `cross_store_audit.py`. |
| Recovery | `backup_lightrag_checkpoint.py`; no restore proof. |
| Validation | C-L13 (R-18). |

### 3.5 Memgraph (ontology, LightRAG graph, TeachingUnit projection)

| Field | Value |
|---|---|
| Source of truth | None. Derived from LLM extraction. |
| Schema | `base` nodes keyed by `entity_id`; `__Chunk__` nodes keyed by the first 300 characters of text; edges carry `tenant_id='oneness'` (needs `backfill_edge_tenant_id.py --apply` after each ingestion, root `CLAUDE.md`). `ontology_writer.py:152-163`; `pipeline.py:4392` [per 06]. |
| Unique IDs | Entity name (`MERGE`). |
| Relationships | Entity -> `source_doc_id` (last writer wins). |
| Version | None. |
| Duplicate detection | Name variants; `resolve_entities.py`. |
| Orphan detection | `base` nodes with null `source_doc_id` (R-17). |
| Integrity constraints | Ontology guardrails (`services/ontology_guardrails.py`) [per root `backend/CLAUDE.md`]. |
| Stale data | Facts from withdrawn sources. |
| Lifecycle | Freeze, then remove from deploy (ADR-005, Proposed). |
| Update propagation | Written on each online ingest (`write_ontology_to_neo4j` default `True`, `pipeline.py:1288`). |
| Deletion propagation | `DETACH DELETE` only in consolidation and user erasure (`app/api/memory.py:1290` [per 06]). None by source. |
| Reconciliation | `cross_store_audit.py`. |
| Recovery | `neo4j_graph_dump.json` in the repo is a stale fragment (DATA-19). |
| Validation | C-L14 (R-17). |

### 3.6 Supabase Postgres (content and memory relevant tables)

| Field | Value |
|---|---|
| Source of truth | Postgres for users, conversations, memory, telemetry and ingestion jobs. Not for teaching text. |
| Schema | `corpus_sources`, `source_releases`, `ingest_jobs`, `ingestion_checkpoints` (ingestion spec §2.3); `kb_sources`, `kb_chunks` (`vector(768)`, unused); `gurus`; `chat_messages.citations text[]`; `memory_consent_receipts`, `memory_outbox`, `pending_extractions`; `study_notebooks` (scoped by `user_id`, no `tenant_id`) (root `CLAUDE.md` PR #76 section). New tables in ingestion spec §3.3. |
| Unique IDs | UUID PKs; `corpus_sources.source_identity`; `source_releases` UNIQUE `(corpus_id, source_identity, release_version)` and `(…, content_checksum)`. |
| Relationships | `source_releases.source_identity` -> `corpus_sources.source_identity` (by value, no FK in the migration read). `corpus_sources.active_release_id` -> release (no FK in the migration read). |
| Version | `release_version`; `supabase/schema_snapshot.sql` for schema. |
| Duplicate detection | Duplicate `CREATE TABLE` lint (`scripts/guards/migration_lint.py`); `kb_sources` is append-only with no unique URL. |
| Orphan detection | Active source with no active release (SQL-1); `ingest_jobs` stuck (SQL-2). |
| Integrity constraints | `source_releases` CHECK set (status, positive version, approval audit); one active release per source (unique index). Memory FKs must `ON DELETE CASCADE` (SQL-3). RLS on all tables. |
| Stale data | `ingest_jobs` `running` with an old heartbeat (swept by `sweep_stale_ingest_jobs`, default 45 minutes, `tasks/ingest_tasks.py:598`). |
| Lifecycle | Migrations forward only; schema snapshot diff in CI (DATA-11 Closed). |
| Update propagation | Backend writes via service role. |
| Deletion propagation | User erasure cascades (memory scope). Citation rows do not exist yet (DATA-12). |
| Reconciliation | Snapshot diff in CI; SQL checks below. |
| Recovery | No off-host Postgres backup proven (SYS-012 needs an owner decision). |
| Validation | C-S7 (migration lint and snapshot, exists); SQL-1 to SQL-4 (live or scratch DB). |

### 3.7 Redis

| Field | Value |
|---|---|
| Source of truth | None. Cache and counters. |
| Schema | `cache:first_person_exact:{lang}:{sha256}` (TTL 86,400 s); `mukthiguru:cache:tenant:*`; `mukthiguru:semcache:*`; `rl:*`; `anon:*`; `mukthiguru:lock:*`; `yt:avail:*` (24 h); `ingestion_checkpoint:{tenant}:{chunk}`; Celery keys [per 06; FP key read at `first_person_pipeline.py:3118`; checkpoint key at `ingest/handlers/checkpoint.py` `_get_redis_key`]. |
| Unique IDs | FP key = sha256 of normalised query, teacher, language, collection, calibration fit time, rerank mode, answerability flag, policy fingerprint (`first_person_pipeline.py:3085-3119`). |
| Relationships | Cached answer -> cited point IDs and expected evidence. |
| Version | Collection name and policy fingerprint inside the key. No content version. |
| Duplicate detection | n/a |
| Orphan detection | Cached entries that cite points no longer present (found at replay by revalidation). |
| Integrity constraints | Replay revalidates points, rights, block state and (context store) text, hashes, coordinates, provenance (`:3122-3155`). |
| Stale data | Entries older than a text correction. They miss on replay (context store only). |
| Lifecycle | TTL 24 h for FP exact cache. |
| Update propagation | Not pushed. Pulled at replay. |
| Deletion propagation | Optional `SCAN` delete. Correct without it. |
| Reconciliation | None needed for FP exact cache. |
| Recovery | Rebuild by traffic. |
| Validation | C-L15 (TTL and key shape); ING-A10 and ING-A11 in the ingestion spec. |

### 3.8 OKF bundle (`memory/okf/`, `compiled.json`)

| Field | Value |
|---|---|
| Source of truth | Markdown files with front matter. `compiled.json` is derived. |
| Schema | Front matter: `type` in `teaching, practice, glossary, qa, reflection`; non-empty `source`; `teacher`; optional `updated`, `status`, `generated`, `verified`, `sources`. (`backend/services/memory/okf_store.py:79, 100-103, 220-227`; `backend/CLAUDE.md` OKF section). |
| Unique IDs | File path. |
| Relationships | Entry -> `source` URL -> `video_id`. |
| Version | Git history; `updated` date. |
| Duplicate detection | Same title and source across teacher subdirectories. |
| Orphan detection | Entry whose `source` video is absent from the register or withdrawn. |
| Integrity constraints | `OKFStore.list_entries()` gate: doctrine type, non-empty source, no extraction artifacts; `staging/` and `_scripts/` excluded (`okf_store.py:198-210`). |
| Stale data | `compiled.json` drift (429 compiled vs 721 eligible files, DATA-17, `[DOC-CLAIM]`); absolute host paths. |
| Lifecycle | staging (LLM) -> human review -> bundle -> compile. |
| Update propagation | Recompile; the cache is keyed on `compiled.json` mtime. |
| Deletion propagation | Manual file removal and recompile. Not automated. |
| Reconciliation | `okf_quote_gate_report.py`, `data_quality_audit.py` OKF quote check [per 06]. |
| Recovery | Git. |
| Validation | C-S8 (`test_okf_doctrine_only.py`, `test_okf_pipeline_integrity.py`); C-L16 (source video check). |

### 3.9 Host audio archive and attribution data

| Field | Value |
|---|---|
| Source of truth | The owner's host (`~/mukthiguru_attribution_data/`). |
| Schema | `audio_archive/wavs/<video_id>.wav`; `manifest.json` entries: `video_id`, `status`, `filename`, `sha256`, `bytes`, `duration_s`, `sample_rate`, `channels`, `source_url`, `rights_status`, `archived_at`, `error`, `retry_count` (`audio_archive.py:565-580`). Transcripts as markdown with a `Transcript Hash:` header. |
| Unique IDs | `video_id`; `sha256` of the WAV. |
| Relationships | WAV -> transcript -> spans (`video_id`). |
| Version | Manifest `updated_at`; WAV SHA. |
| Duplicate detection | Two YouTube IDs with identical audio (one pair mapped, `first_person_store.py:99-103`). |
| Orphan detection | Manifest entry with no WAV; WAV with no manifest entry (`verify()`, `:339-423`). |
| Integrity constraints | Atomic manifest write; SHA, size, channels, sample-rate check in `verify()`. |
| Stale data | `rights_status: "cleared"` is a literal (DATA-24). |
| Lifecycle | pending_download -> archived; `unavailable`, `age_restricted`. |
| Update propagation | None downstream. |
| Deletion propagation | Manual. |
| Reconciliation | `audio_archive.py verify`. |
| Recovery | None off-host (DATA-01, SYS-012). |
| Validation | C-L10 (R-10); `verify`. |

### 3.10 Manifests and decision files (rights register, serving contract, video decisions)

| Field | Value |
|---|---|
| Source of truth | Register JSON (rights); contract JSON (what a collection is allowed to assert); decision JSON (human block or approve per video). |
| Schema | Register: `assets[]` with `video_id`, `canonical_source_url`, `rights_status`, `evidence_sha256`, `permission_basis`, `review_date`. Contract: `collections{name: {schema, role, corpus_version, required_payload_fields, evidence_policy, optional encoder, collection_digest, approved_corpus_version}}`. Decisions: `VideoDecision` fields (`first_person_video_decisions.py:71-95`). |
| Unique IDs | `video_id`; collection name. |
| Relationships | Register `video_id` -> payload `video_id`; contract name -> collection. |
| Version | Register file date in its name; contract `schema` string. |
| Duplicate detection | Two register assets with one `video_id`. |
| Orphan detection | Served `video_id` not in the register (C-L10). |
| Integrity constraints | Register missing or empty stops production startup (`main.py:786-798`). Contract validator fails closed (`first_person_serving_contract.py:444-630`). Decisions use atomic write and a lock (`first_person_video_decisions.py:213-330`). |
| Stale data | Register holds `/Users/...` paths in `independent_sources` (register note: scrub needs a re-pin of three digests). No digest pin compared at boot. |
| Lifecycle | Hand-edited by the owner; decisions by admin API. |
| Update propagation | Cached by file stat; read live per request for decisions. |
| Deletion propagation | n/a |
| Reconciliation | Health shows register count and digest prefix (`health.py:228-235`). |
| Recovery | Git for the register and contract; the decisions file lives in the container volume (DATA-18, Open). |
| Validation | C-S3, C-S4; C-L9 digest. |

## 4. Lineage

| Hop | Link ID | Carried by | Break today |
|---|---|---|---|
| Source -> audio | `video_id` | manifest key, WAV name | Manifest rights literal (DATA-24) |
| Audio -> transcript | `video_id`; `transcript_hash` header | transcript file | Header hash is replaced by the computed one on mismatch |
| Transcript -> span | `word_start`, `word_end`, `video_transcript_sha256` | `source_span_id` | v8 IDs use `start_ms`, `end_ms`: jitter makes a new ID |
| Span -> point | `uuid5(namespace, source_span_id)` (v10) or `uuid5(ns, hash:start:end)` (v8) | point ID | none |
| Point -> graph | None (name-keyed `entity_id`) | n/a | No provenance (DATA-08) |
| Point -> answer citation | `point_id`, `source_span_id`, `video_id`, `start_ms`, `end_ms`, span hash | response citation dict | Persisted as free text only (DATA-12, Open) |
| Answer -> cache | cited point IDs plus expected evidence | FP exact cache entry | Legacy store does not compare text on replay |

Rule: every derived record carries `video_id` and a hash of the text it was derived from. A record that cannot name its source cannot be deleted by source.

## 5. Checks

Pass criteria are exact. Static checks need no live store. Live checks are read-only. Result files must never contain `verbatim_text` (public-repo rule, `14c` IP-001, guard in `scripts/guards/lesson_guards.py:40-53`).

Python header for all snippets (run with `backend/.venv/bin/python3 -I`, from the repo root):

```python
import hashlib, os, uuid, collections, json
from qdrant_client import QdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchValue
C = QdrantClient(url=os.environ["QDRANT_URL"], api_key=os.environ.get("QDRANT_API_KEY") or None, timeout=60)
def scroll_all(coll, flt=None, fields=True, page=512):
    off = None
    while True:
        pts, off = C.scroll(coll, scroll_filter=flt, with_payload=fields, with_vectors=False, limit=page, offset=off)
        yield from pts
        if off is None: break
CHILD = Filter(must=[FieldCondition(key="record_type", match=MatchValue(value="retrieval_child"))])
```

### 5.1 Static checks (CI on fixtures)

| ID | Check | How | Pass | Existing or new |
|---|---|---|---|---|
| C-S1 | Span hash equals `sha256(verbatim_text)`; v2 requires both new hashes | `SourceSpan.model_validate` on a fixture | Valid spans validate; a tampered text raises | Exists: `test_writer_hash_contract.py::test_source_span_v2_refuses_span_hash_mismatch` |
| C-S2 | Writer contract over every writer | Parametrised test over builder, legacy upsert, context upsert | 0 payloads where span hash differs from `sha256(verbatim_text)` | Exists (partial); add the builder case (A5) |
| C-S3 | Contract validator | `validate_serving_contract` on fixture contracts | Undeclared collection fails; digest or approved-version mismatch fails | Exists: `test_data_quality_promotion_gate.py`, `test_qdrant_write_governance.py` |
| C-S4 | Digest determinism and one identity basis | `compute_collection_digest` on a fixture | Same digest from builder, audit and boot paths | Digest exists; identity test is new (A7) |
| C-S5 | Legacy point ID recompute | local-mode Qdrant (`QdrantClient(":memory:")`), `FirstPersonStore.upsert_clips` on 3 clips | `str(point.id) == make_first_person_point_id(hash, start, end)` for all | Covered by write-time check (`first_person_store.py:548-562`); add a fixture test |
| C-S6 | Chat ID canonicalisation | Two URL forms of one video | Same point IDs | New (DATA-10) |
| C-S7 | Schema snapshot and duplicate tables | `scripts/guards/migration_lint.py` | Clean migrate equals `supabase/schema_snapshot.sql`; 0 duplicate `CREATE TABLE` after baseline | Exists: `test_migration_lint.py` |
| C-S8 | OKF gate | `OKFStore.list_entries()` on a fixture with a `runbook`, an empty source and a staging file | Only the valid doctrine entry loads | Exists: `test_okf_doctrine_only.py` |

### 5.2 Live checks (owner's stores, read-only)

Collection names below use `COLL` (the v10 serving name) and `LEG` (the legacy name). Set them from checklist step V-1.

| ID | Check | Query | Pass | Maps to |
|---|---|---|---|---|
| C-L1 | Inventory | `[(c.name, C.get_collection(c.name).points_count) for c in C.get_collections().collections]` | Every collection named in the contract and in use exists. List any collection not referenced by code. | R-1 |
| C-L2 | Dimension and vector names | `C.get_collection(COLL).config.params.vectors` and `.sparse_vectors` | `passage_dense` size 1024, cosine; `passage_sparse` present. v8 also `question_dense` 1024. Equals `settings.embedding_dimension` (T3-12). | R-3 |
| C-L3 | Hash integrity (v10) | For each `retrieval_child`: `hashlib.sha256(p.payload["verbatim_text"].encode()).hexdigest() == p.payload["source_text_hash"]` | `BAD == 0` | R-7 |
| C-L4 | Hash integrity (v8) | Same on `transcript_hash` | `BAD == 0` | R-7 |
| C-L5 | Point-ID recompute | v10: `uuid5(uuid5(NAMESPACE_URL,"askmukthiguru/fp-context/v1"), source_span_id) == str(p.id)` and the span ID recomputes. v8: `uuid5(UUID("b3f9479e-4e67-4a0b-9d48-6a5814e5f7a2"), f"{transcript_hash}:{start_ms}:{end_ms}")` | 0 mismatches | R-8 |
| C-L6 | Teacher and speaker values | `C.facet(COLL, key="guru_id", limit=50)`; `facet` on `speaker_verified`, `voice_verification_method` (needs payload indexes; else a `Counter` over a scroll) | Every `guru_id` is in `backend/config/gurus.yaml` (`ekam`, `preethaji`, `krishnaji`). 0 spans with `speaker_verified=True` and no method. | R-6, DATA-13 |
| C-L7 | Rights stamp | `C.count(COLL, count_filter=Filter(must=[FieldCondition(key="domain_rights_status", match=MatchValue(value="licensed"))]), exact=True)` versus the child count | Equal. A lower count means DATA-20 effects. | DATA-20 |
| C-L8 | Payload indexes | `C.get_collection(COLL).payload_schema.keys()` | Includes every key in `SPAN_INDEXES` (`first_person_context_store.py:140-160`) | R-13 |
| C-L9 | Contained-span duplicates | Per `video_id`, sort children by `(start_ms, -end_ms)`; a span is contained when `start_ms >= prev.start_ms and end_ms <= prev.end_ms` of a kept container | Report the rate. Project scorecard target applies (`contained_in_other_span_rate`, `[DOC-CLAIM]` 17.14% on v10). | `06` §7 |
| C-L10 | Orphans against registry and archive | `served_vids - archived_vids` and `served_vids - cleared_register_vids` (code in `22` R-10) | Both sets empty | R-10, DATA-01 |
| C-L11 | Collection digest | `compute_collection_digest(scroll_all(COLL, fields=True))` from `services.first_person_serving_contract` | Equal to the signed digest. Today the contract holds none: record the value as the baseline. | R-16, DATA-26 |
| C-L12 | URL-form duplicates (chat) | Code in `22` R-9 | 0 `video_id`s with more than one `source_url` | R-9 |
| C-L13 | LightRAG | Counts per `lightrag_vdb_*`; `find_artifact` on 500 chunks | Retired, or contamination below 1% | R-18 |
| C-L14 | Memgraph | Cypher in `22` R-17 | Edges without `tenant_id` = 0 | R-17 |
| C-L15 | Redis cache shape | `redis-cli --scan --pattern 'cache:first_person_exact:*' \| head -20`, then `TTL <key>` | Keys match the pattern; TTL at most 86,400 | `06` S-10 |
| C-L16 | OKF sources | For each OKF `source`, extract the video ID and check it exists in the register | 0 entries whose video is absent or withdrawn | DATA-17 |

SQL checks (run on the owner's Postgres or a scratch database migrated from `supabase/migrations/`; read-only):

```sql
-- SQL-1: active source with no active release
SELECT s.source_identity FROM public.corpus_sources s
LEFT JOIN public.source_releases r
  ON r.source_identity = s.source_identity AND r.corpus_id = s.corpus_id AND r.status = 'active'
WHERE s.status = 'active' AND r.id IS NULL;
-- pass: 0 rows (or each row explained: a source not yet released)

-- SQL-2: stuck ingest jobs (sweeper threshold is 45 minutes)
SELECT id, status, heartbeat_at, created_at FROM public.ingest_jobs
WHERE status IN ('running','processing')
  AND coalesce(heartbeat_at, created_at) < now() - interval '45 minutes';
-- pass: 0 rows

-- SQL-3: memory foreign keys referencing consent receipts must cascade
SELECT tc.table_name, rc.delete_rule
FROM information_schema.referential_constraints rc
JOIN information_schema.table_constraints tc ON tc.constraint_name = rc.constraint_name
JOIN information_schema.table_constraints tc2 ON tc2.constraint_name = rc.unique_constraint_name
WHERE tc2.table_name = 'memory_consent_receipts';
-- pass: every row for memory_outbox and pending_extractions shows CASCADE

-- SQL-4: citations that exist as free text (baseline for DATA-12)
SELECT count(*) FROM public.chat_messages WHERE citations IS NOT NULL AND array_length(citations, 1) > 0;
-- pass: none (informational: the size of the history that cannot be withdrawn by span)
```

SQL-3 and the "pass" values come from root `CLAUDE.md` (PR #76 invariant). I did not run them.

### 5.3 Reconciliation and recovery rules

1. Protected-field digest: hash the sorted tuples `(point_id, source_text_hash, speaker_verified, voice_verification_method, domain_rights_status)`. Record it at sign-off. Compare daily (R-16). A change without a recorded build is an incident.
2. After any build: per-video expected-ID list versus scrolled IDs. Differences mark the video failed (ingestion spec §4.1).
3. After any rights-register change: re-stamp is a new candidate collection, not an in-place edit.
4. Restore drill: restore a snapshot into a scratch collection, run C-L1 to C-L11 there, and delete only the scratch collection (checklist V-3).

## 6. Observability

Existing names (verified in `backend/app/metrics.py`): `CORPUS_ORPHAN_POINTS_TOTAL` (`:675`), `CORPUS_DRIFT_POINTS_TOTAL` (`:680`), `CORPUS_LINEAGE_COMPLETENESS_RATIO` (`:726`), `FP_FAIL_CLOSED_TOTAL` (`:55`), `FIRST_PERSON_QUARANTINED_TOTAL` (`:787`). `audit_lineage_completeness.py` sets the lineage gauge; `reconcile_orphans.py` sets the orphan counter. Nothing sets a digest-drift metric yet. Add `corpus_digest_match` (gauge, 1 or 0) only together with the code that computes it (ingestion spec NEW-ING-4).

## 7. Acceptance criteria

| # | Criterion | Test | Pass / fail | Type |
|---|---|---|---|---|
| D1 | Each static check C-S1 to C-S8 runs in CI | `backend/tests/` files named above plus new cases A5, A7, C-S5, C-S6 | All pass | S |
| D2 | The live audit reads the serving collection by name from the contract | new `test_data_quality_audit.py::test_audit_reads_serving_collection_from_contract` | Audit targets the active name | S |
| D3 | A local-mode fixture collection with one tampered `verbatim_text` fails C-L3 logic | new `test_data_quality_audit.py::test_hash_check_detects_tamper` | BAD count is 1 | S |
| D4 | A fixture with a contained span is counted by C-L9 logic | new `::test_contained_span_rate` | Rate matches the fixture | S |
| D5 | A fixture span with `domain_rights_status="unverified"` fails C-L7 logic | new `::test_rights_stamp_check` | Reported | S |
| D6 | C-L1 to C-L16 run on the owner's stores and the results are filed | Checklist run | Each pass criterion in §5.2 met, or a finding filed | L, H |
| D7 | SQL-1 to SQL-4 results filed | Owner runs them | As stated | L |
| D8 | A restore into a scratch collection passes C-L1 to C-L11 | Checklist V-3 | Same counts and digest as source | L |

## 8. Implementation tasks (PR-sized, ordered)

| Order | Task | Maps to | Depends on | Non-goals | Rollback |
|---|---|---|---|---|---|
| 1 | NEW-DQ-1: refactor the live checks of `22` into `scripts/ops/fp_live_audit.py` (read-only, `--collection`, output with no text fields, exit non-zero on a failed check) | DATA-15 (Partial) | none | No writes; no default scheduling | Delete the script |
| 2 | NEW-DQ-2: add D2 to D5 tests on local-mode Qdrant | DATA-15 | 1 | No live Qdrant in CI | Revert |
| 3 | NEW-DQ-3: unify the digest identity (ingestion spec NEW-ING-4) | DATA-26, DATA-27 | none | None | Revert |
| 4 | NEW-DQ-4: record `approved_corpus_version` and encoder in the contract after the owner picks the collection | DATA-16, RET-07 | D-14 | Agent does not choose the value | Edit the contract back |
| 5 | NEW-DQ-5: opt-in workflow that runs `fp_live_audit.py` when a read-only secret exists | DATA-15 | 1 | Never default on | Delete the workflow |
| 6 | T3-06 (registry, `message_citations`, runtime state to Postgres) | DATA-07, DATA-12, DATA-18 | T3-08 merged | See ingestion spec | See ingestion spec |
| 7 | T3-07 (canonical teacher IDs) | DATA-13 | T8-01 | No payload rewrite in place | New collection |
| 8 | T3-11 (freeze graph writes; OKF compile report) | DATA-08, DATA-10, DATA-17 | D-05 | No data deletion | Flag |

A new script under `scripts/ops/` and `backend/scripts/ops/` must be byte-identical if it exists in both (`tests/test_repo_layout.py`). Put it in `backend/scripts/ops/` only.

## 9. Open questions

| ID | Question | Link |
|---|---|---|
| D-14 | Which collection serves, which encoder, which approved version? | `unresolved-questions.md` |
| D-15 | Who besides the builder writes to Qdrant? | `unresolved-questions.md` |
| D-08 | Where does the source bundle live? | `unresolved-questions.md` |
| PROPOSED D-DQ1 | Should the legacy store's `points_servable` compare text and hash (closes a stale-cache gap)? Recommendation: yes. | new |
| PROPOSED D-DQ2 | Which minimum `contained_in_other_span_rate` blocks promotion? The project scorecard sets the current threshold. | new |

## 10. Verified, assumptions, unknowns

**Verified** [V-STATIC at `c9b42d3e`]: the flag and name resolution (§2); contract contents; store write guards; metric names; scripts exist; `restore_drill.py` collection resolution; nightly workflow is fixture-only.

**Assumptions** [INF]: stores marked [per 06] behave as `06` describes; Postgres has no FK between `source_releases` and `corpus_sources` (I read the `source_releases` and `corpus_sources` migrations only).

**Unknowns** [LIVE-Q, LIVE-L]: every live count, distribution and duplicate rate; the owner's effective flags; whether v10 payloads carry `licensed`; the Redis key population.
