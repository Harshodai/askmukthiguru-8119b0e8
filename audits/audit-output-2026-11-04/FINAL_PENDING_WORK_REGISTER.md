# Final pending-work register (2026-11-05)

Owner: documentation agent for the final verification. Branch `feature/audit-strengthen-rag-qdrant`, head `c9b42d3e`. Base of the remediation range: `c7befa3d` (73 commits). Source of findings: `findings-index.md` (152 defect findings plus 1 strength, MEM-006). Conventions: `CONVENTIONS.md`.

This register does not change any severity. It does not claim that CI is green: the CI result on the branch head was not observed while this register was written. Separately, the lead observed on 2026-11-05 that every workflow on `c9b42d3e` failed (GitHub Actions run list, [V-GIT]).


> **Verification note 2026-11-06 (head `fb5cab0f`).** The row statuses in section 2 are now as of `fb5cab0f`. Where a status changed, the row keeps the old status (for example "Open at c9b42d3e -> Partial at 2edee1c4"). I read the diff and the code at head for the 21 commits `2edee1c4` to `a7be7e65` (batches 9 to 13). I did not run any test and I did not observe CI. Result: 2 findings closed (UX-005, ADV-06), 15 moved to Partial, 4 not changed (SYS-003, AI-005, CQ-002, SEC-006 kept Partial with new evidence). SYS-003 is untouched: 2318a368 names it but changes only naming and gateway methods. Four claims in commit messages are larger than the diff (MEM-002, GURU-010, CQ-009, PRD-006); each row says why. The batch tables in `IMPLEMENTATION-AGENT-PROMPT.md` (0p to 0t) are claims, not evidence. Counts before and after are in section 1.

## Status vocabulary

| Status | Meaning |
|---|---|
| Closed | A commit SHA and the code or test that proves it were read for this register. |
| Partial | Part of the finding is closed. The "Remaining work" column says what is left. |
| Open | No commit addresses it. An agent can do it, or it is reserved. |
| Needs owner decision | Blocked by a D-** question in `unresolved-questions.md`. |
| Needs human | A clinician, rights holder, native speaker, gold labeller or guru reviewer must act. |
| Needs live infrastructure | Needs Qdrant, Railway or Supabase. |

No finding is marked "Claimed closed, unverified" or "Superseded" (statuses at `c9b42d3e`). Every closure that `IMPLEMENTATION-AGENT-PROMPT.md` §0g claimed was read. Five of the 38 claimed closures are downgraded to Partial (see section 8).

## 1. Summary counts (severity x status)

Each cell shows `after (before)`. "After" is at head `fb5cab0f` (verified 2026-11-06). "Before" is at `c9b42d3e`.

| Severity | Index count | Closed | Partial | Open | Needs owner decision | Needs human | Needs live infrastructure | Total here |
|---|---|---|---|---|---|---|---|---|
| P0 | 2 | 0 (0) | 0 (0) | 0 (0) | 2 (2) | 0 (0) | 0 (0) | 2 |
| P1 | 47 | 11 (11) | 12 (10) | 5 (6) | 8 (8) | 10 (11) | 1 (1) | 47 |
| P2 | 81 | 15 (14) | 22 (12) | 8 (19) | 28 (28) | 7 (7) | 1 (1) | 81 |
| P3 | 22 | 9 (8) | 3 (0) | 2 (5) | 7 (8) | 1 (1) | 0 (0) | 22 |
| All defects | 152 | 35 (33) | 37 (22) | 15 (30) | 45 (46) | 18 (19) | 2 (2) | 152 |

Status changes since `c9b42d3e`: Open -> Closed: UX-005, ADV-06. Open -> Partial: PRD-006 (P1); MEM-002, MEM-004, PRD-010, CQ-003, CQ-006, CQ-007, CQ-009, GURU-010, GURU-013, DATA-13 (P2); UX-009, UX-011 (P3). Needs human -> Partial: SAFE-004 (P1). Needs owner decision -> Partial: CQ-014 (P3). Partial -> Partial with new evidence: SEC-006.

Index counts: P0 2, P1 47, P2 81, P3 22, strength 1, total 153 (the "Counts" table of `findings-index.md`). The section headings of that file still say P1 45, P2 77, P3 19. The table is authoritative. The headings are stale (see section 8).

Compared with `IMPLEMENTATION-AGENT-PROMPT.md` §0g (38 closed, 7 partial, 107 open) at `c9b42d3e`: this register found 33 closed and 22 partial. At head it finds 35 closed and 37 partial. 117 findings are not closed. Both P0 findings are not closed. A Partial row is not a closure: the "Remaining work" column says what is left.

Closed per severity at head: P1 11 of 47, P2 15 of 81, P3 9 of 22, P0 0 of 2.

## 2. Full register (P0 to P3; the strength MEM-006 is excluded)

Columns: ID, title, severity, status, evidence (commit SHA and code or test read), remaining work, who can close it, roadmap task, blocking decision. "Any agent" means no owner decision, clinician, native speaker or live system is needed. "Reserved" means `IMPLEMENTATION-AGENT-PROMPT.md` §0j keeps the task for a supervised stronger model. Test ids use `file::test_name`; I did not run any test.

