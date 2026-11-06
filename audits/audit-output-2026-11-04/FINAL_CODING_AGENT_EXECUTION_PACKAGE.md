# Final coding-agent execution package (2026-11-05)

Head `c9b42d3e` on `feature/audit-strengthen-rag-qdrant`. This file tells an independent coding agent where to start, in what order to work, and what it must never do. It extends `IMPLEMENTATION-AGENT-PROMPT.md`; it does not replace it.

## 1. First instruction (paste as is)

> You are the implementation agent for Ask Mukti Guru. Work in small, reviewable steps.
>
> 1. Read the audit package. Start with `audits/audit-output-2026-11-04/README.md`, then `FINAL_READINESS_AND_GAP_ANALYSIS.md` (index and release decision), then this file, then `IMPLEMENTATION-AGENT-PROMPT.md`.
> 2. Read `lessons.md` from the top through the Nov 4 and Nov 5 sections, and root `CLAUDE.md`. Where CLAUDE.md disagrees with code, the code wins. Known stale CLAUDE.md values are listed in `FINAL_LESSONS_AND_DOCUMENTATION_REVIEW.md` §8.
> 3. Check the real repository state: `git log --oneline -20`, the CI result for the head commit, and every file your task names. Do not trust a document's description of the code.
> 4. Use `FINAL_PENDING_WORK_REGISTER.md` as the status source for findings. Add the new defect IDs from `FINAL_AUDIT_GAP_ANALYSIS.md` §2 to `findings-index.md` when you confirm each one with a failing test.
> 5. Follow the phase order in §3 of this file. Do one coherent phase per branch, and one task per commit.
> 6. Never implement a decision-gated variant before the owner records the decision (`FINAL_DECISION_AND_RISK_REGISTER.md`). Never do a reserved task (T4-04, T6-07, T3-06, T6-05, T6-06, T7-02) without explicit owner approval and a stronger reviewer. Never fake a human sign-off.
> 7. Validate every change on its own: write a failing test first for a defect; run `python3 scripts/guards/lesson_guards.py` modes on changed files, the targeted tests and the formatter; record the commands and their output in the commit or PR.
> 8. Never claim that Qdrant, Railway, Supabase or the LLM provider works without evidence from that system. Mark such items UNPROVEN.
> 9. When a finding closes or a new one appears, update `FINAL_PENDING_WORK_REGISTER.md` and `docs/plans/PROD_READINESS_TASK_LIST_2026-10-11.md`. Add a lesson to the top of `lessons.md` only when it is proven, with a unique ID (search first).

## 2. Where each task's details live

Every task ID below is defined in a specification's §8 table. For each task, the agent reads:

| Need | Read |
|---|---|
| Files to change, dependencies, non-goals, rollback | The spec's §8 row |
| Current behaviour with `path:line` | The spec's §2 |
| Contracts (schemas, fields, IDs) | The spec's §3 |
| Tests and pass conditions | The spec's §7 |
| Root cause | The finding record named in the row (`findings-index.md` points to the owning doc) |
| Invariants | Root `CLAUDE.md` first-person invariants and "Voice Governance & Invariants" |

## 3. Ordered phases

Order rule: safety of data and honesty of answers first, then what staging needs, then observability, then quality work. Inside a phase, follow the file-conflict order in `20-ordered-engineering-roadmap.md` §5.

### Phase 0: preconditions (owner and agent)

| # | Task | Who | Spec |
|---|---|---|---|
| 0.1 | CI passes on the head commit | Owner (in progress) | — |
| 0.2 | Copy the Qdrant snapshot off the owner's Mac (DATA-01) | Owner | Qdrant checklist |
| 0.3 | Findings recount with the new IDs from the gap analysis §2 | Agent | Pending register |

### Phase 1: data integrity before any rebuild (no decision needed)

| # | Task | Closes | Spec |
|---|---|---|---|
| 1.1 | NEW-ING-1: builder takes rights from the register and stamps `domain_rights_status` | DATA-20, DATA-21 | Ingestion §8 |
| 1.2 | NEW-ING-2: snapshot failure aborts; upsert then delete; per-run manifest | DATA-22, DATA-23 | Ingestion §8 |
| 1.3 | NEW-ING-3: audio archive reads rights from the register | DATA-24 | Ingestion §8 |
| 1.4 | NEW-DQ-1, NEW-DQ-2: read-only live audit script; D2-D5 tests on local-mode Qdrant | DATA-15 | Data quality §8 |

