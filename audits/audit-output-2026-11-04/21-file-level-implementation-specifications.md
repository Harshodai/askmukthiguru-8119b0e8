# 21 — File-level implementation specifications

Owner: lead. Scope: every P0 and P1 task in `20`. P2/P3 tasks use the remediation, acceptance and regression-test fields of their finding record (see `findings-index.md` for the owning document).

**Line numbers are approximate, from reads of `main@46b808fb` on 2026-11-04. Before editing, the coding agent re-locates each symbol by name (`rg -n '<symbol>'`) and records any drift (T0-06).**

Template for each spec: Files and symbols · Existing behaviour · Required change · Non-goals · Tests · Acceptance · Risk · Rollback · Evidence.

---

## T0-02 — Purge public teaching content; extend the publication guard
- **Files and symbols:** `audits/evidence/public_release_v10_points_export_2026-10-21.json`; `audits/evidence/*tier*.jsonl` (fields `live_verbatim_text`, `audio_path`); `public/audio/meditation/preethaji-serene-mind.mp3` (and siblings); `data/*.json`; `data/security_report.json`; `scripts/guards/lesson_guards.py`; `scripts/guards/publication_allowlist.txt`, `publication_baseline.txt`; `src/components/meditation/meditationSteps.ts` (~14–22, audio URLs).
- **Existing:** The files above are tracked in a public repository (`14c` IP-001, IP-002, IP-008; `14` SEC-005).
- **Change:** (1) Move each file to the private evidence store (T3-09) and keep only `{path, sha256, bytes}` stubs. (2) Remove teacher audio and point `meditationSteps.ts` at a licensed asset, or disable the step behind a flag until a licence exists. (3) Extend `lesson_guards.py` publication checks so a tracked file fails if it contains JSON keys `verbatim_text`, `source_transcript_text` or `live_verbatim_text`, an `/Users/` path, or an audio file under `public/` without a rights-register id.
- **Non-goals:** History rewrite (owner decision T0-01). OKF files (owner decides in D-02; treat separately).
- **Tests:** Guard unit tests with one positive and one negative fixture per rule.
- **Acceptance:** `git ls-files | xargs <guard>` passes. The Serene Mind feature does not play teacher audio without a licence row.
- **Risk:** Tests that read these files break. Point them at fixture copies.
- **Rollback:** Re-add stubs. Never re-add the content.
- **Evidence:** `14c` §IP-001/IP-002; `01` X-06.

## T0-04 — Honest release-gate test; correct the release scopes; green `main`
- **Files:** `backend/tests/test_first_person_public_release_gate.py` (~924, `test_the_repository_gate_reports_owner_action_required`); `audits/evidence/FIRST_PERSON_OWNER_DECISIONS_2026-10-22.md` (~312–328 scopes); `audits/evidence/public_release_owner_packet_authorization_2026-10-22.md`.
- **Existing:** The test asserts `STATUS_READY` and fails in CI with `OWNER_ACTION_REQUIRED`. The scopes set public production to true; the notes say NO-GO.
- **Change:** (1) Restore the assertion to the computed clean-checkout status (`OWNER_ACTION_REQUIRED` until T1-11 and T3-09 land). (2) The owner edits the scopes to match the notes (owner-only local review). The agent does not edit owner decisions.
- **Non-goals:** Changing the gate logic (T1-11).
- **Tests:** The existing test, honest.
- **Acceptance:** "Lint & Test" and "Production Readiness" are green on `main`.
- **Risk:** None.
- **Rollback:** Not applicable.
- **Evidence:** `01` §8.3; `23` GURU-001, GURU-004.

## T1-01 — Voice governance
- **Files:** `CLAUDE.md` (section "First-Person Voice Architecture & Invariants": "Direct Sacred Presence", "Quote Weaver"); `AGENTS.md` (matching text); `scripts/guards/lesson_guards.py`.
- **Existing:** Agent guidance orders all teaching to be delivered in the first person ("I invite you to see…") and quotes to be "woven organically". `GURU_SYSTEM_PROMPT` (`backend/rag/prompts/system.py` ~179–184) forbids speaking as the founders.
- **Change:** Replace the section with this rule: the teachers' words appear only as verbatim spans rendered from the store, with a source. The assistant speaks in its own labelled voice and never in a teacher's first person. Add a guard that fails if agent-instruction files contain directives to generate teacher first-person text.
- **Non-goals:** Changing prompts (T1-06).
- **Tests:** Guard test with a fixture paragraph.
- **Acceptance:** `rg -n "Direct Sacred Presence|MUST be delivered directly in the first person"` returns nothing in the instruction files.
- **Evidence:** `10` ANS-005.

