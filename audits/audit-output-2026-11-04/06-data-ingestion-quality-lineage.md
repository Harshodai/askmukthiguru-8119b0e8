# 06 — Data ingestion, data quality and cross-database lineage

> **2026-11-06:** Superseded in part by `specifications/DATA_QUALITY_AND_CROSS_STORE_CONSISTENCY_SPEC.md` (15-field contract per datastore, lineage with link IDs, reconciliation rules). Status of findings: `FINAL_PENDING_WORK_REGISTER.md`.

Owner: Specialist S2. Target: `origin/main@46b808fb`. Conventions: `CONVENTIONS.md`.
No live store was contacted. Every count from a live store is `[DOC-CLAIM]` or needs `[LIVE-Q]`. The read-only verification procedure is in `22-qdrant-graph-deferred-validation-runbook.md`.

## 1. Summary

1. The serving corpus (first-person collections) is **not reproducible from the repository plus infrastructure**. Only host-side scripts can build it, and they read from `~/mukthiguru_attribution_data` on the owner's Mac. See DATA-01.
2. The repository has **two unrelated ingestion systems** for the same videos:
   - (A) the online `IngestionPipeline`, which writes YouTube-caption text to the chat corpus, LightRAG, Memgraph and OKF;
   - (B) the offline first-person builders, which write Whisper-on-archived-audio text to `first_person_v*`.
   No key joins the two. See DATA-09.
3. The word `transcript_hash` has **three meanings** across stores. The v10 serving gate had to move to a second field, `source_text_hash`. See DATA-03.
4. **No cross-store deletion or takedown exists for teaching content.** A video "block" is a JSON file that only the first-person serving path reads. See DATA-07.
5. The **rights register that every served clip depends on** is a file under `audits/`. The Railway image does not copy that directory. The result is a silent fail-closed outage: every clip abstains. See DATA-02.
6. The v10 serving collection **fails its own data-quality scorecard** (13 of 26 checks) `[DOC-CLAIM]`. See DATA-14.
7. Positive evidence:
   - The deterministic IDs are well designed.
   - The v8 builder diffs IDs and refuses an empty build.
   - The `fp-context-v1` schema is strict (`extra="forbid"`, hash validators, deterministic span IDs).
   - The serve-time rights check fails closed.

## 2. Datastore inventory (discovered, not assumed)

### 2.1 Stores the running system uses

| # | Store | Technology | What it holds | Writers | Readers on serving path today | Evidence |
|---|---|---|---|---|---|---|
| S-1 | `first_person_v10` (and v11 staging) | Qdrant, schema `fp-context-v1` | ParentUnit + SourceSpan records. Vectors: `passage_dense` 1024-d, `passage_sparse` | Host scripts `backend/scripts/ops/build_full_corpus_v10.py`, `backend/scripts/ops/build_fp_context_from_v9.py`, ingestion dual-index (off) | v10-only posture: context harness (`first_person_context_store.py`) | `backend/domain/first_person_context.py:166-301`, `backend/config/first_person_serving_contract.json` [V-STATIC] |
| S-2 | `first_person_v8` (legacy default), v1-v9 | Qdrant, schema `first-person-legacy-clip-v1` | Flat clips. Vectors: `passage_dense`, `question_dense`, `passage_sparse` | `backend/scripts/ops/build_first_person_index.py` (host) | Legacy path whenever the harness flags are off (code default) | `backend/app/config.py:41,205-209,2294-2310`; `backend/services/first_person_store.py:276-376` [V-STATIC] |
| S-3 | `spiritual_wisdom_contextual` (chat corpus); legacy `spiritual_wisdom` | Qdrant, vectors `dense`/`sparse` | YouTube-caption chunks, RAPTOR summaries | `IngestionPipeline`, `QdrantIndexer.upsert_chunks`, 7 scripts under `scripts/ingestion/` | Only when the first-person module does not claim (personalize turns) or fails open | `backend/app/config.py:709`; `backend/services/qdrant/indexer.py:203-480`; `backend/rag/pipeline_registry.py:79-104` [V-STATIC] |
| S-4 | `lightrag_vdb_{entities,relationships,chunks}_baai_bge_m3_1024d` | Qdrant (via LightRAG) | LLM-extracted entities and relations | `LightRAGService.ainsert` from ingestion | Generating path only (`rag_lightrag_context_injection_enabled=True`) | `backend/services/lightrag_service.py:370-415,775-790`; `lessons.md:6293-6300` [V-STATIC]/[DOC-CLAIM] |
| S-5 | `mukthi_semantic_cache_1024d` | Qdrant | Chat answer cache (semantic) | Cache adapter | Generating path only | `backend/services/cache/semantic_adapter.py:56`; `config.py:1588` [V-STATIC] |
| S-6 | `canonical_memory_vectors`, `second_brain_vault` | Qdrant | User memory vectors, user vault | Memory services | Memory features (S3 scope) | `services/canonical_memory/vector_index.py:49`; `services/second_brain/vault_index.py:45` [V-STATIC] |
| S-7 | Memgraph (`base` entities, `__Chunk__`, ontology labels, `TU_*`) | Memgraph via neo4j driver | Ontology and LightRAG graph, TeachingUnit projection (off) | `ontology_writer.py`, `triple_extractor.py`, LightRAG, `backend/scripts/ops/build_teaching_unit_graph.py` | Generating path graph context; first-person graph expansion (off) | `backend/ingest/ontology_writer.py:152-180`; `backend/ingest/pipeline.py:4380-4400` [V-STATIC] |
| S-8 | LightRAG working dir `data/lightrag` | Local files | LightRAG KV and doc status | LightRAG | LightRAG | `lightrag_service.py:387` [V-STATIC] |
| S-9 | Supabase Postgres | Postgres, 139 migrations, about 85 tables | Users, conversations, memory, telemetry, ingestion jobs, source releases, review queues | Backend, frontend (Supabase JS), edge functions | Auth, conversations, telemetry, memory | `supabase/migrations/` [V-STATIC] |
| S-10 | Redis | Redis | FP exact cache `cache:first_person_exact:*` (TTL 86,400 s); chat cache `mukthiguru:cache:tenant:*`; `mukthiguru:semcache:*`; rate limit `rl:*`; anon quota `anon:*`; locks `mukthiguru:lock:*`; `whatsapp:*`; Celery | Backend, workers | Yes (exact cache, quota, rate limit) | `first_person_pipeline.py:135,3033-3066` [V-STATIC] |
| S-11 | OKF bundle `memory/okf/` | Markdown + `compiled.json` (10.9 MB) | 1,541 tracked `.md` files (820 in `staging/`). 429 compiled entries (424 teaching) | `backend/scripts/extract_okf_from_stores.py` (LLM), `okf_compile` | Routing/reflection only (invariant 12) | `memory/okf/compiled.json` [V-STATIC] |
| S-12 | Rights register | JSON file `audits/evidence/public_release_phase4_rights_manifest_2026-10-22.json` | 751 assets: 702 `confirmed_channel_owner`, 2 `confirmed_video_owner`, 46 `missing_evidence`, 1 `pending_owner_review` | Offline script | **Every served clip** (`source_is_authoritatively_licensed`) | `services/first_person_serving_contract.py:177-186`; `services/qdrant/indexer.py:44-135` [V-STATIC] |
| S-13 | Serving contract | JSON `backend/config/first_person_serving_contract.json` | Schema, role, corpus version, required fields for v1-v11 | Hand-edited | Startup and per-request contract check | [V-STATIC] |
| S-14 | Video decisions | JSON files in `backend/data/fp_video_decisions` (or `FIRST_PERSON_VIDEO_DECISIONS_DIR`) | Per-video human approve/block and audit log | Admin API | First-person serving filter and cache re-check | `services/first_person_video_decisions.py:98-367` [V-STATIC] |
| S-15 | Quality allow/block lists, calibration JSON | Files (paths from settings) | Clip allow/deny IDs; calibration profile (none fitted) | Offline | First-person pipeline | `first_person_pipeline.py:553-640`; `config.py:487-492` [V-STATIC] |
| S-16 | Host audio archive | `~/mukthiguru_attribution_data/audio_archive/` (`wavs/<video_id>.wav`, `manifest.json`) | Immutable 16 kHz mono WAV | `scripts/ops/audio_archive.py` | Builders only | Root `CLAUDE.md` invariant 17 [DOC-CLAIM]; `scripts/ops/audio_archive.py` exists [V-STATIC] |
| S-17 | Host attribution data | `~/mukthiguru_attribution_data/*` (transcripts, ECAPA verdicts, channel metadata, eval summaries) | Inputs to builders and to the rights manifest | Host scripts | Builders only | Rights manifest `independent_sources.channel_metadata.paths` = `/Users/harshodaikolluru/mukthiguru_attribution_data/...` [V-STATIC] |
| S-18 | Release evidence files | `audits/evidence/*.json[l]`, `audits/manifests/` | Candidate tiers, verdicts, rights joins, gold labels, decisions | Offline scripts | Local review route (owner-only), release gates | `audits/evidence/` [V-STATIC] |
| S-19 | Tracked backups | `data/*.json` (largest: `neo4j_graph_dump.json`, 8.0 MB) | Old graph and Qdrant point backups | One-off scripts | None | [V-STATIC] |

