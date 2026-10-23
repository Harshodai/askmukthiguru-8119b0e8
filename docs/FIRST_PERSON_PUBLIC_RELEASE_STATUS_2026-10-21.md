# First-person context harness — public-release status

**Date:** 2026-10-21  
**Release verdict:** **NO-GO — keep `FIRST_PERSON_CONTEXT_HARNESS_ENABLED=false`.**

This report is the clean handoff for the next engineering agent. It separates what is structurally verified from what is not yet proven. It does not authorize Qdrant writes, alias changes, environment changes, or deployment.

## Executive summary

The first-person v10 collection and fp-context-v1 contract are structurally healthy: the strict audit reports 0 contract violations across 2,737 children and 1,460 parents, no topology defects, and complete archived ASR artifact hashes. The serving path also passed local correctness, safety, snapshot/restore, rollback, and bounded-load checks. Those results are necessary but not sufficient for public release.

The release remains blocked because the collection currently makes stronger provenance claims than the independent artifacts support. In particular, the archive contains 1,173 ECAPA verdicts keyed by legacy v9 point IDs, while the live v10 collection has 2,737 source spans and no direct span-keyed acoustic verdicts. The prior audit found 1,631 spans with no independently backed per-span evidence, 298 citation/audio-window failures, and 2,107 word-coordinate mismatches, including 41 coordinates beyond the transcript. A public system must abstain rather than convert payload claims into evidence.

## Verified and safe to retain

- The strict fp-context-v1 schema, deterministic IDs, parent/child topology, guru isolation, exact text hashes, and archived Parakeet ASR artifact hashes pass their structural checks.
- The harness was rolled back to the safe disabled state after the live matrix. Post-rollback evidence showed no teacher clip served, crisis rails remained active, and out-of-corpus/prompt-injection cases abstained or blocked.
- Local snapshot/restore and alias rollback were exercised successfully. This is local recovery evidence, not production deployment evidence.
- The local load sweeps are an envelope only. They do not establish public production capacity or a QPS commitment.

## Seven blocking defects and required closure evidence

### B1 — Per-span ECAPA speaker evidence is missing or not joinable

**Observed:** 2,737 v10 children carry `speaker_verified=true`, but the archived verdict artifact contains 1,173 records keyed by v9 point IDs. Direct overlap with v10 point IDs and v10 `source_span_id` values is zero. A legacy identity join resolves 1,838 children; only 1,106 have a corresponding older verdict, while 732 have no verdict and 899 have no v9 predecessor.

**Required fix:** run a read-only reconciliation first, then regenerate or re-key verdicts by v10 `source_span_id` using the exact source identity and the span's own audio window. The final artifact must include every v10 span with one of `verified`, `refused`, `missing_audio`, `ambiguous_join`, or `not_run`; absent evidence must never become `speaker_verified=true`.

**Exit gate:** 2,737/2,737 spans have an auditable verdict record; every `verified` record contains method/model revision, calibration revision, source span ID, audio hash or immutable audio identity, start/end milliseconds, cosine, margin, threshold/floor, and timestamp. All unresolved or failed records are quarantined and excluded from the serving candidate.

### B2 — Citation text does not reliably fit the cited audio window

**Observed:** 298/2,737 spans fail the token-coverage check; 2 are currently unverifiable under the ASCII audit; 18 cite beyond archived audio duration; 13 worst cases have no overlap between cited text and the playback window.

**Required fix:** rebuild `audio_start_ms`/`audio_end_ms` from the immutable word-timed ASR artifact that produced the span, not from a copied legacy clip record. Validate clip text coverage, bounds, non-zero duration, and a bounded padding policy. Non-alignable spans are quarantined.

**Exit gate:** zero out-of-bounds citations, zero no-overlap citations, and 100% of served spans pass the multilingual-aware coverage check or carry an explicit verified exception reviewed by a human.

### B3 — Deterministic span IDs do not reproduce from the authoritative word coordinates

**Observed:** only 589/2,737 `word_start`/`word_end` pairs reproduce the cited location in the archived timed transcript; 2,107 disagree and 41 are past the transcript end.

**Required fix:** rebuild span coordinates and IDs from the same normalized word sequence used by the ASR timing artifact. Persist transcript hash, normalization version, word indices, and the source artifact hash used to derive each ID.

**Exit gate:** 2,737/2,737 coordinates are in range and re-derive the exact span text and audio window from the immutable artifact; deterministic rebuilds are byte-identical.

### B4 — Legacy and context-harness collection contracts are conflated

