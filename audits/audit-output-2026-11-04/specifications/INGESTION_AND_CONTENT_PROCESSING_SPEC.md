# Ingestion and content processing specification (with knowledge governance)

## 0. Header

| Field | Value |
|---|---|
| Purpose | Give an implementation agent every stage contract, failure rule and governance workflow needed to ingest, correct, withdraw and reprocess teaching content without re-investigating. |
| Status | **partial.** Stages S4 to S12 run offline on the owner's host. Stages S1, S3, S6, S13 (governed), and all of §6 (governance) are missing or decision-blocked. |
| Date / head | 2026-11-05 / `c9b42d3e` on `feature/audit-strengthen-rag-qdrant` |
| Brief parts | 6.1 (ingestion lifecycle), 6.4 and Final Addition B (knowledge governance) |
| Decisions it depends on | D-05 (ADR-005, graph retirement), D-08 (ADR-008, source bundle), D-13 (broadcaster clearance), D-14 (served collection, encoder, approved version), D-15 (Qdrant writers), D-01 and D-10 (rights evidence). ADR-004 and ADR-007 are "Accepted (lead)" in `decision-log.md` §2. |
| Status source | `FINAL_PENDING_WORK_REGISTER.md` (DATA-02, DATA-03, DATA-04, DATA-05, DATA-11 Closed; DATA-06, DATA-14, DATA-15, DATA-16 Partial; DATA-07, DATA-12, DATA-13, DATA-18 Open; DATA-01, DATA-08, DATA-09, DATA-10 need an owner decision). |
| Companions | `DATA_QUALITY_AND_CROSS_STORE_CONSISTENCY_SPEC.md` (stores, lineage, checks); `../FINAL_QDRANT_LIVE_VALIDATION_CHECKLIST.md` (owner-run live checks). |
| Labels | `CONVENTIONS.md` §3. Every path:line below was read in this session at `c9b42d3e`. |

Invariants that bind this spec (root `CLAUDE.md`, first-person section): verbatim-only teacher voice; no LLM text at serve time; on v10 the integrity field is `source_text_hash`; legacy point IDs are `uuid5(FIRST_PERSON_NAMESPACE, f"{transcript_hash}:{start_ms}:{end_ms}")`; a new version is a new collection; the builder refuses an empty build; all text into Qdrant passes `asr_cleaner` and a text change updates the hash fields in the same transaction; embeddings run host-side; OKF is never teacher voice; quotes are never translated.

## 1. Existing coverage and exactly what it lacks

| Existing document | Covers | Lacks (this spec adds) |
|---|---|---|
| `06` §2-§6, DATA-01..19 | Store inventory, two ingestion systems, lineage diagrams, deletion matrix (§6), findings | Stage contracts (input, output, ID, idempotency key, partial-failure detection, resume, reprocess). The source state machine. Correction and withdrawal workflows. The exact deletion mechanism per store. |
| `07` §2 | Processing chain table (acquisition to playback); segmentation against invariants 10 and 11 | Failure behaviour per stage; resume rules; what the builders do when a step fails partway. |
| `21` T3-04, T3-06, T3-09 | File lists and one-paragraph changes | Data model for `transcript_versions`, `takedowns`, `span_index`; step order for a takedown; test names. |
| `17` ADR-005, ADR-007, ADR-008 | Decisions | Operational consequences of each for ingestion. |
| `14c` | Rights facts, IP-001 to IP-004 | How a rights change reaches serving, caches and derived stores. |
| `22` R-14, R-15 | Live deletion and re-ingestion verification queries | The write-side procedure those checks verify. |
| `FINAL_PENDING_WORK_REGISTER.md` | Status of each finding | New defects in landed code (§2.2). |

## 2. Current state (verified at `c9b42d3e`)

### 2.1 Three ingestion entry points [V-STATIC]

| System | Entry | Writes | Evidence |
|---|---|---|---|
| A. Online `IngestionPipeline` | `POST /api/ingest` (admin, AAL2) -> `ingest_url` -> `_ingest_url_impl` | Chat corpus (Qdrant), LightRAG (`ainsert`), Memgraph (`write_ontology_to_neo4j`, default `True`), OKF staging, Postgres `source_releases`, `kb_sources`, `ingest_jobs` | `backend/app/api/ingest.py:93-120`; `backend/ingest/pipeline.py:867`, `:1270`, `:1288`, `:3537`, `:3583`; `backend/app/telemetry_db.py:567` |
| B. Offline first-person builders (host) | `backend/scripts/ops/build_full_corpus_v10.py` (v10 and later), `build_first_person_index.py` (v8 and earlier; dry-run default, `:20`). Both are byte-identical to their `scripts/ops/` copies (`cmp` run). | `first_person_v*` collections | `build_full_corpus_v10.py:1-27` |
| C. Celery first-person task | `ingest_first_person_video_task` | Nothing. It records a FAILED job and raises `FIRST_PERSON_INGESTION_UNAVAILABLE`. | `backend/services/first_person_ingest_service.py:225-271`; `backend/tasks/ingest_tasks.py:509-595`; route `backend/app/api/first_person.py:457-475` |

The two systems share no key (`06` DATA-09, owner decision pending).

Where code and documents disagree (code wins):