| ID | Title | Sev | Status | Evidence | Remaining work | Who can close | Task | Blocking decision |
|---|---|---|---|---|---|---|---|---|
| X-06 | Public repository holds teaching content and operational data | P0 | Needs owner decision | No commit. `T0-02` guard not extended. | Make repo private or decide purge; then remove tracked content and extend publication guard. | Owner | T0-01, T0-02 | D-01, D-02 |
| IP-001 | Verbatim text of 2,737 served spans published in the public repo (reviewer counted 2,737 non-empty `verbatim_text`) | P0 | Needs owner decision | No commit. | Same as X-06. Verbatim spans still tracked. | Owner | T0-01, T0-02 | D-01, D-02 |
| X-01 | Release-gate claim not reproducible on a clean checkout; `main` red | P1 | Partial | 79ae227a, ec890c18: `backend/tests/test_first_person_public_release_gate.py::test_the_repository_gate_reports_owner_action_required` asserts the computed status. | CI result on branch head not observed by this register. `main` green is not shown. | Any agent (confirm CI); Owner (merge) | T0-04, T1-11 | - |
| GURU-001 | "24/24 PASS" not reproducible (gold sheets gitignored) | P1 | Partial | Same as X-01 (79ae227a, ec890c18). | Gold sheets remain gitignored. Gate now says OWNER_ACTION_REQUIRED, so the false "24/24 PASS" claim is no longer asserted by the test. | Owner / Human specialist | T0-04, T1-11 | D-09 |
| GURU-002 | Non-independent "consensus" labels accepted as human gold | P1 | Partial | ec890c18: gate rejects non-independent gold (`test_t1_11_non_independent_gold_review_fails`, `..._single_annotator_fails`, `..._perfect_agreement_without_adjudication_fails`). | Independent labels (>=299, two people) do not exist. Human work. | Human specialist | T1-11, T10-02 | D-09 |
| EVAL-001 | Release gate accepts unverifiable, non-independent gold | P1 | Closed | ec890c18: `scripts/ops/check_first_person_public_release.py` (identical copy under `backend/scripts/ops/`, cmp verified) and the three `test_t1_11_*` gold tests. | None for the gate logic. Gate input data is still missing (see GURU-002). | - | T1-11 | - |
| X-02 | `main` unprotected; merges precede CI; PR-less pushes | P1 | Needs owner decision | No commit. | Turn on branch protection and required checks on GitHub. | Owner | T0-03 | T0-03 (no D-** number) |
| GURU-003 | "Staging readiness" is a local test summary; invalid commit id | P1 | Closed | ec890c18: `_is_ancestor` (`git merge-base --is-ancestor`) and the local-environment check in `_check_staging_readiness`; tests `test_t1_11_staging_commit_must_be_a_real_ancestor`, `..._staging_environment_must_not_be_local`. | A real staging readiness record still does not exist (needs T9-01). | - | T1-11 | - |
| GURU-004 | Machine scopes authorise public release; notes say NO-GO | P1 | Partial | ec890c18: `_check_authorization_scopes` and `test_t1_11_public_scopes_contradicting_a_no_go_note_fail`. | Gate flags the conflict. Owner must correct the scopes in the config (D-11). | Owner | T0-04 | D-11 |
| GURU-005 | Clinician and content-owner sign-offs exist only as strings | P1 | Needs human | ec890c18 adds no evidence; sign-offs remain strings. | Clinician and content-owner written messages filed by hash. | Human specialist / Owner | T3-09, T1-11, HUMAN | D-10 |
| GURU-006 | AI subagent listed as a human audio certifier | P1 | Closed | ec890c18: `test_t1_11_agent_certifier_ids_are_rejected`. | A human audio certifier still has to certify. | - | T1-11 | - |
| GURU-007 | Helpline call verification not in the gate (1/15 verified) | P1 | Partial | ec890c18: `test_t1_11_uncalled_helplines_fail` (365-day age check). | Phone calls to helplines are human work (1/15 verified). | Human specialist | T1-11, T4-07 | T4-07 calls |
| SAFE-005 | Clinician approval evidence is an in-repo string | P1 | Needs human | Same as GURU-005. | Clinician approval artefact filed by hash. | Human specialist | T3-09, HUMAN | D-10 |
| GURU-012 | Teacher-attributed text without a verifiable locator (titles only, or paraphrase in prompts) | P1 | Partial -> Partial at ad53d52 | 4a6ba426: `backend/tests/test_no_unsourced_teacher_attribution.py::test_fallback_tips_are_unattributed_paraphrases`, `::test_no_says_teaches_literals`; `backend/app/api/teachings.py` `DEFAULT_TEACHER` remains for admin-curated tips. ad53d52: `_has_locator`/`_credited` in `backend/app/api/teachings.py`; admin-curated, harvested and cached tips credit a teacher only with a span/point id or a YouTube id plus `start_ms`; `backend/tests/test_teaching_tip_locator.py` (22 cases, red before). | Book and series titles still lack locators. Admin tips stored before ad53d52 keep their teacher field in Redis, but the served payload strips it (`_credited`). | Any agent | T1-03 | - |
| IP-002 | Teacher voice audio from YouTube published with no rights row | P1 | Needs human | No commit. | A human must confirm the voice in the MP3 and file a rights row, or remove the file (T0-02). | Owner / Human specialist | T0-02, HUMAN | D-12, D-01 |
| IP-003 | Rights basis rests on owner statements; no written approval filed | P1 | Needs human | No commit. | Written approval from the rights holder. | Human specialist (rights holder) | T3-09, HUMAN | D-10 |
| IP-004 | yt-dlp acquisition conflicts with YouTube terms unless permitted | P1 | Needs owner decision | No commit. | Decide yt-dlp acquisition policy and the private source bundle (ADR-008). | Owner | T0-05, T3-09 | D-08 |
| ANS-001 | "What is the cause of my anxiety?" gets a distress template, no teaching | P1 | Needs human | No commit. T4-04 is reserved (`IMPLEMENTATION-AGENT-PROMPT.md` §0j). `evals/pr_suite/distress_benign.jsonl` and `distress_crisis.jsonl` exist (32e73280) but are AI-authored. | Clinician-reviewed core, benign (>=200) and multi-turn (>=50) sets; then T4-04 behind a flag. | Reserved (stronger model, supervised) + Human specialist | T4-04 | D-06, D-22 |
| ANS-002 | MILD words always upgraded to MODERATE in chat | P1 | Needs human | No commit. T4-04 is reserved (`IMPLEMENTATION-AGENT-PROMPT.md` §0j). `evals/pr_suite/distress_benign.jsonl` and `distress_crisis.jsonl` exist (32e73280) but are AI-authored. | Clinician-reviewed core, benign (>=200) and multi-turn (>=50) sets; then T4-04 behind a flag. | Reserved (stronger model, supervised) + Human specialist | T4-04 | D-06, D-22 |
| SAFE-002 | Topic repetition escalates to SEVERE crisis pre-emption | P1 | Needs human | No commit. T4-04 is reserved (`IMPLEMENTATION-AGENT-PROMPT.md` §0j). `evals/pr_suite/distress_benign.jsonl` and `distress_crisis.jsonl` exist (32e73280) but are AI-authored. | Clinician-reviewed core, benign (>=200) and multi-turn (>=50) sets; then T4-04 behind a flag. | Reserved (stronger model, supervised) + Human specialist | T4-04 | D-06, D-22 |
| SAFE-003 | Benign-question overfire accepted, not measured on a reviewed set | P1 | Needs human | No commit. T4-04 is reserved (`IMPLEMENTATION-AGENT-PROMPT.md` §0j). `evals/pr_suite/distress_benign.jsonl` and `distress_crisis.jsonl` exist (32e73280) but are AI-authored. | Clinician-reviewed core, benign (>=200) and multi-turn (>=50) sets; then T4-04 behind a flag. | Reserved (stronger model, supervised) + Human specialist | T4-04, T2-01 | D-06, D-22 |
| SAFE-001 | Crisis detection = unreviewed regex; semantic stages off | P1 | Needs human | No commit. T4-04 is reserved (`IMPLEMENTATION-AGENT-PROMPT.md` §0j). `evals/pr_suite/distress_benign.jsonl` and `distress_crisis.jsonl` exist (32e73280) but are AI-authored. | Clinician-reviewed core, benign (>=200) and multi-turn (>=50) sets; then T4-04 behind a flag. | Reserved (stronger model, supervised) + Human specialist | T4-04, T10-02 | D-06, D-22 |
| SAFE-004 | Helplines mostly not call-verified; shown on MODERATE | P1 | Partial (Needs human at c9b42d3e -> Partial at 5db34855) -> Needs human at d35ab6d (code part closed) | 5db34855: `backend/services/crisis_helplines.py` (`_is_call_verified_and_fresh`, `_only_call_verified`, 180-day window from `settings.helpline_max_verified_age_days`, `backend/app/config.py`); `format_helplines_block(verified_only=True)` used only at `backend/rag/meditation.py:131`; `format_support_line` default `verified_only=True` (`crisis_helplines.py:350`); `backend/tests/test_verified_helplines_only.py`. `format_helplines_block` defaults to `verified_only=False` (`crisis_helplines.py:290`). These call sites still show unfiltered lines: `serene_mind_engine.py:952`, `rag/nodes/intent.py:1624`, `rag/prompts/system.py:302`, `first_person_pipeline.py:3626`, `first_person_local_review.py:1560`, `kill_switch_stage.py:75`, `guardrails/lightweight_handler.py:479`. d35ab6d: `verified_only=True` at `serene_mind_engine.get_crisis_resource`, `kill_switch_stage`, the first-person crisis block, `first_person_local_review`, `guardrails/lightweight_handler`, `rag/prompts/system.build_distress_prompt`; `_only_call_verified` falls back to Tele-MANAS plus 112 unless a call-verified non-112 line remains; `backend/tests/test_helplines_verified_everywhere.py`. | Helpline calls by the owner (1 of 15 call-verified; Tele-MANAS 2026-09-26 leaves the 180-day window about 2027-03-25). | Any agent (call sites) + Human specialist / Owner (calls) | T4-07, HUMAN | T4-07 calls |
| RET-09 | Generating path stays enabled as the fail-open target | P1 | Closed | 0d32fbcd: `backend/services/fp_fail_closed.py::teaching_generation_allowed`; guard in `backend/rag/nodes/generation.py` (~2669); tests `backend/tests/test_fp_fail_closed.py::test_bridge_off_returns_static_abstain_without_llm`, `::test_generate_answer_guard_abstains_for_teaching_intent`. | Rollback flag `FP_FAIL_CLOSED_ENABLED` exists. T7-06 retires the generating path (D-04). | - | T1-05 | - |
| ADV-03 | Turning the first-person bridge off sends teaching questions to the generating "warm Guru" prompt | P1 | Closed | 0d32fbcd: `test_fp_fail_closed.py::test_bridge_off_returns_static_abstain_without_llm`, `::test_registry_keeps_module_routable_when_bridge_off`. | None for the bridge-off trigger. | - | T1-05 | - |
| ANS-004 | Live path cannot compose a complete answer (one clip only) | P1 | Needs owner decision | No commit. | Layered composer (ADR-001), flagged. | Any agent after decision | T5-03, ADR-001 | D-03 |
| RET-03 | No multi-video composition of evidence | P1 | Needs owner decision | No commit. | Evidence-set selection across videos (T5-02). | Any agent after decision | T5-02 | D-03 |
| ANS-005 | Root `CLAUDE.md` mandates teacher "I" voice; code forbids it | P1 | Closed | 69d8faaa: root `CLAUDE.md` section "Voice Governance & Invariants" (line 121); `backend/tests/test_voice_governance_docs.py::test_no_teacher_first_person_directives`, `::test_voice_governance_rule_present`. | Owner sign-off on the CLAUDE.md rewrite is requested in prompt §0d. | Owner (sign-off) | T1-01 | - |
| DATA-01 | Serving corpus cannot be rebuilt from repo + infrastructure | P1 | Needs owner decision | No commit. | Private evidence store and source bundle; reproducible rebuild. | Owner + Any agent | T3-09 | D-08 |
| DATA-02 | Rights register not in Railway image → every clip abstains | P1 | Closed | e0f42e1c: `backend/Dockerfile`, `backend/Dockerfile.railway`; `backend/tests/test_rights_register_startup.py::test_missing_register_fails_production`, `::test_serving_images_copy_the_register`. | Docker build not run. Register holds `/Users/...` paths; scrub needs re-pin of three digests (owner). | Owner (scrub); Live infrastructure (image build) | T3-01 | - |
| DATA-05 | v10 builder is add-only; snapshot after writes | P1 | Closed | 741fe70a: `backend/scripts/ops/build_full_corpus_v10.py` (`--replace-existing`, snapshot before first write ~line 957); `backend/tests/test_builder_replace_and_snapshot.py::test_builder_takes_snapshot_before_first_write`, `::test_builder_per_video_replace_deletes_stale_points`, `::test_builder_refuses_empty_build`. | Running a real rebuild needs the owner. | - | T3-04 | - |
| DATA-06 | Uncontrolled concurrent writers to Qdrant (no API key) | P1 | Partial (2026-11-06: `qdrant_write_api_key` has no Python reader; only compose sets the server key, so no write path uses a separate key yet) | 13c818da: `backend/tests/test_qdrant_write_governance.py` (7 tests); read/write key split in `backend/app/config.py` and `backend/docker-compose.yml`. | Keys must be set on the live Qdrant and Railway. Other writers unknown. | Owner / Live infrastructure | T3-02, T1-14 | D-15 |
| DATA-07 | No cross-store takedown of teaching content | P1 | Open | No commit. T3-06 is reserved. | Source registry, `takedown()`, migration review. | Reserved (stronger model, supervised) | T3-06 | - |
| DATA-14 | v10 fails its own data-quality scorecard (13/26) | P1 | Partial | 492e7d33: `evaluate_promotion_gate` in `fp_data_quality_scorecard.py`; `backend/tests/test_data_quality_promotion_gate.py`. | Gate blocks promotion. The v10 data still scores 13/26 [DOC-CLAIM]; fixing the data needs builder runs. | Owner / Live infrastructure | T3-05 | D-14 |
| MEM-003 | Emotional history read and acted on without the consent gate | P1 | Closed | 1e8bf812: `backend/app/orchestrator_utils.py::has_active_memory_consent` (gate before `_build_emotional_arc_turns`, ~line 600); `backend/app/pipeline/stages/distress_stage.py` (~654); `backend/tests/test_emotional_side_effect_consent.py::test_no_consent_no_read_and_no_write`, `::test_consent_lookup_error_fails_closed`, `::test_proactive_serene_mind_needs_consent`. | Default on/off of the features unchanged (D-21). | - | T1-10 | D-21 (default only) |
| UX-001 | Account deletion runs through a churn funnel with win-back emails; it is the only UI deletion path | P1 | Needs owner decision | No commit. | Replace churn funnel with direct delete flow (T1-12). Needs native review of copy. | Any agent after decision | T1-12 | D-19 |
| ADV-01 | Scheduled deletions never execute (no purge job); deletion needs the backend up | P1 | Open | No commit. T6-06 is reserved. | Durable erasure and scheduled purge job; dry-run default. | Reserved (stronger model, supervised) | T6-06, T1-12 | Owner approves purge rule |
| SYS-003 | Sync FP pipeline blocks thread-pool workers on LLM calls | P1 | Open -> Partial at a7359225 (T7-02: v10 harness lane async, proven at the bridge stage in tests; legacy tail still sync on the fp-io pool; live Docker and staging c20 UNPROVEN) -> Partial at dcfb3a5 (review fix; unchanged otherwise) | No closing commit at c9b42d3e. T7-02 is reserved. 2318a368 names SYS-003 but does not touch it. The diff has no change to `first_person_pipeline.py` for this purpose, no async lane, and no thread-pool change. The sync pipeline still runs through `asyncio.to_thread` (`first_person_bridge.py`) and `run_llm_coroutine`. Status unchanged: Open at c9b42d3e and Open at head. SHA correction 2026-11-06: `a7359225`/`0176739e` were pre-rebase SHAs and are not on the branch. Pushed T7-02 commits: a54373b (T7-02a goldens), c89e1b9 (T7-02b lane), baba3da (T7-02c Celery), d177cd2 (T7-02d), 503212f (T7-02e). Review fix dcfb3a5: an outer cancel now cancels the in-flight LLM call and `execute()` has a bound (`test_first_person_bounded_cancel.py`, `test_first_person_execute_bound.py`). | Async teaching lane after staging load test. | Reserved (stronger model, supervised) + Live infrastructure | T7-02 | - |
| SYS-004 | OpenRouter spend cap off by default (the code comment says "Default enabled") | P1 | Closed | 1974dcb1: `backend/app/config.py` lines 643-648 (guard on, fail-closed on), production validator ~2494; `backend/tests/test_config_validation.py::test_uncapped_spend_refused_in_production_unless_recorded`. | Scorer price/timeout remain D-16 (see AI-007). | - | T1-07 | - |
| SYS-006 | FP p95 12–14 s from 3 sequential LLM gates; scorer timeout 12/15/25 s across sources | P1 | Open -> Partial at 3e2882f | T4-06 not started. T7-01 precondition is done (0c643bc2). 3e2882f: `services/first_person_judge.py` (one structured call: relevance, answers, question_answerable), read at the top of `_relevance_select_async`; active only with `first_person_judge_enabled` and a non-empty `first_person_judge_model` (both default off/empty); `backend/tests/test_first_person_judge.py`. 36dc746: rerank call sends `max_tokens=24` (`test_rerank_max_tokens.py`). | Choose the judge model (D-16); run the frozen-bank comparison before the L3 rerank and L2 gate are removed; scorer timeout decision (D-PG13). | Any agent (T4-06 judge); Owner (timeout) | T4-06, T1-07 | D-16 (timeout) |
| SYS-007 | No reproducible deployed environment, no staging | P1 | Needs live infrastructure | No commit. | Railway IaC and staging (T9-01). | Owner + Live infrastructure | T9-01 | D-26 |
| SYS-011 | No signal separates "HTTP 200 but poor" from useful | P1 | Partial | 03237677, 2c80d884, eba53ac5: `backend/app/answer_outcome.py`, `backend/tests/test_answer_outcome_telemetry.py`; `compute_useful_answer`, `/feedback/engagement` (eba53ac5). | Supabase sink write (needs migration) and a value-metrics dashboard are open. | Any agent (code); Owner (migration) | T2-03 | - |
| SYS-012 | RPO unbounded for every store; backup workflow failing | P1 | Needs owner decision | No commit. | Off-host backups and restore drills (T3-10). | Owner + Live infrastructure | T3-10 | D-08 |
| SEC-001 | `/api/first-person/query` unauthenticated, no quota, spends LLM budget | P1 | Needs owner decision -> Closed | T1-08: Auth token or anon session required on `/api/first-person/query` (`backend/app/api/first_person.py`), anon turn quota enforced via `container.anon_quota_service` (429 Retry-After), daily user cost limit enforced via `get_cost_tracker().is_user_over_budget`; covered by 8 tests in `backend/tests/test_first_person_route_quota.py`. | None. | - | T1-08 | D-07 |
| EVAL-002 | No held-out human-labelled set; gold questions AI-written | P1 | Needs human | No commit. `evals/pr_suite/` (32e73280) is AI-authored. | Independent human-labelled held-out set. | Human specialist | T2-04, HUMAN | D-09, D-23 |
| EVAL-003 | CI quality gates inert without a deployment | P1 | Partial | 32e73280: `evals/pr_suite/`, `backend/tests/test_offline_pr_suite.py`, wired into `.github/workflows/eval-gate.yml`. | Offline suite runs without secrets. Live-stack gates are still inert without a deployment. CI result not observed here. | Any agent / Live infrastructure | T2-01 | - |
| PRD-006 | Seekers cannot report a wrong or misattributed clip | P1 | Partial (Open at c9b42d3e -> Partial at a33d6b8d) | a33d6b8d: `src/components/chat/CitationCard.tsx` ("Report clip issue" control, 4 categories); `reason_category` added to the existing clip-report request in `backend/app/api/feedback.py` (the route pre-dates this commit); route `POST /clip-report` now at `feedback.py:386`; `backend/tests/test_clip_reporting_and_saved_answers.py`. Gap read at head: the wire `Citation` schema has no point id or `source_span_id` (`backend/app/schemas/__init__.py`, `backend/tests/test_citation_contract.py` still asserts `point_id` is absent). The control falls back to the YouTube video id (`CitationCard.tsx:221`), which `_POINT_ID_RE` (`feedback.py:269`) accepts. A report therefore names a video, not a clip. | Put a clip id on the wire (PROPOSED D-PQ7), change `test_citation_contract.py` with it, then make the control send that id. Admin queue and E2E test. | Owner (D-PQ7), then Reserved (stronger model, supervised) for T3-06 citations, then agent | T6-04, T3-06 | D-PQ7 (proposed) |
| UX-006 | Signed-in history is tied to one browser, capped at 10, wiped on sign-out or expiry; the cloud copy is never read back | P1 | Open | No commit. | Account-level history (T6-09, needs T6-05). | Reserved (stronger model, supervised) first (T6-05), then agent | T6-09 | - |
| UX-007 | No support line or client crisis fallback on any error except 503; developer text can reach seekers | P1 | Closed | a07ef4b3: `src/lib/chat/errors.ts::buildMessageError` strips `detail`; care line in `src/components/chat/ChatMessage.tsx` (~1293); tests `src/test/chatErrors.test.ts` ("seeker-safe chat errors (T1-17)"), `src/test/crisisHelplines.test.tsx` ("CALL_VERIFIED_CRISIS_LINES"). | Care line uses a `t()` default with no locale key (T1-20). English only. Only call-verified lines are shown (Tele-MANAS). | - | T1-17 | - |
| ANS-003 | Questions mixing a general-task word with an emotion word reach the general lane | P2 | Needs owner decision | No commit. | Single route-decision service (T4-03). | Any agent after decision | T4-03 | D-04 |
| SYS-002 | Lane choice depends on keyword rules for the general-lane exit | P2 | Needs owner decision | No commit. | Same as ANS-003. | Any agent after decision | T4-03, T0-05 | D-04 |
| AI-001 | Domain scope defined three times and disagrees | P2 | Needs owner decision | No commit. | Same as ANS-003. | Any agent after decision | T4-03 | D-04 |
| SYS-001 | Node-level fall-through to generation on narrow failures (missing context, import error, error while abstaining) | P2 | Partial -> Closed in code at 60e8407 | 0d32fbcd: `test_fp_fail_closed.py::test_node_exception_abstains_and_counts`. 60e8407: classifier failure and a node call with no pipeline context fail closed (`backend/tests/test_fp_fail_closed_remainder.py`); f93f9fb narrows two handlers and pins the registry test in both flag states (`test_pipeline_registry.py`). | None in code. Live Docker run UNPROVEN. | Any agent | T1-05 | - |
| RET-01 | Per-video dedup before integrity gates (v8 path; back-fill from 40 videos limits the effect) | P2 | Closed | 59a9ae94: `backend/tests/test_gate_first_then_dedup.py::test_pipeline_serves_valid_lower_span_when_top_span_fails_gate`, `::test_pipeline_with_store_gates_before_dedup`; `deduplicate` flag in `FirstPersonStore.search_hybrid`; pipeline calls with `deduplicate=False`. | Effect not measured on the frozen bank. | - | T4-01 | - |
| RET-02 | v10 retrieval ignores the sparse vector (breaks invariant 5; v10 is not the code default) | P2 | Closed | 4ec9eaed: `backend/services/first_person_context_store.py` (`passage_sparse` prefetch, `Fusion.RRF`, ~551-559 and ~625-633); `backend/tests/test_v10_hybrid_retrieval.py`. | Effect not measured on the frozen bank. Live Qdrant not tested. | - | T4-02 | - |
| DATA-03 | `transcript_hash` has three meanings across writers (both gates fail closed today) | P2 | Closed | 7f8e463d: `backend/domain/hash_fields.py`; `backend/tests/test_writer_hash_contract.py`. | A rebuilt collection with the vNext schema needs a builder run (owner). | Owner | T3-03 | - |
| UX-005 | An interrupted stream leaves teacher text without citation, "Related" label or safety notices, and saves it to history (`final` is sent before `done`) | P2 | Closed (Open at c9b42d3e -> Closed at 43b6c6fd) | 43b6c6fd: `backend/app/stream_orchestrator.py:415-427` emits `done` before `final`; `backend/app/orchestrator.py` queued path publishes `done` then `final`; `src/lib/chat/streaming.ts:428-431` throws `stream_interrupted` on a done-less end; `streaming.ts` 30 s read timeout (`readWithTimeout`); `src/components/chat/ChatInterface.tsx:1712-1730` no longer recovers partial text on a done-less error; `src/test/chat/streaming-contract.test.ts` (3 tests). I read the code and the test names. I did not run them. Caveat: tokens still show on screen before `done` arrives. The client drops them if the stream ends without `done`. | None. | None (closed) | T1-18 | - |
| UX-008 | Trust labels, abstain card, error and quota copy are English in all 13 non-English locales (33 of 234 chat keys missing) | P2 | Needs human | No commit. | Localise strings (T1-20). Native review before release. | Any agent (keys) + Human specialist | T1-20, HUMAN | D-22 |
| PRD-009 | Client conversation summary is produced by sending "Summarize our conversation so far." to `/api/chat`; the clip or abstain reply is stored and reused as context | P2 | Closed | 3d81a932, 27606c82: `src/test/chat/noClientSummary.test.ts`; `transport.ts` summary call removed. | Local last-5-messages fallback is still stored in `conv.summary`. | - | T1-19 | - |
| PRD-010 | Landing and welcome copy promise a conversational "AI companion"; the teaching lane answers with a clip or a static abstain | P2 | Partial (Open at c9b42d3e -> Partial at 2a91817f) | 2a91817f: `src/components/chat/ChatHelpers.tsx:65` welcome text lists three outcomes (clip, honest abstain, crisis lines). Landing and meta copy still says "AI companion": `src/locales/en.json:244,1137`, `src/pages/Index.tsx:31,43`. | Change the landing and meta copy. Owner review before release. Native translations (T1-20). | Any agent + Owner | T6-10 | - |
| ADV-02 | Undocumented third-party processors: Lovable AI gateway (memory extraction, STT fallback, admin ask, eval), Sarvam STT, Sentry replays, SMTP, web push | P2 | Needs owner decision | No commit. | Processor inventory is agent work. Agreements are not. | Any agent (inventory); Owner | T6-08 | T6-08 owner input |
| ADV-04 | Admin `eval-run` scores Gemini answers judged by the same model, not the product | P2 | Open | No commit. `supabase/functions/eval-run` still exists. | Retire or relabel the edge function. | Any agent | T2-01 | - |
| ADV-05 | On-demand client translation of teacher quotes carries no machine-translation label | P2 | Closed | 0fc474dd: `src/components/chat/ChatMessage.tsx`; `src/test/LanguageTranslateButton.test.tsx`. | Label has an i18n default only, no `en.json` key; 13 locales need native review (T1-20). | - | T5-06 | - |
| X-03 | PR size makes review impossible | P2 | Needs owner decision | No commit. | PR-size warning and branch protection (T0-03). | Owner | T0-03 | T0-03 |
| X-05 | Two frontend writers; `lovable-sync` diverged | P2 | Needs owner decision | No commit. | Resolve `lovable-sync`. | Owner | T0-07 | D-24 |
| X-07 | Documents used as system memory; loose root files | P2 | Open | No commit. | Documentation diet (T1-15). | Any agent | T1-15 | - |
| AI-002 | Distress turns pay for retrieval + grading, then discard | P2 | Closed | c9b42d3e: `backend/rag/graph_strategies.py` routes DISTRESS to `"distress"`; `backend/tests/test_graph_strategy_wiring.py`, `test_graph_strategies.py`. | Standard strategy only was read. Fast and Deep not checked. | - | T4-05 | - |
| AI-003 | Teacher-style register block appended to general-mode prompts ("how, not what"; forbids invented first-person sentences) | P2 | Closed | 42da2db2: `backend/rag/nodes/generation.py`; `backend/tests/test_general_mode_no_register.py::test_no_teacher_register_in_general_mode`. | Register block in non-L3 prose not checked. | - | T1-06 | - |
| AI-004 | 37 prompt constants + 72 inline prompts; no registry/version | P2 | Partial | eba53ac5: per-call `prompt_id`, model, tokens, cost in `TokenAccumulator.record_call`. | No prompt registry or versions (T5-07). | Any agent | T2-03, T5-07 | - |
| AI-005 | Two provider stacks; `container.ollama` holds OpenRouter | P2 | Needs owner decision | No closing commit at c9b42d3e. 2318a368 renamed the container attribute and added gateway methods. It removed no provider stack. D-17 is still undecided. Status unchanged. | One LLM gateway (T7-03). | Any agent after decision | T7-03 | D-17 |
| AI-006 | Dormant editorial prompt rewrites teacher words (P0 if enabled) | P2 | Closed | 66e0ef3e: quote-weaver editorial/hybrid paths removed (`backend/services/quote_weaver.py`, -521 lines); no `quote_weaver_mode` editorial match remains. | `first_person_mode="hybrid"` still accepted as `retrieval_only` (prompt §0a). | - | T1-02 | - |
| AI-007 | Relevance-scorer model is an env-only dependency | P2 | Needs owner decision | No commit. | Make scorer model required; record price (T1-07 remainder). | Any agent after decision | T1-07 | D-16 |
| ANS-006 | No depth or mode control on the live path | P2 | Needs owner decision | No commit. | AnswerPlan (T5-01). | Any agent after decision | T5-01 | D-03 |
| ANS-007 | Follow-up continuity is string concatenation | P2 | Needs owner decision | No commit. | `answer_trace` (T5-05). | Any agent after decision | T5-05 | D-03 |
| ANS-008 | Indic seekers get English quote + translated glue | P2 | Needs human | No commit. | Language field and labelled translation after native review (T5-06). | Human specialist | T5-06, HUMAN | D-22 |
| MEM-001 | Seven overlapping memory planes (plus WhatsApp SQLite and edge extraction, ADV-06) | P2 | Needs owner decision | No commit. | Consolidate memory (T6-01); snapshot and owner OK. | Owner + Any agent | T6-01 | Owner approval of memory migration |
| MEM-002 | Memory read on the teaching lane and never used | P2 | Partial (Open at c9b42d3e -> Partial at 2edee1c4) (unchanged 2026-11-06, decision-gated) | 2edee1c4: `_apply_memory_reranking` at `backend/services/first_person_pipeline.py:2022`, called at `:5225`; `execute(memory_signals=...)` bypasses the exact cache (`:5694`); signal builder at `backend/app/pipeline/stages/first_person_bridge.py:850-876`; `backend/tests/test_fp_memory_signals.py`. Gap read at head: the builder reads `citations` from `ctx.state["original_chat_history"]` and tests `isinstance(msg, dict)`. That value is `chat_body.messages` (`backend/app/orchestrator_utils.py:635`), a list of `MessagePayload` models with only `role` and `content` (`backend/app/schemas/__init__.py:46-62`, `extra="forbid"`). So `seen_video_ids` stays empty on the live path. `stated_interests` is built and never used by the reranker. Opus thread 2026-11-06: not implemented. A server-side seen-clip source needs the learning_events table and D-PM4, or a `MessagePayload` change (frontend, Sonnet-owned). | Feed real seen-clip ids (a server-side source, not the chat history payload). Use or drop `stated_interests`. Add a test that goes through `ChatRequest`. | Any agent | T6-02 | - |
| MEM-004 | LLM-written "spiritual profile" of the user | P2 | Partial (Open at c9b42d3e -> Partial at 649ea2c3) -> Partial at 1c5f3f2 | 649ea2c3: `backend/services/layered_memory/l3_persona_generator.py` prompt now limits output to user-stated facts and bans inferred spiritual stages. An LLM still writes the persona (`generate_persona`, same file, merges with `existing_persona`). `compile_user_preferences` (`:27`) has no call site outside `backend/tests/test_l3_persona_preferences.py`. Old stored personas are not rewritten. 1c5f3f2: `generate_persona` no longer calls an LLM; it returns `render_user_preferences(compile_user_preferences(atoms))` or the existing persona (`backend/tests/test_l3_persona_preferences.py`). | Personas stored before 1c5f3f2 stay until new stated atoms replace them: owner decision whether to purge them. | Any agent | T6-03 | - |
| SAFE-007 | No emotional-dependency guard | P2 | Needs human | No commit. T6-07 reserved. | Clinician-written rule, then guard. | Reserved (stronger model, supervised) + Human specialist | T6-07, HUMAN | - |
| EVAL-004 | Benchmarks measure the dormant generating path | P2 | Partial | 32e73280: offline suite measures the serving lane. | Older benchmarks still target the dormant generating path. | Any agent | T2-01 | - |
| EVAL-005 | LLM judge not calibrated against humans | P2 | Needs human | No commit. | Judge calibration against human labels (T2-04). | Human specialist | T2-04 | D-09 |
| EVAL-006 | Pass bar accepts 70% abstention on answerable questions | P2 | Needs owner decision | No commit. | Add usefulness target; served-share floor. | Any agent after decision | T0-05, T2-01 | D-25 |
| DATA-04 | Ingestion dual-index writes fabricated provenance (P0 if enabled) | P2 | Closed | 66e0ef3e: ingestion FP dual-index writer removed (`backend/ingest/pipeline.py` -234 lines, `test_fp_dual_index_default_off.py` deleted); no `dual_index` match remains in `app/ services/ ingest/ rag/`. | None. | - | T1-02 | - |
| DATA-08 | Graph and LightRAG have no span-level provenance | P2 | Needs owner decision | No commit. | Freeze or retire graph stores (T3-11). | Any agent after decision | T3-11 | D-05 |
| DATA-09 | Two transcript lineages per video; online ingest downloads directly | P2 | Needs owner decision | No commit. | Canonical transcript per video (T3-09). | Owner + Any agent | T3-09 | D-08 |
| DATA-10 | Chat-corpus IDs use raw URL; scripts skip stale cleanup | P2 | Needs owner decision | No commit. | T3-11. | Any agent after decision | T3-11 | D-05 |
| DATA-11 | Supabase schema drift (32 tables created more than once) | P2 | Closed | 37032757: `supabase/schema_snapshot.sql`, `scripts/guards/migration_lint.py`, `.github/workflows/supabase-schema-snapshot.yml`; `backend/tests/test_migration_lint.py`. | Squash of the baseline needs the owner. L-07 (production RLS state) needs Supabase. | Owner / Live infrastructure | T3-08 | - |
| DATA-12 | Stored citations are unstructured `text[]` | P2 | Open | No commit. T3-06 reserved. | Structured citations. | Reserved (stronger model, supervised) | T3-06 | - |
| DATA-13 | Teacher-ID vocabulary differs per store | P2 | Partial (Open at c9b42d3e -> Partial at 4eb04ae8) | 4eb04ae8: same change as GURU-013. `scripts/ops/check_legacy_guru_tables.py` (identical copy in `backend/scripts/ops/`) scans for runtime use of `kb_chunks` and `gurus`. I did not run it. Stored vocabularies are not unified. | Live collection audit; unify stored values (dry-run, snapshot, ask, apply). | Live infrastructure + Any agent | T3-07 | - |
| DATA-15 | No continuous data-quality gate on serving collections | P2 | Partial (evidence added 087af0a) | 492e7d33: `data_quality_audit.py`, `.github/workflows/nightly-audit.yml` (runs the promotion-gate tests). 087af0a: `points_servable` can re-check `sha256(verbatim_text)` against the stored hash behind `first_person_points_servable_hash_check_enabled` (default False); `backend/tests/test_points_servable_hash_check.py`. | The audit of the live serving collection needs Qdrant access. | Live infrastructure | T3-05 | - |
| DATA-16 | Approved corpus version ≠ served version | P2 | Partial | 492e7d33: `approved_corpus_version` parsed in `backend/services/first_person_serving_contract.py` (~114, ~294). | `backend/config/first_person_serving_contract.json` sets no `approved_corpus_version`, so the check is inactive until the owner records it. | Owner | T3-05 | D-14 |
| DATA-18 | Runtime state lives in container files | P2 | Open | No commit. T3-06 reserved. | Move runtime state out of container files. | Reserved (stronger model, supervised) | T3-06 | - |
| RET-04 | Compound path does not retrieve per facet | P2 | Needs owner decision | No commit. | Per-facet retrieval (T5-02). | Any agent after decision | T5-02 | D-03 |
| RET-05 | Graph/LightRAG: unproven value, dirty data, no provenance | P2 | Needs owner decision | No commit. | Retire stores (T3-11, ADR-005). | Any agent after decision | T3-11, ADR-005 | D-05 |
| RET-06 | TU graph builder filters on a forbidden field; wrong default collection | P2 | Needs owner decision | No commit. | TU graph builder fix (T5-02). | Any agent after decision | T5-02 | D-03 |
| RET-07 | No serving-vs-index encoder check | P2 | Partial | 4b86ae8b: encoder check in `first_person_serving_contract.py`; `backend/tests/test_first_person_serving_contract.py::test_encoder_model_mismatch_is_error`, `::test_encoder_dimension_mismatch_is_error`. | The shipped contract records no encoder, so the check does nothing until the owner records it. | Owner | T3-12 | D-14 |
| RET-08 | No Recall@k/MRR/nDCG on the serving collection | P2 | Partial | 04fc2900: `evals/retrieval_bank/` and `backend/tests/test_retrieval_bank_harness.py`. | Bank is small. Labels are human work. No live runner. | Any agent (runner); Human specialist (labels) | T2-02 | - |
| RET-10 | Duplicate LLM ranking: up to 4 LLM calls per question | P2 | Open -> Partial at 3e2882f | No commit. 3e2882f: the judge replaces the L4 scorer call when active (default off). | L3 rerank and L2 answerability stay until the frozen-bank comparison shows the judge is not worse; D-16 model choice. | Any agent | T4-06 | D-16 |
| SYS-008 | Load evidence uses a mock LLM | P2 | Needs live infrastructure | No commit. | Real-model load test (T9-02). | Live infrastructure | T9-02 | D-26 |
| SEC-002 | Public video streaming by id | P2 | Needs owner decision -> Closed | T1-08: `stream_video_endpoint` in `backend/app/api/ingest.py` calls `resolve_source_rights_status("", video_id)`; returns 403 unless rights status is `"licensed"`; toggle `video_stream_rights_gate_enabled` in `backend/app/config.py`; tested in `backend/tests/test_first_person_route_quota.py`. | None. | - | T1-08 | D-07 |
| SEC-003 | Distress and question text logged at INFO | P2 | Partial | 4ec81cad: `backend/rag/intent_prerouter.py`, `backend/rag/resolve_followup.py`; `backend/tests/test_no_seeker_text_in_logs.py`. | `KNOWN_OFFENDER_BUDGET = 19` other possible log sites remain. Fix them and lower the budget. | Any agent | T1-09 | - |
| SEC-004 | Erasure gaps; deletion impossible while backend down | P2 | Open | No commit. T6-06 reserved. | Erasure completeness. | Reserved (stronger model, supervised) | T6-06 | - |
| SEC-005 | Public repo tracks corpus/graph backups and internal reports | P2 | Needs owner decision | No commit. | Remove tracked backups and reports (T0-02). | Any agent after decision | T0-02 | D-01, D-02 |
| SEC-006 | Datastores on 0.0.0.0; Qdrant no API key; unpinned image | P2 | Partial | 0ba6615c: `backend/docker-compose.yml` ports on 127.0.0.1; `backend/tests/test_docker_compose_healthcheck.py`. 13c818da: Qdrant key settings. 49c92325: `backend/docker-compose.yml:45,880` pins Memgraph `2.20.1` and Autoheal `1.2.0`; no `:latest` remains in that file. I did not check that the tags exist on the registry. No test was added. `backend/Dockerfile.railway:16,58` still uses the floating `python:3.12-slim`. `backend/CLAUDE.md` still says `memgraph-mage:latest`. | Pin `Dockerfile.railway` base image. Add a test that rejects `:latest`. Production keys are infrastructure. | Any agent (pins); Live infrastructure | T1-14 | D-15 |
| SEC-007 | Prompt injection: low on FP gates, real on general lane | P2 | Needs owner decision | a8bd93a5 fences clip and summary text only. | General-lane injection defence (T4-03, T5-04). | Any agent after decision | T4-03, T5-04 | D-04 |
| CQ-001 | Giant functions (execute 2,145 lines; generate_answer 1,247) | P2 | Partial | 31ebbd89..0c643bc2 (T7-01a-l): `FirstPersonPipeline.execute` in `backend/services/first_person_pipeline.py` is about 266 lines (269 by AST span, def line 5601); golden test `backend/tests/test_first_person_pipeline_golden.py`. | `generate_answer` (1,247 lines) untouched. The fp-context harness block is still one method. | Any agent | T7-01 | - |
| CQ-002 | ~14 overlapping LLM abstraction modules | P2 | Needs owner decision | No closing commit at c9b42d3e. 2318a368 added `generate_fast` and `stream` to `LLMGateway` (`backend/services/llm_gateway.py`) and the `container.llm` name. The ~14 overlapping modules remain. D-17 is still undecided. Status unchanged. | T7-03. | Any agent after decision | T7-03 | D-17 |
| CQ-003 | At least 8 cache mechanisms | P2 | Partial (Open at c9b42d3e -> Partial at a12ea273) | a12ea273: cache key now binds collection, `prompt_version`, `cache_key_version` (`backend/app/pipeline/pipeline_coordinator.py`, settings in `backend/app/config.py`); `backend/app/pipeline/stages/cache_stage.py` skips semantic and vector writes for teachings and discards semantic hits that carry teaching markers; `backend/tests/test_cache_versioning_and_teaching_guard.py`. No mechanism was removed. The count of cache mechanisms is unchanged. 7f63fe4c fixed a wrong setting name (`collection_name` -> `qdrant_collection`) in the new key code. | Consolidate the cache mechanisms (hit-rate data from T2-03 exists). | Any agent | T7-04 | - |
| CQ-004 | 5+ memory subsystems | P2 | Needs owner decision | No commit. | Same as MEM-001. | Owner + Any agent | T6-01 | Owner approval of memory migration |
| CQ-005 | Root `langdetect` stub always returns "en" | P2 | Closed | 42e883b3: root `langdetect/` removed (directory absent). | None. | - | T1-13 | - |
| CQ-006 | 1,513 `except Exception`; 70 silent swallows | P2 | Partial (Open at c9b42d3e -> Partial at 924419df) | 924419df: `scripts/guards/exception_ratchet.py`, `scripts/guards/exception_baseline.txt` (ceiling 729 broad excepts in `app/`, `rag/`, `services/first_person*`; 17 silent swallows allowed; 0 in first-person services), `backend/tests/test_exception_and_import_ratchets.py`. Those counts are a ceiling, not a reduction. The original 1,513 and 70 were repo-wide counts. I found no hook or workflow that calls the script. The pytest test runs it. | Lower the ceilings step by step. Cover the rest of `backend/`. Remove the 17 silent swallows. | Any agent | T7-05 | - |
| CQ-007 | 1,465 function-local imports hide cycles | P2 | Partial (Open at c9b42d3e -> Partial at 924419df) | 924419df: `scripts/guards/import_layer_lint.py` and `scripts/guards/import_layer_allowlist.txt` (25 grandfathered upward imports; limit 50) block new upward layer imports. The 1,465 function-local imports are not reduced. | Reduce the grandfathered list and the local imports. | Any agent | T7-05 | - |
| CQ-008 | 112 tests assert on source text; no real-store CI | P2 | Partial | 60076bc5: `.github/workflows/fixture-stores.yml`; `backend/tests/test_fixture_stores.py`. | Source-text tests are not yet replaced (112 tests). | Any agent | T2-05 | - |
| CQ-009 | 11.2 MB markdown; key docs drift from code | P2 | Partial (Open at c9b42d3e -> Partial at 2c81a2d1) | 2c81a2d1: root `CLAUDE.md` stage chain corrected; `scripts/guards/pipeline_order_guard.py` compares it with `build_default_pipeline()` (`backend/app/pipeline/stages/pipeline_builder.py:53-92`, 19 stages); `backend/tests/test_pipeline_order_guard.py`. The guard reads only the root `CLAUDE.md`. `backend/CLAUDE.md` still shows the old order. The documentation diet (archive `lessons.md`, one status file) is not done. 1503e5f2 names CQ-009 but changes no documentation. | Check `backend/CLAUDE.md` and `docs/` with the same guard. Archive `lessons.md`. One status file. | Any agent | T1-15 | - |
| CQ-010 | 679 settings; 27 unread; 23 undeclared reads | P2 | Partial | bec6e27b: `scripts/guards/config_lint.py`; `backend/tests/test_config_lint.py`. | 14 missing settings declared. The 27 unread settings are not removed. | Any agent | T2-06 | - |
| CQ-012 | 21 `first_person_*` modules, many default-off | P2 | Needs owner decision | No commit. | T7-06. | Any agent after decision | T7-06 | D-04 |
| GURU-010 | Registry exists; 621 literals in 128 runtime files bypass it | P2 | Partial (Open at c9b42d3e -> Partial at 1503e5f2) | 1503e5f2: `backend/config/gurus.yaml` new fields; `backend/services/guru_registry.py` (`validate_guru_registry_schema`, `get_impersonation_patterns`); `backend/guardrails/lightweight_handler.py` adds registry patterns to one rail; `backend/tests/test_guru_extensibility.py`. `scripts/guards/guru_literal_guard.py` checks the registry schema and pattern coverage. It does not scan for literal teacher names, and nothing calls it (no hook, workflow or test reference). The 621 literals in 128 files were not re-counted and not reduced. | T8-02: replace literals with registry lookups. Make the guard scan for literals and wire it into the pre-commit or CI. | Any agent | T8-02 | - |
| GURU-011 | Seeds/personas for other teachers and "private teachings" | P2 | Needs owner decision | No commit. | Remove other-teacher seeds (T1-04). | Any agent after decision | T1-04 | D-20 |
| GURU-013 | Two identifier vocabularies for the same teachers | P2 | Partial (Open at c9b42d3e -> Partial at 4eb04ae8) | 4eb04ae8: `canonical_guru_id` in `backend/services/guru_registry.py`; Qdrant filters in `backend/services/first_person_store.py` and `first_person_context_store.py` use it; `backend/tests/test_canonical_teacher_ids.py`. It normalises query filters only. Stored payload values are unchanged. Whether the canonical value matches every stored value needs a live collection check. | Live check of stored `teacher_id` and `guru_id` values; backfill or alias plan if they differ. | Any agent (code) + Live infrastructure (check) | T3-07 | - |
| GURU-014 | No joint-attribution rule | P2 | Needs human | No commit. | Joint-attribution rule; guru review. | Human specialist (guru review) | T8-01, HUMAN | - |
| IP-005 | Broadcaster content treated as teacher-approved | P2 | Needs human | No commit. | Broadcaster permission. | Human specialist (rights holder) | T3-06, HUMAN | D-13 |
| IP-006 | Seed data defines other teachers and a "private teachings" persona | P2 | Needs owner decision | No commit. | Same as GURU-011. | Any agent after decision | T1-04 | D-20 |
| PRD-001 | Relative `/api` fetches break cross-origin deploys | P2 | Closed | f4d94f13: `eslint.config.js` rule; 5 call sites changed. | ESLint regex also matches a few lookalike paths. | - | T1-16 | - |
| PRD-003 | "Server history" is client-written | P2 | Open | No commit. T6-05 reserved. | Backend writes assistant turns. | Reserved (stronger model, supervised) | T6-05 | - |
| PRD-004 | Push prompt can follow a crisis answer | P2 | Closed | e47d9f9f: `src/lib/chat/pushEligibility.ts`; `src/test/chat/pushEligibility.test.ts`. | Frontend `TEACHING_ROUTES` allowlist is strict. | - | T1-10 | - |
| PRD-005 | Assistant slugs disagree (fails closed with 403) | P2 | Needs owner decision | No commit. | Unify assistant slugs (T1-04). | Any agent after decision | T1-04 | D-20 |
| PRD-008 | No user research grounds product decisions | P2 | Needs human | No commit. | User study (T2-07, needs staging). | Human specialist + Live infrastructure | T2-07, HUMAN | - |
| UX-002 | Streak copy ties usage to spiritual progress | P2 | Needs owner decision | No commit. | Neutral streak copy (T1-12). | Any agent after decision | T1-12 | D-19 |
| UX-003 | Engagement prompts ignore emotional context | P2 | Closed | e47d9f9f and 1e8bf812 (same fix as PRD-004). | None. | - | T1-10 | - |
| UX-004 | Retention metrics are usage-based | P2 | Open | T2-03 (eba53ac5) added outcome metrics; retention metrics unchanged. | Outcome-based retention view. | Any agent | T2-03 | - |
| X-04 | Designated branch already merged; checkout stale and shallow | P3 | Open | No commit. | Revalidate against current `main` (T0-06). | Any agent | T0-06 | - |
| ADV-06 | Memory inventory omits WhatsApp SQLite and the edge extraction worker | P3 | Closed (Open at c9b42d3e -> Closed at 4af5e711) | 4af5e711: `12-personal-mentor-memory-ethical-retention.md` now lists the WhatsApp SQLite store (`whatsapp_bot/wa_bot.py:119-130`, tables `wa_messages`, `wa_state`) and the edge extraction worker (`supabase/functions/memory-extract*`). Documentation fix only. The "Disabled by policy" label in the new row is not checked against code. | None. | None (closed) | T6-01 | - |
| AI-008 | Static model routing on the FP lane | P3 | Needs owner decision | No commit. | T7-03. | Any agent after decision | T7-03 | D-17 |
| MEM-005 | Client conversation summary enters prompt unfenced | P3 | Closed | a8bd93a5: `backend/tests/test_untrusted_prompt_fences.py::test_conversation_summary_is_fenced_as_untrusted`. | None. | - | T6-03 | - |
| SAFE-006 | `REFERENCE_VOICE` health claims left in a serving module | P3 | Closed | 66e0ef3e: `REFERENCE_VOICE` health claims removed from the serving module; the only remaining match is a docstring in `backend/services/voice/style.py:8`. | None. | - | T1-02 | - |
| SAFE-008 | Transcript text unfenced in scorer prompt | P3 | Closed | a8bd93a5: `test_untrusted_prompt_fences.py::test_relevance_scorer_prompt_fences_clip_text`. | None. | - | T5-04 | - |
| DATA-17 | OKF compile drift; absolute host paths | P3 | Needs owner decision | No commit. | T3-11. | Any agent after decision | T3-11 | D-05 |
| DATA-19 | Corpus and graph backups tracked in the public repo | P3 | Needs owner decision | No commit. | T0-02. | Any agent after decision | T0-02 | D-01, D-02 |
| RET-11 | Three vector schemas and searchers for teaching content | P3 | Needs owner decision | No commit. | T7-06. | Any agent after decision | T7-06 | D-04 |
| SEC-008 | CORS wildcard converted to credentialed regex | P3 | Closed | 6d47a2fc: `backend/app/main.py::_assert_no_bare_wildcard_origin`; `backend/tests/test_main_cors.py::test_production_rejects_bare_wildcard_origin_at_startup`. | Scoped wildcard patterns are still allowed by design. | - | T1-14 | - |
| SEC-009 | Dead WhatsApp JWT signer with default secret | P3 | Closed | b1231288: `whatsapp_bot/wa_bot.py` signer and PyJWT dependency removed. | None. | - | T1-13 | - |
| SEC-010 | Unauthenticated deep health check | P3 | Closed | 6d47a2fc: `backend/app/api/health.py` token check; `backend/tests/test_health.py::test_health_public_view_is_shallow_without_token`. | Check Railway probes read only the status code. | - | T1-14 | - |
| CQ-011 | `asyncio.run` inside Celery tasks | P3 | Open -> Closed in code at 0176739e (`tasks/worker_loop.py`, `test_celery_worker_loop.py`) (SHA corrected: baba3da) | Part of T7-02. SHA correction 2026-11-06: the Celery loop landed as baba3da; `0176739e` is not on the branch. | Celery event-loop handling. | Reserved (stronger model, supervised) | T7-02 | - |
| CQ-013 | Sync `Depends` in `compliance.py` (breaks L-DOCKER-18) | P3 | Closed | b045054a: `backend/app/api/compliance.py` `_get_container_safely` is async. | None. | - | T1-13 | - |
| CQ-014 | Misleading names (`container.ollama`) | P3 | Partial (Needs owner decision at c9b42d3e -> Partial at 2318a368) | 2318a368: `container.llm` is canonical; `ollama` is a property alias (`backend/app/container.py`); `get_llm_provider` helper; `backend/tests/test_container_llm_gateway.py`. The alias stays. `container.ollama` is still used in `backend/app/api/admin.py:906`, `backend/rag/graph_builder.py:69`, four scripts and 56 test lines. | Move the remaining callers to `container.llm`; then remove the alias. | Any agent | T7-03 | - |
| PRD-002 | Client sends a system prompt the backend discards | P3 | Needs owner decision | No commit. | Stop sending the client system prompt (T1-04). | Any agent after decision | T1-04 | D-20 |
| PRD-007 | Two first-person surfaces with different contracts | P3 | Needs owner decision | No commit. | One FP surface (T5-03). | Any agent after decision | T5-03 | D-03 |
| IP-007 | Demo music, images, video licences unconfirmed | P3 | Needs human | No commit. | Licences for demo assets. | Human specialist (rights holder) | HUMAN | - |
| IP-008 | Tracked evidence leaks owner's local paths and username | P3 | Needs owner decision | No commit. | T0-02. | Any agent after decision | T0-02 | D-01 |
| UX-009 | Personalisation controls and memory copy promise effects the teaching lane ignores | P3 | Partial (Open at c9b42d3e -> Partial at 2a91817f) | 2a91817f: `src/components/profile/GuidancePreview.tsx` says tone and depth apply to practices and reflections, and teachings stay verbatim. Other memory and personalisation copy was not checked or changed. | Audit the remaining personalisation and memory copy. Owner review. | Any agent + Owner review | T6-10 | - |
| UX-010 | WhatsApp button always shown although the channel is `disabled_by_policy` | P3 | Closed | f4d94f13: `src/hooks/useChatCapabilities.ts`; `src/test/DesktopSidebar.test.tsx`, `src/test/useChatCapabilities.test.ts`. | None. | - | T1-16 | - |
| UX-011 | Anonymous quota invisible until used up; reset time never shown | P3 | Partial (Open at c9b42d3e -> Partial at 2a91817f) | 2a91817f: `src/components/chat/QuotaAuthPrompt.tsx` shows "Resets in N hours" from `retry_after_seconds` (sent by `backend/app/api/chat.py:127`). It shows only after the quota is used up. The quota stays invisible before that. | Show remaining quota before the limit. | Any agent | T6-10 | - |