## T1-03 — Remove unsourced attributions
- **Files:** `backend/app/api/teachings.py` (~60–141, `CURATED_FALLBACK_TIPS`); `src/lib/healingCourses.ts` (~59, "Sri Krishnaji says…"); `src/components/chat/DeepenAndTuneBar.tsx` (attributions).
- **Existing:** Teacher-attributed quotations with no video id or timestamp.
- **Change:** For each string, either (a) replace it with a verbatim span from the store, with `{video_id, start_ms, end_ms}`, or (b) relabel it as an assistant paraphrase without a teacher name. Add a lint (frontend and backend) that flags `Sri (Krishnaji|Preethaji) (says|said|teaches)` literals outside the registry and test fixtures.
- **Tests:** Lint test; snapshot of the teachings endpoint shows no unsourced attribution.
- **Acceptance:** The lint passes. Every remaining attribution has a span id.
- **Evidence:** `11` GURU-012.

## T1-05 — Fail closed on the teaching route
- **Files and symbols:** `backend/app/pipeline/stages/first_person_bridge.py` (~573–583, bridge-disabled branch); `backend/rag/pipeline_registry.py` (~65–76, registry dispatch when the flag is off); `backend/rag/nodes/first_person.py` (~52–65, exception handler); `backend/app/pipeline/stages/graph_stage.py` (~211–220, classifier-failure branch); `backend/rag/nodes/generation.py` (`generate_answer`, ~3203, entry guard).
- **Existing:** (a) **Kill switch (ADV-03, the main path):** when `FIRST_PERSON_CHAT_BRIDGE_ENABLED=false`, teaching questions go to the generating "warm Guru" prompt. An operator who turns first person off during an incident gets LLM-written teaching prose. (b) Narrow node faults (missing pipeline context, import failure, error while abstaining) fall through to the generating graph (SYS-001). The bridge already catches its own exceptions (`first_person_bridge.py:585-596,616-627`); keep that.
- **Change:** (1) Introduce one predicate, `teaching_generation_allowed()`, true only when `FIRST_PERSON_LLM_FALLBACK_ENABLED=true` is set deliberately. (2) When the bridge is off and the predicate is false, teaching-lane turns return the static abstain with `verification={"passed": False, "method": "fp_disabled", "citations_verified": False}`. Crisis, greeting, practice and boundary lanes are unchanged. (3) Node faults return the same abstain with `method: "fp_node_error"` and increment a metric. (4) `generate_answer` returns early with the abstain if it is reached for a teaching intent while the predicate is false.
- **Non-goals:** Removing the graph (T7-06).
- **Tests:** Fault injection: patch the FP pipeline to raise; assert the response has no generated text, `route_decision` is abstain, and the metric increments.
- **Acceptance:** `integrity_breach_count` stays 0 in the PR suite.
- **Risk:** More abstains during faults. Intended.
- **Rollback:** Flag `FP_FAIL_CLOSED_ENABLED` (default true).
- **Evidence:** `05` §SYS-001; `08` §RET-09; independent check `26` §2.

## T1-07 — Spend cap and scorer model required
- **Files:** `backend/app/config.py` (~645–647 budget guard fields; ~478 `first_person_relevance_model`); `backend/Dockerfile.railway`; `scripts/deploy/deploy_railway.sh`; `backend/.env.example` (~195).
- **Existing:** Budget guard off and not fail-closed by default. The scorer model is blank in the example and falls back to the generation model.
- **Change:** Default `openrouter_budget_guard_enabled=True` and fail-closed=True. A production validator requires daily and monthly caps and a non-empty scorer model. The deploy script sets them explicitly.
- **Tests:** Settings validator tests for production with and without values.
- **Acceptance:** A production boot without caps fails with a clear error.
- **Evidence:** `15` SYS-004; `09` AI-007.