1. `06` DATA-04 lists the dual-index writer as open. It is removed: `grep -rn "dual_index" backend --include=*.py` finds nothing outside tests, and the register marks DATA-04 Closed.
2. `07` §1 item 5 says `ingest/verbatim/` is used by the offline builders. The v10 builder imports only `asr_cleaner_flags` (`build_full_corpus_v10.py:87`) plus `boundary_defects` and sentence slicing. It does not call the ROVER vote, `clips.py` or `speaker_verify.py` [V-STATIC, import read]. The orchestrator is not wired into `ingest/pipeline.py` (invariant 7 holds).
3. Invariant 13 says all text passes `asr_cleaner`. In the v10 builder the cleaner only quarantines (`build_full_corpus_v10.py:1022`, comment "never edits"). The legacy store rewrites and re-hashes (`first_person_store.py:430-436`). Both avoid a stale hash. The contracts differ.
4. `06` §5 and DATA-02 say builder and serve time read the same pinned register. The v10 builder does not read it (DATA-21 below).

### 2.2 New defects found in landed code (PROPOSED IDs)

| ID | Defect | Evidence | Severity (proposed) |
|---|---|---|---|
| DATA-20 | The v10 builder never stamps `domain_rights_status`. `SourceSpan` defaults it to `"unverified"`. The builder writes `s.to_payload()` through `QdrantService.upsert_points`. Only `FirstPersonContextStore.upsert` stamps the register status. Retrieval filters on `domain_rights_status == "licensed"`. A fresh build is unservable until another step stamps it. How live v10 became "licensed" is unknown. | `backend/domain/first_person_context.py:204`; `build_full_corpus_v10.py:1232-1245` (the builder never references the field, `grep -n domain_rights_status` returns nothing); `first_person_context_store.py:376-383`, `:464`, `:1332` | P1 for any rebuild or v11 promotion [LIVE-Q] |
| DATA-21 | The builder decides rights from a hard-coded channel set and name substrings (`"preethaji"`, `"krishnaji"`, `"ekam"`), then writes `rights_cleared=True` as a literal. `CLEARED_CHANNELS` includes `"times now"`. The register is not consulted at build time. | `build_full_corpus_v10.py:143-156`, `:975-979`, `:1161` | P1 (conflicts with D-13) |
| DATA-22 | A failed pre-build snapshot is only a warning. The build writes anyway. A failed stale-point delete is only a warning, so stale points can remain. The register marks DATA-05 Closed; these are residual gaps in that closure. | `build_full_corpus_v10.py:957-965`, `:1292` | P2 |
| DATA-23 | Per-video replace is delete-then-upsert. If the upsert fails, the handler deletes the attempted IDs. The old points are already gone, so the video ends with zero points. | `build_full_corpus_v10.py:1262-1325` | P1 for in-place replace; low for a new collection |
| DATA-24 | `audio_archive.py` writes `rights_status: "cleared"` as a literal on `migrate` and on every download. The manifest carries no rights evidence. | `scripts/ops/audio_archive.py:244`, `:306`, `:575` | P2 |
| DATA-25 | No writer emits `fp-context-v2`. The builder sets `span_text_sha256` and `video_transcript_sha256` (`:1150-1152`) but leaves `schema_version` at the v1 default. The serving contract declares no v2 collection. The register marks DATA-03 Closed for the schema and tests only. | `first_person_context.py:30-31`, `:174`; `grep -rn "fp-context-v2" backend scripts` outside tests returns only `domain/` | P2 |
| DATA-26 | Startup passes no `active_collection_digest`. The contract JSON sets no `collection_digest` or `approved_corpus_version` (read with `python3`). The digest and version checks are inert at boot. The nightly "continuous audit" step runs `pytest` on fixtures only and never contacts Qdrant. This is why the register shows DATA-15 and DATA-16 as Partial. | `backend/app/main.py:860-872`; `first_person_serving_contract.py:411-440`; `.github/workflows/nightly-audit.yml:43-46` | P2 |
| DATA-27 | Digest identity differs by caller. The audit script keys each point by `payload["point_id"]` or `source_span_id`. The contract helper hashes whatever `id` it receives. | `scripts/ops/data_quality_audit.py:251-258`; `first_person_serving_contract.py:383-408` | P2 [INF] |

Treat DATA-20 to DATA-27 as PROPOSED until the lead merges them into `findings-index.md`.

### 2.3 Facts the stage design relies on [V-STATIC]

