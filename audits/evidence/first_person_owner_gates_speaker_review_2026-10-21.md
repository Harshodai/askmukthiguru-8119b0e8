# First-person context harness: speaker review, evidence requirements, and owner gates

**As of:** 2026-10-21  
**Overall status:** **BLOCKED** for candidate readiness and production promotion. Local auditor availability and the focused code-test rerun are **VERIFIED**; those do not establish candidate data completeness.

## Executive summary

A metadata-only, read-only Qdrant scroll examined all **1,981** points in `first_person_v9`. The legacy payload contains `speaker_verified=true` for **779** points and has the `speaker_verified` key entirely **absent** for the other **1,202** points. There were no explicit `false`, `null`, empty-string, or malformed values in this collection snapshot. Those 1,202 records span **359 distinct videos** and comprise **635** records tagged with legacy `teacher_id=krishnaji` / stored speaker label `Sri Krishnaji`, and **567** tagged `teacher_id=preethaji` / stored label `Sri Preethaji`. All **1,202 point IDs are unique** in the review.

The legacy teacher/speaker labels are metadata, not verification evidence. Do not backfill `speaker_verified=true` from `teacher_id`, display label, channel, or collection membership. The existing 779 true booleans are not by themselves a complete fp-context attribution record either: the auditor finds `guru_id`, `speaker_id`, and `speaker_role` missing on all 1,981 legacy points, as are other fp-context contract fields.

The Qdrant collection is green and the legacy audit reports no rights/eligibility flag failures, no verbatim/hash failures, and no duplicate point IDs. These are useful checks on legacy fields, but they do **not** replace source-based per-video rights evidence, word-timed ASR, speaker identity evidence, parent/child coverage, audio/citation alignment, or human evaluation for a new candidate.

The running-backend focused suite was rerun after the approved `/opt` mount setup: **296 passed in 15.14s**. No application code was changed by the mount setup. The audit, speaker review, and tests made no Qdrant writes; the alias remains `first_person -> first_person_v7`.

## Detailed speaker-flag findings

| Finding | Result |
|---|---:|
| Points scanned in `first_person_v9` | 1,981 |
| `speaker_verified=true` | 779 |
| Key absent (not false) | 1,202 |
| Explicit `false` / `null` / empty / non-boolean | 0 |
| Distinct point IDs among the 1,202 flagged records | 1,202 |
| Distinct videos among the 1,202 flagged records | 359 |
| Missing-key records tagged `krishnaji` | 635 |
| Missing-key records tagged `preethaji` | 567 |

The auditor JSON is aggregate-only; it did not contain item IDs. A separate `points/scroll` read used `with_payload` restricted to `speaker_verified`, legacy speaker/teacher labels, video ID, clip start/end, and transcript hash, and `with_vector=false`. It fetched no transcript text or vectors and did not mutate Qdrant. The resulting item-level file contains the 1,202 unique point IDs and minimum metadata needed to route each record for review:

[Metadata-only point review: `first_person_speaker_flag_review_2026-10-21.json`](first_person_speaker_flag_review_2026-10-21.json)  
SHA-256: `02c82c5fb3740052a9b6347342a9ed4718105797ece8f31e1672f83e9378558f`  
Fields include point ID, video ID, start/end offsets, stored teacher/speaker labels explicitly marked as unverified metadata, and transcript hash. No transcript text or vectors are included.

## Current readiness snapshot

- `first_person_v9`: 1,981 points; collection status green. The `first_person` alias still targets **v7**, while this audit expects **v9**.
- The auditor reports all 18 required fp-context fields missing on all 1,981 points **except** `speaker_verified`, which is missing on 1,202. The fields missing on all 1,981 are: `asr_engine`, `asr_model_version`, `audio_end_ms`, `audio_start_ms`, `boundary_status`, `caption_status`, `completeness_status`, `corpus_version`, `guru_id`, `parent_unit_id`, `source_asset_id`, `source_span_id`, `source_text_hash`, `speaker_id`, `speaker_role`, `turn_id`, and `turn_index`.
- `fp_context_v1_local` has 1,082 points and is green, but its schema is partial (for example, `rights_cleared` and `source_span_id` are present on 591 points, and indexed vectors count is 591). It is not evidence that the approved, complete fp-context-v1 parent/child candidate exists or is ready to serve.
- The source handoff says the workspace has only two plain transcript `.txt` files and no required word-timed ASR JSON. A fresh transcription/alignment artifact is required; do not infer timings from clip boundaries or from plain text.
- The context harness and shadow route are code/test complete but active serving is not wired; `FIRST_PERSON_CONTEXT_HARNESS_ENABLED` and shadow remain disabled. Do not enable either against legacy data.