## T1-08 — Protect `/api/first-person/query` and video streaming
- **Files:** `backend/app/api/first_person.py` (~297–301 route; rate limit `config.py` ~1191); `backend/app/api/ingest.py` (~561 video stream route).
- **Existing:** No auth, no anonymous quota, 120 requests per minute per IP, up to 3 LLM calls per request. Video bytes are served by id.
- **Change:** Apply the same identity resolution, anonymous quota and budget check as `/api/chat` (`resolve_anon_identity`, anon quota service), or restrict the route to admins (owner decision D-07). Serve video only for ids whose rights status is servable; otherwise 403.
- **Tests:** Anonymous request beyond quota → 429. Unlicensed id → 403.
- **Evidence:** `14` SEC-001, SEC-002.

## T1-10 — Consent gate on emotional side effects; no engagement prompts on safety turns
- **Files:** `backend/app/orchestrator_utils.py` (~577–610 healing-course assignment; ~636–705 proactive Serene Mind); `src/components/common/PushPermissionPrompt.tsx` (~31–37); `src/components/chat/ChatInterface.tsx` (~1548, ~1941 event dispatch).
- **Existing:** Episodic emotional arcs are read and an assignment is written without checking active consent. The push prompt opens 4 s after any non-blocked answer.
- **Change:** Check the active consent receipt and an explicit opt-in before reading arcs or writing assignments. Dispatch the push event only when `route_decision` is a grounded teaching answer and no safety notice is present.
- **Tests:** Unit tests for no-consent and no-opt-in. Frontend test: a safety-route answer does not trigger the prompt.
- **Evidence:** `12` MEM-003; `03` PRD-004.

## T1-11 — Release-gate hardening
- **Files:** `backend/scripts/ops/check_first_person_public_release.py` (~788–835 gold check; staging check; evaluate); `backend/config/first_person_public_release_gate.json`; tests.
- **Existing:** The gate checks file presence and one non-blank column. It accepts `independent_review:false`, an invalid commit SHA, and an AI certifier, and has no helpline check.
- **Change:** (1) Gold: load the sheets from the private store by hash (T3-09); recompute agreement and κ; fail if `independent_review` is not true, annotators are not two distinct humans, or agreement is exactly 1.0 on more than 50 items without an adjudication record. (2) Staging: `git merge-base --is-ancestor <sha> HEAD` must pass; `environment_id` must not be `local-*`. (3) Certifiers: reject ids matching `subagent|agent|bot|claude`. (4) Helplines: fail if any displayed entry has `last_verified_by_call` older than the configured age. (5) Fail if machine scopes authorise more than the human note.
- **Tests:** One fixture per rule.
- **Acceptance:** Each defect in `16` X-RC2 makes the gate fail.
- **Evidence:** `23` GURU-001 … GURU-007; `18` EVAL-001.

## T2-01 — Offline PR eval suite
- **Files:** `.github/workflows/eval-gate.yml` (~61–78 skip branch); new `evals/pr_suite/{routing.jsonl, distress_benign.jsonl, distress_crisis.jsonl, abstain_null.jsonl, voice_lint.py, quote_integrity.py}`; runner under `backend/tests/` or `backend/evaluation/`.
- **Existing:** Eval gates skip without `BACKEND_URL` and write "This PR received no live quality proof".
- **Change:** A suite that runs in-process with stubbed LLM calls where the decision is deterministic (routing pre-filter, distress regex and discriminator, quote integrity, voice lint) and records LLM-dependent items as "requires live" without passing them. It blocks merge on regression versus the committed baseline. Datasets are reviewed by humans before they become blocking (crisis set: clinician).
- **Acceptance:** The suite runs on every PR in under 10 minutes and blocks on regression.
- **Evidence:** `18` EVAL-003, EVAL-004; `14b`.

## T2-03 — Outcome telemetry
- **Files:** `backend/app/metrics.py`; `backend/app/telemetry_sink.py`; the response assembly stage; frontend feedback hooks.
- **Change:** Emit one `answer_outcome` event per turn: `request_id, lane, route_reason, served|abstained|crisis, layers[], span_ids[], verification, latency_ms by stage, llm_calls[{prompt_id@version, model, tokens_in, tokens_out, cost_usd}], cache_hit`. Join frontend signals: helpful/not, clip played (seconds), report, follow-up within 5 minutes, saved. Define `useful_answer` = served AND (helpful OR played ≥ 20 s OR saved) AND NOT reported. Dashboard: cost per useful answer, served share, integrity breaches.
- **Acceptance:** 100% of turns emit the event in tests. No seeker text in the event.
- **Evidence:** `15` SYS-011; `12b` UX-004.