| Fact | Evidence |
|---|---|
| Audio archive: atomic manifest write (`os.replace`), SHA-256 per WAV, `get_path` returns only `status == "archived"`. The script exists only under `scripts/ops/`. | `scripts/ops/audio_archive.py:199-222`, `:339-423`, `:425-430` |
| Transcript parse: the body hash is recomputed. A mismatching header hash is replaced by the computed one. The `transcripts/` directory is untracked (`git ls-files transcripts` returns 0). | `build_full_corpus_v10.py:348-388` |
| Word timings are never synthesised. A video without alignment is quarantined `no_word_timings`. | `build_full_corpus_v10.py:9-12` |
| The builder refuses an empty candidate list, and refuses a live target without `--allow-live-target`. | `build_full_corpus_v10.py:924` (empty), `:853-860` (live target) |
| `--replace-existing` rebuilds videos already present and deletes that video's points first. | `build_full_corpus_v10.py:777-782`, `:899-900`, `:1262-1295` |
| Speaker provenance is asserted before every write. | `build_full_corpus_v10.py:1241`; `first_person_context_store.py:173-252` |
| Legacy write path: re-clean, re-hash, validate, recompute the point ID, read back. | `first_person_store.py:381-600` |
| `canonical_video_id` maps one re-upload pair only. | `first_person_store.py:99-103` |
| Takedown today is a JSON block per video (`admin_approved is False` or `human_speaker_check == "rejected"`), read by serving and by exact-cache revalidation. | `first_person_video_decisions.py:71-95`, `:348-390`; `admin_video_review.py:222-223` |
| The FP exact cache key holds the collection name and a policy fingerprint, not a content version. A hit revalidates cited points. On the context store the check compares text, hashes, coordinates and provenance to the current payload. On the legacy store it checks eligibility flags only. | `first_person_pipeline.py:3085-3119`, `:3122-3155`; `first_person_context_store.py:1283-1349`; `first_person_store.py:601-636` |
| Rights register: file `audits/evidence/public_release_phase4_rights_manifest_2026-10-22.json`, copied into the Railway image; production startup refuses a missing or empty register; health shows count and digest prefix. No digest pin is compared. | `backend/Dockerfile.railway:90-92`; `backend/app/main.py:786-798`; `backend/app/api/health.py:228-235`; `first_person_serving_contract.py:188-227` |
| Register status counts: `confirmed_channel_owner` 702, `missing_evidence` 46, `confirmed_video_owner` 2, `pending_owner_review` 1. Asset fields include `evidence_sha256`, `permission_basis`, `review_date`, `permitted_use`. | the register JSON, read with `python3` |
| Postgres has `corpus_sources` (PK `source_identity`, `status` default `'active'`), `source_releases` (versioned, one active per source, approval-audit constraint), `ingest_jobs` (heartbeat, attempt, `source_identity`), `ingestion_checkpoints`. | `supabase/migrations/20261028000002_corpus_sources.sql:10-20`; `20260805000003_source_releases.sql:2-34`; `20261028000000_ingest_jobs_lifecycle.sql:14-22` |
| The online pipeline has no rights check: `grep -n rights backend/ingest/pipeline.py` returns nothing. | `backend/ingest/pipeline.py` |
| After an online ingest, three answer caches are cleared (exact, doctrine, hot). `cache:first_person_exact:*` is not cleared there. It is revalidated per hit. | `backend/ingest/pipeline.py:3583-3620` |

## 3. Target contracts

### 3.1 Identifier chain (one ID per hop)

| Hop | ID | Rule | Store |
|---|---|---|---|
| Source | `source_id` = canonical YouTube `video_id` | One row per recording. Re-uploads map through `source_aliases`. | Postgres `corpus_sources` (extend) |
| Audio | `audio_sha256` | SHA-256 of the archived WAV | Audio manifest; registry column |
| Transcript | `transcript_version_id` = `{source_id}:{video_transcript_sha256[:16]}` | New text or new alignment = new version | Postgres `transcript_versions` (new) |
| Span (v10 and later) | `source_span_id` = `sha256(guru_id|video_id|corpus_version|word_start|word_end|transcript hash)` | Unchanged (`first_person_context.py:137-150`) | Qdrant payload; Postgres `span_index` (derived) |
| Point (v10 and later) | `uuid5(_POINT_NAMESPACE, source_span_id)` | `first_person_context_store.py:250-256` | Qdrant |
| Point (legacy) | `uuid5(FIRST_PERSON_NAMESPACE, f"{transcript_hash}:{start_ms}:{end_ms}")` | Invariant 4. `transcript_hash` is the clip hash here. | Qdrant |
| Answer citation | `{message_id, collection, corpus_version, point_id, source_span_id, video_id, start_ms, end_ms, span_text_sha256}` | DATA-12 | Postgres `message_citations` (new, T3-06) |

Do not change any ID formula. A change is a new collection.

### 3.2 Source state machine (new, in `corpus_sources`)

```
registered -> acquired -> transcribed -> attributed -> built(candidate) -> approved -> active
any state  -> held | withdrawn
active     -> superseded   (a newer transcript_version becomes active)
withdrawn  -> terminal      (reinstatement is a new registration with a new approval)
```

| State | Entry condition | Evidence stored |
|---|---|---|
| `registered` | Row has `source_id`, `canonical_url`, `rights_entry_id` (reference to a register asset). `rights_entry_id` may be null only in `held`. | Row + audit row |
| `acquired` | WAV exists, `audio_sha256` recorded, `rights_status` copied from the register (fixes DATA-24) | Manifest + registry |
| `transcribed` | A `transcript_versions` row exists with `video_transcript_sha256`, ASR engine and revision, timing-artifact hash | Row |
| `attributed` | Per-span speaker verdicts exist with a calibration ID | Verdict file hash |
| `built(candidate)` | Spans sit in a new candidate collection | Collection name, counts, digest |
| `approved` | Promotion gate passed and a named human approved | `approved_by`, `approved_at`, gate report hash |
| `active` | The serving contract names the collection and `approved_corpus_version` | Contract diff |
| `held`, `withdrawn` | Takedown or rights change (§6) | `takedowns` row |

### 3.3 New tables (after T3-08 per `20` §5)