### 2.2 Stores defined but not on any serving path

| Store | Status | Evidence |
|---|---|---|
| `kb_sources`, `kb_chunks` (pgvector `vector(768)`) | A second vector store. Its dimension (768) differs from BGE-M3 (1024). One backend file references it. | `supabase/migrations/20260605023720_*.sql:22-66` [V-STATIC] |
| `gurus` table (`slug`, `collection_name`) | A second teacher registry. It does not match `backend/config/gurus.yaml`. | `20260703170000_gurus_and_configurations.sql:18-27` [V-STATIC] |
| `fp-context-v1` / `fp_context_v1` collections | Named in code and in the TU-graph builder default. The serving collection is `first_person_v10`. | `config.py:296-302`; `backend/scripts/ops/build_teaching_unit_graph.py:425-426` [V-STATIC] |
| GPTCache server | Compose service `gptcache-server` | `backend/docker-compose.yml:594` [V-STATIC] |

## 3. Per-store assessment

| Store | Identifier | Versioning | Duplicate / orphan / stale risk | Deletion | Backup | Tenant boundary |
|---|---|---|---|---|---|---|
| v10 (S-1) | `source_span_id = sha256(guru|video|corpus_version|word_start|word_end|transcript_hash)`; point = `uuid5(ns, span_id)` | `corpus_version` is part of the ID. A new version gets new IDs. | The builder is additive and skips present videos (DATA-05). 17.14% of spans are contained in another span `[DOC-CLAIM]`. | Manual per-ID delete only | Snapshots on the owner's host `[DOC-CLAIM]` | `guru_id`. No tenant field. |
| v8 (S-2) | `uuid5(FIRST_PERSON_NAMESPACE, transcript_hash:start_ms:end_ms)`. `video_id` is not in the ID. | New collection per version | The builder diffs and deletes stale IDs and refuses an empty build. 27% of clips are contained in another clip; 1 of 1,802 clips is unexplained `[DOC-CLAIM]`. | Builder diff | Snapshots on the owner's host `[DOC-CLAIM]` | `teacher_id` |
| Chat corpus (S-3) | `make_point_id(source_url, chunk_index, raptor_level)` | Alias swap via `qdrant_aliases.py`; `source_releases` | The raw URL is not canonicalised (DATA-10). Scripts write without `replace_source_url`. `teacher_id` is not uniform: only 4,337 of 12,904 points are `ekam` `[DOC-CLAIM]`. | `delete_by_source` (Qdrant only) | Nightly cron, not installed `[DOC-CLAIM]` | `tenant_id` on edges; corpus scope |
| LightRAG (S-4, S-8) | Content hash (LightRAG internal) | None | No `file_paths` provenance (DATA-08). 41.4% of chunks were contaminated `[DOC-CLAIM]`. | None by source | None found | None |
| Memgraph (S-7) | `entity_id` (name) MERGE; `__Chunk__` keyed by the first 300 characters of text | None | Last-writer-wins `source_doc_id` (DATA-08) | `DETACH DELETE` only in consolidation and user erasure | Cron, not installed `[DOC-CLAIM]` | `tenant_id='oneness'` on edges (needs backfill script after each ingestion, root `CLAUDE.md`) |
| Postgres (S-9) | UUID PKs. 66 `ON DELETE CASCADE`, 9 `SET NULL`. RLS enable statements for 84 tables. | Migrations; 32 tables have more than one `CREATE TABLE` (DATA-11) | Stored citations are unstructured (DATA-12) | User-erasure cascades (S3 scope) | **None**. The backup workflow refuses public-repo artifacts (`PROD_READINESS_TASK_LIST` §2 N2) `[DOC-CLAIM]` | RLS per user |
| Redis (S-10) | FP key = `sha256(norm_query, teacher, lang, collection, calibration, rerank, ans, policy_fingerprint)` | Policy fingerprint includes the rights/contract file digest | TTL 24 h. A hit re-checks `points_servable` (rights, block, eligibility). | TTL | Not needed (cache) | Language and teacher in key |
| OKF (S-11) | File path; `source` URL | Git | 721 eligible files vs 429 compiled entries (gap not explained). `compiled.json` holds absolute host paths. | Git | Git (public repo) | Teacher subdirectories |
| Rights register (S-12) | `canonical_source_url`, `video_id`, `source_asset_id` | Date in file name; pinned path | 46 `missing_evidence` assets | Edit file | Git | n/a |

