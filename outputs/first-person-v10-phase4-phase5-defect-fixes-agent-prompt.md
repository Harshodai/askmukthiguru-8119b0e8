Phase 4/5 is accepted as engineering progress, but the overall verdict remains NO-GO.

Before any owner sign-off, fix the two misleading evidence defects and the deterministic-ID collision identified in the latest verification report. Then rebuild the local container so the owner-only preview route is actually available for testing.

Do not enable the public harness. Do not change the public first_person alias. Do not deploy to Railway or production. Do not write to Qdrant unless separately authorized after a snapshot, isolated collection plan, dry-run, validation, and rollback plan.

## Current verified facts

- Overall release: NO-GO.
- Phase 4: PARTIAL. Rights register exists but owner confirmation is pending.
- Phase 5: engineering PASS, release NO-GO.
- Owner-only file-backed preview is logically isolated:
  - production + flag on refuses;
  - local + flag on allows;
  - local + flag off refuses;
  - default local-review flag is false.
- The running container is stale and does not contain the new preview route; it currently returns HTTP 404 for that route.
- Public first-person route remains safe/abstaining with zero citations.
- Exact candidate tier: 1,529 spans.
- Review-required tier: 71 spans.
- Exact Phase-3 candidate total: 1,600 spans.
- All 45 speaker conflicts are excluded from the served tier.
- Variant candidate count: 1,126 distinct rebuilt IDs, but the source set contains 1,127 variant rows.
- Unlocatable quarantine count: 10.
- Rights register contains 751 assets and is independently based on `CONTENT-RIGHTS.md`, but owner sign-off is pending.
- Smoke matrix: 19/19 passed with no LLM-generated answer text.
- Full backend suite: 10,858 passed, 25 skipped, 2 deselected, 3 xfailed, 0 failed.
- No Qdrant, Redis, alias, environment, Docker, git, or deployment mutation occurred in the prior work.

## Required reading

Before editing:

- `AGENTS.md`
- `lessons.md`
- `docs/FIRST_PERSON_PUBLIC_RELEASE_STATUS_2026-10-21.md`
- `.claude/tasks/first-person-v10-public-release-plan-2026-10-21.md`
- `docs/FIRST_PERSON_V5_V10_COMPLETION_2026-10-21.md`
- the latest Phase 4/5 evidence report
- the latest Phase 2 and Phase 3 reports
- the rights register and rights join report
- the speaker-conflict packet
- the tier manifests
- the local review preview implementation and route
- the current Docker Compose configuration

Inspect every relevant directory-level `AGENTS.md`. Preserve unrelated dirty work.

## Defect 1 — correct the speaker-conflict packet duration field

The 45-row speaker-conflict packet currently stores the slice width in a field named `audio_duration_ms`.

Example:

- window: `172540 → 183020 ms`;
- packet currently says `audio_duration_ms: 10480`;
- Phase-2 verdict says the actual file duration is `214692`;
- the slice duration is `10480`.

This is misleading to a human reviewer.

Fix the schema so it explicitly distinguishes:

```text
audio_file_duration_ms
audio_slice_duration_ms
audio_start_ms
audio_end_ms
```

If the complete file duration is available, include it. Otherwise use a clearly named field that cannot be confused with the WAV duration.

Requirements:

- update the packet generator;
- update the packet schema;
- update all 45 rows;
- add a migration/compatibility note if old artifacts are retained;
- add tests proving file duration and slice duration are not confused;
- re-run the bounds check and prove 0/45 windows are out of bounds;
- make the report explicitly state that the previous field name was misleading and has been corrected.

Do not silently overwrite the prior artifact. Write a versioned corrected artifact and retain hashes for both old and corrected artifacts.

## Defect 2 — repair unlocatable quarantine identity

All 10 `unlocatable_quarantine` rows currently have empty `source_span_id`. Some share the same `(video_id, guru_id)`, so that pair is not unique.

Trace these rows back to the Phase-3 input and authoritative ASR/source manifests.

For each row, do one of the following:

1. recover the exact live/source identity and record it; or
2. if the span truly cannot be identified, assign a deterministic quarantine record ID derived from all available evidence and explicitly mark:
   - `source_span_id: null`;
   - `quarantine_record_id`;
   - `identity_status: unresolved`;
   - `identity_resolution_reason`;
   - all available video/guru/artifact references;
   - source row number or input record hash.

Do not invent a source span ID.

Requirements:

- every quarantine row must have a unique immutable quarantine record ID;
- duplicate `(video_id, guru_id)` rows must remain distinguishable;
- tests must prove row uniqueness and stable IDs;
- update the quarantine report and tier manifest;
- explain whether these 10 records correspond to known live spans or are genuinely unlocatable.

## Defect 3 — surface and isolate the deterministic-ID collision

The prior wording about a "byte-identical duplicate" was incorrect.

The actual issue is:

- 1,127 variant rows;
- only 1,126 distinct rebuilt IDs;
- two different live spans collide on rebuilt ID `b7d1c4a06dccace5…`;
- the live spans are `3c4862e8…` and `8a330f28…`;
- both are from video `MmiI3xo5Ju4`;
- the current variant tier keeps one row and hides the collision.

This must be treated as a real identity defect.

Fix the builder and validation path so a collision can never be absorbed.

Requirements:

- preserve both source/live span IDs;
- emit a dedicated collision record containing all colliding inputs;
- quarantine every member of a deterministic-ID collision;
- do not keep one silently;
- make the variant manifest one-row-per-source-span, not one-row-per-rebuilt-ID;
- add collision counts to every summary;
- add tests for two distinct source spans producing the same rebuilt ID;
- determine whether the collision is caused by an incomplete ID namespace, incorrect normalization, insufficient coordinates, or an input artifact conflict;
- propose and implement the smallest safe namespace/version fix only if it can be proven backward-compatible;
- otherwise mark the collision as unresolved and keep both spans out of any serving tier.

