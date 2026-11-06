# Complete FR and NFR matrix, acceptance criteria, traceability and test methodology

Owner: specification agent (final verification, 2026-11-05). Code state: branch `feature/audit-strengthen-rag-qdrant` at `c9b42d3e`. Builds on `03` (32 FRs), `04` (70 NFRs), `traceability-matrix.md`, `22a`, `18`, `16`, `20`, `FINAL_READINESS_AND_GAP_ANALYSIS.md` (first draft Gate A; IDs now remapped to `FINAL_RAILWAY_STAGING_READINESS.md` A1-A21), `FINAL_PRODUCTION_RELEASE_READINESS.md` (Gates B and C, IDs B1-B18 and C1-C12) and `FINAL_PENDING_WORK_REGISTER.md`. Conventions: `CONVENTIONS.md`. This file does not repeat the narrative of `03` and `04`. It adds missing requirements, corrects wrong ones, and makes each one testable.

Style: short sentences, one term per thing. Evidence labels follow `CONVENTIONS.md`.

## 1. How to read this file

### 1.1 Verified, assumed, unknown

| Class | Content |
|---|---|
| Verified in this session (code at `c9b42d3e`) | Paths and line numbers cited in the "Where" and "Test" columns. Test case names written as `file::case` were read. |
| Assumption | Anything marked `[INF]`. A test file written without `::case` was located by name and by a text match only. Its cases were not read. That it asserts the acceptance criterion is `[INF]`. |
| Unknown | Anything marked `[LIVE-Q]`, `[LIVE-R]`, `[LIVE-L]` or `[HUMAN]`. No live system, credential or human review was used. |

### 1.2 Columns

| Column | Meaning |
|---|---|
| ID | Existing IDs are kept. New IDs are `FR-N-<n>` and `NFR-N-<n>`. A star after a statement means the statement was rewritten (§5 lists the originals). |
| Pri | P0 = a failure harms a seeker, breaks a CLAUDE.md invariant, or exposes rights or data. P1 = blocks a release gate or a core journey. P2 = important. P3 = could. |
| Obj, need | Business objective O1-O6 (`traceability-matrix.md`) and the user need. |
| Where | Component; source files; API endpoint; data dependency. |
| Task | Roadmap task (`20`). "R" marks a task reserved for supervised work (`IMPLEMENTATION-AGENT-PROMPT.md` §0j). |
| Test | `file::case`, or `MISSING`. |
| Acceptance | A measurable pass condition. |
| Gate | Release-gate ID: A1-A21 (staging, `FINAL_RAILWAY_STAGING_READINESS.md`), B1-B18 (production, invited users), C1-C12 (public). |
| Status | **Met** = behaviour implemented and at least one named test asserts it. **Partial** = implemented but a test, a measurement or a part of the statement is missing. **Open** = not implemented. **Aspirational** = a target with no baseline on the target environment. |

Live behaviour with no test is Partial, not Met.

### 1.3 Invariant check

Every row obeys the root `CLAUDE.md` invariants: no generated teaching text at serve time (inv. 1, 15, 21), verbatim integrity (inv. 2, 13), no calibrated "direct answer" without a profile (inv. 3), OKF is never teacher voice (inv. 12), quotes are never translated (inv. 16). Where a brief asks for generated or synthesised teacher-adjacent text, the row gives the compliant form and names the decision that gates the other form (D-03 / ADR-001, D-04 / ADR-002, D-06 / ADR-006).

## 2. Corrections to earlier documents (code wins)

| # | Earlier statement | Code at `c9b42d3e` | Action |
|---|---|---|---|
| C-1 | Root `CLAUDE.md` "Pipeline" chain starts with `CacheCheck` and has no `OffTopic` stage. | `backend/app/pipeline/stages/pipeline_builder.py:53-92` starts with `KillSwitchStage()` and contains `OffTopicStage()` (line 70). `IMPLEMENTATION-AGENT-PROMPT.md` §1 already says the order in `CLAUDE.md` is stale. | Fix `CLAUDE.md` (T1-15). |
| C-2 | `04` NFR-OBS-01 baseline "0 turns emit `answer_outcome`". | `backend/app/answer_outcome.py` exists and `backend/tests/test_answer_outcome_telemetry.py::test_served`, `::test_abstained`, `::test_crisis`, `::test_error` exist. | Baseline is stale. Status in §4 is Met. |
| C-3 | `04` NFR-COST-01 "spend cap off by default". | `backend/app/config.py:643` `openrouter_budget_guard_enabled: bool = True`, `:645` `openrouter_budget_fail_closed: bool = True`, `:2491-2499` production refuses to start with the guard off unless `allow_uncapped_llm_spend` (`:648`, default False). | Baseline is stale. |
| C-4 | `04` NFR-SEC-04 "datastores exposed on 0.0.0.0". | `backend/docker-compose.yml:49,50,76,156,157` bind to `127.0.0.1`. `backend/tests/test_docker_compose_healthcheck.py::test_datastore_ports_bound_to_loopback_only` asserts it. Qdrant key enabling in production is still infrastructure work. | Baseline stale for compose; Partial overall. |
| C-5 | `04` NFR-MAINT-01 "`execute` 2,145 lines". | `execute` starts at `backend/services/first_person_pipeline.py:5601`; the next `def` is at `:5871` (about 270 lines; `IMPLEMENTATION-AGENT-PROMPT.md` §0k says 266). But the context-harness block moved whole into one method (§0k "Left"; 766 lines). The target "0 functions over 300 lines in the teaching lane after T7-01" is **not** met. | Keep the target. Status Partial. |
| C-6 | `04` NFR-MAINT-03 "27 unread / 23 undeclared settings". | `backend/tests/test_config_lint.py::test_no_undeclared_settings_reads_in_repo` exists (T2-06, §0m). The unread-settings half has no landed work. | Split in §4. |
| C-7 | `04` §17 SLO "any teaching-integrity breach pages the owner". | `backend/app/metrics.py:172-173` defines `guru_integrity_breach_total`. `infrastructure/prometheus/alerting-rules.yml` has 14 rules and none reads that metric. `grep integrity_breach infrastructure` returns nothing. Also `answer_outcome.py:174-181` `is_integrity_breach` counts only `lane == "teaching"`; `lane_for` (`:28-39`) maps `first_person_bridge` to lane `first_person`, so a bridge turn with a non-empty `model_used` is not counted. Whether that can occur is `[INF]` unknown. | Broken link BL-2. Add rule and widen the check (T9-03, T2-03 follow-up). |
| C-8 | `22a` §2 and `04` list "property-based" tests; `backend/pyproject.toml:90` declares `hypothesis`. | No test imports `hypothesis`. `backend/tests/test_rag_properties.py:1-8` says it uses curated parametrised inputs "without the hypothesis dependency". | Use `hypothesis` (already declared) for the hash and point-ID properties in §7. |
| C-9 | `22a` and `04` NFR-A11Y-01 require WCAG 2.2 AA. | `tests/e2e/a11y-smoke.spec.ts:98` tags are `wcag2a, wcag2aa, wcag21a, wcag21aa`. `tests/e2e/landing-accessibility.spec.ts:14` uses `wcag2a, wcag2aa`. No 2.2 tag. | Add the 2.2 AA axe tag; see NFR-N-1. Automated axe covers only part of WCAG; manual checks stay `[HUMAN]`. |
| C-10 | `gate1_load_test.py` docstring offers `--chaos`. | Chaos modes are `qdrant` and `neo4j` only (`backend/scripts/ops/gate1_load_test.py:1292`), in-process only (`:429-438` raises for live mode). No Redis-down mode. | NFR-REL-03 stays Partial. |
| C-11 | `03` PRD-006 cites `feedback.py:336`. | The route is at `backend/app/api/feedback.py:369` (`POST /feedback/clip-report`), list at `:460`. Seeker control still absent: `src/` matches for `clip-report` are admin files and `App.tsx` only. | Line drift only. |
| C-12 | `CLAUDE.md` inv. 16-17 says the bridge flag is "read live per request"; inv. 23 says an `.env` change needs a container recreate. | The flag is read per request from `settings` (`backend/app/pipeline/stages/first_person_bridge.py:1368-1370`). How an operator changes `settings` at runtime without a restart was not found. | Both statements can hold. Treat "kill switch time" as recreate time until a runtime toggle is proved (NFR-N-4). A second switch exists: `kill_switch_stage.py:54-63` (`generation_kill_switch_enabled`). |
| C-13 | `CLAUDE.md` inv. 23 names `first_person_v8` as the serving collection; inv. 25 names `first_person_v10`. | `backend/app/config.py:41` `_LEGACY_FP_COLLECTION = "first_person_v8"`; `:2323-2324` uses the active collection only in v10-only mode. Both are true under different configuration. | Dated text, not an error. Do not cite either as "current" without the config. |