## 4. End-to-end lineage

### 4.1 First-person path (the path that serves users)

```mermaid
flowchart LR
  YT[YouTube video\nvideo_id] -->|yt-dlp android/ios clients| AA[(Host audio archive\nwavs/video_id.wav\nmanifest.json)]
  AA -->|Whisper, sacred-vocab prompt| TR[(Host transcripts\nTranscript Hash header)]
  TR -->|word timings + asr_cleaner + boundaries| SEG[Spans\nword_start..word_end]
  AA -->|ECAPA per-span slice| SPK[(Speaker verdicts\ncalibration_v2 id)]
  SEG --> B10[build_full_corpus_v10.py\nHOST ONLY]
  SPK --> B10
  RR[(Rights manifest\naudits/evidence/...json)] --> B10
  B10 -->|BGE-M3 dense+sparse| Q10[(Qdrant first_person_v10\nsource_span_id -> uuid5)]
  Q10 -->|dense-only group-by parent| H[Context harness\nHASH_GATE source_text_hash]
  RR -->|serve-time licence check| H
  VD[(Video decisions JSON)] --> H
  H --> CIT[Citation\nvideo_id start_ms end_ms\nplayback ±0.25 s]
  CIT --> UI[UI YouTube embed]
  CIT -.->|text[] only| PG[(Postgres chat_messages.citations)]
```

### 4.2 Online ingestion path (feeds the generating graph, which is off the teaching path)

```mermaid
flowchart LR
  URL[Admin URL] --> IP[IngestionPipeline.ingest_url]
  IP -->|youtube-transcript-api / yt-dlp subtitles / audio fallback| CAP[Caption text]
  CAP --> CH[Chunker + quality gate]
  CH -->|point = source_url:chunk_index:raptor_level| QC[(Qdrant spiritual_wisdom_contextual)]
  CH -->|ainsert(text) no file_paths| LR[(LightRAG: Qdrant x3 + Memgraph + data/lightrag)]
  CH --> OW[ontology_writer / triple_extractor] --> MG[(Memgraph base nodes)]
  CH -->|extract_okf auto_approve=False| OKFS[(memory/okf/staging)]
  CH -.->|fp_dual_index_collections, OFF| Q10[(first_person_v10)]
  IP --> SR[(Postgres source_releases / corpus_sources / ingest_jobs)]
```

### 4.3 Identity chain and where it breaks

| Level | Identity | Carried forward? | Break |
|---|---|---|---|
| Source | `video_id`. One hard-coded re-upload map (`CANONICAL_VIDEO_IDS`, 1 pair). | Yes | Re-uploads beyond one pair are not unified (`first_person_store.py:87-103`). |
| Audio | `wavs/<video_id>.wav`, manifest | Host only | Not in any deployable store (DATA-01). |
| Transcript | `transcript_hash` of the whole body (v10) | Into span ID | Online captions have no hash link to the Whisper transcript (DATA-09). |
| Segment | `word_start`/`word_end`, `start_ms`/`end_ms` | Yes | v8 IDs use `start_ms`/`end_ms`, so jitter of ±200 ms gives a new ID (`first_person_store.py:89-96` comment). |
| Embedding | `embedding_model`, `embedding_revision` in v10 payload (`first_person_context.py:249-250`) | v10 only | Not checked at serve time (RET-07). v8 has no record. |
| Graph | `entity_id` (name), `source_doc_id` overwritten | Partial | Last writer wins; LightRAG has no source (DATA-08). |
| Answer | Citation dict: `point_id`, `video_id`, `start_ms`, `end_ms`, `transcript_hash` (= clip hash on v10), `video_transcript_hash` | Yes, in the response | Persisted only as `text[]` (DATA-12). |
| UI | Playback window `start_ms − 0.25 s` to `end_ms + 0.25 s` (`first_person_pipeline.py:154,1697-1700`) | Yes | Frontend handling is S4 scope. |

## 5. Cross-store consistency matrix

| Entity | Authoritative store (today) | Copies | Join key | Consistency check that exists | Missing check |
|---|---|---|---|---|---|
| Video (source) | None. It is split across the host manifest, `corpus_sources`, the rights manifest and Qdrant payloads. | 6 or more | `video_id` (and raw URL in the chat corpus) | Rights manifest lookup at serve time | A single source registry; URL canonicalisation; re-upload map |
| Transcript text | Host transcripts (FP); YouTube captions (chat) | 2 divergent | None | v10 builder recomputes the body hash (`backend/scripts/ops/build_full_corpus_v10.py:349-385`) | Chat ↔ FP transcript join |
| Served span text | Qdrant v10 payload `verbatim_text` | Release evidence JSONL | `source_span_id` | `source_text_hash == sha256(verbatim_text)` at serve (harness HASH_GATE) | Continuous audit of the live collection (DATA-15) |
| Speaker attribution | v10 payload `speaker_verified` + `voice_verification_method` | Speaker verdict files (host) | `source_span_id` | Builder gate; v11 post-checks `[DOC-CLAIM]` | Write lock (DATA-06); the dual-index path fabricates it (DATA-04) |
| Rights status | Rights manifest file | Payload `domain_rights_status`, `rights_cleared` | URL / `video_id` | Serve-time re-resolution (fail closed) | Shipping the file to Railway (DATA-02) |
| Takedown | Video decisions JSON | None | `video_id` | FP serve and cache-hit re-check | Every other store (DATA-07) |
| Graph concept → evidence | Memgraph | LightRAG Qdrant | Entity name | None | Span-level provenance (DATA-08) |
| OKF entry → source | `source` URL in front matter | `compiled.json` | URL | `backend/scripts/ops/data_quality_audit.py` OKF quote check | Compile drift (721 vs 429) |
| Conversation → citation | `chat_messages.citations text[]` | None | Free text | None | Structured citation table (DATA-12) |
| Corpus version → release approval | Owner decision files | Serving contract | `corpus_version` | None | Binding check (DATA-16) |

## 6. Deletion propagation and re-ingestion

