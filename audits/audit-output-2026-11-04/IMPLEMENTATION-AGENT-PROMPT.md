# Implementation-agent prompt (copy everything below the line into a fresh coding session)

---

You are the implementation agent for **Ask Mukti Guru** (repository `Harshodai/askmukthiguru-8119b0e8`). An independent architecture and product audit was completed on 2026-11-04 against `origin/main@46b808fb`. Your job is to implement its roadmap correctly, safely and verifiably, one small PR at a time, until every task you are unblocked to do is complete. This prompt carries the essential context. The full audit package (`audits/audit-output-2026-11-04/`; every `audit-output/` path below means this folder) holds the evidence. Read the named files when you need detail.

## 0. Work already done (branch `feature/audit-strengthen-rag-qdrant`, commits after `c7befa3d`, head `5a9501ac` plus this docs commit)

These tasks are implemented. Verify them in CI and do not redo them. Re-check each against its spec before building on it.

| Task | What landed | Verified | Follow-up left for you |
|---|---|---|---|
| T0-04 | Release-gate repo test asserts the computed status (`OWNER_ACTION_REQUIRED`) | Gate test file 34/37 in a minimal venv (3 need full conftest); CI pending | — |
| T1-01 | Root `CLAUDE.md` voice section replaced by "Voice Governance & Invariants"; `test_voice_governance_docs.py` | 75 tests passed (with quote-weaver and voice tests) | — |
| T1-02 | Quote-weaver editorial/hybrid LLM paths, ingestion FP dual-index writer, `REFERENCE_VOICE` and their flags removed | 289 passed, 2 skipped (bridge, wiring, stale flags, repo layout, config) | `first_person_mode="hybrid"` is still accepted and behaves like `retrieval_only`; remove it in a separate PR. `QuoteWeaverAssertionGate` and `_run_sync` have no production caller. Exact-cache fingerprint changed (one-time cache miss). |
| T1-05 | `services/fp_fail_closed.py`: `teaching_generation_allowed()`; bridge off → abstain `fp_disabled`; node fault → `fp_node_error` + `guru_fp_fail_closed_total`; `generate_answer` guard; rollback flag `FP_FAIL_CLOSED_ENABLED` (default true) | `test_fp_fail_closed.py` and bridge/wiring tests passed in the integrated branch (298 passed) | Classifier-failure branch in `graph_stage.py` (~211–220) still routes to the general boundary lane; a node call with no pipeline context still reaches the general graph except where `generate_answer` catches a teaching intent. |
| T1-06 | `_maybe_apply_langhanam_voice` skips register blocks in general mode | `test_general_mode_no_register.py` passed | — |
| T1-07 | Budget guard and fail-closed default on; production validator; `ALLOW_UNCAPPED_LLM_SPEND` escape (default false) | Spend tests passed | Production now refuses to start with the guard off unless the escape is set. Scorer model and timeout remain owner decisions (D-16). |
| T1-09 | Prerouter and follow-up resolver log length + sha256 prefix; ratchet budget 26 → 19 | Ratchet test passed | — |
| T1-10 | Backend: `has_active_memory_consent()` gates emotional-arc reads, course assignment and the proactive Serene Mind trend. Frontend: push prompt only after a grounded `first_person_bridge` answer with no safety signals | Consent tests 10 passed after a test fix (they had been running as anonymous); frontend vitest passed | Frontend `TEACHING_ROUTES` allowlist is strict; add routes deliberately. Default on/off flags unchanged (D-21). |
| T1-11 | Gate rejects non-independent gold, agreement 1.0 over >50 items without adjudication, non-ancestor SHAs, `local*` environments, agent-like certifiers, unverified helplines (365-day age), scopes that exceed the notes; one fixture per rule | Gate fixtures passed (minimal venv); real repo still `OWNER_ACTION_REQUIRED` with 5 failing checks | The gate now needs `git` on PATH and lazy-imports PyYAML. |
| T1-16 | Absolute API URLs (5 sites, one found by the new ESLint rule); WhatsApp button hidden unless a `whatsapp` capability and number exist | Lint 0 errors; vitest passed; build passed | ESLint regex `^.api.` also matches a few lookalike paths. |
| T1-17 | Every chat error card shows a care line with call-verified helplines (Tele-MANAS) and a retry; developer text to console only; vitest ties the constant to `config/helplines.yaml` | vitest passed | No e2e for 500/drop/timeout/429 yet; the care line uses a `t()` default with no `en.json` key (i18n sync needs an API key). Fold into T1-20. |
| T1-19 | Client summary call to `/api/chat` removed | vitest passed | Local last-5-messages fallback still stored in `conv.summary`; `updateConversationSummary` is now unused (clean up). |
| T3-01 | Both backend Dockerfiles copy the pinned rights register; production startup fails if it is missing or empty; health shows `rights_register` (count, sha256 prefix) | `test_rights_register_startup.py` passed in the integrated run | No digest-versus-serving-contract check (the contract has no digest field yet). Docker build not run. |

