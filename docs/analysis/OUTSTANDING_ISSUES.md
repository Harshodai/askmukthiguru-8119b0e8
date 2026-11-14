# Outstanding issues (authoritative list for the 2026-11-13 engagement)

Owner instruction 2026-11-13: this file is the single list for the engagement; it is updated at
every gate. Older open work stays in `docs/plans/PROD_READINESS_TASK_LIST_2026-10-11.md`
(its §24 E-series rows are carried here under the same ids). Spend: `docs/operations/SPEND_LOG_2026.md`.
Graded-7 bars: `docs/runbooks/GRADED_7_PRE_REGISTERED_CRITERIA.md`.

Status words: **FIXED** (in tree or committed, test named), **OPEN**, **BLOCKED** (on the named thing),
**OWNER** (decision only the owner can take), **HUMAN** (a human gate no agent can close).
Severity: P0 security/data-integrity failure; P1 core product or release blocker; P2 significant;
P3 maintainability. Every FIXED row names its test. Nothing here is production evidence: one Mac, local Docker.

Last updated: 2026-11-13, gate "Phase 2 fixes" (commits `8a3274cc` .. `34226440` plus the Phase 2 commit).

## 0. Baseline (Phase 0)

Graded-6 re-read against the registered bars by `backend/scripts/ops/graded_registered_report.py`
(numbers recounted by hand and equal): `docs/analysis/GRADED_6_BASELINE_2026-11-13.md`.
Served 43 of 89 answerable core rows (0.483); p95 on served core rows 9,443 ms; core abstain 69/69;
crisis 7/7; unanswerable groups all pass; **hub rule failed** (one clip serves 4 questions; 31 clips
for 43 answers); **showable by both graders not measured and the run is invalid as a registered
run**: one model sat in both grader slots and 33 of 43 served rows have one verdict. First grader
alone: 34/43 = 0.791 (Wilson 95% 0.648 to 0.886). Settings: sparse off, judge on, min score 3,
answerability gate off. Harness gaps: `docs/analysis/HARNESS_AUDIT_2026-11-13.md`.
At about 43 served rows the 85% lower-bound bar needs 42 of 43 showable.

## 1. Fixed in this engagement