| Event | Chat corpus | v8 / v10 | LightRAG | Memgraph | OKF | Redis | Postgres | Verdict |
|---|---|---|---|---|---|---|---|---|
| Re-ingest a video (same URL) | Two-phase replace when the pipeline passes `replace_source_url` (`indexer.py:220-480`). Scripts do not. | Not touched | Re-extract; duplicate merge risk | MERGE by name | New staging entry | `_invalidate_answer_caches(source_url)` (`pipeline.py:3598`) | New `source_releases` row | Partial |
| Re-ingest under a different URL form | New point set (duplicate) | n/a | Duplicate | Merge | Duplicate | Miss | Same `source_identity` (video ID) | **Duplicates** (DATA-10) |
| Rebuild FP v10 for a corrected video | n/a | **Skipped**: "already indexed" (`backend/scripts/ops/build_full_corpus_v10.py:867-894`) | n/a | n/a | n/a | Policy digest changes only if contract/rights files change | n/a | **Stale** (DATA-05) |
| Takedown of a video | Not removed | Blocked at serve via JSON | Not removed | Not removed | Not removed | FP cache re-check blocks it | Old citations remain | **Incomplete** (DATA-07) |
| User erasure | n/a | n/a | n/a | `DETACH DELETE` user and memories (`app/api/memory.py:1290`) | n/a | Memory keys | Cascades | S3 scope |

## 7. Data-quality scorecard

Scale: Good / Fair / Poor / Unknown. Numbers are `[DOC-CLAIM]` unless marked `[V-STATIC]`.

| Dimension | Rating | Evidence |
|---|---|---|
| Accuracy (text = speech) | Poor–Fair | v10: `text_edited_vs_source_rate` 48.92% (1,339/2,737); `script_mixed_or_loop` 9 spans (`audits/evidence/fp_data_quality_scorecard_v10_live_2026-10-25.md`). Separately, 23 of 24 served clips matched YouTube captions (`PROD_READINESS_TASK_LIST` §0). |
| Completeness (self-contained thoughts) | Poor | v10: `boundary_defect_rate` 24.48%; `strict_clean_rate` 39.90% (target ≥ 60%). v8 grading: grade A was 336 of 1,801 (18.7%); the strict second pass kept 119 (6.6%). "About 1 in 7 clips is clean" (`PROD_READINESS_TASK_LIST` §0). Only 15/29 test questions had one showable clip in the top 10 (root `CLAUDE.md` invariant 24). |
| Uniqueness | Fair | v10: 0 duplicate identities; `duplicate_text_rate` 1.17%; `contained_in_other_span_rate` 17.14%. v8: 27% contained. v7: 1,484 of 3,236 (45.9%) stale orphans (root `CLAUDE.md` invariant 23). LightRAG duplicates not measured. |
| Consistency | Poor | Three meanings of `transcript_hash` (DATA-03) `[V-STATIC]`; teacher-ID vocabulary drift (DATA-13) `[V-STATIC]`; v10 `transcript_hash == sha256(verbatim_text)` on only 1,839 of 2,758 children (root `CLAUDE.md` invariant 2). |
| Validity | Good (v10 schema) / Fair (legacy) | `fp-context-v1` validators: hash equality, deterministic ID, `extra="forbid"` (`first_person_context.py:166-301`) `[V-STATIC]`. v10: 0 missing required fields, 0 invalid time windows. |
| Timeliness | Fair | Scorecard `export_age_days` 4.6. No continuous audit (DATA-15). |
| Provenance | Fair (FP) / Poor (graph, chat) | v10 `speaker_verified_without_method` 732 (2026-10-25), backfilled on 2026-10-31: 729 pass, 13 spans demoted (`audits/evidence/first_person_v11_speaker_backfill_and_build_2026-10-31.md`). LightRAG has no source (DATA-08). |
| Version integrity | Poor | Corpus-version mismatch between serving and approved evidence (DATA-16); additive v10 builder (DATA-05); concurrent-writer incident (DATA-06). |
| Rights coverage | Fair | 702 + 2 of 751 assets confirmed; 46 `missing_evidence`; 1 pending `[V-STATIC]` (rights manifest). Basis: owner confirmations of 2026-09-23/26, channel-level, including a `channel:times-now` entry. The legal sufficiency is S4/IP scope `[HUMAN]`. |

## 8. Findings

### DATA-01 — The serving corpus cannot be rebuilt from the repository and infrastructure
| Field | Value |
|---|---|
| Pillars | P1, P3, P4 |
| Category | Lineage / disaster recovery |
| Severity | P1 |
| Type | Architectural risk |
| Confidence | High |
| Evidence | `backend/scripts/ops/build_full_corpus_v10.py:19-24` (needs `--wav-dir`, `--attr-root`); the rights manifest `independent_sources.channel_metadata.paths` points to `/Users/harshodaikolluru/mukthiguru_attribution_data/...`; `scripts/ingestion/corpus/` has 0 tracked files; root `CLAUDE.md` invariants 17-18 (host-side embedding, host archive). [V-STATIC] |
| Actual behaviour | Only the owner's Mac holds the audio, transcripts, speaker verdicts and channel metadata that produce `first_person_v10`. |
| Expected behaviour | A versioned, checksummed source bundle in durable storage can rebuild any serving collection deterministically. |
| Root cause | The builders grew as host scripts. The Docker image cannot run BGE-M3/ECAPA (6 GiB OOM). |
| User impact | Losing the host loses the ability to correct or rebuild the answers users see. |
| Downstream impact | No CI rebuild, no staging parity, unbounded RPO for source truth. |
| Dependencies | Object storage decision (S1); rights to store audio `[HUMAN]` (S4/IP). |
| Remediation | Define `source_bundle/<corpus_version>/` (WAV, transcripts, verdicts, rights snapshot, `MANIFEST.sha256`) in private object storage. Builders read only from a bundle. Record the bundle digest in the collection's release record. |
| Acceptance criteria | A clean machine with the bundle and a Qdrant instance rebuilds v10. Point IDs and `source_text_hash` match 100%. |
| Regression test | `test_builder_reproducible_from_bundle` on a 3-video fixture bundle: two runs give identical point sets. |
| Implementation risk | Medium (storage cost; audio rights). |
| Verification | [V-STATIC] + [LIVE-L] |

### DATA-02 — The rights register is not in the Railway image, so every clip would abstain
| Field | Value |
|---|---|
| Pillars | P1, P4 |
| Category | Deployment data wiring |
| Severity | P1 |
| Type | Confirmed defect (deployment) |
| Confidence | High for the code path; Medium for Railway behaviour (not deployed) |
| Evidence | `services/first_person_serving_contract.py:177-186` (`RIGHTS_MANIFEST_RELPATH = "audits/evidence/public_release_phase4_rights_manifest_2026-10-22.json"`); `services/qdrant/indexer.py:55-60` (missing file → `{}`); `indexer.py:103-135` (→ `"unverified"`); `first_person_rights.py:6-26` (fail closed). `backend/Dockerfile.railway` copies `backend/`, `memory/` and `config/helplines.yaml`, not `audits/`. `backend/docker-compose.yml:468` mounts `../audits:/app/audits:ro`. A search found no startup or health check on register load. [V-STATIC] |
| Actual behaviour | On an image without the mount, `source_is_authoritatively_licensed` returns False for every clip. The route abstains on every question with no error. |
| Expected behaviour | Startup fails, or `/api/health` turns red, when the register is missing or has 0 cleared assets. |
| Root cause | Release evidence and runtime data share one directory. The runtime dependency is implicit. |
| User impact | Total silent loss of answers in production. |
| Downstream impact | Abstain metrics would look like "the gates work". |
| Dependencies | S1 Railway runbook (`22b`). |
| Remediation | Move the register (or a derived `rights_runtime.json`) into `backend/config/` or a Postgres table. Pin it by sha256 in the serving contract. Add a startup check: assets loaded > 0 and digest matches. |
| Acceptance criteria | The Railway image starts only with a valid register. `/api/health` reports `rights_assets_cleared=704`. |
| Regression test | Container smoke test with the register absent → startup refused. |
| Implementation risk | Low |
| Verification | [V-STATIC] + [LIVE-R] |

