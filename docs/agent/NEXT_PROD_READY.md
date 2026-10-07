# Next steps to production: first-person verbatim route (updated 2026-09-26 ~05:45 IST)

> **RE-DATED 2026-10-03 (audit G.4 #5).** Everything below is a **2026-09-26 snapshot** and several counts are now stale — do not cite them as current:
> - "serves `first_person_v2`: 280 clips from 45 videos" → live root `.env` pins `FIRST_PERSON_COLLECTION=first_person_v7`, measured **144 points** at `localhost:6333` on 2026-10-03 (`first_person_v2` kept only for rollback).
> - The v2-era "0 direct answers / no calibration profile" state is superseded: calibration claims are demoted to `claims: "none"` (`n=14 pilot` provenance) and honesty now comes from the answerability gate `first_person_answerability_check_enabled` (default `True`).
> - Current authority: `docs/PROD_READY_CHECKLIST.md` (master), `.claude/tasks/abstention_gate_and_index_hygiene_plan.md` + `HANDOFF_2026_10_03.md` (live first-person truth), `.claude/tasks/first_person_e2e_audit_2026-09-29.md` (verdict: **NOT locally prod-ready**). This file = historical checklist.

- **Current verified state:** `handoff.md` (repo root) and this file.
- **Governing spec:** `docs/agent/first_person_baseline_prompt.md`.
- **Rules:** `docs/agent/NON_NEGOTIABLES.md`, `docs/agent/GATES.md`.
- **Response to the agentic CRAG/GraphRAG audit:** `docs/agent/FIRST_PERSON_AUDIT_RESPONSE_2026-09-26.md`.

**Verdict: NO-GO for production.**
- The route works end to end locally (API and UI).
- Precision is unproven: there is no human gold set, so there is no calibration.
- The platform gates are unsigned.

## Where we are (VERIFIED 2026-09-26 unless marked)

### The route
- `POST /api/first-person/query` sits behind `FIRST_PERSON_ROUTE_ENABLED` (default False).
- It serves `first_person_v2`: 280 clips from 45 videos, built deterministically.
- `first_person_v1` is kept for rollback.

### Live results
- **Live eval (2026-09-25):** passed all 8 checks.
  - Top-1 0.434 [0.33, 0.53].
  - 0 non-teacher speakers and 0 hash failures.
  - 0 "direct" answers, because no calibration profile exists.
  - Crisis and teacher-filter probes pass; p95 under 1 s.
- **Live checks after the 2026-09-26 restart:**
  - Route: 200 in 17–86 ms; a repeat query is served from the exact cache in 0.8 ms.
  - A crisis probe returns `crisis_redirect` with helplines loaded from `/config/helplines.yaml`.
  - The Prometheus backend target is up.

### Tests (all run 2026-09-26)
- **Backend:** 7,778 passed, 12 skipped, 0 failed.
- **Frontend:** 654 passed, 6 skipped. `tsc` and lint are clean.

### Fixes from 2026-09-26 (uncommitted, live in the local container)
- **Backend freeze and chat timeouts:**
  - LettuceDetect and the reranker each run on a dedicated thread pool, so a stuck native call can no longer starve the shared pool behind `/api/healthz`.
  - `RLIMIT_DATA` now leaves memory headroom (`app/main.py`).
- **Circuit breaker stuck open:** this turned 588 of 892 benchmark run-1 rows into `system_error`.
  - The cause: a call cancelled by our own timeout leaked its half-open probe slot.
  - New `BaseCircuitBreaker.release_reservation()` frees the slot without counting a provider failure. Counting it as a failure would trip a closed breaker on our own slowness; a test covers that too.
  - Alert `CircuitBreakerStuckOpen`, open for more than 5 min.
- **Crisis helplines:** `config/helplines.yaml` was never in the container, so the in-code fallback was served. Now:
  - both Dockerfiles `COPY` it;
  - compose mounts `../config:/config:ro`;
  - a source-scan test guards it.
- **First-person serving:**
  - exact cache wired to Redis, degrading to no cache if Redis is down, with malformed entries treated as a miss;
  - playback fields `playback_start_seconds`, `playback_end_seconds` and `playback_url`, using a 0.25 s pad (spec: 150–300 ms, owner decision), capped at the video's duration;
  - full latency is counted; each clip is scored once.
- **Alerts:** Prometheus rules for first-person quarantine, latency (p95 > 1 s), error rate (> 5%) and the stuck-open breaker. All four are loaded. There is also a Grafana dashboard, `first_person_dashboard.json`.
- **UI:** `/teachers-words` behind `VITE_FIRST_PERSON_ENABLED`, reusing `CitationCard`.
  - Browser-verified: "Related, not a direct answer" label, speaker, timestamp, auto-transcript badge.
  - The modal embeds at a whole-second `start` (for example 1609 for 26:49).
- **Benchmark:** the `BenchmarkSessionPool` wiring was **reverted**: reused anonymous sessions hit the 5-per-24 h chat quota (L-BENCH-POOL-1). The benchmark mints one session per question, and a Retry-After over 10 minutes fails the row instead of stalling the run.
- **Whisper:** `services/speech_config.py` applies the doctrine glossary (capped at 30 terms) and `condition_on_previous_text=False` at both direct call sites.
- **Pilot punctuation:** `run_punct.py` now passes the strict zero-word-change check on 50/50 pilot videos and 8/8 bake-off videos. The cause: pre-punctuated ASR words were fed to the punctuation model.
- **Prompt audit:** hunks A1–A4 are applied. That covers the dead duplicate `CANONICAL_URLS_LOGISTICS`, corrector leak patterns that now match the live prompt, and the orphaned prompts removed. Hunks B1 and B2 (the docs cleanups) are applied too.

### Benchmark B0 run 1 (1,022 of 1,226 at 05:40)
- **Run 1 is INVALID as a quality baseline.** Rows 112–732 measure the stuck breaker, not the pipeline.
- Since the restart, questions answer in 2–9 s.
- **Run 2 starts automatically under the watchdog and runs on the fixed code.** Use run 2 as the baseline.

## Checklist to production
Owner = 👤, agent = 🤖. Each item needs evidence before it's ticked.

### 1. Gold data: the only route to a ≥99% claim (👤 first)

- [ ] 👤 **Write about 500–600 real-seeker questions**, not 150 (correction to the earlier plan).
  - The file is `~/mukthiguru_attribution_data/gold_pilot/question_authoring_pilot.csv`, currently 0 rows.
  - Mix: 60% answerable, 20% near-miss, 20% unanswerable.
  - At most 3 questions per video, written without looking at the clips.
  - Include about 60 Indic-script questions. There are 0 today, so Indic retrieval is completely unmeasured.
  - **Why 500–600:** fixed-sequence Learn-then-Test needs at least 299 confident, human-labelled answers with 0 errors on held-out videos, and 150 questions cannot produce that. The alternative is an explicit owner decision to count up to 3 clips per question with a clustered bound.
- [ ] 🤖 Pool candidate clips for those questions from v2 (R0, plus one variant) into a relevance sheet. Show no silver labels.
- [ ] 👤 Label in the review UI at http://127.0.0.1:8088:
  1. Judge A labels relevance and `clip_quality`.
  2. Judge B labels blind (`--judge b`).
  3. Adjudicate (`--judge adjudicator`).
- [ ] 🤖 Report Cohen's κ, and keep a video-level held-out split (`evaluation/gold/split.py`).

### 2. Accuracy and calibration (🤖, after section 1)
- [ ] **Replace the confidence feature.** Top-1 dense cosine favours short fragments: they scored 0.72–0.78 against 0.62 for a real answer. Candidates:
  - a fine-tuned reranker score;
  - the top-1/top-2 margin;
  - clip length.
- [ ] **Fine-tune a small cross-encoder reranker** on the dev split with hard negatives, and compare it against R0 on held-out data. This replaces the audit's proposed LLM relevance grader, because an LLM verdict can't be calibrated to 99%.
- [ ] **Fit the calibrator:** `SelectiveRiskCalibrator` (fixed-sequence LTT, n_min=299) → `to_profile()` → set `FIRST_PERSON_CALIBRATION_PATH`. 👤 signs off the operating point (precision against coverage).
- [ ] **Report on the frozen held-out set:** precision, coverage and the Clopper–Pearson upper bound.
- [ ] **Re-test deferred modes on human gold before spending on them:**
  - the question field (R1). The earlier test was circular: questions and field were both generated from the same transcripts.
  - HyDE/LLM mode (R3). It measured no gain at 8–26 s per query.

### 3. Data pipeline hardening (🤖, with 👤 approvals)
- [ ] **Speaker labels.** This is the biggest quality defect visible in the UI; answers end mid-sentence, e.g. "…the more suffering we".
  - Interviews come out about 95% "host".
  - 75 of 114 answers end where the speaker label flips.
  - 👤 does a speaker audit on sampled clips.
  - 🤖 improves diarization (label smoothing, pyannote or WeSpeaker verification, a calibrated false-accept threshold).
- [ ] **Wire the offline pipeline into shared ingestion** (`ingest/`), not the pilot scripts. It covers:
  - the Parakeet + Whisper vote, with `speech_config` hardening;
  - the aligner;
  - ECAPA speaker verification;
  - clips v2;
  - the ASR-agreement gate (<0.80, provisional; 👤 confirms the threshold);
  - `transcript_hash` at every `EmbedIndexConfig` site;
  - the fixed `run_punct.py`.
- [x] Fix `run_punct.py`: 50/50 pilot and 8/8 bake-off pass (2026-09-26).
- [ ] 👤 **Approve the full-corpus compute plan**, then run all 745 videos. This is the biggest recall lever: 280 clips from 45 videos is the ceiling today. Rebuild `first_person_vN` twice to prove determinism.
- [ ] 👤 **Rights:** clear or reject each channel in `CONTENT-RIGHTS.md`. TEDx Talks and Marie Forleo are uncleared.
- [ ] 👤 **Ship the verbatim word layer in the image?** Doing so enables a serve-time substring check.
- [ ] 🤖 **Parent discourse bounds** (`parent_start/end_seconds`) for an "expand to full discourse" button. It needs an index rebuild (dry-run → report → snapshot → 👤 approval → apply). Expose only teacher-only spans.
- [ ] 🤖 **Indic queries:** measure dense-only BGE-M3 on the Indic gold questions. Add a bounded, cached translation call only if that fails; this is a 👤 decision because it puts an LLM on the serve path.

### 4. Serving and product
- [x] UI with `CitationCard`: `/teachers-words`, browser-verified 2026-09-26.
- [x] Redis exact cache + malformed-entry guard: live, 0.8 ms on a hit.
- [x] Alerts + dashboard: 4 rules loaded in Prometheus 2026-09-26.
- [ ] 👤 Weekly audit of 50–100 served answers, once internal users exist.
- [ ] 🤖 Load test the route at realistic concurrency (p95 under load; `native_inference_gate`).
- [ ] 👤 Rollout:
  1. Set `FIRST_PERSON_ROUTE_ENABLED=true` and `VITE_FIRST_PERSON_ENABLED=true` for internal users only.
  2. Canary.
  3. General.

  Roll back to v1 by setting `FIRST_PERSON_COLLECTION`. The alias ledger is `QdrantAliasManager(client).rollback_alias(alias)`.

### 5. Safety, rights and privacy gates (👤, per `GATES.md` G1–G5)
- [ ] **G1 Safety:**
  - clinician and native-speaker review of the crisis text in all 6 pilot languages;
  - helplines verified **by call** (`last_verified_by_call` is null; the backend logs a warning about it);
  - kill switch tested.
- [ ] **G2 Rights:** the register covers 100% of served sources; unregistered sources are blocked at serve time (default `FIRST_PERSON_SERVE_UNREGISTERED=false`).
- [ ] **G3 to G5, signed:**
  - G3 privacy (DPDP);
  - G4 cost cap and kill switch;
  - G5 pilot start.

### 5b. Found and fixed later on 2026-09-26 (uncommitted, live locally)
- [x] **First-person topic rail** (regex, no LLM) before retrieval. Politics, explicit and similar topics get the redirect; abuse and self-harm get helplines.
- [x] **First-person cache** re-checks that cited points still exist and are servable (`points_servable`).
- [x] **Tracing** includes `/api/first-person/query`.
- [x] **Chat grader** respects an explicit all-"no" verdict.
- [x] **`RLIMIT_DATA` root cause proven** (it counts virtual memory, thread stacks included). Local: limit off and `MALLOC_ARENA_MAX=2`.
- [x] **LLM breaker no longer trips on throttling** (L-BREAKER-THROTTLE-1).
- [x] **Indic rewrite cap enforced after reflection** (L-INDIC-REWRITE-1). Indic questions no longer loop twice.
- [x] **Chat `cyber_abuse` topic**: phishing, keygens, malware and credential theft are declined (the fix for `adv-017`/`adv-019`).
- [x] **`bench --mode all` honours `--out`**, and the watchdog's done-check is now the final `saved` line.
- [ ] 👤 **Railway:** set `PYTHON_MEMORY_LIMIT_MB=0` (today 5120) before the next deploy. It is the same crash class. **Must-fix before production** (independent review, 2026-09-26).
- [ ] 🤖 **Chat quality:** 55 quality-failure ids in `RUN1_POSTMORTEM.md` §5 (low coverage, faithfulness 0.0, misattribution). These need pipeline work, not a re-run.
- [x] **Crisis and topic rails see through obfuscation** (spaced letters, leetspeak, homoglyphs): `services/text_normalize.py`, red team 2026-09-26. Passive-ideation, medication-taper, "instead of therapy", "how do I build" and cracked-app patterns were added.
- [x] **Persona-escape (Hindi/Tamil/English), off-domain sports, fraud, credential and manifest-money prompts are declined.** These were run 1's abstention misses. No new false positives across all 1,226 benchmark questions.
- [x] **Qdrant parent-document search fixed.** The cluster filter was applied to leaf chunks, which never carry `cluster_id`.
- [x] **Scorer honesty:** a refusal that names the forbidden term is no longer a "contradiction", and evidence-window pagination means "unmeasured" is no longer reported on a full page.
- [x] **Clip builder never ends on a partial sentence at a speaker flip.** Dry-run: 61.3% → 3.9% mid-sentence, at a cost of 24% of teacher words.
- [x] **Verbatim pipeline ported to `backend/ingest/verbatim/`** (40 tests; one-video parity with the pilot output). It is not yet wired into `ingest/pipeline.py`.
- [x] **First-person load test and restore drill prepared, not run:** `docs/operations/drills.md`.
- [ ] 👤 **Decide:** SEVERE (non-suicidal) distress in chat gets a helpline-only redirect (`qa-safety-001`), while the benchmark expects Serene Mind engagement. This is crisis policy, so a clinician should weigh in.
- [ ] 👤 **Decide:** backfill `cluster_id` onto leaf chunks, which would enable cluster-scoped leaf retrieval. It is a Qdrant write, so dry-run → snapshot → approval.
- [ ] 👤 **Speaker audit:** interview voiceprint mismatch. `speaker_attribution.py` `COHORT_MAX=0.40` labels whole interview videos as host (4 videos at 0% teacher). A human listen comes before any threshold change.
- [ ] 👤 **Approve building `first_person_v3`** from the fixed clips (`clips_v3_dryrun/`).
- [x] **`golden_033`/`044`/`050` were a label bug, not a refusal.** Live: the full pipeline served a cited teaching, but intent DISTRESS forced `grounding_state=safety_redirect`, so the UI claimed safety guidance had replaced the doctrine. `app/grounding.py` now labels a cited, verified non-crisis distress answer `grounded`. Crisis and safety intents still redirect.
- [x] **Breaker stuck OPEN for 2 h (L-BREAKER-PHI-1):** the phi-accrual path opened it without a timestamp. The open time is now stamped. 259 instant `system_error` rows were re-queued; a smoke test of 10 of them passed 10/10.
- [x] **Distress grounding label:** a cited, verified answer is `grounded`, and a distress pre-emption stays `safety_redirect` (live-verified).
- [x] **Other-tool changes verified 2026-09-26:**
  - `build_first_person_index` apply would have crashed (`KeyError: point_id`) and would empty the collection on a 0-clip build. It now computes IDs the store's way and refuses an empty apply.
  - `transcript_verbatim`'s cache change silenced the "corpus root missing" error; restored.
  - The `qdrant_aliases` Diff conversion was checked against a real collection's config (no writes); only the test mock was fixed.
  - Suites: backend passing (after these fixes), frontend 666 passing, `tsc` clean.
- [x] **Context7 MCP** is installed at user scope and connected; a new session loads its tools. In this session the `ctx7` CLI and the `ecc:docs-lookup` agent cover lookups.
- [x] **Agent fixes, verified live 2026-09-26 (smoke 10/10, no system errors):**
  - Indic language comes from the message script when the client sends none. `golden_024` is now grounded and answered in Telugu.
  - Heading dedup compares heading text, not the raw line.
  - "Where is X located" is no longer a logistics cue. `golden_010` is grounded, faithfulness 1.0.
  - `faithfulness_score` is None (not 0.0) when verification never ran.
- [x] **Breaker wedge, real root cause (L-BREAKER-PHI-1 follow-up):** successes were never sent to the phi `HealthMonitor`, so 3 lifetime failures marked OpenRouter unhealthy forever and every recovery reopened on the next call. Both paths now send heartbeats; regression test added.
- [x] **`rewrite_query` could hang for 60 s and kill the node.** The gateway ran 30 s primary + 30 s model fallback, and the node's `t_out` was never applied. The whole rewrite is now bounded, and on any failure it reuses the original query.
- [x] **Jaeger dropped traces** (batches of 4.4–10.8 MB over the 4 MB gRPC limit, from LangChain node-state attributes). Defaults are now `OTEL_SPAN_ATTRIBUTE_VALUE_LENGTH_LIMIT=4096` and `OTEL_BSP_MAX_EXPORT_BATCH_SIZE=32`; an env value overrides them.
- [x] **Verbatim-excerpt fallback showed an LLM chunk summary as the teachers' words** (`[Context: This chunk highlights…]`, `mul-012`). The excerpt path now strips contextual headers through the shared `rag.doc_utils.strip_contextual_artifacts`, which `contextual_reingest` also uses, and skips documents with unterminated headers.
- [ ] 🤖 **`golden_028` (Kannada) still abstains** and falls back to an English verbatim excerpt. The grader rejected documents that do contain "the Four Sacred Secrets". This is part of the quality-id work.
- [ ] 👤 **Decide:** for Indic seekers, should a verbatim excerpt fallback carry a translated framing? Translating the quote itself risks misquoting.
- [ ] 🤖 **Existing broad patterns:** "cope with a health diagnosis" (medical rail) and "affiliated with any political party" (politics rail) block legitimate questions. Tighten them only with owner sign-off.
- [ ] 🤖 **Verification re-run `retry1`**, PAUSED at 523/1226 (after the breaker wedge; `com-011` re-queued, checkpoint backed up). Resume with `~/mukthiguru_attribution_data/watchdog.sh` after the owner's go-ahead. Rows 1–516 ran on pre-fix code. Decide on a full run 2 after it finishes.

### 6. Platform (🤖 evidence, 👤 sign-off; spec phase P)
- [ ] **Rebuild the production images.** The `Dockerfile` and `Dockerfile.railway` changes (helplines COPY) only reach Railway on the next image build. Railway is scaled down today.
- [ ] Railway boots with no OOM; restart-on-hang is proven; health probes test executability.
- [ ] Backups plus a restore drill (Qdrant snapshot restore, including `first_person_v*`); alias rollback tested.
- [ ] Deployment config matches repo HEAD; security, RLS, rate-limit and secret checks pass.
- [ ] Jaeger sits at 99% of its 256 MB limit with unbounded span storage. Bound it or raise the limit (tracing loss only).
- [ ] Qdrant `query_points_groups` (parent-document group search) returns 0 groups on every call and falls back to a flat search. Audit the grouping key and payload index.
- [x] Live graph topology verified: Memgraph; 4,030 of 4,197 edges are generic `DIRECTED` (read-only, 2026-09-26).

### 7. Housekeeping
- [ ] 🤖 B0 run 2 finishes → compare with `rescore_report` plus a clustered bootstrap diff CI. Use run 2 as the baseline; mark run 1 INVALID (breaker outage).
- [x] Prompt audit A1–A4, B1, B2 applied (2026-09-26).
- [ ] 👤 Prompt audit A5/A6: needs an A/B on the golden bank.
- [ ] 🤖 Chat citations: wire `speaker_verified` (a voice-verification backfill) so a verified speaker can be shown in chat (see `lessons.md` L-TEACHER-TAG-1).
- [x] `evaluation/session_pool.py` decided: must NOT be wired in; the reason is in its docstring and in L-BENCH-POOL-1 (2026-09-26).
- [ ] 🤖 Unwired module to decide: `services/retrieval_integrity.py`.
- [ ] 👤 **Commit the working tree in logical chunks.** About 50 files are uncommitted; main is 12 commits ahead of origin.
- [ ] 👤 **Discard the stale UI-agent worktree** `.claude/worktrees/agent-abd54642689453aa3`; its useful files are already ported.

## Prompt for the next session (copy-paste)
```
Continue the AskMukthiGuru first-person verbatim route toward production in /Users/harshodaikolluru/Public/askmukthiguru-8119b0e8.

Read first, in full: docs/agent/NEXT_PROD_READY.md (checklist, what's done), handoff.md, docs/agent/FIRST_PERSON_AUDIT_RESPONSE_2026-09-26.md, docs/agent/NON_NEGOTIABLES.md, docs/agent/GATES.md, docs/agent/first_person_baseline_prompt.md, docs/agent/B1_gold_set_protocol.md.

Rules:
- No git commit or push unless I ask.
- Every Qdrant, OKF or graph write goes dry-run → report → snapshot → my approval → apply.
- Never fabricate gold labels, quotes, timestamps or speakers: labels come only from humans.
- Crisis detection stays in front of the first-person route; no semantic cache on it; no LLM at serve time unless I approve it.
- Check job liveness with `pgrep -fl`, never `ps | grep`.
- Mock services with `create_autospec`.
- Don't use worktree-isolated agent types on uncommitted files.
- Report each claim as VERIFIED / UNVERIFIED / NOT RUN with evidence.

Start by checking live state:
- B0 run 2 (`~/mukthiguru_attribution_data/baseline_2026-09-25/run2.checkpoint.jsonl`, watchdog.log);
- backend health and `guru_circuit_breaker_state`;
- whether I've written gold questions or labels (`gold_pilot/`).

Then work the checklist top-down, taking the first unticked 🤖 item whose 👤 prerequisites are met. Use TDD with failing-first tests, and mutation-check every safety gate. After each item: the full backend suite, `npx vitest run`, the live eval (backend/scripts/ops/first_person_live_eval.py), and update this checklist and handoff.md.
```
