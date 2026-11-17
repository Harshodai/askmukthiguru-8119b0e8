# Engineering mission plan: scalable text rules and end-to-end readiness

**Date:** 2026-11-16
**Status:** Proposed. Waiting for owner confirmation. Nothing in Phases 1 to 9 has started.
**Source:** the owner's two prompts of 2026-11-15 (regex rationalisation; the full engineering mission).
**Complexity:** Large overall. Phases 0 and 1 are small.

> **Single-list rule.** CLAUDE.md says `docs/plans/PROD_READINESS_TASK_LIST_2026-10-11.md` is the only open-work list and new plan files should not be started. This file exists because the owner asked for one. The task list carries a pointer to it. When an item here closes, update the task list, not only this file.

---

## 0. Where things stand (verified 2026-11-16)

### Done this session (uncommitted, working tree only)

| Item | File | Evidence | Not yet done |
|---|---|---|---|
| Crisis downgrade fixed: the existential carve-out can no longer lower CRISIS, and lowers SEVERE only when "empty inside" is the only detected signal | `backend/app/pipeline/stages/distress_stage.py` (carve-out near line 303, helper `_only_existential_signal`) | New tests pass; `evals/run_safety_scenarios.py`: 226 pass, 4 declared expected failures, 0 unexpected | Container not rebuilt; full suite not re-run after the edit |
| Quadratic compound-question pattern made linear | `backend/app/pipeline/stages/first_person_bridge.py` (`_COMPOUND_QUESTION_RE`) | 10,000-char inputs under 0.25 s (was 0.94 s at 8,000); verdict identical to old pattern on every 1-5 word combination of 14 marker words; only change is a 200-char cap on the "both ... and" span | Same as above |
| Regression tests | `backend/tests/test_crisis_downgrade_and_compound_redos_2026_11_16.py` | 10 passed; related suites 418 passed | |
| Saved measurements | `audits/work/phase1-2026-11-15/` (scanner JSON, breadth inventory, per-alternative hit counts, baseline summary) | | Untracked |

### Owner-accepted residual
- A SEVERE message whose only detected signal is "empty inside" still goes to the compassionate lane, even when it mentions means the engine does not recognise ("I feel empty inside and I have the pills ready"). Owner chose "keep narrowed" on 2026-11-16. The root cause is engine phrase coverage, which belongs to slice R7 and the pending native-speaker and clinician review.

### Baseline numbers
- Full backend suite before this session's edits: 14,361 passed, 22 skipped, 2 deselected, 2 xfailed (548 s).
- Local stack up: backend, celery worker, Qdrant, Redis, Memgraph, Jaeger, Prometheus, Grafana, local Supabase.
- Serving collection `first_person_v10`: 4,224 points, 2,758 with `verbatim_text`; `source_text_hash` matches on all 2,758.
- `first_person_v8`: 1,801 points; `transcript_hash` matches on all 1,801 (v8 has no `source_text_hash` field; this is not a defect).

### Tree state (blocks any release until handled in Phase 0)
- `main` is ahead of and behind `origin/main`.
- Another session has 36 modified files and several untracked scripts in the same checkout. `distress_stage.py` contains edits from both sessions.

---

## 1. Requirements restated

1. **Regex.** Replace regex where it is the wrong tool, keep it where it is right, and make every text rule listable, testable and individually measurable. Served answers may change only through a registered graded run.
2. **Mission.** Understand and improve the whole system: harness, knowledge layer (OKF, Memgraph, ontology), answer routes, LLM wiring, ingestion, data engineering, distributed behaviour, code structure, security, observability, evaluation and product. Each area ends with evidence, fixes where justified, and an honest readiness statement.
3. **Non-negotiables carried from CLAUDE.md:** no generated teacher speech; integrity gates fail closed; store writes go dry-run, snapshot, ask, apply; human-owned evidence is never edited; safety floors stay deterministic; no flag without a reader; no production deploy, no Railway changes, no owner-gated serving switches.

---

## 2. Execution model (owner's latest instructions)