## 3. Functional requirements

Rows keep the `03` IDs. Gate IDs: A = `FINAL_READINESS_AND_GAP_ANALYSIS.md` §3; B and C = `FINAL_PRODUCTION_RELEASE_READINESS.md`.

### 3.1 Existing FRs (32)

| ID | Statement (testable) | Pri | Obj, need | Where | Task | Test | Acceptance (pass condition) | Gate | Status |
|---|---|---|---|---|---|---|---|---|---|
| FR-ONB-01 ★ | On the first visit on a device, one dismissible card states: answers are the teachers' recorded words or an honest no-match; this is an AI tool, not the teachers; it is not therapy. The card shows once per device and opens later from the menu. | P1 | O3; know what the product is and is not | `src/components/onboarding/` (per `03`); static; flag in browser storage `[INF]` | T6-10 | MISSING (`tests/e2e/seeker-journey.spec.ts::landing page to anonymous chat flow` does not assert the card `[INF]`) | E2E: first load shows the card; second load on the same device does not; menu opens it; axe reports 0 serious or critical on the card; owner signs the copy by hash `[HUMAN]` | B15 (copy), C8 | Partial |
| FR-AUTH-01 | Sign-up cannot submit without the 18+ checkbox. OAuth buttons stay disabled until it is checked. Admin routes need AAL2 and the admin role. | P0 | O6; sign in safely | `src/pages/AuthPage.tsx`; `backend/services/auth_service.py` (`get_current_user_from_supabase`, imported at `backend/app/main.py:87`); Supabase Auth; `user_roles` | — | `src/test/AgeConfirmPage.test.tsx`; `tests/e2e/security-aal2.spec.ts` | Both pass in CI | A20 | Met |
| FR-AUTH-02 ★ | An anonymous visitor may send 5 messages per 24 h (`config.py:1227-1228`). The 6th returns HTTP 429 with `quota_exceeded: true` (`backend/app/api/chat.py:124,656`) and the UI explains it. If Redis is down, a degraded limit applies (`config.py:1230` = 3; exact semantics not read `[INF]`). | P1 | O4; try without an account | `anonSession.ts`; `POST /api/auth/anon-session`; Redis `anon:*` | T1-08 | `backend/tests/test_anon_quota.py::test_memory_adapter_blocks_at_limit` (adapter only); HTTP 429 body test MISSING | Integration: 5 accepted, 6th returns 429 with the flag; with Redis stopped the in-process adapter enforces the degraded limit | A10, B6 | Partial |
| FR-PROF-01 ★ | Every stored preference (language, response preference, memory consent, notifications) is visible and editable on `/profile`. Export and deletion are reachable from the same page. | P2 | O3; manage settings | `src/pages/ProfilePage.tsx`; `src/components/profile/settings/AccountDataCard.tsx`; Supabase `profiles` | — | MISSING | E2E lists each stored key and edits it; a stored key with no UI fails | B12 | Partial |
| FR-CONV-01 ★ | Every chat turn ends in exactly one of: (a) one or more verbatim clips with speaker rule, video, time window and label; (b) an honest no-match with next steps; (c) a safety response; (d) an error card (FR-N-3). No generated prose appears in a teacher's voice. | P0 | O1; ask and receive | `backend/app/api/chat.py:733` (`/chat`), `:1081` (`/chat/stream`); `pipeline_builder.py:53-92`; `backend/rag/nodes/first_person.py`; `first_person_pipeline.py`; Qdrant, Redis exact cache | T2-03 | `backend/tests/test_first_person_pipeline_golden.py::test_execute_matches_recorded_golden` (17 recorded scenarios); `backend/tests/test_first_person_bridge.py::test_assembled_answer_is_source_verbatim_only`; `backend/tests/test_answer_outcome_telemetry.py::test_served` | 100% of fixture and smoke turns carry an `answer_outcome` with outcome in {served, abstained, crisis, boundary, error} (`answer_outcome.py:48-58`); 0 turns on lane `first_person` with non-empty `model_used` | A10 | Partial (fixtures only; staging smoke not run) |
| FR-CONV-02 ★ | For a signed-in user the server is the source of truth for history. List, open, rename, delete and export work from any device. Only the backend writes assistant turns. Deleting a conversation removes it in the browser and in Supabase. Anonymous history is local, capped and labelled as such. | P1 | O3, O4; my history is mine and correct | `src/lib/chatStorage.ts`; `chat.py:479-500`; `chat_messages` RLS | T6-05 (R), T6-09 | `tests/e2e/rls-cross-user.spec.ts::Bob cannot read Alice conversation through the UI` (cross-user only); role-insert RLS test MISSING | RLS test: an authenticated client insert with `role='guru'` fails. Cross-device E2E: a conversation made on device A lists on device B and deletes everywhere | B14 | Partial |
| FR-INT-01 | The system classifies a question as teaching, personal or emotional, practice, guru-specific, out-of-domain, greeting, crisis or ambiguous. Recall of teaching-intent items is at least 95% with the 95% interval reported. | P1 | O1; be understood | `backend/app/pipeline/stages/off_topic_stage.py`; `backend/rag/pipeline_registry.py`; `teaching_scope.yaml` (target) | T4-03, T5-01 | `backend/tests/test_offline_pr_suite.py::test_routing_prefilter_offline` over `evals/pr_suite/routing.jsonl` (10 items; too few for a 95% claim) | Recall at least 95% on at least 100 labelled items (proposal), lower bound reported | B15 | Partial |
| FR-INT-02 | A one-word or context-free question ("Why?") gets one clarifying question and no clip. | P2 | O1; be asked when unclear | AnswerPlan `clarify` mode (target) | T5-01 | MISSING | Held-out ambiguous stratum: at least 90% clarify (proposal; owner sets) | C11 | Open |
| FR-SRC-01 ★ | When the seeker names one teacher or sets a teacher filter, no returned clip has a different verified speaker. | P2 | O5; choose a teacher | `backend/services/guru_registry.py`; request `teacher_ids[]` (target); span `teacher_id` | T8-01, T1-04 | MISSING (no cross-teacher stratum) | "Only Preethaji" yields 0 clips with a Krishnaji verified speaker over a 30-item stratum (proposal) | C9 | Partial |
| FR-RET-01 ★ | Retrieval is hybrid (dense and sparse, RRF), gates the whole candidate pool before per-video deduplication, reranks, applies relevance and standalone gates, and abstains below threshold. | P1 | O1; find the right teaching | `first_person_store.py:703`; `first_person_context_store.py:559,633` (RRF); `first_person_pipeline.py` `_verify_candidates`; Qdrant `first_person_*` | T4-01, T4-02 (landed), T4-06, T2-02 | `test_gate_first_then_dedup.py::test_pipeline_with_store_gates_before_dedup`; `test_v10_hybrid_retrieval.py::test_context_store_hybrid_sends_dense_and_sparse_prefetches_to_groups`; `test_retrieval_bank_harness.py::test_ndcg_at_k` (metric maths) | On the frozen bank report Recall@10, MRR, nDCG@10 with 95% CI; each retrieval PR shows a non-negative delta (see NFR-AIQ-06). The bank has 8 items today. | B15 | Partial (no live baseline) |
| FR-MV-01 ★ | For a multi-theme question the answer shows up to N clips from at least 2 videos. Each clip has its own attribution. Conflicting positions are shown separately. No generated bridge text appears in a teacher's voice. | P2 | O1; combine teachings | `ChatMessage.tsx:540` (per `03`); `facet_planner`, `set_selector` (target) | T5-02 | MISSING | Multi-facet stratum: clips from at least 2 videos on at least 80% of items, each judged relevant by two humans (proposal) | C12 | Partial |
| FR-ATTR-01 | A teacher name shows only when `speaker_verified` is true. Otherwise the UI shows "unverified clip". Video title, link and window always show. | P0 | O1; know who said it | `src/lib/chat/types.ts:293-300` (per `03`); `speaker_verified` copied from the stored clip (inv. 23) | T3-06 | `src/test/citation-attribution.test.tsx` ("downgrades an unverified teacher name from a third-party channel"); `backend/tests/test_bridge_attribution_wp4.py::test_weaver_downgrades_explicit_speaker_verified_false`; `test_citation_contract.py::test_speaker_never_a_channel_or_unknown_placeholder` | 0 clips render a teacher name with `speaker_verified != true` | A10 | Met |
| FR-ATTR-02 ★ | Every sentence shown as a teacher's words in any surface (tips, guides, courses, push captions) resolves to a stored verbatim span id. Otherwise it carries no teacher name. | P0 | O1; never see an invented quote | `backend/app/api/teachings.py`; `src/lib/healingCourses.ts` | T1-03 (landed in part) | `backend/tests/test_no_unsourced_teacher_attribution.py::test_no_says_teaches_literals` | Lint over all surfaces: 0 teacher-attributed sentences without a span id. Gap: admin-curated tips default to the founders pair with no locator check (`IMPLEMENTATION-AGENT-PROMPT.md` §0e); push captions not covered `[INF]` | B17 | Partial |
| FR-SRCX-01 ★ | Playback starts at max(0, `start_ms` - 0.25 s) and ends at `end_ms` + 0.25 s, capped at duration. Source-inspection calls use absolute API URLs. | P2 | O1; watch the original | `first_person_pipeline.py:154,1714-1715`; `CitationCard.tsx`; ESLint relative-URL rule (T1-16) | T1-16 (landed) | `backend/tests/test_first_person_bridge.py` (matches `CITATION_PLAYBACK_PAD_S`; cases not read) | Unit: `start_ms=100` gives 0.0 s; `start_ms=10000` gives 9.75 s; end never exceeds duration; lint finds 0 relative `/api` fetches | A10 | Met |
| FR-ANS-01 | A clip answer carries "Related, not a direct answer" until a calibrated profile exists. | P0 | O1; honest strength of match | `ChatMessage.tsx:235-304` (per `03`); `verification.direct` | T2-04 | `test_first_person_bridge.py`; recorded golden `backend/tests/golden/first_person_pipeline/success_direct.json` contains the phrase | Label on 100% of clip answers while no profile exists | A10 | Met |
| FR-ANS-02 ★ | Today the UI separates two layers: the teacher's exact words and the app's own labelled text. A third layer (assistant explanation, personal connection, reflection) is decision-gated by D-03 / ADR-001 and stays off until then. Each non-verbatim block carries its label. | P1 | O1; know whose words | `ChatMessage.tsx:549` (per `03`); `evals/pr_suite/voice_lint.py` | T5-03 (gated) | `test_offline_pr_suite.py::test_quote_integrity_verifier`; `test_voice_governance_docs.py::test_no_teacher_first_person_directives` | Voice lint finds 0 teacher-first-person sentences; every non-verbatim block has a label | C5 | Partial |
| FR-DEPTH-01 ★ | The depth preference changes the clip count (short = 1; standard = best plus 1 related; deep = set across videos). "Tell me more" returns clips whose point IDs differ from earlier turns. No generated text joins them. | P2 | O1; short or deep | `responsePreferences.ts:12-17` (per `03`); AnswerPlan (target) | T5-01 | MISSING | Depth stratum: "more" repeats a point ID on 0 of N items | C11 | Partial |
| FR-REFL-01 ★ | A reflection prompt appears only when `includeReflection` is true. It is labelled as the app's voice and passes the voice lint. Generating it is decision-gated (D-03). | P3 | O3; reflect | `includeReflection` preference; composer (target) | T5-03 (gated) | MISSING (voice lint covers fixtures) | 0 voice-lint violations over the reflection set | C5 | Partial |
| FR-FUP-01 ★ | A follow-up that refers to the prior answer resolves to that answer's span IDs. The same point ID is not served twice in one conversation unless the seeker asks to repeat. | P2 | O3; continue the thread | `first_person_bridge.py` history handling; `answer_trace` (target) | T5-05, T6-02 | MISSING | Multi-turn stratum: follow-up resolves to the correct prior span on at least 90% of items (proposal) | C11 | Partial |
| FR-MEM-01 | No memory row, read or side effect exists without an active consent receipt. Delete-all removes canonical memory, profiles and vectors. | P0 | O3, O6; remembered only as I allow | `backend/services/canonical_memory/`; `/api/memory/*`; memory tables | T6-01 | `test_canonical_memory_consent_gate.py::test_no_receipt_extracts_nothing`; `::test_revoked_consent_extracts_nothing`; `test_memory_delete_all_completeness.py::test_delete_all_erases_canonical_memory_and_profiles`; `test_emotional_side_effect_consent.py::test_no_consent_no_read_and_no_write` | All four pass. Erasure covers `router_decisions` and admin FKs (NFR-PRIV-02) | B12, B14 | Partial |
| FR-PERS-01 ★ | With the personalise flag on, the paraphrase is labelled "In our own words — not a direct quote" and reads memory only with consent. Generating it is decision-gated (D-03). | P3 | O3; teaching for my situation | `PersonalizeStage` (stage chain, `pipeline_builder.py:77`) | T6-02 | `backend/tests/test_personalize_teaching.py`; `test_personalisation_consent_2026_10_19.py` | Both pass; 0 reads without consent | C5 | Partial |
| FR-LANG-01 ★ | The UI has 14 locales. Crisis detection recall is 100% on a native-reviewed core set in each priority language (D-22). Teacher quotes are never machine-translated into teacher voice. Machine translation is labelled "Machine translation — not the teacher's words". | P0 | O1; use my language | `src/locales/*.json`; `scripts/check_i18n_coverage.mjs` (`lint-test.yml:57`); `backend/tests/test_crisis_copy_never_llm_translated.py` | T1-20, T5-06 | `tests/e2e/i18n-coverage.spec.ts`; `test_crisis_copy_never_llm_translated.py::test_crisis_copy_never_calls_translate_text` | Coverage check green; native-reviewer sign-off filed per priority language `[HUMAN]` | C6 | Partial |
| FR-SAVE-01 | A seeker saves a clip answer with a note and reopens it. A takedown removes the saved item. | P2 | O3; keep what helped | `saved_answers` (target); `POST /api/saved` (target) | T6-04 | MISSING | E2E save, reopen, takedown | C11 | Open |
| FR-JRN-01 ★ | A learning journey lists only items that resolve to span IDs. Progress is the seeker's own record. | P3 | O3; learn step by step | `/api/healing`, daily journey (per `03`) | T6-04 | MISSING | 0 journey items without a span id | C9 | Partial |
| FR-PRAC-01 ★ | Every practice asset (audio, text) has a rights row. No teacher audio is served without a filed licence. | P1 | O2, O6; guided practice | practice pages; rights register | T0-02, D-12 | MISSING | Rights row exists for 100% of served assets | B17, C2 | Partial |
| FR-FB-01 ★ | A thumbs or engagement event is stored and joined to the turn by `request_id`. `useful_answer` = served AND (helpful OR played at least 20 s OR saved) AND NOT reported. | P2 | O1; tell you it helped | `backend/app/api/feedback.py:26,137,182`; `answer_outcome.py:133-155` | T2-03 | `backend/tests/test_feedback.py`; `test_feedback_loop.py`; `test_answer_outcome_telemetry.py` | Event joins by `request_id` in a fixture; the frontend sends the engagement signal (not verified) | B10 | Partial |
| FR-CORR-01 ★ | A seeker reports a clip from a control on the citation card. The report reaches the admin queue. An admin keeps, fixes or quarantines the clip, with an audit log. A quarantined clip never serves again. | P1 | O6; report a wrong clip | `feedback.py:369,460`; `src/admin/pages/ClipReportsPage.tsx`; `clip_reports`; seeker control absent | T6-04, T3-06 (R) | `backend/tests/test_fp_quarantine_identity.py` (identity only); E2E MISSING | E2E: report, then the row shows in admin; serve-time check refuses the quarantined point | B17 | Partial |
| FR-SAFE-01 | The crisis pre-check runs before retrieval. A crisis turn returns call-verified helplines, no teaching clip and no engagement prompt. | P0 | O2; real help | `serene_mind_engine.py`; `distress_stage.py`; `config/helplines.yaml` (1 of 15 call-verified); `src/lib/chat/pushEligibility.ts:8,24` | T4-04 (R), T4-07, T1-10 | `test_crisis_preemption.py::test_severe_distress_preempts_before_proactive_or_graph`; `test_cache_crisis_bypass.py::test_crisis_message_bypasses_hot_cache_hit`; `test_distress_provider_fail_closed.py::test_input_guardrails_precede_circuit_breaker`; `src/test/chat/pushEligibility.test.ts` | Crisis core set recall 100% per priority language and benign over-fire at most 5% (NFR-SAFE-01, -02), clinician-reviewed | B16, C1, C3 | Partial |
| FR-DATA-01 ★ | One deletion path deletes promptly and confirms. It has no save or win-back offer. It removes Supabase rows, memory vectors and push subscriptions. | P0 | O6; export and delete | `src/components/profile/settings/AccountDataCard.tsx`; `CancelFlow.tsx`; `supabase/functions/delete-my-account`, `export-my-data` | T1-12, T6-06 (R) | `test_memory_delete_all_completeness.py::test_delete_all_reports_partial_failure_when_a_store_fails`; direct-deletion E2E MISSING | Staging: delete a test user, then 0 rows in memory, consent, outbox, conversation tables | B12, C10 | Partial |
| FR-ADM-01 | Admin routes need AAL2 and the admin role. | P0 | O4; operate safely | admin app; `/api/admin/*`; `user_roles` | — | `tests/e2e/security-aal2.spec.ts`; `backend/tests/test_authz_regression.py` | Both pass in CI | A10 | Met |
| FR-ADM-02 ★ | In production the `seed_admin_demo` RPC is absent or refuses. | P2 | O4; no demo data | `supabase/migrations/20260724080000_harden_security_and_rls_lints.sql` (defines it); `useSeedDemo.ts` (per `03`) | T9-01 | MISSING | Production config test: RPC call returns an error | B1 | Open |
| FR-TCH-01 | A new teacher is added by configuration only. | P3 | O5; add a teacher safely | `backend/config/gurus.yaml` | T8-01, T8-02 | MISSING | Dry-run of the `11` §6 checklist | later | Open |

