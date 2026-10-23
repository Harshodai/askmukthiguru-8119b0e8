Phase 2 is independently verified as PASS for B1 only.

The overall public-release verdict remains NO-GO.

Now prepare a safe, isolated local/staging user-testing environment and close the next engineering blockers. The goal is to let the owner test the experience without exposing unverified attribution publicly and without weakening any safety or provenance gate.

Do not deploy to Railway or production. Do not enable the public harness. Do not point the public `first_person` alias at any candidate collection.

## Confirmed Phase 2 facts

Phase 2 produced:

- 1,600 per-span ECAPA verdict rows;
- exact key equality with the 1,600 Phase-3 exact candidate spans;
- 0 quarantined spans included;
- all 1,137 Phase-3 quarantined spans excluded;
- 447 distinct audio files, all from `audio_archive/wavs/`;
- 1,600 successful audio slices;
- pinned SpeechBrain ECAPA model;
- independently regenerated calibration;
- 267 positive and 267 impostor calibration trials;
- 262 positive and 262 impostor held-out test trials;
- observed test FAR 0/262 and FRR 0/262;
- calibrated cosine floor `0.282826`;
- margin threshold `1e-06`;
- deterministic repeated outputs;
- no Qdrant, Redis, alias, environment, Docker, or deployment mutation.

## Important limits that must remain explicit

The 0/262 FAR and FRR are not human-certified public error rates because the trial labels derive from the same anchor-based speaker setup. Treat them as relative system-consistency evidence only.

Do not claim "human-verified teacher attribution" yet.

Also:

- 45 spans have video-to-teacher label conflicts and must be quarantined until reviewed.
- 1,127 spans are transcript/text variants and must not be admitted without an explicit owner decision.
- 10 spans remain unlocatable and must stay quarantined.
- B4 legacy/context schema separation remains open.
- B5 independent rights register remains open.
- B6 clinician review of the distress boundary remains open.
- B7 human speaker labels, human gold labels, and public-scale evidence remain open.

## Phase 0 — inspect and freeze again

Before making changes:

1. Re-read:
   - `AGENTS.md`
   - `lessons.md`
   - `docs/FIRST_PERSON_PUBLIC_RELEASE_STATUS_2026-10-21.md`
   - `.claude/tasks/first-person-v10-public-release-plan-2026-10-21.md`
   - `docs/FIRST_PERSON_V5_V10_COMPLETION_2026-10-21.md`
   - Phase 3 and Phase 2 evidence reports
   - `backend/scripts/ops/reconcile_v10_ecapa_verdicts.py`
   - `backend/scripts/ops/rebuild_v10_asr_coordinates.py`
   - `backend/scripts/ops/verify_speakers_ecapa.py`
   - `backend/scripts/ops/build_full_corpus_v10.py`
   - the first-person context store, harness, pipeline, bridge, and cache-fingerprint code

2. Record:
   - git status and all dirty/untracked files;
   - exact HEAD and origin;
   - active harness flag;
   - Qdrant collections, aliases, point counts, vector counts, and schemas;
   - Redis state without mutating it;
   - Docker image/container identity;
   - all current Phase-2 and Phase-3 artifact hashes.

3. Do not touch peer dirty files unless strictly required.

## Workstream A — independent rights register

Build or complete an independent rights/provenance manifest for the 1,600 exact candidate spans.

Do not derive it from Qdrant payload fields.

Each asset entry must include, where available:

- `source_asset_id`;
- video ID;
- canonical source URL;
- title;
- channel/rightsholder;
- permission or license basis;
- permitted use;
- attribution requirements;
- review date;
- evidence URL or document;
- evidence hash;
- owner review status;
- ambiguity/restriction reason.

Join the rights register to every candidate span.

Rules:

- missing rights evidence means quarantine;
- ambiguous rights means quarantine;
- payload `rights_cleared=true` is not independent evidence;
- do not mark anything rights-cleared merely because it appears in the old collection;
- preserve the original rights payload and clearly label it as untrusted/derived.

Produce:

- rights manifest;
- rights join report;
- quarantined-rights report;
- human-readable B5 report;
- exact counts by rights status.

If owner/legal confirmation is required, do not fabricate it. Mark the affected assets `pending_owner_review`.

## Workstream B — quarantine contradictory speaker labels

Create a deterministic quarantine/review artifact for all 45 `refused_guru_mismatch` spans.

For each mismatch include:

- source span ID;
- video ID;
- expected/video teacher;
- ECAPA predicted teacher;
- cosine and margin;
- audio window;
- audio file hash;
- model/calibration revision;
- transcript/source hash;
- reason code;
- recommended review action.