## T2-04 — Golden dataset v2 and judge calibration
- **Files:** new `evals/golden_v2/` (schema in `18` §4); `backend/evaluation/gold/calibrator.py` (keep).
- **Change:** Build tooling for item authoring from real (consented) and synthetic questions, blind presentation, two independent raters, adjudication, and κ/α computation. Calibrate the LLM judge with prediction-powered inference (`18` §3). **Labels come only from humans.**
- **Acceptance:** ≥299 confident human items with independent double rating before any calibration fit (invariant 3).
- **Evidence:** `18` EVAL-002, EVAL-005.

## T3-01 — Rights register in the image; startup check
- **Files:** `backend/services/first_person_serving_contract.py` (~177–186 load); `backend/services/qdrant/indexer.py` (~55–135 rights read); `backend/Dockerfile.railway` (COPY list); `backend/app/api/health.py`.
- **Existing:** The register lives under `audits/`, which the Railway image does not copy. A missing file returns `{}`, so every clip is unlicensed and the system abstains silently.
- **Change:** Ship the register (or a DB table) inside `backend/config/`. At startup in production, fail if it is missing or empty, or if its digest differs from the serving contract. Expose the digest and count in the health payload.
- **Tests:** Boot test with missing, empty and mismatched registers.
- **Evidence:** `06` DATA-02.

## T3-02 — Qdrant write governance
- **Files:** `backend/app/config.py` (~710 `qdrant_api_key`); `backend/docker-compose.yml` (~151–160); builders.
- **Change:** Qdrant runs with API keys enabled. The backend gets a read-only key. Builders use a write key loaded from the host environment only. After a sign-off, the builder records a collection digest (count + hash of point ids and `span_text_sha256`), and the backend verifies it at startup.
- **Acceptance:** A backend write attempt fails. A digest mismatch fails startup.
- **Evidence:** `06` DATA-06 (v11 incident).

## T3-03 — Hash-field semantics
- **Files:** `backend/domain/first_person_context.py` (~166–301 `SourceSpan`); `backend/services/first_person_store.py` (~172–215); `scripts/**/build_full_corpus_v10.py` (~349–385); `backend/ingest/pipeline.py` (~3759); `backend/services/first_person_context_store.py` (~1320); frontend citation type.
- **Change:** In the vNext schema, replace `transcript_hash` with `video_transcript_sha256` and `span_text_sha256`. The integrity gate compares `sha256(verbatim_text) == span_text_sha256`. One writer contract test runs against every writer.
- **Non-goals:** Rewriting v8/v10 in place (new collection per invariant 4).
- **Evidence:** `06` DATA-03; root `CLAUDE.md` invariant 2.

## T3-04 — Builder per-video replace; snapshot before apply
- **Files:** `backend/scripts/ops/build_full_corpus_v10.py` (both tracked copies; ~867–894 skip-existing; ~1238–1298 snapshot order); `tests/test_repo_layout.py` (byte-identity).
- **Change:** For each video in the build, compute the new point set, delete stale ids for that video, upsert new ones. Take the snapshot before the first write. Refuse an empty build (keep the existing pattern from `build_first_person_index.py`).
- **Acceptance:** Rebuilding a corrected video leaves no stale point. A snapshot exists before the first write.
- **Evidence:** `06` DATA-05.

## T3-05 — Scorecard promotion gate; daily audit; approved = served
- **Files:** `scripts/ops/data_quality_audit.py` (~288–306); `fp_data_quality_scorecard.py`; new workflow; serving contract.
- **Change:** Promotion requires 0 BLOCKER fails and strict-clean ≥ the project's target (60%). A daily read-only audit compares the serving collection with its signed digest and the release record's approved corpus version.
- **Evidence:** `06` DATA-14, DATA-15, DATA-16.