## 3. Next 15 tasks an agent can do now without decisions

Updated 2026-11-06 for head `fb5cab0f`. Done since `c9b42d3e` and removed: T1-18 (UX-005 closed), T6-01 (ADV-06 closed). Tasks 8 to 14 and 5 are now remainders of work that landed as Partial. Task 5 replaces the old T1-18 slot.

Rules used: no owner decision, no clinician or native speaker, no live system, not a reserved task. Order: severity of the findings closed first, then the file-conflict order in `20-ordered-engineering-roadmap.md` §5 (`first_person_pipeline.py`: T4-01 -> T7-01 -> T4-06 -> T7-02; `config.py`: T2-06 last; `ChatInterface.tsx`: T1-16 -> T1-19 -> T1-10 -> T1-18 -> T6-09). One task ID per PR, under about 400 changed lines.

| # | Task | Closes | Sev | Files it touches |
|---|---|---|---|---|
| 1 | Confirm CI on the current head. Fix any regression. Treat T1-05 and SEC-010 behaviour as intended. | X-01, GURU-001 (Partial) | P1 | whatever the failing job names; no planned file |
| 2 | T4-06 evidence-judge consolidation (ADR-009). T7-01 is done. The scorer timeout stays D-16. | SYS-006 (judge part), RET-10 | P1, P2 | `backend/services/first_person_pipeline.py`, `backend/tests/test_first_person_pipeline_golden.py`, relevance-gate tests |
| 3 | GURU-012 remainder: locator check for admin-curated and harvested tips. | GURU-012 (Partial) | P1 | `backend/app/api/teachings.py`, `backend/tests/test_no_unsourced_teacher_attribution.py` |
| 4 | EVAL-003/004 remainder: point legacy benchmarks at the serving lane, or label them as the dormant path. | EVAL-003, EVAL-004 (Partial) | P1, P2 | `backend/benchmarks/`, `.github/workflows/eval-gate.yml`, `evals/` |
| 5 | T6-10 remainder: change landing and meta copy that still says "AI companion"; audit the other personalisation copy; show remaining quota before the limit. Owner review before release. | PRD-010, UX-009, UX-011 (Partial) | P2, P3 | `src/locales/en.json`, `src/pages/Index.tsx`, `src/components/chat/QuotaAuthPrompt.tsx` |
| 6 | SYS-001 remainder: classifier-failure branch and no-context node call fail closed. | SYS-001 (Partial) | P2 | `backend/app/pipeline/stages/graph_stage.py` (~211-220), `backend/rag/nodes/first_person.py`, `backend/tests/test_fp_fail_closed.py` |
| 7 | SEC-003 remainder: fix the other log sites in the ratchet and lower `KNOWN_OFFENDER_BUDGET` (19). | SEC-003 (Partial) | P2 | files the AST scan in `backend/tests/test_no_seeker_text_in_logs.py` reports |
| 8 | ADV-04: retire or relabel the admin `eval-run` edge function. | ADV-04 | P2 | `supabase/functions/eval-run/`, docs |
| 9 | T1-14 remainder: pin the `Dockerfile.railway` base image; add a test that rejects `:latest` in compose; fix `memgraph-mage:latest` in `backend/CLAUDE.md`. | SEC-006 (Partial) | P2 | `backend/Dockerfile.railway`, `backend/tests/test_docker_compose_healthcheck.py`, `backend/CLAUDE.md` |
| 10 | T1-15 remainder: run the stage-order guard on `backend/CLAUDE.md` and `docs/`; archive `lessons.md`; one status file. | X-07, CQ-009 (Partial) | P2 | `lessons.md`, `backend/CLAUDE.md`, `docs/`, `scripts/guards/pipeline_order_guard.py` |
| 11 | T8-02: replace teacher-name literals with registry lookups; make `guru_literal_guard.py` scan for literals and wire it into pre-commit or CI. | GURU-010 (Partial) | P2 | `scripts/guards/guru_literal_guard.py`, `.pre-commit-config.yaml`, runtime files the scan reports |
| 12 | T6-02/T6-03 remainder: feed real seen-clip ids to `memory_signals` (the chat history payload carries no citations); call `compile_user_preferences` in the persona path. | MEM-002, MEM-004 (Partial) | P2 | `backend/app/pipeline/stages/first_person_bridge.py`, `backend/services/layered_memory/l3_persona_generator.py`, `backend/tests/test_fp_memory_signals.py` |
| 13 | T7-05 remainder: lower the exception ceiling (729) and remove the 17 silent swallows; shrink the import allowlist. | CQ-006, CQ-007 (Partial) | P2 | `scripts/guards/exception_baseline.txt`, `scripts/guards/import_layer_allowlist.txt`, files the scans report |
| 14 | T4-07 remainder: pass `verified_only=True` at the other helpline call sites (after the owner agrees that only verified lines may show). | SAFE-004 (Partial) | P1 | `backend/services/serene_mind_engine.py`, `backend/rag/nodes/intent.py`, `backend/rag/prompts/system.py`, `backend/app/pipeline/stages/kill_switch_stage.py`, `backend/guardrails/lightweight_handler.py`, `backend/tests/test_verified_helplines_only.py` |
| 15 | T2-06 remainder, last in the `config.py` order: remove the 27 unread settings. | CQ-010 (Partial) | P2 | `backend/app/config.py`, `scripts/guards/config_lint.py`, `backend/tests/test_config_lint.py` |

