Phase 3 is accepted as evidence for the 1,600 exact-reconstruction spans only.

Proceed with Phase 2: regenerate independently calibrated per-span ECAPA speaker evidence.

The overall public-release verdict remains NO-GO. Do not enable the harness, do not write to Qdrant, do not change aliases, do not mutate Redis, do not deploy, and do not touch Railway.

## Confirmed Phase 3 facts

Phase 3 produced a candidate package with:

- 1,600 exact-reconstruction spans;
- 1,137 quarantined spans;
- 1,127 transcript/text variants;
- 10 spans not locatable in the authoritative artifact;
- 0 failures across 11 validation checks for the 1,600 exact spans;
- 0 audio-window coverage failures for those 1,600 spans;
- 0 audio-end violations;
- 0 out-of-range coordinates;
- 0 deterministic source-span-ID mismatches;
- two independent byte-identical rebuilds;
- authoritative artifacts from `transcripts_B/{video_id}.json`;
- normalization `fp-norm-unicode-v1`;
- coordinate space `fp-coords-v1`;
- corpus version `fp-context-transcript-v2`;
- audio source `audio_archive/wavs/{video_id}.wav`.

Do not include the 1,127 variants or 10 unlocatable spans in Phase 2 unless a separate owner approval explicitly authorizes the variant tier.

## First: read the required context

Before changing anything, re-read:

- `AGENTS.md`
- `lessons.md`
- `docs/FIRST_PERSON_PUBLIC_RELEASE_STATUS_2026-10-21.md`
- `.claude/tasks/first-person-v10-public-release-plan-2026-10-21.md`
- `docs/FIRST_PERSON_V5_V10_COMPLETION_2026-10-21.md`
- the Phase 3 report and final-verification JSON
- `backend/scripts/ops/verify_speakers_ecapa.py`
- `backend/scripts/ops/build_full_corpus_v10.py`
- `backend/scripts/ops/rebuild_v10_asr_coordinates.py`
- `backend/scripts/ops/audit_first_person_v10_strict.py`
- the existing ECAPA verdict/calibration artifacts

Inspect all relevant directory-level `AGENTS.md` files before editing files.

## Phase 2 safety constraints

1. Slice audio only from:

   `audio_archive/wavs/{video_id}.wav`

2. Never use:

   `<asr_root>/audio/`

   The Phase 3 evidence shows that most files there are header-only WAV stubs.

3. Use the Phase 3 exact candidate's rebuilt:

   - `source_span_id`
   - `video_id`
   - `audio_start_ms`
   - `audio_end_ms`
   - `source_text_hash`
   - transcript/artifact hash

4. Never use the live v10 payload's old audio coordinates.

5. Never use the old v9 clip window as the ECAPA slice.

6. Do not infer speaker verification from:
   - `speaker_verified=true` in the existing payload;
   - a legacy v9 verdict;
   - a video-level speaker label;
   - a filename or channel name;
   - a partial or ambiguous join.

7. Do not write any verdict back to Qdrant.

8. Do not update `speaker_verified` in any payload.

9. Do not enable `FIRST_PERSON_CONTEXT_HARNESS_ENABLED`.

10. Do not change aliases, collections, Redis, Docker volumes, production configuration, or Railway.

## Dependency work

The current evidence says `soundfile` is absent from:

- `backend/requirements.txt`;
- `backend/requirements.lock`;
- the runtime image.

Resolve this only through the repository's normal dependency process.

Before editing dependency files:

1. Inspect the current dependency workflow, lock-generation instructions, and repository scripts.
2. Confirm whether `soundfile` is actually required by the chosen implementation or whether an existing supported audio reader can be used.
3. Do not perform an ad hoc `pip install`.
4. Do not modify the runtime image or recreate production services.
5. If dependency files must change, make the smallest reproducible change and record:
   - package version;
   - reason;
   - lock-generation command;
   - command exit code;
   - resulting diff;
   - import/runtime verification.

If lock generation needs network access or owner approval, stop and report the exact command and approval required rather than bypassing the process.

## Calibration requirements

The old verdict archive is not release-grade because:

- it lacks `cosine_floor`;
- it lacks `calibration_available`;
- its `threshold=0.4668` is the p01 of correct-clip margins, not an impostor-calibrated false-accept floor;
- its false-accept rate is therefore unknown.

Regenerate calibration using a held-out impostor set.

The calibration artifact must include at least:

- model name and exact model revision;
- embedding/preprocessing configuration;
- reference/guru centroid construction method;
- positive and impostor trial counts;
- train/calibration/test split definition;
- score distribution summaries;
- margin threshold;
- cosine floor;
- false-accept and false-reject measurements;
- calibration method/version;
- data/artifact hashes;
- `calibration_available=true` only when the required held-out evidence exists;
- generation timestamp;
- deterministic input manifest hash.

Do not invent a threshold from the existing archive. Do not reuse `0.4668` as a release threshold.

If the held-out impostor set is insufficient, fail closed and produce an explicit blocked calibration report.

## Per-span verdict requirements

Generate one verdict row for each of the 1,600 exact-reconstruction spans.

Each row must include:

- `source_span_id`;
- `video_id`;
- source/transcript/artifact hash;
- audio file path or immutable audio identity;
- audio file hash if practical and supported by the repository;
- `audio_start_ms`;
- `audio_end_ms`;
- actual sliced-audio duration;
- speaker model and revision;
- calibration revision;
- predicted guru;
- expected guru;
- cosine score;
- runner-up score;
- margin;
- cosine floor;
- margin threshold;
- verdict;
- reason code;
- generation timestamp or deterministic run identifier.

Allowed verdict/reason categories should distinguish at least:

- `verified`;
- `refused_below_cosine_floor`;
- `refused_below_margin`;
- `refused_guru_mismatch`;
- `missing_audio`;
- `invalid_audio`;
- `out_of_bounds`;
- `too_short`;
- `calibration_unavailable`;
- `not_run`.

The verdict file must be keyed by `source_span_id`, not legacy v9 point ID.

Every span must receive exactly one row. No span may be silently omitted.

## Required validation

For every span:

- confirm the source span exists in the exact Phase 3 candidate;
- confirm the audio file exists and is a real PCM WAV;
- confirm audio bounds;
- confirm `audio_end_ms > audio_start_ms`;
- confirm the slice uses the candidate coordinates;
- confirm the audio slice corresponds to the correct video;
- confirm the expected guru is explicit and not inferred from an unverified display label;
- confirm calibration fields are finite and present;
- confirm the verdict is reproducible from the recorded score and thresholds;
- confirm no verdict is emitted for quarantined spans;
- confirm the output is deterministic apart from explicitly documented timestamps.

Add or extend tests for:

- exact candidate span loading;
- 1,600-row completeness;
- exclusion of all 1,137 quarantined rows;
- missing audio;
- header-only/stub audio;
- out-of-bounds coordinates;
- invalid WAV;
- too-short slices;
- absent calibration;
- non-finite score;
- guru mismatch;
- below-floor score;
- below-margin score;
- exact threshold boundary;
- duplicate source-span ID;
- deterministic repeated output;
- no Qdrant/write mutation;
- schema validation of every verdict row.

## Required deliverables

Create:

1. the smallest appropriate dependency change, only if required;
2. the regenerated calibration artifact;
3. the per-span ECAPA verdict artifact;
4. a machine-readable Phase 2 summary;
5. a human-readable Phase 2 evidence report;
6. focused tests and their results;
7. updated plan status with exact commands, exit codes, and artifact hashes.

Use a clear evidence location such as:

```text
audits/evidence/public_release_phase2_...
```

Do not overwrite the old verdict archive. Write a new versioned artifact.

## Required measurements

Report:

- exact candidate spans requested: 1,600;
- verdict rows emitted;
- verified count;
- refused count by reason;
- missing/invalid/not-run count;
- calibration availability;
- positive trial count;
- impostor trial count;
- false-accept measurement;
- false-reject measurement;
- threshold/floor values;
- model and calibration hashes;
- audio files successfully opened;
- audio slices successfully generated;
- any quarantined or excluded rows;
- whether every output row is keyed by `source_span_id`.

## Required commands and evidence

Run and record actual exit codes for:

- dependency validation;
- lock generation, if applicable;
- `py_compile`;
- focused Phase 2 tests;
- Phase 3 regression tests;
- reconciliation regression tests;
- relevant lint;
- deterministic repeated-run comparison;
- verdict schema validation;
- the Phase 2 dry-run/generation command.

Do not hide failures with `|| true` or lossy pipelines.

## Mutation statement

End the report with an explicit statement covering:

- Qdrant reads/writes;
- collection creation/deletion;
- alias changes;
- Redis reads/writes/flushes;
- environment changes;
- Docker image/container changes;
- git reset/clean/checkout/stash/commit/push;
- Railway/deployment actions.

The expected result is:

```text
No Qdrant write.
No alias change.
No Redis mutation.
No harness enablement.
No deployment.
No Railway action.
```

## Stop conditions

Stop and report BLOCKED if:

- calibration cannot be independently measured;
- `soundfile` or another dependency cannot be added through the approved process;
- the exact Phase 3 candidate cannot be loaded;
- audio provenance is ambiguous;
- any span cannot be mapped to its own audio window;
- the output cannot be keyed by `source_span_id`;
- any requested action would mutate Qdrant or serving state.

## Final response format

End with:

1. Verdict: `GO`, `NO-GO`, or `BLOCKED`.
2. Phase 2 verdict separately: `PASS`, `FAIL`, or `BLOCKED`.
3. Exact files created/modified.
4. Exact commands and exit codes.
5. Test counts.
6. Calibration metrics and artifact hashes.
7. Per-span verdict totals and reason counts.
8. Confirmation that only the 1,600 exact spans were processed.
9. Confirmation that all 1,137 quarantined spans were excluded.
10. Explicit mutation statement.
11. Remaining blockers:
    - B4 legacy/context schema separation;
    - B5 independent rights register;
    - B6 clinician review;
    - B7 human gold labels and public-scale evidence.
12. Exact next approval required.

Do not claim public readiness after Phase 2. Phase 2 only closes or measures B1. The overall release remains NO-GO until B4–B7 and all final integration/safety/rollback gates are complete.
