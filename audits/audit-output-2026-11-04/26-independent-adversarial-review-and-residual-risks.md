# 26 — Independent adversarial review and residual risks

Reviewer: independent adversarial reviewer (did not author docs 01–23). Target: `origin/main@46b808fb`, read from the read-only snapshot. Conventions: `CONVENTIONS.md`.

## 1. Method and limits

| Item | Value |
|---|---|
| Method | Re-read every cited line for 16 headline claims. Traced each request path end to end (stage chain → OffTopicStage → GraphStage → registry → bridge → graph). Searched the code for services and stores that docs 05/06 do not list. Compared the documents with each other. |
| Tools | `rg`/`grep`/`sed`, one `python3 -I` count script (no teaching text printed). No services contacted. No tests run. |
| Not done | No live Qdrant, Railway, Supabase or Redis checks. No runtime simulation of regex routing (static tracing only). Frontend read only where a finding needed it (deletion flow, translation, citation flags). |
| Main limit | Live configuration (Railway variables, Supabase `pg_cron`, owner `.env`) can change several verdicts. Those cases are labelled `[LIVE-R]` or `[LIVE-L]`. |

## 2. Claim verification (Task A table)

Verdict scale: CONFIRMED / PARTLY / REFUTED / CANNOT VERIFY. Severity call: right / inflated / deflated, with the severity I would assign.