Everything else in section 6 is still open. Owner-gated items are listed in section 5.

### 0b. Second batch (P2/P3), head `0fc474dd`

| Item | What landed | Verified | Left |
|---|---|---|---|
| SEC-008 + SEC-010 (T1-14 part) | Production startup rejects a bare `*` CORS origin (scoped patterns still allowed). `/api/health` and `/api/health/services` return only `{ready, status}` unless the caller sends the `METRICS_SCRAPE_TOKEN` bearer | 12 tests passed (`test_health`, `test_health_hard_bound`, `test_main_cors`) | Railway and Docker health probes still get the short form; check they only read the status code |
| SEC-006 (T1-14 part) | Qdrant, Redis, Memgraph and gptcache host ports bound to `127.0.0.1` in `backend/docker-compose.yml`; test asserts no datastore port on all interfaces | 2 passed | Qdrant API keys (T3-02) and image pinning not done |
| CQ-013 (T1-13 part) | `compliance.py` `_get_container_safely` is async | 14 passed | Root shim packages and the `langdetect` stub (CQ-005) not removed |
| MEM-005 + SAFE-008 | Client conversation summary and relevance-scorer clip text are fenced as untrusted data | 98 passed | — |
| ADV-05 (T5-06 part) | Quote-translation popover labelled "Machine translation — not the teacher's words" (i18n default; no `en.json` key yet) | 18 vitest passed | Add the key to all 14 locales with native review (T1-20) |
| SEC-009 | **Skipped**: `mint_jwt` has no runtime caller, but `tests/test_whatsapp_bot_integration.py` patches `wa_bot.JWT_SECRET` | — | Remove both together |

### 0c. CI state and review concerns (2026-11-04)

- CI on `0a80eb36` (first batch): Backend regression gates **5 failed, 12,485 passed, 52 skipped**. "Lint & Test" also failed. At least one failure is a T1-05 behaviour change: a test now receives `route_metadata.decision_method = "fp_node_error"` with `selected_variant = "no_match_abstain"`. Decide per test whether the new fail-closed behaviour is intended (update the test with a T1-05 comment) or a bug. The second batch (`0fc474dd`) has not been through CI yet. The owner is fixing CI.
- CI on `73d49814` (second batch, observed 2026-11-04): Backend regression gates 15 failed, 12,480 passed, 52 skipped. All 15 were intended behaviour changes: 10 in `test_health_falsifiability.py` (SEC-010 shallow health body without the scrape token) and 5 in `test_pipeline_registry.py` (T1-05 fail-closed claims the turn). Both test files were updated with task-ID comments. "Backend Lint & Test" failed only on `ruff format --check` (12 files; `ruff check` clean) and "Validate Pre-commit Hooks" on trailing whitespace in `FlashcardPractice.tsx` and end-of-file newlines in two test files; all fixed. The result of the follow-up CI run is not yet observed.
- Read-only guardrail review (Haiku) found no guardrail violation. Concerns to resolve: (1) the rights register now copied into both backend images contains the owner's local `/Users/...` paths (lines ~18786–18787): scrub them before the next image build; (2) the root `CLAUDE.md` voice section was rewritten (T1-01) and needs the owner's sign-off; (3) proactive Serene Mind now requires memory consent (intended, MEM-003); (4) more abstains when the bridge is off (intended, T1-05); (5) production startup now needs the spend guard on (or `ALLOW_UNCAPPED_LLM_SPEND=true`) and the rights register present.

### 0d. What remains to fully complete (register)

