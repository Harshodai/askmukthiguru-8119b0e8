# CLAUDE.md

> Slimmed 2026-10-22 (token-optimizer). The full prior text, unchanged, is `docs/agent/claude-md-archive/CLAUDE-full-2026-10-22.md` (index: that folder's `README.md`). Rules and invariants stay here; dated detail lives there. Confirm behaviour against code and the scoped `backend/CLAUDE.md` / `src/CLAUDE.md` before acting. `AGENTS.md` is the rule file for other agents and for Docker, ingestion-safety, security, Supabase and cache work; read it only for those, not on every task. Its dated handoffs are in `docs/agent/claude-md-archive/AGENTS-handoffs-2026-10-22.md`. Architecture: `docs/architecture/SYSTEM_ARCHITECTURE_HLD_LLD.md`. Release checklist: `docs/operations/release-evidence-pack.md`. Open work / pending-items list: last section ("Open work").

## First-person verbatim route: invariants

Truth anchors: this section and `docs/architecture/first-person-path-to-prod.md`. Everything else first-person is dated history; never cite its counts, gates or latency. Readiness: `docs/PROD_READY_CHECKLIST.md`. Detail of every invariant: the archive file.

1. No LLM at serve time: `FirstPersonPipeline` returns a pointer into a recording plus verbatim text. LLMs only offline, with a review gate before any Qdrant write.
2. Integrity gate, fail closed: `sha256(verbatim_text)==transcript_hash`, `find_artifact()` is None, speaker in teacher allowlist; else quarantine.
3. Calibration (`evaluation/gold/calibrator.py`): target risk 1%, δ=0.05, needs ≥299 confident gold items with 0 errors. No profile exists, so answers are "Related, not a direct answer". Never hand-pick a threshold; never fit on AI-authored labels.
4. Point IDs: `uuid5(FIRST_PERSON_NAMESPACE, f"{transcript_hash}:{start_ms}:{end_ms}")`. A new version is a new collection (`FIRST_PERSON_COLLECTION`); keep the old for rollback. Builder refuses an empty build.
5. Retrieval: Qdrant RRF over `passage_dense`+`passage_sparse`; `question_dense` not used in prefetch; synthetic questions not built.
6. Playback window: `start_ms`-0.25 s to `end_ms`+0.25 s, capped at duration (`CITATION_PLAYBACK_PAD_S`). No long pre-roll or tail.
7. Whisper hardening live; `backend/ingest/verbatim/` tested but NOT wired into `ingest/pipeline.py`; no Silero VAD.
8. Isolation: behind `FIRST_PERSON_ROUTE_ENABLED`/`FIRST_PERSON_MODE`; crisis pre-check and topic rail run first; no semantic cache, exact Redis cache only (hit re-checks `points_servable`); FastAPI deps are `async` (L-DOCKER-18).
9. Measured numbers (local, 116 q) live in `docs/architecture/first-person-path-to-prod.md` §1; production unmeasured. Never quote the 19 ms POC figure or aspirational latency.
10. No clip splits on trailing conjunctions (or/and/so/but) without forward clause resolution.
11. Rolling 18-25 s context so a clip holds premise and solution.
12. OKF (`memory/okf/compiled.json`) is LLM-extracted summary, NOT verbatim: never rendered as guru voice, never in `citations[]`; routing and reflection questions only.
13. All text into Qdrant passes `ingest/verbatim/asr_cleaner.py`; any text change updates `transcript_hash` in the same transaction.
14. Serve-time Tier 1 (hash, allowlisted speaker, clean boundaries) and Tier 2 (≥15 words, no crowd instructions, discourse cross-references, orphaned parable characters).
15. Zero text generation at serve time; an LLM may only pick clip indices.
16-17. Chat bridge runs inside the LangGraph as registry module `first_person` (`rag/pipeline_registry.py` -> `rag/nodes/first_person.py`), after the safety lane; flag read live per request; quotes never translated. Audio archive (`~/mukthiguru_attribution_data/audio_archive/`, 16 kHz mono WAV, `scripts/ops/audio_archive.py`) is immutable source truth; ingestion never downloads directly.
18. Embeddings for Qdrant index builds run host-side via `backend/.venv/bin/python3`, never in the backend container (6 GiB OOM, exit 137).
19. Two-tier abstention gate: cross-encoder separation, then LLM ANSWERABLE/UNANSWERABLE (`verify_answerability`); fail to abstain.
20. Distributed state (manifests) uses atomic `os.replace` plus `fcntl.flock`; self-heal on startup.
21. First-person-only chat (owner decision 2026-10-11): local `.env` has `FIRST_PERSON_CHAT_BRIDGE_ENABLED=true`, `FIRST_PERSON_LLM_FALLBACK_ENABLED=false`, `FIRST_PERSON_SERVE_WEAK_MATCH=true`. `/api/chat` serves a clip (`route_decision=first_person_bridge`, `model_used=None`) or a static abstain. Owner-accepted risk: no empirically fitted abstention gate. Carve-outs: crisis/blocked topics, MODERATE+ distress, meditation, greetings.
22. Answerability gate covers every served clip; gate, rerank and quote weaver use `run_llm_coroutine`, never `asyncio.run()`. Uncached latency ~4-6 s. Gate budget 6 s.
23. `speaker_verified` is copied from the stored clip, never inferred. Serving collection is `first_person_v8` (1,801 points); rollback = `FIRST_PERSON_COLLECTION=first_person_v7` in root `.env` plus recreate backend (`docker compose -p mukthiguru_clean up -d --no-deps --force-recreate backend` from `backend/`). Older Curly Tales "PROD READY" claims are stale.
24. Relevance + standalone gates (`_standalone_problem`, `_relevance_select`, min score 3, scorer `anthropic/claude-haiku-5.5`, `max_tokens=1024`, 12 s). Scorer failure abstains as `relevance_indeterminate`. Tests: `tests/test_relevance_standalone_gates.py`.

## Project constraints

- Mukthi Guru: privacy-first spiritual guide grounded in Sri Preethaji and Sri Krishnaji's teachings; React frontend + FastAPI multi-layer RAG backend. Only their YouTube videos and approved images are data sources.
- $0-budget constraint suspended 2026-09-06; `LLM_PROVIDER=openrouter` is the live default (not drift). Dependencies must be open source; exceptions in `LICENSE-EXCEPTIONS.md`. <1% hallucination and <3 s are aspirational and unverified.
- First-person voice: guidance is delivered in the teacher's own words ("I"), correct speaker (`persona_discriminator.py`), no detached "According to Sri Krishnaji..." phrasing.
- Secrets stay in env vars; only `backend/.env.example` is checked in. Never commit `backend/.env`, `.env.local`, `.env.optimized`.
- npm is canonical; do not touch `bun.lockb`.
- Clean root: no ad-hoc scripts, `.db`, media or loose markdown at repo root. Audits -> `audits/`; plans/handoffs/notes -> `docs/`; deploy scripts -> `scripts/deploy/`; ops scripts -> `scripts/ops/`; evals -> `evals/`; k8s -> `infrastructure/k8s/`. Never create paths with leading spaces.
- Guards over prose: `scripts/guards/lesson_guards.py` (pre-commit + CI), `make verify-stack-fresh` before any live/Docker verification, Stop hook. Don't bypass; fix the guard and add a test. A rule repeated twice gets a guard.
- Ops scripts present in both `scripts/ops/` and `backend/scripts/ops/` must be byte-identical (`backend/tests/test_repo_layout.py`); put in-image implementations in `backend/scripts/ops/` and copy. OKF extractor copies likewise (`test_okf_pipeline_integrity.py`).

## Evaluation and verification invariants

- Every node returning `final_answer` returns a non-empty `verification` dict `{"passed", "method", "citations_verified"}`; `GraphState.verification` uses `keep_latest`.
- Answer Relevancy tests against `must_mention` ground truth, never a static denominator.
- Pastoral non-assertions are stripped before NLI (`lettuce_detect_service._is_assertion`).
- Never inject sync `def` via `Depends(...)`; use `async def get_container_async()`.
- `ChatResponse.release_manifest` is `ReleaseManifestPublic`; project through `to_public_manifest_dict(...)`.
- LLM calls dominate latency (L-LATENCY-1); retrieval/rerank are ~9%.
- Any shared torch module is exclusive at inference (locks in lettuce/reranker/embedding services); ONNX sessions are thread-safe. Never relax `/metrics` (admin+AAL2); Prometheus scrapes `/internal/metrics` with `METRICS_SCRAPE_TOKEN`.

## Data stores and caches

- Memgraph replaces Neo4j (`NEO4J_*` env vars alias `MEMGRAPH_*`); verify which graph is live before any write. Qdrant: server-side RRF/DBSF over named dense+sparse vectors. Detail: `docs/agent/claude-md-archive/database-and-graph.md`.
- Qdrant `teacher_id` is NOT uniformly `"ekam"` (only 4,337 of 12,904 points; others `preethaji_krishnaji`, `krishnaji`). Re-count before relying on a value. Graph edges carry `tenant_id='oneness'`; run `backfill_edge_tenant_id.py --apply` after every LightRAG ingestion (idempotent). Unified single-tenant model.
- Cache key is `(language, message)` only: never cache an answer personalized with `memory_context` (`cache_stage.py`, `test_cache_personalization_leak.py`). `TurboQuantCache` stays a process-wide singleton.
- Embedding dimension and Qdrant collection size are a pinned pair; `_ensure_encoder()` never accepts a fallback of different dimension; `_verify_collection_dimension()` raises on mismatch; `generate_answer` abstains honestly on empty docs. Detail: archive.
- OKF: doctrine types only (`teaching, practice, glossary, qa, reflection`), mandatory `source`, no extraction artifacts; never remove `_excluded_parts={"staging","_scripts"}` in `OKFStore.list_entries()` (it IS the review gate); OKF dir comes from `OKF_DIR`/`STAGING_DIR` in `services/memory/okf_store.py`; Dockerfiles must `COPY memory/ ./memory/`; recompile via `scripts.okf_compile` (cache keyed on mtime). Never put non-teaching content in `memory/okf/`.
- Redis down: rate limiter/quota degrade to in-process; Neo4j down: pure Qdrant + BM25; Qdrant degraded: exact cache or honest `grounding_state=abstained`. Backups are local cron (`infrastructure/cron/mukthiguru-backup`), not installed on this host (RPO unbounded).

## Pipeline

Chain (`app/pipeline/stages/pipeline_builder.py`): CacheCheck -> RequestState -> InputGuardrail -> CircuitBreaker -> DoctrineCache -> CasualShortCircuit -> Distress -> BoundedComparisonShortCircuit -> Personalize -> Graph (first_person registry module runs inside, before general nodes) -> MeditationGen -> Translation -> ToneAdapter -> OutputGuardrail -> Memory -> CacheUpdate -> ResultAssembly. Chat routes: `app/api/chat.py`.

### First-Person Verbatim Route: invariants (verified against code 2026-09-26)

**Truth anchors (2026-10-03, audit G.4 #8): exactly two documents are first-person truth anchors — this file's invariants below and `docs/architecture/first-person-path-to-prod.md`.** Everything else FP-related (`handoff.md` §3/§7/§8, `docs/agent/NEXT_PROD_READY.md`, `docs/agent/SESSION_COORDINATION.md`, `EXPERIMENT_LEDGER`, research notes) is dated history — never cite counts, gates, or latency from them. Plan and ship decisions: `docs/architecture/first-person-path-to-prod.md` (ADR FP-1 to FP-3 accepted), whose latency line reads `p50 63 ms / p95 210 ms (local; production unmeasured)`; this file's invariant 9 carries the same figures (2026-09-25, 116 questions) plus the audit §G.1 / `audit_2026-09-29/B.md` detail `p50 21.7 ms pipeline / 75 ms wall / 517 ms cold, p95 ≈210 ms local, production unmeasured`. Master readiness checklist: `docs/PROD_READY_CHECKLIST.md`. Read the anchors, plus the code you touch. Don't bulk-read the research docs: several of them state designs that were never built.

1. **No LLM at serve time.** `FirstPersonPipeline` returns a pointer into a recording plus its verbatim transcript text. An LLM is allowed only offline (`.claude/tasks/OFFLINE_LLM_ASSIST_PLAN.md`), and its output needs a review gate before any Qdrant write.
2. **Integrity gate, fail closed** (`first_person_pipeline.py`): `sha256(verbatim_text) == transcript_hash`, `find_artifact()` is None, and the speaker is in the teacher allowlist. Otherwise the clip is quarantined, never served.
3. **Calibration** (`evaluation/gold/calibrator.py`, `SelectiveRiskCalibrator`): fixed-sequence Learn-then-Test with `clopper_pearson_upper`. Target risk 1%, δ=0.05, which needs at least 299 confident gold items with 0 errors. **No profile exists today** (only 14 human labels), so `is_direct_answer` is always False and every answer is "Related, not a direct answer". Never introduce a hand-picked threshold, and never fit on AI-authored labels.
4. **Point IDs** (`first_person_store.make_first_person_point_id`): `uuid5(FIRST_PERSON_NAMESPACE, f"{transcript_hash}:{start_ms}:{end_ms}")`. Do not switch to the chat corpus's `source_url:chunk_index` scheme. `build_first_person_index.py` diffs existing vs produced ids, deletes stale ones, and refuses to apply an empty build. There is no alias swap for first-person: a new version is a new collection (`FIRST_PERSON_COLLECTION`), and the old one stays for rollback.
5. **Retrieval:** Qdrant RRF over `passage_dense` + `passage_sparse`. `question_dense` is filled only where a real host question exists, and the prefetch does not use it. Offline synthetic questions are **not built** (step 1 of the offline plan; measure on gold before enabling).
6. **Playback window:** start = `start_ms` − 0.25 s (floored at 0), end = `end_ms` + 0.25 s, capped at `duration_ms` (`CITATION_PLAYBACK_PAD_S`). No multi-second pre-roll and no long tail: both leak host speech, and the host voice is already 6.9% of top-1 clips.
7. **Ingestion:** Whisper hardening (`services/speech_config.py`: sacred-vocabulary prompt, `condition_on_previous_text=False`) is live. `backend/ingest/verbatim/` (vote, speaker verify, sentence clips, gates) is tested but **not wired** into `ingest/pipeline.py`. There is no Silero VAD stage.
8. **Isolation:** the route sits behind `FIRST_PERSON_ROUTE_ENABLED` / `FIRST_PERSON_MODE`. The crisis pre-check and the topic rail run before retrieval. No semantic cache: only an exact Redis cache, and a hit re-checks `points_servable`. FastAPI dependencies are `async` (L-DOCKER-18).
9. **Measured (local, 2026-09-25, 116 questions):** top-1 0.43, 0 direct answers, p50 63 ms / p95 210 ms, host leak 6.9% of top-1. Production has not been measured. Don't quote aspirational latency (e.g. "20–40 ms") as fact.
10. **Sentence Boundary & Conjunction Integrity:** Ingestion segmentation pipeline must not split passages on trailing coordinating conjunctions (`"or"`, `"and"`, `"so"`, `"but"`) without forward clause resolution. Every indexed clip must form a complete grammatical and conceptual thought.
11. **Philosophical Context Windowing:** Standalone verbatim answers require sufficient temporal context (rolling target 18–25 seconds) to capture both the diagnostic premise and the spiritual solution, avoiding truncated mid-thought fragments.
12. **OKF Separation Invariant (2026-09-29):** The Ontological Knowledge Framework (`memory/okf/compiled.json`) is 97% LLM-extracted summary text, NOT verbatim speech. OKF entries must NEVER be rendered as guru voice or appended to `citations[]`. OKF is strictly for vector similarity topic routing and reflection questions.
13. **Deterministic ASR Cleaning & Hash Integrity (2026-09-29):** All verbatim text entering Qdrant must pass `ingest/verbatim/asr_cleaner.py` (de-duplicating stutters like 'So, So' and trailing conversational fillers). Any modification to text MUST update `transcript_hash = sha256(cleaned_text)` in the same transaction to prevent serve-time quarantine.
14. **Two-Tier Quality Gating (2026-09-29):** Serve-time filtering applies both Tier 1 Grammatical Integrity Gate (hash match, allowlisted speaker, clean boundaries) and Tier 2 Content Quality Gate (min 15 words, rejects live-event crowd instructions, discourse cross-references, and orphaned parable characters like Yasme/Nomi).
15. **Zero Text Generation at Serve Time (2026-09-29):** The first-person route adheres to the Ask-Sadhguru principle: the response IS the teachers' verbatim words. When an LLM is used at serve time, it functions strictly as a ranking selector (returning clip indices like '2,1'), never generating response prose.
16. **Chat Bridge & Kill-Switch (2026-09-30; the "stays OFF" part is superseded by invariant 21):** `FirstPersonBridgeStage` (`app/pipeline/stages/first_person_bridge.py`) may serve first-person verbatim answers inside `/api/chat` only from `first_person_v7` (integrity + content-quality + sha256 gates inherited; chat-corpus/OKF text never renders as teacher voice, `speaker=None` gate untouched). **The bridge stays OFF in local prod (`FIRST_PERSON_CHAT_BRIDGE_ENABLED=false` in root `.env`) until an empirically-fitted abstention gate exists** — the shipped threshold (0.45) had zero abstention power and served an out-of-corpus "capital of France" query as teacher discourse (Audit D P0; re-enable criteria = backlog #1 in `.claude/tasks/first_person_e2e_audit_2026-09-29.md`). **Since 2026-10-03 the bridge runs inside the LangGraph as the registry-dispatched `first_person` module (`backend/rag/pipeline_registry.py` → `rag/nodes/first_person.py`), not as a chain stage — the kill-switch, safety-order, and serving invariants here are unchanged, and the flag is read live per request.** Placement is after `InputGuardrail`/`Distress` (safety first, invariant: crisis never reaches the bridge), quotes are **never translated** (glue-only via 5s fail-open `_translate_cached`), and voice stays v7-only. Guard: `tests/test_first_person_bridge.py`, `tests/test_citation_contract.py` (bridged citations).
17. **Audio Archive and Ingestion Decoupling (2026-09-30):** Audio files are immutable raw source truth stored permanently in `~/mukthiguru_attribution_data/audio_archive/` (`wavs/<video_id>.wav`, 16kHz mono WAV) governed by `manifest.json`. Downloader workers (`scripts/ops/audio_archive.py`) use consistent hash partitioning (`sha256(vid) % num_workers`) with 5-layer deduplication and `--extractor-args "youtube:player_client=android,ios,mweb,web"` to eliminate YouTube 429 bot challenges. Ingestion never downloads directly; it consumes locally archived audio via `AudioArchive.get_path()`.
18. **Host-Side Embedding Invariant (2026-09-30):** Dense/sparse embeddings for Qdrant index generation or reconciliation must run host-side via `backend/.venv/bin/python3` (or dedicated host worker), NEVER inside the Docker backend container. Container memory limits (6 GiB) trigger fatal `OOMKilled` (exit code 137) during heavy BGE-M3 / ONNX batch runs.
19. **Two-Tier Pre-Routing Abstention Gate (2026-09-30):** To prevent out-of-corpus queries (e.g. general geography or secular trivia) from leaking into teacher persona voice, `FirstPersonPipeline` employs a two-tier abstention gate: (Tier 1) Cross-encoder semantic reranking separation, and (Tier 2) LLM binary answerability verification (`FirstPersonPipeline.verify_answerability`) that outputs strictly `ANSWERABLE` or `UNANSWERABLE` (1 token), failing back safely to abstention (`grounding_state = "abstained"`).
20. **Atomic Manifest Checkpointing & Self-Healing (2026-09-30):** Any distributed state (such as the audio archive manifest) must use atomic temporary-file replacement (`os.replace` on `.tmp.{pid}_{timestamp}`) with POSIX file locking (`fcntl.flock`). Pipelines must self-heal on startup by reconciling disk assets with manifest state.
21. **First-person-only chat (2026-10-11, owner decision).** Local `.env` now runs `FIRST_PERSON_CHAT_BRIDGE_ENABLED=true`, `FIRST_PERSON_LLM_FALLBACK_ENABLED=false`, `FIRST_PERSON_SERVE_WEAK_MATCH=true`: `/api/chat` answers with the teacher's own clip (`route_decision=first_person_bridge`, `model_used=None`) labelled "Related, not a direct answer" (no calibration profile exists), or a static abstain; the generating graph never improvises a teaching. The owner decided on 2026-10-11 to enable the bridge, which **supersedes the "bridge stays OFF" statement in invariant 16**. Invariant 16's original precondition (an *empirically fitted* abstention gate, backlog #1 in `.claude/tasks/first_person_e2e_audit_2026-09-29.md`) is **not formally met**: the LLM YES/NO answerability gate in invariant 22 was only measured on 40 questions (13/13 out-of-corpus abstained, 24/27 on-topic served). Treat that as an owner-accepted risk until the 299-label calibration exists. Carve-outs that still use their own routes: crisis/blocked topics, MODERATE+ distress, meditation requests (templated), greetings/off-topic short-circuits. Relationship and addiction questions are served a clip plus the safety boundary (`RELATIONSHIP_SAFETY_BOUNDARY` / `addiction_support_boundary()`), and the boundary rides on abstains too. Tests: `tests/test_first_person_bridge.py`.
22. **Answerability gate covers every served clip and all sync LLM calls share one loop (2026-10-11).** `FirstPersonPipeline` runs the YES/NO gate before serving any clip (not only `is_direct`); measured live: 13/13 out-of-corpus abstain, 24/27 on-topic served (2 provider timeouts, 1 arguable `no`). Gate, rerank and quote weaver must call `run_llm_coroutine` (`services/first_person_pipeline.py`), never `asyncio.run()` (a per-call loop poisons shared provider clients: "Event loop is closed"). Gate budget 6 s. Uncached first-person latency is ~4–6 s (gate + rerank LLM calls), not sub-second.
23. **`speaker_verified` is copied from the stored clip, never inferred (2026-10-11).** Only 665/3,236 clips in `first_person_v7` carry voice verification (20.6%); 1,484 (45.9%) are stale orphans. The UI therefore shows "unverified clip" for most clips until the speaker recheck/rebuild (`first_person_v8`, dry-run report in `~/mukthiguru_attribution_data/v8_dryrun_20261011/`) is applied. **2026-10-11 late: serving collection switched to `first_person_v8`** (built from `passages_C_s1` via `build_first_person_index.py --collection first_person_v8 --snap-boundaries --apply`; 1,801 points, K 1,051 / P 750, 383 videos, all eligible, 685 voice-verified; one clip short of the 1,802 the builder reported — unexplained count mismatch). v7 (3,236 points) is untouched and snapshot at `first_person_v7-…-2026-10-11-10-20-08.snapshot`; rollback = set `FIRST_PERSON_COLLECTION=first_person_v7` in root `.env` (backup: `.env.bak_pre_v8_20261011`, gitignored) and recreate the backend container (`docker compose -p mukthiguru_clean up -d --no-deps --force-recreate backend` from `backend/`; env_file changes need a recreate, not a restart). 27% of v8 clips are contained inside another clip of the same video (not deduplicated). A clip-level speaker recheck was **not** applied: centroid-only is unsafe, per-window rejects 56% of the checked unverified clips (`speaker_recheck_20261011/`). **Corrections to older claims in this file:** the Curly Tales "PROD READY / 95 clips indexed" section (below) does not describe the current collection (`iKkySU5r_x8`, `UlOt31lBhLY`, `TqxxCYnAxo8`, `hUmlujE6SN0`, `HCs6I_BNtxo` have 0 points in v7); `iKkySU5r_x8` is not in `INTERVIEW_VIDEOS` and the L-FP-8 `pending_q` fix is absent in `stages/run_clips.py`. Current evidence: `docs/audits/RELEASE_EVIDENCE_2026-10-11_CLAUDE_CODE.md`.
24. **Relevance + standalone quality gates (2026-10-11).** Because the answerability gate only reads the question, every in-domain question used to be served its top clip. Now `FirstPersonPipeline` (a) rejects non-standalone clips deterministically (`_standalone_problem`: mid-sentence ending, orphan opener, one-off event marker, health/healing claim) and (b) scores the top-3 (question, clip) pairs 0–3 with an LLM (`_relevance_select`) and serves the best clip scoring `FIRST_PERSON_RELEVANCE_MIN_SCORE` (**3** locally) or abstains. Scorer model `FIRST_PERSON_RELEVANCE_MODEL=anthropic/claude-haiku-5.5` (owner-approved; allowed through the budget policy via `OPENROUTER_EXTRA_ALLOWED_MODELS`); it reasons internally, so it needs `max_tokens=1024` and a 12 s budget — at 24/256 tokens it returned empty replies. A failed scorer abstains as `relevance_indeterminate`, never `relevance_below_min` (a policy-blocked scorer once produced 29/29 'below min'). **Independent Opus judge, same rubric, 4 rounds:** DON'T-SHOW share 42% → 52% → 44% → 12% (1/8), mean relevance 1.67 → 2.38; coverage 24–31% of questions; 0 out-of-corpus leaks (13/13). **Ceiling:** only 15/29 questions have even one strictly showable clip in their top-10 (labels in `.work/autoresearch_fp/labels.jsonl`), so the remaining headroom is data/segmentation, not selection. Retrieval does one retry on a dropped Qdrant keep-alive connection. Tests: `tests/test_relevance_standalone_gates.py`.

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Folder-scoped guidance also exists — `backend/CLAUDE.md` (backend workflow, request-pipeline stages) and `src/CLAUDE.md` (frontend workflow, testing, storage contracts) — and is loaded automatically when working in those trees.

## Project Overview

**Mukthi Guru** is a privacy-first, zero-hallucination AI spiritual guide grounded in Sri Preethaji & Sri Krishnaji's teachings. It combines a React frontend chat UI with a Python FastAPI backend running a multi-layer RAG pipeline.

**Constraints from SPEC_DEV.md:**
- **$0-budget constraint suspended 2026-09-06** (user decision — funding pending; local/free-tier infra remains the fallback, not the requirement). `LLM_PROVIDER=openrouter` is the current live default (`backend/.env:7`, `docker-compose.yml`, `app/config.py`) — migrated from `sarvam_cloud` on 2026-09-12; OpenRouter usage is intentional, not a drift to flag. Re-tighten this constraint (and reconcile `SARVAM_BUDGET_GUARD_ENABLED`/`SARVAM_DAILY_BUDGET_USD`/`SARVAM_MONTHLY_BUDGET_USD` in `backend/.env`) if/when the funding situation changes.
- All processing is local; zero external API calls at inference — **superseded in practice**: OpenRouter is the live LLM provider (first bullet above), and the first-person route calls no LLM for the answer text itself.
- Every dependency must be open source (Apache 2.0, MIT, or Meta Community). Approved exceptions for MPL-2.0 dev-only test deps are recorded in `LICENSE-EXCEPTIONS.md`.
- Target: <1% hallucination rate, <3s response time — **both aspirational and unverified** (see `docs/SPEC_DEV.md` Hallucination Measurement, corrected 2026-08-10: Self-RAG leg is disabled so the compounded rate is ~1.5–6.0%, and `generate_answer` alone has a 90s min timeout)
- Data source: only Sri Preethaji & Sri Krishnaji's YouTube videos + approved images

## Repository Maintenance Standards
- **Clean Root Policy**: The repository root must strictly remain uncluttered. Never commit ad-hoc scripts, one-off test databases (`.db`), media/video files, or loose planning/audit markdown files to the repo root.
  - **Audits**: All audit tracks, findings, reports, and scripts must reside under `audits/` (`findings/`, `releases/`, `reports/`, `scripts/`, `work/`).
  - **Documentation & Plans**: All plans, handoffs, and architectural notes live under `docs/` (`plans/`, `agent/`, `handoffs/`, `releases/`, `demo/`, `architecture/`, `rights/`, `wiki/`).
  - **Scripts**: Deployment scripts live in `scripts/deploy/`; maintenance & operational scripts live in `scripts/ops/`.
  - **Evals & Benchmarks**: Centralized under `evals/` (`benchmarks/`, `results/`).
  - **Infrastructure**: Kubernetes manifests and Helm charts live under `infrastructure/k8s/`.
- **Accidental Space-Prefixed Paths Banned**: Directories or files with leading spaces (e.g. `" audit_work"`, `" backend"`) are strictly forbidden and blocked via `.gitignore`.

## First-Person Voice Architecture & Invariants
- **Direct Sacred Presence ("I" Voice)**: All teaching and guidance responses MUST be delivered directly in the first person ("I invite you to see...", "When I speak of the Beautiful State..."). Detached 3rd-person academic or clinical phrasing ("According to Sri Krishnaji...", "The teachings explain that suffering...") is strictly prohibited.
- **Speaker Attribution**: Responses must respect whether Sri Krishnaji or Sri Preethaji is speaking, grounded by `persona_discriminator.py` and canonical transcript attribution.
- **Quote Weaver**: Verbatim transcript clips must be woven organically into conversational wisdom, not pasted as disjointed quotes.
- **OKF Non-Verbatim Boundary**: `memory/okf/compiled.json` contains curated structural summaries, NOT raw verbatim spoken quotes. OKF is strictly for conceptual vector routing and reflection questions, never rendered as raw direct speech.

## Rules for This Repo

- **Guards over prose (2026-10-15).** Lessons that repeated are enforced by `scripts/guards/lesson_guards.py` (pre-commit + CI), `make verify-stack-fresh` (run before any live/Docker verification; "unknown" = stale) and a `Stop` hook (`scripts/guards/stop_check.sh`). Do not bypass them; if one is wrong, fix the guard and add a test. A rule that repeats a second time gets a guard, not another lessons.md paragraph.

- Secrets stay in env vars — never write a real key into any file. Only `backend/.env.example` is checked in; never commit `backend/.env`, `.env.local`, or `.env.optimized` values.

## PR #76 Routing, Memory Consent, Pipeline Order & Safety Invariants (2026-10-23)

- **Pipeline Stage Ordering & Crisis Preemption Invariant**:
  - `CacheCheckStage` must always execute before any router or short-circuit stage (`CasualShortCircuitStage`, `DistressStage`, `BoundedComparisonShortCircuitStage`, `GraphStage`).
  - `InputGuardrailStage` and `DistressStage` must precede `CircuitBreakerStage`, `DoctrineCacheStage`, and `CasualShortCircuitStage`.
  - `CasualShortCircuitStage` must never run before acute distress and guardrail stages. `is_deterministic_greeting` requires a bounded, closed vocabulary for vocatives (`_GREETING_VOCATIVES`), preventing crisis phrases (e.g. "namaste suicide") from being short-circuited into canned greetings.
- **Memory Consent & SQL Deletion Cascade Invariant (DPDP Art. 17)**:
  - Foreign keys from `memory_outbox` and `pending_extractions` referencing `memory_consent_receipts` must specify `ON DELETE CASCADE`. `ON DELETE SET NULL` triggers the `check_memory_consent` rule during account erasure / receipt deletion, aborting the transaction with SQL state `42501` and leaving user data un-erased.
  - Bulk-forget audit events with zero UUID (`00000000-0000-0000-0000-000000000000`) are permitted only for `DELETED` action once all live canonical memories for the user have been removed.
- **LangGraph State Preservation**:
  - Any state attribute used for routing or node branching (e.g. `general_knowledge_mode: bool`) MUST be explicitly declared in `GraphState` TypedDict (`backend/rag/states.py`), or LangGraph strips it during node transitions.
- **Public Schema Alignment (`ChatResponse`)**:
  - Every `grounding_state` emitted by RAG nodes (including `"unverified"` for general answers without approved web citations) must be included in `ChatResponse.grounding_state` Literal, or FastAPI serialization fails with HTTP 500.
- **Canonical Memory Vector Invalidation & Indexing**:
  - `embedder` in `_index_memory_vector` is an async function and must be awaited directly (`await embedder(statement)`).
  - Post-commit cache and index invalidations must run outside the primary commit `try` block (`_invalidate_after_commit()`) returning HTTP 503 instead of 500 on failure, preventing duplicate write retries.
  - Vector deletion must include `IsEmptyCondition(key="tenant_id")` alongside the active tenant ID so legacy pre-PR vectors without tenant payloads can be purged.
- **System Prompt Safety Constraints**:
  - `GURU_SYSTEM_PROMPT` must keep the acute distress helpline instruction within the first 200 characters, preserve anti-impersonation boundaries ("never as the founders themselves"), and forbid hype words.
  - Dynamic prompt interpolation in `build_guru_system_prompt()` must use `\n\n` rather than literal escaped backslashes `\\n\\n`.
- **Web Search Domain Firewall Separation**:
  - `OFFICIAL_ALLOWED_DOMAINS` strictly contains only official Ekam/Oneness domains (`ekam.org`, `theonenessmovement.org`, `ekamworldpeacefestival.com`).
  - Secular reference sources (WHO, CDC, documentation, news wires) are partitioned into `GENERAL_ALLOWED_DOMAINS` and combined under `APPROVED_SOURCE_DOMAINS` for general assistant mode only.
- **Python Regex Raw Strings**:
  - Never use `\\s` inside raw f-strings (`rf"..."`); use `\s` so the compiled pattern matches whitespace rather than literal backslash-s.
- **Personal Knowledge Graph Schema Invariant**:
  - `study_notebooks` table is scoped solely by `user_id` and has no `tenant_id` column. Never filter it by `tenant_id`.

## Evaluation & Verification Invariants (2026-09-15)

- **Verification Metadata Invariant**: Every node that returns `final_answer` (casual handlers in `intent.py`, fallbacks in `short_circuit.py`, and `format_final_answer` in `generation.py`) MUST return a non-empty `verification` dict containing `{"passed": bool, "method": str, "citations_verified": bool}`. `GraphState.verification` uses `Annotated[Optional[dict], keep_latest]` to ensure deterministic multi-branch merging without `InvalidUpdateError`.
- **Answer Relevancy Ground Truth**: In evaluation benchmarks (`ragas_eval.py`), Answer Relevancy must test against `item.get("must_mention")` ground-truth concepts from `question_bank.py` and salient question tokens, never a static category-level denominator. Refusing adversarial jailbreaks is recorded as 100% relevant.
- **Pastoral Non-Assertion Filtering**: Persona instructions direct the model to provide compassionate guidance ("Reflect on this deeply", "Take a moment to sit quietly"). These non-assertions are stripped prior to NLI claim entailment (`services.lettuce_detect_service._is_assertion`) so tone guidance is never penalized as an ungrounded factual claim.
- **FastAPI Async Dependency Invariant (L-DOCKER-18)**: Never inject synchronous `def` callables via `Depends(...)` into FastAPI endpoints. Synchronous dependencies force Starlette to delegate to AnyIO's worker threadpool via `run_in_threadpool`, exhausting glibc thread stack allocation under load. Always use `async def get_container_async()`.
- **ReleaseManifest Public Projection Invariant**: `ChatResponse.release_manifest` is strictly typed as `ReleaseManifestPublic` (`extra="forbid"`). Never pass raw manifest dictionaries (`get_release_manifest().to_dict()`) into public response bodies; always project through `to_public_manifest_dict(...)`.
- **Multi-Stage RAG Latency Profile (L-LATENCY-1)**: Vector search (Qdrant) + GraphRAG (Memgraph) + ONNX INT8 Reranker takes only 2.1s (9.0%). 86.6% of pipeline time is consumed by 3 sequential LLM calls (`navigate_and_hyde` 5.4s, `generate_answer` 12.5s, `reflect_on_answer` 2.4s). Use Adaptive Parallel HyDE and local CPU ModernBERT verification to cut latency to <5s.

## Graph database and Qdrant/Memgraph/LightRAG upgrades (detail archived)

- Decision (2026-09-15, confirmed 2026-09-19): Memgraph (C++, Bolt-compatible) replaces Neo4j. `NEO4J_*` env vars remain aliases for `MEMGRAPH_*`; local Docker holds the authoritative graph.
- Qdrant: server-side RRF/DBSF fusion over named dense+sparse vectors, group search by `parent_id`, INT8 quantization with on-disk originals. LightRAG: dual-level routing and teacher-alias canonicalization.
- Rationale, rejected alternatives, Railway transition steps and the ops commands: `docs/agent/claude-md-archive/database-and-graph.md`.

## SPOF & Replication Policy (P2-2)

Official architecture, disaster recovery, and high availability policy across stateful components (Redis, Neo4j, Qdrant) across growth tiers (1k, 10k, 100k users).

| User Tier | Target QPS (p95) | Redis Policy | Neo4j Policy | Qdrant Policy | Target SLA / RTO / RPO |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **1k Tier** (Pilot / MVP) | 5-15 QPS | **Single Node**: Standalone Docker/Railway container with AOF persistence. Local in-memory TTL fallback on network disconnect. | **Single Instance**: Community edition with local persistent volume. Nightly automated dump (`neo4j-admin dump`). | **Single Node**: Local storage volume with automated nightly snapshot backup to S3 (`scripts/ops/qdrant_backup.py`). | **99.0% SLA**<br>RTO < 15 min<br>RPO < 24 hrs |
| **10k Tier** (Production HA) | 50-150 QPS | **Primary + Read Replica**: Master-replica with automated Sentinel failover (<5s). Read queries load-balanced across replicas; rate limits & anonymous quota use Redis ZADD sliding window. | **Causal Cluster**: 1 Core Leader + 2 Read Replicas (or Neo4j AuraDB HA). Asynchronous read-scaling with transactional causal chaining. | **Distributed 3-Node Cluster**: `replication_factor=2`, `write_consistency_factor=1`. Sharded collections across nodes with dynamic consensus routing. | **99.9% SLA**<br>RTO < 30 sec<br>RPO < 1 min |
| **100k Tier** (Enterprise Multi-AZ) | 500-1500+ QPS | **Multi-AZ Redis Cluster**: Multi-region Redis Cluster with active-passive read-replicas, segregated tiers (Session/RateLimit vs. Semantic/Doctrine Cache), Envoy L7 proxy. | **Enterprise Multi-AZ Cluster**: Multi-region Core Cluster + edge read replicas co-located with API pods. Dedicated read routing and Cypher connection poolers. | **Multi-AZ Sharded Qdrant Cluster**: `replication_factor=3`, `write_consistency_factor=2` across 3 AZs. HNSW scalar/binary quantization, collection tenant partitioning, zero-downtime rolling upgrades. | **99.99% SLA**<br>RTO ~ 0 (transp. failover)<br>RPO = 0 (quorum writes) |

### Failover & Degradation Invariants
1. **Redis Degradation**: If Redis drops, `AnonQuotaRedisAdapter` and `RedisBackedRateLimiter` degrade gracefully to in-process memory caches; search queries bypass semantic cache and proceed directly to vector/graph retrieval without failing requests with HTTP 500.
2. **Neo4j Degradation**: If Neo4j becomes unreachable, GraphRAG retrieval gracefully falls back to pure Qdrant dense vector search + BM25 keyword retrieval; OKF static teachings remain operable.
3. **Qdrant Degradation**: If Qdrant cluster is degraded, exact-match and hot doctrine caches serve answers; fallback returns honest zero-source abstention (`grounding_state=abstained`) rather than fabricating ungrounded teachings.

### Backup caveat (P6, verified 2026-09-13)
Backups stay local-cron per policy (`infrastructure/cron/mukthiguru-backup`: 02:00 Qdrant, 02:30 Neo4j, retention 7, disk-only) — deliberately NOT Celery Beat (`celery_config.py` `beat_schedule` covers win-back/memory only). The cron needs manual sudo install (`/etc/cron.d/` + `/etc/mukthiguru/backup.env`); it was absent on this host, so RPO is unbounded until installed. Qdrant scratch-restore is proven queryable (157 pts + search hit); Neo4j `.dump` load stays an offline maintenance-window op — queryable replay unproven.
- `PersonalizeStage` returns None without a `personalize_teaching` ref; otherwise declines terminally or stashes `personalize_clip` (tests: `tests/test_personalize_teaching.py`).
- `ToneAdapterStage` is a deliberate tested no-op; do not "clean it up". Dead on live config: `DoctrineCacheStage`, `regenerate_gate`, `agentic_graph_traversal`, standalone BM25 lane, `lightrag` param of `retrieve_for_single_query`.
- LangGraph built by `rag/graph_strategies.py`; entry routing via `rag/pipeline_registry.py` (recipe `docs/DEVELOPER_GUIDE.md` §6). `decompose_query` stays merged into `navigate_and_hyde`; don't re-split or fan out (`tests/test_graph_strategy_wiring.py`). Node detail: archive `rag-graph-pipeline.md`.
- Faithfulness: `verify_answer` (LettuceDetect, floor 0.6) decides; unsupported sentences are redacted.
- DI composition root `backend/app/dependencies.py` (`ServiceContainer`, `get_container()`); never instantiate services in route handlers.
- Auth: admin routes use strict `get_current_user_from_supabase` (never relax); chat/jobs use `get_optional_user` and must call `resolve_anon_identity(user, session_id)`.
- Ingestion: `POST /api/ingest` -> `ingest/pipeline.py:IngestionPipeline.ingest_url()`; Qdrant collection `settings.qdrant_collection`; bulk jobs reuse `IngestionCheckpoint`; web fetch keeps `follow_redirects=False` (SSRF guard).

## Gotchas

- Backend on the host needs overrides: `QDRANT_URL=http://localhost:6333`, `NEO4J_URI=bolt://localhost:7687`, `REDIS_URL=redis://:...@localhost:6379/0`, reachable `SUPABASE_URL` (a wrong one is silent apart from `Telemetry Sink insert failed`; see `telemetry_sink_writes_total{outcome="error"}`).
- Which LLM service class is live depends on `LLM_PROVIDER`; `OpenRouterService`, `SarvamCloudService`, `OllamaService` share no code, so patch the provider actually in use. Live OpenRouter models: generation `deepseek/deepseek-chat`, fallback `meta-llama/llama-3.3-70b-instruct`, fast `meta-llama/llama-3.1-8b-instruct`.
- Railway is scaled down and stays stopped until Harsha says otherwise; verify locally. When it resumes: `/api/health` gate, `FORWARDED_ALLOW_IPS=10.0.0.0/8`, `PYTHON_MEMORY_LIMIT_MB=0` (archive `railway-deployment.md`).
- Mobile: `android/` and `ios/` are Capacitor 8; read `docs/MOBILE_RELEASE_RUNBOOK.md` before any store work (not submission-ready). Regenerate icons with `python3 scripts/ops/generate_mobile_assets.py`; verify tracking with `git status --short --untracked-files=all ios/`.
- Guru voice: `GURU_SYSTEM_PROMPT` states the model speaks "never as the founders themselves"; voice code only appends (`tests/test_guru_voice_langhanam.py`).

## Commands

```bash
npm run dev | build | lint | test | test:e2e     # frontend, Vite on :8080
cd backend && .venv/bin/pytest [tests/test_x.py]  # backend tests
cd backend && docker compose up -d --build        # full stack; logs -f backend; down
cd backend && uvicorn app.main:app --port 8000 --reload   # host run, see Gotchas
scripts/ops/backend_py.sh script.py [args] | -c 'code'    # python in the backend container (cwd /app); loop it for sweeps
```

Services: frontend :8080, API docs :8000/docs, health :8000/api/health, Qdrant :6333/dashboard, Jaeger :16686, Neo4j :7474, Ingest portal :8000/ingest/.
Config: `backend/.env` (from `.env.example`); key flags and models in `backend/app/config.py` (`from app.config import settings`). CI: `.github/workflows/` (build-deploy, dependency-check, lint-test, security-audit, golden25-gate).

## Tooling

Prefer MCP code-intelligence tools (codebase-memory) over raw grep for symbols, flows and impact. Node 22 LTS only (Node 25 OOMs WASM tooling). Update this file and `AGENTS.md` when directory layout, services, env config or core pipeline patterns change. Scoped guidance: `backend/CLAUDE.md`, `src/CLAUDE.md`.

## Open work (read before answering "what's pending?")

- Single open-work list (status source; edit it when an item closes or appears, never start another plan file): `docs/plans/PROD_READINESS_TASK_LIST_2026-10-11.md`, start at "Ruthless order of work" and "Start here". The SessionStart hook `scripts/guards/open_work_reminder.sh` prints its age and warns at 3+ days stale.
- Live roadmap: `docs/plans/PLAN.md` (safety spine / evals / NotebookLM parity, phases A-I, §5 decisions). Session history: `docs/handoffs/handoff.md`, `docs/handoffs/HANDOFF_2026_10_14.md` §8; findings: `lessons.md` (newest on top).
- Top safety item: multilingual crisis detection (`backend/services/serene_mind_engine.py`, `assess_distress()`) is AI-authored and AI-tested, NOT native-speaker reviewed. See `evals/README.md`.
- Human-only gates, all PENDING (agents surface them, never fake-close): native-speaker reviewers (`evals/native_speaker_review_packet.md`), clinician reviewers (`evals/clinician_review_packet.md`), 299-pair B1 gold batch, 4 gold videos restored, helpline phone-confirmation (never test-call 112), Twilio/Meta creds, backup archive copied off the Mac (`~/mukthiguru_attribution_data/backups_2026-10-08`), Railway login/secrets/Qdrant upgrade, store accounts, rights sign-off.
- `config/helplines.yaml` (15 entries) AI-web-verified and owner-approved 2026-09-23; not a phone-call verification. On-call/safety reviewer: project owner (Harshodai).
- #1 priority (2026-09-24): clean data and a stable baseline for first-person verbatim answers before feature work. Spec: `docs/agent/first_person_baseline_prompt.md`; design: `docs/agent/first_person_research_2026-09-24.md`; master prompt: `docs/agent/CLAUDE_CODE_MASTER_PROMPT.md`.

## Compact instructions

When compacting, keep: the current task and files modified, test commands run and their result, pending human-only gates, and the open-work list path. Drop tool-output dumps, file listings and exploration that led nowhere.

## Subagent model routing

Pass `model: "haiku"` to read-only search, locate, count and file-listing subagents (Explore, cavecrew-investigator, ecc:code-explorer). Sonnet for edits and implementation. Opus only for safety/crisis code, red-team and final independent review. Never haiku for anything that edits files or judges safety.