| # | Claim (owner doc) | Verdict | Evidence checked | Severity call |
|---|---|---|---|---|
| 1 | ANS-001: "What is the cause of my anxiety?" → MODERATE → bridge declines → template (`10`) | CONFIRMED [V-STATIC] | `anxiety` is in the MODERATE list (`backend/services/serene_mind_engine.py:368`). `_DISTRESS_DECLINE_LEVEL = 2` (`backend/app/pipeline/stages/first_person_bridge.py:67`); decline at `:677-684` unless `first_person_distress_serve_clip_enabled` (default `False`, `backend/app/config.py:455`). The graph then runs `handle_distress` (`backend/rag/nodes/intent.py:1511`), which returns the template. The owner's recorded env has the flag `true` (`audits/evidence/public_release_phase0_state_2026-10-21.json:72`), so config B serves a clip under compassion framing. Missed detail: the question also matches `_SYNTHESIS_SHAPE_RE` ("the cause of", `first_person_bridge.py:81-89`). If distress is fixed, this rule still routes the question to synthesis when fallback is on. | Right (P1) |
| 2 | ANS-002 / SAFE-002: MILD→MODERATE upgrade; 2+ MODERATE turns → SEVERE pre-emption (`10`, `14b`) | CONFIRMED [V-STATIC] | MILD always maps to `"gentle"`, so the upgrade at `serene_mind_engine.py:1698-1703` is unconditional. History escalation is at `:1810-1826`. `_quick_distress_check` counts MODERATE+ keywords (`:2111-2126`). DistressStage calls `analyze_with_history` (`backend/app/pipeline/stages/distress_stage.py:492`) and pre-empts at SEVERE+ (`:283`). The LLM downgrade is off (`config.py:1637`) and is skipped after prior distress (`distress_stage.py:532-535`). | Right (P1). The failure is safe-direction over-firing, so it is a trust defect, not a safety defect. |
| 3 | ANS-003 / SYS-002: grief, ego, attachment, happiness miss `_ON_TOPIC_RE` and go to the general LLM (`10`, `05`) | REFUTED for questions with no keyword; PARTLY for one narrow class [V-STATIC] | `OffTopicStage.run` sets `domain_route="teaching"` and returns for any question that is not off-topic or live-info (`backend/app/pipeline/stages/off_topic_stage.py:591-607`). "What is ego?" matches neither `_OFF_TOPIC_RE` (`:267-280`) nor `_GENERAL_TASK_RE`. GraphStage honours the route (`graph_stage.py:210-211`). The registry claims it for first person (`backend/rag/pipeline_registry.py:86-90`). The stage is on by default (`config.py:1376`). Lines `:645-680` run only after a question is already classed off-topic. Real residual: a question that matches `_GENERAL_TASK_RE` (e.g. "mental health", "therapy", "career path") **and** an `_INNER_HELP_RE` word that is not in `_ON_TOPIC_RE` (sad, worried, upset, overthinking) skips the boundary and gets `general_knowledge_mode=True` (`:625-669`). The Jev `live_research` route also goes general (`:510-530`). Doc 09 row 122 repeats the error. | Inflated. ANS-003 → P2. SYS-002 (regex routing as architecture risk) → P2. |
| 4 | AI-003: "THE TEACHER'S VOICE … match this register" appended in general mode (`09`) | PARTLY [V-STATIC] | The general prompt is built at `backend/rag/nodes/generation.py:3214-3220`. `_maybe_apply_langhanam_voice` then runs for both modes (`:3250`). `langhanam_voice_enabled=True` (`config.py:1888`). Block text: `backend/services/voice/register.py:292`. Mitigations: the block says "governs HOW… never WHAT" and "Never invent a first-person sentence" (`register.py:229-236`). With no teacher docs it picks the neutral "shared" register (`:195-196`). At default first-person-only config, general mode is reachable only by the narrow paths in #3 and #5 and by ADV-03. This is style mimicry on assistant prose, not first-person impersonation. | Right (P2) |
| 5 | SYS-001 / RET-09: a first-person exception or classifier failure falls through to the generating graph (`05`, `08`) | PARTLY [V-STATIC] | `FirstPersonBridgeStage.run` catches bridge exceptions and, in first-person-only mode, returns a static abstain (`first_person_bridge.py:585-596`, `:616-627`). The node's own `except` (`backend/rag/nodes/first_person.py:52-65`) fires only for a missing `pipeline_ctx`, an import failure, or an exception inside `_decline`/`_abstain`. The classifier fallback (`graph_stage.py:211-221`) fires only when `domain_route` is not already `"teaching"`. No first-person-only guard exists under `backend/rag/` (confirmed). The documents miss a larger fail-open: ADV-03. | SYS-001 inflated (P1 → P2). RET-09 right (P2). |
| 6 | SYS-004: OpenRouter budget guard off and not fail-closed by default (`15`) | CONFIRMED [V-STATIC]; Railway values [LIVE-R] | `config.py:645` `False`, `:647` `False`. The comment at `:644` says "Default enabled", which is wrong. Read at `backend/app/openrouter_budget.py:123,128`. Enabled only in `.env.example:44-45`, `backend/.env.example:40-41` and compose. `backend/Dockerfile.railway` sets no budget variables. | Right (P1) while SEC-001 is open; P2 once SEC-001 is fixed |
| 7 | SEC-001: `/api/first-person/query` has no auth and no anon quota (`14`) | CONFIRMED [V-STATIC] | `backend/app/api/first_person.py:295-301`: `@limiter.limit("120/minute")`, no user dependency, no quota call. The route is on by default (`config.py:184`, `:222`). Up to 3 LLM calls per request (see C-3). | Right (P1) |
| 8 | DATA-02: rights register not in the Railway image, so every clip is unlicensed (`06`) | CONFIRMED [V-STATIC]; runtime [LIVE-R] | `RIGHTS_MANIFEST_RELPATH` points to `audits/evidence/…` (`backend/services/first_person_serving_contract.py:177-186`). A missing file gives `{}` (`backend/services/qdrant/indexer.py:55-60`), then `"unverified"`, then `False` (`backend/services/first_person_rights.py:15-26`). `backend/Dockerfile.railway:81-94` copies `backend/`, `memory/` and `helplines.yaml`, not `audits/`. No `backend/audits/` exists. Compose mounts it (`backend/docker-compose.yml:468`). It fails closed, with no startup error. | Right (P1). This is a release blocker, not an integrity defect. |
| 9 | RET-02: v10 retrieval is dense-only (`08`) | CONFIRMED [V-STATIC] | `query_sparse` is accepted (`backend/services/first_person_context_store.py:429-437`) and never used. Both query paths use `using="passage_dense"` (`:527-532`, `:570-575`). This contradicts invariant 5. | Inflated (P1 → P2). The effect is unmeasured, and v10 is not the code-default serving path (C-1). |
| 10 | RET-01: per-video dedup before quality gates (`08`) | CONFIRMED for the v8 path [V-STATIC] | Payload, rights and blocklist checks run **before** dedup (`backend/services/first_person_store.py:703-718`). The integrity, content and speaker gates run after it (`backend/services/first_person_pipeline.py:4741-4760`). `dedup_limit=max(40, k*8)` back-fills from other videos (`:4518-4521`). | Inflated (P1 → P2). The 40-video back-fill reduces the effect, and the funnel numbers are `[DOC-CLAIM]`. |
| 11 | MEM-003: healing-course assignment reads emotional arcs without the consent check (`12`) | CONFIRMED [V-STATIC]; data presence [LIVE-L] | `backend/app/orchestrator_utils.py:575-610` is gated only by incognito, flag (`config.py:1678` `True`) and a persistable user id. The consent gate at `:893-919` is not applied. `_build_emotional_arc_turns` (`:636-654`) reads `guru_memories` and legacy memories. | Right (P1) |
| 12 | UX-001: deletion wired to a churn funnel and win-back emails; UI "dormant" (`12b`, `03`) | CONFIRMED and understated. The "dormant" claim is REFUTED [V-STATIC] | The UI is mounted: `src/pages/ProfilePage.tsx:583` → `src/components/profile/settings/AccountDataCard.tsx:140-195` → `CancelFlow`. This is the **only** UI path to `delete-my-account`. `confirm-cancel` queues 4 emails for every retention choice, including `delete_immediately` (`backend/app/api/cancel_flow.py:502-515`). The task skips only on `no_cancellation`, `already_sent` or `reactivated` (`backend/tasks/cancel_flow_tasks.py:157-167`). Who gets emails: (a) a `delete_immediately` user — the edge function deletes `cancellations` rows (`supabase/functions/delete-my-account/index.ts:158-162`), so later emails skip, but the day-0 email (countdown 0) can be sent before deletion [INF]; (b) a `keep_30_days` or `keep_90_days` user gets all four, and **no executor ever deletes the account** (ADV-01). | Right (P1). Real exposure is larger; see ADV-01. |
| 13 | GURU-002 / EVAL-001: gold labels `independent_review:false`; the gate checks only presence (`23`, `18`) | CONFIRMED [V-STATIC] | `audits/evidence/public_release_gold_label_report_2026-10-22.json:12-13` and `…agreement_calibration_report…:9-10`: `independent_review: false`, `curated_consensus_alignment`. `…speaker_certification…:24-25` is also `false`. `backend/scripts/ops/check_first_person_public_release.py:788-835` checks only file presence and non-blank cells. | GURU-002 P0 is inflated → P1. EVAL-001 P1 is right. The release is not public, and the owner gates are pending. |
| 14 | IP-001: 2,737 `verbatim_text` in an exported JSON; teacher-voice MP3s (`14c`) | CONFIRMED for text; PARTLY for audio | Script count: 2,737 non-empty `verbatim_text` fields in `audits/evidence/public_release_v10_points_export_2026-10-21.json` (7.9 MB). `public/audio/meditation/` has **one** MP3 (`preethaji-serene-mind.mp3`, 3.7 MB) plus a README. Whether the voice is the teacher's: [HUMAN]. Repo visibility is public per doc 01 [V-GIT]. | Inflated (P0 → P1). The source speech is already public. The harm is to rights and trust, not to security or integrity. It is still urgent, because Git history is permanent. |
| 15 | GURU-012: teacher-attributed quotations with no source (`11`) | PARTLY [V-STATIC] | `backend/app/api/teachings.py:60-141` `CURATED_FALLBACK_TIPS` has a `source` label (book or series title) but no locator (page, video, timestamp). It is served at `:235` and `:305`. `src/lib/healingCourses.ts:52,59,89` puts teacher-attributed paraphrases into `guruPrompt` strings, sent as user prompts. Display as quotes not verified. | Right (P1). The source label exists; the verifiable locator is missing. |
| 16 | DATA-03: `transcript_hash` has different meanings across writers (`06`) | CONFIRMED [V-STATIC]; counts `[DOC-CLAIM]` | Cleaned-text hash (`first_person_store.py:431`). Recompute (`:954`). The v10 adapter maps `transcript_hash := source_text_hash` (`first_person_pipeline.py:2558`). Merged-span re-hash (`:2652`). 1,839/2,758 measured in root `CLAUDE.md` invariant 2. | Inflated (P1 → P2). Both gates fail closed today. The hazard is future code. |