### Phase 2: honest answers and release invariants (no decision needed)

| # | Task | Closes | Spec |
|---|---|---|---|
| 2.1 | NEW-ANS-1: pin the real grounding and outcome composition with tests | Probable mislabelled "Related" clip | Answer contract §8 |
| 2.2 | NEW-ANS-2: keep the abstain cause; a store error never reports `verification.passed=True` | Misleading success state | Answer contract §8 |
| 2.3 | SYS-001 remainder: classifier-failure branch and no-context node fail closed | SYS-001 | Pending register task 6 |
| 2.4 | NEW-AI-1: declare `_meditation_misroute` and `grounding_state` in `GraphState`; scan test | AI-001 area | Harness §8 |
| 2.5 | NEW-SEC-1: integrity detector uses the posture, not the bridge flag; served-clip re-check at assembly | Integrity coverage | Reliability §8 |
| 2.6 | NEW-ANS-8: release invariants suite (the 100%-class checks) | — | Answer contract §8 |

### Phase 3: Railway staging enablement

| # | Task | Needs | Spec |
|---|---|---|---|
| 3.1 | NEW-RW-4: fix `deploy_railway.sh` (Redis `noeviction`, no random `JWT_SECRET`, missing variables) | — | Railway §8 |
| 3.2 | NEW-RW-1: drain seconds in IaC; fix stale comments | — | Railway §8 |
| 3.3 | NEW-RW-2: release identity (GitHub trigger, or CI sets `GIT_SHA`) | — | Railway §8 |
| 3.4 | NEW-RW-3: forward SIGTERM to the Celery child; test | — | Railway §8 |
| 3.5 | NEW-AI-3 and NEW-OPS-6: scorer model required; startup posture log and `guru_effective_posture_info` | D-PG13 for the timeout value | Harness §8; reliability §8 |
| 3.6 | T9-01: full `.railway/railway.ts`; staging environment; `plan` then `apply` | D-26, D-30, D-29 | Railway §5, §8 |
| 3.7 | NEW-RW-5: migration procedure and manual workflow | — | Railway §8 |
| 3.8 | NEW-RW-8: measure boot time without Memgraph; skip flag only if needed | — | Railway §8 |
| 3.9 | NEW-RW-7: correct stale health-gate statements in CLAUDE.md Gotchas, the archive file and `22b` | — | Railway §8 |
| 3.10 | Run Gate A A1-A21 | Owner + agent | `FINAL_RAILWAY_STAGING_READINESS.md` |

### Phase 4: observability and operations

| # | Task | Spec |
|---|---|---|
| 4.1 | NEW-OPS-1: repair alert rules, scrape config and routing; add an integrity-breach rule | Reliability §8 |
| 4.2 | NEW-OPS-4 then T3-10: backup fixes, off-host backups, one restore drill per store | Reliability §8 |
| 4.3 | NEW-OPS-8, NEW-OPS-3, NEW-OPS-7: budget denials, collection count and snapshot age, Celery metrics | Reliability §8 |
| 4.4 | NEW-OPS-9: incident log; runbooks with an anchor per alert; fix `ONCALL.md` endpoint | Reliability §8 |
| 4.5 | NEW-OPS-5: external probe and two crisis canary messages after deploy (D-PE6) | Reliability §8 |

### Phase 5: security hardening

| # | Task | Needs | Spec |
|---|---|---|---|
| 5.1 | NEW-AI-2: `services/untrusted.py` fence helper used in generation, scorer, rerank, selector | — | Harness §8 |
| 5.2 | NEW-SEC-2: route-exposure CI test; per-user job cap | — | Reliability §8 |
| 5.3 | T1-08: auth, quota and budget on `/api/first-person/query` | D-07 | Reliability §8 |
| 5.4 | NEW-AI-5: ingest-time and lane injection screens | D-PG16 | Harness §8 |
| 5.5 | NEW-SEC-5 / NEW-AI-6: adversarial suite with stub LLM in CI | — | Reliability §8; harness §8 |
| 5.6 | NEW-MEM-1: real-Postgres RLS fixture and memory RLS tests | Test database | Memory §8 |
| 5.7 | SEC-003 remainder; T1-14 image pins | — | Pending register |

