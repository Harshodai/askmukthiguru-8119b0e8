# Handoff prompt: first-person v10 public-release remediation

You are the implementation agent for the AskMukthiGuru repository at:

```text
/Users/harshodaikolluru/Public/askmukthiguru-8119b0e8
```

Your job is to execute the approved first-person v10 public-release remediation plan rigorously, beginning with the per-span ECAPA speaker-evidence reconciliation. A separate reviewing agent will inspect your work end to end, so every claim must be reproducible from files, commands, logs, tests, and machine-readable evidence.

## Primary documents to read first

Read these before modifying anything:

1. `AGENTS.md` — binding repository rules and historical first-person invariants.
2. `lessons.md` — known regressions and prohibited shortcuts.
3. `docs/FIRST_PERSON_PUBLIC_RELEASE_STATUS_2026-10-21.md` — current no-go status and all seven blockers.
4. `.claude/tasks/first-person-v10-public-release-plan-2026-10-21.md` — approved staged plan.
5. `docs/FIRST_PERSON_V5_V10_COMPLETION_2026-10-21.md` — prior evidence, exact counts, and prior fixes.
6. `docs/FIRST_PERSON_COLLECTION_EVOLUTION_V1_TO_V10.md` — collection evolution and evidence boundaries.
7. `backend/scripts/ops/verify_speakers_ecapa.py` — current verifier and legacy verdict schema.
8. `backend/scripts/ops/audit_first_person_v10_strict.py` — strict audit and current blocker calculations.
9. `backend/scripts/ops/build_full_corpus_v10.py` — v10 builder, timing, speaker, and ID behavior.
10. `backend/scripts/ops/validate_fp_context_candidate.py` — fail-closed candidate manifest contract.

Also inspect relevant `AGENTS.md` files in every directory you enter. Do not assume the current dirty tree is safe to overwrite.

## Current verified state

The current release verdict is **NO-GO**. Keep:

```text
FIRST_PERSON_CONTEXT_HARNESS_ENABLED=false
```

Do not enable the public harness, change Railway, deploy, mutate production, or switch public aliases.

Verified structural results:

- 2,737 v10 child spans and 1,460 parents pass the strict fp-context-v1 contract/topology audit.
- Archived ASR artifact hashes and Parakeet provenance pass the structural audit.
- Local live correctness/safety matrix, snapshot/restore, rollback, and bounded load evidence exist, but they are local evidence only.
- Post-rollback live evidence showed no teacher clip served and safety rails remained active.

Known blocker counts:

- 2,737 v10 spans have no directly joinable span-keyed acoustic verdict.
- The archive contains 1,173 ECAPA verdicts keyed by legacy v9 point IDs.
- Direct overlap between archived v9 point IDs and v10 point IDs/source span IDs is zero.
- A legacy identity join resolves 1,838 v10 children; 1,106 have a corresponding legacy verdict, 732 have no verdict, and 899 have no v9 predecessor.
- Therefore 1,631 v10 children currently lack independently backed per-span acoustic evidence.
- 298/2,737 spans fail citation/audio-window coverage; 18 cite beyond archived audio duration; 13 worst cases have no overlap.
- 2,107/2,737 word-coordinate pairs disagree with the authoritative timed transcript; 41 are beyond transcript bounds.
- The legacy store cannot safely read fp-context-v1 because it expects `first_person_eligible`; schema/path conflation must be resolved.
- Rights evidence is not independent of payload claims.
- A moderate distress case bypassed compassion framing; clinician review is required before tuning this boundary.
- Human threshold calibration still needs approximately 299 human zero-error labels.

## Operating rules

1. Work in the current checkout. Do not reset, clean, checkout another branch, overwrite peer changes, or delete existing work.
2. Before edits, record `git status --short --branch`, HEAD, changed/untracked files, active env flags, Docker state, Qdrant collections/aliases, and relevant file hashes.
3. Use the repository-prescribed Docker path or Makefile. The Docker binary is at `/Users/harshodaikolluru/.docker/bin/docker`.
4. Do not use global Redis flushes, destructive volume operations, mutable model downloads, broad graph changes, or Railway deployment.
5. Never default missing `speaker_verified` to `true`.
6. Never synthesize audio timings or word coordinates from WAV duration.
7. Never treat payload claims as independent evidence.
8. Any missing, ambiguous, conflicting, stale, or malformed evidence must be quarantined and excluded from a serving candidate.
9. Retrieval-only first-person answer text must remain exact stored source-span text. Do not introduce LLM-authored teaching prose.
10. Every generated artifact must include source/model/calibration revisions and enough metadata for reproduction.
11. Capture real exit codes. Do not hide failures behind `|| true`, lossy pipelines, or omitted logs.
12. Do not claim production scale from local desktop load tests.

