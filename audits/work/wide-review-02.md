# Ingestion and Data Quality Review — First-Person System

**Scope:** source discovery through transcription, normalization, speaker attribution, segmentation, provenance, rights, indexing, retries, backfills, deletion, and validation.

## Executive finding

The repository has a meaningful fail-closed indexing design, deterministic point IDs, per-video checkpointing, ASR agreement, speaker verification modules, hash checks, rights metadata, and quality reports. The main weakness is that these protections are split across several scripts and stages rather than enforced by one canonical, typed ingestion state machine. This is acceptable for controlled pilot work but unsafe for onboarding additional gurus without code changes and stronger policy boundaries.

## Evidence and actual guarantees

### Source discovery and fetch

- `backend/ingest/sources/youtube_service.py`, `backend/ingest/youtube_loader.py`, `backend/ingest/video_pipeline.py`, and `backend/ingestion/web_ingest_pipeline.py` implement source acquisition paths.
- `backend/scripts/ops/build_first_person_index.py:lookup_channel_metadata()` uses `yt-dlp --skip-download` and degrades metadata failures to `UNKNOWN`/unknown duration. That is correctly fail-closed for rights and bounds, but metadata failure is not a durable source-state transition.
- `scripts/ingestion/all_videos_corpus_status.csv`, `scripts/ingestion/all_ingest_urls.txt`, and `scripts/ingestion/corpus/` hold large operational data outside a single canonical registry. `docs/agent/STATE_RECONCILIATION_2026-09-27.md` explicitly records that one inventory-generating script is missing and that multiple inventories use different definitions.

**Gap:** discovery, fetch, and source identity are not represented by one immutable manifest with URL, platform ID, channel ID, rights decision, fetch timestamp, content hash, and policy version.

### ASR, voting, and normalization

- `backend/ingest/verbatim/pipeline.py` orchestrates vote → ASR agreement check → speaker verification → clips → punctuation.
- `backend/ingest/verbatim/vote.py`, `backend/ingest/audio_transcriber.py`, `backend/services/whisper_local_service.py`, and `backend/ingest/verbatim/punctuation.py` provide the transcription pieces.
- `backend/ingest/verbatim/pipeline.py` records `asr_agreement_gate_reason`, but its own documentation says the gate is “recorded, not a hard stop”; the later `backend/scripts/ops/build_first_person_index.py` applies the hard video quarantine.

**Gap:** an intermediate pipeline output can report `ok: true` while carrying a low-agreement reason. A downstream caller can accidentally treat it as publishable. The canonical result should be a typed state such as `quarantined(asr_agreement_low)` that cannot be passed to indexing without an explicit override record.

### Speaker attribution

- `backend/ingest/verbatim/speaker_verify.py` provides injectable ECAPA embedding, clustering, teacher/host/unknown labels, and fail-closed exception handling.
- `backend/scripts/ops/speaker_attribution.py` contains the heavier voiceprint workflow.
- `backend/scripts/ops/build_voice_profiles.py` builds profiles, but the reconciliation notes say production ingestion has not yet proven that `speaker_verified=True` is produced end to end.
- `backend/scripts/ops/build_first_person_index.py` ultimately trusts clip `speaker` values in the passages input and maps only `preethaji`/`krishnaji` to display labels.

**Gap:** title/channel labels and speaker verification are not the same contract. Every indexed clip needs a `speaker_verification_id`, model/version, score, coverage, threshold, and quarantine/reviewer status.

### Segmentation and transcript integrity

- `backend/ingest/verbatim/clips.py`, `backend/ingest/chunkers/youtube_chunker.py`, `backend/services/speaker_diarization.py`, and `backend/scripts/ops/build_first_person_index.py` implement turn-aware and sentence-aware clipping.
- `backend/scripts/ops/build_first_person_index.py:_gate_clip()` checks substring, SHA-256 hash, bounds, and dangling conjunctions.
- `backend/services/first_person_pipeline.py:_passes_integrity_gate()` repeats hash, speaker allowlist, artifact, and dangling-conjunction checks at serve time.
- The 8-second minimum is a v5 build policy, not a universal store invariant: `backend/scripts/ops/build_first_person_index.py:MIN_CLIP_DURATION_S = 8.0`; `backend/services/first_person_store.py:validate_clip_entry()` does not enforce it.

**Guarantee:** clips that reach the verified v5 collection passed the current build gates. **Not guaranteed:** every intermediate artifact or every future collection will obey the same minimum and provenance policy.