Do not silently relabel the video, the speaker, or the guru.

Create a review format that a human can inspect and approve or reject. Use audio playback references if the repository has a supported mechanism.

Do not admit these 45 spans to any user-testing collection until explicitly reviewed.

## Workstream C — define the testable corpus tiers

Create explicit corpus tiers:

1. `exact_verified_candidate`
   - only spans passing exact Phase-3 reconstruction;
   - only spans with Phase-2 per-span verdicts;
   - exclude all 45 speaker-label conflicts;
   - exclude all rights-pending assets;
   - exclude all variants and unlocatable spans.

2. `review_required`
   - the 45 speaker-label conflicts;
   - rights-pending spans;
   - any other human-review records.

3. `variant_candidate`
   - the 1,127 transcript/text variants;
   - never serve by default;
   - require a separate owner decision.

4. `unlocatable_quarantine`
   - the 10 spans not found in the authoritative artifact.

Produce exact counts and immutable manifests for every tier.

Do not call the first tier "public verified" until human speaker and rights review are complete. Use a name such as `local_review_candidate` or `automated_evidence_candidate`.

## Workstream D — separate legacy and context serving contracts

Fix B4 without breaking the safe path.

The legacy first-person store must not point at an fp-context-v1/v2 collection unless its schema is explicitly compatible.

Implement startup/configuration validation that fails closed when:

- legacy store points to an fp-context collection;
- context store points to a legacy-only collection;
- expected payload fields are absent;
- corpus version/schema version is incompatible;
- cache fingerprint omits collection, schema, corpus version, or evidence policy.

Keep:

```text
FIRST_PERSON_CONTEXT_HARNESS_ENABLED=false
```

for the normal/public path.

Do not repoint the public `first_person` alias.

## Workstream E — build a safe owner-only test mode

The owner needs to test the user experience, but this must be isolated from public serving.

Implement the smallest safe testing route or mode, using one of these approaches in priority order:

1. file-backed candidate preview that reads the immutable candidate manifests directly and does not mutate Qdrant; or
2. a disposable, explicitly named local Qdrant collection containing only the approved `local_review_candidate` tier, created only after a snapshot and a dry-run validation; or
3. a separate local-only test project/compose profile with an explicit test collection and test-only environment flag.

Do not use the production alias.

The test mode must:

- require an explicit local-only flag;
- refuse to start if the source manifest, verdict manifest, rights manifest, or schema contract is missing;
- serve only the exact candidate tier;
- exclude all 45 mismatches;
- exclude all rights-pending spans;
- exclude all 1,127 variants;
- exclude all 10 unlocatable spans;
- expose citations only when text hash, source span ID, audio window, speaker verdict, and rights status all pass;
- return an explicit "review candidate / not public release" label in the test UI or response metadata;
- log evidence policy, corpus version, collection, and manifest hashes;
- fail closed on stale or modified artifacts;
- never use LLM-authored teaching text in retrieval-only mode;
- preserve crisis and distress guardrails;
- make cross-guru and out-of-corpus queries abstain safely.

If a Qdrant collection is required, use a new versioned local collection name. Take a snapshot before any write. Do not create or modify the public alias. Verify point counts, payload schemas, hashes, and rollback before allowing test requests.

## Workstream F — owner-facing test protocol

Create a concise test guide for the owner covering:

- how to start the isolated local test mode;
- how to verify the environment is test-only;
- supported test queries;
- direct on-topic queries;
- cross-guru queries;
- multilingual queries;
- follow-up/context queries;
- out-of-corpus queries;
- prompt injection queries;
- distress and crisis queries;
- exact-cache hit/miss tests;
- audio citation playback checks;
- expected abstentions;
- how to collect a bug report with request ID, query, route, evidence policy, citation, and timestamp;
- how to shut down and roll back the test mode.

The test guide must clearly state:

- this is not public release;
- attribution is automated evidence, not human-certified;
- no sensitive user data should be entered;
- crisis situations must use professional/emergency support;
- test results must not be interpreted as clinical advice.

Use a no-LLM-authored-text retrieval-only test posture.

## Workstream G — required tests

Add focused tests for:

- legacy/context collection-schema mismatch;
- stale/missing manifest refusal;
- manifest hash mismatch;
- corpus-tier exclusion;
- 45 mismatch exclusion;
- rights-pending exclusion;
- variant exclusion;
- unlocatable exclusion;
- exact text/hash verification;
- speaker verdict source-span matching;
- audio window verification;
- cross-guru isolation;
- out-of-corpus abstention;
- distress/crisis routing;
- prompt-injection blocking;
- cache fingerprint scope;
- test-only flag refusal in production/public mode;
- no alias mutation;
- rollback of disposable test collection if used.

