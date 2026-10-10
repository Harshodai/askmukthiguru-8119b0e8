# Claude Code Handoff: Full Production Readiness, Faculty Preview, and Public User Readiness

**Date:** 2026-10-11  
**Repository:** `Harshodai/askmukthiguru-8119b0e8`  
**Working directory:** `/Users/harshodaikolluru/Public/askmukthiguru-8119b0e8`  
**Target branch:** `main`  
**Current `main` / `origin/main`:** `a8843b71d79c671af851673bcbde8e02ca317af4`  
**Operating mode:** Local Mac Docker stack, current main checkout  
**Release posture at handoff:** **NO-GO until all pending evidence gates below are completed**

---

## 1. Purpose

This document is a complete handoff for Claude Code. It contains:

1. the repository and runtime context;
2. the work already performed by Manus;
3. the evidence that is actually verified;
4. the conflicts between repository release documents and fresh live evidence;
5. the exact remaining implementation and validation tasks;
6. the faculty-preview and public-user release criteria;
7. a copy-paste prompt for Claude Code.

Do not treat historical documents claiming “100% green” as current proof. Re-run the gates against the current working tree and current Docker runtime.

---

## 2. Non-negotiable operating rules

### Preserve the user’s work

- Do **not** reset, clean, stash, revert, checkout another branch, or overwrite the working tree.
- Do **not** delete `.work/`, existing reports, untracked files, or user-authored changes.
- `main` and `origin/main` are synchronized at the commit listed above.
- The current working tree contains intentional user changes and Manus audit changes. Classify them before editing.
- Do not commit or push unless explicitly authorized.

### Repository invariants

Read these before modifying code:

- `/Users/harshodaikolluru/Public/askmukthiguru-8119b0e8/AGENTS.md`
- `backend/CLAUDE.md`
- `src/CLAUDE.md`
- `lessons.md`
- `docs/architecture/first-person-path-to-prod.md`
- `docs/audits/manus-ruthless-audit-prompt-2026-10-05.md`
- `docs/audits/PROD_READINESS_PENDING_LIST_V9.md`
- `docs/audits/release-certification-2026-10-05.md`

Apply **SOLID, DRY, YAGNI, and KISS**. Prefer a small, canonical fix over duplicated special cases.

### Safety and data rules

- Never run Redis `FLUSHALL` for routine cache maintenance.
- Use the repository’s targeted cache commands only.
- Do not modify Qdrant, Memgraph/Neo4j, OKF, or ingestion data without the repository’s dry-run → snapshot → explicit-apply process.
- Do not use production secrets or print credentials.
- Do not present local Docker evidence as Railway/production evidence.
- Never claim a test passed if it exited with code 5, timed out, was skipped, or was not actually run.

---

## 3. Current repository and runtime state

### Git state

- Branch: `main`
- `main == origin/main`: `a8843b71d79c671af851673bcbde8e02ca317af4`
- Working tree is not clean.
- Existing modifications include backend configuration, Docker configuration, first-person pipeline/store/indexing, grounding, generation, verification, telemetry, tests, frontend first-person UI/service work, `lessons.md`, and audit artifacts.
- Untracked work includes `.work/`, readiness documents, and quality scripts.

Start every session with:

```bash
git status --short --branch
git rev-parse HEAD
git rev-parse origin/main
git diff --stat
git diff --name-only
```

### Docker state observed

The local stack was healthy during the latest audit:

- `mukthiguru-backend` — healthy, port `8000`
- `mukthiguru-frontend` — healthy, port `80`
- Redis — healthy, port `6379`
- Qdrant — healthy, ports `6333–6334`
- Memgraph — healthy, port `7687`
- Prometheus, Grafana, Jaeger, Alertmanager, watchdog, and autoheal were running.

Latest `/api/health` reported:

- `ready=true`
- `status=healthy`
- Qdrant ready
- Redis ready
- Memgraph/Neo4j ready
- LLM ready
- embedding ready with dimension `1024`
- runtime artifacts complete
- fast/standard/deep graph spines present
- exact and semantic caches healthy

Docker instructions from `AGENTS.md`:

```bash
export PATH="/Users/harshodaikolluru/.docker/bin:$PATH"
```

Prefer repository Makefile targets where available.

### Cache evidence