| Who can do it | Tasks still open |
|---|---|
| **Agent, no decision needed** (do these next, in this order) | T2-05 fixture-store CI → T2-03 outcome telemetry → T2-01 PR eval suite harness (crisis set non-blocking until clinician review) → T2-02 retrieval-bank harness → T2-06 config lint → T3-12 encoder fingerprint → T3-02 Qdrant read-only/write keys (code) → T3-04 builder per-video replace → T3-08 schema snapshot CI → T3-05 promotion gate + daily audit → T3-03 hash rename in vNext (code only) → T3-06 source registry + takedown + structured citations (migration written, not applied) → T4-01 gate-then-dedup → T4-02 hybrid RRF on v10 → T4-05 DISTRESS direct route (routing only, no classifier change) → T4-06 evidence-judge consolidation (after T7-01) → T1-18 stream contract → T6-05 client RLS `role='user'` → T6-09 account history → T6-06 durable erasure + purge job → T6-04 save/report/revisit → T6-02 memory on the teaching lane → T6-03 remaining (replace L3 persona) → T6-10 honest copy → T7-01 split → T7-02 async → T7-03 LLM gateway → T7-04 caches → T7-05 ratchets → T8-01/T8-02 teacher registry → T1-13 rest (shims, `langdetect` stub, WA signer + its test) → T1-14 rest (Qdrant keys in compose, verified image pins) → T1-15 documentation diet → T1-19 cleanup (`updateConversationSummary` now unused) → scrub `/Users/` paths from the shipped rights register |
| **Owner decision first** | T0-01/T0-02 (D-01, D-02 public exposure), T0-03 branch protection, T0-04 scopes (D-11), T0-07 (D-24), T1-04 personas (D-20), T1-08 FP endpoint (D-07), T1-12 deletion funnel (D-19), T3-09/T3-10 storage and backups (D-08), T3-11 graph stack (D-05), T4-03 general lane (D-04), all of P5 (D-03), T7-06 (D-04), scorer model and timeout (D-16), sign-off on the T1-01 `CLAUDE.md` rewrite |
| **Clinician or native speakers** | T4-04 distress topic-vs-state, T6-07 dependency guard, crisis items in T2-01 becoming blocking, T1-20 translations, T5-06 labelled translations |
| **Live infrastructure** (owner present) | T9-01 staging, T9-02 smoke and load, T9-03 alerts, T9-04 Qdrant/Railway runbooks, applying any migration, running builders, T4-07 helpline calls (never test-call 112) |
| **Human-only** | T2-04 independent gold labels (≥299), T2-07 user study, T10-02 gates, T10-01 review package, T10-03 scorecard |


### 0e. Third batch

| Item | What landed | Verified | Left |
|---|---|---|---|
| CI repair | `ruff format` on 12 files; trailing whitespace fix; health and registry tests updated to SEC-010 and T1-05 behaviour | Local: 160 passed (formatted files), 38 passed (health and registry), pre-commit whitespace and EOF hooks pass on all 120 changed files | Confirm the next CI run is green |
| T1-03 | Fallback wisdom tips are unattributed paraphrases (no teacher, source `paraphrase`); healing-course prompts and concept bar no longer attribute wording to a teacher; new test blocks `Sri X says/said/teaches` literals | Backend 7 passed; vitest DeepenAndTuneBar 5 passed; eslint clean | Admin-curated tips still default the teacher to the founders pair (admin-entered, no locator check); harvested tips use their stored source URL |
| SEC-009 | Removed `mint_jwt`, `JWT_SECRET`, the PyJWT dependency, the signer test and README mentions in `whatsapp_bot` | `test_whatsapp_bot_integration.py` 19 passed | — |
| T1-19 cleanup | Removed unused `updateConversationSummary` and its mocks | tsc and eslint clean; vitest `src/test` 142 files, 943 tests passed | Local last-5-messages fallback still stored in `conv.summary` |
| Rights register paths | **Skipped.** The file's sha256 is pinned in `backend/config/first_person_public_release_gate.json`, `backend/config/first_person_local_review.json` and `scripts/guards/publication_baseline.txt` | — | Owner decision: re-pin all three digests together with the path scrub, then rebuild images |


## 1. What the product is

- A privacy-first spiritual guide grounded in the recorded teachings of **Sri Krishnaji** and **Sri Preethaji**.
- A seeker asks a question. The system answers with the teachers' **own recorded words**: a clip from a video, a padded playback window (start −0.25 s, end +0.25 s), and the verbatim transcript text. Otherwise it abstains honestly. Crisis turns get verified helplines and care.
- Stack:
  - Frontend: React + Vite + TypeScript (`src/`, Capacitor shells).
  - Backend: FastAPI (`backend/app/`) and a LangGraph RAG (`backend/rag/`).
  - Data: Qdrant (teaching spans with named dense + sparse vectors), Supabase Postgres + Auth (139 migrations, RLS), Redis.
  - Workers: Celery worker + beat.
  - LLMs: OpenRouter.
  - Memgraph and LightRAG exist but are off the serving path.
- Chat flow at code defaults: the request goes through 19 stages (`app/pipeline/stages/pipeline_builder.py`; the order in root `CLAUDE.md` is stale), then the LangGraph `GraphStage`, then the registry module `first_person` → `FirstPersonPipeline`. That pipeline is the legacy v8 engine by default; the v10 harness runs only when both harness flags are true. The bridge then returns one verbatim clip (+1 optional clip from another video) or a static abstain. In-domain turns make 3 LLM calls (rerank, answerability, relevance scorer). None writes answer text.

## 2. The state you inherit (facts, 2026-11-04)

