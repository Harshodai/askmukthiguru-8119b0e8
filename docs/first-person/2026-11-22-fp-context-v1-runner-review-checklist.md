# Official-channel `fp-context-v1` runner review checklist

## Legacy versus modern schema

| Concern | Legacy `VideoPipeline` record | Modern `fp-context-v1` contract |
|---|---|---|
| Storage shape | Flat detached chunk, commonly `content_type=video_transcript` | One `ParentUnit` plus ordered `SourceSpan` children |
| Retrieval identity | Arbitrary/legacy point ID and optional chunk metadata | Deterministic parent/span IDs, converted to deterministic Qdrant UUIDs |
| Context | No parent window or ordered child relationship | Parent carries ordered child IDs; serving can hydrate full parent context |
| Text | May mix producer text and local temporary paths | Exact verbatim text, clip hash, transcript hash, canonical YouTube URL |
| Serving gates | Often missing `record_type`, rights, eligibility, and parent fields | `retrieval_child`, `rights_cleared`, register-derived `domain_rights_status`, `first_person_eligible` |
| Attribution | Could promote title-derived teacher labels | Shared/unverified identity until pinned biometric or human evidence |
| Vectors | Legacy dense/sparse naming and writer path varied | Named `passage_dense` and `passage_sparse`, written through `FirstPersonContextStore.upsert` |
| Governance | Legacy rows could be mistaken for modern coverage | Draft manifests remain owner-review-only; no compiled OKF mutation |

## Scope and posture

- [x] Target only `first_person_v13_shadow`.
- [x] Keep `official_channel_shadow_20221122` isolated from serving/main spaces.
- [x] Do not change serving aliases, deployment flags, `memory/okf/compiled.json`, or `spiritual_wisdom_contextual`.
- [x] Keep public first-person release posture NO-GO.
- [x] Archive legacy result artifacts before reset; never treat legacy rows as modern validation.

## Source and rights

- [x] Canonicalize every source to `https://www.youtube.com/watch?v={video_id}`.
- [x] Resolve rights through curated register at write time; never hard-code `licensed`.
- [x] Reject unverified/revoked sources before model construction or Qdrant write.
- [ ] Persist every rejected candidate to `public.corpus_gate_rejections` with source coordinates in the production batch adapter.
- [ ] Add separate graph-write adapter that stamps the same namespace and is independently retryable.

## Speaker provenance

- [x] Never infer individual speaker from title, description, channel metadata, or filename.
- [x] Use shared corpus identity `preethaji_krishnaji` and `shared_unverified` speaker ID.
- [x] Set `speaker_verified=False` and `speaker_verification_status=pending_voice_check`.
- [x] Do not emit ECAPA method, score, margin, calibration, or reviewer fields without evidence.
- [ ] Only promote an individual speaker after pinned ECAPA or human-listen evidence passes the existing review gate.

## Windowing and text integrity

- [x] Accept ASR segment timings, preserve verbatim segment text, and use interval-based inclusion.
- [x] Close windows at sentence boundaries when possible.
- [x] Keep target window duration around 18–25 seconds; reject empty or invalid intervals.
- [x] Compute video transcript hash from the ASR transcript and clip hash from exact stored text.
- [x] Keep `is_verbatim=True`, `text_origin=asr_voted`, and no LLM-authored text.
- [ ] Add artifact/loop/event-marker quality gates to batch input before record construction.

## Parent/child contract

- [x] Construct one validated `ParentUnit` with ordered child IDs.
- [x] Construct strict `SourceSpan` children with `extra="forbid"` validation.
- [x] Use deterministic `make_parent_unit_id` and `make_source_span_id` inputs.
- [x] Ensure parent and children agree on `guru_id`, `video_id`, and `corpus_version`.
- [x] Include `record_type=parent_unit` and `record_type=retrieval_child` through canonical serializers.
- [x] Stamp `first_person_eligible=True` and real `chunker_version=boundary_v1:sentence_closing_18-25s`.
- [x] Call `FirstPersonContextStore.ensure_indexes()` before upsert.
- [x] Call `FirstPersonContextStore.upsert(parent, spans, vectors)` only; no direct legacy point writes.

## Vectors and retrieval

- [x] Call `EmbeddingService.encode_batch()` once per batch of retrieval texts.
- [x] Map dense vectors to `passage_dense`.
- [x] Convert sparse output to Qdrant `SparseVector` and map to `passage_sparse`.
- [ ] Smoke-test `FirstPersonContextStore.retrieve()` against a live shadow point.
- [ ] Smoke-test `FirstPersonStore.search_hybrid()` against a live shadow point.
- [ ] Verify named vector dimensions against the target collection before full batch.

## Graph and operational safety

- [x] Keep Memgraph namespace deletion scoped to exact `ingest_namespace`.
- [ ] Implement modern graph upsert as a separate transaction after Qdrant success.
- [ ] Make graph retries idempotent by deterministic parent/span IDs.
- [ ] Emit per-video result rows only after Qdrant write returns.
- [ ] Mark draft OKF output `draft_needs_owner_review=True`; never compile it.
- [ ] Relaunch full batch only after one-video smoke evidence is recorded.

## Required smoke evidence before full batch

For `-EpUdkE15NM`, attach:

1. Qdrant snapshot/report and before/after namespace counts.
2. One `parent_unit` payload and all matching `retrieval_child` payloads.
3. Canonical source URL and hash fields.
4. `speaker_verified=False`, `pending_voice_check`, and shared attribution.
5. Successful dense retrieval and hybrid retrieval using shadow collection.
6. No writes to serving alias, legacy general collection, or compiled OKF.

## Legacy-to-modern migration stop conditions

Stop batch immediately on any of:

- Missing or non-licensed rights status.
- Any title-derived individual speaker attribution.
- Bare `speaker_verified=True` or unverifiable voice fields.
- Missing parent, child, deterministic IDs, hashes, canonical URL, or named vectors.
- Qdrant write bypassing `FirstPersonContextStore.upsert`.
- Any direct write to serving/main collection or alias.
- A draft OKF row being scored or compiled as a label.