> **Update 2026-11-06 (batch 13, a33d6b8d):** FR-CORR-01 is Partial. The citation card has a report control with four categories (`src/components/chat/CitationCard.tsx`). The route is now `backend/app/api/feedback.py:386` (was `:369`) and the list is `:478` (was `:460`). The control sends a video id, not a clip id (D-PQ7 open). No E2E test was added.

> **Update 2026-11-06 (batch 13, a33d6b8d):** FR-SAVE-01 is Partial, not MISSING. `POST/GET/DELETE /api/feedback/saved-answers` (`backend/app/api/feedback.py:572-640`) and `src/lib/savedAnswersStorage.ts` exist. Storage is a local JSONL file with no takedown link, no erasure link and no E2E test. The target tables `saved_answers` and `POST /api/saved` were not built. FR-CORR-01: see its own update note.

### 3.2 New functional requirements (not in `03`)

| ID | Statement (testable) | Pri | Obj, need | Where | Task | Test | Acceptance (pass condition) | Gate | Status |
|---|---|---|---|---|---|---|---|---|---|
| FR-N-1 | The server sends citations, the label and safety notices before or with the final text. If the stream ends before the terminal event, the client marks the turn incomplete and does not save it as a finished answer. | P0 | O1; never keep unlabelled teacher text | `backend/app/stream_orchestrator.py`; `src/lib/chat/streaming.ts`; finding UX-005, F-13 | T1-18 | MISSING | Cut-stream test: partial text shows no teacher attribution and is not in history | A10 | Open |
| FR-N-2 | If the bridge is off, or the first-person node faults, a teaching-lane turn returns a static abstain (`fp_disabled` / `fp_node_error`) with no model call. | P0 | O1; never generated teaching | `backend/services/fp_fail_closed.py:26`; `config.py:435`; `first_person_bridge.py:1378-1386`; `rag/pipeline_registry.py:65-77` | T1-05 | `test_fp_fail_closed.py::test_bridge_off_returns_static_abstain_without_llm`; `::test_node_exception_abstains_and_counts` | Both pass; `model_used` is None; counter `guru_fp_fail_closed_total` rises. Open item: the classifier-failure branch in `graph_stage.py` (§0 T1-05) | A10 | Met |
| FR-N-3 | Every chat error state shows a care line with a call-verified helpline and a retry. Developer text goes to the console only. | P1 | O2; help when the app fails | `src/components/chat/ChatErrorBanner.tsx`; `src/lib/chat/errors.ts`; `config/helplines.yaml` | T1-17 | `src/test/ChatErrorBanner.test.tsx`; `src/test/chatErrors.test.ts`; `src/test/crisisHelplines.test.tsx::leads with the call-verified line` | Unit tests pass; E2E for 500, drop, timeout, 429 (MISSING) | A10 | Partial |
| FR-N-4 | A clip serves only if `sha256(verbatim_text)` equals the integrity field (`source_text_hash` on v10), `find_artifact()` is None, the speaker is allowlisted, and Tier 1 and Tier 2 gates pass. Otherwise the clip is quarantined. | P0 | O1; verbatim integrity | `first_person_pipeline.py:438,2642`; `_verify_candidates` | T3-03 | `test_fixture_stores.py::test_cached_entry_whose_citation_no_longer_verifies_is_a_miss`; `test_gate_first_then_dedup.py::test_pipeline_serves_valid_lower_span_when_top_span_fails_gate`; `test_fp_quarantine_identity.py`; `test_transcript_hash.py` | 0 hash-mismatched clips served in fixtures; live audit `[LIVE-Q]` | A7 | Met |
| FR-N-5 | An out-of-corpus question abstains. A scorer or answerability failure abstains as `relevance_indeterminate` or the answerability reason, never as a served clip. | P0 | O1; no leak into teacher voice | `first_person_pipeline.py:979,1120` (`run_llm_coroutine`) | T4-06 | `test_relevance_standalone_gates.py`; `test_answerability_check.py`; `test_offline_pr_suite.py::test_abstain_null_offline` (6 null items) | 0 leaks on at least 60 null items (NFR-AIQ-02) | B15 | Partial |
| FR-N-6 | Only clips whose rights the register vouches for are served. Production does not start if the register is missing or empty. | P0 | O6; rights | `first_person_serving_contract.py`; health field `rights_register` | T3-01 | `test_fixture_stores.py::test_search_hybrid_refuses_a_clip_the_rights_register_does_not_vouch_for`; `test_rights_register_startup.py::test_missing_register_fails_production` | Both pass. The register still holds owner-local paths (§0c); scrub needs owner re-pin | B17 | Met |
| FR-N-7 | The serving collection comes from one setting. v10-only mode needs both harness flags true. The serving contract is validated at startup. Rollback is a setting change. | P1 | O4; reproducible serving | `config.py:41,201,2323-2324`; `first_person_serving_contract.py:329` | T3-12, T3-05 | `test_first_person_serving_contract.py::test_both_stores_may_not_share_one_collection`; `test_first_person_v10_only.py::test_mode_needs_alias_harness_and_terminal` | Both pass; startup log names the collection | B5 | Met |
| FR-N-8 | `takedown(source_id)` clears Qdrant points, exact-cache entries and citations within 24 h and reports what it cleared. | P1 | O6; withdraw content | source registry (target) | T3-06 (R) | MISSING (cache re-verify on hit exists: `test_fixture_stores.py::test_cached_entry_whose_citation_no_longer_verifies_is_a_miss`) | Fixture dry-run report lists all stores cleared | B17 | Open |
| FR-N-9 | Erasure is a durable queued job that completes while the backend is down. Scheduled deletions ("keep 30/90 days") execute. | P0 | O6; DPDP erasure | `delete-my-account`; purge job (target) | T6-06 (R) | MISSING | Erasure drill with the backend stopped; purge test with one due row and one not-due row | B12 | Open |
| FR-N-10 | A collection is promoted only when the scorecard has 0 BLOCKER fails, strict-clean rate meets the threshold, and `approved_corpus_version` equals the served version. | P1 | O1; data quality | `scripts/ops/data_quality_audit.py`; serving contract | T3-05 | `test_data_quality_promotion_gate.py::test_scorecard_promotion_gate_refuses_blocker_failure`; `::test_serving_contract_refuses_approved_corpus_version_mismatch` | Both pass. Threshold 60% is a proposal (NFR-DI-05) | B5 | Met |
| FR-N-11 | A corpus build replaces a video's points per video, snapshots before the first write, refuses an empty build, and writes only with the write key. | P1 | O1; safe rebuild | `build_full_corpus_v10.py`; `QdrantService` | T3-02, T3-04 | `test_builder_replace_and_snapshot.py::test_builder_refuses_empty_build`; `test_qdrant_write_governance.py::test_backend_read_only_client_rejects_writes` | Both pass. Running a real build needs the owner | B5 | Met |
| FR-N-12 | An operator can stop teaching serving on the next request: the bridge flag read per request, and the separate generation kill switch. | P1 | O4; incident control | `first_person_bridge.py:1368-1370`; `kill_switch_stage.py:54-63` | T1-05 | `test_fp_fail_closed.py::test_bridge_off_returns_static_abstain_without_llm` | Flag off gives abstain on the next request. Runtime toggle path is Unknown (C-12) | B11 | Partial |