## Required execution order

### Phase 0 — state freeze

Create a read-only state/evidence record before mutation. Include:

- git branch/HEAD/status and dirty-file inventory;
- relevant file hashes;
- Docker context, image/container identity, health;
- active first-person env flags and collection/alias targets;
- Qdrant collection counts and schemas;
- locations and hashes of v9/v10 point exports, verdict files, ASR manifests, timing artifacts, and rights manifests;
- current harness flag and serving route configuration.

Do not mutate anything in Phase 0.

### Phase 1 — implement the per-span reconciliation script first

Create:

```text
backend/scripts/ops/reconcile_v10_ecapa_verdicts.py
```

Add focused tests:

```text
backend/tests/test_reconcile_v10_ecapa_verdicts.py
```

Keep the script read-only and preferably standard-library-only. Do not connect to Qdrant unless the script is explicitly reading a supplied export through a read-only API; prefer file inputs.

Required inputs:

- v10 Qdrant points export;
- archived ECAPA verdict JSON keyed by legacy v9 point ID;
- v9 points export or immutable v9-to-source identity manifest;
- optional ASR/source-span manifest;
- output JSONL and summary JSON paths.

Matching order:

1. exact v10 `source_span_id`;
2. exact Qdrant point ID;
3. strict legacy identity tuple using `video_id`, normalized verbatim text hash, `start_ms`, `end_ms`, and source/asset identity where available;
4. unique fallback using `video_id`, text hash, and word coordinates only if all fields exist.

Every v10 child must produce exactly one output row. Allowed match classes:

```text
exact_span_id
exact_point_id
unique_identity_match
ambiguous_identity_match
missing_legacy_point
missing_verdict
identity_conflict
invalid_input
```

Each row must include:

- v10 `source_span_id`;
- v10 point ID;
- legacy point ID if found;
- match class;
- candidate count;
- identity fields used;
- computed and declared text hashes;
- v10 and legacy video/source/time fields;
- verdict payload when found;
- `safe_to_upgrade`.

`safe_to_upgrade` may be true only when the match is unique and all available text, video/source, time-bound, and verdict-schema checks agree. The script must never edit Qdrant, mutate manifests, or set `speaker_verified`.

The summary must include:

- total v10 children;
- counts by match class;
- direct span-ID coverage;
- legacy identity coverage;
- verdict coverage;
- unique safe matches;
- ambiguous/conflicting/missing counts;
- malformed/invalid counts;
- release-blocking boolean and reasons;
- input file hashes and script version.

Exit behavior:

- malformed input, duplicate identity keys, conflicts, or unsafe write-mode attempts: non-zero;
- ordinary missing coverage: produce the full report and exit with a documented release-blocking status;
- never silently drop a v10 span.

Tests must cover:

- exact span match;
- exact point match;
- unique legacy identity match;
- duplicate/ambiguous identity;
- text-hash mismatch;
- time-bound mismatch;
- missing verdict;
- missing legacy point;
- malformed verdict;
- all-v10-row completeness;
- deterministic byte-identical repeated output;
- fail-closed behavior;
- no Qdrant/write mutation.

Run and record:

```bash
python -m py_compile backend/scripts/ops/reconcile_v10_ecapa_verdicts.py
python -m pytest backend/tests/test_reconcile_v10_ecapa_verdicts.py -q
python backend/scripts/ops/reconcile_v10_ecapa_verdicts.py --help
```

Then run a dry-run against the real current artifacts. It must reproduce the known coverage gaps without upgrading payloads.

### Phase 2 — regenerate independent ECAPA evidence

Do not start this phase until Phase 1 is reviewed locally and the input artifact shapes are confirmed.

- Resolve the missing `soundfile`/audio dependency through the repository’s normal dependency process; do not install an ad hoc unpinned dependency into the release image.
- Regenerate calibration with both cosine floor and margin threshold from a measurable held-out impostor set.
- Run ECAPA on each span’s own `[start_ms, end_ms]` slice.
- Persist per-span source ID, audio identity/hash, start/end, model revision, calibration revision, cosine, margin, threshold/floor, verdict, and reason.
- Quarantine unavailable, too-short, out-of-bounds, or below-threshold spans.
- Do not upgrade v10 payloads merely because a legacy verdict matches.

Exit only with explicit 2,737-row coverage or a complete quarantine report.

### Phase 3 — rebuild ASR coordinates and audio windows