| ID | Sev | Subsystem | Issue (evidence) | Root cause | Test | Status |
|---|---|---|---|---|---|---|
| A-01 | P2 | Serving / cache | Follow-up text shared one first-person cache entry across conversations ("why does that happen?" after anger and after money). | Exact-cache key hashes the bare question; the bridge rewrites the retrieval query from history (`first_person_bridge.py` follow-up block). | `test_fp_audit_fixes_2026_11_13.py::test_history_resolved_followup_bypasses_exact_cache` | FIXED |
| A-02 | P2 | Serving / async | Blocking YouTube availability check (sync `httpx` + sync Redis) ran on the request event loop inside the harness worker. | `_passes_integrity_gate` called directly in an `async def`. | `::test_availability_check_does_not_run_on_the_event_loop` (drives `aexecute`) | FIXED |
| A-03 | P3 | Observability | `route_metadata.corpus_version` was always `""`. | `FirstPersonPipelineResult` never set the attribute the bridge reads. | `::test_served_result_reports_corpus_version_and_replay_rederives` | FIXED |
| A-04 | P3 | Observability | A context-store outage logged "falling back to legacy" (false in terminal mode) at WARNING. | Log text predates terminal mode. | `::test_retrieval_error_in_terminal_mode_abstains_loudly` | FIXED (log + `result.error`); user-facing copy is T-E5 |
| A-05 | P3 | Security | Answerability prompt took the raw question; the relevance scorer already neutralised it. | Missing `neutralise()`. Partial hardening only: it escapes prompt-fence tags, not instructions. Strict YES/NO parse and the relevance gate remain the containment. | `::test_gate_user_prompt_is_neutralised` | FIXED (partial by design) |
| A-06 | P2 | Routing / latency | Ambiguous-domain router timed out on every call (27 of 27 in 12 h; measured 470-690 ms against a 0.45 s budget), costing 0.45 s per ambiguous turn. | Budget below the callee's latency. | `test_lead_audit_fixes_2026_11_13.py::test_ambiguous_domain_router_is_off_by_default` | FIXED (default off; enabling needs a budget above latency and a graded comparison) |
| A-07 | P3 | Config | `first_person_corpus_version` declared twice on `Settings`. | Two edits, no guard. | `::test_settings_declares_every_field_once` | FIXED |
| A-08 | P1 | Serving posture | Live `FIRST_PERSON_ANSWERABILITY_CHECK_ENABLED=false` while invariants 19 and 22 describe the gate as always on. Graded-6 manifest confirms it ran OFF. | Set in `.env`; no compose pin; nothing announced it. | `::test_startup_log_carries_the_gate_warning` | FIXED (startup WARNING); on/off is **T-E1 OWNER** |
| A-09 | P2 | Security | `GET /api/search/inspect-source` returned full transcripts to anonymous callers with no blocked-video, rights or quarantine gate and no rate limit. | Route predates the serving gates. | `test_security_audit_fixes_2026_11_13.py` (3 tests) | FIXED |
| A-10 | P2 | Security | Same route: a blocked video reached through `m.youtube.com`, `music.`, `-nocookie` or `/shorts/` skipped the blocked gate (found by the test-challenge pass). | Route's id extractor knew two hosts. | `::test_blocked_video_refused_on_every_youtube_host_and_path` (4 cases) | FIXED |
| A-11 | P3 | Privacy / logs | Seeker text logged at INFO in `rag/nodes/on_device_intent.py` (5 lines). | f-string logs of `text[:50]`. | `::test_on_device_intent_logs_no_user_text` | FIXED |
| A-12 | P1 | Deploy preflight | `validate_production_env.py` passed environments that crash at boot (no `BRAIN_KEK`, no `FACULTY_ACCESS_CODE`, budget guard off, unparseable booleans). | Preflight not kept in step with `Settings.validate_production_restrictions`. | `test_validate_production_env_parity_2026_11_13.py` (24 cases) | FIXED |
| A-13 | P2 | Database / RLS | `message_citations`: any signed-in user could read every row; no INSERT policy, so every browser insert was denied. | `USING (true)`; GRANT without policy. | Proven twice in a transaction that was never committed (own read 1, foreign read 0, own insert ok, forged insert denied). | FIXED in migration `20261113000000`; **applied nowhere** (T-E4) |
| A-14 | P2 | Data integrity (client) | Citation ledger wrote unknown rights as `licensed`, unknown speaker as verified, a 32-bit hash as `source_text_hash`, and swallowed insert errors. | Defaults chosen for convenience; `supabase-js` does not throw. | `src/test/citationLedgerFlags.test.ts` | FIXED (ledger is still client-attested: A-24) |
| A-15 | P2 | Source inspection | `inspect-source` never reached Qdrant live (`QdrantService` had no `get_client` / `collection_name`), silently serving the file fallback. Found and fixed by the parallel review session. | Facade never declared the names the route calls. | `test_inspect_source_qdrant_facade.py` | FIXED in tree; live after the next image build (T-E3) |

## 2. Open: agent-owned