The targeted cache procedure was executed successfully:

```bash
make flush-cache
make verify-cache-empty
```

The procedure recreated the Qdrant semantic-cache collections and removed only the intended Redis query-cache namespaces. It preserved sessions, quotas, telemetry, queues, and user-memory namespaces.

Important: the frontend browser `localStorage` response cache is separate. If browser UI evidence is required, clear only the relevant browser keys through the documented UI/devtools procedure.

---

## 4. Evidence already verified by Manus

### Targeted code and regression tests

- Verification/grounding regression suite: **26 passed**.
- Focused production/safety/readiness suite: **145 passed**.
- Static compilation of touched backend modules: passed.
- `git diff --check`: passed after removing trailing blank lines.
- Docker health check: passed.
- Cache flush and cache-empty verification: passed.

The focused 145-test command was:

```bash
backend/.venv/bin/pytest -q \
  backend/tests/test_manus_scenarios_e2e.py \
  backend/tests/test_release_failure_injection_2026_10_05.py \
  backend/tests/test_ruthless_audit_remediation.py \
  backend/tests/test_guardrails_safety_audit.py \
  backend/tests/test_first_person_release.py \
  backend/tests/test_audit_first_person_boundaries.py \
  backend/tests/test_corpus_release_registry.py \
  backend/tests/test_readiness_gate.py
```

### Full-suite status

The full backend suite was attempted:

```bash
backend/.venv/bin/pytest -q
```

It exited with **code 5** and did not provide a useful terminal diagnostic. This is **not a pass**. Diagnose and rerun it.

The frontend suite was attempted multiple times. One run stalled/timed out under parallelism. A single-worker Vitest run was started but did not produce a completed result before the session interruption. Do not mark frontend readiness green until Vitest, typecheck, and build each have captured successful terminal results.

### Existing repository claims

`docs/audits/PROD_READINESS_PENDING_LIST_V9.md` claims **FACULTY-READY GO**, including 809 frontend tests and green clean-Docker evidence.

`docs/audits/release-certification-2026-10-05.md` also claims a later **FACULTY-READY GO**.

Those documents are valuable historical evidence, but they conflict with fresh live evidence from the current working tree. Claude Code must reconcile them rather than blindly repeat them.

---

## 5. Fresh live scenario evidence before the latest patches

The four exact seeker questions were run with a fresh signed anonymous session after a targeted cache flush.

The probe script is:

```text
.work/live-audit/run_scenarios.py
```

Questions:

1. `What is the root cause of human suffering, and how do two states of being determine our daily life?`
2. `How can I heal from self-judgment and the inner wall of defense in my relationships?`
3. `Guide me in a meditation to calm the wandering mind and experience inner stillness.`
4. `How does the wisdom of Ekam view the difference between detachment and living in a beautiful state?`

### S1 — root cause and two states

Observed:

- Substantive answer returned.
- `grounding_state=grounded`.
- `verification_passed=true`.
- `faithfulness_score=1.0`.
- Public `citations_verified=null`.
- Sources had `speaker_verified=false` or unknown speaker labels.
- Timestamps were absent.

Risk:

The thematic answer may be useful, but faculty users cannot reliably distinguish verified teacher teaching from an unverified retrieved synthesis.

### S2 — relationships, self-judgment, and defense wall

Observed:

- `grounding_state=abstained`.
- `verification_passed=false`.
- `faithfulness_score=0.0`.
- Returned a source-only partial/excerpt response.
- The response was safer than shipping unsupported prose, but it did not fully answer the practical question.

Risk:

The system is honest but incomplete. It needs either a genuinely supported practical sequence or a better-labelled partial answer with an explicit next step.

### S3 — meditation

Observed:

- Fast, coherent meditation response.
- Five practical steps.
- Stop condition for dizziness, panic, or discomfort.
- Serene Mind recording cited.
- `grounding_state=grounded`.
- `verification_passed=true`.
- Public `citations_verified=null`.

Risk:

The content is promising, but the public metadata contract is incomplete and source attribution is not yet fully verified.

### S4 — Ekam, detachment, and Beautiful State

Observed:

- Conservative refusal: the system could not answer from the held teachings.
- `grounding_state=abstained`.
- `verification_passed=false`.
- Irrelevant citations were still attached to the refusal envelope.

Risk:

The response text was conservative, but the UI could show unrelated references beside a refusal, misleading the user.

---

## 6. Changes already made during this readiness pass

These changes are in the working tree and must be preserved/reviewed:

### `backend/rag/nodes/verification.py`

Added fail-closed logic so a gateway result without claim-level evidence cannot override local claims marked `supported=False`.

### `backend/app/grounding.py`

Changed grounding-state derivation so missing citation verification is not promoted to `grounded`. Explicit nested verification is accepted only when the verification result is not explicitly failed. Existing grounded-partial evidence remains a deliberate exception because it is deterministic source-only content.

### `backend/app/api/chat.py`

Added public propagation of:

- `citations_verified`
- `orphan_citations_stripped`

### `backend/app/orchestrator.py`

Added the same fields to the queued response serializer.

### `backend/rag/nodes/generation.py`

A bounded max-retry refusal now returns an empty public citation list. Internal evidence remains available through verification/telemetry, but it is not presented as support for the refusal.

### Tests

Added regressions for:

- gateway pass cannot override unsupported local claims;
- missing citation verification cannot promote to grounded.

Re-run all affected tests after any further edits.

---

## 7. Current pending work: implementation task list

### P0 — public contract and release integrity

- [ ] Confirm direct `/api/chat` returns `citations_verified` correctly.
- [ ] Confirm queued `/api/chat` returns `citations_verified` correctly.
- [ ] Confirm SSE final/done payloads preserve the same field.
- [ ] Confirm `orphan_citations_stripped` is consistent across all paths.
- [ ] Confirm `grounding_state`, `verification.passed`, and `citations_verified` never contradict each other.
- [ ] Confirm bounded refusals expose zero public citations unless the citation directly supports the refusal itself.
- [ ] Add/execute serializer tests for direct, queued, and stream paths.

### P0 — answer acceptance and hallucination prevention

- [ ] Trace every path that can return `final_answer`.
- [ ] Verify every terminal path returns `verification.passed`, `verification.method`, and `verification.citations_verified`.
- [ ] Ensure a failed verification cannot ship the original generated substantive answer.
- [ ] Ensure local unsupported claims cannot be overridden by gateway/CoVe output lacking claim evidence.
- [ ] Test provider timeout, provider graceful-degradation strings, empty verification, and malformed verification.
- [ ] Test one unsupported claim mixed with supported claims.
- [ ] Test unsupported promises, medical claims, therapeutic claims, and metaphysical certainty.

### P0 — provenance and teacher attribution

- [ ] Trace `teacher_id`, raw `speaker`, display name, `speaker_verified`, transcript source, and citation mapping end to end.
- [ ] Never infer teacher identity from text alone.
- [ ] Never display `Unknown Channel`, `Unknown`, or unverified metadata as a teacher name.
- [ ] Never set `speakerVerified=true` by default in the frontend mapper.
- [ ] Preserve `speaker_verified=false` publicly.
- [ ] Add timestamps only when the source payload contains a real timestamp.
- [ ] Never fabricate `0:00` or a default timestamp.
- [ ] Distinguish direct excerpt, verbatim quote, retrieved excerpt, model synthesis, and general guidance.
- [ ] Validate the exact YouTube title, channel, transcript, speaker, and timestamp for every scenario citation.

### P1 — Scenario completeness

- [ ] S1 must explain root cause and both states without unsupported universal claims.
- [ ] S2 must provide supported inner-observation/relationship steps or clearly explain that the corpus evidence is insufficient.
- [ ] S3 must retain the actionable meditation, stop condition, and recording source without promising outcomes.
- [ ] S4 must either provide a supported define-and-contrast answer or an honest absence-of-term explanation—not unrelated excerpts.
- [ ] Every scenario must answer the user’s actual question before offering reflection or follow-up.

### P1 — first-person / QuoteWeaver

- [ ] Test first-person answers with verified speaker clips.
- [ ] Test mixed-speaker retrieval.
- [ ] Test unverified speaker metadata.
- [ ] Test ASR head fragments, tail fragments, promise clips, and incomplete clips.
- [ ] Test quote hash, token overlap, verbatim text, and citation-footnote gates.
- [ ] Confirm first-person mode never impersonates a teacher.
- [ ] Confirm teacher display-name mapping is deterministic and source/voice based.
- [ ] Test multilingual first-person outputs.