- `main` is **red**: one backend test fails (`tests/test_first_person_public_release_gate.py`, ~line 924). On a clean checkout the release gate reports `OWNER_ACTION_REQUIRED`, but the test was edited to expect READY. Cross-browser e2e (Firefox, WebKit, Mobile Safari) fails in "Pre-launch gate".
- `main` has **no branch protection**. Recent large changes landed before CI finished, or without a PR.
- The repository is **public**. It contains 2,737 verbatim teaching spans (`audits/evidence/public_release_v10_points_export_2026-10-21.json`), tier JSONLs with transcript text and `/Users/...` paths, 1,546 OKF teaching files, `data/*.json` corpus and graph backups, and `public/audio/meditation/preethaji-serene-mind.mp3` (teacher voice audio extracted from YouTube, with no rights record).
- Never deployed since August. No staging. The OpenRouter spend cap is **off by default** (`config.py` ~645–647; its comment wrongly says "Default enabled"). `/api/first-person/query` has **no auth and no anon quota** (~297–301) and can spend up to 3 LLM calls per request.
- The rights register lives under `audits/` and is **not copied into the Railway image**. A missing register makes every clip unlicensed, so a deploy would abstain on everything, silently.
- **"What is the cause of my anxiety?"** matches the MODERATE distress regex (`services/serene_mind_engine.py` ~368). The bridge declines (`first_person_bridge.py` ~682), and the seeker gets a meditation template and helplines, not a teaching. Every MILD match is upgraded to MODERATE (~1698–1703). Two MODERATE keywords in recent turns escalate to SEVERE crisis pre-emption (~1810–1826). Only 1 of 15 helplines is call-verified.
- **Kill switch fails open:** turning `FIRST_PERSON_CHAT_BRIDGE_ENABLED` off sends teaching questions to the generating "warm Guru" prompt (`first_person_bridge.py` ~573–583; `pipeline_registry.py` ~65–76; `generation.py` ~3203).
- Account deletion in the UI goes **only** through a churn funnel (`ProfilePage.tsx` ~583 → `AccountDataCard.tsx` ~140–195 → `CancelFlow`), which queues four win-back emails. "Keep 30/90 days" deletions **never execute** (no purge job). Deletion is impossible while the backend is down.
- Memory: 7+ overlapping planes. Memory is read on the teaching lane and never used. Healing-course assignment reads emotional history **without the consent check** (`orchestrator_utils.py` ~575–610 skips ~893–919).
- Data: `transcript_hash` has three meanings across writers (on v10 the integrity field is `source_text_hash`). The v10 builder is add-only and snapshots after writing. Qdrant has no API key, and another writer once re-marked 17 demoted spans as verified. There is no cross-store takedown. v10 fails its own data scorecard (13/26; 39.9% strict clean; a repository claim).
- Retrieval: v10 search is dense-only (breaks invariant 5). On v8, per-video dedup runs before the integrity gates.
- Evaluation: there are no independent human gold labels. The 303-row "gold" reports say `independent_review:false`; tracked packets have 0/300 judgments. CI eval gates skip without a deployment. The admin `eval-run` edge function judges Gemini answers with Gemini.
- Undocumented processors receive user data: the Lovable AI gateway (Supabase `memory-extract` functions), Sarvam STT, Sentry replays, SMTP and web push.
- Frontend journey (`audit-output/14d`): signed-in history lives in one browser, capped at 10, and is wiped on sign-out (the cloud copy is never read back). Only the 503 error card shows a helpline. The backend sends `final` before `done`, so a cut stream leaves teacher text without citation, label or safety notices. 33 of 234 chat strings are missing in every non-English locale. The client "summary" posts "Summarize our conversation so far." to `/api/chat`. Landing copy promises an "AI companion".
- Docs drift: root `CLAUDE.md` is stale in several places. Its "First-Person Voice Architecture" section orders teacher first-person delivery. **That section is wrong**: the code's `GURU_SYSTEM_PROMPT` forbids it, and so do you.

## 3. Root causes (fix these, not symptoms)

| RC | Cause |
|---|---|
| RC-1 | No single source of truth: scope ×3, teacher registries ×7, ~14 LLM modules, ≥8 caches, 679 settings |
| RC-2 | Status is typed, not computed |
| RC-3 | Three products in one code path: generative RAG, verbatim clips, general assistant |
| RC-4 | Data identity and lifecycle are ungoverned |
| RC-5 | Safety confuses a topic with a state |
| RC-6 | The answer model is "one clip or abstain" |
| RC-7 | Rights are statements, and the repository is public |
| RC-8 | `main` is unprotected; giant PRs; docs used as memory |
| RC-9 | Operations never exercised |

## 4. Non-negotiable guardrails