| Table | Key columns | Constraints |
|---|---|---|
| `corpus_sources` (extend) | `source_id` text PK (reuse `source_identity`), `canonical_url`, `rights_entry_id`, `audio_sha256`, `lifecycle_state`, `lifecycle_updated_at` | CHECK `lifecycle_state` in the §3.2 set |
| `source_aliases` | `alias_video_id` PK, `canonical_source_id` FK | No self-reference |
| `transcript_versions` | `transcript_version_id` PK, `source_id` FK, `video_transcript_sha256`, `asr_engine`, `asr_revision`, `timing_artifact_sha256`, `supersedes_id` FK null, `status` (`candidate`, `active`, `superseded`, `withdrawn`), `created_by`, `created_at` | UNIQUE (`source_id`, `video_transcript_sha256`); partial UNIQUE (`source_id`) WHERE `status = 'active'` |
| `span_index` | `source_span_id` PK, `source_id`, `transcript_version_id`, `collection`, `point_id`, `span_text_sha256`, `state` | Derived. Rebuilt from Qdrant by the reconcile job. Never a source of text. |
| `takedowns` | `takedown_id` PK, `source_id`, `scope` (`video`, `span`, `channel`), `reason_code`, `requested_by`, `approved_by`, `status`, `report_json`, timestamps | `report_json` holds per-store counts |
| `content_audit_log` | `id`, `actor`, `action`, `source_id`, `before_hash`, `after_hash`, `at` | Append-only (revoke UPDATE and DELETE from `service_role`) |

Teacher text never enters these tables. They hold IDs and hashes only (public-repo rule, `14c` IP-001).

### 3.4 Files to create or change

| Path | Change | Task |
|---|---|---|
| `supabase/migrations/<ts>_source_registry.sql` | Tables in §3.3, RLS service-role only, REVERT block. The owner approves migration text (register §"T3-06"). | T3-06 |
| `backend/services/source_registry/` (`registry.py`, `takedown.py`, `deleters/{qdrant,redis,okf,graph,citations}.py`) | Registry API, one deleter per store | T3-06 |
| `backend/services/first_person_video_decisions.py` | Read decisions from Postgres; keep JSON as fallback until verified | T3-06 |
| `backend/scripts/ops/build_full_corpus_v10.py` and `scripts/ops/build_full_corpus_v10.py` | Fix DATA-20 to DATA-23; keep both copies byte-identical (`tests/test_repo_layout.py`) | NEW-ING-1, NEW-ING-2 |
| `scripts/ops/audio_archive.py` | Take `rights_status` from the register | NEW-ING-3 |
| `backend/config/first_person_serving_contract.json`, `backend/app/main.py` | Populate `collection_digest` and `approved_corpus_version`; pass `active_collection_digest` at boot | NEW-ING-4 |
| `.github/workflows/nightly-audit.yml` | Add an opt-in live audit job that runs only where a read-only Qdrant secret exists | NEW-ING-5 |

## 4. Behaviour per stage

**Idem.** = idempotency key. **Status**: Impl, Part (partial), Miss (missing). "Target" means the rule to implement. "Today" means verified current behaviour.

