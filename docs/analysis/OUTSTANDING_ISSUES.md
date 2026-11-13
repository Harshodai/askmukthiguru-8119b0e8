# Outstanding issues (authoritative list for the 2026-11-13 engagement)

Owner instruction 2026-11-13: this file is the single list for the engagement; it is updated at
every gate. Older open work stays in `docs/plans/PROD_READINESS_TASK_LIST_2026-10-11.md`
(its §24 E-series rows are carried here under the same ids). Spend: `docs/operations/SPEND_LOG_2026.md`.
Graded-7 bars: `docs/runbooks/GRADED_7_PRE_REGISTERED_CRITERIA.md`.

Status words: **FIXED** (in tree or committed, test named), **OPEN**, **BLOCKED** (on the named thing),
**OWNER** (decision only the owner can take), **HUMAN** (a human gate no agent can close).
Severity: P0 security/data-integrity failure; P1 core product or release blocker; P2 significant;
P3 maintainability. Every FIXED row names its test. Nothing here is production evidence: one Mac, local Docker.

Last updated: 2026-11-13, gate "Phase 1 issue list".

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
| P2-a | P1 | Answer quality | **Same-clip defect.** Graded-6: 43 served answers use 31 clips; 9 clips serve 21 answers; strict reader says 7 of 43 answer the question. Judge sees one clip per call (`first_person_judge.py`, harness fan-out). Analysis: `SAME_CLIP_DEFECT_2026-11-13.md`. | Comparative judge (candidate A) behind a default-off flag; measure on `negative_controls.jsonl` before any graded spend; hub metric (no clip > 3 questions). | OPEN (in progress) |
| P2-c / T-E6 | P2 | Frontend a11y | Screen reader announces "no close match" over a served clip (clips carry `groundingState 'abstained'` by design); a rights 403 renders as "0 chunks". | Key the announcement on what is shown; explicit refusal states. Frontend-only. | OPEN (in progress) |
| P2-d | P2 | Latency | Verify-call stall: 7 calls at about 6.45 s in graded-6. Cause unknown (pool wait or provider first byte). | Add timing of connection-pool wait versus first byte before changing anything. | OPEN (in progress) |
| T-E5 | P2 | Serving / UX | Retrieval outage in terminal mode still tells the seeker "no verified teaching" (`abstain_cause()` reads only status/reason). | Error-aware cause so the copy says "temporarily unavailable"; still abstains. | OPEN (in progress) |
| A-16 | P1 | Conversation continuity | **Anonymous users have no follow-up context.** `populate_server_side_history` (`app/api/chat.py:427`) empties client history for anonymous sessions, so "why does that happen?" is searched as bare text. Signed-in users get a heuristic concat of the last user turn only. | Pass the client's last user turn to the follow-up resolver only (never into generation or the safety stages); run `evals/run_safety_scenarios.py` after. | OPEN (in progress) |
| A-17 | P2 | Runtime config | The backend container was recreated at 2026-11-13 06:18 UTC from `docker-compose.yml` alone. It runs a config no graded run measured: min score 2, sparse on, judge off, monthly cap 100. | Phase 4 rebuilds from the commit with the graded overlay and records resolved values. | OPEN |
| A-18 | P3 | Eval harness | Graded compose does not pin `FIRST_PERSON_ANSWERABILITY_CHECK_ENABLED` (rides on `.env`). More gaps: `HARNESS_AUDIT_2026-11-13.md`. | Pin every serving flag the manifest records. | OPEN (waits on the harness audit) |
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