Task 14 needs one owner confirmation first (the visible helpline list shrinks to Tele-MANAS and 112). Treat it as ready only after that.

Also ready, not ranked: T1-20 (locale keys; native review before release), T5-07 (prompt registry), T0-06 (revalidation, X-04), CQ-008 (replace source-text tests), T7-04 remainder (cache consolidation, CQ-003), T3-07 remainder (needs a live collection check), UX-004 (outcome-based retention view, T2-03). T1-12 needs D-19 first. T6-04 remainder (clip id on the wire) needs PROPOSED D-PQ7 first.

## 4. Items blocked by each decision (D-**)

| Decision | Topic | Findings blocked |
|---|---|---|
| D-01 | Private repository, purge | DATA-19, IP-001, IP-002, IP-008, SEC-005, X-06 |
| D-02 | Tracked OKF files | DATA-19, IP-001, SEC-005, X-06 |
| D-03 | ADR-001 layered answer | ANS-004, ANS-006, ANS-007, PRD-007, RET-03, RET-04, RET-06 |
| D-04 | ADR-002 general lane | AI-001, ANS-003, CQ-012, RET-11, SEC-007, SYS-002 |
| D-05 | ADR-005 retire graph stack | DATA-08, DATA-10, DATA-17, RET-05 |
| D-06 | Clinician and distress ADR | ANS-001, ANS-002, SAFE-001, SAFE-002, SAFE-003 |
| D-07 | `/api/first-person/query` clients | SEC-001, SEC-002 |
| D-08 | Private evidence store and backups | DATA-01, DATA-09, IP-004, SYS-012 |
| D-09 | Gold sheet authorship | EVAL-002, EVAL-005, GURU-001, GURU-002 |
| D-10 | Sign-off artefacts outside the repo | GURU-005, IP-003, SAFE-005 |
| D-11 | Scope of the 2026-11-04 authorisation | GURU-004 |
| D-12 | Voice extraction rights | IP-002 |
| D-13 | Broadcaster clearance | IP-005 |
| D-14 | Served collection, encoder, approved version | DATA-14, DATA-16, RET-07 |
| D-15 | Qdrant writers and keys | DATA-06, SEC-006 |
| D-16 | Scorer model and price | AI-007, RET-10, SYS-006 |
| D-17 | Remove provider code | AI-005, AI-008, CQ-002 (CQ-014 rename done at 2318a368; alias remains) |
| D-19 | Churn funnel | UX-001, UX-002 |
| D-20 | Other-teacher seeds | GURU-011, IP-006, PRD-002, PRD-005 |
| D-21 | Consent defaults | MEM-003 |
| D-22 | Priority Indic languages | ANS-001, ANS-002, ANS-008, SAFE-001, SAFE-002, SAFE-003, UX-008 |
| D-23 | Seeker questions for held-out set | EVAL-002 |
| D-24 | Lovable role | X-05 |
| D-25 | Usefulness target | EVAL-006 |
| D-26 | Qdrant hosting | SYS-007, SYS-008 |