| # | Stage | Input -> output | ID produced; where stored | Idem. | Failure behaviour | Partial detection | Resume | Status |
|---|---|---|---|---|---|---|---|---|
| S1 | Source registration | URL + register entry -> `corpus_sources` row | `source_id`; Postgres | `source_id` | Target: reject a URL that does not parse to one `video_id`; hold a source with no register entry. Today: no registry. Online `_derive_source_identity` is at `pipeline.py:711-725`. | Row stuck in `registered` | Re-run is a no-op | Miss |
| S2 | Source acquisition | `source_id` -> WAV | WAV file + manifest entry; host disk | `source_id`; manifest `status` | Retry with backoff. Set `unavailable` or `age_restricted` (exists, `audio_archive.py:650-692`). Target: do not download unless the register entry is cleared. Today: no gate (IP-004). | Manifest `pending_download`; `verify()` size or SHA mismatch (`:339-423`) | `download_pending` skips `archived` (`:476-480`) | Part |
| S3 | Raw storage | WAV -> bundle | `audio_sha256`; ADR-008 bundle | `audio_sha256` | Target: verify SHA after copy, abort on mismatch. Today: host disk only (DATA-01). | `verify()` fails | Re-copy from the archive | Miss (D-08) |
| S4 | Transcript extraction | WAV -> transcript markdown + word timings | `video_transcript_sha256`; host `transcripts/` (untracked) | `video_transcript_sha256` | Missing alignment: quarantine `no_word_timings`, never synthesise. Header-hash mismatch: use the computed hash and log (`:376-388`). | Quarantine counter | Re-run ASR for that video only | Impl (host) |
| S5 | Speaker identification | WAV slice per span -> verdict | Per-span method, score, calibration ID; Qdrant payload | `source_span_id` + calibration ID | A failing span stays `speaker_verified=False` (`pending_voice_check`). A guru mismatch skips the video (`:1064-1070`). | `assert_speaker_provenance` before write (`:1241`) | Re-run verdicts; keyed to the span hash | Impl (host) |
| S6 | Language identification | Span text -> `language` | `SourceSpan.language` (`first_person_context.py:245-249`) | Span hash | Target: a span with unknown language is not servable in the English lane. Today: the builder sets no language (`grep -in language build_full_corpus_v10.py` returns nothing). | Count of null `language` | Backfill into a new collection | Miss |
| S7 | Normalisation and cleaning | Words -> spans; `asr_cleaner_flags` | Flags; quarantine counters | Span hash | v10: a flagged span is dropped and counted `asr_cleaner_<flag>` (`:1022-1030`). Legacy: rewrite and re-hash in one step. Never change text without changing the hashes in the same write. | Quarantine counters | Re-run | Impl |
| S8 | Chunking and clip boundaries | Words + timings -> sentence spans | `word_start`, `word_end`, `start_ms`, `end_ms` | Span ID | `boundary_defects()` sets `UNCERTAIN` and `FRAGMENT` (`:1127`). Invariant 10: no head conjunction without forward resolution. Invariant 11: 18 to 25 s target. Today: v10 `boundary_defect_rate` 24.48%, median clip 38 s `[DOC-CLAIM]` (`06` §7, `07` §2.1). | Scorecard `boundary_defect_rate` | New candidate collection | Part |
| S9 | Metadata enrichment | Span -> tags, topics, parent unit | `parent_unit_id` | Parent ID | Tagging is derived data. It may not change text, speaker fields or any hash. A tagging writer must not touch speaker fields (v11 incident, `06` DATA-06). | Digest of protected fields (data spec §5) | Re-tag into a candidate | Part |
| S10 | Quality validation | Candidate -> gate report | Report hash | Collection name | Two-tier gates (invariant 14). Release-grade defects are reported, not dropped. Promotion gate: 0 BLOCKER, 0 HIGH, strict-clean at or above 0.60 (`fp_data_quality_scorecard.py:947-973`). | Gate report | Re-run | Impl (manual) |
| S11 | Embedding | `instruction + text` -> dense 1024 + sparse | Vectors; `embedding_model`, `embedding_revision` (`:1172-1173`) | Span ID | Host-side only (invariant 18). Dimension mismatch aborts (`first_person_store.py:569-575`). | Null `embedding_revision` count | Re-embed missing | Impl (host) |
| S12 | Vector indexing | Points -> new collection | Point ID; Qdrant | Point ID (upsert) | Refuse an empty build. Target: abort if the snapshot fails (DATA-22); stamp rights from the register (DATA-20); upsert first, delete stale second (DATA-23). | Per-video expected-ID list vs scrolled IDs | Re-run `--only-videos` into the same candidate | Part |
| S13 | Graph update | n/a | n/a | n/a | Today: active by default. `write_ontology_to_neo4j` defaults to `True` (`pipeline.py:1288`, `:1576`, `:1922`); LightRAG `ainsert` runs when instantiated (`:1270`). ADR-005 retires it (D-05). Compliant now: a default-off flag that skips both writes, with tests for both flag states (T3-11). Decision-gated: removal from the deploy stack. | n/a | n/a | Part |
| S14 | Publication and promotion | Candidate -> serving | Serving contract entry; `(collection, corpus_version, digest)` | Same triple | Promotion needs: gate pass, digest recorded, owner approval, contract diff. Rollback = point the contract back (invariant 4). Today: fields exist, unpopulated (DATA-26). | Boot-time digest mismatch | Re-point the contract | Part |

### 4.1 Resume and partial-failure rules (every builder run)

1. Write only to a candidate collection that does not serve traffic.
2. Take a snapshot first. If the snapshot call fails, stop (DATA-22).
3. Keep a per-run manifest `build_manifest_<run_id>.json` on the host, not tracked. Per video it holds the expected point-ID list and a status: `planned`, `written`, `verified`, `failed`.
4. After each video write, scroll by `video_id` and compare to the expected list. A difference marks the video `failed`.
5. A rerun with `--only-videos` processes `planned` and `failed` videos only.
6. Do not treat "video present in the collection" as "video done". That was the root cause of DATA-05 (the `--only-videos` help still says it skips present videos, `:702-704`). Use `verified`.
7. At the end, compute the collection digest and write it into the run manifest. Use one identity basis: the Qdrant point UUID plus `span_text_sha256` (DATA-27).

### 4.2 Reprocess per stage, without duplicate knowledge

| Stage | Reprocess rule | Why no duplicate appears |
|---|---|---|
| S2, S3 | Re-download only if `verify()` fails. A new WAV has a new `audio_sha256`. | Manifest keys by `video_id` |
| S4 | A new transcript gets a new `video_transcript_sha256` and a new `transcript_versions` row. | Version row is unique per source and hash |
| S5 | New verdicts update the span record in the candidate only. | Verdicts key to the span hash |
| S7 to S9 | Re-run in a candidate collection. | Span ID is deterministic |
| S11 | Re-embed in a candidate. Same text, same revision, same vectors. | Point ID is deterministic |
| S12 | Compliant: build a new collection. The new transcript hash is part of the v10 span ID, so old and new IDs cannot collide. | New collection; the old one stays for rollback |
| S14 | Re-point the contract. | One active version per source (partial UNIQUE) |

Compliant variant (buildable now): build a new candidate collection (for example `first_person_v11`). The builder refuses a live target without `--allow-live-target` (`:853-860`). Run the gate and digest, then promote by contract change.