- **No Workflow tool.** Work runs inline or through individual subagents.
- **Opus:** design, safety review, adversarial refutation of findings.
- **Sonnet:** implementation and refactoring.
- **Haiku:** read-only search, inventories, counts, release checklists.
- **Lead (this session, Fable or Opus):** assigns bounded tasks, reads results, challenges them, approves or rejects diffs.
- **Every delegated prompt carries full context:** the measured facts in this file, the repo state, the paths under `audits/work/`, the exact files in scope, whether it may edit, and the invariants that apply. Agents must not rediscover what is already measured.
- **Stage the work.** One area per session or per small batch, with results saved to `audits/work/` before the next step, so a usage limit loses one step and not the mission. (The 2026-11-15 run lost 18 of 20 agents to the limit.)
- **Release gate.** No commit or push without the owner's explicit go (global rule and the "push once at end" memory). When the go comes: commit locally by path on the task branch, one final push, one PR.

---

## 3. Patterns to mirror

| Category | Source | Pattern |
|---|---|---|
| Fail closed | `backend/services/first_person_content_assessment.py` (`assess_content`) | Detector exception returns a `degraded` assessment that blocks serving; never a silent pass |
| Typed decisions | `backend/domain/first_person_decision.py` | Findings carry `code`, `kind`, `severity`, `detector`, `contract_version` |
| Store changes | `backend/scripts/ops/build_fp_context_from_v9.py --dry-run` | Preview first, snapshot (`snapshot_qdrant.py`), owner approval, then apply |
| Corpus audits | `backend/scripts/ops/fp_data_quality_scorecard.py` | Read-only scroll, counts per reason, stored text must be a fixed point of the cleaner |
| Tests | `backend/tests/test_<topic>_<yyyy>_<mm>_<dd>.py` | Plain pytest, parametrised real inputs, no mocks of the unit under test |
| Module self-check | `first_person_content_assessment.py` `__main__` block | New modules end with a runnable assert-based self-check (backend/CLAUDE.md) |
| Ops script copies | `scripts/ops/` and `backend/scripts/ops/` | Byte-identical where both exist (`tests/test_repo_layout.py`) |

---

## 4. Findings so far (new IDs `EM-nn`; existing register IDs reused where they apply)

| ID | Severity | Kind | Where | Evidence | Status |
|---|---|---|---|---|---|
| EM-01 | Critical (safety) | Confirmed defect | `distress_stage.py` existential carve-out | Engine rated three probe messages CRISIS; carve-out returned MILD_EXISTENTIAL and the stage lowered them | Fixed in tree, uncommitted |
| EM-02 | High | Confirmed defect | `first_person_bridge.py` `_COMPOUND_QUESTION_RE` on the user query | 0.94 s at 8,000 chars, quadratic, message cap 10,000 | Fixed in tree, uncommitted |
| EM-03 | Medium (pending trace) | Confirmed behaviour change, introduced by commit `d5bed8dd` (other session); consequence is a hypothesis | `backend/ingest/verbatim/asr_cleaner.py` token state machine | On stored v10 text the new cleaner changes 9 clips; the pre-`d5bed8dd` cleaner changed 6. The 3 extra clips are all non-Latin script (Urdu script with Korean and Latin fragments, which looks like garbled ASR), where the new cleaner collapses repeated words (`ہی ہی`, `بھی بھی`, `ایسا ایسا`, `لے لے`). Whether those repeats are legitimate is not established. `_LEGIT_DOUBLES` (line 19) is English-only. On v8 neither cleaner changes any clip. Idempotence failures 0; flag differences 0. **Hypothesis to trace:** `first_person_store.py:126` and `build_first_person_index.py:311,566` re-derive `transcript_hash` and the point id through this cleaner, while the v10 serving integrity field is `source_text_hash`; does a rebuild or store lookup on these clips change id or hash? Also check whether the 3 points are servable at all | Open; tell the owner of `d5bed8dd` |
| EM-03b | Medium | Measured; invariant 13 breach that predates this session | 6 stored v10 clips | Stored text that the pre-`d5bed8dd` cleaner would still change (examples: dropped "you know", "Some Some", "awareness awareness", "opportunities Opportunities"). Invariant 13 requires stored text to be cleaned before hashing | Open; closing it is a store write (dry-run, snapshot, approval, apply) |
| EM-04 | Unknown until reachability confirmed | Hypothesis | `backend/rag/doc_utils.py:78`, `backend/rag/nodes/generation.py:782`, `backend/services/memory/okf_store.py:342` | Scanner timed these at 5 s or more on adversarial input; scanner reports no direct user-input path | Open |
| EM-05 | Medium | Confirmed (probe) | `backend/app/security_utils.py:37,43` | `^...$` with `re.match` accepts a trailing newline (`_ISO_DATE_RE`, `_EMAIL_RE`) | Open |
| EM-06 | Low | Confirmed (probe) | `backend/services/pii_scanner.py:10`, `backend/app/telemetry_db.py:209` | Aadhaar/ID patterns redact any grouped 12-digit number; email and phone patterns duplicated | Open |
| EM-07 | High (safety) | Confirmed (probe) | `backend/rag/intent_prerouter.py:27,34` | `DISTRESS_RE` misses "suicidal" and "panic attacks"; `GREETINGS_RE` accepts "hi there suicide" and is safe only because distress is checked first | Existing register item **A12** |
| EM-08 | Low | Hypothesis | `backend/app/intake/short_circuit.py` | Second greeting grammar with a different vocative list; CLAUDE.md marks it dormant; caller check not run | Open |
| EM-09 | Medium (maintainability, served quality) | Measured | `first_person_content_assessment.py` | Over 2,758 v10 clips: clinical pattern has 42 alternatives, 6 hit no clip, 11 hit exactly one, 18 hit 2-5; outcome-promise 7 of 12 hit nothing; `namaste` alone marks 38 clips event-bound. Rules are per-clip patches written as general rules | Regex track (Section 5) |
| EM-10 | Owner decision | Measured (all 25 workflow files) | `.github/workflows/*.yml` | Every workflow, including `lint-test`, `main-hard-gates`, `security-audit` and `golden25-gate`, runs only on `workflow_dispatch` or `schedule` (commit `4b054a4b`, to avoid billing failures). Nothing gates a push or PR | Record risk; owner decides |
| EM-11 | Medium | Measured | Codebase-wide | 1,558 regex call sites in 317 files; 992 distinct patterns; 694 uncompiled inline calls; 180 pattern strings repeated across files | Regex track |
| EM-12 | Medium | Measured (codebase-memory graph) | `rag/nodes/generation.py::generate_answer` (cyclomatic 143), `rag/nodes/retrieval.py::retrieve_documents` (127), `first_person_local_review.py::startup_check` (114), `first_person_bridge.py::_bridge` (78), `first_person_pipeline.py::_serve_from_context_harness` (62, 16 params) | Largest files by total complexity: `first_person_pipeline.py` 492, `generation.py` 481, `ingest/pipeline.py` 452 | Phase 8 |