### DATA-03 — `transcript_hash` has three meanings across stores
| Field | Value |
|---|---|
| Pillars | P3, P4 |
| Category | Schema consistency / integrity gate |
| Severity | P1 |
| Type | Confirmed defect (semantic drift) |
| Confidence | High |
| Evidence | Legacy v8: clip hash, validated (`first_person_store.py:172-215`). v10 builder: whole-transcript body hash (`backend/scripts/ops/build_full_corpus_v10.py:349-385`; `first_person_context.py:12-15,261-265`). Ingestion dual-index: clip hash in the same v10 field (`backend/ingest/pipeline.py` ≈3759-3761: `"transcript_hash": text_hash, "source_text_hash": text_hash`). Citation dict: key `transcript_hash` carries the clip hash; `video_transcript_hash` carries the body hash (`first_person_context_store.py:1320-1323`). Root `CLAUDE.md` invariant 2: match on only 1,839 of 2,758 v10 children `[DOC-CLAIM]`. [V-STATIC] |
| Actual behaviour | One field name holds different quantities depending on the writer. Within v10 itself, the two writers disagree. |
| Expected behaviour | One name per quantity: `video_transcript_sha256` and `span_text_sha256`. |
| Root cause | The v10 schema reused the legacy name with a new meaning. |
| User impact | A gate that reads the wrong field either quarantines valid clips (fewer answers) or passes edited text (integrity loss). |
| Downstream impact | Invariants 2 and 13 need special cases. Agents keep re-learning this. |
| Dependencies | DATA-05 (a rebuild path). |
| Remediation | In the next schema (`fp-context-v2`): rename both fields, remove `transcript_hash`, keep one `hash_fields.py` helper, and add a contract test over every writer. |
| Acceptance criteria | 0 occurrences of a bare `transcript_hash` in new writers. Integrity gate pass rate 100% on the rebuilt collection. |
| Regression test | Parametrised test over all FP writers: each payload's span hash equals `sha256(verbatim_text)`. |
| Implementation risk | Medium (cache keys, citations, frontend field). |
| Verification | [V-STATIC] + [LIVE-Q] |

### DATA-04 — The ingestion dual-index path writes fabricated provenance (latent)
| Field | Value |
|---|---|
| Pillars | P4, P3 |
| Category | Provenance integrity |
| Severity | P2 (becomes P0 when `FP_DUAL_INDEX_COLLECTIONS` is set) |
| Type | Confirmed defect (flag-gated) |
| Confidence | High |
| Evidence | `backend/ingest/pipeline.py:3630-3850`: `speaker_verified: meta.get("speaker_verified", True)`, `voice_verification_method: "ecapa_voxceleb_centroid_v1"`, `boundary_status: "verified"`, `rights_cleared: True`, `domain_rights_status` default `"licensed"`. No ECAPA run. The code comment admits it. Default `fp_dual_index_collections=""` (`config.py:217`). [V-STATIC] |
| Actual behaviour | When enabled, caption chunks enter a serving collection marked voice-verified and boundary-verified. |
| Expected behaviour | Unverified writes carry `speaker_verified=False`, `pending_voice_check`, and `boundary_status=unverified`. |
| Root cause | A convenience path that bypasses the builder's gates. |
| User impact | Users would see a "verified" label on unverified clips. |
| Downstream impact | Contaminates release evidence. |
| Dependencies | None |
| Remediation | Remove the path. If it stays, write only `unverified`/`pending` states, and let a guard test forbid literal `True` for provenance fields. |
| Acceptance criteria | No writer outside the builder can set `speaker_verified=True`. |
| Regression test | Static guard in `scripts/guards/lesson_guards.py`, plus a unit test over `_upsert_first_person_context`. |
| Implementation risk | Low |
| Verification | [V-STATIC] |

### DATA-05 — The v10 builder is additive and cannot refresh a corrected video
| Field | Value |
|---|---|
| Pillars | P3, P1 |
| Category | Re-ingestion / versioning |
| Severity | P1 |
| Type | Confirmed defect |
| Confidence | High |
| Evidence | `backend/scripts/ops/build_full_corpus_v10.py:867-894` (videos already present are skipped); `:1238-1258` (on failure, delete the attempted IDs only); `:1295-1298` (snapshot **after** the writes); there is no stale-ID diff. Contrast `backend/scripts/ops/build_first_person_index.py:677-783` (diff, delete stale, refuse empty). `backend/CLAUDE.md` rule: "dry-run → snapshot → ask → apply". [V-STATIC] |
| Actual behaviour | A corrected transcript or speaker verdict for an indexed video never reaches v10 unless someone deletes points by hand. |
| Expected behaviour | Per-video replace: build the new set, snapshot, upsert, delete stale IDs for that video, verify. |
| Root cause | Resume-on-crash logic uses "video present" as "video done". |
| User impact | Known defects persist in served answers. |
| Downstream impact | Manual deletes bypass audit. Combined with DATA-06, the state is unknowable. |
| Dependencies | DATA-06 |
| Remediation | Add `--refresh-videos`, a per-video manifest of expected IDs, a pre-apply snapshot, and a post-apply diff report. Keep the "protected target" refusal. |
| Acceptance criteria | Re-running with a changed transcript for 1 video changes only that video's points. The snapshot exists before the first write. |
| Regression test | Fixture Qdrant (local mode): build, mutate 1 transcript, rebuild → expected diff. |
| Implementation risk | Medium |
| Verification | [V-STATIC] |

