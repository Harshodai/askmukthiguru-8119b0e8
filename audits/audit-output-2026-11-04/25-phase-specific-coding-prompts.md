# 25 — Phase-specific coding prompts

Owner: lead. Each prompt starts with the shared preamble (§0). Paste the preamble plus one prompt into a fresh implementation session. Task details: `20` and `21`.

## §0 Shared preamble (prepend to every prompt)

```
Context: Ask Mukti Guru. Audit package in audits/audit-output-2026-11-04/ (built 2026-11-04 against origin/main@46b808fb).
Read audits/audit-output-2026-11-04/24-coding-agent-master-handoff.md §5 (guardrails) before doing anything. They are binding.
Start from the latest origin/main on a fresh branch. One task ID per PR. Report real test output.
If a task needs an owner decision listed in audits/audit-output-2026-11-04/unresolved-questions.md, stop and ask.
Line numbers in the audit are approximate: re-locate every symbol with `rg -n` before editing.
```

## §1 First task: revalidate the audit (mandatory, read-only)

```
Goal: confirm that the audit still describes the code before anyone changes it. Read-only: change nothing
except a new report file.

1. Record `git rev-parse origin/main` and `git log --oneline 46b808fb..origin/main | wc -l`.
2. For every P0 and P1 finding in audits/audit-output-2026-11-04/findings-index.md, open the cited file and symbol and mark:
   STILL-TRUE / CHANGED / FIXED / CANNOT-LOCATE, with the current file:line.
3. For every task spec in audits/audit-output-2026-11-04/21, confirm each listed file and symbol exists. List any that moved.
4. Re-run the CI-visible facts: is main green? Which jobs fail? (GitHub Actions UI or API, read-only.)
5. Check whether the owner has answered any item in audits/audit-output-2026-11-04/unresolved-questions.md
   (look in audits/audit-output-2026-11-04/decision-log.md §3).
6. Write audits/audit-output-2026-11-04/REVALIDATION-<date>.md with the tables above and a list of roadmap tasks that are now
   unblocked, blocked or obsolete.
Acceptance: every P0/P1 finding has a status; no code changed.
```

## §2 P0 agent tasks (T0-02, T0-04, T0-06, T0-07)

```
Tasks: T0-04 first (honest gate test), then T0-02 (purge + publication guard) once the owner has answered
D-01 and D-02. Specs: audits/audit-output-2026-11-04/21 §T0-04, §T0-02.

T0-04: restore backend/tests/test_first_person_public_release_gate.py so it asserts the status the gate
computes on a clean checkout. Do not change the gate logic here. The owner edits the scopes in
audits/evidence/FIRST_PERSON_OWNER_DECISIONS_2026-10-22.md; you only open a PR note asking for it.
Acceptance: Lint & Test and Production Readiness are green on the PR.

T0-02: move each listed file to the owner's private store (ask for the destination), and leave stubs
{path, sha256, bytes}. Extend scripts/guards/lesson_guards.py publication checks for the keys
verbatim_text / source_transcript_text / live_verbatim_text, "/Users/" paths, and audio under public/
without a rights id. Add positive and negative tests. Do NOT rewrite Git history unless the owner says so.
```

## §3 P1 guardrails (T1-01 … T1-16)

```
Goal: remove every path that can produce a P0, and close the cheap P1 guardrail gaps. Parallel-safe tasks
(different files): T1-01, T1-03, T1-07, T1-08, T1-09, T1-13, T1-14, T1-16. For backend/app/config.py,
merge in this order: T1-07, T1-02, T1-06.

Priority order: T1-05 (fail closed) → T1-02 (latent P0 removal) → T1-01 (voice governance) → T1-07
(spend cap) → T1-08 (endpoint auth) → T1-11 (gate hardening, after T0-04) → T1-03 → T1-10 → others.

For each task, follow audits/audit-output-2026-11-04/21 (P1 specs) or the finding record (P2 tasks). Required tests:
- T1-05: fault injection proves no generated text on teaching intents in first-person-only mode.
- T1-02: grep proves no LLM path writes or rewrites teacher text; existing tests still pass.
- T1-11: one failing fixture per defect listed in audits/audit-output-2026-11-04/16 §3 X-RC2.
- T1-07: production settings validation fails without caps or the scorer model.
Do not change distress or crisis logic in this phase.
```