## T3-06 — Source registry, takedown, structured citations
- **Files:** new migration (extend `corpus_sources`; add `transcript_versions`, `span_index`, `takedowns`, `message_citations`); new `backend/services/source_registry/`; `backend/services/first_person_video_decisions.py` (~98–104 file state; ~348–367); chat response assembly.
- **Change:** The registry becomes the authority. `takedown(source_id, reason)` removes points (Qdrant delete by filter), invalidates caches, marks citations as withdrawn, and writes an audit row with counts. Video decisions move from JSON to Postgres. Assistant messages store citations as rows `{message_id, span_id, video_id, start_ms, end_ms, verification_state}`.
- **Acceptance:** A takedown test on a fixture source clears every store and reports counts.
- **Evidence:** `06` DATA-07, DATA-12, DATA-18.

## T3-09 — Private evidence store and source bundle (human + agent)
- **Change:** Per ADR-008. The bundle holds audio (where rights allow), transcripts per version, and checksums. Builders read only from the bundle. The evidence store holds annotator sheets, sign-offs and approvals; the repo references them by sha256.
- **Evidence:** `06` DATA-01, DATA-09; `23` GURU-005.

## T3-10 — Backups and restore drills
- **Files:** `infrastructure/cron/mukthiguru-backup`; `.github/workflows/backup.yml`.
- **Change:** Nightly encrypted off-host backups for Postgres and Qdrant snapshots, and a second copy of the audio archive. Monthly restore drill into a scratch environment with a query check.
- **Acceptance:** One passed drill per store, recorded.
- **Evidence:** `15` SYS-012; `01` §8.4.

## T4-01 — Gate first, then dedup
- **Files:** `backend/services/first_person_store.py` (~730–735 per-video dedup); `backend/services/first_person_pipeline.py` (~4747 gate application).
- **Change:** Apply integrity, content and length gates to all retrieved candidates first. Then dedup per video, keeping the best surviving candidate.
- **Tests:** A fixture where the top clip of a video fails a gate and a lower clip passes. Assert that the passing clip is served.
- **Acceptance:** Frozen bank served share ≥ baseline.
- **Evidence:** `08` RET-01.

## T4-02 — Hybrid retrieval in v10
- **Files:** `backend/services/first_person_context_store.py` (~429–602 search).
- **Change:** Use Qdrant `query_points` with two prefetches (`passage_dense`, `passage_sparse`), `FusionQuery(RRF)`, and parent grouping. Keep the payload filters (rights, servable, teacher).
- **Tests:** A fixture collection where a keyword-only match must be found.
- **Acceptance:** Frozen bank Recall@10 ≥ dense-only.
- **Evidence:** `08` RET-02; root `CLAUDE.md` invariant 5.

## T4-03 — Single route-decision service
- **Files:** `backend/app/pipeline/stages/off_topic_stage.py` (~57–67 `_ON_TOPIC_RE`; ~645–680 general routing); `backend/rag/pipeline_registry.py` (~75–100); `backend/services/first_person_pipeline.py` (~1329 answerability scope).
- **Change:** New module `backend/services/routing/route_decision.py` with one scope file (`backend/config/teaching_scope.yaml`, new file). It returns `{lane, reason_code, confidence}`. The pipeline order is: crisis and greeting pre-filters → embedding similarity to scope exemplars → small LLM classifier only when ambiguous. All three existing call sites use it. The general lane follows ADR-002.
- **Acceptance:** Teaching-intent routing recall ≥95% on the routing set; no regression on crisis routing.
- **Evidence:** `09` AI-001; `10` ANS-003; `05` SYS-002.

## T4-04 — Distress topic versus state (clinician gate)
- **Files:** `backend/services/serene_mind_engine.py` (~368 MODERATE pattern; ~1696–1709 MILD→MODERATE upgrade; ~1810–1826 history escalation); `backend/app/pipeline/stages/distress_stage.py`; `backend/app/pipeline/stages/first_person_bridge.py` (~682 `_DISTRESS_DECLINE_LEVEL`).
- **Change:** (1) Add a state discriminator: first-person present-tense disclosure ("I am anxious", "I can't stop panicking") versus topic inquiry ("what causes anxiety"). (2) Remove the unconditional MILD→MODERATE upgrade. (3) History escalation counts state disclosures only. (4) The bridge declines only on state ≥ MODERATE. Topic questions get the teaching plus a gentle care footer. (5) Keep crisis (SEVERE+) unchanged and fail toward care when ambiguous.
- **Non-goals:** Turning on LLM escalation or downgrade without validation.
- **Tests:** The benign set (≥200, reviewed), the crisis core set (clinician), and the multi-turn set (≥50 dialogues).
- **Acceptance:** Benign overfire ≤5%; crisis recall 100% on the core set; 0 benign multi-turn SEVERE. **Clinician written sign-off before the production config changes.**
- **Evidence:** `10` ANS-001/002; `14b` SAFE-001…003.