## 3. Missed areas and new findings (Task B)

### ADV-01 — Deletion requests go through a backend-dependent retention funnel, and scheduled deletions never run
| Field | Value |
|---|---|
| Pillars | P5, P4, P6 |
| Severity | P1 |
| Type | Confirmed defect (static); [LIVE-R] for any dashboard-only `pg_cron` |
| Confidence | High (code); Medium (production) |
| Evidence | `AccountDataCard.tsx:140-195` (mounted at `ProfilePage.tsx:583`). `CancelFlow.tsx:86-106` throws "Backend unavailable." without `BACKEND_URL`. `:180-197`: `confirm-cancel` must succeed before `onComplete`. `cancel_flow.py:433-515` schedules four emails for every retention choice. `scheduled_deletion` appears only in `cancel_flow.py`, `cancel_flow_tasks.py:170,254` and migration `20260715020000_cancel_flow.sql:46,58`. No job deletes accounts on that date. |
| Actual behaviour | (1) "Keep 30/90 days" signs the user out, says deletion is scheduled, sends win-back mail, and never deletes. (2) When the FastAPI backend is down (Railway is stopped per root `CLAUDE.md`), the UI cannot reach `delete-my-account` at all. |
| Expected behaviour | One deletion action that works without the backend and completes on the stated date. |
| Remediation | Call `delete-my-account` directly. Remove the funnel (UX-001). If a grace period is kept, add a scheduled purge job with an evidence log. |
| Acceptance criteria | E2E: delete with the backend down succeeds. Seeded scheduled cancellation is purged on its date. Zero emails after a deletion request, except one confirmation. |
| Verification | [V-STATIC]; [LIVE-R] |

