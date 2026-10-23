# Agent Handoff Prompt — First-Person v5/v10 End-to-End Completion

You are taking over the AskMukthiGuru repository on the user’s macOS device. Execute the current first-person continuation plan ruthlessly, but preserve safety and evidence boundaries. Your work will be reviewed end to end by another agent.

## Repository and environment

- Repository: `Harshodai/askmukthiguru-8119b0e8`
- Workspace: `/Users/harshodaikolluru/Public/askmukthiguru-8119b0e8`
- Active device: user macOS desktop; Docker is installed at `/Users/harshodaikolluru/.docker/bin/docker`.
- Use repository Makefile commands where possible. If invoking Docker directly, prepend:

```bash
export PATH="/Users/harshodaikolluru/.docker/bin:$PATH"
```

- Do not switch devices.
- Do not reset, clean, checkout another branch, overwrite, or discard existing dirty work.
- Do not commit or push unless explicitly requested.
- Railway is paused. Do not deploy to Railway.

## Mandatory reading before action

Read these first:

1. `/Users/harshodaikolluru/Public/askmukthiguru-8119b0e8/AGENTS.md`
2. `lessons.md`, especially entries beginning `L-FP-`, `L-CONTEXT-`, `L-QDRANT-`, `L-DEPLOY-`, `L-VERIFY-`, `L-MATRIX-`, and `L-REPLICATE-`.
3. `.claude/tasks/first-person-v5-end-to-end-continuation-2026-10-21.md`
4. `docs/FIRST_PERSON_CONTEXT_HARNESS_PHASE_A_2026-10-20.md`
5. `docs/FIRST_PERSON_CONTEXT_HARNESS_PHASE_C_2026-10-20.md`
6. `docs/FIRST_PERSON_COLLECTION_EVOLUTION_V1_TO_V10.md`
7. `docs/plans/core-safe-program-board.md`
8. `docs/plans/MASTER_PLAN_FP_ROUTING_PROFILE_2026-10-17.md`
9. `docs/PRODUCTION_READINESS_CHECKLIST.md`
10. Current v10 readiness/provenance artifacts under `audits/evidence/` and current continuation/build plans under `.claude/tasks/`.

Before broad code exploration, use the repository’s code-review graph MCP tools if available: architecture overview, changed-node detection, impact radius, affected flows, and tests-for relationships. Use bounded file reads only where graph coverage is insufficient.

## Prior shared task history — authoritative context

Two prior shared tasks were read end to end:

- `HOjROlgd5b3mr2NB5PZ7ZI` — “Complete First Person v5 Pipeline Readiness and Scalability Review”
- `BBYLD9UwzYhmByrF7Z3Ow4` — “Assess First Person v5 Pipeline Production Readiness and Scalability”

Do not assume their claims are current. Reconcile every claim against the current checkout and live Docker/Qdrant state.

### What those tasks established

1. The first-person mode mismatch was fixed:
   - default must be `retrieval_only`;
   - allowed modes are exactly `disabled`, `retrieval_only`, `hybrid`;
   - `editorial` is not an allowed serving mode;
   - local/deployment env pins must be explicit;
   - hybrid is explicit opt-in only.

2. A strict fp-context contract/store/harness was implemented:
   - deterministic IDs;
   - strict payload models with `extra="forbid"`;
   - guru/parent isolation;
   - speaker, rights, hash, boundary, completeness, citation/audio gates;
   - deterministic answer reconstruction from stored span text only;
   - no LLM-authored teaching answer text;
   - bounded selector/metrics/trace support;
   - red-team tests.

3. A v10 candidate was built from archived audio/transcription artifacts. Earlier review measured:
   - 4,197 total points;
   - 2,737 retrieval-child points;
   - 1,460 parent points;
   - initial provenance gap on `asr_engine` / `asr_model_version`;
   - later task history reported existing mass-ingest artifacts covering all 2,737 children with Parakeet `parakeet-tdt-0.6b-v3`, deterministic run IDs, and aligned windows.

4. The later task reported additive enrichment of the local v10 child payloads, strict in-image validation of `181 passed, 1 skipped`, successful parent hydration, and attempted local harness enablement. Credit ended before final post-enable health, live correctness, load, metrics, and rollback proof.

These are historical claims only. Verify them independently now.

## Hard safety and integrity invariants

- Never default missing `speaker_verified` to `true`.
- Never invent or infer ASR engine, ASR model, transcription run ID, word timings, rights clearance, speaker identity, guru identity, or citation offsets.
- Never serve a span whose required provenance or integrity evidence is missing.
- First-person answer text must be deterministic stored source-span text in retrieval-only mode. No paraphrase, connective teaching prose, invented affirmation, or LLM-generated doctrine.
- Every citation must match source span ID, exact text, source URL, guru, parent, and audio offsets.
- Never use OKF, graph content, prompts, memory state, or system labels as teacher speech.
- Crisis/self-harm guardrails run before first-person retrieval and must not be bypassed by provider or circuit-breaker failures.
- Fail closed on mixed-guru/mixed-parent, unverified speaker, rights failure, hash mismatch, boundary failure, citation/audio mismatch, prompt injection, or malformed candidate data.
- Do not use global Redis `FLUSHALL`.
- Do not mutate Neo4j/Memgraph schema, enable mutable model downloads, widen graph concurrency, or change thresholds without held-out evidence.
- Do not claim production readiness from static compilation, a green health endpoint, an exact-text benchmark, or a local average latency number.

## Required execution sequence

### Phase 0 — Read-only reconciliation

Record before mutation:

- `git status --short --branch`, HEAD, origin, and complete dirty/untracked inventory;
- byte-level hashes of relevant dirty first-person files;
- Docker context/containers/images;
- active env values, especially `FIRST_PERSON_CONTEXT_HARNESS_ENABLED`, `FIRST_PERSON_COLLECTION`, `FIRST_PERSON_MODE`, and score thresholds;
- Qdrant collections, aliases, point counts, vector schemas, and payload field counts;
- current readiness/provenance reports and candidate manifests;
- current backend logs and health responses.

Write a machine-readable state report and a concise reconciliation markdown report. Do not mutate source, Qdrant, aliases, or env in Phase 0.

### Phase 1 — Preflight and candidate audits

Run the real production-env validator from supported invocation locations. Run the current v10 readiness auditor and provenance join against the actual collection. Verify every parent/child field, strict schema, text hash, source-span identity, guru/parent isolation, rights, boundary/completeness, audio offsets, ASR engine/model, speaker evidence, and source manifest coverage.

Run the deterministic builder twice and compare manifests byte-for-byte. Any unexplained point, missing provenance, fabricated value, structural defect, or non-deterministic result is a no-go.

### Phase 2 — Code contracts and tests

Trace API → bridge → first-person pipeline → context store/harness → citation/audio projection → cache fingerprint.

Verify:

- harness remains default-off until gates pass;
- local env value is known and intentional;
- cache fingerprint includes all answer-shaping harness policy fields;
- retrieval-only cannot invoke LLM-authored teaching text;
- hybrid remains explicit opt-in;
- cross-guru, cross-parent, speaker, rights, hash, boundary, citation/audio, prompt-injection, OKF/system-point, selector, and cache-corruption gates work;
- tests pin env-sensitive flags instead of inheriting `.env`.

Run focused in-container suites, then full backend tests with collection errors visible, frontend tests/typecheck, lint/format, compile checks, repository layout/parity checks, and `git diff --check`. Capture true command exit codes; do not pipe to `tail` without `pipefail`.

Fix only confirmed defects. Keep diffs minimal. Add regression tests for every fix.

### Phase 3 — Runtime proof

Build affected Docker images using the prescribed Docker path. Prove running code identity using image creation metadata, in-container file hashes/content markers, and intended source baseline. Recreate only affected services without volume purges.

Verify:

- `/api/health` and detailed health;
- startup posture and logs;
- collection/alias target;
- harness flag inside container;
- mode and provider posture;
- no unexpected warnings/errors.

If collection changes are necessary, snapshot first and apply only additive, validated local changes. Read back and re-audit. Retain rollback metadata. Never touch Railway.

### Phase 4 — Live safety/correctness matrix

Run a throttled local matrix covering:

- direct on-topic queries for each guru;
- multi-span/context/coreference queries;
- follow-ups;
- multilingual/Indic inputs;
- out-of-corpus controls;
- related-not-direct and ambiguous inputs;
- prompt injection in source text;
- cross-guru and cross-tenant isolation;
- distress/self-harm/crisis controls;
- exact-cache hit and cache policy invalidation;
- Qdrant, Redis, provider, and worker timeout/degraded paths.

Record for each response: route, answerability, model-used, exact text/hash result, citations, audio offsets, guru/speaker/rights fields, abstain stage/reason, latency, and errors. Any hallucinated/paraphrased teacher text, OOC leak, citation/audio mismatch, crisis bypass, unverified speaker, cross-guru leak, or unexplained 5xx is a no-go.

### Phase 5 — Load, scalability, rollback

Run the existing readiness/load gate against its real report schema. Fix gate adapters if they crash instead of evaluating reports. Run bounded warm/cold concurrency tests for exact-cache hit/miss, retrieval, harness, and provider-disabled paths.

Measure success rate, p50/p95/p99 latency, Qdrant/Redis/CPU/memory, queue behavior, and cost proxies. Test graceful degradation. Create/verify a Qdrant snapshot and exercise restore into a disposable local target where possible. Verify alias switch and rollback, then return to intended state.

Do not claim 1,000+ QPS or production scalability from a small local run. Report measured envelope.

### Phase 6 — Enable local harness only after all gates pass

If and only if Phases 1–5 pass:

1. Set `FIRST_PERSON_CONTEXT_HARNESS_ENABLED=true` only in local project env.
2. Recreate backend so `env_file` is reread.
3. Verify flag inside container.
4. Repeat health, focused tests, live matrix, cache fingerprint checks, and a short soak.
5. Confirm harness metrics/counters are emitted and bounded.
6. Disable flag and recreate backend to prove rollback to safe prior path.
7. Update plan, lessons, docs, and evidence with exact outcomes.

If any gate fails, keep harness disabled and document the blocker. Do not weaken thresholds or delete failing tests.

## Deliverables required before handoff

Create or update:

- Phase 0 state/reconciliation report;
- machine-readable readiness/provenance reports;
- test and live-matrix evidence;
- load/rollback evidence;
- updated continuation plan with completed and blocked items;
- applicable `lessons.md`, README/docs/checklist updates;
- final status report separating:
  - verified complete;
  - fixed during this run;
  - blocked by missing artifacts;
  - blocked by human rights/gold-label/clinician/product sign-off;
  - not run due to environment limits.

Do not commit or push. Leave worktree state explicit. Before finishing, run repository hygiene and prune only temporary worktrees created by you.

## Handoff format to reviewer

End with:

1. Exact current HEAD and dirty-file summary.
2. Exact local collection and alias state.
3. Harness flag before and after.
4. Commands run and true exit codes.
5. Test counts and skips.
6. Live correctness/safety results.
7. Load p50/p95/p99, success rate, resource observations.
8. Snapshot/restore/rollback result.
9. Every remaining blocker with the exact artifact or decision needed.
10. Links to all generated evidence files.

Be ruthless about evidence. “Health 200,” “exact text matched,” or “benchmark passed” is not sufficient proof by itself.