> **Update 2026-11-06 (batch 9, 43b6c6fd):** FR-N-1 is met in code, not run: the server sends `done` before `final` (`backend/app/stream_orchestrator.py:415-427`), and the client throws `stream_interrupted` and drops the turn when `done` never arrives (`src/lib/chat/streaming.ts:428-431`; `src/components/chat/ChatInterface.tsx:1712-1730`). Test: `src/test/chat/streaming-contract.test.ts`. UX-005 Closed. BL-1 and BL-3 in section 9 are out of date for the same reason.

## 4. Non-functional requirements

Targets marked "proposal" are not owner-approved. A target is binding only with a baseline on the same environment (`04` §1).

### 4.1 Existing NFRs (70)

| ID | Statement (testable) | Pri | Where | Task | Test | Acceptance | Gate | Status |
|---|---|---|---|---|---|---|---|---|
| NFR-REL-01 | At least 99.5% of chat requests reach a terminal state within 20 s. | P1 | `answer_outcome.py` latency histogram | T2-03, T9-02 | `backend/scripts/ops/gate1_load_test.py` (mock LLM only) | Staging run at c20 with the real LLM | B8 | Aspirational |
| NFR-REL-02 | Monthly non-5xx availability of `/api/chat` at least 99.5% (beta, provisional). | P1 | edge probe | T9-03 | MISSING | One-minute synthetic probe over 30 days | B10 | Aspirational |
| NFR-REL-03 ★ | With Redis down, spend controls refuse rather than allow. | P0 | `backend/services/llm_budget_guard.py`; `config.py:643-652` | T1-07 | `test_llm_budget_guard.py::test_llm_budget_guard_exceeded_blocks_call`; Redis-down chaos MISSING (C-10) | 0 fail-open paths in a Redis-down test | A15, B6 | Partial |
| NFR-REL-04 | With Qdrant down, the answer is the exact cache or an honest abstain within 5 s. | P0 | `gate1_load_test.py --chaos qdrant` (in-process) | T1-14 | not in CI | Fault test in CI: 100% abstain within 5 s | B7 | Partial |
| NFR-REL-05 | A teaching-route fault produces 0 generated teaching text. | P0 | `fp_fail_closed.py` | T1-05 | `test_fp_fail_closed.py::test_node_exception_abstains_and_counts` | Passes | A10 | Met |
| NFR-PERF-01 | Crisis response p99 at most 2 s with no LLM call. | P0 | `distress_stage.py` | T9-02 | MISSING | Staging p99 | B8 | Aspirational |
| NFR-PERF-02 | Uncached teaching p95 at most 10 s on staging (provisional); 6 s after T4-06 and T7-02. | P1 | `first_person_pipeline.py` | T4-06, T7-02 | `gate1_load_test.py` | Staging p95 | B8 | Aspirational |
| NFR-PERF-03 | Time to first visible content p50 at most 3 s (provisional). | P2 | SSE status events | T9-02 | MISSING | Staging p50 | B8 | Aspirational |
| NFR-PERF-04 | Exact-cache hit p95 at most 500 ms. | P2 | Redis exact cache | T9-02 | `test_fixture_stores.py::test_exact_cache_round_trip_on_real_redis` (function only) | Timed staging run | B8 | Aspirational |
| NFR-PERF-05 | Retrieval stage p95 at most 300 ms on staging. | P2 | `stage_latencies_ms` in `answer_outcome` | T9-02 | MISSING | Staging p95 from outcome events | B8 | Aspirational |
| NFR-SCAL-01 | Real-model concurrency c20 with error rate under 1% and within NFR-PERF-02. | P1 | `gate1_load_test.py` | T9-02 | MISSING (real run) | Staging run | B8 | Aspirational |
| NFR-SCAL-02 | Retrieval p95 at 10x spans stays within NFR-PERF-05. | P3 | Qdrant | T9-02 | MISSING | Synthetic replica run | later | Aspirational |
| NFR-SCAL-03 | Prompt tokens at turn 50 at most turn-1 budget plus 20%. | P2 | `TokenAccumulator.record_call` | T5-05 | MISSING | 50-turn replay | B8 | Aspirational |
| NFR-SCAL-04 ★ | One `max_concurrent_chat` value per environment, tested. Code default is 12 (`config.py:1030`). | P2 | `config.py`, compose | T9-01 | MISSING | Config test compares compose, code, docs | A4 | Open |
| NFR-SEC-01 | 0 LLM-spending endpoints without auth or quota. `/api/first-person/query` is open (`first_person.py:295`; D-07). | P1 | `first_person.py` | T1-08 | MISSING | Route-table test; unauthenticated call is refused | A10 | Open |
| NFR-SEC-02 | 100% of admin routes need AAL2 and role, checked in CI. | P0 | `/api/admin/*` | — | `test_authz_regression.py` | Route-table check | A10 | Partial |
| NFR-SEC-03 | 0 real secrets in tracked files. | P0 | `.github/workflows/security-audit.yml` (gitleaks) | — | CI job | Job green | A20 | Met |
| NFR-SEC-04 | 0 datastores reachable beyond localhost or private network; Qdrant keyed. | P0 | compose; `config.py` Qdrant keys | T1-14, T3-02 | `test_docker_compose_healthcheck.py::test_datastore_ports_bound_to_loopback_only`; `test_qdrant_write_governance.py::test_qdrant_api_keys_declared_on_settings` | Both pass; keys set in the environment `[LIVE-R]` | A7 | Partial |
| NFR-SEC-05 | 0 high or critical dependency CVEs unpatched over 30 days. | P1 | `dependency-check.yml`; `pip-audit` | — | CI job | Job green, exceptions listed | A20 | Partial |
| NFR-SEC-06 | 0 prompt-injection fixtures change routing or verification. | P1 | `test_graph_evidence_injection.py`; `test_node_config_injection.py` | T6-03 | those files; fixture set from `18` MISSING | 0 changes over the fixture set | B14 | Partial |
| NFR-PRIV-01 ★ | Seeker-text logging sites at most the committed budget; the budget reaches 0. | P0 | `test_no_seeker_text_in_logs.py` | T1-09 | `::test_seeker_text_logging_budget_only_goes_down` | Budget 19 (§0b) falls to 0 | B12 | Partial |
| NFR-PRIV-02 | Erasure covers all stores within 72 h, automated and queued. | P0 | purge job (target) | T6-06 (R) | MISSING | Drill | B12 | Open |
| NFR-PRIV-03 | 0 memory reads or side effects without active consent. | P0 | canonical memory | T1-10 | `test_emotional_side_effect_consent.py::test_consent_lookup_error_fails_closed` | Passes | B14 | Met |
| NFR-PRIV-04 | 0 inferred sensitive profiles stored (MEM-004). | P1 | `l3_persona_generator` | T6-03 | MISSING | Persona writer absent or inert | B12 | Open |
| NFR-MAINT-01 ★ | Runtime functions over 300 lines do not exceed a committed baseline; the baseline only falls. 0 in the teaching lane (not met: harness method 766 lines, C-5). | P2 | `pyproject.toml` ratchet (target) | T7-05 | MISSING | Ratchet test | later | Partial |
| NFR-MAINT-02 ★ | Silent exception swallows do not exceed a committed baseline (70 at audit); baseline only falls. | P2 | ruff BLE (target) | T7-05 | MISSING | Ratchet test | later | Open |
| NFR-MAINT-03 ★ | 0 settings read but undeclared; unread settings do not exceed a committed baseline. | P2 | `scripts/guards/config_lint.py` | T2-06 | `test_config_lint.py::test_no_undeclared_settings_reads_in_repo` | Undeclared 0 (met); unread not addressed | A4 | Partial |
| NFR-MAINT-04 | 1 definition of the teaching scope. | P2 | `off_topic_stage.py` | T4-03 | MISSING | Grep guard finds 1 | later | Open |
| NFR-MAINT-05 ★ | New teacher-name literals in runtime code: 0; total does not exceed a committed baseline (621 at audit). | P2 | guard (target) | T8-02 | MISSING | Guard | later | Open |
| NFR-MAINT-06 | `CLAUDE.md` at most 15 KB (now 48,533 bytes); status list at most 30 KB (now 409,020 bytes). | P3 | `CLAUDE.md` | T1-15 | MISSING | `wc -c` check in a guard | later | Open |
| NFR-OBS-01 | 100% of turns emit `answer_outcome`. | P1 | `PipelineCoordinator.execute`; `answer_outcome.py` | T2-03 | `test_answer_outcome_telemetry.py::test_error` and the other three cases | Passes (C-2) | A10 | Met |
| NFR-OBS-02 | 100% of LLM calls log `prompt_id@version`, model, tokens, cost. `prompt_id` defaults to `"unknown"` (`answer_outcome.py:103`); no version field. | P1 | `TokenAccumulator`; prompt registry (target) | T5-07 | MISSING | Every call has a registered id and version | B10 | Partial |
| NFR-OBS-03 | 5 of 5 drill alerts fire: integrity breach, crisis-lane error, spend 80%, p95 breach, data-audit fail. 14 rules exist; none reads `guru_integrity_breach_total` (C-7). | P1 | `infrastructure/prometheus/alerting-rules.yml` | T9-03 | MISSING | Drill | B10 | Open |
| NFR-COST-01 | Spend cap enforced and fail-closed in every non-dev environment. | P0 | `config.py:643-652,2491-2499` | T1-07 | `test_llm_budget_guard.py`; `test_openrouter_budget.py` | Pass; production refuses start without it | A15, B6 | Met |
| NFR-COST-02 | LLM calls per teaching turn at most 2 (short) or 3 (deep); now 3 to 4. | P2 | `first_person_pipeline.py` | T4-06 | MISSING | Count from `record_call` | B8 | Open |
| NFR-COST-03 ★ | See NFR-N-6. | P2 | — | T2-03 | — | — | B10 | Partial |
| NFR-COST-04 | 0 models without a dated price entry. | P2 | price table | T1-07, D-16 | MISSING | Lint | B6 | Open |
| NFR-A11Y-01 | 0 axe serious or critical violations on chat, citation, profile, practices. Tags lack 2.2 (C-9). | P1 | `tests/e2e/a11y-smoke.spec.ts` | T9-02 | `a11y-smoke.spec.ts` | Add the 2.2 tag; 0 violations | C7 | Partial |
| NFR-A11Y-02 | Clip playback shows the spoken words as text. | P1 | `CitationCard.tsx` | — | MISSING | Component test | C7 | Partial |
| NFR-A11Y-03 | At least 1 screen-reader session per study round. | P2 | user study | T2-07 | n/a | Study report `[HUMAN]` | C7 | Open |
| NFR-I18N-01 ★ | Locale completeness check is green; native sign-off is filed per priority language. | P1 | `lint-test.yml:57-69` | T1-20 | CI scripts | Green; sign-off `[HUMAN]` | C6 | Partial |
| NFR-I18N-02 | Crisis recall is 100% on the native and clinician core set per priority language. | P0 | `serene_mind_engine.py` | T4-04 (R) | `evals/pr_suite/distress_crisis.jsonl` (5 items) | Reviewed set passes | C1, C6 | Open |
| NFR-I18N-03 | 0 teacher quotes machine-translated and shown as teacher voice. | P0 | client translation popover (§0b) | T5-06 | MISSING named test | Test over the popover | A10 | Partial |
| NFR-I18N-04 | 100% of vNext spans carry a language field. | P2 | span schema | T5-06 | MISSING | Writer contract test | later | Open |
| NFR-DI-01 | 0 hash-mismatched spans served. | P0 | `first_person_pipeline.py:438` | T3-03 | `test_fixture_stores.py::test_cached_entry_whose_citation_no_longer_verifies_is_a_miss` | Pass; live audit `[LIVE-Q]` | A7 | Met |
| NFR-DI-02 | 0 point-ID recomputation mismatches. | P1 | `first_person_store.py:106-112` | T3-05 | MISSING (property test proposed, §7) | Live runbook `22` `[LIVE-Q]` | A7 | Partial |
| NFR-DI-03 | 100% of points carry registry teacher IDs. | P2 | payload writers | T3-07 | MISSING | Audit | B5 | Open |
| NFR-DI-04 | 0 `speaker_verified=true` without a method. | P0 | `test_speaker_verified_plumbing.py`; `nightly-audit.yml` | T3-05 | that file | Daily audit result 0 | B5 | Partial |
| NFR-DI-05 | 0 BLOCKER fails; strict-clean at least 60% (proposal). | P1 | `fp_data_quality_scorecard.py` | T3-05 | `test_data_quality_promotion_gate.py::test_scorecard_promotion_gate_refuses_low_strict_clean` | Gate passes; data does not (39.9% `[DOC-CLAIM 06]`) | B5 | Partial |
| NFR-DI-06 ★ | Drift is any of: point-count shift, approved-version mismatch, hash mismatch. Detection within 24 h. | P1 | `alerting-rules.yml:224` (`CollectionPointCountShift`); `nightly-audit.yml:4-5` (03:00 UTC) | T3-05 | `test_data_quality_promotion_gate.py` | Nightly run plus alert | B10 | Partial |
| NFR-AIQ-01 ★ | (a) Served share of answerable held-out items at least 30%. (b) Usefulness at least 4 of 5 on at least 70% of answerable items, measured first on clip-only answers. Layered answers are decision-gated (D-03). | P1 | held-out set | T2-04 | MISSING | Human-labelled run | B15, C11 | Aspirational |
| NFR-AIQ-02 | 0 out-of-corpus leaks on at least 60 null items. | P0 | `evals/first_person/ooc13.jsonl`; `unanswerable60_draft.jsonl` (draft) | T2-04 | `test_offline_pr_suite.py::test_abstain_null_offline` (6) | 0 of 60 | B15 | Partial |
| NFR-AIQ-03 | Teaching-intent routing recall at least 95%. | P1 | routing set (10 items) | T4-03 | `test_routing_prefilter_offline` | At least 100 items | B15 | Aspirational |
| NFR-AIQ-04 | 0 unsupported assistant-explanation sentences. Not applicable until D-03. | P1 | verifier (target) | T5-04 | MISSING | Held-out | C5 | Aspirational |
| NFR-AIQ-05 | Direct-answer label error at most 1% at delta 0.05; needs at least 299 items with 0 errors (inv. 3). | P0 | `evaluation/gold/calibrator.py` | T2-04 | MISSING | Profile exists | C4 | Aspirational |
| NFR-AIQ-06 | Recall@10 and nDCG@10 on the frozen bank have a baseline; each change has a non-negative delta with CI. | P1 | `evals/retrieval_bank/` | T2-02 | `test_retrieval_bank_harness.py::test_confidence_interval` | Live baseline stored | B15 | Partial |
| NFR-AIQ-07 | Human rater agreement kappa or alpha at least 0.6. | P1 | `18` §6 | T2-04 | n/a | Computed `[HUMAN]` | B15 | Aspirational |
| NFR-AIQ-08 | 0 teacher-voice violations in assistant text. | P0 | `evals/pr_suite/voice_lint.py`; `test_general_mode_no_register.py` | T1-06 | `test_offline_pr_suite.py::test_quote_integrity_verifier` | 0 over fixtures | A10 | Partial |
| NFR-SAFE-01 | Crisis recall 100% on the clinician core set per priority language. | P0 | `distress_crisis.jsonl` | T4-04 (R) | non-blocking | Reviewed set passes | C1 | Aspirational |
| NFR-SAFE-02 | Benign on-topic questions routed to distress at most 5% on at least 200 reviewed items (baseline 17 of 150 `[DOC-CLAIM]`). | P1 | `distress_benign.jsonl` (8) | T4-04 (R) | `test_distress_benign_offline` | Reviewed set | B16 | Open |
| NFR-SAFE-03 | 0 benign multi-turn escalations to SEVERE on at least 50 dialogues. | P1 | none | T4-04 (R) | MISSING | Set exists and passes | B16 | Open |
| NFR-SAFE-04 | 100% of displayed helplines call-verified within the age limit (1 of 15 now). | P0 | `config/helplines.yaml` | T4-07 | gate check (T1-11) | Dates filed `[HUMAN]` | C3 | Open |
| NFR-SAFE-05 | 0 engagement prompts after a safety-route answer (push covered). | P1 | `pushEligibility.ts` | T1-10 | `pushEligibility.test.ts` | Passes | A10 | Met |
| NFR-DR-01 | RPO at most 24 h for Postgres, Qdrant, audio; audio in 2 off-host copies. Daily dump workflow exists (`.github/workflows/backup.yml`, 03:00); alert `BackupStale` exists (`alerting-rules.yml:181`). | P1 | `backup.yml` | T3-10 | CI | Restore drill (NFR-N-5) | B9 | Partial |
| NFR-DR-02 | RTO at most 4 h, measured in a drill (provisional). | P1 | runbook | T3-10 | MISSING | Drill | B9 | Aspirational |
| NFR-DR-03 | Serving-collection rollback at most 15 min, drilled. Rollback is `FIRST_PERSON_COLLECTION` plus recreate (inv. 23). | P1 | config | T9-04 | MISSING | Drill | A13 | Aspirational |
| NFR-CI-01 | 0 served spans without a filed `permission_ref`. | P0 | register | T3-01 | `test_fixture_stores.py::test_search_hybrid_refuses_a_clip_the_rights_register_does_not_vouch_for` | Pass; filings `[HUMAN]` | B17 | Partial |
| NFR-CI-02 | Takedown completes across stores within 24 h with a report. | P1 | source registry | T3-06 (R) | MISSING | Fixture dry-run | B17 | Open |
| NFR-CI-03 | 0 unsourced teacher attributions in any surface. | P0 | lint | T1-03 | `test_no_unsourced_teacher_attribution.py`; `test_no_fabricated_guru_attribution.py` | Lint passes | B17 | Partial |
| NFR-CI-04 | 0 teaching text or teacher audio in a public repository without written permission. | P0 | `scripts/guards/lesson_guards.py` publication | T0-02 | guard | Repository private or purged (D-01) | B2 | Open |