## §4 P2 measurement (T2-01 … T2-06)

```
Goal: make quality and safety measurable before any behaviour change in P4/P5.

T2-05 first (fixture Qdrant + Redis CI job), then T2-02 (frozen retrieval bank: Recall@k, MRR, nDCG
artifacts per PR), T2-01 (offline PR eval suite: routing set, benign and crisis distress sets, quote
integrity, voice lint, abstain set; blocking on regression), T2-03 (answer_outcome events, prompt_id@version,
tokens and cost per call, useful_answer definition per audits/audit-output-2026-11-04/21 §T2-03), T2-06 (config lint).

Datasets: you may draft items, but crisis items become blocking only after the clinician reviews them,
and multilingual items only after native review. Never label gold items yourself (T2-04 is human).
Acceptance: the suite runs on every PR without a deployment, in under 10 minutes, and blocks on regression.
```

## §5 P3 data correctness (T3-01 … T3-12)

```
Goal: governed identity, deployable rights, write control, takedown.
Order: T3-01 (rights register in image + startup check) and T3-12 (encoder fingerprint) → T3-02 (Qdrant
keys + digest) → T3-04 (builder per-video replace, snapshot first) → T3-03 (hash-field rename in vNext,
writer contract test) → T3-08 (schema snapshot CI) → T3-06 (source registry authority, takedown(),
structured citations) → T3-05 (promotion gate + daily audit) → T3-07 → T3-11 (after D-05) → T3-09/T3-10
(after D-08).

Rules: never mutate a serving collection in place; a new schema means a new collection (root CLAUDE.md
invariant 4). Every write: dry-run → snapshot → ask → apply. Builders host-side. Keep script twins
byte-identical. Prove each change with the fixture-store CI job.
```

## §6 P4 retrieval, routing and safety (T4-01 … T4-07)

```
Goal: the right questions reach the teaching lane, and the right clips survive.
Each change must show a non-negative delta on the frozen bank (T2-02) and the PR suite (T2-01).

T4-01 gate-then-dedup; T4-02 hybrid dense+sparse RRF grouped by parent in the v10 store;
T4-03 single route-decision service with one scope file (after D-04); T4-05 Standard DISTRESS direct route;
T4-06 evidence-judge consolidation (prefer after T7-01): ≤2 LLM calls per in-domain turn, scorer failure
abstains as relevance_indeterminate; T4-07 verified helplines only.

T4-04 (distress topic vs state) is safety code: build it behind a flag; evaluate on the clinician-reviewed
crisis core set (recall must be 100%), the reviewed benign set (overfire ≤5%) and the multi-turn set
(0 benign SEVERE). Do not change the production default until the owner files the clinician's written
sign-off. Never weaken SEVERE/CRISIS handling.
```

## §7 P5 answer intelligence (only after the owner decides D-03 / ADR-001)

```
Goal: complete answers without ever speaking as a teacher. All work behind default-off flags
ANSWER_PLAN_ENABLED and LAYERED_ANSWER_ENABLED.

T5-01 AnswerPlan (intent, depth, mode, facets, teacher filter, language).
T5-02 per-facet retrieval + evidence-set selection (coverage, video diversity, contained-span removal,
teacher labels kept separate; never merge two teachers' words).
T5-04 verifier: exact-substring quotes; every assistant-explanation sentence cites span ids and passes
entailment against them, or is dropped; attribution check; untrusted text fenced in prompts.
T5-03 layered composer + response contract layers[{type, text, span_ids, voice}] + UI rendering
("In our own words" for assistant layers; quotes with play buttons for verbatim layers).
T5-05 answer_trace follow-ups; T5-06 language field + labelled translation (after native review);
T5-07 prompt registry.

Acceptance: voice lint 0 violations; 0 unsupported explanation sentences on the held-out set; flag off =
identical behaviour to today (snapshot test).
```

