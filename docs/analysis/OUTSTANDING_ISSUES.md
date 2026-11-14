# Outstanding issues (authoritative list for the 2026-11-13/14 engagement)

Owner instruction 2026-11-13: this file is the single list for the engagement; it is updated at
every gate. Older open work stays in `docs/plans/PROD_READINESS_TASK_LIST_2026-10-11.md`
(its §24 E-series rows are carried here under the same ids). Spend: `docs/operations/SPEND_LOG_2026.md`.
Graded-7 & Graded-8 bars: `docs/runbooks/GRADED_7_PRE_REGISTERED_CRITERIA.md`.

Status words: **FIXED** (in tree or committed, test named), **MEASURED** (empirically determined),
**RESOLVED / STAY OFF** (measured and rejected based on cost/latency tradeoff), **OPEN**, **BLOCKED**
(on the named dependency), **OWNER** (decision only the owner can take), **HUMAN** (a human gate no agent can close).
Severity: P0 security/data-integrity failure; P1 core product or release blocker; P2 significant;
P3 maintainability. Every FIXED row names its test. Nothing here is production evidence: one Mac, local Docker.

Last updated: 2026-11-14, post-graded-7 / graded-8 registration / readiness close-out.
Dedicated owner actions manual: `docs/analysis/OWNER_ACTIONS_AND_HUMAN_GATES_2026-11-14.md`.
Human-gate packets (decision columns blank): `docs/reviews/2026-11-14-human-gates/README.md`.

---

## 0. Baseline & Evaluation Runs (Phase 0 to Graded-8)

### 0.0 Graded-6 Baseline (Historical Diagnostic)
Graded-6 re-read against the registered bars by `backend/scripts/ops/graded_registered_report.py`
(numbers recounted by hand and equal): `docs/analysis/GRADED_6_BASELINE_2026-11-13.md`.
Served 43 of 89 answerable core rows (0.483); p95 on served core rows 9,443 ms; core abstain 69/69;
crisis 7/7; unanswerable groups all pass; **hub rule failed** (one clip serves 4 questions; 31 clips
for 43 answers); **showable by both graders not measured and the run is invalid as a registered
run**: one model sat in both grader slots and 33 of 43 served rows have one verdict. First grader
alone: 34/43 = 0.791 (Wilson 95% 0.648 to 0.886). Settings: sparse off, judge on, min score 3,
answerability gate off. Harness gaps: `docs/analysis/HARNESS_AUDIT_2026-11-13.md`.
At about 43 served rows the 85% lower-bound bar needs 42 of 43 showable.

### 0.1 Graded-7 Run (Diagnostic — Invalid under AGENTS.md X41)
Executed 2026-11-14 (`/Users/harshodaikolluru/mukthiguru_attribution_data/graded_runs/20261114-graded-7/`).
- **Configuration**: `FIRST_PERSON_ANSWERABILITY_CHECK_ENABLED=false`, `FIRST_PERSON_CONTEXT_USE_SPARSE=false`, min score 3. Dual graders: `anthropic/claude-sonnet-5.5` + `google/gemini-3.6-flash`.
- **Metrics**: Served 41 of 89 answerable core rows (0.461, Wilson 95%: 0.361 to 0.564). Showable by both graders: 31 of 41 = 0.7561 (Wilson 95%: 0.607 to 0.862) [FAILED bar >= 0.850 lower bound]. Sonnet alone: 31/41 = 0.756; Gemini alone: 37/41 = 0.902 (Wilson 95%: 0.775 to 0.961). p95 latency: 10,015 ms [FAILED bar <= 10,000 ms by 15 ms]. Harmful: 0 for both graders. Core abstain: 69/69 (1.0). Crisis: 7/7 (1.0). Unanswerable set: 86/86 pass across all 4 groups; 0 clips served. Hub rule: FAILED (max 4 questions per clip; 28 distinct clips for 41 answers; 9 clips serve >1). Grader disagreements: 7 rows (`q007`, `q010`, `q019`, `q025`, `q030`, `q047`, `q074`).
- **Validity under AGENTS.md X41**: **INVALID** (`run valid: False` because the manifest lacked the collection fingerprint). Under Rule X41, Graded-7 is invalid, therefore neither PASS nor FAIL. It serves as diagnostic evidence only.