Before any new ID goes into the register, grep `docs/analysis/OUTSTANDING_ISSUES.md` and the task list; the highest existing A-number seen is A39.

---

## 5. Regex track

### 5.1 Decision

Sort every rule by what it does and give each kind one home.

| Kind | Home | Regex? |
|---|---|---|
| Format parsing (ids, timestamps, URLs, dates) | Code | Yes: compiled once at module level, `fullmatch`, input length capped |
| Word and phrase lists | Reviewed data files with rule id, language, severity, provenance, positive and negative examples; matched by one engine (the existing `DoctrinePhraseTrie` or an equivalent token matcher) | No |
| Meaning judgments about a stored clip (health claim, self-contained, event-bound, promise) | Versioned label on the point, computed offline, reviewed, read at serve time; missing or stale label fails closed | Only as a deterministic floor |
| Phrases that match one or two clips | Reviewed exclusion list keyed by point id with a reason | No |
| Query-side safety (crisis, off-topic, intent) | Phrase lists as data plus the existing LLM escalation | Deterministic floor stays |

Rejected:
- Rewriting each regex as a hand-written scanner per file (the approach in `d5bed8dd`): same maintenance cost, and EM-03 shows it can silently change stored text.
- A rules framework or new dependency.
- An LLM at serve time for clip judgments (invariants 1 and 15).

### 5.2 Slices, in order