### ADV-02 — Undocumented third-party processors of user content
| Field | Value |
|---|---|
| Pillars | P1, P5 |
| Severity | P2 |
| Type | Architectural risk / documentation gap |
| Evidence | Lovable AI Gateway (`ai.gateway.lovable.dev`) is used by `supabase/functions/memory-extract/index.ts:25`, `memory-extract-drain/index.ts:22` (chat text → extracted facts), `sarvam-stt/index.ts:8` (voice audio fallback), `admin-ask/index.ts:58` and `eval-run/index.ts:144`. Sarvam STT/TTS: `sarvam-stt/index.ts:7`, `sarvam-tts/index.ts:6`. Sentry with 50% error replays: `src/lib/sentry.ts:15-26`. SMTP: `backend/app/services/email_service.py:45`. Web push: `supabase/functions/push-send`. None of these appears in the docs 05/06 inventories. "Lovable" appears in doc 05 only as a frontend host. |
| Actual behaviour | User chat text (memory extraction, consent-gated at `src/lib/chat/transport.ts:608-626` and flag-gated by `VITE_MEMORY_EXTRACTION_ENABLED`) and voice audio can reach an LLM gateway that is not OpenRouter. There is a second, parallel memory writer outside the backend. |
| Remediation | Add these processors to the datastore and processor register and the privacy notice. Decide on one LLM gateway. |
| Verification | [V-STATIC]; whether secrets are set [LIVE-R] |

### ADV-03 — The first-person "kill switch" fails open to LLM generation
| Field | Value |
|---|---|
| Pillars | P4, P1 |
| Severity | P1 |
| Type | Confirmed defect (static) |
| Evidence | `FirstPersonBridgeStage._enabled()` (`first_person_bridge.py:573-583`) returns False when `FIRST_PERSON_CHAT_BRIDGE_ENABLED=false`, `FIRST_PERSON_ROUTE_ENABLED=false` or `FIRST_PERSON_MODE=disabled`. The registry then picks `general` (`pipeline_registry.py:65-76`, `:115-131`). `first_person_llm_fallback_enabled` is read only in the bridge and OffTopicStage (rg). It is never read in `rag/`. The teaching prompt is "delivered as a warm, understanding Guru" (`generation.py:3203`). Root `CLAUDE.md` invariant 16 calls this flag the kill switch. |
| Actual behaviour | An operator who switches first person off during an incident sends every teaching question to `generate_answer`. That is the failure that invariant 21 forbids. |
| Expected behaviour | In first-person-only mode, a disabled bridge gives a static abstain. Incident response uses `KillSwitchStage`. |
| Acceptance criteria | Test: with the bridge flag off and fallback off, a teaching question returns `route_decision=first_person_abstain` and `model_used=None`. |
| Verification | [V-STATIC] |