Do not change existing live IDs in Qdrant.

## Recompute and verify all tier counts

After these fixes, recompute and report:

- exact candidate tier;
- review-required tier;
- variant tier;
- unlocatable quarantine;
- deterministic-ID collision quarantine;
- rights-pending count;
- speaker-conflict count;
- total unique source/live span IDs;
- total output rows;
- duplicate IDs by every identity level.

The arithmetic must reconcile without hiding collisions.

## Rebuild the local owner-only test environment

The file-backed preview is logically isolated, but the running Docker container predates the route change.

Use the repository-prescribed Docker path and rebuild/recreate only the affected local backend service. Do not purge volumes.

Before recreation, record:

- current image/container ID;
- current image hash;
- container start time;
- harness flag;
- local-review flag;
- Qdrant collection and alias state;
- Redis state;
- Docker volume list.

Then:

1. rebuild the local backend image through the prescribed repository command;
2. recreate only the local backend service;
3. verify the route exists inside the container;
4. verify the route is inaccessible/refuses in production mode;
5. verify local-review mode requires the explicit flag;
6. verify the normal public route remains unchanged and abstains;
7. verify no Qdrant write or alias change occurred;
8. verify no Redis mutation occurred;
9. verify container health and code identity;
10. record all image/container hashes and command exit codes.

Do not create a Qdrant test collection yet unless separately authorized. Continue using the file-backed preview because it is currently the safest user-test path.

## Improve the owner-only test experience

The owner-only preview must visibly and consistently label every response as:

```text
REVIEW CANDIDATE — NOT PUBLIC RELEASE
AUTOMATED EVIDENCE — NOT HUMAN-CERTIFIED ATTRIBUTION
```

Ensure this label appears in:

- CLI output;
- structured response metadata;
- any local UI/preview response;
- citation metadata;
- owner testing documentation.

The preview must continue to:

- use only the exact local-review candidate tier;
- exclude the 45 conflicts;
- exclude rights-pending assets;
- exclude variants;
- exclude unlocatable rows;
- use no LLM-authored teaching text;
- preserve crisis, distress, harm, prompt-injection, cross-guru, and out-of-corpus safeguards;
- fail closed on missing or stale manifest hashes.

## Produce owner decision packets

Create concise sign-off packets for the owner. Do not mark them approved yourself.

### Rights packet

Include:

- rights register hash;
- asset count;
- candidate asset count;
- confirmed/pending/rejected counts;
- source URL and permission evidence per asset;
- owner decision field;
- explicit statement that payload flags are not evidence;
- signature/date fields.

### Speaker packet

Include:

- corrected 45-conflict packet;
- all score/calibration/model/audio hashes;
- corrected file-duration and slice-duration fields;
- explicit statement that current FAR/FRR is relative automated evidence, not human-certified public attribution;
- per-row owner decision field;
- signature/date fields.

### Variant decision packet

Include:

- 1,127 original variant rows;
- 1,126 distinct rebuilt IDs;
- the collision record;
- choices:
  - rebuild source text/timing from a single voted layer;
  - retain as non-serving review variants;
  - exclude permanently;
- owner decision field.

### Clinician packet

Include:

- observed distress-classifier gap;
- current crisis/harm behavior;
- exact affected test cases;
- proposed behavior options;
- explicit statement that the agent must not tune the boundary without clinician review;
- clinician decision field;
- signature/date fields.

### Gold-label packet

Include:

- required human speaker labels;
- remaining human gold-label count;
- annotation instructions;
- recommended audio review workflow;
- agreement fields;
- reviewer identity/date fields.

Use a supported human audio-labeling workflow if already available. Do not require the owner to guess which field means file duration versus slice duration.

## Required tests and evidence

Run exact exit codes for:

- packet schema tests;
- quarantine identity tests;
- collision tests;
- tier reconciliation;
- local preview tests;
- serving-contract tests;
- Phase-2 regression tests;
- Phase-3 regression tests;
- reconciliation tests;
- repository-layout tests;
- lint;
- full backend suite;
- local Docker rebuild;
- container route smoke tests;
- owner-only 19-case smoke matrix;
- public-route safety smoke matrix;
- stale-manifest refusal;
- production-mode refusal.

Capture:

- before/after file hashes;
- Docker image/container identity;
- Qdrant collection/alias state;
- Redis mutation status;
- harness/local-review flags;
- exact artifact paths.

## Public-readiness rule

Do not claim "ready for everyone" after this work.

The target result is:

- owner-only testing works in the rebuilt local container;
- evidence artifacts no longer mislead reviewers;
- deterministic-ID collisions are visible and quarantined;
- no unreviewed speaker attribution is served;
- no rights-pending asset is served;
- public harness remains disabled;
- public alias remains unchanged;
- owner sign-off packets are ready.

Public release remains blocked until the owner provides:

1. rights-register approval;
2. speaker-conflict decisions and human speaker-label certification;
3. variant-tier decision;
4. clinician safety decision;
5. human gold-label review;
6. final staging/production authorization.

End with:

1. Overall verdict: GO, NO-GO, or BLOCKED.
2. Phase 4 verdict.
3. Phase 5 verdict.
4. Whether the rebuilt owner-only test route works inside Docker.
5. Exact owner test commands.
6. Exact files created/modified.
7. Updated tier counts and collision counts.
8. Corrected packet hashes.
9. Test counts and failures.
10. Docker/Qdrant/Redis/env mutation statement.
11. Remaining owner decisions.
12. Exact next approval required.