## T4-06 — Evidence-judge consolidation
- **Files:** `backend/services/first_person_pipeline.py` (~4960–4975 LLM rerank; ~5118–5180 relevance; ~785–1110 prompts; answerability gate); `backend/rag/nodes/reranking.py`.
- **Change:** Use the ONNX cross-encoder pre-rank (if the frozen bank shows no loss), then one structured LLM call on the top N (≤5) returning `[{id, relevance_0_3, answers_question: bool, reason}]`. It replaces the rerank, relevance and answerability calls. On scorer failure, abstain as `relevance_indeterminate` (keep invariant 24).
- **Acceptance:** ≤2 LLM calls per in-domain turn. Frozen-bank quality is non-inferior. Out-of-corpus abstention is 100% on the null set.
- **Evidence:** `08` RET-10; `05` SYS-006; ADR-009.

## T4-07 — Verified helplines only
- **Files:** `config/helplines.yaml`; `backend/rag/meditation.py` (~117–138); `backend/services/crisis_helplines.py`.
- **Change:** Display only entries with `last_verified_by_call` within the configured age. Always keep one verified national line (Tele-MANAS today). **Calls are human work; never test-call 112.**
- **Evidence:** `14b` SAFE-004.

## T5-02 — Per-facet retrieval and evidence sets
- **Files:** `backend/services/facet_planner.py`; `backend/services/set_selector.py` (new files; implemented later as `backend/services/first_person_facet_planner.py` and `backend/services/first_person_set_selector.py`); `backend/services/first_person_pipeline.py` (~5684–5690, ~5817–5822 compound path); `scripts/**/build_teaching_unit_graph.py` (~157–161 `rights_status` → `domain_rights_status`; ~425 default collection).
- **Change:** Embed and retrieve each facet separately. The selector maximises facet coverage and video diversity, removes contained or duplicate spans, and keeps each teacher's spans labelled separately. Remove the `IS_PRODUCTION=false` condition on the selector once it is measured.
- **Evidence:** `08` RET-03, RET-04, RET-06; `07` §4.

## T5-03 — Layered composer (ADR-001; owner decision required)
- **Files:** new `backend/services/answer_composer/`; `backend/app/pipeline/stages/first_person_bridge.py` (~930–948 assembly); response schema (`backend/schemas/`); `src/components/chat/ChatMessage.tsx`; `CitationCard.tsx`; `src/pages/TeacherWords.tsx` (consolidate).
- **Change:** Response contract `layers: [{type: "verbatim"|"context"|"explanation"|"personal"|"reflection"|"follow_up", text, span_ids[], voice: "teacher"|"assistant"}]`. Only `verbatim` may have `voice: "teacher"`, and its text is copied from the store by span id. The UI renders the assistant layers under an "In our own words" label and the verbatim layers as quotes with a play button.
- **Acceptance:** Voice lint: 0 teacher-voice assistant sentences. All verbatim layers pass exact-substring. Flag off = today's behaviour.
- **Evidence:** `10` ANS-004, §5; `17` ADR-001.

## T5-04 — Verifier
- **Change:** (1) Quote check: exact substring of the stored span text. (2) Every L3 sentence must cite ≥1 span id; NLI entailment (`services/lettuce_detect_service.py`, floor as configured) against the cited spans; unsupported sentences are dropped, and if the explanation loses >50% of its sentences, it is dropped entirely. (3) Attribution: the speaker of each cited span matches the label. (4) Fence untrusted text in all prompts.
- **Evidence:** `14b` SAFE-008; `09`.