### ADV-04 — Admin "eval-run" measures a different model, not the product
| Field | Value |
|---|---|
| Pillars | P4, P6 |
| Severity | P2 |
| Type | Confirmed defect (static) |
| Evidence | `supabase/functions/eval-run/index.ts:77-120`: answers come from `google/gemini-2.5-flash` via Lovable (`:85-88`), and the same model judges them. Results are written to `eval_runs` and `eval_results`. It is invoked from the frontend (`invoke('eval-run'`). |
| Actual behaviour | Admin quality numbers (faithfulness, relevancy) describe a generic model with no retrieval. They do not describe Mukthi Guru answers. |
| Remediation | Remove the function, or point it at `/api/chat` and label the judge. |
| Verification | [V-STATIC]; dashboard use [LIVE-R] |

### ADV-05 — On-demand client translation of teacher quotes has no "machine translation" label
| Field | Value |
|---|---|
| Pillars | P4 |
| Severity | P3 |
| Type | Probable defect |
| Evidence | `src/components/chat/ChatMessage.tsx:2087-2120` translates the whole `message.content` (which includes the verbatim clip text) through `/api/translate` and shows only the translated text. Invariant 16 says quotes are never translated. |
| Remediation | Exclude quote spans, or label the popover "Machine translation of the teacher's words". |
| Verification | [V-STATIC] |

### ADV-06 — The memory inventory omits two stores
| Field | Value |
|---|---|
| Pillars | P5 |
| Severity | P3 |
| Type | Documentation gap |
| Evidence | WhatsApp bot SQLite `wa_messages`/`wa_state` (`whatsapp_bot/wa_bot.py:121-185`, purge at `:233-237`). The edge-function extraction worker (ADV-02). Neither is listed as a memory plane in doc 12 §1. Doc 12 says "seven planes" but its table lists eight. |
| Verification | [V-STATIC] |

Checked and clean (no new finding):

| Area | Result |
|---|---|
| Rights lookup | Fails closed (`first_person_rights.py:15-26`). |
| `backup.yml` | Refuses a public repo (already in `14`/`15`). |
| `build-deploy.yml` | Pushes images to GHCR only. No Railway, migration or Supabase-functions deploy. |
| `cache-warm.yml` | Writes cache only if `CACHE_WARM_API_URL` is set. |
| WhatsApp bot | Calls the same `/api/chat` chain. |
| `sarvam-tts` | No frontend caller. |
| First-person answers and caches | They skip the cache, output-guardrail and memory stages (`graph_stage.py:600-606`). The semantic cache therefore never replays a clip. |

## 4. Cross-document contradictions (Task C)