### P1 — safety

- [ ] Run deterministic acute self-harm tests across supported scripts.
- [ ] Run indirect/passive ideation tests.
- [ ] Run abuse, coercion, and unsafe relationship tests.
- [ ] Run meditation panic/destabilization tests.
- [ ] Run addiction and medical-overreach tests.
- [ ] Confirm safety redirects never become grounded teaching answers.
- [ ] Confirm crisis responses contain verified helplines only.
- [ ] Confirm provider failure does not bypass input safety ordering.

### P1 — frontend and UX

- [ ] Verify source cards show truthful evidence labels.
- [ ] Verify direct excerpts show speaker, transcript text, and timestamp only when verified.
- [ ] Verify unverified sources are labelled related/partial rather than direct teaching.
- [ ] Verify refusal responses do not show irrelevant source panels.
- [ ] Verify mobile 375px, tablet 768px, desktop 1024px, and wide desktop.
- [ ] Verify screen-reader labels and keyboard interaction.
- [ ] Verify SSE reconnect/final-event handling.
- [ ] Verify browser localStorage cache is cleared for live UI validation.

### P1 — operations and production

- [ ] Run full backend suite in the dependency-complete environment.
- [ ] Run full frontend Vitest suite.
- [ ] Run frontend typecheck.
- [ ] Run frontend production build.
- [ ] Run security, secret, dependency, corpus, and artifact scans.
- [ ] Run automatable launch gates.
- [ ] Run load/readiness matrix only against local or explicitly approved staging.
- [ ] Verify Railway `FORWARDED_ALLOW_IPS` before any deployment.
- [ ] Verify rollback and release-manifest behavior.
- [ ] Confirm production Qdrant collection and environment before any production NDCG/evaluation run.

### P2 — documentation and governance

- [ ] Reconcile contradictory readiness documents.
- [ ] Mark historical evidence as historical.
- [ ] Add the final current evidence report.
- [ ] Update `lessons.md` with any new durable invariant.
- [ ] Update product opportunities/technical debt if a new limitation remains.
- [ ] Do not claim public launch readiness based solely on faculty-preview evidence.

---

## 8. Required validation commands

### Baseline

```bash
git status --short --branch
git rev-parse HEAD
git rev-parse origin/main
git diff --check
```

### Backend targeted

```bash
backend/.venv/bin/pytest -q \
  backend/tests/test_nli_claim_verification.py \
  backend/tests/test_grounding.py \
  backend/tests/test_grounding_state_for_redaction.py \
  backend/tests/test_format_final_answer.py
```

### Backend focused readiness

```bash
backend/.venv/bin/pytest -q \
  backend/tests/test_manus_scenarios_e2e.py \
  backend/tests/test_release_failure_injection_2026_10_05.py \
  backend/tests/test_ruthless_audit_remediation.py \
  backend/tests/test_guardrails_safety_audit.py \
  backend/tests/test_first_person_release.py \
  backend/tests/test_audit_first_person_boundaries.py \
  backend/tests/test_corpus_release_registry.py \
  backend/tests/test_readiness_gate.py
```

### Backend full

```bash
backend/.venv/bin/pytest -q
```

Exit code 5, timeout, import failure, dependency skip, or collection failure is a **failed gate**, not an inconclusive pass. Diagnose the exact cause.

### Static and security

```bash
backend/.venv/bin/python -m py_compile \
  backend/app/api/chat.py \
  backend/app/orchestrator.py \
  backend/rag/nodes/generation.py \
  backend/app/grounding.py \
  backend/rag/nodes/verification.py

git diff --check
```

Run the repository’s configured secret, dependency, corpus, and artifact checks without installing new packages unless explicitly authorized.

### Frontend

Use the installed Vitest version’s supported options:

```bash
./node_modules/.bin/vitest --version
./node_modules/.bin/vitest run --coverage --pool=threads --no-file-parallelism --maxWorkers=1 --maxConcurrency=1
npm run typecheck
npm run build
```

Capture each result separately.

### Docker and caches

```bash
make flush-cache
make verify-cache-empty
curl -fsS http://localhost:8000/api/health
```

Restart/rebuild only as needed. Do not purge volumes or data.

### Live scenarios