## §8 P6 mentor and memory (T6-01 … T6-07)

```
Goal: continuity the seeker controls. Every memory read or side effect checks active consent.
T6-01 consolidate onto canonical memory (snapshot + owner approval before any migration of user data);
T6-02 use memory on the teaching lane only for: not repeating clips, continuity offers, depth/language
preferences; T6-03 user-stated preferences replace the LLM persona; fence client summaries;
T6-04 save answer + collections + seeker clip report + journeys v1 (sourced spans only);
T6-05 backend writes assistant turns; client RLS role='user' only; T6-06 durable erasure job;
T6-07 dependency guard only from a clinician-written rule.
No streaks tied to progress, no guilt notifications, no win-back flows.
```

## §9 P7 reliability, performance and cost (T7-01 … T7-06)

```
T7-01: split FirstPersonPipeline.execute into named steps. Behaviour-identical: record golden outputs for
the frozen bank and the PR suite before, compare after. No logic change in this PR.
T7-02: make the teaching lane async; remove run_llm_coroutine and the thread hop; one event loop per Celery
worker; delete the start_railway.py watchdog only after a staging c20 load test shows no starvation.
T7-03: one LLM gateway (budget, timeouts, retries, dated price table, telemetry); rename container.ollama.
T7-04: caches to 2–3 versioned tiers; no semantic cache on teaching answers.
T7-05: ruff BLE and import-linter ratchets (counts only go down).
T7-06: retire the legacy FP engine and the generating graph from chat serving after vNext wins on the
frozen bank (ADR-004) and the owner confirms D-04.
```

## §10 P8 teacher extensibility (T8-01, T8-02)

```
Extend backend/config/gurus.yaml (sources, rights policy, attribution policy, aliases, voice references,
allowed surfaces). Generate guardrail patterns, labels and doctrine aliases from it. Add a CI guard that
rejects new teacher-name literals in runtime code (ratchet the existing 621). Dry-run the onboarding
checklist in audits/audit-output-2026-11-04/11 §6 with a fictional test teacher in fixtures only. Never add a real teacher
without the owner and that teacher's written permission.
```

## §11 P9 deploy and operations (T9-01 … T9-04) — owner present

```
Only when the owner asks in this session. T9-01 Railway IaC for backend, worker, beat, Redis (and Qdrant
if self-hosted) per environment; staging first; env-var names only in the repo. T9-02 smoke suite,
cross-browser e2e green, real-model load test at c20 (record p50/p95/p99, error rate, cost). T9-03 alerts
(integrity breach, crisis-lane error, spend 80%, p95 breach, data-audit fail) firing in a drill.
T9-04 run audits/audit-output-2026-11-04/22 (Qdrant) and 22b (Railway) runbooks read-only and file the reports.
```

## §12 Final implementation-verification prompt (independent reviewer)

```
You are an independent verifier. You did not implement this work. Read-only.
1. For every finding in audits/audit-output-2026-11-04/findings-index.md marked closed by a merged PR, open the PR, read the
   diff, and confirm the acceptance criteria in audits/audit-output-2026-11-04/21 or the finding record are met. Re-run the
   named tests. Mark VERIFIED / NOT MET / PARTIAL with evidence.
2. Re-run: the PR eval suite (T2-01), the frozen retrieval bank (T2-02), the release gate on a clean
   checkout (T1-11), the voice lint, the publication guard, and the fixture-store CI job. Attach outputs.
3. Check the guardrails in audits/audit-output-2026-11-04/24 §5 across all merged PRs: any teacher-voice generation, any
   edited gate or test to force a status, any in-place collection mutation, any secret, any human gate
   marked done without an artefact hash.
4. Re-score audits/audit-output-2026-11-04/23 "Release-readiness scorecard" with evidence links. Never upgrade a dimension
   without the computed evidence.
5. Write audits/audit-output-2026-11-04/VERIFICATION-<date>.md. List residual risks plainly. Do not claim readiness that the
   evidence does not show.
```