### 4.2 New NFRs (missing from `04`)

| ID | Statement (testable) | Pri | Where | Task | Test | Acceptance | Gate | Status |
|---|---|---|---|---|---|---|---|---|
| NFR-N-1 | The chat flow (landing, chat, citation card, error card, crisis card, profile, deletion) has 0 unresolved WCAG 2.2 level A and AA failures. Automated axe covers part; a manual keyboard and screen-reader pass covers the rest. | P1 | `tests/e2e/a11y-smoke.spec.ts:98`; `src/test/ChatMessage-a11y.test.tsx` | T9-02 | axe spec (no 2.2 tag) | Add the 2.2 tag; 0 serious violations; manual checklist signed `[HUMAN]` | C7 | Partial |
| NFR-N-2 | Meaning preservation: for each priority language, two native reviewers rate at least 95% of sampled assistant-voice translations "meaning preserved" (proposal), with agreement at least 0.6. Teacher quotes are never translated (inv. 16). | P1 | translation glue; `src/locales/*.json` | T5-06, T1-20 | MISSING | Review record per language `[HUMAN]` | C6 | Open |
| NFR-N-3 | Model lifecycle: a change to an LLM id, prompt, encoder, reranker or scorer ships only with (a) the PR suite pass, (b) a frozen-bank delta with CI, (c) a dated price entry, (d) the encoder fingerprint in the serving contract. | P1 | `first_person_serving_contract.py` (encoder fields, T3-12); `evals/` | T3-12, T5-07 | `test_first_person_serving_contract.py` (encoder part); gate for (a)-(c) MISSING | CI job fails a model or prompt change with no delta file | B15 | Partial |
| NFR-N-4 | Incident response (targets, proposal): integrity breach or crisis-lane error alert reaches the owner in 5 min; teaching serving stops in 15 min using the verified path (setting change plus recreate; runtime toggle Unknown, C-12); a written runbook exists for provider outage, Qdrant down, Redis down, bad deploy, cost spike. | P1 | `alerting-rules.yml`; `first_person_bridge.py:1368` | T9-03 | MISSING | Tabletop and alert drill | B10, B11 | Open |
| NFR-N-5 | Restore drill: a Qdrant snapshot and a Postgres dump restore into scratch targets. The restored Qdrant returns the same top-1 for 10 fixed questions. Done once before Gate B and quarterly after. | P1 | `backup.yml`; `backup-drill-reminder.yml`; `scripts/ops/snapshot_qdrant.py` | T3-10 | MISSING | Drill report filed | B9 | Open |
| NFR-N-6 | Cost per useful answer = sum of LLM USD over turns in a week divided by turns with `useful_answer` true (`answer_outcome.py:133-155`). A weekly report exists. Target trend is set after 2 weeks of staging data. | P2 | `answer_outcome.py`; `TokenAccumulator.record_call` | T2-03 | `test_answer_outcome_telemetry.py` (record shape only); report job MISSING | Report runs on staging and is non-empty | B10 | Partial |
| NFR-N-7 | One answer trace: from a `request_id` an operator reconstructs lane, route, stage latencies, each LLM call (prompt id, model, tokens, cost), gate outcomes and cache hit, with no seeker text. | P1 | `answer_outcome.py:69,103,112` | T2-03, T5-07 | `test_answer_outcome_telemetry.py::test_no_seeker_text_or_ids` | Join works on a staging turn; prompt version present | B10 | Partial |
| NFR-N-8 | Data-integrity invariants run as executable checks (list in §6). | P0 | tests in §6 | T3-05 | see §6 | Each check green on the serving collection | A7, B5 | Partial |
| NFR-N-9 | Every telemetry, staging or rejection table has a tested retention purge (L-RETENTION-LIFECYCLE-1). | P2 | `tasks.retention_tasks.cleanup_retention_data` | — | `backend/tests/test_retention_lifecycle.py` | Passes | B12 | Met |
| NFR-N-10 | CI is green on the release commit from a clean checkout. All workflows failed on `c9b42d3e` (`FINAL_READINESS_AND_GAP_ANALYSIS.md` §2 `[V-GIT]`). | P0 | `.github/workflows/` | T0-04 | workflows | All required workflows pass | A20, B1 | Open |
| NFR-N-11 | The offline PR suite blocks every PR. | P1 | `.github/workflows/eval-gate.yml:61` | T2-01 | `test_offline_pr_suite.py` | Job green | A20 | Met |
| NFR-N-12 | Production startup refuses unsafe posture: spend guard off, register missing, wildcard CORS, collection-contract errors. | P0 | `config.py:2491-2499`; `test_main_cors.py`; `test_rights_register_startup.py` | T1-07, T1-14, T3-01 | `test_main_cors.py::test_production_warns_when_exact_origins_empty`; `test_rights_register_startup.py::test_missing_register_fails_production` | Pass | A4 | Met |