Decision-gated variant (not decided): `--replace-existing` against a serving collection. It conflicts with "a new version is a new collection". If the owner approves (PROPOSED D-PI1), fix DATA-22 and DATA-23 first, then require `--allow-live-target`, a snapshot and the post-write per-video diff.

Legacy v8: `build_first_person_index.py` diffs existing and produced IDs, deletes stale ones, refuses an empty build, and skips deletion on a subset build (`:677-783`). Keep that behaviour.

Duplicate check after any rebuild: `count(video_id == X)` equals the expected list length; exactly one `transcript_version` is `active` for `X`; no second `source_url` form exists for `X` in the chat corpus.

## 5. Deterministic versus model steps

| Step | Kind | Owner of model or prompt | Rule |
|---|---|---|---|
| ASR | Model (Whisper, host) | `services/speech_config.py` (sacred-vocabulary prompt) | Pin the revision. Store `asr_engine` and `asr_model_version` on the span. |
| Speaker verification | Model (ECAPA, host) | Calibrated floors, `calibration_v2` | Never infer from words in the text. |
| Cleaning, boundaries, gates, hashing, IDs, rights lookup | Deterministic | n/a | Must reproduce bit for bit. |
| Embedding | Model (BGE-M3, host) | `settings.embedding_model` and revision | Record the revision on the payload. |
| Tags, topics, parent labels | May use an LLM offline | Offline review gate before any Qdrant write (invariant 1) | Output cannot alter text, speaker or hash fields. |
| OKF extraction | LLM | `scripts/extract_okf_from_stores.py` | Output goes to `memory/okf/staging/`. It never serves until a human moves it (`okf_store.py:206-208`). |
| Selection at serve time | LLM selector only | First-person pipeline | Returns indices. Never writes teaching text (invariant 15). |

## 6. Knowledge governance (Final Addition B)

| Capability | Today | Target | Status |
|---|---|---|---|
| Authoritative source registration | Split across audio manifest, rights JSON, `corpus_sources` (chat path only) | `corpus_sources` is the authority (ADR-007) | Miss |
| Permissions via rights register | Register keyed by `video_id`; serve-time fail closed (`first_person_rights.py:6-26`) | Source row holds `rights_entry_id`; builder reads the register (DATA-21) | Part |
| Provenance | v10 payload carries video, timing, ASR, speaker method | Add `transcript_version_id` and `audio_sha256` on candidate payloads | Part |
| Version history | `corpus_version` in IDs; `source_releases` (chat path) | `transcript_versions` with `supersedes_id` | Part |
| Transcript correction | None. The builder skips present videos unless `--replace-existing`. | §6.1 | Miss |
| Translation correction | Quotes are never translated. A gloss is optional and not in the index. | Keep glosses outside Qdrant, labelled "translation, not the teacher's words". A correction edits the gloss store only. | Miss (low risk) |
| Duplicate source resolution | One re-upload pair (`first_person_store.py:99-103`); chat IDs use the raw URL (DATA-10) | `source_aliases`; canonicalise at every write boundary | Miss |
| Content withdrawal | Video block JSON, serve-time only | `takedown()` (§6.2) | Part |
| Deletion propagation | None beyond the block | §6.2 | Miss |
| Approval workflow | `source_releases` states with an approval-audit constraint (chat path); owner decision files for FP | Reuse the same state set for `transcript_versions` and promotion | Part |
| Audit trail | `VideoDecisionStore` audit log; `ingest_jobs` | `content_audit_log` (append-only) | Part |
| Reprocessing | §4.2 | Same | Part |

### 6.1 Transcript or attribution correction, end to end

Goal: after a correction, no stale text is servable in any store. Each step names its proof.

| Step | Action | Proof |
|---|---|---|
| 1 | A reviewer files a correction: `source_id`, span range or "speaker", reason code, evidence hash. Insert a `content_audit_log` row. | Row exists |
| 2 | Contain first. Set the video decision to `admin_approved=False`, reason "correction in progress" (`PUT /{video_id}`, `admin_video_review.py:222`). This stops serving and fails every cached replay on the next hit (`first_person_pipeline.py:3122-3155`). | `video_is_blocked(video_id)` is true; a cached replay misses |
| 3 | Create a `transcript_versions` row (`candidate`) with the corrected hash. | Row exists |
| 4 | Rebuild the video into a new candidate collection (§4.2). The corrected text has a new `source_text_hash` and `span_text_sha256`. | Expected-ID list equals scrolled IDs |
| 5 | Run the gate. Compare old and new span sets. An attribution change must show a new `voice_verification_method` evidence record. | Gate report hash |
| 6 | Promote: contract points at the new collection; the old `transcript_versions` row becomes `superseded`; digest recorded. | Boot check passes |
| 7 | Purge derived copies (§6.2 rows 3 to 9). | Zero hits per store |
| 8 | Lift the containment block after steps 6 and 7 pass. | Decision file shows `admin_approved=None` |

Why step 2 comes first: an in-place payload edit is not allowed (a new version is a new collection), and the legacy `points_servable` does not compare text (`first_person_store.py:601-636`). Only the block closes the gap during the rebuild. NEW-ING-6 closes the legacy gap.

### 6.2 Withdrawal and deletion propagation

