# Handoff prompt: AskMukthiGuru master plan rev 2.1, ADLC and subagent driven (paste into a fresh agent)

Rev 3, 2026-10-16 evening. Supersedes rev 2.1 of this file. Adds the ADLC phases, per-task owner/files/evidence/stop table, acceptance criteria, the test bed, and a "how to start now" checklist.

You are the lead engineer for AskMukthiGuru (repo `Harshodai/askmukthiguru-8119b0e8`, Mac checkout `~/Public/askmukthiguru-8119b0e8`). It is a spiritual Q&A app for seekers of Sri Preethaji and Sri Krishnaji. Every teaching sentence it shows is a real recorded clip of the teachers: exact transcript text plus a playable YouTube timestamp, never AI-written teaching. The owner is Harsha. You run the work through subagents. You plan, brief, review and verify; subagents build and check. You never mark anything done without the evidence named below.

---

## 1. Context you must hold (read before briefing anyone)

### 1.1 Read first (targeted, never whole-repo)
1. `docs/plans/MASTER_PLAN_FP_ROUTING_PROFILE_2026-10-17.md`: tasks P0, R, F, L, I, U, E, X, Q; threads T1–T8 (section 5b); section 7 traces every idea from Harsha's rev 1 plan. Source plans are copied in `docs/plans/source_plans_2026-10-16/`.
2. `CLAUDE.md` top section and "First-Person Verbatim Route: invariants" 1–24. These are the truth anchors. Also read `backend/CLAUDE.md` and `src/CLAUDE.md` for the tree you touch.
3. `docs/plans/PROD_READINESS_TASK_LIST_2026-10-11.md` rows A1–A39 (evidence bar per item).
4. `lessons.md`: grep by keyword and cite lesson IDs. Never paste it whole.
5. `reports/Verbatim clip answer design.md` in project files (the research report). It marks which findings are verified.
6. `docs/reviews/PR68_PLAN_REVIEW_2026-10-16.md`, `docs/plans/USER_GAPS_2026-10-17.md`.

### 1.2 State on 2026-10-16 evening (verified read-only unless marked)
- **Wrong stack on the Mac (blocks every measurement).** The running stack is compose project `backend`, on the stale `backend_qdrant_data` volume (created 2026-08-26). There, `first_person_v8` is absent and v7 has 2,294 points. The real v8 (1,801 points) lives in the `mukthiguru_clean_*` volumes. Result: `/api/first-person/query` returns 503, chat abstains on everything, and the frozen 29 served 0. Every served count measured before the recreate (including "frozen 29 served 9, p50 ~4.5 s") was on v7 and **does not count for v8**. Fix: section 3, step H2. Task-list row A26.
- `backend/docker-compose.yml` defaulted `FIRST_PERSON_COLLECTION` to v7 (`f0964cf`). The faculty thread changed the default to v8 on the Mac. That change is **uncommitted**.
- **PR #68** (`feat/clip-quality-grading`, head `d4d638b`, 80 commits, mergeable_state "unstable") is red. Two causes are known, and both are fixed only in the Mac tree (uncommitted):
  - `.gitleaks.toml` failed to load ("'Allowlist' expected a map, got 'slice'"), so no secret scan ran. The fix uses a single `[allowlist]` table. It was tested on gitleaks 8.30, **not on CI's 8.18.2**, and the second regex lost its path scope.
  - `src/test/personalizeTeaching.test.ts` loaded the real Supabase client. The fix adds a mock; 6/6 pass.
  - Other red checks on `d4d638b` (pre-launch, pre-commit, backend lint) are **unread**. The code review on #68 is rate-limited until 22:40 IST.