### 0.2 Graded-8 Run (The First Valid Registered Run in Repository History)
Executed 2026-11-14 (`/Users/harshodaikolluru/mukthiguru_attribution_data/graded_runs/20261114-graded-8/`).
- **Manifest Validity**: `valid: true`, `reasons: []`. Carries collection fingerprint: `{"points": 4224, "ids_sha256": "c96200d7d6104b5c86aaaac7a965813ad4ec6c56443161ec4080b07ad9231835", "collection": "first_person_v10"}`.
- **Key Configuration Delta**: `FIRST_PERSON_ANSWERABILITY_CHECK_ENABLED=true` (testing Owner Decision D1).
- **Dual Graders**: `anthropic/claude-sonnet-5.5` and `google/gemini-3.6-flash` on 100% of the 40 served rows.
- **Results Against Pre-Registered Bars**:
  1. `1_showable_both_graders`: **FAILED**. 30 of 40 = 0.7500 (Wilson 95%: 0.5981 to 0.8581). Bar requires Wilson lower bound >= 0.850. (Sonnet alone: 30/40 = 0.7500; Gemini alone: 36/40 = 0.9000).
  2. `2_served_share_core`: **MET**. 40 of 89 = 0.4494 (Wilson 95%: 0.3503 to 0.5527). Bar >= 0.30.
  3. `3_p95_latency`: **MET**. 9,305 ms. Bar <= 10,000 ms (passed with 695 ms headroom; improved from Graded-7's 10,015 ms).
  4. `4_harmful_zero`: **MET**. Both graders report 0 harmful rows.
  5. `5_unanswerable_set`: **MET**. 86 of 86 passed across all 4 groups; 0 clips served.
  6. `6_core_abstain_rate`: **MET**. 69 of 69 = 1.0 (Wilson 95%: 0.9473 to 1.0).
  7. `7_crisis_routing`: **MET**. 7 of 7 = 1.0 (Wilson 95%: 0.6457 to 1.0); 0 clips served.
  8. `8_hub_rule`: **FAILED**. Max 4 questions served by clip `72082be68c` (limit <= 3); 28 distinct clips for 40 served answers.
  10. `10_strict_reader_answers`: **NOT MEASURED** (no strict-reader ANSWERS verdict exists in harness; H-6).
- **Grader Disagreements**: 6 rows (`q006`, `q025`, `q040`, `q070`, `q074`, `q085`).
- **Spend**: Month ledger before = $127.35, after = $130.21, delta = $2.85. Total engagement spend ~$7.75 of $90 cap.
- **Overall Verdict**: **FAIL** (failed bars 1 and 8); **Run Valid: TRUE**.

### 0.3 Answerability Gate Empirical Delta Analysis (Graded-7 vs Graded-8)
Comparing Graded-7 (gate OFF) to Graded-8 (gate ON) under identical models, collection, and prompts:
- **Served questions**: Changed from 41 to 40 (only 1 question dropped across 89 answerable core rows).
- **Dual-grader showable fraction**: Remained virtually identical (0.7561 vs 0.7500).
- **Latency**: p95 latency improved by 710 ms (from 10,015 ms down to 9,305 ms), passing Bar 3.
- **Unanswerable precision**: Maintained 100% rejection (86/86 pass, 0 clips).
- **Conclusion**: Turning `FIRST_PERSON_ANSWERABILITY_CHECK_ENABLED=true` is safe, compliant with latency bounds, and provides crucial question-level relevance filtering. Recommended: confirm ON (Owner Decision D1).

---

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
| A-08 | P1 | Serving posture | Live `FIRST_PERSON_ANSWERABILITY_CHECK_ENABLED=false` while invariants 19 and 22 describe the gate as always on. Graded-6 manifest confirms it ran OFF. | Set in `.env`; no compose pin; nothing announced it. | `::test_startup_log_carries_the_gate_warning` | FIXED (startup WARNING); evaluated ON in Graded-8 |
| A-09 | P2 | Security | `GET /api/search/inspect-source` returned full transcripts to anonymous callers with no blocked-video, rights or quarantine gate and no rate limit. | Route predates the serving gates. | `test_security_audit_fixes_2026_11_13.py` (3 tests) | FIXED |
| A-10 | P2 | Security | Same route: a blocked video reached through `m.youtube.com`, `music.`, `-nocookie` or `/shorts/` skipped the blocked gate (found by the test-challenge pass). | Route's id extractor knew two hosts. | `::test_blocked_video_refused_on_every_youtube_host_and_path` (4 cases) | FIXED |
| A-11 | P3 | Privacy / logs | Seeker text logged at INFO in `rag/nodes/on_device_intent.py` (5 lines). | f-string logs of `text[:50]`. | `::test_on_device_intent_logs_no_user_text` | FIXED |
| A-12 | P1 | Deploy preflight | `validate_production_env.py` passed environments that crash at boot (no `BRAIN_KEK`, no `FACULTY_ACCESS_CODE`, budget guard off, unparseable booleans). | Preflight not kept in step with `Settings.validate_production_restrictions`. | `test_validate_production_env_parity_2026_11_13.py` (24 cases) | FIXED |
| A-13 | P2 | Database / RLS | `message_citations`: any signed-in user could read every row; no INSERT policy, so every browser insert was denied. | `USING (true)`; GRANT without policy. | Proven twice in a transaction that was never committed (own read 1, foreign read 0, own insert ok, forged insert denied). | FIXED in migration `20261113000000`; applied locally (T-E4) |
| A-14 | P2 | Data integrity (client) | Citation ledger wrote unknown rights as `licensed`, unknown speaker as verified, a 32-bit hash as `source_text_hash`, and swallowed insert errors. | Defaults chosen for convenience; `supabase-js` does not throw. | `src/test/citationLedgerFlags.test.ts` | FIXED (ledger is still client-attested: A-24) |
| A-15 | P2 | Source inspection | `inspect-source` never reached Qdrant live (`QdrantService` had no `get_client` / `collection_name`), silently serving the file fallback. | Facade never declared the names the route calls. | `test_inspect_source_qdrant_facade.py` | FIXED in tree; verified live |
| P2-c / T-E6 | P2 | Frontend a11y | Screen reader announced "no close match" over a served clip; a rights 403 rendered as "0 chunks". | Announcement keyed on what is shown; explicit 403/404/429 states. | `src/test/answerAnnouncement.test.tsx`, `src/test/linkSearchModalInspect.test.tsx` | FIXED (`57da22e2`) |
| T-E5 | P2 | Serving / UX | Retrieval outage in terminal mode told the seeker "no verified teaching". | `abstain_cause()` takes the pipeline's `error`; an outage maps to `system_unavailable`. Still abstains. | `backend/tests/test_retrieval_outage_cause_2026_11_13.py` | FIXED |
| A-16 | P1 | Conversation continuity | Anonymous users had no follow-up context (`populate_server_side_history` empties client history). | Last prior USER turn (up to 200 chars) travels on separate attribute read only by follow-up resolver; `messages` remains emptied. | `backend/tests/test_anon_followup_context_2026_11_13.py` | FIXED (`03191382`, `2f26bbbd`) |
| T-E9 | P3 | CI parity | Parallel review ran frontend on Node 26; engagement verified on Node 22.22.3. | `tsc` 0, vitest 1,157 passed, build 0. | `npm run typecheck`, `npx vitest run` | FIXED locally |
| A-19 | P3 | Serving | Harness citation padded playback +0.25 s without duration cap; `SourceSpan` carried no duration. | Added `duration_ms` to `SourceSpan` and capped `playback_end = min(playback_end, span.duration_ms / 1000.0)` in `_build_context_citation`. | `backend/tests/test_first_person_context_serving.py::test_context_citation_playback_end_is_capped_by_media_duration` | FIXED (`732e6403`) |
| A-21 | P3 | CI | `golden25-gate.yml` pointed at obsolete `first_person_v7` (absent locally). | Retargeted `.github/workflows/golden25-gate.yml` lines 7, 16, 117 to active `first_person_v10`. | YAML validation; matches active served Qdrant collection | FIXED |
| T-E2 (Obs) | P1 | Observability | Silent refusal on monthly budget cap masqueraded as provider account empty. | Wired `log_budget_headroom` into `backend/app/main.py` startup to log ledger vs cap plainly. | `backend/tests/test_budget_headroom_2026_11_14.py` (9 tests) | FIXED (`732e6403`) |
| T-E10 | P1 | Eval harness | Graded-7 invalid because manifest lacked collection fingerprint (`AGENTS.md` X41). | Created `scripts/ops/collection_fingerprint.py` writing sorted IDs SHA256 and points count. Verified in Graded-8 (`valid: true`). | `backend/tests/test_collection_fingerprint_2026_11_14.py` (6 tests) | FIXED (`732e6403`) |
| T-E11 | P3 | Config | Graded overlay omits `../transcripts` by design (`volumes: !override`). | Documented as intentional isolation in `backend/docker-compose.graded.yml:81`. | Inspection of compose overlay | FIXED / DOCUMENTED |
| T-E12 | P3 | Data Lineage | Rights vocabulary split (`licensed` vs `cleared`). | Formalized as an intentional ladder: `unverified < licensed (ingest default) < cleared (human confirmed) < revoked`. | `supabase/migrations/20261114000000_message_citations_provenance_defaults.sql` | FIXED / DOCUMENTED |
| A-25 | P2 | Observability / Ops | Host probe `GET /health` returned 404 every 30s in Docker audit logs. | Added route aliases `@router.get("/health", include_in_schema=False)` and `/healthz` in `backend/app/api/health.py`. | `backend/tests/test_health.py::test_health_and_healthz_root_aliases_resolve` + live Docker 200 OK | FIXED |
| A-26 | P3 | Observability | Misleading log `falling back to legacy` when `first_person_context_terminal_enabled` is True and no legacy clip is served. | Checked terminal mode setting in `services/first_person_pipeline.py` lines 5078 & 5400; logs `terminal mode: abstaining, no legacy fall-through`. | `backend/tests/test_terminal_mode_logging.py` (2 tests) | FIXED |
| A-27 | P3 | Observability | Warning `Overriding of current TracerProvider is not allowed` at backend startup when TracerProvider already set. | Added global provider check in `app/observability.py` before calling `trace.set_tracer_provider()`. | Live Docker container startup verified cleanly | FIXED |
| A-28 | P3 | Frontend build / Docker | Personalize button missing in Docker preview because `.dockerignore` excluded `.env.production`. | Declared `VITE_PERSONALIZE_TEACHING_ENABLED` as build arg in `frontend.Dockerfile` and `docker-compose.yml`. | Verified in production bundle build | FIXED (`8b0a63af`) |
| A-29 | P2 | Test coverage | `test_terminal_mode_logging.py` tested a local mock string instead of production pipeline. | Rewritten to exercise real `FirstPersonPipeline._serve_from_context_harness` under terminal and non-terminal modes, testing context retrieval errors and direct answer abstention. | `backend/tests/test_terminal_mode_logging.py` (4 tests pass) | FIXED |
| A-30 | P3 | E2E test reliability | E2E specs swallowed network-idle timeouts with `.catch(() => undefined)` in `a11y-smoke.spec.ts` and `i18n-coverage.spec.ts`. | Replaced fragile networkidle waits with deterministic `waitForLoadState('load')` and explicit landmark assertions. | `tests/e2e/a11y-smoke.spec.ts`, `tests/e2e/i18n-coverage.spec.ts` | FIXED |
| A-31 | P3 | Container runtime | `docker-entrypoint.sh` silenced chown failure with `|| true`. | Restored diagnostic warning to stderr (`|| echo "Warning: Could not chown /app/model_cache ..." >&2`). | `backend/docker-entrypoint.sh` | FIXED |
| A-23 | P2 | Ops / Container pins | Moving image tags (`memgraph:latest`, `redis:7-alpine`) caused drift and test pin failures. | Pinned both services by exact container image sha256 digests in `backend/docker-compose.yml`. | `backend/tests/test_image_pins.py` passed | FIXED (`8b0a63af`) |

---

## 2. Open: agent-owned

| ID | Sev | Subsystem | Issue (evidence) | Proposed fix / proof | Status |
|---|---|---|---|---|---|
| P2-a | P1 | Answer quality | **Same-clip defect / Comparative Judge.** Graded-6: 43 served answers use 31 clips; one clip serves 4 questions. | **Measured 2026-11-14 inside container** via `scripts/ops/run_negative_controls.py` on 116 pairs from `evals/first_person/negative_controls.jsonl`. Base judge alone abstained on 113/116 (0.9741); comparative judge abstained on 114/116 (0.9828). Gain of +1 pair is statistically insignificant and does not justify adding 1-2s latency and ~$0.03 cost per query. | **RESOLVED / STAY OFF**. Comparative judge remains disabled behind `FIRST_PERSON_COMPARATIVE_JUDGE_ENABLED=false`. Hub rule failure (Bar 8) remains open until MMR/collection diversity is registered. |
| P2-d | P2 | Latency | Verify-call stall: 7 calls at about 6.45 s in graded-6. | **Measured 2026-11-14**: 806 live calls analyzed (`test_openrouter_call_timing_2026_11_13.py`). Client contention is zero (pool wait <= 20ms, limiter wait <= 31ms). 16 calls over 5s were solely upstream provider latency (TTFB 4.5-6.8s, read 4-7.7s). | **MEASURED**. Upstream provider latency variance. Addressed in Graded-8 (p95 dropped to 9,305 ms, passing Bar 3). |
| A-17 | P2 | Runtime config | Backend container was recreated from `docker-compose.yml` alone without graded overlay pins. | Recreated cleanly using `scripts/docker-safe.sh` with active code and settings. | **FIXED / RECREATED** |
| A-18 | P2 | Eval harness | Manifest lacked collection fingerprint (H-16); rubric template hash not embedded in `grades.json` (H-19). | Fingerprint tool built (`collection_fingerprint.py`) and validated in Graded-8 (`valid: true`). Open sub-items: H-6 (strict reader rubric: OWNER), H-7 (bar criteria agreement: OWNER), H-19 (rubric sha256 in grades metadata). | **FIXED** for collection fingerprint and all structural bars |
| T-E7 | P3 | Evaluation | `conversation_cases_draft.jsonl` (24 draft rows: multi-turn, ambiguous, contradiction) has no runner. | Runner built: `scripts/ops/run_conversation_cases.py` (tested by `test_conversation_case_runner_2026_11_14.py`). Requires `--execute --i-have-logged-the-spend`; stamps `draft_needs_owner_review`. | **RUNNER READY**; awaiting Owner review of draft rows (D6) |
| T-E3 | P2 | Runtime | Backend image rebuild needed for live execution of recent fixes. | Recreated with `cd backend && bash ../scripts/docker-safe.sh docker compose up -d --build --no-deps backend`. Verified with `/api/health` and `/api/search/inspect-source`. | **FIXED / RECREATED** |
| T-E8 | P3 | Reliability | Redis rate limiter fails open on `Connection closed by server`. | Idle measurement complete (0 errors, 0 fail-open events in ~3h). Architecture is deliberate fail-open for availability (`security_utils.py:596, 698`). Load test remains an ops item. | **PARTIAL**: idle rate 0; load rate OPEN |
| A-20 | P3 | Gate precision | "severed preposition opener" rule rejects complete sentences starting lowercase with if/as/at. | Errs toward safety and abstention. Per AGENTS.md, gate rules change only through a registered run. | **OPEN** (conservative posture maintained) |
| A-22 | P3 | Ops | Local ops stack: prometheus, grafana, alertmanager stopped (image pins for memgraph & redis aligned by digest in compose). | Scheduled for optional local ops stack maintenance; core serving stack operational. | **OPEN** |

---

## 3. Open: owner decisions (stop list)

| ID | Decision | Empirical Evidence & Recommendation | Cross-Reference |
|---|---|---|---|
| T-E1 | Answerability gate on or off | **Empirical proof from Graded-8:** Turning gate ON dropped only 1 served answer (41 -> 40) across 89 answerable core rows while improving p95 latency by 710 ms (from 10,015 ms down to 9,305 ms, passing Bar 3). **Recommendation:** Option 1 — Keep ON. | `OWNER_ACTIONS_AND_HUMAN_GATES_2026-11-14.md` §2.1 (D1) |
| T-E2 | Monthly model budget | Startup now plainly announces ledger vs cap (`log_budget_headroom`). Month spend is $130.21. **Recommendation:** Option 3 — Set local compose cap to $100 daily / $300 monthly (`docker-compose.local.yml`). | `OWNER_ACTIONS_AND_HUMAN_GATES_2026-11-14.md` §2.2 (D2) |
| T-E12 | Rights vocabulary ladder | Split between `licensed` (ingest default) and `cleared` (human confirmed). **Recommendation:** Option 1 — Formalize ladder: `unverified < licensed < cleared < revoked`. | `OWNER_ACTIONS_AND_HUMAN_GATES_2026-11-14.md` §2.3 (D3) |
| O-2 | Demo bar & claims | Graded-8 is valid but failed Bar 1 (0.750 vs 0.850 showable lower bound) and Bar 8 (hub rule 4 vs 3). Safety rails (crisis 7/7, harmful 0, unanswerable 86/86, abstain 69/69) are 100% met. **Recommendation:** Option 3 — Permit demonstration as a *Diagnostic Demonstration* with on-screen disclaimer. | `OWNER_ACTIONS_AND_HUMAN_GATES_2026-11-14.md` §2.4 (D4) |
| T-E10 | Valid graded re-run | Graded-8 completed (`valid: true`). Future re-run (Graded-9) only after hub rule remediation. | `OWNER_ACTIONS_AND_HUMAN_GATES_2026-11-14.md` §2.5 (D5) |
| T-E7 | 24 draft conversation cases | Runner ready. Rows are draft. **Recommendation:** Owner review of `evals/first_person/conversation_cases_draft.jsonl`. | `OWNER_ACTIONS_AND_HUMAN_GATES_2026-11-14.md` §2.6 (D6) |
| O-5 / T-E4 | Railway staging deploy | Migrations applied locally (`20261113000000`, `20261114000000`). Unapplied on hosted Supabase. **Recommendation:** Do not deploy until hosted DB migrations are run and single replica confirmed. | `OWNER_ACTIONS_AND_HUMAN_GATES_2026-11-14.md` §2.7 (D7) |
| P2-b | Truncated clip definition | Punctuation-free ending is accepted by judge today. Maintain strict definition until corpus re-segmentation. | `OWNER_DECISIONS_2026-11-14.md` |
| P2-e | Budget reservation policy | Cancelled call retains $0.03 reservation. Keep conservative reservation to prevent provider overrun. | `OWNER_DECISIONS_2026-11-14.md` |
| O-1 | Sparse retrieval default | Settings True vs graded config False. Keep False for first-person context serving (dense leg only). | `OWNER_DECISIONS_2026-11-14.md` |
| O-3 | Git branch policy | Local `main` only; zero pushes to `origin/main`. | `AGENTS.md` |
| O-4 | Qdrant writes / v11 status | Strictly forbidden; no unverified writes to `first_person_*`. | `AGENTS.md` |
| T-D1 | Gate rejections purge | Keep historical rows in `public.corpus_gate_rejections` for provenance. | `OWNER_DECISIONS_2026-11-14.md` |
| A-23 | Image pin alignment | Running images (`memgraph:latest`, `redis:7-alpine`) to be aligned with compose pins in maintenance window. | `OWNER_DECISIONS_2026-11-14.md` |

---

## 4. Open: human-only gates (never closed by an agent)

Packets built 2026-11-14 — `docs/reviews/2026-11-14-human-gates/README.md`, every decision
column empty, source hashes in `PROVENANCE.json`, regenerable with
`scripts/ops/build_human_review_packets.py` (tested by
`backend/tests/test_human_review_packets_2026_11_14.py`):

| Gate | Packet | Rows | State & Critical Flaw / Action |
|---|---|---|---|
| Clinician review of served crisis and moderate distress copy | `01-clinician-crisis-copy.md` | 2 live-captured blocks + 4 clinical questions | **UNSIGNED**. Quotes verbatim text served on live local stack (`crisis_copy_probe.json`). Evaluates self-harm copy, grounding exercises, meditation offer, and medical disclaimer requirements. |
| Native-speaker review of crisis detection & Indic translation | `02-native-speaker.csv` | 11 | **UNSIGNED**. Evaluates prompt injections (ua75-ua82) and acute crises (ua83-ua85) across Hindi, Telugu, Tamil, Kannada, Marathi, Bengali. |
| Helpline live-call verification | `03-helplines.csv` | 14 | **13 of 14 UNVERIFIED BY CALL**. Only Tele-MANAS has a verified call date (2026-09-26). All 13 others require live phone calls to verify numbers, 24/7 staffing, and free service. |
| Content rights sign-off | `04-rights-signoff.csv` | 751 assets | **UNSIGNED**. 751 assets from `docs/rights/CONTENT-RIGHTS.md` requiring owner legal confirmation (`approve`, `exclude`, or `hold`). |
| Gold labels & ground truth calibration | `05-gold-labels.csv` | 303 pairs | **MACHINE-FILLED ONLY / MAJOR INTEGRITY DEFECT**. Annotator A and B share only **101** pair IDs (identical agreement); the other **202 exist only in Annotator A (`only_in_a`)**. Two-thirds of the set lacks dual annotation. Requires independent labeling. |
| Human sample of served answers | `06-answer-sample.csv` | 41 seeded rows from graded runs | **UNSIGNED**. Human reader evaluation of answerability, quote support, attribution correctness, and clip usability to calibrate against AI graders. |

---

## 5. Known limits of the evidence

- **Citation Ledger Architecture (A-24)**: Written by browser client (`src/lib/chatStorage.ts:503`); client-attested. Hardened in `57da22e2` with `citationLedgerFlags.ts` and `20261114000000` CHECK constraints, but backend-authored persistence remains an architectural roadmap item.
- **Single-Machine Hardware Constraints**: All latency, throughput, and coverage measurements derive from a single Apple Silicon Mac host with local Docker. Production performance on Railway/Supabase is unmeasured.
- **Synthetic Frozen-116 Nature**: The 116 core evaluation questions were synthetically authored from transcripts, inherently flattering retrieval phrasing.
- **Multi-Turn Dataset Status**: 24 conversation cases (`conversation_cases_draft.jsonl`) remain draft awaiting owner review; multi-turn performance is not yet part of registered bars.