Use the immutable word-timed transcript that produced the ASR artifact. Recompute:

- normalized word sequence and normalization version;
- `word_start`/`word_end`;
- text hash;
- `start_ms`/`end_ms`;
- deterministic source span ID.

Require multilingual-aware validation. Reject out-of-range or no-overlap windows. Repeat the build twice and compare manifests byte-for-byte.

### Phase 4 — independent rights register

Create or validate an independent rights manifest with:

- source asset/video ID;
- source URL;
- title/channel/rightsholder;
- license or permission basis;
- permitted use;
- review date;
- artifact hash;
- owner decision/status.

Join every candidate asset to the register. Missing or ambiguous rights quarantine all related spans.

### Phase 5 — separate serving contracts

Choose and document one architecture:

- context harness uses fp-context-v1/v10 and its own store/schema; legacy store points to a legacy-schema collection; or
- context harness remains disabled until an explicitly isolated context route is ready.

Add startup/configuration tests that reject a legacy store pointed at fp-context-v1. Ensure collection/schema identity is in cache policy fingerprints. Do not allow disabled-harness behavior to silently read context records through legacy filters.

### Phase 6 — human safety and gold review

Do not tune distress behavior yourself without the required clinician/owner review. Obtain:

- signed decision on moderate distress behavior;
- versioned human-reviewed safety set;
- false-negative/false-positive results;
- fallback copy and regression tests;
- completed human gold labels and agreement measurement;
- held-out calibration report for abstention/speaker thresholds.

Automated exact-text scores are not a substitute for human speaker, safety, or provenance review.

### Phase 7 — integration and final evidence

Only after all prior phases pass:

- run strict structural/readiness audits;
- run focused and complete test suites with exact exit codes;
- run a local harness-on live matrix only in an isolated local environment;
- verify exact-cache hit/miss and policy invalidation;
- exercise Qdrant/Redis/worker fault paths fail-closed;
- run bounded warm/cold load tests;
- snapshot, restore, switch alias in a disposable target, and roll back;
- disable the harness and verify safe rollback;
- update the continuation plan, evidence index, lessons/docs if applicable;
- leave Railway untouched.

The public release remains NO-GO if any gate fails.

## External guidance already researched

Use these sources as design guidance, not as substitutes for repository evidence:

- SpeechBrain speaker verification API: https://speechbrain.readthedocs.io/en/latest/API/speechbrain.inference.speaker.html
- NIST Speaker Recognition Evaluation: https://www.nist.gov/itl/iad/mig/speaker-recognition
- WhisperX word timestamps/alignment/diarization: https://github.com/m-bain/whisperx
- PyTorch CTC forced alignment: https://docs.pytorch.org/audio/main/tutorials/ctc_forced_alignment_api_tutorial.html
- Qdrant snapshots: https://qdrant.tech/documentation/snapshots/
- Qdrant migration guidance: https://qdrant.tech/documentation/tutorials-operations/migration/
- WHO AI health ethics/governance: https://www.who.int/publications/i/item/9789240029200
- NIST AI RMF GenAI Profile: https://www.nist.gov/publications/artificial-intelligence-risk-management-framework-generative-artificial-intelligence
- WIPO AI and IP: https://www.wipo.int/en/web/frontier-technologies/artificial-intelligence/index
- Creative Commons attribution: https://wiki.creativecommons.org/wiki/Recommended_practices_for_attribution

## Required deliverables from your run

At minimum, leave:

- the reconciliation script;
- focused tests;
- machine-readable reconciliation output and summary;
- a human-readable Phase 0/Phase 1 report;
- updated plan status with commands, exit codes, and blockers;
- no unverified payload mutation;
- no harness enablement unless every gate is explicitly proven.

For each phase, record:

```text
phase
command
cwd
environment/container identity
start/end time
exit code
output/evidence path
result
remaining blocker
```

## Final handoff format

End your response with:

1. concise verdict: `GO`, `NO-GO`, or `BLOCKED`;
2. exact files changed/created;
3. exact commands run and exit codes;
4. test counts and failures/skips;
5. reconciliation totals by match class;
6. whether any Qdrant/Redis/env/alias/deployment mutation occurred;
7. unresolved blockers with exact artifacts or human decisions needed;
8. recommended next action.

Do not claim 10/10 confidence merely because tests pass. A 10/10 review requires independent evidence, complete span coverage, fail-closed behavior, reproducibility, human safety/rights decisions, and honest limits on scale claims.

Begin with Phase 0 read-only inspection, then implement only Phase 1 unless the plan owner explicitly approves continuation.