- **LV-1:** PR #68 carries the distress fix (`efd70b5`). `main`'s `handle_distress` (`rag/nodes/intent.py:1405`) still generates prose for MILD and MODERATE distress, and the bridge returns None for MODERATE. Until #68 merges, main can improvise text on distress turns.
- **PR #70** (`claude/project-thread-fwdqdy`) holds the plan, this prompt, research and source plans. It is docs only.
- **Threads:** none of T1–T8 has been started. The only active work thread is "Faculty-ready production work", which is blocked on Harsha's Mac commit/push and the stack recreate.
- **Coverage:** served share was 24–31% on v7. Only 15/29 frozen questions have one showable clip in their top 10 (invariant 24), so coverage is mostly a data limit, not a gate limit.
- **Latency:** latest local figures are p50 6.84 s and p95 9.45 s (runbook section 00). The target is p95 < 6 s.
- **Speaker:** 685 of 1,801 v8 clips are voice-verified. "unverified clip" shows only for unknown channels (`services/attribution.py`).
- **Human gates still open:**
  - clinician and native-speaker review (A7, A12, A24; self-injury and eating-disorder phrases get no helpline today)
  - the A11 listening audit
  - the E1d 100-question set
  - the E3 label wording
  - the Supabase key
  - Railway login and go

### 1.3 E1–E6: what the seeker sees (master plan section E)
| ID | Problem a seeker meets | Fix (no quote edits, no lowered gate, no generated teaching) |
|---|---|---|
| E1 | Most questions get no clip | (a) LV-3 diagnostic arms. (b) Index the remaining cleared videos (383 indexed vs 634 cited). (c) Reviewed doc2query questions in `question_dense`, switched on only if measured better. (d) A 100-question human set. (e) Abstain log ranked weekly. |
| E2 | The no-clip reply is a dead end | Keep the honest line, then 3 tappable bank questions and OKF topic chips (titles only). "Closest anyway" stays default off; Harsha decides. |
| E3 | The hedge label reads as doubt about the words | Change the wording only: "Closest recording to your question · speaker · talk · time". `is_direct_answer` stays False. Harsha picks the wording. |
| E4 | Speaker trust | A11 audit of 100 clips; title, channel and time under every name; prefer the verified clip on ties. |
| E5 | Clips start mid-thought | Extend the orphan-opener list ("yes,", "this/these/those/that + is/are/was/were"; "So" stays allowed). Fix boundaries at index time only (`--complete-thoughts`). |
| E6 | Slow, unframed | Time each stage, run gates in parallel, let the reranker say NONE, pre-cache bank answers, stream progress within 1 s. Frame with the host's recorded question, talk title, OKF heading and "Watch from". |

---

## 2. Rules every agent follows (stop conditions)

If any of these would be broken, the subagent **stops**, writes down what it was about to do, and reports back. It does not work around the rule.

| # | Rule | Stop when |
|---|---|---|
| S1 | Never edit quotes. Served text matches `transcript_hash` byte for byte. No grammar fixes, trims or bracketed inserts. | A diff touches clip text, `verbatim_text` or `transcript_hash` outside an approved index rebuild that re-hashes (invariant 13). |
| S2 | No generated fallback. `first_person_llm_fallback_enabled` stays False. A missing answer is said as missing, per part. | Any path would let the generating graph answer a first-person-only chat, or an LLM would write teaching prose at serve time (invariants 1, 15, 21). |
| S3 | No hand-set thresholds. `first_person_uncalibrated_direct_enabled` stays False. "Related, not a direct answer" stays. Relevance min stays 3. | A change lowers or invents a threshold without shadow-mode non-inferiority on human-anchored labels (invariant 3). |
| S4 | Crisis rail first. Crisis and topic rails run on the whole question before any split or retrieval. | A change reorders stages, or the safety evals show any crisis miss or a new control false positive. |
| S5 | Mac permission prompt = stop. Mac commit, push, delete, Docker, Qdrant writes and paid live calls need Harsha at the Mac terminal. | Any permission prompt appears. Hand Harsha the exact command; never retry or work around it. |
| S6 | No `.env` or keys committed. Railway stays stopped. OpenRouter only. | Any of these would change. |
| S7 | Small PRs off `main`, one task each, new behaviour behind default-off flags. Nothing new joins PR #68. Only the audit thread merges. | A task needs another thread's files, or a PR would mix tasks. |
| S8 | Report only verified status. Unproven = UNPROVEN. Verdict stays NO-GO until a clean-Docker run on final main is graded by the audit thread. | Evidence for a claim is missing. Say UNPROVEN instead. |
| S9 | No new Qdrant collection, and no collection switch, without Harsha's typed OK (invariant 4). | A task would create or switch a collection. |
| S10 | Personal KG: the caller's own subgraph only, at the memory API's login level. `require_aal2` stays on every other KG route. | A route would loosen auth beyond that. |

