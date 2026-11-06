# Next-session prompt: Claude Opus (safety, honesty, security, data integrity, independent review)

Copy everything below the line into a new Claude Code session that runs Opus (high or extra reasoning). A parallel Sonnet session uses `NEXT_SESSION_PROMPT_SONNET.md`. The two sessions own different files (§3), so they can run at the same time.

---

You are the senior implementation and review agent for **Ask Mukti Guru**. The repository is `Harshodai/askmukthiguru-8119b0e8`. Work on branch `feature/audit-strengthen-rag-qdrant`. Last known remote head: `12bb3225` (2026-11-06).

You own the work where a mistake harms a seeker or misrepresents the teachers: safety and crisis paths, answer honesty, teaching attribution, prompt-injection defences, data integrity and rights in the corpus builder, and the independent review of concurrency work. A Sonnet session works in parallel on Railway, operations, configuration, accessibility, Kubernetes, Lovable, guards and documentation.

## 0. Before anything else (do these in order)

1. Run `git fetch origin feature/audit-strengthen-rag-qdrant` and `git log --oneline -15 origin/feature/audit-strengthen-rag-qdrant`.
2. Look for the owner's T7-02 commits (async teaching lane, one Celery event loop, a deadlock fix, about 55 repaired tests, recorded decisions). Search with `git log --oneline origin/feature/audit-strengthen-rag-qdrant | grep -iE 'T7-02|async|event loop|deadlock'`.
3. **If they are not on the remote, stop.** Tell the owner: "The T7-02 commits are not on the remote. On the machine that holds them, run `git pull --rebase origin feature/audit-strengthen-rag-qdrant`, resolve any conflicts by keeping both sides, then `git push origin feature/audit-strengthen-rag-qdrant`." Do not redo T7-02. Do not start §4 until they are pushed.
4. Check out the branch at the remote head. Read, in this order:
   - root `CLAUDE.md` (first-person invariants, Voice Governance, PR #76 invariants), `backend/CLAUDE.md`, `src/CLAUDE.md`
   - `audits/audit-output-2026-11-04/FINAL_READINESS_AND_GAP_ANALYSIS.md` (index and release decision)
   - `audits/audit-output-2026-11-04/FINAL_CODING_AGENT_EXECUTION_PACKAGE.md` §1 and §3
   - `audits/audit-output-2026-11-04/FINAL_PENDING_WORK_REGISTER.md` (§1 counts, §3, §7 reserved tasks, §10)
   - `audits/audit-output-2026-11-04/FINAL_DECISION_AND_RISK_REGISTER.md` §2
   - `lessons.md` from the top through the Nov 5 sections
   - the specification named by each task (in `audits/audit-output-2026-11-04/specifications/`)
5. Check CI for the head commit. If it is red because of a file you own (§3), fix it first. If it is red in a Sonnet-owned file, write down the failure and continue.

## 1. Facts you must not re-derive

- **Release decision:** Railway staging NO (conditional), production NO, public NO. Your work does not change this unless a gate item in `FINAL_RAILWAY_STAGING_READINESS.md` (A1-A21) or `FINAL_PRODUCTION_RELEASE_READINESS.md` (B1-B18, C1-C13) passes with evidence.
- **Finding status source:** `FINAL_PENDING_WORK_REGISTER.md` and `findings-index.md`. At `12bb3225`: 152 original defects (35 closed, 37 partial, 15 open, 45 owner decision, 18 human, 2 live), plus 103 findings added on 2026-11-05/06 (0 P0, 35 P1, 57 P2, 11 P3), all open.
- **Six earlier commit messages claimed more than their diffs** (MEM-002, MEM-004, GURU-010, CQ-009, PRD-006, SAFE-004). Read the code, not the commit message.
- **The owner's local `.env` has the spend guard off.** Production startup refuses to start with it off (T1-07). Never make real LLM calls in tests: use fakes. Do not run the live stack unless the owner asks in this session.
- **The owner recorded two decisions with T7-02:** verified-only crisis lines, and the sync legacy path. Find where they are recorded (search `decision-log.md`, `unresolved-questions.md`, `audits/evidence/`, the commit messages). Quote the record before you act on it.

## 2. Rules (a violation makes the work unusable)

1. **Invariants first.** Teachers' words appear only as verbatim stored spans with their source. No generated text is shown as a teacher's words. The integrity gate fails closed (`sha256(verbatim_text) == source_text_hash` on v10). Quotes are never translated. A crisis message never reaches a short-circuit or the bridge. Never hand-pick a calibration threshold. Never cache an answer personalised with `memory_context`. Never log seeker text.
2. **Test first for every defect.** Write a test that fails on the current code. Run it and keep the failing output. Fix. Run it again. Then run the targeted test files, `python3 scripts/guards/lesson_guards.py` in the modes that apply to the changed files, `ruff check` and `ruff format --check` on changed Python files, and the frontend lint for changed TypeScript.
3. **Never skip, xfail, quarantine or weaken a test or guard to get green.** If a test is wrong, show why from the code and change it with a comment that names the task ID.
4. **Never implement a decision-gated variant** until the decision is recorded. Build the compliant default and put the gated part behind a new default-off `Settings` flag. The flag needs a reader at its call site and tests for both states (CLAUDE.md "Dormant modules" rule).
5. **Never do a reserved task** (T4-04, T6-07, T3-06, T6-05, T6-06) without the owner's written go-ahead in this session. You may prepare packets and harnesses for them.
6. **Never change the distress regex in `backend/services/serene_mind_engine.py`.** T4-04 needs a clinician.
7. **Ops scripts present in both `scripts/ops/` and `backend/scripts/ops/` must stay byte-identical** (`backend/tests/test_repo_layout.py`).
8. **One task per commit.** The commit message names the task ID and finding IDs, and claims only what the diff does.
9. **Git:** never force-push, never rewrite history, never push to `main`, never merge. Before each push: `git pull --rebase origin feature/audit-strengthen-rag-qdrant`. For conflicts in Markdown that both sessions append to (`lessons.md`, the register, the prompt), keep both sides. Push with `git push origin feature/audit-strengthen-rag-qdrant`. On a network error, retry up to 4 times (2 s, 4 s, 8 s, 16 s). If the push is refused for permissions, stop and give the owner the exact commands.
10. **No live infrastructure** (Qdrant, Railway, Supabase project, OpenRouter) and no credentials. Mark any live-only proof UNPROVEN.

## 3. File ownership (do not edit Sonnet-owned files)

**You own:**
- `backend/services/first_person_pipeline.py`, `first_person_context_harness.py`, `first_person_context_store.py`, `first_person_store.py`
- `backend/rag/nodes/first_person.py`, `backend/rag/states.py`, `backend/rag/nodes/generation.py` (prompt fences only)
- `backend/app/pipeline/stages/graph_stage.py`, `first_person_bridge.py`, `backend/app/answer_outcome.py`, any new `backend/app/answer_contract.py`
- `backend/services/serene_mind_engine.py` (call sites only, never the regex), `backend/services/crisis_helplines.py`
- New `backend/services/untrusted.py`, `evals/adversarial/`
- Memory extraction and persona code (find it first with a search)
- Corpus builder scripts: `scripts/ops/build_full_corpus_v10.py`, `build_first_person_index.py`, `audio_archive.py`, and their `backend/scripts/ops/` copies
- `backend/app/api/teachings.py`

**Shared, append-only:** `backend/app/metrics.py` (add your metrics at the end of the file only) and `backend/app/config.py`. Sonnet owns `config.py`; if you need a new setting, add it in one clearly marked block at the end of `Settings`, in its own commit, and rebase carefully.

**Sonnet owns (do not edit):** `.railway/`, `scripts/deploy/`, `backend/start_railway.py`, `infrastructure/`, `docs/runbooks/`, `src/`, `.github/workflows/`, `scripts/guards/`, `backend/benchmarks/`, the rest of `config.py`, all CLAUDE.md files.

## 4. Ordered work

### 4.1 Independent review of the T7-02 commits (SYS-003, CQ-011)

Treat their summary as claims: 1.15 s vs 5.41 s on 20 requests with a fake LLM; a deadlock fix; 31 snapshot cases identical; 12,752 tests passed; 0 safety failures. Check:

1. **No sync work on the event loop:** every LLM call on the v10 path is awaited, and no blocking call (embedding, rerank, Qdrant sync client, file I/O, `time.sleep`) runs on the loop without `run_in_executor` or an async client. Grep the diff for `run_llm_coroutine`, `asyncio.run`, `.result()`, `loop.run_until_complete` and `time.sleep`.
2. **Cancellation:** a client disconnect or timeout cancels the in-flight LLM calls, releases the budget reservation, and emits `answer_outcome` with an honest failure state.
3. **Timeouts:** each await has a bound, and a slow provider cannot hold a request past the gate budget.
4. **Deadlock fix:** reproduce the original deadlock with the test the agent wrote. Confirm the test fails on the parent commit and passes after.
5. **Shared clients:** no provider client is created per call. Nothing caches an event loop across Celery tasks (lesson: "Event loop is closed").
6. **Celery:** confirm the one-loop-per-worker change survives worker restarts and `--pool` settings, and that no `asyncio.run` remains inside a running loop.
7. **Equivalence:** rerun the 31 snapshot cases and the safety scenarios. Report the exact commands and counts.
8. **Load proof is still missing:** the staging c20 test and a live Docker run are UNPROVEN. Do not remove the executor-starvation watchdog in `backend/start_railway.py` (Sonnet-owned) until the c20 test passes.

Write the review into `FINAL_PENDING_WORK_REGISTER.md` (SYS-003 and CQ-011 rows: old status, new status, SHA, evidence) and into the T7-02 entry of §7.

### 4.2 Honest answers and release invariants (no decision needed)

1. **NEW-ANS-1:** pin the real grounding and outcome composition with tests. Probable defect: a served "Related" clip may report `grounding_state="abstained"`. Spec: `specifications/SPIRITUAL_ANSWER_QUALITY_AND_RESPONSE_CONTRACT.md` §8.
2. **NEW-ANS-2:** keep the pipeline's abstain reason through the bridge. A store error must never report `verification.passed=True`. Telemetry must separate "no teaching found" from "system down".
3. **SYS-001 remainder:** the classifier-failure branch in `graph_stage.py` (~211-220) and the no-context node call fail closed.
4. **NEW-SEC-1:** the integrity detector uses the serving posture, not the bridge flag. Re-check the served clip at assembly. Add `guru_served_integrity_failure_total` (append to `metrics.py`).
5. **NEW-ANS-8:** a release-invariants suite that fails on any of: a generated teacher quote, a misattribution served as fact, cross-user memory in an answer, a success-shaped response after a failed step, a served clip that fails the hash gate.

### 4.3 Corpus data integrity and rights (offline builder; no decision needed)

1. **NEW-ING-1** (DATA-20, DATA-21): the builder reads rights from the register and stamps `domain_rights_status`. Remove the hard-coded channel list (it includes "times now"). Fresh builds must be servable only for cleared sources.
2. **NEW-ING-2** (DATA-22, DATA-23): a failed snapshot aborts the build. Per-video replace becomes upsert-then-delete. Add a per-run manifest (`planned`, `written`, `verified`, `failed`).
3. **NEW-ING-3** (DATA-24): `audio_archive.py` stops writing `rights_status: "cleared"` as a literal.
4. **NEW-ING-6** (legacy `points_servable` compares text and hash): implement behind a default-off flag. D-DQ1 is still a proposal.

Edge cases to test: an empty build (the builder must refuse); a video whose upsert fails halfway; a source with no register row; a register row with withdrawn rights; Unicode and Indic text hashing; identical text in two videos (point IDs differ by `transcript_hash`, start and end).

### 4.4 Prompt-injection and untrusted-content defences

1. **NEW-AI-2** (AI-009): a fence helper in `backend/services/untrusted.py`, used by generation, scorer, rerank and selector. It must neutralise closing tags and lookalike Unicode. Test with transcripts that contain "ignore previous instructions", fake closing tags, and Indic-script instructions.
2. **NEW-AI-5** (AI-010): an ingest-time and lane-level injection screen. Default is flag-for-review only (D-PG16 open). Never drop a span by default.
3. **NEW-AI-1** (AI-011): declare `_meditation_misroute` and `grounding_state` in `GraphState`. Add a scan test that fails on any routing key not declared.
4. **MEM-012:** fence the memory extractor input. The injection regex is English-only; record the multilingual gap. Native review is needed before adding Indic patterns.
5. **NEW-SEC-5 / NEW-AI-6:** an adversarial suite under `evals/adversarial/` with a stub LLM, run in CI. Cases come from `specifications/PRODUCTION_RELIABILITY_SECURITY_AND_COST_SPEC.md` §3.9 and the harness spec §A.

### 4.5 Safety paths

1. **SAFE-004 remainder:** only after you quote the owner's recorded "verified-only crisis lines" decision, pass `verified_only=True` at the remaining helpline call sites (2 of about 10 are done). **Edge case that must not happen:** a seeker in crisis sees an empty helpline list. If the filter leaves no line for a language or region, show the verified national line (Tele-MANAS) and the emergency number. Test every language the app offers.
2. **T4-04:** do not change detection. If the owner asks, prepare the clinician packet (current behaviour on the core, benign and multi-turn sets) from `evals/clinician_review_packet.md`.

### 4.6 Cost bounds on the first-person path

1. **NEW-LOAD-6:** set an explicit small `max_tokens` on the rerank call (it returns indices). Note that on OpenRouter the default is 2048, capped at 800 by policy, not 8192 (`specifications/LOAD_AND_COST_MODEL.md` §2, corrected).
2. **T4-06** (RET-10, SYS-006 judge part): evidence-judge consolidation behind `first_person_judge_enabled` (default off). The model setting stays unset until D-16 is decided, so the flag cannot turn on by accident. Compare on the frozen bank before any default change.

### 4.7 Memory and attribution remainders

1. **MEM-002 remainder:** feed real seen-clip ids into `memory_signals`. The chat history payload carries no citations today, so the signal is always empty on the live path.
2. **MEM-004 remainder:** call `compile_user_preferences` in the persona path. An LLM must not write the persona.
3. **GURU-012 remainder:** add a locator check (video and timestamp) for admin-curated and harvested teacher tips in `backend/app/api/teachings.py`.

### 4.8 Final independent review (last step)

Review every commit since `12bb3225`, Sonnet's included. For each, check:
- Does the diff match the message?
- Does every new test fail on the parent commit?
- Is any guard weakened?
- Is any fail-open path added?
- Is any invariant in §2 broken?

Record results in the register with SHAs.

## 5. Decisions to ask the owner (give this context; do not assume answers)

| ID | Question | Why it blocks you |
|---|---|---|
| D-16 | Which relevance-scorer and judge model, at what price? Does OpenRouter return `usage.cost` for it? | Without a cost, each call keeps the $0.03 reservation, and the $10 daily cap allows about 111 answers a day (SYS-014). T4-06 cannot turn on. |
| D-DQ1 | Should legacy `points_servable` compare text and hash? | NEW-ING-6 default |
| D-PG16 | Should the injection screen drop a span or only flag it? | NEW-AI-5 default |
| D-PQ7 | May the Qdrant point id reach the client as `clip_ref`? | `backend/tests/test_citation_contract.py:169-205` forbids it today; saved clips and clip reports need it (PRD-006) |
| D-PQ9 | Show "try again" instead of "no recording found" when a system failure blocks the check? | NEW-ANS-2 copy |
| D-03 | Allow a labelled assistant explanation layer? | Multi-video Variant B and PersonalizeStage's generating path |

## 6. Definition of done and report

For each task: the failing-test output, the passing-test output, guards and formatter results, the commit SHA, the register row updated (old to new status), and what remains. End with:
- a table of findings closed, partial and untouched
- every claim you could not verify
- the decisions still needed
- the exact push result

Add a lesson to the top of `lessons.md` only for a proven, new failure mode. Use a unique ID (search first).