### DATA-06 — Uncontrolled concurrent writers to serving collections
| Field | Value |
|---|---|
| Pillars | P1, P4 |
| Category | Write governance |
| Severity | P1 |
| Type | Confirmed defect (with an incident) |
| Confidence | High |
| Evidence | `config.py:710` (`qdrant_api_key=""`, "no auth (current default)"); `backend/docker-compose.yml:151-160` (ports 6333/6334 published, no API-key env). Incident: "another client (host `backend/.venv`) wrote tags/topics and re-set `speaker_verified=true` on 17 demoted spans" (`audits/evidence/first_person_v11_speaker_backfill_and_build_2026-10-31.md`). The static guard `fp_write_allowlist.txt` covers source files, not runtime clients. [V-STATIC]/[DOC-CLAIM] |
| Actual behaviour | Any process that reaches port 6333 can overwrite serving payloads. |
| Expected behaviour | The serving backend uses a read-only key. Writes need a separate key and a write-lock record. |
| Root cause | No authentication or role separation on Qdrant. |
| User impact | Demoted clips can be served as verified again. |
| Downstream impact | Release evidence can become false after sign-off. |
| Dependencies | S1 SEC (network and secrets). |
| Remediation | Enable `QDRANT__SERVICE__API_KEY` and `READ_ONLY_API_KEY`. The backend gets the read-only key. Builders hold the write key. Add a payload-digest check after each sign-off. |
| Acceptance criteria | A write with the backend key returns 403. A nightly digest diff of v10 is empty unless a build ran. |
| Regression test | Integration test with local Qdrant and the read-only key. |
| Implementation risk | Low–Medium (cache, admin tools need the write key). |
| Verification | [V-STATIC] + [LIVE-Q] |

### DATA-07 — No cross-store takedown or deletion for teaching content
| Field | Value |
|---|---|
| Pillars | P4, P3 |
| Category | Deletion propagation |
| Severity | P1 |
| Type | Confirmed defect |
| Confidence | High |
| Evidence | Delete endpoints exist only for memory, jobs, push and teachings-curated (`rg @router.delete backend/app`). The video block is a JSON file read only by FP serving (`services/first_person_video_decisions.py:348-367`; `first_person_store.py:596-631`). `delete_by_source` is Qdrant-chat only (`indexer.py:735`). LightRAG `ainsert(clean_text)` has no source (`pipeline.py:1270,1547`). [V-STATIC] |
| Actual behaviour | Withdrawn content stays in the chat corpus, LightRAG, Memgraph, OKF, the semantic cache and stored citations. |
| Expected behaviour | A takedown request removes or blocks the source in every store and produces a verification report. |
| Root cause | No authoritative source registry drives the stores. |
| User impact | A teacher or rights holder cannot have content withdrawn with confidence. |
| Downstream impact | Blocks the guru-review promise of "content correction" (S4). |
| Dependencies | DATA-08, DATA-12, a source registry. |
| Remediation | Make `corpus_sources` (Postgres) the source registry. Implement `takedown(source_identity)` with a deleter per store (Qdrant collections by `video_id`, Memgraph by provenance, OKF by `source`, Redis caches by pattern, citations flagged) and an audit row. |
| Acceptance criteria | After a takedown, the runbook queries (`22`) return 0 hits for that `video_id` in every store, within one run. |
| Regression test | An end-to-end test with local Qdrant/Memgraph fakes. |
| Implementation risk | Medium |
| Verification | [V-STATIC] |

### DATA-08 — The graph and LightRAG stores have no span-level provenance
| Field | Value |
|---|---|
| Pillars | P3, P4, P2 |
| Category | Lineage |
| Severity | P2 |
| Type | Confirmed defect |
| Confidence | High |
| Evidence | `ontology_writer.py:152-163` (`MERGE (n:base {entity_id})` then `SET n.source_doc_id`, so the last writer wins); `backend/ingest/pipeline.py:4392` (`MERGE (src:__Chunk__ {text: $chunk_text[:300]})`); `pipeline.py:1270,1547` (`ainsert(clean_text)` without `file_paths`); `lessons.md:6295` (LightRAG chunks 41.4% contaminated) `[DOC-CLAIM]`. [V-STATIC] |
| Actual behaviour | A graph fact cannot be traced to a video and timestamp, or deleted by source. |
| Expected behaviour | Every node or edge used as evidence lists the `source_span_id`s that support it. |
| Root cause | LightRAG defaults; name-keyed MERGE. |
| User impact | No user impact today (off the teaching path). It blocks any graph-grounded synthesis. |
| Downstream impact | Takedown impossible (DATA-07). |
| Dependencies | RET-05 decision. |
| Remediation | Freeze LightRAG writes. If a concept graph stays, key it by `(corpus_version, concept_id)` and store `support_span_ids[]` on edges. |
| Acceptance criteria | 100% of edges used at serve time have a non-empty `support_span_ids` that resolve in the serving collection. |
| Regression test | Graph builder unit test with a 2-video fixture. |
| Implementation risk | Low (freeze) / Medium (rebuild) |
| Verification | [V-STATIC] |

### DATA-09 — Two transcript lineages for the same video, with no join
| Field | Value |
|---|---|
| Pillars | P3 |
| Category | Source of truth |
| Severity | P2 |
| Type | Confirmed defect |
| Confidence | High |
| Evidence | Online ingestion fetches captions or downloads directly (`backend/ingest/youtube_loader.py:7-12,190-195`; `pipeline.py:542-555,1129-1137`), which contradicts root `CLAUDE.md` invariant 17 ("ingestion never downloads directly"). FP builders use archived WAV + Whisper. Chat IDs are `source_url:chunk_index`; FP IDs come from text hashes. [V-STATIC] |
| Actual behaviour | The same discourse has two different texts in two stores. |
| Expected behaviour | One canonical transcript per `(video_id, transcript_version)`. |
| Root cause | Two eras of the product. |
| User impact | Low today. High if chat synthesis returns. |
| Downstream impact | Graph and OKF are derived from the weaker caption text. |
| Dependencies | DATA-01 |
| Remediation | Retire caption ingestion for teacher content. Derive all stores from the canonical transcript bundle. |
| Acceptance criteria | Every derived record carries `transcript_version` + `video_id`. |
| Regression test | Lineage test: each chat chunk resolves to a transcript span. |
| Implementation risk | Medium |
| Verification | [V-STATIC] |

### DATA-10 — Chat-corpus IDs use the raw URL; scripts skip stale-chunk cleanup
| Field | Value |
|---|---|
| Pillars | P3 |
| Category | Uniqueness |
| Severity | P2 |
| Type | Probable defect |
| Confidence | Medium |
| Evidence | `services/qdrant/utils.py:23-35` (ID from `source_url`); `backend/ingest/pipeline.py:1038-1216` (`"source_url": url`, uncanonicalised). Only `backend/ingest/pipeline.py:3537` and `video_pipeline.py:311` pass `replace_source_url`. `scripts/ingestion/{bulk_ingest_async,smart_extract_and_ingest,ingest_pageindex_json,ingest_structure_to_qdrant,bulk_ingest_whisper,ingest_four_sacred_secrets}.py` do not. [V-STATIC] |
| Actual behaviour | URL variants (`youtu.be`, `&t=`) create parallel point sets. Shrinking chunk counts leave stale tail chunks. |
| Expected behaviour | ID derived from the canonical `video_id`; every writer replaces by source. |
| Root cause | No canonicalisation helper at the write boundary. |
| User impact | Duplicated evidence on the generating path. |
| Downstream impact | Inflated counts in audits. |
| Dependencies | None |
| Remediation | Canonicalise in `QdrantIndexer.upsert_chunks`. Make `replace_source_url` mandatory. |
| Acceptance criteria | Runbook query R-9 (`22`) finds 0 `video_id`s with points under more than one `source_url`. |
| Regression test | Unit test: two URL forms → the same IDs. |
| Implementation risk | Low |
| Verification | [V-STATIC] + [LIVE-Q] |