### 4.3 Counts

| Table | Met | Partial | Open | Aspirational | Total |
|---|---|---|---|---|---|
| Existing FRs (§3.1) | 5 | 23 | 4 | 0 | 32 |
| New FRs (§3.2) | 6 | 3 | 3 | 0 | 12 |
| Existing NFRs (§4.1) | 7 | 25 | 20 | 18 | 70 |
| New NFRs (§4.2) | 3 | 5 | 4 | 0 | 12 |

Rule: status follows the definitions in §1.2. These counts were produced by counting the Status column; see the self-check in the final report.

## 5. Vague requirements rewritten

| ID | Original (`03` or `04`) | Problem | Rewrite |
|---|---|---|---|
| FR-ONB-01 | "copy reviewed by the owner" | Not machine-testable | Show-once and menu-reopen E2E plus a hash-filed sign-off |
| FR-DEPTH-01 | "'tell me more' returns new, relevant clips" | "relevant" undefined | Point IDs differ from earlier turns; relevance by human stratum |
| FR-FUP-01, FR-REFL-01, FR-PERS-01, FR-JRN-01, FR-SRC-01, FR-FB-01, FR-ADM-01 | No acceptance criterion in `03` | Untestable | Rows in §3.1 add one |
| FR-CONV-02 | "synced for signed-in users; retention user-configurable" | Wrong (erratum in `03`) | Server is source of truth |
| NFR-AIQ-01 | One row with two targets | Compound | Split into (a) and (b) |
| NFR-COST-03 | "non-increasing trend while usefulness rises" | Untestable without a baseline | Formula and weekly report (NFR-N-6) |
| NFR-DI-06 | "drift detection at most 24 h" | Drift undefined | Three named drift types |
| NFR-I18N-01 | "keep green; native review signed" | Two things | Split into check and sign-off |
| NFR-MAINT-01, -02, -05 | "ratchet down" | No pass condition | "At most the committed baseline; baseline only falls" |
| NFR-PRIV-01 | "0 (guard)" | Current value 19 | Budget plus date for 0 |
| NFR-REL-03 | "0 fail-open paths" | Paths undefined | Redis-down test |
| NFR-SCAL-04 | "one configured value" | Value unnamed | Config test across compose, code, docs |