Run and record exact exit codes for:

- `py_compile`;
- focused tests;
- Phase-2 tests;
- Phase-3 tests;
- reconciliation tests;
- repository-layout tests;
- lint;
- full backend suite;
- local test-mode smoke matrix;
- deterministic manifest comparison;
- candidate tier validation.

## User-testing smoke matrix

Create a machine-readable and human-readable smoke matrix with at least:

1. direct on-topic query for each guru;
2. request explicitly naming each guru;
3. cross-guru request;
4. Hindi/Hinglish or another supported Indic query;
5. multi-span/context query;
6. follow-up query;
7. unrelated technical question;
8. prompt injection;
9. self-harm crisis;
10. harm-to-others intent;
11. moderate distress;
12. exact-cache hit;
13. stale-cache policy invalidation;
14. missing-artifact startup refusal;
15. stale-manifest refusal;
16. citation audio playback verification.

For every case record:

- route;
- test mode;
- answerability/abstain state;
- whether an LLM generated answer text;
- citation count;
- exact source text/hash match;
- source span ID;
- audio start/end;
- speaker verdict;
- rights status;
- corpus/schema version;
- evidence policy;
- latency;
- error status;
- expected versus observed result.

## Research requirements for the implementation report

Use and cite these authoritative sources:

- [NIST Speaker Recognition Evaluation](https://www.nist.gov/itl/iad/mig/speaker-recognition)
- [NIST OSAC Speaker Recognition Evaluation Metrics](https://www.nist.gov/video/osac-speaker-recognition-evaluation-metrics)
- [SRI trial-based calibration with a reject option](https://www.sri.com/wp-content/uploads/2021/12/toward_fail-safe_speaker_recognition_trial-based_calibration_with_a_reject_option.pdf)
- [Qdrant pre-migration baseline](https://qdrant.tech/documentation/migration-guidance/pre-migration-baseline/)
- [Qdrant migration fundamentals](https://qdrant.tech/documentation/faq/qdrant-fundamentals/)
- [WHO ethics and governance of AI for health](https://www.who.int/publications/i/item/9789240029200)
- [NIST AI RMF](https://www.nist.gov/itl/ai-risk-management-framework)
- [NVIDIA/Label Studio human audio-labeling workflow](https://developer.nvidia.com/blog/generating-high-quality-labels-for-speech-recognition-with-label-studio-and-nemo/)
- [Label Studio](https://github.com/HumanSignal/label-studio)
- [Speaker-verification score calibration toolkit](https://github.com/alumae/sv_score_calibration)

Do not treat web sources as proof that this repository is safe. Use them to justify design choices only. Repository evidence and human review remain authoritative.

## Stop conditions

Stop and report BLOCKED if:

- the test mode would be reachable through the public alias;
- the test mode cannot prove its manifest hashes;
- a candidate span lacks exact text/hash, audio, speaker verdict, or rights status;
- the 45 conflicts cannot be quarantined;
- the test mode would serve a variant or unlocatable span;
- the system would expose unreviewed attribution as public fact;
- a clinician/rights decision is required but unavailable;
- any Qdrant write would occur without snapshot, dry-run, isolated collection, and rollback evidence.

## Required deliverables

Create:

1. independent rights manifest and report;
2. 45-span speaker-conflict review package;
3. explicit corpus-tier manifests;
4. B4 schema-isolation implementation and tests;
5. owner-only isolated test mode or file-backed preview;
6. owner testing guide;
7. machine-readable smoke matrix;
8. human-readable Phase 4/5 evidence report;
9. updated remediation plan with exact commands, exit codes, hashes, and blockers.

## Final response format

End with:

1. Overall verdict: `GO`, `NO-GO`, or `BLOCKED`.
2. Phase 4 verdict.
3. Phase 5 verdict.
4. Whether owner-only testing is available.
5. Exact local start/test commands.
6. Exact files created/modified.
7. Test counts and failures.
8. Corpus-tier counts.
9. Rights status counts.
10. Speaker-conflict counts.
11. Smoke-matrix results.
12. Explicit mutation statement.
13. Remaining blockers:
    - human speaker-label certification;
    - B5 rights owner confirmation;
    - B6 clinician review;
    - B7 human gold labels;
    - 1,127 variant-tier decision;
    - public-scale evidence.
14. Exact next approval required.

Do not claim "ready for everyone" or public release after this work. The intended outcome is:

- safe owner-only local testing is available;
- public harness remains disabled;
- public alias remains unchanged;
- all unreviewed evidence is clearly labeled;
- every remaining human and production gate is explicit.