| # | Topic | Doc versions | Code supports |
|---|---|---|---|
| C-1 | Default serving collection | `05:39`, `05:105`: "default `first_person_v10`". `08 §2.1`: "`first_person_v8` unless overridden". | **v8** at code default and in `.env.example`. `first_person_active_collection="first_person_v10"` (`config.py:209`) fills the legacy slot only when harness **and** terminal are both true (`:2300-2308`). Both default false (`:289`, `:305`; `backend/.env.example:201,223`). Otherwise `_LEGACY_FP_COLLECTION="first_person_v8"` (`:41`). The owner's local setup is v10-only (invariant 25) `[DOC-CLAIM]`. |
| C-2 | Relevance scorer timeout and model | Root `CLAUDE.md` inv. 24: haiku-5.5, 12 s. `05`/`15`: 25 s default vs 12 s documented. | Three values: `config.py:478-480` (model `""` = provider default, 25 s); `backend/docker-compose.yml:321` (15 s); `CLAUDE.md` (12 s). Docker runs use **15 s** unless env overrides it. No doc mentions 15 s. |
| C-3 | LLM calls per served clip | `05 §5`: 3 on defaults. `09:12`: 3 "under local config". `CLAUDE.md` inv. 22: gate + rerank (2). | **3** on code defaults: `first_person_llm_rerank_enabled=True` (`config.py:247`), answerability `True` (`:424`), relevance `True` (`:472`). The rerank call is at `first_person_pipeline.py:4963-4972`. |
| C-4 | First-person latency | `CLAUDE.md` inv. 9: p50 63 ms / p95 210 ms. Inv. 22: ~4–6 s. `05`/`15`: p50 6.8–7.6 s / p95 12.3–13.9 s `[DOC-CLAIM]`. | Code cannot measure latency. Its budgets (rerank 2.5 s, gate 6 s, relevance 15–25 s) make p95 above 6 s plausible. `05`/`15` fit the code; inv. 9 measures retrieval only. |
| C-5 | Unknown-keyword questions | `10` ANS-003, `05` SYS-002, `09:122`: go to general LLM. `05:131`: registry picks first person when claims hold. | **Teaching lane** (`off_topic_stage.py:591-607`). See row 3 of §2. |
| C-6 | CancelFlow status | `03:74`, `03:363`, `12b:36-39`: "dormant". | **Mounted and live** (`ProfilePage.tsx:583`, `AccountDataCard.tsx:25,162`). |
| C-7 | Severity of one defect | GURU-002 P0 vs EVAL-001 P1. SYS-001 P1 vs RET-09 P2. | P1 and P2 respectively (§2). |
| C-8 | Number of memory systems | `12`: "at least seven" with eight rows. Other docs: none. | At least ten stores hold user-derived content (doc 12's eight, the edge-function extraction worker and WhatsApp SQLite), plus browser-local chat. |

## 5. Answers to the adversarial questions (Task D)

| Question | Answer |
|---|---|
| Did the audit inspect all meaningful subsystems? | No. Edge functions as processors (ADV-02, ADV-04), the deletion executor (ADV-01) and kill-switch semantics (ADV-03) were missed. Coverage of the backend request path is good. |
| Did it miss data stores? | Yes: the Lovable gateway path, Sentry replays, SMTP, push, Sarvam and WhatsApp SQLite as a memory plane. Qdrant, Supabase, Redis and Memgraph are covered. |
| Silent fallbacks? | Mostly found: distress over-fire, rights fail-closed, classifier fallback. Missed: the kill switch fails open to generation (ADV-03), and deletion silently never completes (ADV-01). Translation and cache fallbacks checked; no new defect. |
| Are source attributions accurate? | Line references are mostly accurate (±5 lines). Two conclusions overreach their lines: ANS-003 cites `:656-665` but ignores the early return at `:604-607`, and SYS-001 ignores the bridge's internal `try` (`:588-596`). |
| Did it confuse generated interpretation with teaching? | Mostly no. The docs keep OKF, meditation infusion and curated tips separate from verbatim clips. The `eval-run` metrics (ADV-04) are generated-on-generated and were not flagged. |
| Can a future teacher be added without rewrites? | Partly. Speakers come from `backend/config/gurus.yaml` (`guru_registry.py:21`; `first_person_store.py:63`). But 50 runtime Python files still name the teachers, `_ON_TOPIC_RE` hard-codes lineage terms (`off_topic_stage.py:57-66`), and the rights register, voice profiles and speaker centroids are per teacher. Doc 11's conclusion holds. |
| Is the system needlessly expensive? | Moderately. 3 LLM calls per served clip; the relevance scorer is a reasoning model with `max_tokens=1024`. A second LLM gateway (Lovable) runs alongside OpenRouter. Seven or more memory planes. |
| What will break at scale? | Process-local hot and vector caches per replica. The per-IP limiter on an unauthenticated LLM route (SEC-001). Relevance budgets of 15–25 s holding workers. Celery countdowns of up to 28 days on a Redis broker; a `visibility_timeout` below the countdown redelivers tasks [INF]. `already_sent` limits duplicates. |
| Which conclusions rely on inaccessible infrastructure? | Served collection contents and counts [LIVE-Q]. All latency figures. Railway variables (budget, collection, register mount) [LIVE-R]. Supabase `pg_cron` purge jobs [LIVE-R]. Legacy emotional-arc data for MEM-003 [LIVE-L]. Whether the MP3 is the teacher's voice [HUMAN]. |
| What important failures remain possible? | See §6. |

## 6. Residual risks

| # | Risk | Basis | Owner action |
|---|---|---|---|
| R-1 | Incident response causes LLM teacher-voice prose (ADV-03), plus narrow node and general-lane fall-through (SYS-001, row 3). | [V-STATIC] | Make a disabled bridge a static abstain in first-person-only mode. |
| R-2 | Deletion requests are not honoured, or cannot be made while the backend is down (ADV-01, UX-001). | [V-STATIC]; [LIVE-R] | Direct edge-function deletion; purge job; remove the funnel. |
| R-3 | Unbounded LLM spend from an unauthenticated route with the budget guard off by default (SEC-001 + SYS-004). | [V-STATIC]; [LIVE-R] | Default the guard on and fail-closed; add a quota to the route. |
| R-4 | Benign seekers get distress templates or helplines on topic words (ANS-001/002, SAFE-002). Under-detection in Indic languages is not native-reviewed. | [V-STATIC]; [HUMAN] | Clinician-reviewed topic-vs-state rule; native-speaker review. |
| R-5 | Release gate passes on non-independent labels (EVAL-001). A public repo holds 2,737 verbatim spans (IP-001). The Railway image lacks the rights register (DATA-02). | [V-STATIC]; [V-GIT] | Gate on `independent_review=true`; move evidence private; ship the register in the image with a startup check. |
| R-6 | Config drift: three relevance budgets (C-2) and two serving postures (C-1) mean tested behaviour may not be deployed behaviour. | [V-STATIC] | One profile file per environment and a startup log of the effective posture. |

## 7. Lead reconciliation

### 7.1 Corrections accepted and applied

| Review result | Action taken | Where |
|---|---|---|
| ANS-003/SYS-002 REFUTED in the broad form | Narrowed to "general-task word + emotion word"; P1 → P2; AI-001 P1 → P2 | `findings-index.md`; errata in `05`, `09`, `10`; `16` RC-3, FM-3, F-11 |
| SYS-001 PARTLY (bridge catches its own exceptions) | P1 → P2; T1-05 now leads with the kill-switch path | `findings-index.md`; `05` erratum; `20` T1-05; `21` T1-05 |
| ADV-03 kill switch fails open (new P1) | Added; merged into T1-05; RET-09 kept at P1 as its root | `findings-index.md`; `16` FM-4, F-12 |
| UX-001: the funnel is mounted and is the only deletion UI | P2 → P1; T1-12 changed from "remove" to "replace, new path first" | Errata in `03`, `12b`; `20` T1-12; `21` T1-12 |
| ADV-01 scheduled deletions never run (new P1) | Added; T6-06 raised to P1 with a purge job | `20` T6-06; `21` T6-06; `14` addendum |
| ADV-02 undocumented processors (new P2) | New task T6-08 | `20`; `14` addendum |
| ADV-04 self-judging admin eval (new P2) | Folded into T2-01 | `20` T2-01 |
| ADV-05 unlabelled quote translation (P3) | **Raised to P2** (a translated quote can read as the teacher's words); folded into T5-06 | `20` T5-06 |
| ADV-06 memory inventory gaps (P3) | Folded into T6-01 scope | `findings-index.md` |
| RET-01, RET-02, DATA-03 severity inflated | P1 → P2 | `findings-index.md`; `20` |
| GURU-002 P0 inflated | The whole X-RC2 cluster is P1 | `16` §3, §4 |
| Default collection is v8, not v10 | Corrected | `05` erratum; `17` §2b.2 |
| Scorer timeout 12 / 15 / 25 s | Recorded; T1-07 pins one value | `05` erratum; `findings-index.md` SYS-006 |
| LLM calls = 3 (not 2); 63 ms is retrieval-only | Already stated in `05`/`09`; noted in `04` | `04` §3 |

### 7.2 Where the lead disagrees with the reviewer

| Item | Reviewer | Lead | Reason |
|---|---|---|---|
| IP-001 / X-06 public exposure | P1 | **P0** | It is the only finding where harm happens every day right now. It cannot be undone once cloned. It is the largest threat to the trust conversation with the teachers. Stopping it costs minutes (make the repository private). Severity here signals "do it today". |
| ADV-05 | P3 | P2 | See 7.1. |

### 7.3 Lead answers to the mission's adversarial questions

| Question | Answer |
|---|---|
| Missed subsystem? | The 14-step frontend journey and a structured competitor analysis were thin. They were added (`14d`, `02b`) by a separate read-only pass. The processors in ADV-02 were missed by the specialists and found by the reviewer. |
| Conclusions without code evidence? | Latency (p95 12–14 s), served share (24–31%), usefulness (~11%), clip quality (~1 in 7 clean) and host-voice leak (6.9%) are all `[DOC-CLAIM]` from the repository's own reports, measured locally, and are not re-run here. The architecture recommendations do not depend on their exact values, only on their order of magnitude. |
| Documentation versus implementation? | Where they disagreed, the code won: stage order, default collection, LLM call count, scorer timeout, CancelFlow status. Root `CLAUDE.md` is stale in at least five places. |
| Symptom versus root cause? | The low answer rate was long treated as a selection problem. The repository's own funnel data and this audit place the root in segmentation and data quality (RC-4) and in the distress classifier (RC-5). Retrieval tuning alone will not fix it. |
| Proposals adding complexity? | ADR-001 (layered answer) adds 1–2 LLM calls and a verifier. It is justified only if the owner and the teachers' organisation accept it, and only behind a flag measured on the held-out set. ADR-007 (source registry) adds tables but removes JSON state files and makes takedown possible. Everything else in the target removes components. |
| Premature recommendations? | P5 must not start before P2 (measurement) and P4 (routing, distress). Multi-video synthesis must not start before the frozen bank shows per-facet retrieval works. |
| Missing data that could invalidate the target? | (1) The teachers' organisation may refuse any assistant explanation. Then P5 reduces to an L1-only, multi-clip composition with context labels, and the rest of the target still holds. (2) Live Qdrant contents may differ from the documents (`22`). (3) Real seeker questions may differ from the AI-written test sets (T2-07). |
| Conflicting tasks? | File hotspots and their sequences are in `20` §5. Two added conflicts: T1-12 must ship its new deletion path before removing the funnel; T6-06 must land the purge job before any "keep N days" option survives. |
| Migrations that could break behaviour? | T6-05 (client RLS `role='user'` only) breaks the current client sync of guru turns, so the backend must write assistant turns first. T6-01 moves user memory: snapshot first, owner approval. T3-03 renames hash fields: new collection only, never in place. |
| Unmeasurable acceptance criteria? | Usefulness and emotional appropriateness need the held-out human set (T2-04). Until then they are marked "measurement pending". Latency targets are provisional until staging. |
| Tests that would miss a regression? | The 112 source-text tests; mock-only retrieval tests; LLM-dependent items in the PR suite (non-blocking by design); the e2e matrix while it is red. `22a` §7 lists these. |
| Weak research support? | Personas, JTBD and preferred depth are hypotheses (`02` §3–§6). No seeker has been interviewed. The study (T2-07) is the remedy. |
| Unverified Qdrant and Railway claims? | Collection counts, payload fields, duplicates, hash recomputation (`22`); real latency, cost, error rates, image contents at deploy time, and which backend URL the live frontend calls (`22b`). |
| What could still break after the roadmap? | See 7.4. |

### 7.4 Residual risks after full implementation

| # | Risk | Why it survives | Mitigation that remains |
|---|---|---|---|
| R-1 | A crisis disclosure in an Indic language is missed | Detection depends on native-reviewed sets that do not exist yet | Native + clinician review; conservative fallback toward care; monitoring of crisis-lane volume per language |
| R-2 | The data ceiling limits usefulness | Only a minority of stored clips are clean, self-contained teachings [DOC-CLAIM] | Re-segmentation at source (T3-09) and the layered answer (ADR-001) |
| R-3 | The teachers' organisation does not approve | Consent is outside engineering | The review package (`23`) and the evidence trail; the product stays owner-only until then |
| R-4 | Cost at scale is unknown | No production traffic | Spend caps (fail-closed), outcome-based cost reporting (T2-03) |
| R-5 | Emotional dependency | No clinician-defined rule yet | T6-07; usage-pattern monitoring without engagement incentives |
| R-6 | Regressions from many agent sessions | Process risk | Branch protection, small PRs, the PR suite, one status file |
| R-7 | Rights challenges for already-public content | History cannot be fully recalled | Make the repository private; follow legal advice on history rewrite |