```bash
backend/.venv/bin/python .work/live-audit/run_scenarios.py \
  | tee .work/live-audit/post-fix-scenarios-$(date -u +%Y%m%dT%H%M%SZ).ndjson
```

Verify `cache_hit=false` and inspect the complete JSON, not only the printed summary.

### Launch gates

```bash
cd backend
bash scripts/ops/launch_readiness_gates.sh
```

This script does not cover load, chaos, or human review. Do not treat it as complete production certification.

### Readiness matrix

Only run when the target and prerequisites are explicit:

```bash
cd backend
LOAD_TEST_URL=http://localhost:8000 \
BENCHMARK_SECRET='<local-only-secret>' \
READINESS_USERS='25 100 250 500' \
READINESS_DURATION='180s' \
bash benchmarks/run_readiness_matrix.sh
```

Do not run a remote target unless it is explicitly approved staging and all required environment variables are set.

---

## 9. Faculty-preview release criteria

Faculty preview is a controlled, password-protected release—not a public launch.

Minimum faculty gate:

- zero P0/P1 safety failures;
- no false teacher attribution;
- no unsupported claim shipped as grounded;
- complete public provenance contract;
- honest partial/refusal behavior;
- fresh cache-free S1–S4 evidence;
- faculty access gate confirmed;
- crawler/public exposure disabled as intended;
- documented known limitations;
- full required test gates pass.

Suggested score:

| Area | Weight | Minimum expectation |
|---|---:|---|
| Answer completeness | 20 | Every scenario addresses the actual question or clearly explains why it cannot |
| Teaching fidelity | 20 | Claims match primary teaching evidence |
| Provenance integrity | 20 | Source, speaker, excerpt, and timestamp labels are truthful |
| Safety | 20 | Crisis, abuse, addiction, and destabilization paths are fail-closed |
| UX clarity | 10 | Evidence strength and uncertainty are visible |
| Reliability/latency | 10 | No uncontrolled timeout or provider-failure degradation |

Recommended faculty-preview minimum: **85/100 with zero P0/P1 defects**.

---

## 10. Public-user production criteria

Public launch requires everything in the faculty gate plus:

- clinician sign-off where required by the clinical safety dossier;
- native-speaker review for supported Indic crisis copy;
- production environment and Railway gates verified;
- production Qdrant/Redis/Memgraph evidence;
- backup, rollback, monitoring, and alerting verified;
- public privacy, age, terms, and deletion flows verified;
- no public crawler exposure unless intentionally enabled;
- production load/readiness evidence;
- no reliance on local-only credentials, benchmark auth, or Docker hostnames;
- production smoke tests using the real signed-session flow.

**Faculty-ready does not automatically mean public-user-ready.**

---

## 11. Required final Claude Code output

At the end, Claude Code must produce:

1. exact branch and commit;
2. complete list of files changed;
3. complete list of tests/commands run with exact pass/fail counts;
4. live Docker health result;
5. cache flush and cache-empty evidence;
6. S1–S4 result table with answer quality, grounding, verification, citations, speaker verification, timestamps, latency, and cache status;
7. safety/failure-injection result table;
8. faculty-preview score out of 100;
9. public-user production score out of 100;
10. P0/P1/P2/P3 issue register;
11. explicit **GO / CONDITIONAL GO / NO-GO** for faculty preview;
12. explicit **GO / CONDITIONAL GO / NO-GO** for public launch;
13. exact remaining tasks if either decision is not GO;
14. no invented evidence and no “green” claim based only on historical documents.

---

# Copy-paste Claude Code prompt

Paste the following prompt into Claude Code from the repository root.