### DATA-11 — Supabase schema drift from repeated `CREATE TABLE IF NOT EXISTS`
| Field | Value |
|---|---|
| Pillars | P3, P6 |
| Category | Migration integrity |
| Severity | P2 |
| Type | Confirmed defect |
| Confidence | High |
| Evidence | 32 tables are created in more than one migration (for example `app_settings` ×3, `guru_memories`, `user_profiles`, `pending_extractions`). `doctrine_faqs.citations` is added as `jsonb` (`20260824140000_*.sql:8`) and again as `TEXT` (`20260919000000_*.sql:6`). Lovable UUID-named migrations are mixed with hand-written ones. [V-STATIC] |
| Actual behaviour | The second definition silently does nothing. The real columns depend on which migration ran first. |
| Expected behaviour | One definition per table. CI compares the migrated schema with a committed snapshot. |
| Root cause | Two authoring tools (Lovable and agents) wrote migrations independently. |
| User impact | Latent runtime errors on fresh databases. |
| Downstream impact | Railway Postgres may differ from the developer database. |
| Dependencies | S1 (`migration-revert-check.yml`). |
| Remediation | Generate `supabase/schema_snapshot.sql` from a clean migrate. Diff it in CI. Squash a baseline. |
| Acceptance criteria | A clean-database migrate equals the snapshot. 0 duplicate `CREATE TABLE`s in new migrations. |
| Regression test | A CI job using the Supabase CLI. |
| Implementation risk | Medium |
| Verification | [V-STATIC] |

### DATA-12 — Stored answer citations are unstructured
| Field | Value |
|---|---|
| Pillars | P5, P4, P3 |
| Category | Lineage (answer level) |
| Severity | P2 |
| Type | Confirmed defect |
| Confidence | High |
| Evidence | `supabase/migrations/20260506064449_*.sql:34-42` (`chat_messages.citations text[]`). [V-STATIC] |
| Actual behaviour | A saved answer cannot be re-verified, replayed or withdrawn by span. |
| Expected behaviour | `message_citations(message_id, collection, corpus_version, point_id, source_span_id, video_id, start_ms, end_ms, span_text_sha256)`. |
| Root cause | The schema predates first-person citations. |
| User impact | Saved wisdom and revisit features (P5) cannot show a stable, checkable source. |
| Downstream impact | Takedown cannot reach history. |
| Dependencies | DATA-07 |
| Remediation | Add the table. Write it in the response assembly stage. |
| Acceptance criteria | 100% of FP answers persist structured citations. A re-verify job flags rows whose span hash no longer resolves. |
| Regression test | API test: chat → citations rows. |
| Implementation risk | Low |
| Verification | [V-STATIC] |

### DATA-13 — Teacher identity vocabulary differs per store
| Field | Value |
|---|---|
| Pillars | P4, P3 |
| Category | Consistency |
| Severity | P2 |
| Type | Confirmed defect |
| Confidence | High |
| Evidence | Chat: `teacher_id` ∈ {`ekam`, `preethaji_krishnaji`, `krishnaji`} (root `CLAUDE.md`, 4,337 of 12,904 `ekam`) `[DOC-CLAIM]`. v8: `teacher_id`/`speaker` ∈ {`preethaji`, `krishnaji`} (`backend/scripts/ops/build_first_person_index.py:561-578`). v10: `guru_id`. OKF: `teacher: sri-krishnaji`. Postgres `gurus.slug` "preethaji_krishnaji". Runtime registry `backend/config/gurus.yaml`. [V-STATIC] |
| Actual behaviour | Filters and joins need per-store translation. |
| Expected behaviour | One registry ID set used by every store. |
| Root cause | No registry when the early stores were built. |
| User impact | Teacher filters can miss content. |
| Downstream impact | Blocks clean multi-teacher extension (S4 `11`). |
| Dependencies | S4 GURU findings. |
| Remediation | `gurus.yaml` IDs are canonical. Back-fill `teacher_ids[]` everywhere. Drop the Postgres `gurus` table or sync it from the YAML. |
| Acceptance criteria | Runbook R-6 (`22`): 100% of points carry IDs that exist in `gurus.yaml`. |
| Regression test | Contract test over writers. |
| Implementation risk | Low |
| Verification | [V-STATIC] + [LIVE-Q] |

### DATA-14 — The v10 serving collection fails its own data-quality scorecard
| Field | Value |
|---|---|
| Pillars | P2, P4 |
| Category | Data quality |
| Severity | P1 |
| Type | Confirmed defect (measured by the project) |
| Confidence | High (as reported) |
| Evidence | `audits/evidence/fp_data_quality_scorecard_v10_live_2026-10-25.md`: verdict FAIL, 13/26 checks pass; `strict_clean_rate` 39.90%; `boundary_defect_rate` 24.48%; `duration_out_of_band_rate` 26.42%; `contained_in_other_span_rate` 17.14%; `text_edited_vs_source_rate` 48.92%. [DOC-CLAIM] |
| Actual behaviour | v10 is the owner-chosen serving collection (root `CLAUDE.md` invariant 25), yet it fails 7 gating checks. |
| Expected behaviour | Promotion requires a scorecard pass on the exact collection served. |
| Root cause | Segmentation and boundary quality at source (see `07`). |
| User impact | Fragmentary or mid-thought clips; high abstention. |
| Downstream impact | A ceiling on any retrieval or selection improvement. |
| Dependencies | `07` segmentation redesign. |
| Remediation | Make the scorecard a promotion gate (no `BLOCKER`/`HIGH` fails). Re-segment at source, not with serve-time filters. |
| Acceptance criteria | `strict_clean_rate` ≥ 60% and 0 BLOCKER fails on the promoted collection. |
| Regression test | `make fp-scorecard` in the release pipeline against the export of the candidate collection. |
| Implementation risk | Medium (corpus work) |
| Verification | [DOC-CLAIM] + [LIVE-Q] |