D-18 (delete dormant modules) blocks no finding here. D-07 is decided (Auth + quota + budget on `/api/first-person/query` and video rights gate, closed under T1-08). D-27 is decided (audit committed under `audits/audit-output-2026-11-04/`). The four T7-01 sub-decisions were answered on 2026-11-05 and T7-01 is done. T0-03 (branch protection) is an owner action with no D-** number and blocks X-02 and X-03.

## 5. Human-only items

| Gate | Findings | Note |
|---|---|---|
| Clinician review (core, benign, multi-turn sets; discriminator; dependency rule) | ANS-001, ANS-002, SAFE-001, SAFE-002, SAFE-003, SAFE-007, SAFE-005 | T4-04 and T6-07 are also reserved. `evals/pr_suite/distress_crisis.jsonl` is AI-authored. |
| Native-speaker review | ANS-008, UX-008 | Also the care line and the ADV-05 label. |
| Independent gold labels (>=299, two people) and held-out set | GURU-001, GURU-002, EVAL-002, EVAL-005 | D-09, D-23. |
| Helpline phone calls (never test-call 112) | GURU-007, SAFE-004 | 1 of 15 verified. |
| Written rights approvals and licences | GURU-005, IP-002, IP-003, IP-005, IP-007 | D-10, D-12, D-13. |
| Guru review of joint attribution | GURU-014 | |
| User study | PRD-008 | Needs staging (T9-01). |