### Phase 6: evaluation baseline

| # | Task | Needs | Spec |
|---|---|---|---|
| 6.1 | NEW-RET-1, NEW-RET-2, NEW-RET-4: bank schema v2 with correct intervals; pipeline runner; budget drift test | — | Retrieval §8 |
| 6.2 | NEW-RET-3: bank stage 1 labels | Human labellers | Retrieval §8 |
| 6.3 | NEW-RET-7: baseline run; owner sets floors | D-PQ3, live collection | Retrieval §8 |
| 6.4 | EVAL-003/004 remainder | — | Pending register |

### Phase 7: retrieval and multi-clip answers (shadow mode first)

| # | Task | Needs | Spec |
|---|---|---|---|
| 7.1 | NEW-RET-6: containment-aware dedup | — | Retrieval §8 |
| 7.2 | NEW-RET-5: `RetrievalPlan` in shadow | D-PQ1 | Retrieval §8 |
| 7.3 | NEW-SYN-1, NEW-SYN-2: evidence sets and shadow integration | — | Synthesis §8 |
| 7.4 | NEW-ANS-3: `answer_blocks` and wire parity | D-PQ7 | Answer contract §8 |
| 7.5 | NEW-SYN-3 to NEW-SYN-6: copy, rendering, A/B sheet, serve Variant A | D-PQ2 | Synthesis §8 |
| 7.6 | T4-06: evidence-judge consolidation behind a default-off flag | D-16 | Retrieval §8; harness §8 |

### Phase 8: teacher registry

NEW-GURU-1 to NEW-GURU-8 with T8-01, T8-02, T1-04, T3-07, in the guru spec's §8 order. NEW-GURU-7 (graph freeze) needs D-05 for full removal.

### Phase 9: personal mentor

The memory spec's §8 order: NEW-MEM-2 to NEW-MEM-11, T6-03, T6-04, T6-02, T6-01. Journeys and reminders wait for D-PM6 and D-PM9.

### Reserved, human or decision-only (do not start without the owner)

T7-02 (SYS-003, CQ-011), T6-06 (erasure queue), T6-05 (RLS role change), T3-06 (registry and runtime state), T4-04 (clinician), T6-07 (clinician), T5-03 and T5-04 (Variant B; D-03), T1-12 (D-19).

## 4. Rules the agent must keep

1. Teachers' words appear only as verbatim spans from the store, each with its source. No generated text is shown as a teacher's words.
2. A new corpus version is a new collection. Never rewrite a serving collection in place (D-PI1 open).
3. A failure is reported as a failure. Never return a success-shaped response after a failed step.
4. Every new flag has a reader and tests for both states (CLAUDE.md "Dormant modules").
5. Never hand-pick a calibration threshold. Never fit on AI-authored labels.
6. Never write seeker text to logs.
7. Do not reintroduce anything on the "do not reintroduce" list in `specifications/ARCHITECTURE_DECISION_RECORDS_HISTORICAL.md`.

## 5. Gaps in this handoff

| Gap | Effect | Remedy |
|---|---|---|
| New defect IDs (gap analysis §2) are not in `findings-index.md` | An agent may miss them | Step 4 of the first instruction |
| Several spec task rows name tests that do not exist yet (MISSING) | The agent must create them | Write the test first; it must fail before the fix |
| Stale CLAUDE.md values (lessons review §8) | An agent may implement old values | Owner applies the proposed corrections, or NEW-RW-7 / NEW-GURU-1 do it |
| The retrieval bank has 8 rows with placeholder IDs | Phase 6 cannot measure anything yet | NEW-RET-3 labels (human) |
| Decisions not yet taken | Phases 3.6, 5.3, 5.4, 6.3, 7.2, 7.4, 7.5 wait | `FINAL_DECISION_AND_RISK_REGISTER.md` §2 |