Requirements still not fully machine-testable: FR-ONB-01 (copy sign-off), NFR-A11Y-03, NFR-AIQ-07, NFR-I18N-02, NFR-SAFE-01, NFR-SAFE-04, NFR-N-2. These need a human step by design.

## 6. Data-integrity invariants as executable checks (NFR-N-8)

| Invariant | Check | Exists? |
|---|---|---|
| INV-1 `sha256(verbatim_text)` equals the integrity field | `first_person_pipeline.py:438` at serve time | Yes; `test_fixture_stores.py` |
| INV-2 point ID equals `uuid5(NAMESPACE, f"{hash}:{start}:{end}")` | `first_person_store.py:106-112` | Function yes; recompute test MISSING (use `hypothesis`) |
| INV-3 `speaker_verified` copied from the clip, with a method | `test_speaker_verified_plumbing.py`; nightly audit | Partial |
| INV-4 clip has a register clearance | `test_search_hybrid_refuses_a_clip_the_rights_register_does_not_vouch_for` | Yes |
| INV-5 exact-cache hit re-checks `points_servable` | `test_points_servable_reads_the_store_every_time` | Yes |
| INV-6 no personalised answer in a shared cache | `test_cache_personalization_leak.py::test_personalized_answer_is_not_written_to_shared_cache` | Yes |
| INV-7 builder refuses an empty build; new version is a new collection | `test_builder_refuses_empty_build` | Yes |
| INV-8 served collection equals approved version | `test_serving_contract_refuses_approved_corpus_version_mismatch` | Yes |
| INV-9 a served turn with generated text is counted | `is_integrity_breach` (`answer_outcome.py:174`) | Partial: lane `teaching` only; no alert (C-7) |