```text
You are Claude Code operating in the repository:
/Users/harshodaikolluru/Public/askmukthiguru-8119b0e8

Your mission is to make AskMukthiGuru genuinely ready for:
1. controlled faculty preview;
2. eventual public user launch;
3. production operation with truthful provenance, safety, reliability, and rollback evidence.

This is a ruthless audit-and-implementation task. Do not hand-wave, do not trust historical “100% green” documents without rerunning them, and do not mark anything complete without current evidence.

## Hard operating constraints

- Preserve the current working tree. Do not reset, clean, stash, revert, or switch branches.
- Do not delete .work/, reports, untracked files, or existing user changes.
- Do not commit or push unless I explicitly ask.
- Current target is main. Verify main and origin/main before doing anything.
- Read AGENTS.md, backend/CLAUDE.md, src/CLAUDE.md, lessons.md, the first-person production architecture, the Manus ruthless audit prompt, the pending readiness list, and release certification before modifying code.
- Apply SOLID, DRY, YAGNI, and KISS.
- Never run Redis FLUSHALL.
- Never change corpus/Qdrant/Memgraph/OKF data without dry-run, snapshot, and explicit apply safeguards.
- Never expose or print secrets.
- Never claim local Docker evidence is production evidence.

## Known current state

- main and origin/main currently point to:
  a8843b71d79c671af851673bcbde8e02ca317af4
- The local Docker stack has recently reported healthy backend, frontend, Redis, Qdrant, Memgraph, LLM, embedding, graph, and runtime-artifact services.
- Existing working-tree modifications are intentional and must be classified, not discarded.
- Targeted query caches were flushed using make flush-cache and verified with make verify-cache-empty.
- A focused readiness suite passed 145 tests.
- A targeted verification/grounding suite passed 26 tests.
- The full backend suite was attempted but exited code 5 and is not yet green.
- The frontend full suite was attempted but stalled/timed out under prior parallelism. Rerun with the installed Vitest version and supported single-worker flags; then separately run typecheck and build.

## Important findings from fresh live S1-S4 evidence

S1: substantive answer, but public citations_verified was null and retrieved sources had unverified/unknown speakers and no timestamps.
S2: correctly downgraded to an abstained source-only partial, but it did not fully answer the practical relationship question.
S3: five-step meditation with stop condition and Serene Mind recording, but citations_verified was publicly null and provenance still needs confirmation.
S4: honest refusal, but irrelevant citations were attached to the refusal envelope.

## Changes already made during this pass

1. backend/rag/nodes/verification.py:
   a gateway pass without claim-level evidence cannot override local unsupported claims.
2. backend/app/grounding.py:
   missing citation verification cannot be promoted to grounded; grounded partial evidence remains a deliberate source-only exception.
3. backend/app/api/chat.py:
   direct response now propagates citations_verified and orphan_citations_stripped.
4. backend/app/orchestrator.py:
   queued response now propagates citations_verified and orphan_citations_stripped.
5. backend/rag/nodes/generation.py:
   bounded max-retry refusals return zero public citations.
6. Regression tests were added for the verifier override and missing verification cases.

Review these changes for correctness and improve them if necessary. Do not assume they are correct only because focused tests pass.

## Execute these phases end to end

### Phase 0 — baseline

Run and record:
- git status --short --branch
- git rev-parse HEAD
- git rev-parse origin/main
- git diff --stat
- git diff --name-only
- Docker status and health
- current cache state

### Phase 1 — public response contract

Trace every response builder:
- direct /api/chat
- queued/orchestrator path
- /api/chat/stream final/done events
- any /api/chat/v2 path

Ensure these fields are truthful and consistent everywhere:
- citations_verified
- orphan_citations_stripped
- verification
- grounding_state
- route_decision
- citations

Add regression tests for direct, queued, and streaming serialization.

### Phase 2 — fail-closed verification

Trace every terminal final_answer path.
Ensure every terminal path has:
- verification.passed
- verification.method
- verification.citations_verified

Prove that:
- unsupported local claims cannot be overridden by a gateway pass without claim evidence;
- provider timeout and graceful-degradation content fail closed;
- missing verification is not grounded;
- failed verification cannot ship the original unsupported substantive answer;
- refusal citations are empty unless directly relevant;
- source-only partial evidence is visibly labelled partial and not presented as verified teacher doctrine.

Add adversarial tests for unsupported claims, promises, medical claims, teacher attribution, malformed citations, timeout, and provider degradation.

### Phase 3 — teaching and YouTube provenance

Use the existing scenario questions and the established YouTube/official teaching evidence. Revalidate the answer against Sri Preethaji and Sri Krishnaji teaching sources.

For every cited source verify:
- URL
- title
- channel
- transcript/excerpt
- teacher identity
- timestamp when available
- whether the answer is direct quote, excerpt, paraphrase, synthesis, or general guidance

Never infer teacher identity from words in the text. Never display Unknown Channel or Unknown as a teacher. Never fabricate timestamps. Never call an unverified source direct teaching.

### Phase 4 — S1-S4 outcomes

Run all four exact questions fresh after restarting the backend and flushing targeted caches.
Save complete JSON responses and produce a table with:
- answer completeness
- teaching fidelity
- grounding state
- verification result
- citations_verified
- citation count
- speaker_verified values
- timestamps
- latency
- cache_hit
- route decision

S1 must explain the root cause and both states without unsupported universal claims.
S2 must provide supported practical relationship/inner-observation steps or clearly explain evidence insufficiency.
S3 must remain bounded, actionable, and safe, with its recording source.
S4 must provide a supported comparison or an honest absent-term explanation, never unrelated excerpts.

### Phase 5 — first-person and QuoteWeaver

Test verified and unverified speakers, mixed speakers, head/tail fragments, promise clips, ASR defects, quote hashes, token overlap, footnotes, bridge sentences, teacher display mapping, and multilingual paths.

First-person mode must never impersonate a teacher or attribute unverified audio/text to a teacher.

### Phase 6 — safety

Run acute self-harm, passive ideation, abuse/coercion, meditation destabilization, addiction, medical overreach, provider outage, and multilingual safety tests.

Verify input safety precedes circuit-breaker/provider failure behavior.
Verify crisis responses use only verified helplines and never become grounded spiritual answers.

### Phase 7 — full quality gates

Run:
- targeted backend tests;
- focused readiness tests;
- complete backend suite;
- frontend Vitest suite with supported installed flags;
- frontend typecheck;
- frontend production build;
- py_compile;
- git diff --check;
- configured secret/dependency/corpus/artifact scans;
- launch-readiness gates.

A timeout, code 5, collection error, skipped suite, or missing output is not a pass.

### Phase 8 — runtime and cache-free validation

Restart or rebuild only what is needed. Do not purge volumes.
Run:
- make flush-cache
- make verify-cache-empty
- health check
- fresh signed anon-session
- S1-S4 live probes
- direct and queued response contract probes
- streaming final-event probe if available

Clear browser localStorage response caches before UI validation.

### Phase 9 — UX and responsive validation

Inspect the actual frontend source panel and chat UI at:
- 375px
- 768px
- 1024px
- desktop

Verify labels clearly distinguish:
- direct excerpt
- teaching-grounded summary
- partial evidence
- general guidance
- safety guidance
- unverified/related source
- refusal/no answer

Check keyboard, screen reader, timestamps, source links, audio, SSE final events, and stale localStorage behavior.

### Phase 10 — release decision

Create or update a current evidence report. It must include:
- exact branch/commit;
- files changed;
- tests and exact results;
- Docker/health/cache evidence;
- S1-S4 evidence;
- provenance findings;
- safety findings;
- known limitations;
- P0-P3 issue register;
- faculty score out of 100;
- public-user score out of 100;
- faculty GO/CONDITIONAL GO/NO-GO;
- public GO/CONDITIONAL GO/NO-GO;
- exact next tasks for every open item.

## Release hard stops

NO-GO if any of these remain:

- false or ambiguous teacher attribution;
- grounded response without explicit verification evidence;
- unsupported claim shipped as supported teaching;
- refusal carrying irrelevant citations;
- crisis input reaches ordinary spiritual guidance;
- full backend or frontend suite is not proven green;
- public response fields are silently dropped;
- source labels do not distinguish direct teaching from synthesis;
- production claims are based only on local Docker evidence;
- required clinician, native-speaker, production, rollback, or deployment evidence is missing for the requested scope.

## Final behavior

Be adversarial and specific. If a test fails, diagnose and fix it where safe. If a gate cannot be run, document exactly why and mark it UNPROVEN. Do not invent evidence. Do not stop at analysis: implement safe fixes, add regression tests, rerun affected gates, and produce the final release decision.
```

---

## 12. Handoff conclusion

The project has substantial work completed and a strong focused test baseline. It is not appropriate to discard that work. The remaining job is to reconcile the **excellent code-level readiness claims** with **fresh end-to-end public-contract, provenance, frontend, full-suite, and live scenario evidence**.

The correct approach is not to restart the project. It is to finish the release proof, close the remaining P0/P1 gaps, and keep faculty preview and public launch decisions separate.