## 6. Live-infrastructure items

| Item | Findings | Task |
|---|---|---|
| Staging environment, IaC | SYS-007 | T9-01 (D-26) |
| Real-model load test | SYS-008, SYS-003 (staging load before T7-02; T7-03 did not change SYS-003) | T9-02 |
| Qdrant keys, live collection audit, hash and ID recomputation, stored teacher-ID check | DATA-06, DATA-15, DATA-14, SEC-006, DATA-13, GURU-013 | T3-02 enable, T9-04, `22` |
| Backups and restore drills | SYS-012 | T3-10 |
| Supabase RLS state versus migrations; applying any migration | DATA-11, L-07 | T3-08 |
| Docker image build with the rights register | DATA-02 | T3-01 |
| Railway runbook | L-03, L-04 | T9-04, `22b` |

## 7. Reserved tasks and their current state

| Task | Findings | State at `c9b42d3e` |
|---|---|---|
| T4-04 distress topic vs state | ANS-001, ANS-002, SAFE-001, SAFE-002, SAFE-003 | Not started. Preconditions (clinician-reviewed sets, owner go-ahead) are not met. |
| T6-07 dependency guard | SAFE-007 | Not started. Needs a clinician-written rule. |
| T3-06 source registry and `takedown()` | DATA-07, DATA-12, DATA-18 | Not started. T3-08 snapshot CI is merged (37032757), so one precondition is met. Owner must approve migration text. |
| T6-05 client RLS `role='user'` | PRD-003 (and UX-006 via T6-09) | Not started. Owner approves migration. |
| T6-06 durable erasure and purge | ADV-01, SEC-004 | Not started. Owner approves purge rule. |
| T7-01 split of `FirstPersonPipeline.execute` | CQ-001 (part) | Done. Commits `31ebbd89` (goldens), `1343702c`, `b9902a59`, `0caa21f2`, `a38cbc28`, `6c1179b8`, `997ccc3a`, `c6e5b4bd`, `2870ddf4`, `e875073c`, `0c643bc2` (T7-01a-l). `execute` went from 2,146 lines to about 266 (269 by AST span). Golden test: `backend/tests/test_first_person_pipeline_golden.py`. I did not run it. Open: the 735-line harness block is one method; `generate_answer` is untouched. |
| T7-02 async teaching lane | SYS-003, CQ-011 | Done in code: a54373b (T7-02a), c89e1b9 (T7-02b), baba3da (T7-02c), d177cd2 (T7-02d), 503212f (T7-02e); independent review 2026-11-06 found that an outer cancel left the LLM call running and `execute()` had no bound, fixed in dcfb3a5 (SHAs corrected 2026-11-06: `a7359225` and `0176739e` were pre-rebase and are not on the branch; §0v of `IMPLEMENTATION-AGENT-PROMPT.md`); staging c20 and watchdog removal remain. Was: not started at head `fb5cab0f`. Precondition T7-01 is met. Needs a staging c20 load test before the watchdog is removed. T7-03 (2318a368) named SYS-003 and did not change it. |

## 8. Notes on severity and on the index

- The section headings of `findings-index.md` (P1 45, P2 77, P3 19) disagree with its "Counts" table (47, 81, 22). I did not change either. The table is authoritative. The new dated line in the index points here.
- The "Pillars" column shows P1 for some findings that sit in P2 or P3 tables (for example AI-002, CQ-011, CQ-013, SEC-008). That is a pillar label, not a severity. Readers can confuse the two. No severity change proposed.
- I propose no severity change. Observation only: after T1-05, the residual in SYS-001 (classifier-failure branch) is narrow, so its P2 stays reasonable.
- Downgraded closures (versus §0g): GURU-012 (admin-curated tips still default the teacher name), SEC-003 (19 other log sites under a ratchet), SYS-001 (residual general-lane branches), DATA-15 (live collection audit not run), DATA-16 (the shipped serving contract sets no `approved_corpus_version`, so the check is inactive). These are Partial here.
- RET-07 is Partial for a similar reason: the shipped serving contract declares no encoder.

## 9. Verified, assumptions, unknowns

**Verified (read in this session, not run).** I read the cited code or test for all 11 P1 closures (EVAL-001, GURU-003, GURU-006, RET-09, ADV-03, ANS-005, DATA-02, DATA-05, MEM-003, SYS-004, UX-007). I read code or tests for 22 of the 22 P2 and P3 closures, with a shallower read (test file exists, key symbol present, commit diff) for AI-006, DATA-04, SAFE-006, MEM-005, SAFE-008, ADV-05, PRD-001, PRD-004, UX-003, UX-010, PRD-009, CQ-013, SEC-009, DATA-03, DATA-11, RET-01, RET-02, AI-002, AI-003 and CQ-005. So 33 closures were checked by reading: 11 P1 with full reads, 22 P2/P3 with spot reads. I checked by `git show --stat` and file greps that the test files named exist for T2-01, T2-02, T2-05, T2-06, T3-02, T3-03, T3-04, T3-05, T3-08, T4-01, T4-02. I confirmed by `cmp` that `scripts/ops/check_first_person_public_release.py` and its `backend/scripts/ops/` copy are identical.