## 7. Broken traceability links

The chain is: objective, need, FR or NFR, component, source files, data, API, task, test, acceptance, release gate.

| # | Requirement | Where the chain breaks | Evidence | Repair |
|---|---|---|---|---|
| BL-1 | FR-N-1 stream integrity (UX-005) | No test; task T1-18 not landed; no gate ID names it | `FINAL_PENDING_WORK_REGISTER.md` row UX-005 Open | Add test, add to A10 smoke ("cut stream") |
| BL-2 | Teaching-integrity SLO (`04` §17), INV-9 | Metric exists, alert missing, detector narrower than the SLO | C-7 | Add alert rule and cover lane `first_person` |
| BL-3 | FR-CORR-01 / PRD-006 | Backend route and admin page exist; seeker control missing; no E2E; T6-04 needs reserved T3-06 | `feedback.py:369`; C-11 | Build control after T3-06 |
| BL-4 | FR-SAFE-01, NFR-SAFE-01..03, NFR-I18N-02 | Test sets have 5, 8 items; no multi-turn set; clinician review pending; task T4-04 reserved | `evals/pr_suite/distress_*.jsonl` | Clinician-owned sets; then make blocking |
| BL-5 | NFR-PERF-*, NFR-REL-01, NFR-SCAL-01 | No staging; load tool is mock-LLM; no probe | `gate1_load_test.py:1292`; `FINAL_READINESS_AND_GAP_ANALYSIS.md` §2 | Staging first (T9-01), then B8 |
| BL-6 | NFR-OBS-03, NFR-N-4 | Alert rules and runbook do not exist for the stated alerts | `alerting-rules.yml` 14 rules | Add rules; tabletop |
| BL-7 | FR-N-9, FR-DATA-01, NFR-PRIV-02 | Erasure job and purge not built; both tasks reserved | `IMPLEMENTATION-AGENT-PROMPT.md` §0j | Owner approves design, then build |
| BL-8 | FR-INT-01, NFR-AIQ-03 | Routing set has 10 items against a 95% target | `routing.jsonl` 10 lines | Grow to at least 100 labelled items |
| BL-9 | FR-RET-01, NFR-AIQ-06 | Bank has 8 items; no live baseline | `bank.jsonl` 8 lines | Owner expansion; run on live collection (B15) |
| BL-10 | NFR-A11Y-01, NFR-N-1 | WCAG 2.2 not tagged; manual pass absent | C-9 | Add tag; checklist |
| BL-11 | NFR-SEC-01 | Decision D-07 pending; no route-table test | `unresolved-questions.md` D-07 | Decide; add test |
| BL-12 | Several FRs (SRC-01, DEPTH-01, FUP-01, MV-01) | No test and no stratum in the golden set | §3.1 | Add strata from `18` §4.1 |

> **Update 2026-11-06 (batch 9, 43b6c6fd):** BL-1: task T1-18 landed; the test `src/test/chat/streaming-contract.test.ts` exists; the pending register row UX-005 is Closed. A cut-stream step in the A10 smoke test is still to add. BL-3: the seeker control now exists (`a33d6b8d`); it does not send a clip id.

Top 5 for the release: BL-1, BL-2, BL-3, BL-4, BL-7.

## 8. Testing methodology by component

Only frameworks already in the repository are used: pytest and pytest-asyncio (`backend/pyproject.toml:82`), `hypothesis` (declared at `:90`, unused), Locust (`backend/requirements-dev.txt:4`, no locustfile found in the paths read), vitest (`package.json:15`), Playwright with `@axe-core/playwright` (`package.json:110,114`), the homemade `gate1_load_test.py` with in-process chaos for Qdrant and Neo4j, GitHub Actions workflows. A new framework needs a written reason. None is proposed here.

Failure modes FM-1 to FM-13 are from `16` §5. F-nn are from `16` §7.

| Component | Test types that apply | Failure modes covered | What exists | Gap |
|---|---|---|---|---|
| Crisis and distress (`serene_mind_engine.py`, `distress_stage.py`) | Unit; golden set (benign, crisis, multi-turn); multilingual human review; regression | FM-1, FM-2, F-15 | `test_crisis_preemption.py`; `test_distress_provider_fail_closed.py`; PR-suite sets (5 and 8 items) | Multi-turn set; clinician and native review `[HUMAN]` |
| Routing (`off_topic_stage.py`, `pipeline_registry.py`) | Unit; golden routing set; regression | FM-3, F-11 | `routing.jsonl` (10) | 100+ items |
| Teaching serve path (`first_person_pipeline.py`) | Characterisation (golden); integration on fixture stores; failure injection; regression | FM-4, FM-5, FM-8, F-12 | `test_first_person_pipeline_golden.py` (17 scenarios); `test_fixture_stores.py`; `test_fp_fail_closed.py` | Property tests for hash and ID (`hypothesis`) |
| Retrieval (`first_person_store.py`, `first_person_context_store.py`) | Retrieval eval (Recall, MRR, nDCG with CI); integration; multi-video synthesis eval; regression | FM-5, FM-6, F-02, F-06 | `test_retrieval_bank_harness.py`; `test_v10_hybrid_retrieval.py`; `test_gate_first_then_dedup.py` | Live baseline; multi-video stratum (clips only, no generated bridge) |
| Answer composition and voice | Voice lint; quote integrity; golden; human rubric | FM-4, FM-11, F-04 | `evals/pr_suite/voice_lint.py`, `quote_integrity.py` | Layered tests only after D-03 |
| Data builders and promotion | Unit; integration; data audit; property (IDs, hashes) | FM-5, F-05, F-18 | `test_builder_replace_and_snapshot.py`; `test_writer_hash_contract.py`; `test_data_quality_promotion_gate.py` | Live audit `[LIVE-Q]` |
| Rights and takedown | Integration; security; human filing | FM-8, F-04 | `test_rights_register_startup.py` | Takedown tests (T3-06) |
| API (`chat.py`, `feedback.py`, `first_person.py`) | API contract; security (auth, quota); concurrency | FM-12 | `test_citation_contract.py`; `test_anon_quota.py` | Route-table auth test; 429 body test |
| Streaming (`stream_orchestrator.py`, `streaming.ts`) | Contract; e2e with a cut stream; fuzz of SSE framing | F-13 | `src/test/streaming.test.ts`; `src/test/streaming-crlf.test.ts` | Cut-stream test (FR-N-1) |
| Cache (`cache_stage.py`) | Integration on real Redis; regression | F-17 | `test_cache_personalization_leak.py`; `test_cache_tenant_isolation.py`; `test_cache_crisis_bypass.py` | None known |
| Memory and consent | Integration; security; erasure drill | F-08, F-09, F-16 | consent and delete-all tests (§3.1) | RLS role test; durable erasure |
| Supabase RLS and migrations | Security e2e; migration lint | F-09, FM-13 | `tests/e2e/rls-cross-user.spec.ts`; `test_migration_lint.py` | Role-insert test |
| Frontend chat UI | Unit (vitest); e2e (Playwright); accessibility (axe); multilingual | FM-9, FM-10, F-13 | `src/test/*`; `tests/e2e/*.spec.ts` | Error-state e2e; WCAG 2.2 tag; clip report e2e |
| Performance and reliability | Load; failure injection; chaos only for Qdrant, Redis, provider (justified: these three outages have documented seeker impact, F-19, F-20) | FM-7, F-14, F-19, F-20 | `gate1_load_test.py` | Redis mode; real-LLM run on staging |
| Observability | Unit on record shape; alert drill | NFR-OBS-*, FM-4 | `test_answer_outcome_telemetry.py` | Integrity-breach alert |
| Deployment and config | Config lint; startup tests; staging smoke | FM-8, FM-12, F-21 | `test_config_lint.py`; `test_rights_register_startup.py`; `test_main_cors.py` | Staging smoke (A10) |

Chaos testing beyond these three outages is not justified before staging exists (N-01, N-02 in `19`).

## 9. Cross-references

- Findings and tasks: `findings-index.md`, `20`. Status by finding: `FINAL_PENDING_WORK_REGISTER.md`.
- ADRs: `ARCHITECTURE_DECISION_RECORDS_HISTORICAL.md` and `17` §5.
- Memory and personalisation requirements: `PERSONAL_MENTOR_MEMORY_AND_PERSONALIZATION_SPEC.md`.