1. **Teacher voice.** Never generate, paraphrase into, or machine-translate into text that is presented in a teacher's voice or first person. Teacher words appear only as verbatim spans rendered from the store by span id, with a source. The assistant speaks only in its own labelled voice ("In our own words").
2. **No fake closure.** Never mark a human gate done. Never edit a test, threshold, gate or evidence file to produce a wanted status. Gates are computed on a clean checkout.
3. **Data writes.** Every Qdrant, Memgraph, Supabase or OKF write follows dry-run → snapshot → ask the owner → apply. Builders run host-side with `backend/.venv/bin/python3`, never in the backend container (6 GiB OOM). Never mutate a serving collection in place: a new schema means a new collection, and the old one stays for rollback.
4. **No live infrastructure** (deploys, Railway, production data, GitHub settings) unless the owner explicitly asks in this session.
5. **Small PRs.**
   - One task ID per PR, about ≤400 changed lines of application code.
   - Behaviour changes go behind a flag.
   - Refactors are behaviour-identical and separate from behaviour changes.
   - Start each branch from the latest `origin/main`. Never stack on merged branches.
6. **Safety code** (`serene_mind_engine.py`, `distress_stage.py`, helplines, crisis copy):
   - Change it only with clinician-reviewed sets.
   - Never change production defaults without the owner filing the clinician's written sign-off.
   - Never weaken SEVERE/CRISIS handling.
   - Never test-call 112.
7. **Secrets and rights.** No secrets in files (only `backend/.env.example` is tracked). Never add teaching text, transcripts or teacher audio to the repository.
8. **Repository rules.**
   - Clean root (audits go in `audits/`, docs in `docs/`, ops scripts in `scripts/ops/`).
   - npm only; do not touch `bun.lockb`.
   - Same-named ops scripts in `scripts/ops/` and `backend/scripts/ops/` stay byte-identical.
   - Use `async def get_container_async()` in `Depends`.
   - Every node that returns `final_answer` returns a non-empty `verification` dict.
9. **Honest reporting.** Paste real test output. If something fails or was skipped, say so.

## 5. Owner decisions you must not assume

Ask the owner, then wait, before the tasks that depend on them:

| ID | Decision | Blocks |
|---|---|---|
| D-01 | Repository private / purge / history rewrite | T0-02 |
| D-02 | OKF files in the repository | T0-02 |
| D-03 | ADR-001: may a labelled assistant explanation sit beside verbatim quotes? Needs the teachers' organisation's consent before public use | All of P5 |
| D-04 | ADR-002: general-assistant lane or a static boundary? (recommended: static boundary) | T4-03 |
| D-05 | ADR-005: retire Memgraph/LightRAG? (recommended: yes) | T3-11 |
| D-06 | Clinician engagement | T4-04 |
| D-07 | Is `/api/first-person/query` used by any client? | T1-08 |
| D-08 | Private evidence store and source bundle location | T3-09, T1-11 |
| D-11 | Correct release scopes | T0-04 |
| D-17/18/19/20/21/24/26 | Remaining owner items | `audit-output/unresolved-questions.md` |

If a decision is missing, skip that task, record it as blocked, and continue with unblocked work.

## 6. Work order (dependency-ordered; full table in `audit-output/20-ordered-engineering-roadmap.md`)

**Step 0 (mandatory, read-only):** run `audit-output/25-phase-specific-coding-prompts.md` §1. Record the current `origin/main` SHA. Re-locate every P0/P1 symbol below with `rg -n`, and mark each STILL-TRUE / CHANGED / FIXED. Write `audits/REVALIDATION-<date>.md`. Do not change code in this step.

**P0 — exposure and honest status**
- T0-04: restore the honest gate-test assertion (computed status on a clean checkout). Ask the owner to correct the scopes. Get `main` green.
- T0-02 (after D-01/D-02):
  - Move the tracked teaching text, transcripts, teacher audio, data backups and `/Users/` paths to private storage, leaving `{path, sha256, bytes}` stubs.
  - Extend `scripts/guards/lesson_guards.py` to block the keys `verbatim_text`, `source_transcript_text` and `live_verbatim_text`; `/Users/` paths; and audio under `public/` without a rights id.
- T0-07: route Lovable edits through PRs; resolve `lovable-sync`.

**P1 — guardrails; remove latent P0 paths** (parallel-safe unless noted; for `config.py`, merge in this order: T1-07, T1-02, T1-06)
- T1-05: fail closed. One predicate, `teaching_generation_allowed()`, true only if `FIRST_PERSON_LLM_FALLBACK_ENABLED=true` is set deliberately. Bridge off, node fault or classifier failure → static abstain with a `verification` method code and a metric. Guard `generate_answer` against teaching intents. Prove it with fault-injection and kill-switch tests.
- T1-02: delete the quote-weaver editorial/hybrid LLM paths, the ingestion first-person dual-index (fabricated provenance), and `REFERENCE_VOICE`.
- T1-01: replace the root `CLAUDE.md`/`AGENTS.md` voice section with the rule in guardrail 1. Add a guard.
- T1-07: spend cap on and fail-closed by default. Production validator requires caps and a scorer model. Pin one relevance-scorer timeout (today 25 s in code, 15 s in compose, 12 s in docs).
- T1-08: give `/api/first-person/query` the same identity, anon quota and budget as `/api/chat` (or make it admin-only per D-07). Video streaming only for rights-servable ids.
- T1-10: consent gate plus opt-in for healing-course assignment and proactive Serene Mind. No push prompt after a safety-route answer.
- T1-12: **replace** the deletion funnel.
  - Ship a direct confirm-and-delete flow in `AccountDataCard` (export offer, typed confirmation) **first**.
  - Then remove the save offers, the win-back emails, the beat task and the templates.
  - Remove "keep 30/90 days" unless T6-06's purge job ships in the same release.
  - Make streak copy neutral and opt-in.