| ID | Sev | Subsystem | Issue (evidence) | Proposed fix / proof | Status |
|---|---|---|---|---|---|
| P2-a | P1 | Answer quality | **Same-clip defect.** Graded-6: 43 served answers use 31 clips; one clip serves 4 questions; strict reader says 7 of 43 answer the question. Judge sees one clip per call (`first_person_judge.py`, harness fan-out). Analysis: `SAME_CLIP_DEFECT_2026-11-13.md`. | **Built, default OFF:** comparative judge (`first_person_comparative_judge_enabled`): one extra call picks an index among contexts that already passed every gate; null or any failure abstains. Tests `test_comparative_judge_2026_11_13.py`. Runner `scripts/ops/run_negative_controls.py` (dry run: 116 pairs, 232 calls, worst-case reservation 6.96). | OPEN: **not measured**. Needs the negative-control run (paid) and a registered run before it may be switched on. Risk: adds one model call to a p95 that is already 9.4 s. |
| P2-c / T-E6 | P2 | Frontend a11y | Screen reader announced "no close match" over a served clip; a rights 403 rendered as "0 chunks". | Announcement keyed on what is shown; explicit 403/404/429 states. | FIXED (`57da22e2`; `answerAnnouncement.test.tsx`, `linkSearchModalInspect.test.tsx`) |
| P2-d | P2 | Latency | Verify-call stall: 7 calls at about 6.45 s in graded-6. | `OPENROUTER_CALL_TIMING` now carries limiter wait, pool wait, connect, time to first byte and read time, and is written for cancelled and refused calls too. Found on the way: the line was only written after a fully successful call, so a call cancelled by the caller's timeout logged nothing (why `operation=verify` never appeared). Test `test_openrouter_call_timing_2026_11_13.py`. | FIXED (measurement). Attribution of the 6.45 s is **still unmeasured** until a live run writes the new line. |
| T-E5 | P2 | Serving / UX | Retrieval outage in terminal mode told the seeker "no verified teaching". | `abstain_cause()` takes the pipeline's `error`; an outage maps to `system_unavailable`. Still abstains. | FIXED (`test_retrieval_outage_cause_2026_11_13.py`) |
| A-16 | P1 | Conversation continuity | **Anonymous users had no follow-up context** (`populate_server_side_history` empties client history). | The client's last prior USER turn (200 chars at most) travels on a separate attribute read only by the follow-up resolver; `messages` is still emptied; incognito and benchmark carry none; safety stages see what they saw before. Safety scenarios after the change: 226 pass, 4 known expected fail, 0 fail. | FIXED (`test_anon_followup_context_2026_11_13.py`). Limits: heuristic, last user turn only, no assistant turn; live check is Phase 4. |
| A-17 | P2 | Runtime config | The backend container was recreated at 2026-11-13 06:18 UTC from `docker-compose.yml` alone. It runs a config no graded run measured: min score 2, sparse on, judge off, monthly cap 100. | Phase 4 rebuilds from the commit with the graded overlay and records resolved values. | OPEN |
| A-18 | P2 | Eval harness | The harness could not evaluate the registered bars: no Wilson bound (H-1), two graders not enforced (H-2), no hub metric (H-4), crisis not a gate (H-5), unpinned flags (H-12, H-14), inputs not fingerprinted (H-16), missing latency could pass (H-18), no negative-control runner (H-8). | `graded_registered_report.py` reports every registered bar as met / failed / not measured with Wilson intervals and invalid-run reasons; graded compose pins the answerability flag (false, as in graded-6) and the router flag; capture manifest records `INTENT_ROUTER_` flags and the sha256 of each input file; `run_negative_controls.py`. | FIXED for H-1, 2, 4, 5, 8, 12, 14, 16, 18. OPEN: collection fingerprint in the manifest is `null` (capture has no Qdrant client; recorded by hand for the run), H-6 (no strict-reader verdict), H-7 (bar file and criteria differ: OWNER), H-19 (rubric hash). |
| T-E7 | P3 | Evaluation | `conversation_cases_draft.jsonl` (24 AI-drafted rows: multi-turn, ambiguous, contradiction, plain fact) has no runner. | Small runner that drives `/api/chat` turn by turn and records route and grounding. Rows stay drafts until the owner reviews them. | OPEN |
| T-E3 | P2 | Runtime | Image rebuild needed for A-15 and every fix above to be live. | Phase 4. | OPEN |
| T-E8 | P3 | Reliability | Redis rate limiter fails open on `Connection closed by server` (2 events in 10 min, parallel review). | Measure under load; record the rate. | OPEN |
| A-19 | P3 | Serving | Harness citation pads playback +0.25 s without the duration cap the legacy path has (`_build_context_citation`); `SourceSpan` carries no duration. At most 0.25 s past the end. | Carry `duration_ms` on the span at build time (ingest change). | OPEN (low value now) |
| A-20 | P3 | Gate precision | "severed preposition opener" rule rejects complete sentences that start lowercase with if/as/at (about a third of a 14-clip sample of the 47 matches in v10). Errs toward abstaining. | Needs a class-of-defect rule and a corpus blast-radius count, then a registered run. | OPEN (not changed: gate rules change only through a registered run) |
| A-21 | P3 | CI | `golden25-gate.yml` runs against `first_person_v7` (absent locally), is manual-only, and exits green when its secrets are missing, so it gates nothing. | Point at the served collection and fail when not run. Needs to know what the CI Qdrant holds. | OPEN |
| A-22 | P3 | Ops | Local stack: prometheus, grafana, alertmanager stopped since 2026-11-01; autoheal exited 139; no celery-beat locally (win-back, memory and prune schedules never run); compose pins differ from running images (memgraph `latest`, redis `7-alpine`). | Start monitoring with the stack; pin images. | OPEN |
| T-E9 | P3 | CI parity | Parallel review ran the frontend on Node 26; this engagement ran it on Node 22.22.3: `tsc` 0, vitest 1,151 passed, build 0. | Closed for Node 22 locally; CI run still to confirm. | FIXED locally |