`takedown(source_id, scope, reason)` runs these deleters in order. Each returns a count. The counts go into `takedowns.report_json`. A store that cannot be cleared marks the takedown `partial` and alerts.

| Order | Store | Mechanism | Idempotent | Today |
|---|---|---|---|---|
| 1 | Video decision | `admin_approved=False` (stops serving at once) | Yes | Exists (JSON) |
| 2 | Redis `cache:first_person_exact:*` | Correct without action (revalidated per hit). Optional `SCAN` delete for hygiene. | Yes | Relies on revalidation |
| 3 | Redis chat, hot and doctrine caches | `exact_cache.invalidate_all`, `doctrine_cache.refresh`, `hot_cache.clear` (`pipeline.py:3583-3620`) | Yes | Called only after ingest |
| 4 | Qdrant serving collections | `delete(filter video_id == X)` on every collection that holds `X`, rollback collections included (list from `get_collections`) | Yes | Missing |
| 5 | Qdrant chat corpus | `delete_by_source` for every URL form (`services/qdrant/indexer.py:735`) plus a `video_id` filter | Yes | Chat only |
| 6 | Qdrant `lightrag_vdb_*`, Memgraph | Frozen by ADR-005. Until retired: filter by `source_doc_id` where it exists. Otherwise record "no provenance, cannot delete" (`06` DATA-08). | Partial | Missing |
| 7 | OKF | Remove or move entries whose `source` matches. Recompile. OKF is routing only (invariant 12) but can carry excerpts (`14c` §3). | Yes | Missing |
| 8 | Postgres citations | Mark `message_citations` rows `withdrawn`. `chat_messages.citations` is `text[]` today (DATA-12), and the answer body may hold the quote. Body redaction is PROPOSED D-PI2. | Yes | Missing |
| 9 | Canonical memory | Memory holds user statements, not clips (`canonical_memory/extractor.py:214`). A grep for `verbatim_text`, `source_span_id`, `point_id` in `services/canonical_memory` and `services/memory` finds no file. No deletion is needed until a feature stores clip references. | n/a | Not applicable |
| 10 | Host archive and bundle | Delete or quarantine WAV and transcript per rights terms | Manual | Missing |
| 11 | Verification | Live checklist V-14 | Yes | Manual |

Rollback collections do not escape withdrawal. Delete the video from them, or mark the collection non-servable in the contract.

### 6.3 Approval workflow

| Gate | Who | Evidence |
|---|---|---|
| Register entry cleared | Owner or content owner [HUMAN] | Filed approval hash (IP-003) |
| Promotion | Owner [HUMAN] | Gate report hash, digest, contract diff |
| Takedown | Owner, with the rights-holder request on file | `takedowns` row |
| Correction | Reviewer + owner | Audit log |

Agents prepare evidence and stop. They never approve.

## 7. Observability

Reuse existing names from `backend/app/metrics.py` (verified by grep): `FP_FAIL_CLOSED_TOTAL` (`:55`), `INGEST_QUALITY_GATE_REJECTIONS_TOTAL` (`:659`), `CORPUS_GATE_REJECTIONS_PERSISTED_TOTAL` (`:665`), `CORPUS_GATE_REJECTIONS_PERSIST_FAILED_TOTAL` (`:670`), `CORPUS_ORPHAN_POINTS_TOTAL` (`:675`), `CORPUS_DRIFT_POINTS_TOTAL` (`:680`), `CORPUS_LINEAGE_COMPLETENESS_RATIO` (`:726`), `FIRST_PERSON_QUARANTINED_TOTAL` (`:787`). Host builders export no Prometheus metrics. Their output is the quarantine log and the run manifest.

Proposed new names, added only with the code that sets them: `corpus_takedown_total{status}`, `corpus_takedown_store_failures_total{store}`, `corpus_source_state{state}`, `corpus_build_video_failed_total`.

Alerts (after DATA-26 wiring): digest mismatch at boot; `corpus_takedown_store_failures_total > 0`; any increase of `corpus_orphan_points_total`.

## 8. Acceptance criteria

Type: S = static on fixtures (CI); L = needs the owner's Qdrant; H = needs a human.