- T1-11 (after T0-04): the release gate recomputes agreement; rejects `independent_review:false`, invalid or non-ancestor SHAs, `local-*` environments and non-human certifiers; checks helpline verification age; flags scopes that exceed the notes. One failing fixture per rule.
- T1-03: remove or relabel unsourced teacher attributions (`backend/app/api/teachings.py` ~60–141, `src/lib/healingCourses.ts`, `DeepenAndTuneBar.tsx`). Add an attribution lint.
- T1-04: remove other-teacher seeds and personas (Sadhguru, ISKCON, "SKY private teachings"). Unify assistant slugs. Stop sending the client system prompt.
- T1-06: no teacher-register block in general mode or non-explanation prose.
- T1-09: no seeker text in logs; guard.
- T1-13: remove the repo-root shim packages, the `langdetect` stub and the dead WhatsApp signer; make the compliance dependency async.
- T1-14: datastores bound to localhost or a private network; Qdrant API keys; pinned images; reject CORS wildcards in production; protect deep health.
- T1-15: documentation diet. Archive `lessons.md`; one status file ≤30 KB; root `CLAUDE.md` ≤15 KB; CI check that the documented stage order equals `pipeline_builder.py`.
- T1-16: replace relative `/api` fetches with `BACKEND_URL`; lint rule; hide the WhatsApp button while the channel is disabled.
- T1-17 (P1): every client error state shows a call-verified helpline line and a retry; the helpline list ships in the bundle; no developer text reaches seekers (`src/lib/errors.ts` ~79–97).
- T1-18: stream contract. Citations, labels and safety notices arrive before or with the final text; the client discards or marks an incomplete turn and never saves it as complete; add a client stream timeout (`orchestrator.py` ~447–468; `streaming.ts` ~320–368).
- T1-19: delete the client summary call to `/api/chat` (`transport.ts` ~433–463).
- T1-20: localise trust, abstain, error and quota strings; CI guard for missing chat keys; native review before release.

**P2 — measurement before behaviour change**
- T2-05: fixture Qdrant + Redis CI job.
- T2-02: frozen retrieval bank (Recall@k, Precision@5, MRR, nDCG@10) posted per PR.
- T2-01: blocking offline PR suite (routing, benign/crisis/multi-turn distress sets, quote integrity, voice lint, abstain set). Retire or relabel the self-judging `eval-run`.
- T2-03: one `answer_outcome` event per turn: lane, reason, served/abstained, layers, span ids, verification, latency per stage, and per LLM call `prompt_id@version`, model, tokens and cost. Plus frontend feedback. `useful_answer` = served AND (helpful OR played ≥20 s OR saved) AND NOT reported.
- T2-06: config lint.
- T2-04: golden-set tooling only. **Humans label.**

**P3 — data correctness**
- T3-01: ship the rights register with the image; production startup fails if it is missing, empty or digest-mismatched; expose the digest in health.
- T3-12: encoder fingerprint check at startup.
- T3-02: read-only Qdrant key for the backend; write key for builders; signed collection digest verified at startup.
- T3-04: builder per-video replace; snapshot before the first write.
- T3-03: vNext schema with `video_transcript_sha256` + `span_text_sha256` (new collection); writer contract test.
- T3-08: Supabase schema snapshot in CI.
- T3-06: Postgres source registry as the authority; `takedown()` clearing Qdrant, caches and citations with a report; structured `message_citations`; video decisions moved from JSON to Postgres.
- T3-05: the scorecard is the promotion gate; daily read-only audit; approved version = served version.
- T3-07: canonical teacher ids everywhere.
- T3-11 (after D-05): freeze and retire LightRAG, Memgraph and the chat corpus from serving.
- T3-09 and T3-10 (after D-08): source bundle, private evidence, off-host backups and restore drills.

**P4 — retrieval, routing, safety** (each change must show non-negative frozen-bank and PR-suite deltas)
- T4-01: gate first, then dedup.
- T4-02: hybrid dense + sparse RRF grouped by parent in the v10 store.
- T4-05: route Standard-strategy DISTRESS directly to its handler.
- T4-03 (after D-04): one route-decision service with one scope file.
- T4-06 (preferably after T7-01): one structured evidence-judge call (optionally after an ONNX cross-encoder pre-rank). ≤2 LLM calls per in-domain turn. A scorer failure abstains as `relevance_indeterminate`.
- T4-07: show only call-verified helplines.
- T4-04 (clinician): topic-versus-state discriminator; remove the unconditional MILD→MODERATE upgrade; history escalation counts state disclosures only; the bridge declines only on state ≥ MODERATE. Targets: crisis recall 100% on the core set; benign overfire ≤5%; 0 benign multi-turn SEVERE.