## T6-04 — Save, report, revisit
- **Files:** `src/components/chat/CitationCard.tsx`; `backend/app/api/feedback.py` (~336 clip-report endpoint); new saved-answers API and table.
- **Change:** Add a "Report this clip" control (reasons: wrong teacher, wrong topic, cut mid-thought, other) wired to the existing endpoint. Add "Save" for an answer, with collections. Saved items reference `message_citations` rows, so takedowns propagate.
- **Evidence:** `03` PRD-006, FR-SAVE-01, FR-CORR-01.

## T7-02 — Async teaching lane
- **Files:** `first_person_pipeline.py` (~1417–1445 `run_llm_coroutine`); `first_person_bridge.py` (~850 `asyncio.to_thread`); `backend/app/api/first_person.py`; `backend/start_railway.py` (~55–63 watchdog); `tasks/memory_outbox_tasks.py` (~264 `asyncio.run`).
- **Change:** After T7-01, make the step functions `async`, await the gateway directly, and remove the thread hop and the watchdog. Celery workers use one event loop per process.
- **Acceptance:** A staging c20 load test shows no executor starvation, and the p95 is recorded.
- **Evidence:** `05` SYS-003.

## T9-01 — Railway IaC and staging
- **Files:** `.railway/railway.ts`; `.railwayignore` (it ignores `*.ts`, which may hide the IaC file; verify); `backend/Dockerfile.railway`; `scripts/deploy/deploy_railway.sh`.
- **Change:** Declare backend, worker, beat and Redis (and Qdrant if self-hosted) per environment. Staging first. Env-var names only in the repo. Health check `/api/health`. `FORWARDED_ALLOW_IPS=10.0.0.0/8`, `PYTHON_MEMORY_LIMIT_MB=0` [DOC-CLAIM root `CLAUDE.md` Gotchas].
- **Acceptance:** A staging deploy from `main` is reproducible; the runbook in `22b` passes.
- **Evidence:** `15` SYS-007; `22b`.

## T9-02 — Smoke, cross-browser, real-model load
- **Files:** `tests/e2e/*`; `playwright.config.ts`; `backend/scripts/ops/gate1_load_test.py`.
- **Change:** Fix the failing Firefox, WebKit and Mobile Safari specs (artifacts in `01` §10). Run the load test with real models at concurrency 20 on staging. Record p50/p95/p99 and the error rate.
- **Evidence:** `01` §10; `15` SYS-008.

## T9-03 — Alerting and SLOs
- **Change:** Alerts on: integrity breach > 0; crisis-lane error; spend at 80% of the cap; p95 above the provisional target for 15 minutes; 5xx rate > 1% for 10 minutes; the daily data audit failing. Route them to the owner's channel. Write an on-call runbook.
- **Evidence:** `15`; `04` NFRs.

---

## Added after the independent review (`26`)

## T1-12 — Replace the deletion funnel (P1)
- **Files and symbols:** `src/pages/ProfilePage.tsx` (~583); `src/components/**/AccountDataCard.tsx` (~140–195); `src/components/**/CancelFlow.tsx` (~86–106, ~180–197); `backend/app/api/cancel_flow.py` (~299–732; queueing ~433–515); `backend/tasks/cancel_flow_tasks.py` (~24–75); `backend/celery_config.py` (beat entry); `supabase/functions/delete-my-account/index.ts`; locale keys for streak copy (`mood.streakRooting`), `StreakMilestoneCard.tsx` (~24).
- **Existing:** The cancellation funnel (exit survey, save offers, "keep 30/90 days") is mounted and is the **only** UI path to account deletion. Four win-back emails are queued for every retention choice. Scheduled deletions never run (no purge job, ADV-01).
- **Change:** (1) Add a direct flow in `AccountDataCard`: explain what is deleted, offer data export, require typed confirmation, call `delete-my-account`, and show the result. (2) Remove the save offers and the win-back emails, the beat task and the email templates. (3) Remove the "keep 30/90 days" options unless T6-06 ships a working purge job in the same release. (4) Make streak copy neutral and opt-in; never tie usage to spiritual progress.
- **Non-goals:** Changing what the edge function deletes (T6-06 owns erasure completeness).
- **Tests:** e2e: a signed-in test user deletes the account from the profile page; no email is queued; the user's rows are gone. Unit tests: no beat schedule entry for win-back.
- **Acceptance:** Deletion takes ≤3 screens with no persuasion step. No cancellation email is sent.
- **Risk:** Removing the funnel before the new flow works would remove deletion from the UI. Ship the new path first.
- **Rollback:** Revert the PR; the edge function is unchanged.
- **Evidence:** `12b` UX-001 (with erratum); `26` §2 claim 12, ADV-01.