## 3. Open: owner decisions (stop list)

| ID | Decision | What is known |
|---|---|---|
| T-E1 | Answerability gate on or off | Off live and in graded-6. With it off a `weak_match` is served with the relevance scorer as the only question-level gate. Graded-6 result with it off: 0 clips on 69 unanswerable groups. |
| T-E2 | Monthly model budget | **Corrected reading:** the refusal is the app's own guard (`openrouter_budget.py:217`): month ledger 123.13 against a 100 monthly cap in the running container. Not shown to be the provider account. The graded overlay raises the local cap to 300. Demo is blocked until the cap or the ledger is changed. |
| P2-b | What counts as a truncated clip | Xfail stays strict. A punctuation-free ending is a judge-approved valid ending today. |
| P2-e | Budget reservation policy | A call with no provider response keeps its USD 0.03 reservation (`llm_budget_guard.settle()`); a stall can exhaust a cap. |
| O-1 | Sparse retrieval default | Settings default True; graded config pins False. Graded-5 (sparse on) served 26, graded-6 (off) served 43. |
| O-2 | Demo bar | May the demo serve below 85% showable, labelled as demo. |
| O-3 | Merge to `origin/main`, any push | Local `main` only. |
| O-4 | Any Qdrant write; v11 status | `first_person_v11` exists (stale fork). No writes made. |
| O-5 | Railway resume, production deploy | Untouched. |
| T-D1 | 3,135 pre-fix `corpus_gate_rejections` rows | Purge or keep. |
| T-E4 | Apply local migrations `20261107000000`, `20261107000001`, `20261113000000` | Additive; a database change, so not applied by an agent. |
| A-23 | Compose image pins versus running images | Recreate from the file or update the file. |

## 4. Open: human-only gates (never closed by an agent)

Native-speaker review of crisis detection; clinician review; helpline phone verification;
rights sign-off; the 299-item gold label batch (0 human labels verifiable in the repo today;
`evals/gold_set_v1/annotator_A.csv` and `_B.csv` are filled with identical notes and 101/101
agreement, so treat them as machine-filled until shown otherwise); a human sample of 50 served
answers (random, seed recorded). Any AI-only score is a diagnostic.

## 5. Known limits of the evidence

- The citation ledger is written by the browser, so it is self-attested (A-24): the backend should
  write it. Not started.
- Latency and coverage numbers are from one Mac. Production is unmeasured.
- The frozen 116 are AI-authored from transcripts; wording mirrors the corpus and flatters retrieval.
- No dataset measures multi-turn behaviour yet (T-E7).