| Slice | Work | Proof | Gate |
|---|---|---|---|
| R1 | Promote `audits/work/phase1-2026-11-15/alt_hits.py` to `backend/scripts/ops/rule_hit_report.py` (read-only, per-rule and per-alternative hit counts over any collection) | Runs on v10 and v8; numbers match the saved file | None |
| R2 | Golden verdict snapshot: every gate verdict (content assessment, standalone, evidence policy) over all v10 clips plus the labelled question sets, stored as JSON with a test that diffs against it | Snapshot reproduces exactly twice in a row | None |
| R3 | Fix EM-03: trace the hash and id consequence; make the cleaner's repeat-collapse script-aware (no collapse outside Latin script unless listed) | Over 2,758 v10 + 1,801 v8 clips: zero changes beyond the pre-`d5bed8dd` cleaner (6 on v10, 0 on v8); `fp_data_quality_scorecard.py` agrees | None (no store write); coordinate with the other session first |
| R3b | Close EM-03b: re-clean and re-hash the 6 clips (`verbatim_text`, `transcript_hash`, `source_text_hash` in one transaction) | Dry-run diff of the 6 points; afterwards stored v10 text is a fixed point of the cleaner | Store write: dry-run, snapshot, owner approval, apply |
| R4 | EM-02 sibling sweep: confirm reachability of EM-04, then make reachable ones linear; add a guard to `scripts/guards/lesson_guards.py` that rejects nested unbounded quantifiers in new code | Timing tests at the input cap | None |
| R5 | Content-assessment lists to data (one file per family under a new rules folder), one matcher, rule ids surfaced in abstain reasons and logs | R2 snapshot identical | None |
| R6 | Per-clip rules to labels and an exclusion list; drop dead alternatives (EM-09) | Dry-run diff listing every clip whose verdict flips | Store write: dry-run, snapshot, owner approval, apply; then a registered graded run |
| R7 | Query-side lists to data: crisis, distress, greeting, off-topic. Merge the three greeting grammars and the two distress lexicons (EM-07, EM-08). Close the "empty inside" residual by adding means phrases with review | `evals/run_safety_scenarios.py` unchanged or better; R2 snapshot identical for routing | Native-speaker and clinician review stays pending; no claim of coverage beyond what reviewers sign |
| R8 | Small fixes: EM-05 (`fullmatch`), EM-06 (one PII module, tighter id patterns), shared compiled patterns for the 180 duplicates where callers agree | Unit tests per pattern | None |
| R9 | Delete instead of migrating regex in code that is dead on the live posture (start with `generation.py`, 69 call sites), after callers are confirmed through the graph and runtime | Graph shows no live caller; suite green | Deletion of dormant modules is the owner's call (CLAUDE.md "Dormant modules") |

---

## 6. Mission areas

Each block: status, evidence so far, open questions, method, deliverable, gate. "Unreviewed" means no finding in this file comes from that area yet.

### A. Agent harness and orchestration
- **Status:** unreviewed.
- **Evidence so far:** a 31-agent Workflow on 2026-11-15 hit the usage limit twice; 18 of 20 started agents returned nothing; two results were saved by hand. Hooks (GateGuard fact-forcing, Stop hook) blocked or interrupted routine writes several times this session.
- **Open questions:** root CLAUDE.md states the first-person invariants twice (slim and full list): where do they disagree? How many tokens load each session? Which hooks block legitimate work, and do they have tests? Do guards in `scripts/guards/` run anywhere now that CI is manual (EM-10)? Which referenced files, flags and commands no longer exist?
- **Method:** diff the two invariant lists; measure auto-loaded size; read `.claude/settings*.json` and hook scripts; check each referenced path exists.
- **Deliverable:** contradictions list, trimmed instruction proposal (no binding rule removed), hook and guard test gaps.
- **Gate:** edits to hooks, permissions and CLAUDE.md need owner approval.

### B. OKF, Memgraph and LightRAG
- **Status:** unreviewed.
- **Evidence so far:** files mentioning graph or OKF under `backend/app` and `backend/rag` include `rag/kg_expansion.py`, `rag/nodes/reranking.py`, `rag/nodes/citation_extractor.py`, `rag/nodes/generation.py`, plus config, metrics and health files. This does not show graph output reaching an answer.
- **Open questions:** on the live first-person-only posture, which call sites read the graph or OKF, and can their output reach the response body, only routing, or nothing? What is the actual Memgraph schema (labels, relationship types, indexes, constraints)? Is there any registered graph-on versus graph-off comparison?
- **Method:** `trace_path` from `/api/chat` handlers into graph and OKF readers; read-only Cypher counts; a controlled ablation on the 116-question tuning set with graph off versus on, scored by the existing grader.
- **Deliverable:** per-component verdict (keep, simplify, move offline, retire) with the ablation numbers.
- **Gate:** retiring a component is an owner decision; the ablation itself is a registered run.