### DATA-15 — No continuous data-quality gate on the serving collections
| Field | Value |
|---|---|
| Pillars | P1, P3 |
| Category | Observability (data) |
| Severity | P2 |
| Type | Confirmed defect |
| Confidence | High |
| Evidence | `scripts/ops/data_quality_audit.py:1-25,288-306` audits `settings.qdrant_collection` (chat), not `first_person_*`. `.github/workflows/nightly-audit.yml` runs unit tests only. The FP scorecard is manual (`Makefile:190`). [V-STATIC] |
| Actual behaviour | Drift in v10 (for example the v11 writer incident) is found only by chance. |
| Expected behaviour | A scheduled read-only audit of the serving collection with alerts. |
| Root cause | The data gate predates first-person. |
| User impact | Indirect. |
| Downstream impact | Release evidence goes stale silently. |
| Dependencies | DATA-06 |
| Remediation | Extend the data gate to the serving collection (checks R-1..R-12 in `22`). Run it daily. Alert on change. |
| Acceptance criteria | A daily report exists. An injected payload change raises an alert within 24 h. |
| Regression test | Unit test of the audit against a local-mode fixture collection. |
| Implementation risk | Low |
| Verification | [V-STATIC] |

### DATA-16 — The approved corpus version is not the served corpus version
| Field | Value |
|---|---|
| Pillars | P4 |
| Category | Version integrity |
| Severity | P2 |
| Type | Probable defect |
| Confidence | Medium |
| Evidence | Serving contract: `first_person_v10.corpus_version = "fp-context-transcript-v1"`; builder `DEFAULT_CORPUS_VERSION = "fp-context-transcript-v1"` (`backend/scripts/ops/build_full_corpus_v10.py:131`). Release evidence: `public_release_phase4_tiers_manifest_2026-10-22.json` `corpus_version = "fp-context-transcript-v2"`; `build_fp_rights_register.py:636,748`; owner packets. [V-STATIC] |
| Actual behaviour | Owner decisions reference a file-based v2 candidate corpus. The served Qdrant collection is declared v1. |
| Expected behaviour | Each release record binds `(collection, corpus_version, bundle digest, scorecard digest, decisions)`. Startup verifies it. |
| Root cause | Evidence pipeline and serving pipeline evolved separately. |
| User impact | Approved quality may not describe what users see. |
| Downstream impact | Guru-review package credibility (S4 `23`). |
| Dependencies | S4 verification of the gate 24/24 claim. |
| Remediation | Add `release_record.json` and a startup check. |
| Acceptance criteria | Startup refuses when the served collection's corpus version differs from the release record. |
| Regression test | Unit test on the serving-contract validator. |
| Implementation risk | Low |
| Verification | [V-STATIC] + [LIVE-Q] |

### DATA-17 — The OKF bundle has compile drift and host-path leakage
| Field | Value |
|---|---|
| Pillars | P3 |
| Category | Data hygiene |
| Severity | P3 |
| Type | Confirmed defect |
| Confidence | High |
| Evidence | `memory/okf/compiled.json`: 429 entries. 721 non-staging `.md` files (676 flat + 31 shared + 2 + 12). Entry `path` values are `/Users/harshodaikolluru/Public/...`. The sample body repeats its H1. 820 staging files are tracked. [V-STATIC] |
| Actual behaviour | Compiled routing data does not match the files. The public repo exposes a local path. |
| Expected behaviour | Repo-relative paths. A compile report explains every excluded file. |
| Root cause | The compiler writes absolute paths and has no exclusion report. |
| User impact | Low (OKF is routing only). |
| Downstream impact | Public-repo exposure of LLM-generated "teaching" text (IP: S4 `14c`). |
| Dependencies | S4 IP decision on the public repo. |
| Remediation | Store relative paths. Emit `compile_report.json`. Move `staging/` out of the public repo. |
| Acceptance criteria | 0 absolute paths. Report counts reconcile. |
| Regression test | `test_okf_compiled_relative_paths`. |
| Implementation risk | Low |
| Verification | [V-STATIC] |

### DATA-18 — Runtime state lives in container files
| Field | Value |
|---|---|
| Pillars | P1 |
| Category | State management |
| Severity | P2 |
| Type | Architectural risk |
| Confidence | High |
| Evidence | Video decisions JSON (`first_person_video_decisions.py:98-104`, `/app/data`); rights register file; allow/block lists; calibration JSON; corpus publication manifests (`config.py:296-300`); LightRAG `data/lightrag`. [V-STATIC] |
| Actual behaviour | Each replica sees its own copy. An admin block on one replica is not seen by another. |
| Expected behaviour | Shared, audited state (Postgres) or immutable, digest-pinned artifacts. |
| Root cause | Single-host development. |
| User impact | Inconsistent serving across replicas after a takedown. |
| Downstream impact | Railway horizontal scale. |
| Dependencies | S1 Railway runbook. |
| Remediation | Move mutable decisions to Postgres with an audit table. Ship immutable artifacts in the image, pinned by digest. |
| Acceptance criteria | A block made through replica A is enforced by replica B within 60 s. |
| Regression test | A two-process test. |
| Implementation risk | Low–Medium |
| Verification | [V-STATIC] |

### DATA-19 — Tracked data backups in a public repository
| Field | Value |
|---|---|
| Pillars | P3, P4 |
| Category | Data hygiene |
| Severity | P3 |
| Type | Confirmed defect |
| Confidence | High |
| Evidence | `data/neo4j_graph_dump.json` (8.0 MB), `data/qdrant_chunk_reclean_backup_*.json`, `data/qdrant_lightrag_*_orphan_backup.json`. [V-STATIC] |
| Actual behaviour | Stale corpus fragments are public. They are not a usable backup. |
| Expected behaviour | Backups in private storage, with retention. |
| Root cause | One-off safety copies committed. |
| User impact | None directly. |
| Downstream impact | IP exposure (S4); security review (S1). |
| Dependencies | Owner decision on repo visibility. |
| Remediation | Remove from the tree. Purging history is an owner decision. |
| Acceptance criteria | `data/` holds no corpus dumps. |
| Regression test | Publication guard rule. |
| Implementation risk | Low |
| Verification | [V-STATIC] |

## 9. Cross-references

- Retrieval, graph and Qdrant: `08-qdrant-graph-retrieval.md`.
- Multi-video and segmentation: `07-video-audio-multisource-synthesis.md`.
- Live checks: `22-qdrant-graph-deferred-validation-runbook.md`.
- Security of Qdrant ports, secrets and the public repo: S1 `14-security-safety-privacy-permissions.md`.
- Railway deployment: S1 `22b-railway-deployment-readiness-runbook.md`.
- Rights and IP: S4 `14c-content-permissions-and-ip-register.md`.
- Memory stores and erasure: S3 `12-personal-mentor-memory-ethical-retention.md`.