**P5 — answer intelligence** (only after D-03; flags `ANSWER_PLAN_ENABLED`, `LAYERED_ANSWER_ENABLED`, default off)
- T5-01: AnswerPlan.
- T5-02: per-facet retrieval and evidence sets (coverage, video diversity, contained-span removal, teachers never merged).
- T5-04: verifier: exact-substring quotes; every explanation sentence cites span ids and passes entailment, or is dropped; attribution check; fenced untrusted text.
- T5-03: layered contract `layers[{type, text, span_ids, voice}]`, where only `verbatim` may have `voice: "teacher"`. UI renders the layers distinctly.
- T5-05: server-side `answer_trace` follow-ups.
- T5-06: language field; labelled translations, including a "machine translation" label on the client's on-demand quote translation.
- T5-07: prompt registry.

**P6 — mentor and memory**
- T6-06: durable queued erasure that works with the backend down; a purge job for due scheduled deletions; erasable `router_decisions`.
- T6-08: processor inventory and privacy notice.
- T6-01: consolidate onto canonical memory (snapshot + owner approval).
- T6-02: use memory only for continuity and to avoid repeated clips.
- T6-03: user-stated preferences replace the LLM persona; fence the client summary.
- T6-04: save, collections, seeker clip report, journeys v1 (sourced spans only).
- T6-05: backend writes assistant turns; client RLS allows `role='user'` only.
- T6-07: dependency guard from a clinician-written rule.
- T6-09 (P1, after T6-05): account-level history. The server is the source of truth for signed-in users; list, open and delete from any device; no silent wipe on sign-out; wire or remove the retention setting.
- T6-10: honest copy and controls. A first-use explainer of the three outcomes (clip, honest abstain, safety); landing copy that matches the product; explanations of "Related" and "unverified clip"; personalisation copy only for real effects; visible quota and reset time.

**P7 — reliability and cost**
- T7-01: split `FirstPersonPipeline.execute` (2,145 lines), behaviour-identical, proven with golden snapshots.
- T7-02: async teaching lane; remove `run_llm_coroutine` and the watchdog after a staging c20 test.
- T7-03: one LLM gateway.
- T7-04: 2–3 versioned cache tiers; no semantic cache on teaching answers.
- T7-05: exception and import ratchets.
- T7-06: retire the legacy engine and the generating graph from chat once vNext wins on the frozen bank.

**P8 — teachers:** T8-01 extend `backend/config/gurus.yaml` (sources, rights, attribution policy, aliases). T8-02 generate guardrails and labels from it, plus a literal-name ratchet guard.

**P9 — deploy (owner present):** T9-01 Railway IaC for backend, worker, beat and Redis (+ Qdrant if self-hosted), staging first. T9-02 smoke, cross-browser e2e green, real-model c20 load. T9-03 alerts (integrity breach, crisis-lane error, spend 80%, p95, data audit). T9-04 run the Qdrant and Railway runbooks (`audit-output/22`, `22b`).

**P10 — review and release:** T10-01 guru-review package from staging (`audit-output/23`). T10-02 human gates (never fake). T10-03 re-score the readiness scorecard.

File-conflict sequences:
- `first_person_pipeline.py`: T4-01 → T7-01 → T4-06 → T7-02 → T5-02 → T5-04.
- `first_person_bridge.py`: T4-04 → T7-02 → T5-03 → T5-05 → T5-06.
- `supabase/migrations/`: T3-08 first.
- `ChatInterface.tsx`: T1-16 → T1-19 → T1-10 → T1-18 → T6-09 → T5-03.
- `chatStorage.ts`: T6-05 → T6-09.

## 7. Verification protocol for every PR (`audit-output/22a` §4)

1. Re-locate the symbols. Note any drift.
2. Write behaviour tests first and watch them fail. No source-text assertions.
3. Run the affected tests: `cd backend && .venv/bin/pytest tests/<files> -q`. For `src/`: `npm run lint && npm test`.
4. Run the fixture-store job if retrieval, cache, RLS or erasure is touched.
5. Run the PR suite and the retrieval bank if routing, retrieval, gates, prompts or safety code is touched. Paste both deltas.
6. Run `python3 scripts/guards/lesson_guards.py`.
7. Confirm no secret, teaching text, transcript or teacher audio was added.
8. PR body: `<task-id>: <objective>`; findings closed; files; test output; acceptance checklist; rollback note.