**Observed:** `FIRST_PERSON_COLLECTION=first_person_v10` points the legacy clip store at an fp-context-v1 collection. The legacy path filters on `first_person_eligible`, which fp-context-v1 does not carry. With the harness disabled, the local stack serves no first-person teaching.

**Required fix:** choose one explicit architecture: (a) enable the context harness only after B1–B3 and human gates pass, with the legacy route still isolated; or (b) restore a separately named legacy-schema collection and point the legacy store there while the harness uses its own collection. Add a startup invariant that rejects schema/path conflation.

**Exit gate:** each route has a schema-compatible collection, cache fingerprint, and rollback target; a disabled harness cannot silently read context records through the legacy store.

### B5 — Rights/provenance register is not independent of payload claims

**Observed:** `rights_cleared=true` is present on children, but the current rights manifest was derived from payload data. The builder allowlist is only an engineering input and needs owner confirmation against `CONTENT-RIGHTS.md`.

**Required fix:** create an independent channel/video rights register with source URL, title, rightsholder/permission basis, license or permission record, permitted use, review date, and artifact hash. Join it to every asset before candidate generation.

**Exit gate:** every served asset has an independent rights entry and owner sign-off; missing, expired, or ambiguous rights quarantine all associated spans.

### B6 — Distress boundary and human safety review are unresolved

**Observed:** one moderate distress case reached teacher-clip serving without compassion framing because the distress classifier did not fire. Acute crisis cases were blocked correctly. The repository explicitly forbids tuning this boundary without clinician review.

**Required fix:** obtain a clinician/owner decision on the intended boundary and fallback behavior. Evaluate false negatives and false positives on a human-reviewed safety set; keep the current safe disabled or abstaining posture until the decision is recorded.

**Exit gate:** signed clinical-safety decision, versioned evaluation set, measured false-negative/false-positive results, explicit fallback copy, and live regression coverage for crisis, moderate distress, ambiguous distress, and benign emotion queries.

### B7 — Gold-label calibration and public-scale evidence are incomplete

**Observed:** threshold fitting still needs approximately 299 human zero-error labels. The 42-question exact-text/boilerplate benchmark is not evidence of speaker correctness or public-scale quality. Local load runs are not production capacity proof; Redis/worker outage injection and production/staging retest were not run.

**Required fix:** complete the human gold set with independent annotation and agreement measurement; calibrate abstention and speaker thresholds on held-out data. Run bounded warm/cold, cache hit/miss, dependency fault, and rollback tests, reporting p50/p95/p99, error rate, resource headroom, and test environment.

**Exit gate:** signed gold-label report, held-out calibration report, no-go thresholds met, fault behavior fail-closed, and capacity claims limited to the measured environment unless production evidence is separately authorized.

## Per-span reconciliation script contract

The first implementation should be a **read-only** script at:

```text
backend/scripts/ops/reconcile_v10_ecapa_verdicts.py
```

It should accept:

- a Qdrant v10 points export;
- the archived ECAPA verdict JSON keyed by v9 point ID;
- a v9 points export or immutable v9-to-source identity manifest;
- optional ASR/source-span manifest for stronger identity validation;
- an output JSONL path and a summary JSON path.

It must normalize and compare, in order:

1. exact v10 `source_span_id` (expected to be absent in the legacy file);
2. exact Qdrant point ID;
3. strict legacy identity tuple: `video_id`, normalized verbatim text hash, `start_ms`, `end_ms`, and asset/source identity when available;
4. a unique fallback identity using `video_id`, text hash, and word coordinates only if all components are present.

Every output row must include the v10 span ID, v10 point ID, legacy point ID if found, match class, candidate count, identity fields used, verdict payload, and a `safe_to_upgrade` boolean. Allowed classes should include `exact_span_id`, `exact_point_id`, `unique_identity_match`, `ambiguous_identity_match`, `missing_legacy_point`, `missing_verdict`, `identity_conflict`, and `invalid_input`. `safe_to_upgrade` may be true only for a unique match whose text hash, video/asset identity, time bounds, and verdict schema all agree. The script must never edit Qdrant, mutate manifests, or set `speaker_verified`.

The summary must report totals for all classes, v10 coverage, verdict coverage, unique safe matches, ambiguous matches, missing matches, invalid records, and whether the result is release-blocking. Exit non-zero for malformed input, duplicate identity keys, conflicting matches, or any attempt to run in write mode.

## Public-source guidance used

These sources support the design requirements; they do not replace repository-specific evidence or human sign-off:

- [SpeechBrain speaker-recognition API](https://speechbrain.readthedocs.io/en/latest/API/speechbrain.inference.speaker.html): verification is a comparison of two waveforms with an explicit threshold and score; the artifact must retain the trial inputs and decision threshold.
- [NIST Speaker Recognition Evaluation](https://www.nist.gov/itl/iad/mig/speaker-recognition): speaker-recognition systems require explicit evaluation plans and calibration-oriented measurement, not a single unqualified score.
- [WhisperX](https://github.com/m-bain/whisperx): word-level timestamps are produced through alignment; diarization is a separate imperfect process and alignment models are language-specific.
- [PyTorch CTC forced alignment tutorial](https://docs.pytorch.org/audio/main/tutorials/ctc_forced_alignment_api_tutorial.html): forced alignment maps transcript tokens to speech and returns token timestamps/scores; missing or invalid alignment must not be replaced by guessed offsets.
- [Qdrant snapshots](https://qdrant.tech/documentation/snapshots/) and [Qdrant migration guidance](https://qdrant.tech/documentation/tutorials-operations/migration/): collection migration and rollback require explicit backup/restore and validation, which supports keeping v10 and legacy schemas isolated.
- [WHO ethics and governance of AI for health](https://www.who.int/publications/i/item/9789240029200): health-adjacent AI requires accountability, human rights, human oversight, and governance.
- [NIST AI RMF GenAI Profile](https://www.nist.gov/publications/artificial-intelligence-risk-management-framework-generative-artificial-intelligence): trustworthy deployment requires lifecycle risk management and evaluation of systems, not only a model-level test.
- [WIPO AI and IP](https://www.wipo.int/en/web/frontier-technologies/artificial-intelligence/index): training and deployment data can contain copyright-protected works and need rights infrastructure.
- [Creative Commons attribution practices](https://wiki.creativecommons.org/wiki/Recommended_practices_for_attribution): source, author/rightsholder, title, and license should be retained where applicable.

## Release recommendation

Do not enable the public harness, do not claim verified teacher attribution for v10 spans, and do not deploy to Railway. Approve implementation only for read-only reconciliation, artifact regeneration, independent rights registration, human safety review, and evidence collection. Release requires all seven blocker exit gates to pass and the final decision to be recorded in the plan and evidence index.

## Addendum — Phase 0/1 executed 2026-10-21 (read-only)

The reconciliation script described below now exists and has been run against the
live collection. Nothing else in this report has changed, and the verdict is
still **NO-GO**.

| Item | Value |
|---|---|
| Script | `backend/scripts/ops/reconcile_v10_ecapa_verdicts.py` (read-only, stdlib only, no write mode) |
| Tests | `backend/tests/test_reconcile_v10_ecapa_verdicts.py` — 28 passed |
| Report | `audits/evidence/public_release_phase0_phase1_report_2026-10-21.md` |
| Summaries | `audits/evidence/public_release_v10_ecapa_reconciliation_summary_2026-10-21.json` (`release_grade`, default) and `…_summary_legacy_v1_2026-10-21.json` (comparability only) |
| Per-span rows | `.work/public_release/reconciliation_v10_ecapa.jsonl` — 2,737 rows |
| Transcript | `audits/evidence/public_release_phase1_verification_2026-10-21.txt` |

**B1 is now measured rather than asserted.** Match classes over the 2,737 v10
children: `exact_span_id` 0, `exact_point_id` 0, `unique_identity_match` 1,106,
`ambiguous_identity_match` 0, `missing_legacy_point` 898, `missing_verdict` 732,
`identity_conflict` 1, `invalid_input` 0. Legacy identity coverage is 1,838;
**1,631** spans have no verified acoustic backing — identical to the figure in
this report. The single conflict (`bf7deb57267fda2c…`, video `VrPi2RUUXq4`) has
a legacy clip at the same `start_ms` but a different `end_ms` and a different
text hash; the prior "899 with no v9 predecessor" bucket splits into 898 with
no predecessor plus 1 conflicting one.

`safe_to_upgrade` is **0 / 2,737** under the default `release_grade` policy
because the archived verdict file has no `cosine_floor` and no
`calibration_available`, and its `threshold` was derived from correct clips
rather than from an impostor set. The `--verdict-schema-policy legacy_v1` mode
reports 1,106 for comparability and is **not** release evidence.

B2 (298 citation-window failures), B3 (2,107 word-coordinate disagreements, 41
out of range), B4, B5, B6 and B7 are unchanged — a read-only re-run of the
strict audit reproduces them exactly
(`audits/evidence/public_release_v10_strict_audit_2026-10-21.json`).