## T6-06 — Erasure completeness and scheduled purge (P1)
- **Files:** `supabase/functions/delete-my-account/index.ts` (~48–62, backend purge call); `router_decisions` migration (no user column); admin foreign keys; `backend/app/api/memory.py` erasure routes; `scheduled_deletion` rows (migration `20260715020000`); new purge job (Celery beat or Supabase scheduled function).
- **Existing:** The edge function fails closed when the backend purge fails, so deletion is impossible while the backend is down. `router_decisions` stores query text with no user column, so it cannot be erased per user. Scheduled deletions are recorded and never executed.
- **Change:** (1) Queue erasure durably: the edge function writes an erasure request, and the request completes asynchronously with retries; the user sees "deletion in progress" with a deadline. (2) Add a user key (or a hash of it) to `router_decisions`, or stop storing query text there. (3) Fix the admin FKs that block deletion (`ON DELETE CASCADE` or nulling, per the DPDP invariant in root `CLAUDE.md`). (4) Add a purge job that executes due scheduled deletions daily, with a metric and an alert on backlog.
- **Tests:** Erasure drill with the backend stopped: the request queues and completes after restart. Purge job test with a due row. Per-user `router_decisions` erasure test.
- **Acceptance:** Every erasure request completes within 72 h (NFR-PRIV-02). No due scheduled deletion older than 24 h.
- **Evidence:** `14` SEC-004; `26` ADV-01.

## Added after the journey walkthrough (`14d`)

## T1-17 — Client safety fallback on every error (P1)
- **Files:** `src/lib/chat/errors.ts` (~79–97, error-to-card mapping); the chat error cards under `src/components/chat/`; a static list of call-verified helplines generated from `config/helplines.yaml` at build time.
- **Existing:** Only the 503 error card carries a support line. A 500, a network drop, a timeout or a 429 shows a generic card. Developer text such as "Set VITE_BACKEND_URL" can reach seekers. A seeker who writes a crisis message during a backend fault sees nothing protective.
- **Change:** Every error card shows a short care line with at least one call-verified helpline (Tele-MANAS today) and a retry. Map developer-facing errors to seeker-safe copy. The helpline list ships with the bundle, so the fallback works when the backend is down.
- **Non-goals:** Client-side crisis classification (server-side safety stays authoritative).
- **Tests:** e2e for 500, network drop, client timeout and 429: each renders the support line; no developer string appears.
- **Acceptance:** NFR-SAFE-05 plus "support line on every error state" passes in the e2e matrix.
- **Evidence:** `14d` UX-007.

## T6-09 — Account-level conversation history (P1)
- **Files:** `src/lib/chatStorage.ts` (~22–39 cap; ~302–309; ~396–445 one-way cloud sync; ~590–603 wipe); `src/components/**/UserMenu.tsx` (~131–137 sign-out); `SessionExpiredHandler.tsx` (~41–50, ~88–92); conversation list/read/delete API (backend, after T6-05).
- **Existing:** For signed-in users, history lives in one browser's local storage, capped at 10, and is wiped on every sign-out or session expiry. The cloud copy is written but never read back. Server-held conversations cannot be listed or deleted one by one. `setRetentionDays` has no caller.
- **Change:** Signed-in history reads from the server (paginated list, open, delete one, delete all). Local storage becomes a cache. Sign-out clears the cache but not the account history, and the UI says so. Wire the retention setting to a server-side retention job, or remove it. Anonymous users keep local-only history with a clear notice.
- **Dependencies:** T6-05 (the backend writes assistant turns; client RLS `role='user'`).
- **Tests:** e2e: create conversations, sign out, sign in on a second browser, see them; delete one; confirm it is gone on both. RLS tests for list and delete.
- **Acceptance:** History survives sign-out and device change; per-conversation delete works; the retention setting has an effect or does not exist.
- **Evidence:** `14d` UX-006; `03` erratum 5.