**Assumptions.** (1) The statuses of open items rest on the commit list `git log c7befa3d..HEAD` (73 commits) and on `IMPLEMENTATION-AGENT-PROMPT.md` §0 to §0o; I assumed an item with no commit is open. (2) "Who can close" follows §0i and §0j of that prompt, revalidated against the roadmap task table. (3) The `evidence` column cites symbol or test names, not line numbers, except where I read a line.

**Unknowns.** (1) CI state on `c9b42d3e`: not observed. No test was run for this register. (2) Whether Fast and Deep strategies also route DISTRESS directly (AI-002): only the Standard change was read. (3) Whether non-L3 prose still gets the register block (AI-003). (4) Live Qdrant state, hash recomputation, Railway behaviour (L-01 to L-04). (5) The effect of T4-01 and T4-02 on retrieval quality: the frozen bank is small and was not run. (6) The owner's local `.env` flags (L-05).

**Verified 2026-11-06 (batches 9 to 13, head `fb5cab0f`).** I read `git show` for all 21 commits and the code at head for UX-005, MEM-002, MEM-004, PRD-006, SAFE-004, CQ-003, CQ-006, CQ-007, CQ-009, GURU-010, GURU-013, DATA-13, SEC-006, CQ-014 and ADV-06. I did not run any test. **Could not verify:** (1) that the pinned image tags `memgraph-mage:2.20.1` and `autoheal:1.2.0` exist (no network); (2) the test pass counts quoted in the commit messages and in `IMPLEMENTATION-AGENT-PROMPT.md` 0p to 0t; (3) the UX-009 copy outside `GuidancePreview.tsx` and the `Disabled by policy` label added for ADV-06; (4) whether stored Qdrant `teacher_id` values match the new canonical filter value (live system); (5) the CI state at head. The `Left` column of 0p to 0t shows "-" for items this register keeps as Partial; the agents did not list the gaps found here.

## 10. Findings from the 2026-11-06 reviews (not yet in `findings-index.md`)

The mobile, k8s and accessibility reviews added findings with new prefixes. They are not in the counts in §1. The prefixes are now registered in `CONVENTIONS.md` §5, and all 75 findings from the specifications (DATA, MEM, OPS, ANS, RET, MOB, K8S, A11Y) are listed in the last section of `findings-index.md`, status Open (found 2026-11-05/06). They are still not in the §1 counts or the §2 register.

| Prefix | P0 | P1 | P2 | P3 | P1 IDs | Source |
|---|---|---|---|---|---|---|
| MOB | 0 | 6 | 6 | 3 | MOB-01, MOB-02, MOB-03, MOB-04, MOB-05, MOB-10 | `specifications/MOBILE_APPS_REVIEW_AND_RELEASE_SPEC.md` |
| K8S | 0 | 1 | 6 | 2 | K8S-06 | `specifications/K8S_MANIFESTS_REVIEW.md` |
| A11Y | 0 | 7 | 9 | 1 (6 parts) | A11Y-01, A11Y-02, A11Y-03, A11Y-05, A11Y-06, A11Y-11, A11Y-16 | `specifications/ACCESSIBILITY_AUDIT_AND_REQUIREMENTS.md` |
| Total | 0 | 14 | 21 | 6 | | |

Now indexed: DATA-20 to DATA-27, MEM-007 to MEM-012, OPS-001 to OPS-009, ANS-009 to ANS-013, RET-12 to RET-17. Still not indexed because they carry no ID: the Railway, AI-harness, GURU and RLIMIT groups of `FINAL_AUDIT_GAP_ANALYSIS.md` §2.

### 10.1 Second pass (2026-11-06): IDs assigned to unnumbered groups and the Lovable review

| Prefix | P0 | P1 | P2 | P3 | P1 IDs | Source |
|---|---|---|---|---|---|---|
| RW | 0 | 4 | 2 | 0 | RW-01, RW-02, RW-03, RW-05 | Railway runbook spec |
| AI | 0 | 2 | 3 | 0 | AI-009, AI-010 | Harness spec |
| GURU | 0 | 0 | 2 | 0 | — | Guru spec |
| SYS | 0 | 0 | 1 | 0 | — | Lessons review |
| LOV | 0 | 3 | 4 | 1 | LOV-01, LOV-02, LOV-03 | `specifications/LOVABLE_SYNC_PATH_REVIEW.md` |
| Total | 0 | 9 | 12 | 1 | | |

All 22 are registered in `findings-index.md` (second-pass section). Status: Open. Who can close: an agent for RW-01 to RW-06, AI-009 to AI-013, GURU-016, SYS-013, LOV-02 to LOV-08; the owner for LOV-01 (GitHub settings) and GURU-015 (D-05).

### 10.2 Third pass (2026-11-06): load model and accessibility proxy session

| ID | Sev | Who can close |
|---|---|---|
| SYS-014 | P1 (lead) | Agent (NEW-LOAD-3) after the owner records the scorer price (D-16) |
| A11Y-20 | P2 | Agent (NEW-A11Y-2) |
| A11Y-22 | P2 (candidate) | Human screenshot check, then agent |
| A11Y-18, A11Y-19, A11Y-21 | P3 | Agent |

Running total of findings added by the final verification pass: 75 (first pass) + 22 (second pass) + 6 (third pass) = 103, all in `findings-index.md`.

## 11. Opus thread, 2026-11-06: status changes with SHAs, and the final review (§4.8)

Branch `feature/audit-strengthen-rag-qdrant`. Every SHA below is on the pushed branch. Tests ran in the cloud container with fakes only (no Qdrant, no Docker, no real LLM). A local Mac run on the same head is UNPROVEN until it is reported separately.

### 11.1 Findings without a §2 row (indexed in §10)

| Finding | Task | Old -> new status | SHA | Proof (test) | Remaining |
|---|---|---|---|---|---|
| ANS-011 | NEW-ANS-1 | Open -> Closed in code | 3959928 | `test_answer_outcome_composition.py::test_served_related_clip_counts_as_served` (failed before: outcome "abstained") | Whether the UI styles a served related clip as an abstain: frontend, UNVERIFIED |
| ANS-010, RET-17 | NEW-ANS-2 | Open -> Closed in code | 307560d | `test_abstain_cause.py` (5 bridge cases failed before); `test_fp_fail_closed.py` | Abstain copy per cause waits on D-PQ9 and NEW-ANS-4 |
| OPS-001, OPS-002 | NEW-SEC-1 | Open -> Closed in code | 1dac911 | `test_first_person_bridge.py::test_breach_detector_fires_with_the_bridge_flag_off`, `test_served_integrity.py` | Speaker check at assembly not done by design (unverified clips are served with a downgraded label) |
| AC-ANS-01..09 | NEW-ANS-8 | Open -> Closed in code | e863a55, CI job 58176fb | `test_release_invariants.py` (17 cases) | Making the job a required check is a branch-protection setting (owner) |
| DATA-20, DATA-21, DATA-22, DATA-23 | NEW-ING-1, NEW-ING-2 | Open -> Closed in code | f87c0de | `test_corpus_build_safety.py` | A real build against Qdrant: live infrastructure |
| DATA-24 | NEW-ING-3 | Open -> Closed in code | b5eda55 | `test_audio_archive.py` | - |
| AI-009 | NEW-AI-2 | Open -> Closed in code | 61a0ab8 | `test_untrusted_prompt_fences.py`; adversarial suite (9 of 27 cases fail on the base before 61a0ab8) | The answerability and judge prompts neutralise the seeker question but do not fence it (low) |
| AI-011 | NEW-AI-1 | Open -> Partial | 54d5305 | `test_graph_state_routing_keys.py` | `_context_sufficient` routing is dead (the rewrite branch never runs): owner decision; 18 undeclared input or read keys listed in the test |
| MEM-012 | MEM-012 | Open -> Partial | e0ff3c3 | `test_memory_poisoning.py` | Patterns are English only (D-22, native-speaker review) |
| AI-010 | NEW-AI-5 | Open -> Partial | aba9bf4, c609c6f | `test_injection_screen.py` (22 cases) | Flag-for-review is the default; drop mode waits on D-PG16. `ingest/pipeline.py` still drops `InjectionScanner` matches ("act as" included) on the chat corpus |
| NEW-SEC-5, NEW-AI-6 | adversarial suite | Open -> Closed in code (offline part) | 226e974 | `test_adversarial_suite.py` (27 cases; 2 tracked gaps ADV-S10c, ADV-U2a) | Live-stack cases listed in `evals/adversarial/README.md` |
| SYS-014 (rerank part) | NEW-LOAD-6 | Open -> Partial | 36dc746 | `test_rerank_max_tokens.py` | Scorer price (D-16) |

### 11.2 Final independent review of every commit since `12bb3225` (49 commits plus c609c6f)

Method: `git show` of each commit; code at head for the changed paths; for metric, alert and helpline changes, the metric names, labels and vocabularies were checked against the code. One defect was found and fixed (c609c6f). The rest are notes for the owner or the owning thread; none blocks the branch by itself.

| Commits | Author / thread | Verdict | Notes |
|---|---|---|---|
| a54373b, c89e1b9, baba3da, d177cd2, 503212f, 991222e | Harsha (T7-02) | Reviewed in §4.1; one defect fixed in dcfb3a5 | Outer cancel left the LLM call running and `execute()` had no bound. §0v SHAs corrected (see SYS-003 row) |
| ec2e6da, 1ae9429, 3cb9fce | Harsha (test alignment) | No assertion weakened | Fixtures follow T4-01 (one clip per video) and T3-04; helpline asserts now pin the verified block |
| 93b3adc | Sonnet (RW-04) | OK | If the supervisor loop raises for a reason other than a signal, the child is not terminated (the old code called `terminate()` in `finally`). Low |
| 49144c7 | Sonnet (RW-03) | OK, 2 notes | (1) Redis `noeviction` on a Redis that holds the cache and the quota counters: when 512 MB fills, every write fails (cache, rate limit, quota). Needs TTLs on every cache key or a separate cache Redis; UNPROVEN live. (2) The `railway variables set GIT_SHA=...` result is not checked; the script prints success either way. Startup fails closed on a missing SHA, so low |
| 6387f96, a6f2b60, 68f14c1, 72a29bb | Sonnet (Railway, runbooks) | OK | Drain 45 s under a 60 s Railway drain; healthz statements match the code |
| 5327419 | Sonnet (AI-013) | OK | Startup stops in production when the scorer model is empty and the gate is on |
| 6be465f | Sonnet (OPS-8, LOAD-4/5) | Suite red, needs an owner decision | `docker-compose.graded.yml` scorer timeout went from 12 s to 25 s while D-PG13 is open. A stalled scorer now holds a graded request up to 25 s against the 10 s p95 bar. Two tests now disagree: `test_graded_run_preflight.py::test_override_drops_every_code_bind_and_pins_the_serving_path` pins the graded value at 12 (fails at head), and `test_runtime_budget.py::test_compose_files_do_not_override_the_settings_default` requires every compose file, the graded one included, to equal the Settings default 25. Not changed here: the choice is D-PG13. **Resolved 2026-11-07:** Harsha chose option A (graded run 12 s, Settings default 25 s); pinned in 32c12c4, wording in dea7b44 |
| 2ba0b23, 3481144, 260fc87 | Sonnet (CQ-010, T7-05) | OK | Settings use `extra="ignore"`, so an old env var for a removed setting does not stop startup; no compose or env file sets one |
| 159c9c1 | Sonnet (OPS-001..003) | OK | `first_person_requests_total{reason}` exists and `relevance_indeterminate` is in the pinned vocabulary; `guru_integrity_breach_total{lane}` exists |
| 750781c, b4a55f9 | Sonnet (OPS-4, OPS-3/7) | OK, 1 note | `refresh_ops_gauges` catches TimeoutError, OSError, ValueError and RuntimeError only: another exception type from the Qdrant client makes `/internal/metrics` return 500 (a DOWN target, not silence). A new Qdrant client is made per refresh and not closed. Low |
| 58176fb, 7c9a1df | Sonnet (ANS-8 CI, AI-4) | OK | Fakes only |
| 6ea59c6, db87fc3, d9b423d | Sonnet (A11Y) | OK | New label key `chat.relatedNotDirectAnswer` has no locale entry, but the old keys had none either: no translation regression |
| dcfb3a5 to ad53d52 (Opus) | Opus | 2 defects, fixed | aba9bf4: the harness metric folded the new `injection_screen` abstain reason into "other"; fixed in c609c6f (test failed before). d35ab6d: `test_first_person_speculative_parallelism.py::test_crisis_preemption_invariant_s4_...` still asserted the unverified line 988 (passed on d35ab6d^, failed on d35ab6d; the file was not in the subset run); aligned in 024a881 |

