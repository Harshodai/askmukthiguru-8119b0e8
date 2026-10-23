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