## Required evidence package before candidate-build approval

The owner/data steward should provide or approve the following versioned artifacts. Every artifact must be tied to an immutable source/corpus version and candidate manifest.

1. **Source and rights inventory, per video/asset.** Stable `source_asset_id`, `video_id`, canonical URL, asset owner/source, documentary permission/license basis and scope, restrictions, rights reviewer, date/version, and quarantine disposition. Unknown, restricted, or disputed assets must be quarantined, not presumed clear. The legacy audit's `rights_cleared=true` flags are not the documentary inventory.
2. **Raw audio/source provenance.** Immutable source audio/video identity, duration, checksum, retrieval/access date and permitted-use record; any extracted audio file checksum and mapping back to the source. Do not put restricted source media in the candidate without rights approval.
3. **ASR/transcription package with word-level timing.** Original machine output plus canonical reviewed text; word tokens with start/end times, diarization/speaker-turn IDs, turn order, language, engine/provider and exact model/version, settings, and asset checksum. The current local plain `.txt` files do not meet this. The plan notes Sarvam Batch STT supplies diarization/chunk timestamps but not word-level timestamps, so an owner must select a compatible provider/alignment workflow and approve its cost, or explicitly approve a revised acceptance criterion with compensating evidence before implementation.
4. **Speaker verification evidence.** Review the 1,202 IDs in the linked report against the original audio; record reviewer/method, evidence reference, decision, timestamp, confidence/ambiguity, `speaker_id`, `speaker_role`, `guru_id`, `teacher_id` mapping where supported, and `speaker_verified=true` only when the evidence supports it. The 779 existing true flags also need traceable verification provenance before they are accepted into the new typed candidate. Unknown/host/dialogue/overlap/ambiguous segments should be excluded or quarantined. Never repair this by mapping an ID or existing label to a name.
5. **Verbatim, hash, and boundary proof.** Canonical source-span text tied to the approved transcript; stable `source_text_hash` and retained video-level `transcript_hash`; exact word-index and millisecond offsets; validated start/end order and media-duration bounds; `boundary_status` and `completeness_status`; ASR engine/model version; `caption_status`; automated drift checks plus human listening samples. Hashes prove byte identity, not speaker attribution or rights.
6. **Parent/child/context manifest.** A versioned candidate manifest with `corpus_version`, deterministic `source_span_id`, `parent_unit_id`, `turn_id`, `turn_index`, `source_asset_id`, `guru_id`, `speaker_id`/role/verification, span ordering, relationships and explicit quarantine reasons. Parent and child IDs, guru/video/turn membership, payload/vector counts, indexes, checksums, and source mapping must agree. Use the existing builder in dry-run mode first; it is intentionally unable to write to Qdrant.
7. **Citation/audio alignment package.** For every candidate span, prove the rendered citation points to the same immutable span/text/hash and exact start/end playback offsets in the source audio/video. Store stable source URL and timestamps. Harness reconstruction must remain deterministic and use stored span text in order; no model-authored teaching text.
8. **Coverage and integrity audit.** Per-guru, per-video and per-speaker counts; included/quarantined totals and reasons; all required contract fields present; rights and speaker flags true only with evidence; duplicate/deterministic-ID checks; source-text and transcript-hash verification; exact-audio boundary samples; parent-child consistency; complete holdout-exclusion proof. Zero unexplained count differences.

## Required benchmark and human-evaluation evidence

Before enabling shadow or asking for release:

- A video/parent-disjoint train/calibration/held-out split and a documented leakage check; stratify by guru, language, question type, directness, ambiguity/coreference, host dialogue, and boundary conditions.
- Human-authored gold questions and relevance/answerability labels; independent second annotation and adjudication of disagreements. AI-generated labels do not count as calibration evidence.
- Candidate-bound retrieval and answerability results: intended-span/parent rank and recall, abstention/false-direct rates, refusal and out-of-corpus leakage, multilingual strata, cross-guru and cross-parent red-team outcomes, citation/audio correctness, and per-class error examples.
- The threshold/selector calibration record, annotator protocol, label counts, inter-annotator disagreement/adjudication, exact candidate and code hashes, test command/results, latency percentiles, memory and model/provider cost.
- Regression evidence for cache-policy fingerprints, exact-text reconstruction, rights/speaker/hash/completeness/boundary gates, bounded telemetry, and crisis invariance. The existing 296-test run verifies code contracts, not live corpus quality.

## Pending owner decisions and approvals

| Status | Owner decision / approval | Required approval payload or artifact |
|---|---|---|
| BLOCKED | Supply/authorize source assets and per-video rights review | Asset inventory and documented rights basis; define what is excluded/quarantined. |
| BLOCKED | Select ASR/word-alignment and speaker-verification workflow, and approve budget | Provider/model/version and method; word-level timing acceptance; source-audio handling; diarization and human-review protocol; cost cap. |
| BLOCKED | Approve speaker-attribution review of 1,202 missing records and provenance policy for 779 existing `true` flags | Point-ID review file; named reviewer/role and method; evidence references; quarantine criteria; no blanket boolean backfill. |
| NOT RUN | Authorize candidate build/upsert after the dry-run manifest passes | Exact new collection name/version, input-manifest hash, expected point counts, schema/index plan, dry-run report, rights/quarantine totals, snapshot/rollback steps, operator and execution window. This is separate from local read-only audit approval. Do not overwrite v8/v9 or switch aliases. |
| BLOCKED | Approve human-labeling/calibration scope and evaluation budget | Sampling plan, video-disjoint split, rubric, independent annotator and adjudicator, label target, cost/latency limits, acceptance thresholds. |
| NOT RUN | Approve isolated backup/restore drill and staging blue-green/soak window | Backup/snapshot manifest and checksums; isolated restore destination; recovery commands and count/hash verification; rollback target; soak duration; p50/p95/p99, memory/cost thresholds. Never point a drill at live data. |
| NOT RUN | Approve live shadow activation after candidate passes all gates | Exact environment/flag and candidate collection, traffic/sample limits, telemetry review, kill switch, duration, rollback. Current flags remain false/empty. |
| NOT RUN | Approve alias promotion, active serving and production deployment | Separate exact alias operation, release artifact/image hash, staged/canary checks, smoke matrix, rollback, production owner and window. Not implied by candidate-build approval. |
| BLOCKED | Approve any crisis-policy change | Separate clinician/safety review and targeted crisis regression; no crisis behavior change is in this plan's current authorization. |
| NOT RUN | Production-readiness declaration | Requires every prior evidence package, all approvals, tested rollback/restore, full soak and owner sign-off. |

## Completed in this follow-up

- Reviewed the auditor JSON and then performed an item-level read-only scroll because the JSON itself contains counts but no IDs.
- Verified **1,202 missing / 779 true / 0 explicit false / 359 videos**, with 1,202 unique point IDs. Wrote the metadata-only review file and its checksum above; no vectors or transcript text were fetched.
- Re-ran the exact focused selection inside `mukthiguru-backend`: **296 passed in 15.14s** after the alternate mount setup.
- No Qdrant writes, alias updates, source/corpus rebuild, application-code edit, deployment, or crisis change occurred.

## Status conclusion

Local test readiness and the read-only item-level review are **VERIFIED**. Candidate data/evidence, human calibration, live restore/soak, shadow activation, alias promotion, deployment, and final sign-off remain **BLOCKED** or **NOT RUN** as labelled above. No further mount approval is pending. Move to the next stage only when the owner provides the listed source/rights/ASR/speaker inputs and gives the distinct approval required for the exact candidate build operation.