| # | Criterion | Test (file::case) | Pass / fail | Type |
|---|---|---|---|---|
| ING-A1 | Builder stamps `domain_rights_status` from the register | NEW `backend/tests/test_builder_rights_stamp.py::test_builder_payload_rights_from_register` | Cleared fixture video gives `licensed`; uncleared gives `unverified` and is skipped | S |
| ING-A2 | Builder ignores channel-name substrings | same file::`test_builder_rejects_uncleared_channel_named_ekam` | A fixture channel "ekam fan channel" absent from the register is skipped | S |
| ING-A3 | Snapshot failure aborts | add `test_builder_replace_and_snapshot.py::test_snapshot_failure_aborts_build` (new) (existing cases `:25`, `:62`, `:163`) | Non-zero exit; zero upserts | S |
| ING-A4 | A failed upsert keeps old points | `::test_failed_upsert_keeps_old_points` | Old IDs still present | S |
| ING-A5 | Builder emits `fp-context-v2` for a v2 target and the contract declares it | add `test_writer_hash_contract.py::test_builder_emits_v2` (new) | Payload validates as v2 | S |
| ING-A6 | Boot fails in production on a digest mismatch through the real startup path | add case beside `test_qdrant_write_governance.py::test_serving_contract_digest_mismatch_fails_startup_in_production` (`:157`) | Startup raises | S |
| ING-A7 | One digest identity for builder, audit and boot | NEW `::test_digest_identity_consistent` | Same digest from all three on one fixture | S |
| ING-A8 | `takedown()` clears every fixture store | NEW `backend/tests/test_takedown_fixture.py::test_takedown_clears_all_stores` (local-mode Qdrant, fake Redis) | Zero counts in every collection and cache | S |
| ING-A9 | A failing deleter ends `partial` and alerts | `::test_takedown_partial_on_store_failure` | Status `partial`; metric incremented | S |
| ING-A10 | After a text correction, a cached answer misses | `::test_cached_answer_misses_after_text_correction` | Replay misses on the context store | S |
| ING-A11 | Legacy `points_servable` rejects changed text | NEW `test_first_person_store_servable.py::test_legacy_points_servable_rejects_changed_text` | Returns False | S |
| ING-A12 | Online ingest refuses a source with no cleared register entry | NEW `test_ingestion_rights_gate.py::test_ingest_url_refuses_unregistered_source` | Status not `success`; zero upserts | S |
| ING-A13 | Online graph writes sit behind a default-off flag | `test_graph_writes_flag.py::test_no_graph_write_when_flag_off` (new), `::test_graph_write_when_flag_on` | Both states pass | S |
| ING-A14 | Live digest equals the signed digest | Checklist V-9, V-16 | Equal | L |
| ING-A15 | Pilot takedown on a scratch restore leaves zero hits per store | Checklist V-14 | 0 | L |
| ING-A16 | Rights evidence filed per served channel | Owner decision blocks | Hash present | H |

## 9. Implementation tasks (PR-sized, ordered)

| Order | Task | Depends on | Non-goals | Rollback |
|---|---|---|---|---|
| 1 | NEW-ING-1: builder takes rights from the register and stamps `domain_rights_status` (DATA-20, DATA-21) | none | No change to any rights status | Revert (host-side script) |
| 2 | NEW-ING-2: snapshot-abort, upsert-then-delete, per-run manifest (DATA-22, DATA-23) | 1 | No in-place replace by default | Revert |
| 3 | NEW-ING-3: audio archive reads rights from the register (DATA-24) | 1 | No re-download | Revert |
| 4 | NEW-ING-4: populate contract digest and approved version; pass the digest at boot; one digest identity (DATA-26, DATA-27) | 2; D-14 | No extra Qdrant call at boot unless a default-off flag is set | Flag off |
| 5 | T3-06a: migration for §3.3 | T3-08 (merged) | No text backfill | Forward-fix (repo rule: no down migration) |
| 6 | T3-06b: `source_registry`, deleters, `takedown()`, video decisions to Postgres | 5 | No UI | Flag `SOURCE_REGISTRY_ENABLED` default off |
| 7 | NEW-ING-6: legacy `points_servable` compares text and hash (ING-A11) | none | No schema change | Revert |
| 8 | NEW-ING-7: online rights gate and alias canonicalisation (DATA-10) | 5 | No change to chat IDs without a new collection | Flag off |
| 9 | T3-11: flag-off graph writes; OKF compile report | flag now; D-05 for removal | No deletion of Memgraph data | Flag on |
| 10 | NEW-ING-8: emit `fp-context-v2` into a new candidate; declare it in the contract (DATA-25) | 1, 2, 4 | No rewrite of v8 or v10 | Point the contract back |
| 11 | T3-09: source bundle | D-08 | None until the owner answers | n/a |
| 12 | NEW-ING-5: opt-in live audit workflow | 4 | Never default on | Delete the workflow |

`backend/ingest/pipeline.py` order from `20` §5: T1-02 (landed), then T3-11, then T3-09.

## 10. Open questions

| ID | Question | Link |
|---|---|---|
| D-05, D-08, D-13, D-14, D-15 | As in `unresolved-questions.md` §1 | existing |
| PROPOSED D-PI1 | May `--replace-existing` run on a serving collection, or does every correction need a new collection? Recommendation: new collection only. | new |
| PROPOSED D-PI2 | After a takedown, redact the quoted text in stored assistant messages, or only flag the citation? | new |
| PROPOSED D-PI3 | Does "every Qdrant collection" for withdrawal include all legacy `first_person_v*` rollbacks? | new |
| PROPOSED D-PI4 | How did live v10 obtain `domain_rights_status = "licensed"` (DATA-20)? Needs the owner's build log. | new [LIVE-L] |

## 11. Verified, assumptions, unknowns

**Verified** [V-STATIC at `c9b42d3e`]: §2.1 and §2.3 facts; DATA-20 to DATA-27 as code behaviour; the T3-01, T3-02, T3-03, T3-04 and T3-05 code and tests exist; startup passes no digest.

**Assumptions** [INF]: the owner builds on a host that holds a `transcripts/` directory; a separate stamping step made live v10 "licensed"; DATA-27 matters only if a signed digest was produced by the other identity basis.

**Unknowns** [LIVE-Q, LIVE-L, HUMAN]: live collection contents and their rights stamping; whether any `collection_digest` was ever recorded; whether the rights holder permits storing audio in a bundle (D-08); legal sufficiency of channel-level register entries (S4 `14c`).