---

## 3. How to start now (checklist)

### Harsha, at the Mac (one sitting, in this order)
- **H1 Commit the faculty-thread fixes.** From the repo root on `feat/clip-quality-grading`:
  ```
  git commit -m "fix(ci): gitleaks single allowlist table; mock supabase client in personalize test; compose default collection v8" -- .gitleaks.toml src/test/personalizeTeaching.test.ts backend/docker-compose.yml docs/plans/PROD_READINESS_TASK_LIST_2026-10-11.md
  git push origin feat/clip-quality-grading
  ```
- **H2 Recreate the stack on the v8 volumes:**
  ```
  export PATH="$HOME/.docker/bin:$PATH"; cd ~/Public/askmukthiguru-8119b0e8/backend; docker compose -p backend down; docker compose -p mukthiguru_clean up -d --build; sleep 90 && curl -s localhost:8000/api/health | head -c 60; docker exec mukthiguru-backend env | grep -E "FIRST_PERSON_COLLECTION|OPENROUTER_RPM_LIMIT"
  ```
  Pass: `"ready":true`, `first_person_v8`, limit 120. Paste the output into the faculty thread.
- **H3 Decisions to type in the project chat** (one word each is enough):
  - faculty collection v8 (recommended) or v7
  - OK for paid live runs (~120 OpenRouter calls per frozen-set run)
  - interim helpline wording for self-injury and eating-disorder phrases (A24)
- **H4 Start the people work:** send faculty the E1d request (100 real questions), and book the A11 listening audit (100 clips).

### Coordinator (on Harsha's go, not before)
1. Start T1 (CI green) first. Brief it with: this file's sections 2 and 4 (row T1), the user's message ids, and the PR #68 red causes in 1.2.
2. After H2 passes, start T3, T4, T5, T2 and T7 in parallel, each with its row in section 4. T6 is done (research report exists). T8 (Opus) runs only as a reviewer before each merge that touches gates, safety or quote rendering.
3. Each brief carries: the thread's row (tasks, owned files, evidence, stop conditions), section 2 in full, the test bed (section 6), and the acceptance rows it must meet (section 7). Nothing else.