### Rights and provenance

- `CONTENT-RIGHTS.md`, `config/helplines.yaml`, and `backend/scripts/ops/build_first_person_index.py:CLEARED_CHANNELS/CLEARED_VIDEO_IDS` define rights decisions.
- Rights are persisted separately as `rights_cleared`; `first_person_eligible` is described as a data-quality flag, not a rights decision.
- The reconciliation probe found `first_person_v2` has 72 rights-false points, while v5 has 0.
- The live environment has `FIRST_PERSON_SERVE_UNREGISTERED=true`, which makes rights enforcement configuration-dependent.

**Gap:** rights policy is not an immutable per-source policy record and not an unavoidable reader-side tenant/policy filter. Revocation, deletion, cache invalidation, and audit propagation are not proven end to end.

### Indexing and idempotency

- `backend/services/first_person_store.py:make_first_person_point_id()` uses UUIDv5 over transcript hash/start/end, giving deterministic IDs.
- `backend/ingest/handlers/checkpoint.py` and `backend/ingest/verbatim/pipeline.py` support per-video/per-stage resume.
- `backend/scripts/ops/build_first_person_index.py` deduplicates by transcript hash/start/end and supports dry runs and ID dumps.

**Guarantee:** repeated identical builds can be deterministic for the currently selected inputs. **Gap:** model files, ONNX runtime, tokenizer/preprocessing, input manifests, and build environment are not all bound into the point/build identity. Reconciliation notes report vector differences across ostensibly equivalent v4/v5 builds.

### Retries, backfills, deletion

- Redis locks and Celery/task paths exist in `backend/app/api/admin.py`, `backend/tasks/`, `backend/services/ingestion_tracker.py`, and `backend/app/queue/`.
- Backfill scripts include `backend/scripts/ops/backfill_qdrant_teacher_id.py`, `backfill_edge_tenant_id.py`, and `backfill_chunk_provenance.py`.
- `backend/services/qdrant_service.py` has source deletion helpers; cache adapters expose invalidation methods.

**Gap:** there is no demonstrated universal revocation transaction: source revoked → clips quarantined/deleted → aliases updated → exact cache invalidated → frontend/browser no longer serves the citation → audit record emitted. Backfills can also mutate payloads without changing a collection/build identity.

## What breaks when adding another guru

1. `build_store_clip()` writes `teacher_id`/`teacher_ids`, not arbitrary `guru_id` and policy version.
2. `_TEACHER_LABELS` and `_ALLOWED_SPEAKERS` are product-specific allowlists.
3. Voiceprint profile and threshold selection are not represented as a per-guru registry contract.
4. Rights tables and cleared IDs are hard-coded rather than data-driven per guru/source.
5. Cache and Qdrant collection selection do not prove mandatory server-side guru isolation on every path.
6. Existing “both” semantics can become ambiguous when there are more than two teachers.
7. Benchmark datasets and calibration profiles are not yet partitioned and validated by guru.

## Concrete remediation

- Add a canonical `guru_registry`, `source_registry`, `ingestion_runs`, `speaker_verifications`, `rights_decisions`, `clip_manifests`, and `index_builds` schema.
- Require `guru_id`, `corpus_id`, `policy_version`, `source_id`, `speaker_verification_id`, `build_id`, and `quality_status` in every clip.
- Make the pipeline state machine explicit and fail closed at every transition.
- Store an immutable object-manifest hash and model/runtime hashes in each build report.
- Make revocation/deletion a tested workflow with cache invalidation and alias rollback.
- Keep per-guru voiceprints, rights rules, thresholds, and retention policies outside code.
- Add property tests: same inputs/build manifest produce same IDs/payloads/vectors; retries do not duplicate; any missing policy field prevents indexing.

## Production gate addendum

The deeper design review (`docs/agent/research/FIRST_PERSON_DESIGN_REVIEW_2026-09-27.md`) adds four data-quality blockers that must be treated as release gates: only 35 of 657 rights-cleared videos are represented in v5; v5 payloads lack ASR agreement, disputed-word, and model-version fields; `has_disputed_words` is computed in `backend/services/speaker_diarization.py` but not consumed by serving; and `scripts/ops/data_quality_audit.py` contains no first-person audit path.

Before a new guru is onboarded, require a corpus manifest with source coverage, rights status, ASR/diarization lineage, per-clip disputed rate, speaker verification evidence, and a machine-checkable build ID. Do not promote an index merely because its point count is non-zero or its hashes are internally consistent.