### C. Ontology and semantic model
- **Status:** unreviewed.
- **Open questions:** where are teacher, teaching, practice and concept defined (OKF, graph, Qdrant payload, `guru_registry.py`, `doctrine_terms.py`, `provenance_ontology_service.py`, `ontology_guardrails.py`, prompts)? Which is authoritative? `teacher_id` is not uniform across Qdrant points (CLAUDE.md data stores): what does each value mean?
- **Method:** inventory definitions; count distinct values per store; map which reader uses which.
- **Deliverable:** one ownership table and the drift list.
- **Gate:** any re-labelling of stored data is a store write.

### D. Answer routes
- **Status:** partially reviewed (crisis carve-out and compound pattern only).
- **Open questions:** full route table across web, mobile, WhatsApp, streaming, non-streaming, anonymous and authenticated; does every channel run the same crisis, guardrail and output stages? Is the general-knowledge lane (invariant 21, A-34) reachable on any live turn? Any node returning `final_answer` without the `verification` dict? Any personalised or follow-up answer cached under `(language, message)`?
- **Method:** graph traces from each route; one probe per channel on the local stack using the benchmark or incognito flag.
- **Deliverable:** route table with mode (clip, static, redirect, abstain, generated) and gates per route.
- **Gate:** closing the general-knowledge lane changes served answers; needs a registered run.

### E. LLM wiring
- **Status:** unreviewed.
- **Evidence so far:** provider and gateway classes include `openrouter_service`, `sarvam_service`, `ollama_service`, `nim_service`, `krutrim_service`, `base_llm_service`, `gateways/anthropic_gateway`, `gateways/sarvam_http`. `SarvamHTTPGateway._call_inner` has cyclomatic 61; `OpenRouterService._call_api` 45.
- **Open questions:** CLAUDE.md says the provider classes share no code, yet `base_llm_service.py` exists: who inherits it? For every call site: model setting, timeout, retries, behaviour on failure. Does any fallback model weaken a gate? Where are free-text replies parsed, and do unparseable replies fail closed? Any untrusted text in prompts without delimiting?
- **Method:** graph query for every caller of the provider call methods; read each failure branch.
- **Deliverable:** call-site table and the minimum shared contract (if consolidation removes real duplication).
- **Gate:** none for the audit; changes to judge or scorer behaviour need a registered run.

### F. Ingestion
- **Status:** partially reviewed (cleaners only, EM-03).
- **Evidence so far:** `ingest/pipeline.py` `ingest_url` at line 866, `_embed_and_index` at 3216 (cyclomatic 40); cleaners called from `ingest/pipeline.py`, `ingest/video_pipeline.py`, `build_first_person_index.py`, `build_fp_context_from_v9.py`, `build_full_corpus_v10.py`, `services/first_person_store.py`, `services/quote_weaver.py`. `backend/ingest/verbatim/` is still not wired into `ingest/pipeline.py` (invariant 7).
- **Open questions:** actual stage sequence versus the target lifecycle; every text mutation after a hash is computed; behaviour on crash between Qdrant write, graph write and manifest update; re-ingestion and deletion of stale points; is the transformation version stored on each point; are rejected records kept with reasons?
- **Method:** trace one video end to end against a disposable collection; fault-inject at each write boundary.
- **Deliverable:** stage map, idempotency table per write, crash-recovery results.
- **Gate:** only disposable collections; real store writes need dry-run, snapshot, approval.

### G. Data engineering and distributed behaviour
- **Status:** unreviewed.
- **Evidence so far:** 20 Celery tasks in `backend/tasks/`; `retry_kwargs` with `max_retries` 1-3 present; a grep found no `acks_late` or time limits in `backend/tasks` (unconfirmed; configuration may live elsewhere).
- **Open questions:** delivery semantics per task and what a redelivery does; process-local state that breaks with several replicas (in-memory rate-limit fallback, kill switch, budgets, caches); untracked background tasks; blocking calls in request paths; pool sizes versus workers; which store is authoritative for what and where a crash leaves stores disagreeing.
- **Method:** read Celery config and each task; graph query for `asyncio.create_task` and sync HTTP in async functions; run two API replicas locally against one Redis.
- **Deliverable:** per-task semantics table; replica-safety list; reconciliation gaps.
- **Gate:** none for local tests. Concurrency is sized against the deploy target, not local Docker.