## 8. Definition of done

- A task is done when its acceptance criteria (`audit-output/21` for P0/P1; the finding record otherwise) pass with evidence in the PR.
- A phase is done when its completion evidence in `audit-output/20` §7 exists.
- Release scopes are defined in `audit-output/23` ("Overall verdict"): internal testing → limited beta → broader release.
- You never declare a scope reached. You report the computed evidence; the owner decides.

## 9. Final step

When no unblocked task remains, run `audit-output/25` §12 (independent verification) yourself as a self-check. Then report:

1. Tasks merged, with PR links.
2. Tasks blocked, with the owner decision each needs.
3. Every check run, with its result.
4. The residual risks that remain.

Do not claim readiness that the evidence does not show.

### 0f. T2-03 outcome telemetry (backend part), commit `2c80d884`

- Landed: `backend/app/answer_outcome.py` builds one `answer_outcome` record per turn (no text, no user or session id) and `ResultAssemblyStage` (`glue_stages.py`) emits it inside a try/except. New metrics: `guru_answer_outcome_total{lane,outcome}`, `guru_answer_latency_seconds{lane,outcome}`, `guru_integrity_breach_total{lane}` (a served teaching-lane turn with a non-empty `model_used` while the bridge is on and LLM fallback is off). Tests: 39 passed after rebase (`test_answer_outcome_telemetry.py`, `test_no_seeker_text_in_logs.py`, `test_pipeline_stages.py`).
- Left for the next agent: emit outcomes on early-return paths (exact cache, doctrine cache, other stages that return before ResultAssembly; `cache_hit` is hard-coded false today); per-LLM-call `prompt_id@version`, tokens and cost; per-stage latency; the frontend feedback join and the `useful_answer` metric; the Supabase sink write (needs a schema change).
- CI on `2c80d884` (branch head) not yet observed. Remaining register: §0d (as updated in §0e).


### 0g. Findings status after all batches (2026-11-04, branch head after `311ec7e2`)

| Status | Findings | P1 among them |
|---|---|---|
| Closed in code (pending CI confirmation) | 29: ANS-005, AI-006, DATA-04, SAFE-006, GURU-012, ADV-03, RET-09, SYS-001, AI-003, SYS-004, SEC-003, MEM-003, PRD-004, UX-003, EVAL-001, GURU-003, GURU-006, PRD-001, UX-010, UX-007, PRD-009, DATA-02, SEC-008, SEC-010, CQ-013, SEC-009, MEM-005, SAFE-008, ADV-05 | 11 |
| Partly addressed | 7: X-01 and GURU-001 (honest test; `main` green pending), GURU-002 (gate rejects; independent labels are human work), GURU-004 (gate flags; owner corrects scopes), GURU-007 (gate checks; phone calls are human), SEC-006 (localhost binds; Qdrant keys and pins open), SYS-011 (backend outcome events; early-return paths and frontend join open) | 6 |
| Open | 116 (both P0 included: X-06, IP-001 need owner D-01) | 30 |

**Do first in the next session:** confirm CI on the branch head; fix any remaining failure (treat T1-05/SEC-010 behaviour as intended; anything else is a regression).

**Next agent-doable tasks, in order (no owner decision, no clinician, no live infrastructure):**
1. T2-03 remainder: emit `answer_outcome` on early-return paths (exact cache, doctrine cache), per-call `prompt_id@version`, tokens and cost.
2. T2-05 fixture Qdrant + Redis CI job.
3. T2-01 offline PR eval-suite harness (crisis set non-blocking until clinician review).
4. T2-02 retrieval-bank harness (labels are human work; the harness is not).
5. T1-18 stream contract (citations, labels and safety notices before or with the final text).
6. T3-02 Qdrant read-only and write keys (code and compose; enabling in production is infrastructure).
7. T3-04 builder per-video replace and snapshot-before-write (code only; running it needs the owner).
8. T3-12 encoder fingerprint; T3-08 schema snapshot CI; T3-05 promotion gate and daily audit.
9. T3-06 source registry, `takedown()` and structured citations (migration written, not applied).
10. T4-01 gate-then-dedup; T4-02 hybrid RRF on v10 (both measured on the T2-02 bank).
11. T6-05 client RLS `role='user'` → T6-09 account-level history → T6-06 durable erasure and purge job → T6-04 save, report, revisit.
12. T7-01 split `FirstPersonPipeline.execute` (behaviour-identical) → T4-06 evidence judge → T7-02 async.
13. T1-13 rest (root shims, `langdetect` stub), T1-14 rest (Qdrant keys in compose, verified image pins), T2-06 config lint, T1-15 documentation diet.

**Before every push** (lesson from this session): run `ruff format --check` with the CI version, the pre-commit whitespace and end-of-file hooks on changed files, and `rg` for tests that assert behaviour you changed on purpose.