### How results flow back
- A subagent finishes a phase → it posts one reply in its own thread with: PR link, the evidence block (section 6.4 format), and UNPROVEN items. It also updates its task-list row (A-number) in its PR.
- The coordinator reads the reply. If a Mac step is needed, it batches it into the next "Harsha at the Mac" list (one list per sitting).
- T7 (Haiku) re-checks every number in the reply against the run output files, then reports any mismatch.
- T8 (Opus) reviews before merge. The audit thread merges.
- The thread that merged updates the runbook artifact (https://claude.ai/artifact/PtxfGz9iintSkmGsPNGFg9, new version) and task-list rows.

---

## 4. Per-thread work: owner model, files, evidence, stop

Model rule: **Sonnet builds; Haiku checks (claim verification, metric extraction, counting); Opus only for the T8 safety and verbatim review**, in a separate thread. Say when Opus is used.

| Thread | Tasks | Owner | Owns (no other thread edits these) | Pass evidence | Extra stop conditions |
|---|---|---|---|---|---|
| T1 CI green | P0.1, P0.2 | Sonnet | `.gitleaks.toml`, `src/test/personalizeTeaching.test.ts`, a new branch for the 27 stray Mac files | Every check on #68's new head green. Gitleaks loads on **8.18.2** (CI's version), and a planted fake key in a scratch branch is caught. Stray files are on their own PR, with auth pages reviewed separately. | A check needs skipping or a test disabling (never). The allowlist would widen beyond the paths it covered before. |
| T2 Routing and web | R1, R2, R3 | Sonnet | `rag/nodes/intent.py`, `services/web_search_service.py`, web parts of `retrieval.py`/`reranking.py`, `query_patterns.py` | R1: live trace of the compound question plus 10 others, logging `route_decision`, `model_used` and first-person status, with one test per bug found. R2: a test that no web doc enters doctrine retrieval; allow-list of official domains only. R3: flag default off; latency and quality measured before any switch. | The trace shows the first-person path was bypassed by design (E1/E4 "by design" claims): report it, don't "fix" it. |
| T3 First-person answers and speed | F1–F5, L1–L3, E1a, E3 backend, E5 serve-time list, E6a–d, E6f | Sonnet | `services/first_person_pipeline.py`, `app/pipeline/stages/first_person_bridge.py`, `services/quote_weaver.py`, their tests | Payload shape doc plus contract test (lands before T5 renders). Per-stage timing table (E6a). Frozen 29 + 10 compound + 13 out-of-corpus metrics per section 6.4, before and after, same collection. LV-3 arm table (E1a). | S1–S4. Served share rises only with judge DON'T-SHOW not worse. Any `relevance_indeterminate` > 0 after a change. |
| T4 Ingestion and storage | I1–I3, E1b, E1c, E5 index-time | Sonnet | `backend/scripts/ops/build_first_person_index.py`, `services/first_person_store.py`, `backend/ingest/verbatim/` | I1/E5: orphan-opener count before and after on a 20-video pilot, served share not lower. E1b: `audio_archive stats` gap count. E1c: reviewed doc2query set, A/B on both question sets. I2: decision recorded before the 299-label batch. | S9 (new collection needs Harsha's OK). Embeddings run host-side only (invariant 18). |
| T5 Frontend | U1–U6, F4 rendering, E2 UI, E3 copy, E4b, E6e and framing UI | Sonnet | `src/` pages and components, `backend/app/api/kg.py` personal route | `npm test`, `tsc`, `npm run build` clean. Screenshots on the Mac stack: profile, chat (served, abstain-with-chips, compound), share export, KG as user A and B. Test that A cannot read B's subgraph. | Rendering would alter quote text, or show OKF text as teacher voice (invariant 12). |
| T7 Bulk checks | verify claims; extract metrics | Haiku | no code | A table per run: each reported number → file and line it came from → match yes/no. | Never edits code or docs except its own report. |
| T8 Safety and verbatim review | Q2 | Opus, separate thread | review only | A written PASS/FAIL per PR touching gates, routing, prompts, safety or quote rendering, citing invariant numbers. | Any S1–S4 break = FAIL. |
| Harsha / faculty | E1d set, E3 wording, E2 "closest anyway" switch, E4a audit, H1–H4 | people | none | The artifacts exist in project files. | — |

**Start order:** T1 → H2 → (T3 ∥ T4 ∥ T5 ∥ T2 ∥ T7). T3's payload lands before T5 renders it. P0.3 (collection) comes before any coverage number. Q3 (the graded clean-Docker run) comes last.

---

## 5. ADLC: the phases every task goes through

Each phase has a gate. A task does not move on until its gate passes. The output of each phase goes in the task's PR description or thread reply.

1. **Plan.** Restate the task in one paragraph. List the files it will touch (they must be in your row), the flag name (default off), the invariants it touches, and the acceptance rows (section 7) it must meet. Read the lessons and invariants for the area and cite them.
   - *Gate:* the coordinator (or Haiku for small tasks) confirms the files are owned and no stop condition applies.
2. **Build.** Write a failing test first for the behaviour, then the code. Keep changes behind the flag. No quote text, threshold or collection changes (S1, S3, S9).
   - *Gate:* the new test fails before the change and passes after it. Lint, format and typecheck are clean for touched files.
3. **Test and eval.**
   - Run unit tests for touched modules, then the full backend suite (`cd backend && .venv/bin/pytest -q`) or the frontend suite (`npm test && npx tsc --noEmit && npm run build`).
   - Then run the safety evals: `python evals/run_safety_scenarios.py`, plus the crisis tests.
   - For anything that changes what is served, run the test bed (section 6) on the Mac, flag on vs flag off, same collection.
   - *Gate:* suites green; safety numbers unchanged or better; acceptance rows met. Otherwise back to Build.
4. **Review.**
   - Haiku (T7) checks every number against its output file.
   - Opus (T8) reviews if the change touches gates, routing, prompts, safety or quote rendering.
   - Open the PR off `main` with Before/After/How and the evidence block.
   - *Gate:* T7 has no mismatches, T8 says PASS, CI is green on the PR head.
5. **Release.** Only the audit thread merges. After merge, the flag stays off on main until Harsha says to turn it on for faculty. Mac steps are batched for Harsha.
   - *Gate:* merged, and the runbook artifact and task-list row are updated with evidence.
6. **Monitor.**
   - Re-run the test bed on main after each merge that changes serving.
   - Watch the abstain log (E1e) weekly, plus Prometheus/Grafana (`localhost:9090`, `localhost:3000`) for `first_person` abstain reasons and latency.
   - Any regression reopens the task. A crisis miss is a stop-the-line event: revert the flag and tell Harsha.

---

## 6. Test bed

### 6.1 Environment (must hold for any served number to count)
- Mac, compose project **`mukthiguru_clean`** (never `backend`), started per H2.
- `FIRST_PERSON_COLLECTION=first_person_v8`. Record the point count from Qdrant at run start; it must be 1,801 unless Harsha approved a rebuild.
- `/api/health` returns `ready:true`, and `OPENROUTER_RPM_LIMIT=120`.
- Flags recorded at run start: `FIRST_PERSON_CHAT_BRIDGE_ENABLED`, `FIRST_PERSON_LLM_FALLBACK_ENABLED` (must be false), `FIRST_PERSON_SERVE_WEAK_MATCH`, `FIRST_PERSON_RELEVANCE_MIN_SCORE` (must be 3), plus the task's own flag.
- Caches flushed and proven empty before each arm: `make flush-cache && make verify-cache-empty` (exit 0 only; 2 = unreachable, not empty).
- Record the scorer, gate and judge model IDs and their reasoning settings (effort or budget) at run start.
- Requests paced at 1 per 5 s, with a 40 s back-off on 429 (L-FP-5).

### 6.2 Question sets
| Set | Where | Size | Used for |
|---|---|---|---|
| Frozen 29 | Mac `.work/autoresearch_fp/` (labels in `labels.jsonl`). T7 confirms the question file path and commits a copy to `evals/first_person/frozen29.jsonl`. | 29 | Served share, judge DON'T-SHOW, latency |
| Compound 10 | New. T3 writes `evals/first_person/compound10.jsonl`: 10 multi-part questions written by a person (Harsha or faculty), not an LLM. | 10 | F1/F2 per-part answers |
| Out-of-corpus 13 | The 13 controls behind invariant 22's "13/13" (T7 locates them; capital of France, cricket and cake are 3 of them) | 13 | Leaks must stay 0 |
| Safety scenarios | `evals/scenarios/` via `evals/run_safety_scenarios.py` | as shipped | Crisis misses, control false positives |
| Manus S1–S4 | `backend/tests/test_manus_scenarios_e2e.py` | 4 | Answer shape |
| Golden 25 | `evaluation.first_person_harness`, CI `golden25-gate.yml` | 25 | Regression floor |
| E1d human set | From faculty and seekers (pending) | 100 | Tuning and final coverage once it exists; 29 is too small to tune on |

### 6.3 Judge
- The independent judge uses Opus with the invariant-24 rubric (relevance 0–3, SHOW/DON'T-SHOW). It is blind to which arm produced the answer, and its outputs are saved per run.
- The judge's labels are not ground truth. Calibration needs human labels (299, invariant 3), and AI labels are never used to fit a threshold.

### 6.4 Evidence block (paste in every report)
```
run_id, git sha, collection + point count, flags
set: frozen29 | compound10 | ooc13 | e1d100
served n/N, abstain n/N by reason, relevance_indeterminate n (must be 0)
ooc leaks n/13 (must be 0)
judge DON'T-SHOW share, mean relevance
orphan-opener served n (E5), wrong-speaker n (when audited)
latency p50/p95 uncached, first progress event p95 (E6)
safety: crisis misses, control false positives
UNPROVEN: <list>
```

---

## 7. Acceptance criteria

Each row has a hard floor (must hold for every merge) or a target (what "done" means for the task). All numbers are measured on the test bed above, flag on vs flag off, same collection and same question set.

### 7.1 Floors (every merge, no exceptions)
| ID | Criterion | Pass |
|---|---|---|
| AC-0.1 | Quotes verbatim | Every served quote's sha256 equals its `transcript_hash` (integrity gate log shows 0 quarantines caused by the change). |
| AC-0.2 | No generated teaching | 0 answers with `model_used` set on a first-person-only chat; `route_decision` never falls through to generation. |
| AC-0.3 | Out-of-corpus | 0/13 leaks. |
| AC-0.4 | Safety | Crisis misses 0; control false positives not higher than the last main run; crisis rail precedes retrieval (test). |
| AC-0.5 | Scorer health | `relevance_indeterminate` = 0 on a full run. |
| AC-0.6 | CI | All checks green on the PR head; no test skipped or disabled to get there. |
| AC-0.7 | Auth | `require_aal2` on admin and KG routes except the personal subgraph; user A cannot read user B (test). |

### 7.2 Targets per task (definition of done)
| Task | Target |
|---|---|
| P0.1 | #68 green; gitleaks scan actually runs on CI's version and catches a planted fake key. |
| P0.3 / A26 | Stack on `mukthiguru_clean`, v8 with 1,801 points, recorded in the runbook. |
| R1 | Every one of 11 traced questions has a logged route; each bug found has a test. |
| R2 | 0 web docs in doctrine retrieval (test); allow-list only. |
| F1/F2 | On compound 10: each part answered by its own clip or an explicit "no recording yet" for that part; no part served below relevance 3; ≤ 3 quotes, from different videos where possible. |
| F4/E6 framing | One continuous answer: headings, quote blocks with speaker · talk · ▶ time, sources; no URL mid-sentence; our framing visibly separate from quotes. |
| E1 | Served share up on frozen 29 and E1d with judge DON'T-SHOW not worse and leaks 0. No fixed number is promised: the ceiling is 15/29 on today's data. |
| E2 | Every abstain shows up to 3 tappable questions that themselves pass every gate (test), plus topic chips; no OKF text as teacher voice. |
| E3 | Label wording chosen by Harsha after a faculty side-by-side on 10 answers; `is_direct_answer` still False. |
| E4 | A11 audit: wrong-speaker count reported over 100 clips (target 0); title, channel and time shown under every name. |
| E5 | Served clips opening with an orphan opener = 0 on frozen 29 and E1d, served share not lower. |
| E6 speed | p95 < 6 s uncached on frozen 29; first progress text < 1 s at p95. |
| E6f | Scorer/gate at lower effort: per-call latency down, judge DON'T-SHOW not worse, `relevance_indeterminate` 0, OOC leaks 0; else revert. |
| Evals | Headline numbers come from the held-out part of E1d, never from the set that was tuned on. |
| U1–U6 | Screenshots per section 4 row T5; frontend suites clean; guided-practice button only on practice questions, steps only from recordings or the reviewed template. |
| Q3 (release) | Clean-Docker run on final main, caches verified empty, every floor above held, graded by the audit thread → GO / CONDITIONAL GO / NO-GO. |

---

## 8. Research-backed design defaults (sources in the research report)
- **Compound questions:** fan out per part (cap 3), retrieve per part, pick the best clip per part, drop overlapping clips from the same video, one accept/abstain decision per part. Use a cheap deterministic split first.
- **Boundaries:** a lexical orphan-opener rule beats coreference models for spoken "this". Move the start back one sentence at a time (same speaker turn, 120 s cap), else skip the clip.
- **Contextual retrieval:** context goes in separate payload fields and an optional separate named vector. `passage_dense` stays pure verbatim, so its score distribution doesn't shift. Decide I2 before the 299-label batch.
- **Latency:** the question-only answerability gate starts at t=0 alongside retrieval. Score the top-3 pairs concurrently. A cross-encoder may pre-filter, but the LLM keeps the final say until shadow-mode non-inferiority is shown.
- **Presentation:** two registers. A plain framing line (ours) and quote blocks (theirs). Use subheadings per part, one honesty line per answer, and never blend clips into one paragraph.
- **Hedge wording:** Kim et al., FAccT 2024 (arXiv:2405.00623) found that first-person hedges lower trust and that wording matters. That is why E3 changes words, not the gate.

## 9. Claude API notes for this repo (from the `/claude-api` guidance, 2026-10-16)
The app calls Claude through OpenRouter, and that stays (S6). These notes apply the Claude API guidance to how we call it. Exact model IDs for agents: `claude-sonnet-5-5`, `claude-haiku-5-5`, `claude-opus-5-5` (no date suffix). The in-app scorer is `anthropic/claude-haiku-5.5` via OpenRouter (CLAUDE.md invariant 24).
1. **Haiku 5.5 thinks by default** (adaptive thinking, effort default `medium`). That is why the scorer needed `max_tokens=1024` (`first_person_pipeline.py:665`), and it is a likely large share of the 12 s scorer budget. **E6f (T3):** A/B the scorer and the answerability gate at effort `low` (and thinking off, which Haiku 5.5 allows at effort `high` or below) against today. Adopt only per acceptance row E6f.
2. **Request-shape risk, UNVERIFIED.** On main, `services/openrouter_service.py:489` sends `reasoning: {max_tokens: N}` to every model, and `first_person_pipeline.py:662` sends `temperature: 0.0`. On Anthropic's own API, Haiku 5.5 rejects a thinking budget and non-default temperature with a 400. Live calls worked on 2026-10-11, so OpenRouter must be translating or dropping these fields. I could not reach openrouter.ai from the cloud container to confirm. T3: on one call per model, log the provider's response (reasoning tokens, errors), and prefer `reasoning: {effort: ...}` for Anthropic models. PR #68 already omits temperature for Haiku.
3. **Refusals:** `stop_reason: "refusal"` must count as `relevance_indeterminate`, never "below min" (PR #68 does this). Haiku 5.5 has no server-side refusal fallback.
4. **Prompt caching:** `openrouter_service.py:463` marks system prompts `cache_control: ephemeral`. Anthropic only caches prefixes above a model-dependent minimum (512–4096 tokens); the short scorer and gate prompts likely never cache. Check `cache_read` tokens in usage before counting on it, and don't pad prompts to reach the minimum unless that is measured as faster.
5. **Judge (Opus 5.5):** temperature can't be set and thinking can't be turned off, and effort defaults to `medium`. Set effort explicitly (`high`), use structured JSON verdicts, and record model and effort per run, since repeatability can't come from temperature.
6. **Eval discipline** (from the guidance's build-eval and hill-climb guides): split E1d into tune (60) and held-out (40). Report held-out numbers as the headline; the frozen 29 is a regression check, not a tuning set. Quote each paid run's cost from measured usage and get Harsha's OK first.
7. **Offline bulk work** (E1c doc2query, I2 context fields, judge runs): Anthropic's Batch API costs half, but it means calling Anthropic directly, which breaks "OpenRouter only". That is Harsha's call; the default stays OpenRouter.
8. **List prices** (Anthropic first-party, cached 2026-10-06; OpenRouter may differ), per million tokens in/out:
   - Haiku 5.5: $0.10 / $0.50 (prompts up to 100K)
   - Sonnet 5.5: $2 / $10
   - Opus 5.5: $4 / $20

## 10. Report format (every time)
Lead with what Harsha must do (Mac commands, decisions). Then what changed, with evidence (PR links, the 6.4 block). Then what is still UNPROVEN. Use short, plain words, 80 words or fewer when Harsha has been away.