### H. Code structure
- **Status:** measured at a high level (EM-12).
- **Open questions:** natural seams in `first_person_pipeline.py` and `generation.py`; what in them is dead on live config; duplicate implementations (greeting grammars, retry helpers, caches); flags whose two states are not both tested; import cycles.
- **Method:** codebase-memory graph (complexity, callers, cycles); `Settings` field reader counts.
- **Deliverable:** ranked refactor list with callers named; each refactor proven behaviour-identical by tests and the R2 snapshot.
- **Gate:** deleting dormant modules is the owner's call.

### I. Security, privacy and safety
- **Status:** partially reviewed (EM-05, EM-06, EM-07 only).
- **Open questions:** route table with auth dependency per route; per-user tables with weak or missing RLS; can a client choose another session's anonymous identity; memory isolation and deletion cascade; secrets in the tracked tree (report path and type only); ingestion and web-content prompt injection; rate-limit bypass when Redis is down; dependency pins.
- **Method:** graph query for routes and their dependencies; `supabase/migrations` review; existing `nightly-rls` workflow run by hand.
- **Deliverable:** findings with exploit steps reproduced locally.
- **Gate:** crisis and helpline changes need clinician and native-speaker review, which stays pending.

### J. Observability and runtime
- **Status:** unreviewed.
- **Open questions:** for each pipeline stage, does a log line or span prove it ran for a given request id? Which stages are silent? Startup warnings actually present? Misleading success logs? Serve-path `except Exception` without re-raise or request-id logging? Any raw user text in logs?
- **Method:** `make verify-stack-fresh`; three probes (in-corpus, out-of-corpus, greeting) with the benchmark flag; follow request ids through backend, worker and Jaeger.
- **Deliverable:** silent-stage list and the logging fixes.
- **Gate:** none.

### K. Evaluation and tests
- **Status:** partially reviewed (suite counts; CI trigger state EM-10).
- **Evidence so far:** 14,361 backend tests pass locally; 184 frontend unit test files; `tests/e2e` exists.
- **Open questions:** what CI would gate if switched on; tests that assert on mocks of the unit under test; missing classes (cross-tenant isolation, streaming, failure recovery, ingestion idempotency, concurrency); which sets are tuning and which are held out; are retrieval metrics computed against human labels anywhere.
- **Method:** read workflows and markers; `pytest --collect-only`; map eval sets to label provenance.
- **Deliverable:** gap list; R2 snapshot as a permanent regression gate.
- **Gate:** labels stay human-owned; draft labels never count as gold.

### L. Frontend, mobile and WhatsApp
- **Status:** unreviewed.
- **Open questions:** fields and enum values (`grounding_state`, `route_decision`) the backend emits but the frontend does not handle; what the user sees for abstain, crisis, error and offline; streaming reconnect actually wired; citation playback window versus the backend rule (`start_ms - 0.25 s`, `end_ms + 0.25 s`); accessibility basics; anonymous to signed-in transition.
- **Method:** compare `ChatResponse` with frontend types; `npm run lint`, `npm run test -- --run`; Playwright journeys on the local stack.
- **Deliverable:** contract drift list and user-visible defects.
- **Gate:** store submission work follows `docs/MOBILE_RELEASE_RUNBOOK.md`; not in scope.

### M. Research-backed decisions
- Use `ctx7` for library questions (Qdrant, Memgraph, Celery, FastAPI) before changing their use. Every architectural change records problem, root cause, approach, alternatives, migration, failure modes, tests and rollback, as an ADR under `docs/architecture/`.

---

## 7. Phases and order