Full backend suite at 024a881 in the cloud container (fakes only): 13,031 passed, 1 failed (the graded-timeout conflict above), 58 skipped, 1 collection error (`test_builder_replace_and_snapshot.py`: `soundfile` is not installed in the container). Not run on the Mac.

### 11.3 Follow-up, 2026-11-07: owner decisions (D-PG13, D-16, D-DQ1, D-PG16, D-PQ7, D-PQ9, D-03, outside-India line), Mac run, builder tests

| Item | Status | SHA | Proof |
|---|---|---|---|
| D-PG13 graded scorer timeout | Decided by Harsha (option A) -> Closed in code | 32c12c4 (value, one-source test exempts the graded file), dea7b44 (docs, Sonnet) | `test_graded_run_preflight.py` and `test_runtime_budget.py` both pass at head |
| `test_builder_replace_and_snapshot.py` (2 tests broken by f87c0de) | Failed on the Mac -> Fixed | c190020 | The tests patched the removed `CLEARED_*` lists and used a MagicMock that forgets writes, so `write_video_points` returned `verify_mismatch`. Now: patch `video_rights_decision`, stateful fake Qdrant, and the replace test pins upsert-then-delete. 3 of 3 pass (cloud, with a `soundfile` stub) |
| `ruff format` on `test_openrouter_price_table.py` | Failed on the Mac -> Fixed | 5702573 | Format only |
| D-16 judge model and price (AI-007, RET-10, SYS-006, SYS-014 price part) | Needs owner decision -> Partial | eac1b03 | Model named, price recorded with date and source. The judge sent `temperature=0.0`, which this model rejects (CA-1), so turning the flag on would have abstained on every question; fixed (`test_named_model_gets_the_scorer_call_shape` failed before). Still open: the frozen-bank comparison (T4-06), and whether OpenRouter returns `usage.cost` for this model (UNPROVEN, no live call) |
| D-PQ9 abstain copy (ANS-010 copy part) | Needs owner decision -> Closed in code | 7ad76a7 | `test_abstain_cause.py`: 2 tests failed before. New English line has no owner copy review or native-speaker review (NEW-ANS-4, D-22) |
| Crisis "outside India" line | Needs owner decision -> Closed in code | 144d854 | `test_outside_india_line.py` (5 of 6 failed before); golden `crisis_redirect.json` regenerated (only chars and sha256 change). English only (D-22) |
| D-DQ1 points_servable hash compare | Needs owner decision -> Decided; stays default off | 087af0a, 03d49e2 | `test_points_servable_hash_check.py` |
| D-PG16 injection screen | Needs owner decision -> Decided (flag only) | 03d49e2 | `test_builder_flags_an_injection_span_and_still_writes_it` (guards the decision; passes on the old code too) |
| D-PQ7 point id on the wire | Needs owner decision -> Decided (no) | none | `test_citation_contract.py` keeps forbidding `point_id`; opaque signed id is later work |
| D-03 explanation layer | Needs owner decision -> Decided (not now) | none | ANS-004, ANS-006, ANS-007, PRD-007, RET-03, RET-04, RET-06 stay blocked |

Mac run on 32c12c4 (Remote Control, read-only worktree, 2026-11-07): backend tests 13,215 passed, 45 skipped, 2 failed (the two builder tests above); guards exit 0 (exception ratchet 724 of 724); `ruff check` exit 0; `ruff format` 1 file (above); safety scenarios 226 pass, 4 expected, 0 fail; distress recall 106/110, 0/49 false positives. Not run: Docker, live LLM, e2e. The Mac rerun at the new head is reported in the thread, not here.

## Implementation update 2026-11-07 (Sonnet thread: Railway staging and platform operability)

Head after this thread's last push: `fdd70af` plus the register commit that holds this block. Evidence is the commit diff and the targeted tests named in each commit message. The sandbox had no Mac, no Docker, no Supabase, no Railway, no real Qdrant and no GitHub workflow run. Every row is therefore **UNPROVEN on the Mac and in CI** unless a row says otherwise. Verdict stays **NO-GO**. Rows below that say "Closed" mean the repo change is done and tested here, not that a live system was checked.

| Finding / task | Old status | New status | Commits | What is still open |
|---|---|---|---|---|
| CQ-006 / T7-05 | Partial | Partial | `31cedf9` | Ceiling 724, silent swallows 9 (first-person 0). 8 handlers narrowed or logged. 9 silent sites remain in `api/chat.py`, `api/ingest.py`, `api/admin.py`, `rag/nodes/*`. Import allowlist not shrunk. |
| SEC-003 / NEW-SEC-4 | Partial | Partial | `3f5dfc0` | Log-site budget 19 to 0 for 8 variable names in `app/`, `services/`, `rag/`. Traces, f-string paths with other names and telemetry are not covered by the scan. |
| GURU-010 / T8-02 | Partial | Partial | `99d81af` | Ratchet on 590 lines in 129 files, wired to pre-commit and pytest. No literal was replaced. Line count only. |
| SEC-006 / T1-14 | Partial | Partial | `c97b094` | `Dockerfile.railway` pinned by digest (digest copied from `Dockerfile`, tag existence on the registry UNPROVEN). `:latest` rejected in four compose files. Own images still default to `latest` when `IMAGE_TAG` is unset; `redis:7-alpine` floats. |
| CQ-009 / X-07 / T1-15 | Partial / Open | Partial | `e7259ef` | Stage-order guard now covers `backend/CLAUDE.md` and `docs/` (HLD doc fixed, 5 dated docs on a shrink-only list). `lessons.md` archive not done (cited by number from about 15 code comments; another thread writes to it). "One status file" needs an owner choice. |
| EVAL-003 / EVAL-004 | Partial | Partial | `ebf69ff` | 10 prose-scoring benchmarks labelled `LEGACY_GENERATION_PATH = True`. None re-pointed at the serving lane or run. Live-stack gates still need a deployment. |
| ADV-04 | Open | Partial | `efb3466` | Edge function and admin page relabelled "model-only, not the product". Not retired (owner choice). Edge function not redeployed. |
| DATA-15 / NEW-DQ-1, NEW-DQ-2 | Partial | Partial | `c7f4b9f` | `scripts/ops/fp_live_audit.py` (C-L1 to C-L9, C-L11) and D2 to D5 tests on local-mode Qdrant. Not run against the real Qdrant. C-L10 and C-L12 to C-L16 not built. |
| SYS-008 / NEW-LOAD-1, NEW-LOAD-2 | Needs live infrastructure | Needs live infrastructure | `df8956f` | Locust staging file (s0 to s6, abort rules AB-1/3/5/6) and `load_run_report.py`. No load was generated. NEW-LOAD-7 (the run) needs D-PE7 spend approval. |
| PRD-010, UX-009, UX-011 / T6-10 | Partial | Partial | `fdd70af` | Drafts in `docs/product/COPY_DRAFTS_T6-10_2026-11-07.md` for owner review. No app copy changed. UX-011 needs a backend header and an owner choice. |
| A11Y-01 to A11Y-16 (NEW-A11Y-1 to NEW-A11Y-9) | Open | Partial | `6ea59c6`, `d9b423d`, `db87fc3`, `f9eba2e`, `a67904a`, `1c9b612`, `31eb511`, `aace3bd`, `4d5f9b2`, `5caa10c`, `5ad9944` | 13 axe/Playwright journey tests and vitest pass here (vitest 1139). `/auth`, `/profile`, `/practices` and signed-in states could not run in the sandbox. Settings, memory-settings and delete-account axe states UNPROVEN. NEW-A11Y-10 (human screen-reader pass) untouched. A11Y-17d/e plain-language copy is a draft. Backend `quote_language` field is not added (D-PA11Y4). |
| K8S-01 to K8S-06 (NEW-K8S-1, -2, -5) | Open | Partial | `9e0eb4b`, `49f9e85`, `d55c8e0` | Reference-only headers on 27 files, drift tests, Helm `required` for secrets. Real `helm template` not run. K8S-3 and file moves wait for D-PK8S1. The old chart password literals must be treated as burned if used anywhere live. |
| LOV-02, LOV-03, LOV-04, LOV-06, LOV-07, LOV-08 (NEW-LOV-02 to -08) | Open | Partial | `78ac150`, `8238591`, `d23db14`, `f339f26`, `84ede91`, `5ce3bc9` | Guards and CODEOWNERS written and tested locally. Not observed running in GitHub Actions. Making `release-invariants` and `lovable-guard` (job name in `lovable-pr-guard.yml`) required checks is a repo-settings decision. Lovable "Project knowledge" text not changed (NEW-LOV-05 / D-24). |

## Decisions recorded 2026-11-07 (owner: "do end to end and use intelligence"; "approved and give me the list")

| Decision | Value | Where applied | Status |
|---|---|---|---|
| D-26 | External `QDRANT_URL`; no Qdrant service on Railway | `.railway/railway.ts`, `test_railway_iac.py` | Repo change done. Live URL UNPROVEN |
| D-14 | v10-only: `first_person_v10`, harness and terminal flags on | `.railway/railway.ts` (`SERVING_POSTURE = "v10_only"`) | Repo change done. Clean-Docker start UNPROVEN |
| D-29 | Faculty access code is the only staging gate | `.railway/railway.ts` | Set `FACULTY_ACCESS_CODE` in the dashboard. UNPROVEN |
| D-30 | Worker and beat on; `INCLUDE_CELERY` is the one switch | `.railway/railway.ts` | Repo change done. UNPROVEN on Railway |
| D-24 | Lovable by PR only | guards from `78ac150` to `5ce3bc9` | Needs required checks (below) |
| D-PK8S1 | Kubernetes files are reference only | headers from `9e0eb4b` | Done |
| D-PA11Y6 | No new dependency; axe only | A11Y commits | Done |
| D-PE7 | Spend approved for the staging load run. Harsha then said "remove the cap" (2026-11-07): the harness has no default spend stop; `SPEND_CAP_USD` is optional and a cost log prints every 15 s. The app OpenRouter guard, the provider limit and the Railway usage limit stay as backstops | `backend/benchmarks/fp_staging_load.py` | Approved by Harsha. Run NOT started: no staging exists |
| Indexes | Harsha approved creating the 16 missing indexes on live `first_person_v10` | `scripts/ops/ensure_fp_span_indexes.py` (dry run by default) | Script tested on fakes only. Not run on the live collection |
| Required checks | Harsha approved `release-invariants` and `lovable-guard` (job name in `lovable-pr-guard.yml`) | GitHub settings | Not set: needs a repo admin in the GitHub UI |

Verdict stays **NO-GO**.

## Live `first_person_v10` data fix 2026-11-07 (DATA-15, NEW-DQ-1/2)

Owner approval: Harsha, 2026-11-07 ("approved", "its ok, you can do those", "ok"). Harsha ran the writes in a Mac terminal. The live audit before: C-L3, C-L5, C-L7, C-L8 failed. After: no failed check (C-L1, C-L2, C-L3, C-L5, C-L6, C-L7, C-L8 PASS).

| Change | Tool | Result |
|---|---|---|
| 16 payload indexes | `scripts/ops/ensure_fp_span_indexes.py --apply` | `missing_after` empty, points 4226 |
| `domain_rights_status=licensed` on children that lacked it, value from the serving rights resolver | `scripts/ops/backfill_fp_rights_status.py --apply` | 2758 children, 491 videos, 0 left over; serving filter 2 to 2738 of 2760 (22 lack `speaker_verified`) |
| `source_text_hash` and derived id for 2 hashless test-looking points | `scripts/ops/fix_fp_unhashed_points.py --apply` | `3eb5cc1a…` to `877f7269…`, `52c880a0…` to `20b32148…`; quote text and `transcript_hash` unchanged |

Cause: the v1 build wrote no `domain_rights_status`. The builder was fixed in `f87c0de` but v10 was not rebuilt. Rollback: restore snapshot `first_person_v10-1111874297854021-2026-11-07-01-09-45.snapshot`, or `delete_payload` on the ids in `/tmp/rights_backup_v10.json`. Points 4226 throughout. The C-L11 digest does not cover `domain_rights_status`. Serving is UNPROVEN until the graded clean-Docker run. Verdict stays **NO-GO**.