| Phase | Content | Depends on | Size |
|---|---|---|---|
| 0 | Tree hygiene without disturbing the other session: create a separate `git worktree` off `origin/main` (no branch switch in the shared checkout, which holds the other session's 36 uncommitted files); carry this session's changes over by path, and split `distress_stage.py` hunk by hunk because both sessions' edits are mixed in it; agree file ownership with the other session; rebuild the backend container; re-run the full suite as the new baseline | Owner go | S |
| 1 | R1, R2 (measurement before any refactor) | 0 | S |
| 2 | R3 (EM-03 cleaner change), R4 (EM-04 sweep), R8 small fixes; R3b once the owner approves the store write | 1 | S-M |
| 3 | Audits A, D, E, J (read-only; separate subagents, each saving to `audits/work/`) | 0 | M |
| 4 | Audits B, C, F, G, I, K, L | 0 | M-L |
| 5 | R5, R7 (lists to data, behaviour-identical) | 1 | M |
| 6 | R6 (labels and exclusion list) and any served-answer changes from Phase 3-4 findings, batched into one registered graded run | 5, owner approvals | L |
| 7 | Ingestion and distributed fixes from F and G (idempotency, crash recovery, reconciliation) | 4 | L |
| 8 | Structural refactors from H, R9 deletions | 1, owner decisions | L |
| 9 | Adversarial review of the full diff (Opus), independent verification (Haiku), docs and register updates, release on owner go | all | M |

Phases 3 and 4 are read-only and can start right after Phase 0. Implementation phases run one writer per set of files.

---

## 8. Gates and human-only items

| Gate | Applies to |
|---|---|
| Owner go | Any commit, push or PR; Phase 0 branch work |
| Registered graded run | Anything that changes which answers are served: R6, general-knowledge lane, judge or scorer changes, graph-on/off decisions |
| Store procedure (dry-run, snapshot, approval, apply) | Any Qdrant, OKF or Memgraph write |
| Owner decision | CI triggers (EM-10), deleting dormant modules, retiring a knowledge component, answerability-gate flag (T-E1) |
| Human reviewers (pending, never faked) | Native-speaker and clinician review of crisis lists; 299-pair gold batch; helpline phone confirmation; rights sign-off |

---

## 9. Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| Another session edits the same files | High | Phase 0 ownership agreement; separate branch; never revert their changes |
| A refactor changes served answers silently | Medium | R2 snapshot diff required for every refactor |
| Crisis lexicon changes reduce recall | Medium | Safety scenarios plus the human crisis set before and after; deterministic floor kept |
| Usage limit kills long multi-agent runs | High | Small staged steps, results saved to `audits/work/` after each |
| Local success taken as production readiness | Medium | Final report separates proven locally, measured in a registered run, pending human approval, and unmeasured in production |
| Cleaner change makes rebuilds produce new point ids (EM-03) | Medium | Fix before any rebuild; fixed-point check in R3 |

---

## 10. Validation commands

```bash
cd backend && .venv/bin/pytest -q -p no:cacheprovider
```
```bash
backend/.venv/bin/python3 evals/run_safety_scenarios.py
```
```bash
make verify-stack-fresh
```
```bash
cd backend && .venv/bin/python3 scripts/ops/fp_data_quality_scorecard.py
```
```bash
npm run lint && npm run test -- --run
```

---

## 11. Acceptance

- [ ] Phase 0 done: separate worktree, separated files, rebuilt container, new full-suite baseline.
- [ ] R1 and R2 exist and reproduce; every later refactor shows an identical snapshot.
- [ ] EM-03 closed: the cleaner changes no stored clip beyond the pre-`d5bed8dd` 6 on v10 and 0 on v8.
- [ ] EM-03b closed through the store procedure: stored v10 text is a fixed point of the cleaner.
- [ ] Every mission area A-L has its deliverable saved, with evidence and a status per finding.
- [ ] Served-answer changes went through one registered graded run.
- [ ] Opus adversarial review of the full diff and independent Haiku verification recorded.
- [ ] Task list and `OUTSTANDING_ISSUES.md` updated; no new parallel register.
- [ ] Final report states what was proven locally, what was measured, what awaits human approval, and what is unmeasured in production.

**WAITING FOR CONFIRMATION:** proceed with this plan? (yes / modify / reorder)

---

## 12. Unified plan (2026-11-16, supersedes the phase order above for the next two weeks)

Owner instruction 2026-11-16: "unify all the outputs made into a single plan and then run subagents with sonnet and haiku to get these implemented end to end". Evidence: `docs/research/reports/Answer wiring and data quality.md` and its notes folder `docs/research/research_notes/Answer wiring and data quality/` (data_quality, wiring_map, stitched_answer_design, router_railway_pending, harness_review, config_flags). Earlier review: `docs/reviews/2026-11-16-railway-readiness-and-plan-review.md` (its "intent Jev flag is False" line is wrong: live True, but 0 Jev decisions in 24 h; ambiguous-domain branch is off).

### 12.1 Measured today (local stack)
- `scripts/ops/railway_answer_smoke.py` (new): crisis 3/3 (14416, instant), out-of-corpus abstain 3/3, runbook "fade after marriage" served 2/2, runbook "happy family" **abstained 3/3** (relevance judge 1-2 on all 16 contexts). Do not use "happy family" in the demo until U1 lands and it passes.
- Judge: 16 contexts scored in parallel; timeouts become silent abstains (no retry); one indeterminate at index i blocks all j>=i; RPM limiter stalls bursts (limiter wait 8.6-9.3 s). HyDE: about half of calls cancelled at 2.5 s.
- Graph and OKF expansion run but cannot change the clip: v10 `topic_ids`/`entity_ids`/`facet_ids` empty on all 2,758 children, no `tags`. Only Qdrant + HyDE pick the clip. Personalization does not shape the clip. Nothing joins clips.
- Data: median clip 24 s, p95 125 s, 12.5% in the 18-25 s band, 17% contained in another clip. Resegmentation is not built (shadow builder copies v10 unchanged; dry-run clips 455-630 words).
- Config: 178 flags; 2 dead; 24 live values differ from code defaults (Railway gets code defaults unless pinned).

### 12.2 Work packages
| ID | Work | Agent | Gate | Done when |
|---|---|---|---|---|
| U1 | Judge harness fixes: retry once on judge failure; in parallel mode an indeterminate no longer blocks later contexts; bounded concurrency (4); log indeterminate count | Sonnet | Serving change: smoke now, registered graded run before claiming quality | Unit tests both paths; smoke "happy family" re-measured |
| U2 | Railway variables pinned in `.railway/railway.ts` for the live posture (posture trio, min score, speaker-verified, escalation, sparse, rerank, hash check as decided), contradictions removed; guard test | Sonnet | Owner applies on Railway | Test fails if a posture var is unpinned |
| U3 | Config cleanup, safe tier: delete 2 dead flags; hard-code always-on privacy/spend/fail-closed flags (`fp_fail_closed_enabled`, `openrouter_budget_fail_closed`, `llm_budget_fail_closed`, `openrouter_require_no_training`, `ollama_cloud_only`) | Sonnet | None (behaviour identical on live) | Suite green; flags gone from config/compose/example |
| U4 | Graded harness trust: rubric and grader prompt hashes in `grades.json`; per-grader rates and Cohen kappa in the report; held-out sets reported separately | Sonnet | None | Report shows hashes, kappa |
| U5 | Verify all of the above: full backend suite, safety scenarios, smoke | Haiku (read/run only) | None | Logs saved |
| U6 | `/api/first-person/query` skips DistressStage: add crisis pre-check | Opus (safety rule) | Safety evals + clinician note | Scenario test passes |
| U7 | Enrich v10 spans with topic/entity/tag ids offline (so graph/OKF lanes can match), review gate, store procedure | Sonnet + owner | Store write: dry-run, snapshot, approval | Filtered query returns hits |
| U8 | Resegmentation for real: boundary algorithm with cap (owner: proposed p95 ≤ 90 s, max 160 s), new collection, host-side embeddings, registered run | Other session + owner | Owner cap decision; registered run | Targets in 12.3 |
| U9 | Multi-clip answers: selector returns clip ids only, server renders text, verifier exact-match + one judge, default-off flag; personalize reuses it with cache bypass | Sonnet after U7 | Owner decision on invariant 15 (connectors templated or LLM); registered run | Graded run vs single-clip |
| U10 | Held-out human-labelled set (150-200 questions) | Human | Human-only | Sealed file with hash |

### 12.3 Decidable data-quality targets (proposed, not owner-approved)
Showable both graders Wilson LB ≥ 0.85 on ≥ 30 served and served share ≥ 0.30; clip p95 ≤ 90 s, max ≤ 160 s; contained ≤ 5%; same clip across 3 runs ≥ 95%; no clip serves > 3 questions; recall@10 of a showable clip ≥ 0.85 on a v10 label set. The 116-question set can fail the bar but never certify it (about 200 served answers needed).

### 12.4 Owner decisions needed
1. Invariant 15: may an LLM write connector text between clips, or templated labels only?
2. Clip length cap for resegmentation.
3. `FIRST_PERSON_RELEVANCE_MIN_SCORE` on Railway: 3 (local, graded) or 2 (code default, weak-match serving).
4. `first_person_points_servable_hash_check_enabled` is off live, although invariants 8/13 describe the re-check.
5. Demo framing: diagnostic, no quality-bar claim.
