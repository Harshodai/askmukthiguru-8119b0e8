# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Folder-scoped guidance also exists — `backend/CLAUDE.md` (backend workflow, request-pipeline stages) and `src/CLAUDE.md` (frontend workflow, testing, storage contracts) — and is loaded automatically when working in those trees.

## Project Overview

**Mukthi Guru** is a privacy-first, zero-hallucination AI spiritual guide grounded in Sri Preethaji & Sri Krishnaji's teachings. It combines a React frontend chat UI with a Python FastAPI backend running a multi-layer RAG pipeline.

**Constraints from SPEC_DEV.md (non-negotiable):**
- $0 budget — only free-tier infrastructure (Colab, Qdrant local, Ollama)
- All processing is local; zero external API calls at inference
- Every dependency must be open source (Apache 2.0, MIT, or Meta Community)
- Target: <1% hallucination rate, <3s response time
- Data source: only Sri Preethaji & Sri Krishnaji's YouTube videos + approved images

## Rules for This Repo

- Secrets stay in env vars — never write a real key into any file. Only `backend/.env.example` is checked in; never commit `backend/.env`, `.env.local`, or `.env.optimized` values.

## Gotchas

- The repo has both `package-lock.json` and `bun.lockb`. npm is canonical — don't regenerate or update the bun lockfile.

## Repository Structure

```
/
├── public/                  # Static assets, sitemap.xml, service worker
├── src/                     # React frontend (Vite + TypeScript + shadcn/ui)
│   ├── admin/               # Admin dashboard sub-app
│   │   ├── components/      # KpiCard, LiveFeed, TraceDrawer, SeedDemoButton, etc.
│   │   ├── hooks/           # useAdminData, useAdminGuard
│   │   ├── layout/          # AdminShell, AdminTopbar
│   │   ├── lib/             # adminAuth, exportTrace, formatters, mockData, seed, filtersStore
│   │   ├── pages/           # Overview, Queries, Retrieval, Quality, Feedback, Alerts,
│   │   │                     Triggers, Telemetry, Evals, Prompts, Admins, Ingestion, Logs,
│   │   │                     Settings, DailyTeaching, AdminLogin
│   │   └── types.ts
│   ├── components/
│   │   ├── auth/            # TwoFactorSettings
│   │   ├── chat/            # ChatInterface, ChatHeader, ChatMessage, ChatErrorBanner,
│   │   │                     DailyTeaching, DesktopSidebar, LanguageSelector, MeditationStats,
│   │   │                     MessageList, MobileConversationSheet, PrePracticeGate,
│   │   │                     ScrollToBottomFab, SereneMindModal, SlashCommandMenu,
│   │   │                     ThinkingPills, WisdomCardGenerator
│   │   ├── common/          # ChatErrorBoundary, CommandPalette, CookieConsentBanner,
│   │   │                     ReminderProvider, RootErrorBoundary, SafetyDisclaimer,
│   │   │                     SereneMindProvider, SessionExpiredHandler, ThemeProvider,
│   │   │                     UserMenu, BrandedSpinner
│   │   ├── landing/         # HeroSection, AboutMeditationSection, PracticesSection,
│   │   │                     HowItWorksSection, MeetTheGurusSection, FloatingParticles,
│   │   │                     Footer, Navbar, ContinuePracticeCard
│   │   ├── layout/          # AnimatedLayout, AppShell
│   │   ├── meditation/      # GuidedMeditationFlow, MeditationProgressIndicator,
│   │   │                     breathTechniques, meditationSteps
│   │   ├── profile/           # MemoryManager
│   │   └── ui/              # shadcn/ui primitives (accordion, alert, avatar, badge, button,
│   │                         calendar, card, carousel, chart, checkbox, collapsible, command,
│   │                         context-menu, dialog, drawer, dropdown, form, hover-card, input,
│   │                         input-otp, label, loading, menubar, navigation-menu, pagination,
│   │                         popover, progress, radio-group, resizable, scroll-area, select,
│   │                         separator, sheet, sidebar, skeleton, slider, sonner, switch,
│   │                         table, tabs, textarea, toast, toggle, toggle-group, tooltip)
│   ├── hooks/               # useAdminData, useAdminGuard, use3DTilt, useAuthStatus,
│   │                         useBreathTeaching, useChatShortcuts, useDailyTeaching,
│   │                         useFavorites, useMeditationReminder, useMobile, usePageMeta,
│   │                         useProfile, useRequireAuth, useSpeechRecognition, useSwipeGesture,
│   │                         useTextToSpeech, useTheme, useToast
│   ├── integrations/        # lovable/ (index), supabase/ (client, types)
│   ├── lib/                 # aiService, authTelemetry, chatErrorBus, chatStorage,
│   │                         exportConversation, favoritesStorage, meditationStorage,
│   │                         memoryApi, personalInsights, practicesContent, profileStorage,
│   │                         responseCache, utils
│   ├── pages/               # Index, AuthPage, ChatPage, ProfilePage, PracticesPage,
│   │                         PracticeDetailPage, PrivacyPage, TermsPage, ResetPasswordPage,
│   │                         TTSVerificationPage, AuthDiagnosticsPage, AuthLatencyDashboard,
│   │                         SpiritGuidesPage, NotFound
│   └── test/                # Vitest tests (aiService, chatStorage, profileStorage,
│                               ChatMessage, DesktopSidebar, DailyTeaching, LanguageSelector,
│                               ThinkingPills, SereneMindProvider, useRequireAuth, etc.)
├── ingest-ui/               # Standalone HTML/JS ingestion portal served by backend
├── backend/
│   ├── app/                 # FastAPI application + DI + core
│   │   ├── api/             # API route modules
│   │   ├── contracts/       # Pydantic request/response contracts
│   │   ├── core/            # Core utilities, base classes, middleware
│   │   ├── pipeline/        # PipelineCoordinator + pure-function stages/ (see Request Pipeline section)
│   │   ├── telemetry/       # Telemetry data models
│   │   ├── __init__.py
│   │   ├── coalescer.py
│   │   ├── debug_helper.py
│   │   ├── debug_retrieval.py
│   │   ├── main.py          # FastAPI app, route handlers, lifespan
│   │   ├── config.py        # Pydantic Settings (all config from .env / .env.local)
│   │   ├── constants.py
│   │   ├── context.py
│   │   ├── dependencies.py  # ServiceContainer (composition root, full DI)
│   │   ├── gradio_ui.py
│   │   ├── language_utils.py
│   │   ├── metrics.py
│   │   ├── observability.py # OpenTelemetry / tracing setup
│   │   ├── orchestrator.py  # Pipeline orchestration entry
│   │   ├── orchestrator_utils.py
│   │   ├── qa_wiring_check.py
│   │   ├── sanitization.py
│   │   ├── schemas.py
│   │   ├── security_utils.py
│   │   ├── stream_orchestrator.py  # Streaming orchestrator
│   │   ├── telemetry_db.py
│   │   ├── telemetry_sink.py
│   │   ├── test_sarvam.py
│   │   ├── trace_dashboard.py
│   │   └── tracing.py
│   ├── benchmarks/
│   │   ├── RUN_ME.sh        # One-shot benchmark runner (requires live Docker stack)
│   │   ├── chunk_size_evaluation.py
│   │   ├── comprehensive_benchmark.py
│   │   ├── focused_fix_test.py
│   │   ├── generate_dashboard.py
│   │   ├── native_eval.py
│   │   ├── question_bank.py
│   │   ├── ragas_eval.py
│   │   ├── run_all.py
│   │   ├── ruthless_benchmark.py
│   │   ├── sdlc_rag_benchmark.py
│   │   ├── smoke_doctrine.py
│   │   └── validate_graph.py
│   ├── celery_config.py
│   ├── colab/
│   │   ├── __init__.py
│   │   ├── setup.py
│   │   └── transfer.py
│   ├── docker-compose.yml
│   ├── domain/
│   │   └── ports/
│   ├── evaluation/
│   │   └── ragas_eval.py
│   ├── gptcache_config.yml
│   ├── guardrails/
│   │   ├── config/
│   │   ├── base.py
│   │   ├── chain.py
│   │   ├── disabled_handler.py
│   │   ├── lightweight_handler.py
│   │   └── nemo_handler.py
│   ├── ingest/
│   │   ├── __init__.py
│   │   ├── auditor.py
│   │   ├── cleaner.py
│   │   ├── corrector.py
│   │   ├── image_loader.py
│   │   ├── pipeline.py    # IngestionPipeline orchestrator
│   │   ├── raptor.py      # RAPTOR hierarchical indexing
│   │   └── youtube_loader.py  # Transcript extraction
│   ├── infrastructure/
│   │   ├── k8s.yaml
│   │   └── scheduler.py
│   ├── models/
│   │   ├── feedback.py
│   │   ├── user.py
│   │   ├── Modelfile.sarvam30b   # Ollama Modelfile for Sarvam 30B
│   │   ├── setup_sarvam.sh       # Linux/Colab setup script
│   │   ├── setup_sarvam.ps1      # Windows setup script
│   │   ├── download_models.sh    # Model download helper (Unix)
│   │   └── download_models.ps1   # Model download helper (Windows)
│   ├── optimization/
│   │   └── dspy/
│   ├── rag/
│   │   ├── nodes/           # Modular graph nodes
│   │   │   ├── _services.py
│   │   │   ├── cross_teacher_reasoning.py
│   │   │   ├── generation.py
│   │   │   ├── intent.py
│   │   │   ├── keyword_injection.py
│   │   │   ├── on_device_intent.py
│   │   │   ├── reranking.py
│   │   │   ├── retrieval.py
│   │   │   ├── short_circuit.py
│   │   │   ├── utils.py
│   │   │   └── verification.py
│   │   ├── agentic_nodes.py
│   │   ├── compression.py
│   │   ├── compressor.py
│   │   ├── cot_verifier.py
│   │   ├── dspy_engine.py
│   │   ├── graph.py         # Facade delegating to graph strategies
│   │   ├── graph_strategies.py  # FastGraphStrategy, StandardGraphStrategy, DeepGraphStrategy
│   │   ├── intent_prerouter.py
│   │   ├── meditation.py
│   │   ├── memory.py
│   │   ├── node_command.py
│   │   ├── node_llm_config.py
│   │   ├── node_registry.py
│   │   ├── prompts.py
│   │   ├── resolve_followup.py
│   │   ├── self_correction.py
│   │   ├── states.py
│   │   ├── telemetry_observer.py
│   │   ├── timeout_utils.py
│   │   ├── tools.py
│   │   └── tree_navigator.py
│   ├── routers/
│   │   ├── admin.py
│   │   ├── compliance.py
│   │   └── feedback.py
│   ├── schemas/
│   │   ├── feedback.py
│   │   └── user.py
│   ├── scripts/
│   │   ├── ops/
│   │   ├── cache_warmer.py
│   │   ├── dream_memories.py
│   │   ├── fix_py39_types.py
│   │   ├── ingest_pdf_pipeline.py
│   │   ├── init_db.py
│   │   ├── migrate_data.py
│   │   ├── phase05_audit.py
│   │   ├── seed_admin.py
│   │   ├── verify_sarvam.py
│   │   └── warm_semantic_cache.py
│   ├── services/
│   │   ├── cache/           # Cache adapters (redis, semantic, memory, hot-cache, llm) behind factory.py
│   │   ├── gateways/
│   │   ├── llm/
│   │   ├── translation/
│   │   ├── __init__.py
│   │   ├── ab_testing.py
│   │   ├── adaptive_chunking_adapter.py
│   │   ├── adaptive_chunking_service.py
│   │   ├── auth_service.py
│   │   ├── base_llm_service.py
│   │   ├── cache_service.py
│   │   ├── circuit_breaker.py
│   │   ├── compliance_logger.py
│   │   ├── concurrent_retriever.py
│   │   ├── config_watcher.py
│   │   ├── container_builder.py
│   │   ├── context_compressor.py
│   │   ├── contextual_chunking_service.py
│   │   ├── cookie_helper.py
│   │   ├── cost_tracker.py
│   │   ├── doctrine_cache.py
│   │   ├── embedding_service.py
│   │   ├── feedback_service.py
│   │   ├── http_client_pool.py
│   │   ├── ingestion_tracker.py
│   │   ├── krutrim_service.py
│   │   ├── language_router.py
│   │   ├── lettuce_detect_service.py
│   │   ├── lightrag_service.py
│   │   ├── llm_factory.py
│   │   ├── llm_protocol.py
│   │   ├── memory_service.py
│   │   ├── memory_service_v2.py
│   │   ├── model_failover.py
│   │   ├── model_registry.py
│   │   ├── multi_provider_llm.py
│   │   ├── ocr_service.py
│   │   ├── ollama_service.py
│   │   ├── openrouter_service.py
│   │   ├── phonetic.py
│   │   ├── prompt_store.py
│   │   ├── proposition_service.py
│   │   ├── qdrant_service.py
│   │   ├── reranker_service.py
│   │   ├── rrf_ranker.py
│   │   ├── sarvam_exceptions.py
│   │   ├── sarvam_service.py
│   │   ├── sarvam_stt_service.py
│   │   ├── semantic_cache.py
│   │   ├── semantic_router_fallback.py
│   │   ├── serene_mind_engine.py
│   │   ├── streaming_generator.py
│   │   ├── streaming_hardening.py
│   │   ├── tenant_context.py
│   │   ├── user_profile_service.py
│   │   ├── vector_optimizer.py
│   │   └── whisper_local_service.py
│   ├── tasks/
│   │   ├── __init__.py
│   │   └── ingest_tasks.py
│   └── tests/
│       ├── __init__.py
│       ├── conftest.py
│       ├── test_abstractions.py
│       ├── test_adaptive_chunking.py
│       ├── test_admin.py
│       ├── test_benchmarks.py
│       ├── test_chat_endpoint.py
│       ├── test_coalescer.py
│       ├── test_concurrent_retriever.py
│       ├── test_context_compressor.py
│       ├── test_dspy_optimization.py
│       ├── test_embedding_no_double_prefix.py
│       ├── test_embedding_service.py
│       ├── test_flashrank_rerank.py
│       ├── test_guardrails.py
│       ├── test_guardrails_chain.py
│       ├── test_health.py
│       ├── test_ingestion_pipeline.py
│       ├── test_intent_complexity_parser.py
│       ├── test_intent_prompt_semantics.py
│       ├── test_memory_api.py
│       ├── test_memory_context.py
│       ├── test_memory_service.py
│       ├── test_nodes.py
│       ├── test_observability.py
│       ├── test_openrouter.py
│       ├── test_rag_advanced.py
│       ├── test_retrieve_documents_contract.py
│       ├── test_rrf_ranker.py
│       ├── test_sarvam_observability.py
│       ├── test_serene_mind.py
│       ├── test_tiered_router.py
│       ├── test_tiered_routing_streaming.py
│       └── test_token_budget_guard.py
├── scripts/
│   ├── ingestion/
│   │   ├── pageindex/
│   │   ├── bulk_ingest_async.py
│   │   ├── bulk_ingest_whisper.py
│   │   ├── extract_transcripts.py
│   │   ├── ingest_four_sacred_secrets.py
│   │   ├── ingest_host_whisper.py
│   │   ├── ingest_pageindex_json.py
│   │   ├── ingest_structure_to_qdrant.py
│   │   ├── ingest_youtube_seeds.py
│   │   ├── retry_failed_videos.py
│   │   ├── run_pageindex.py
│   │   ├── smart_extract_and_ingest.py
│   │   └── verify_ingestion_quality.py
│   ├── ops/
│   │   ├── backup_neo4j.py
│   │   ├── backup_qdrant.py
│   │   ├── cleanup_data.py
│   │   ├── flush_cache.py
│   │   ├── full_cleanup.py
│   │   ├── heal_neo4j_poison.py
│   │   └── reset_state.py
│   ├── benchmarks/
│   │   ├── askmukthiguru_ruthless_benchmark.py
│   │   └── load_test.py
│   ├── backup/
│   │   └── snapshot_manager.py
│   ├── check_docker_health.py
│   ├── db_rectify.py
│   ├── generate_all_skills.py
│   ├── load_test.py
│   ├── migrate_tenant_collections.py
│   ├── monitoring_dashboard.py
│   ├── security_audit.py
│   └── whatsapp_webhook.py
├── k8s/
│   ├── helm/
│   │   └── mukthiguru/
│   └── skaffold.yaml
├── .github/
│   └── workflows/
│       ├── build-deploy.yml
│       ├── dependency-check.yml
│       ├── lint-test.yml
│       └── security-audit.yml
└── .emergent/
    └── emergent.yml
```

## Development Commands

### Frontend (React)
```bash
npm run dev          # Start Vite dev server (http://localhost:8080)
npm run build        # Production build
npm run lint         # ESLint
npm test             # Run Vitest tests (once)
npm run test:watch   # Run Vitest in watch mode
npm run test:e2e     # Playwright end-to-end tests
npx vitest run src/test/greeting.test.ts   # Run a single test file
```

Tests are in `src/test/` and `src/tests/`. The `@` alias maps to `src/`.

### Backend (Python)
```bash
cd backend

# Setup (first time)
python -m venv venv
source venv/bin/activate     # Linux/Mac
# venv\Scripts\activate     # Windows
pip install -r requirements.txt

# Run locally (requires Qdrant, Redis, Neo4j running separately)
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# Run infrastructure (Docker, from backend/ directory)
docker compose up -d qdrant redis neo4j jaeger

# Run backend tests
.venv/bin/pytest                     # Run all tests (from backend/ directory)
.venv/bin/pytest tests/test_name.py  # Run specific test file (from backend/ directory)
python3 -m pytest backend/tests/     # Run all tests (from workspace root)
```

### Docker (Recommended)
```bash
cd backend
docker compose up -d --build   # Start Qdrant, Redis, Neo4j, Jaeger + Backend
docker compose logs -f         # Stream logs
docker compose logs -f backend # Backend logs only
docker compose down            # Stop all
```

Ollama must run on the **host** machine (not in Docker) — `ollama serve`.

### Sarvam 30B Model Setup
```bash
cd backend/models
chmod +x setup_sarvam.sh && ./setup_sarvam.sh   # Linux/Colab
# .\setup_sarvam.ps1                               # Windows
```

## Service URLs

| Service | URL |
|---------|-----|
| React Frontend | http://localhost:8080 |
| Backend API + Swagger | http://localhost:8000/docs |
| Ingestion Portal | http://localhost:8000/ingest/ |
| Gradio Chat UI | http://localhost:8000/ui |
| Qdrant Dashboard | http://localhost:6333/dashboard |
| Prometheus Metrics | http://localhost:8000/metrics |
| Health Check | http://localhost:8000/api/health |
| Jaeger Traces | http://localhost:16686 |
| Neo4j Browser | http://localhost:7474 |

## Configuration

All backend config lives in `backend/.env` (copy from `backend/.env.example`). Optimised overrides can be loaded from `backend/.env.optimized` after sourcing `.env`. Key settings:

- `LLM_PROVIDER` — `sarvam_cloud` (default; needs `SARVAM_API_KEY`, optional `SARVAM_RPM_LIMIT`), `ollama` (`OLLAMA_BASE_URL`), or `openrouter` (`OPENROUTER_API_KEY`)
- `OLLAMA_MODEL` — default `sarvam-30b:latest` (used when the provider is `ollama`)
- `QDRANT_URL` — default `http://localhost:6333`
- `QDRANT_LOCAL_PATH` — set for local (no-Docker) Qdrant mode
- `WHISPER_MODEL` — `large-v3` (uses `faster-whisper` backend by default)
- `WHISPER_COMPUTE_TYPE` — `float16` for GPU, `int8` or `float32` for CPU
- `KNOWLEDGE_GRAPH_QUERY_ENABLED` — default `true` (config.py:397). Gates per-query LightRAG/Neo4j traversal in `rag/nodes/retrieval.py`. The traversal sits inside the retrieval `asyncio.gather`, so every RELATIONAL/FACTUAL/QUERY waits on it (up to `LIGHTRAG_RETRIEVAL_TIMEOUT`) while Qdrant returns in ~150ms. It was off historically when the graph held ~5 edges (pure latency tax), but the ontology expansion (commit e84cfed9) grew Neo4j to **11,136 relationships / 7,512 nodes** (verified 2026-07-10), well past the 1,000-edge threshold, so the traversal now adds real retrieval signal and is enabled. Disable again only if a measured latency regression outweighs the retrieval lift. Ingestion and the ontology seeder are unaffected either way.

## Caching invariants

`cache_key` is `(language, message)` only — it carries **no `user_id` and no `tenant_id`** — and every tier (hot, exact, semantic, vector) is process- or Redis-wide. `CacheUpdateStage` therefore **must not** cache an answer that `context_engineer` personalized with `memory_context`, or one seeker's private context gets replayed to the next person asking the same question. Guarded in `app/pipeline/stages/cache_stage.py`; regression test in `backend/tests/test_cache_personalization_leak.py`.

The P90 `TurboQuantCache` must stay a process-wide singleton (`services/turboquant_cache.py:get_shared_vector_cache`) because `PipelineCoordinator` is rebuilt per request — a per-instance cache is written once and discarded, so it never serves a hit.

The OKF compiled index lives at repo-root `memory/okf/compiled.json`, **not** under `backend/`. Both backend Dockerfiles must `COPY memory/ ./memory/`; otherwise `_load_okf_entries()` finds nothing and OKF injection (`rag_okf_injection_enabled`, default `true`) silently contributes zero documents in the image only.

## Embedding dimension contract

`settings.embedding_dimension` and the Qdrant collection's actual vector size are a **pinned pair, never silently changed independently** — a 2026-07-16 production incident (`bge-m3`'s HF cache corrupted → `_ensure_encoder()` silently fell back to a 384-dim model against the existing 1024-dim collection) made every dense search 400 while `/api/health` still reported ready, surfacing as a misleading generic "connection issue" instead of the real cause. Root-caused and fixed in `backend/services/embedding_service.py`, `backend/services/qdrant/client.py`, `backend/rag/nodes/{retrieval,generation}.py`; full analysis in `handoff.md` and `lessons.md`. Three invariants now enforced:

1. **`EmbeddingService._ensure_encoder()`** clears the HF cache and retries once on a load failure (self-heals a corrupted/truncated download), and **never accepts a fallback model whose dimension differs from `settings.embedding_dimension`** — it raises instead of silently downgrading. Regression tests in `backend/tests/test_embedding_service.py`.
2. **`QdrantClientManager._verify_collection_dimension()`** asserts the *existing* collection's real vector size matches `settings.embedding_dimension` at startup and raises loud on mismatch (handles both named and unnamed vector configs; never swallows a genuine transport/auth error as a benign shape surprise). Regression tests in `backend/tests/test_qdrant_dimension_validation.py`.
3. **`generate_answer`** (`rag/nodes/generation.py`) returns an honest "couldn't find relevant teachings" message and skips the LLM call entirely when `relevant_docs` is empty (custom-assistant chats with `assistant_system_prompt` set are exempt — they legitimately answer from persona, not RAG docs), instead of calling the LLM with nothing and surfacing a misleading generic error. **OKF injection no longer requires non-empty vector-search results** (`rag/nodes/retrieval.py`) — curated doctrine can still fill in when Qdrant returns nothing.

**Known open items, not yet done:**
- Pre-caching `bge-m3` into the Docker image at build time (`lessons.md` Option C) would remove the cold-start download/corruption risk entirely; current fix self-heals instead of avoiding the download. Not done — ask before adding, changes the Dockerfile/image size tradeoff.
- Full-suite test isolation: `tests/test_health.py::test_health_check` and `tests/test_fail_closed_paths.py::test_retrieve_documents_empty_results_is_safe` both pass in isolation but fail under the full ~925-test run — some test still mutates the shared `get_container()` singleton's real attributes directly (not via `app.dependency_overrides`, which `tests/conftest.py`'s `_clear_dependency_overrides` autouse fixture already resets). Pre-existing, suite-wide, unrelated to this incident — not chased down.
- `services/openrouter_service.py`'s `_call_api()` no longer wastefully retries the same model on a 429 (fixed — see `_is_retryable_openrouter_error`), but there is still no cross-provider failover: `NIM_API_KEY`/`services/nim_service.py` are fully built but **never instantiated in `app/container.py`**, despite `handoff.md` documenting "OpenRouter (primary), nim (fallback)" as the intended design. Wiring that up is a real, separate feature (new DI wiring, untested in this deployment) — flagged, not built blind on a single observed 429 that was very likely self-inflicted by a heavy verification script rather than real traffic.

## OKF (Open Knowledge Format) pipeline

OKF is [Google Cloud's Open Knowledge Format v0.1](https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md) (June 2026), which formalises Andrej Karpathy's *LLM-wiki* pattern: a **bundle** is a directory of markdown files, one concept per file, each with YAML frontmatter whose **only required field is `type`**. `index.md` and `log.md` are reserved filenames carrying no frontmatter. Recommended fields: `title`, `description`, `resource`, `tags`, `timestamp`. Cross-references are ordinary bundle-relative markdown links (`/beautiful_state.md`).

Ours is a **doctrine bundle**: the teachings of Sri Preethaji & Sri Krishnaji, and nothing else. Every entry is embedded and injected verbatim into answers, so anything in `memory/okf/` is quoted to a seeker *as doctrine*.

**Three invariants, all enforced at load time in `OKFStore.list_entries()` (the single chokepoint for the compiler and the admin API) and guarded by `backend/tests/test_okf_doctrine_only.py`:**

1. **Doctrine types only.** `DOCTRINE_TYPES = {teaching, practice, glossary, qa, reflection}`. Any other `type` (a runbook, an engineering note) is skipped with a warning. Engineering notes live in `docs/engineering-notes/`, never in the bundle.
2. **Provenance is mandatory.** An entry with an empty `source` is uncitable, so `format_final_answer` cannot attribute it. Rejected.
3. **No extraction artifacts.** `OKFQualityFilter` rejects bodies containing RAPTOR debug headers, `_(Source: unknown)_`, or the extraction LLM's own prompt commentary (`"The user wants me to analyze a spiritual teaching…"`). Four such entries were found live in `memory/okf/` and quarantined to `staging/` — `generation.py` rule 6 forbids exposing exactly that text while the knowledge layer contained it.

`compiler.py` embeds `title + description`, not the bare title: a seeker asks *"why do I keep suffering?"* and matching that against the string `"Inner Truth"` is close to noise.

It is markdown on disk, compiled to an embedded index, injected into retrieval as extra documents.

```
ingestion (per video)                     rag_okf_auto_extract_enabled — default TRUE
  └─ _okf_extract_for_video()
       └─ extract_okf(auto_approve=False)
            ├─ reads Qdrant chunks + Neo4j entities + LightRAG relations
            ├─ LLM synthesis (multi-provider → OpenRouter → Ollama)
            └─ writes memory/okf/staging/*.md      ← STAGED, awaiting review
                     │
     admin review ───┤  POST /api/admin/okf/review/{id}/approve
                     ▼
               memory/okf/*.md                     ← LIVE entries
                     │  compile_okf()  (POST /api/admin/okf/compile)
                     ▼
               memory/okf/compiled.json
                     │  _load_okf_entries() — cached per-process
                     ▼
      retrieval.py `_okf_match()` → injected into every non-CASUAL query
```

So **ingestion appends to OKF** — it never overwrites live entries — but only into `staging/`. Nothing reaches an answer until it is approved and recompiled. Auto-extracted entries are *unreviewed by definition*; treat approval as an editorial act, not a formality.

Rules:
- **Never remove the OKF `_excluded_parts` staging filter.** `OKFStore.list_entries()` uses `rglob` (the teacher-subdir layout `sri-preethaji/`/`sri-krishnaji/`/`shared/` requires recursion) and keeps `staging/` and `_scripts/` out via an explicit `_excluded_parts={"staging","_scripts"}` filter — **the filter, not glob depth, is the review gate.** `staging/` holds unreviewed, LLM-generated doctrine; drop the filter and it reaches `compiled.json`, making the review gate a no-op. Reverting to a non-recursive `glob` (the old, wrong "fix") instead silently drops every teacher-subdir teaching from the index. Both failure modes are guarded by `backend/tests/test_okf_pipeline_integrity.py`.
- **Never put non-teaching content in `memory/okf/`.** See the three invariants above. `docs/engineering-notes/` is where RAG/config notes belong.
- **Never re-derive the OKF directory.** `services/memory/okf_store.py` exports `OKF_DIR` / `STAGING_DIR`, which handle both the repo layout and the image layout (inside the image `backend/` *is* `/app`, so `parents[3]` and `_BACKEND.parent` both land on `/`). `compiler.py` and `scripts/extract_okf_from_stores.py` import them.
- `_OKF_CACHE` in `rag/nodes/retrieval.py` is a per-process cache: new entries need a **recompile plus a backend restart** to appear.
- There is exactly one extractor: `backend/scripts/extract_okf_from_stores.py`. A repo-root duplicate existed, silently drifted (lost its Ollama fallback), and was deleted.

Rebuild the wiki from the live stores (needs Qdrant/Neo4j/LightRAG up):

```bash
cd backend
.venv/bin/python -m scripts.extract_okf_from_stores --all --dry-run        # inspect, no writes
.venv/bin/python -m scripts.extract_okf_from_stores --all --limit 20       # → staging/, for review
.venv/bin/python -m scripts.extract_okf_from_stores --all --auto-approve   # → live + compile
.venv/bin/python -m scripts.okf_compile                                    # recompile only
```

Config is loaded via `backend/app/config.py` (pydantic-settings). Import as `from app.config import settings`. For benchmark runs, use `source .env.optimized` after `.env` for tuned timeouts (`LLM_TIMEOUT=90`, `PIPELINE_TIMEOUT=90`, `SEMANTIC_CACHE_SIMILARITY=0.90`).

## Architecture: Request Pipeline (`app/pipeline/`)

Every chat request flows through an ordered chain of pure-function stages that wrap the RAG graph. `app/orchestrator.py` (sync) and `app/stream_orchestrator.py` (SSE) both delegate to `app/pipeline/pipeline_coordinator.py:PipelineCoordinator.execute()`, which runs the chain defined in `app/pipeline/stages/pipeline_builder.py`:

```
CacheCheck → CircuitBreaker → RequestState → InputGuardrail → DoctrineCache
→ CasualShortCircuit → Distress → Graph → MeditationGen → Translation
→ Memory → OutputGuardrail → CacheUpdate → ResultAssembly
```

Stages operate on a shared `PipelineContext` (services via `ctx.container`, coordinator helpers via `ctx.coordinator`) and are unit-testable in isolation. `GraphStage` is the step that invokes the LangGraph described below.

## Architecture: The Multi-Node Anti-Hallucination Pipeline

The chat endpoint (`POST /api/chat`) runs every message through a LangGraph State Machine with ~20 specialized nodes. The original "12-layer" conceptual model has been expanded with additional quality gates and retrieval enhancements.

### Graph Strategy Architecture

`rag/graph.py` is a **thin facade** around `rag/graph_strategies.py`. The actual wiring lives in strategy classes so that new variants can be added without touching the facade:

| Strategy | Class | Purpose |
|----------|-------|---------|
| **Fast** | `FastGraphStrategy` | 5-node pipeline for simple factual queries (~25s) |
| **Standard** | `StandardGraphStrategy` | Full anti-hallucination chain (~133s) |
| **Deep** | `DeepGraphStrategy` | Extended chain for complex multi-part questions |

### Node Architecture (under `rag/nodes/`)

The graph nodes have been modularized into `rag/nodes/`:

| Module | Key Nodes | Purpose |
|--------|-----------|---------|
| `intent.py` | Intent routing, on-device intent classification | Route to distress, meditation, casual, or full pipeline |
| `retrieval.py` | Hybrid retrieval (RAPTOR + leaf + LightRAG + Parent-Child + MMR) | Two-phase hybrid retrieval with keyword injection |
| `reranking.py` | Cascaded ColBERT + CrossEncoder re-ranking | Re-ranking of retrieved documents |
| `generation.py` | Context-only generation, inline hint extraction | Stimulus RAG + generation |
| `verification.py` | Reflect on answer, verify, check contradiction | Self-Reflection RAG, Chain of Verification |
| `keyword_injection.py` | Doctrinal synonym expansion | Improves retrieval coverage for spiritual terms |
| `short_circuit.py` | Fast-path short circuiting | Skips heavy nodes for simple queries |
| `on_device_intent.py` | Local intent classification | On-device intent classification (no LLM call) |
| `utils.py` | Shared node utilities | Context engineering, formatting, fallback handling |

### Pipeline Flow (Standard Path)

**Entry:** `intent_router`
- Routes to `handle_distress` / `handle_meditation` / `handle_casual` / `resolve_followup` (standard/deep) or `retrieve_documents` (fast)

**Fast Path (`FastGraphStrategy`):**
- Skips `resolve_followup`, `decompose_query`, `rerank_documents`, `grade_documents`, `reflect_on_answer`, `verify_answer`, `check_contradiction`, `explain_retrieval`
- Runs: `intent_router` → `retrieve_documents` → `generate_answer` → `format_final_answer`
- Brings latency from ~133s down to ~25s for simple doctrine queries

**QUERY path (full anti-hallucination chain - `StandardGraphStrategy`/`DeepGraphStrategy`):**
- `resolve_followup` — resolves pronouns/references from conversation history
- `decompose_query` — splits complex questions into atomic sub-queries
- `navigate_knowledge_tree` (parallel with `generate_hyde`) — PageIndex-inspired cluster selection + HyDE hypothetical answer generation
- `retrieve_documents` — two-phase hybrid retrieval (RAPTOR summaries + leaf chunks + LightRAG graph + Parent-Child resolution + MMR diversity re-ranking). Expands queries with doctrinal synonyms and injects doctrine keywords
- `rerank_documents` — Cascaded ColBERT + CrossEncoder re-ranking
- `grade_documents` — CRAG batch relevance grading (single LLM call for all docs)
- `check_context_sufficiency` — iterative sufficiency check; clears cluster filters if insufficient
- Conditional branch: relevant → `enrich_context` | rewrite → `rewrite_query` (max 3x) | fallback → `handle_fallback`
- `enrich_context` — fetches neighbor chunks for broader context
- `context_engineer` — assembles structured prompt layers (persona, knowledge, user state, instructions)
- `generate_answer` — inline hint extraction + context-only generation (merged Stimulus RAG + generation)
- `reflect_on_answer` — Self-Reflection RAG: **LettuceDetect only** (embedding/lexical faithfulness). LLM self-consistency check is **disabled** to save ~45s without quality loss on spiritual paraphrasing
- Conditional branch: valid → `verify_answer` | needs_correction → `rewrite_query` (max 3x) | exhausted → `handle_fallback`
- `verify_answer` — **LettuceDetect only** (threshold 0.22 + doctrine boost). CoVe sub-question verification and alternative-answer self-consistency are **disabled** to save ~60s. Fast/tier2_simple tiers already bypass this node
- `check_contradiction` — multi-turn contradiction detection against conversation history
- `explain_retrieval` (parallel) — generates 1-sentence reasoning for each top citation
- `format_final_answer` — confidence-based graduated responses, citation formatting, caveats

**Post-Graph (pipeline stages after `GraphStage`)**
- **Zero-Shot Output Rail** (`OutputGuardrailStage`) — moderates/blocks harmful output
- **Telemetry Logging** — query trace + response trace saved to telemetry DB

The `GraphState` TypedDict in `rag/states.py` is the data contract flowing through all nodes. It includes `request_id` for end-to-end log correlation.

### Pre-Graph (pipeline stages before `GraphStage`)
1. **Zero-Shot Input Rail** (`guardrails/` via `InputGuardrailStage`) — blocks harmful/off-topic input
2. **Serene Mind Distress Detector** (`services/serene_mind_engine.py` via `on_device_intent.py`) — assesses emotional state; does NOT bypass RAG — distress queries run through the full pipeline to retrieve compassionate teachings

## Architecture: Guardrails

Located in `backend/guardrails/`. The guardrails system is chain-based and supports multiple handlers:

| Component | Purpose |
|-----------|---------|
| `base.py` | Abstract base class for guardrail handlers |
| `chain.py` | Orchestrates guardrail chain execution |
| `disabled_handler.py` | No-op handler for bypass mode |
| `lightweight_handler.py` | Zero-shot LLM-based guardrails (default, fast) |
| `nemo_handler.py` | NeMo Guardrails integration for complex policies |
| `config/` | Guardrail configuration files |

## Architecture: Ingestion Pipeline

`POST /api/ingest` triggers `ingest/pipeline.py:IngestionPipeline.ingest_url()`:

1. Detect URL type (YouTube video / playlist / image)
2. Fetch transcript (3-tier: manual captions → Whisper → auto-captions) or OCR via `image_loader.py`
3. Correct transcript (LLM via `corrector.py`)
4. Audit quality (LLM via `auditor.py`) — rejects low-quality/irrelevant content
5. Clean text (`cleaner.py`)
6. Chunk with `RecursiveCharacterTextSplitter(500 chars, 50 overlap)`
7. Embed with `all-MiniLM-L6-v2` → upsert to Qdrant (level 0: leaf chunks)
8. Build Parent-Child index (`raptor.py`): chunks with metadata → upsert to Qdrant

Playlist ingestion uses concurrent workers (`TRANSCRIPT_CONCURRENT_WORKERS=4`).

## Dependency Injection Pattern

`backend/app/dependencies.py` is the **composition root**. `ServiceContainer` creates all singleton service instances in dependency order and holds them for the lifetime of the application. Import via `get_container()`. Never instantiate services directly in route handlers.

## Frontend ↔ Backend Integration

The React frontend (`src/lib/aiService.ts`) supports three modes:
- `placeholder` — offline mode with canned responses (default)
- `custom` — points to the FastAPI backend at `POST /api/chat`
- `openai` — direct OpenAI API calls

The backend `ChatRequest` expects `{ messages, user_message, meditation_step }`. The frontend sends the full conversation history on each turn.

## Service Matrix

### Core LLM Services
| Service | File | Description |
|---------|------|-------------|
| **Ollama** | `ollama_service.py` | Ollama LLM client (Sarvam 30B, etc.) |
| **OpenRouter** | `openrouter_service.py` | OpenRouter multi-model proxy |
| **Sarvam** | `sarvam_service.py` | Sarvam 30B local inference |
| **Sarvam STT** | `sarvam_stt_service.py` | Speech-to-Text via Sarvam |
| **Base LLM** | `base_llm_service.py` | Abstract base for LLM providers |
| **LLM Factory** | `llm_factory.py` | Factory for creating LLM service instances |
| **LLM Protocol** | `llm_protocol.py` | Protocol definitions for LLM services |
| **Multi-Provider** | `multi_provider_llm.py` | Multi-provider LLM orchestration |
| **Model Registry** | `model_registry.py` | Model registration and discovery |
| **Model Failover** | `model_failover.py` | Automatic failover between models |
| **Krutrim** | `krutrim_service.py` | Krutrim AI LLM client |

### Retrieval & Vector Services
| Service | File | Description |
|---------|------|-------------|
| **Embedding** | `embedding_service.py` | `all-MiniLM-L6-v2` embeddings |
| **Qdrant** | `qdrant_service.py` | Qdrant vector DB client |
| **LightRAG** | `lightrag_service.py` | LightRAG graph-based retrieval |
| **Reranker** | `reranker_service.py` | ColBERT + CrossEncoder re-ranking |
| **RRF Ranker** | `rrf_ranker.py` | Reciprocal Rank Fusion ranker |
| **Concurrent Retriever** | `concurrent_retriever.py` | Parallel retrieval worker |
| **Adaptive Chunking** | `adaptive_chunking_service.py` | Dynamic chunk sizing |
| **Chunking Adapter** | `adaptive_chunking_adapter.py` | Chunking strategy adapter |
| **Contextual Chunking** | `contextual_chunking_service.py` | Context-aware text splitting |
| **Proposition** | `proposition_service.py` | Proposition-based chunking |
| **Semantic Cache** | `semantic_cache.py` | Semantic result caching |
| **Vector Optimizer** | `vector_optimizer.py` | Vector space optimization |

### Conversation & Memory
| Service | File | Description |
|---------|------|-------------|
| **Memory v1** | `memory_service.py` | Conversation memory management |
| **Memory v2** | `memory_service_v2.py` | Enhanced memory with context compression |
| **Serene Mind** | `serene_mind_engine.py` | 4-step guided meditation + distress detection |
| **Context Compressor** | `context_compressor.py` | Compresses long context for LLM windows |
| **Prompt Store** | `prompt_store.py` | Dynamic prompt template management |
| **User Profile** | `user_profile_service.py` | User preferences and profile management |
| **Feedback** | `feedback_service.py` | User feedback collection and processing |

### Audio & Speech
| Service | File | Description |
|---------|------|-------------|
| **Whisper Local** | `whisper_local_service.py` | Local Whisper transcription |
| **OCR** | `ocr_service.py` | Image-to-text via EasyOCR |
| **Phonetic** | `phonetic.py` | Phonetic text processing |

### Infrastructure & Reliability
| Service | File | Description |
|---------|------|-------------|
| **Cache** | `cache_service.py` | Multi-tier caching (Redis, in-memory) |
| **Circuit Breaker** | `circuit_breaker.py` | Fault tolerance for LLM calls |
| **Cost Tracker** | `cost_tracker.py` | Token/cost usage tracking |
| **Config Watcher** | `config_watcher.py` | Hot-reload configuration |
| **Container Builder** | `container_builder.py` | Containerized service lifecycle |
| **HTTP Client Pool** | `http_client_pool.py` | Reusable HTTP session management |
| **A/B Testing** | `ab_testing.py` | Experiment framework for response variants |
| **Doctrine Cache** | `doctrine_cache.py` | Spiritual-teaching-specific caching |
| **Semantic Router Fallback** | `semantic_router_fallback.py` | Fallback routing for semantic queries |
| **Language Router** | `language_router.py` | Route by detected language |
| **Tenant Context** | `tenant_context.py` | Multi-tenant context isolation |
| **Ingestion Tracker** | `ingestion_tracker.py` | Pipeline progress tracking |
| **Streaming Generator** | `streaming_generator.py` | Server-sent Event stream generation |
| **Streaming Hardening** | `streaming_hardening.py` | Resilient streaming with retries |

### Quality & Safety
| Service | File | Description |
|---------|------|-------------|
| **LettuceDetect** | `lettuce_detect_service.py` | Embedding/lexical faithfulness checker |
| **CoT Verifier** | `cot_verifier.py` | Chain-of-Thought verification |
| **Compliance Logger** | `compliance_logger.py` | Audit logging for compliance |
| **Auth** | `auth_service.py` | Authentication and authorization |
| **Cookie Helper** | `cookie_helper.py` | Secure cookie management |
| **Sarvam Exceptions** | `sarvam_exceptions.py` | Custom exceptions for Sarvam |

## Benchmarks Suite

| Script | Purpose |
|--------|---------|
| `smoke_doctrine.py` | Quick smoke test for basic retrieval |
| `focused_fix_test.py` | Regression tests for specific bug fixes |
| `comprehensive_benchmark.py` | Full pipeline evaluation with RAGAS |
| `ruthless_benchmark.py` | Stress test with edge cases and adversarial queries |
| `ragas_eval.py` | RAGAS metric evaluation (faithfulness, answer_relevancy, etc.) |
| `sdlc_rag_benchmark.py` | SDLC-style benchmark with golden question bank |
| `chunk_size_evaluation.py` | Evaluate optimal chunk sizing parameters |
| `validate_graph.py` | Validate graph wiring and node connectivity |
| `native_eval.py` | Native (non-RAGAS) evaluation metrics |
| `generate_dashboard.py` | Generate HTML dashboard from benchmark results |
| `run_all.py` | Run all benchmarks sequentially |

## Test Suite

Backend tests are in `backend/tests/` with `conftest.py` fixtures:
- **Unit**: `test_abstractions`, `test_context_compressor`, `test_token_budget_guard`, `test_embedding_service`
- **Integration**: `test_chat_endpoint`, `test_serene_mind`, `test_guardrails`
- **Contract**: `test_retrieve_documents_contract`, `test_tiered_router`
- **Streaming**: `test_tiered_routing_streaming`
- **RAGAS**: `test_rag_advanced`
- **Admin**: `test_admin`
- **Memory**: `test_memory_api`, `test_memory_context`, `test_memory_service`
- **Observability**: `test_sarvam_observability`, `test_observability`
- **OpenRouter**: `test_openrouter`
- **Adaptive Chunking**: `test_adaptive_chunking`
- **Coalescer**: `test_coalescer`
- **Concurrent Retriever**: `test_concurrent_retriever`
- **FlashRank**: `test_flashrank_rerank`
- **Intent Parsing**: `test_intent_complexity_parser`, `test_intent_prompt_semantics`

Frontend tests are in `src/test/` and `src/tests/` using Vitest.

### Security Audit Scripts (`scripts/security/`)
- `audit_log_pii.sh` — scans for PII in log statements
- `audit_secrets.sh` — scans for hardcoded secrets
- `audit_endpoints.sh` — audits API endpoint exposure
- `audit_cors_headers.sh` — checks CORS and security headers
- `run_emergent_audit.sh` — runs all above in sequence
- Report output: `scripts/security/report.md`
- Programmatic runner: `scripts/security_audit.py`

## Scripts & Tooling

### Ingestion Scripts (`scripts/ingestion/`)
- `bulk_ingest_async.py` — Async batch ingestion
- `bulk_ingest_whisper.py` — Batch transcription via Whisper
- `extract_transcripts.py` — Extract YouTube transcripts
- `ingest_four_sacred_secrets.py` — Ingest specific content
- `ingest_host_whisper.py` — Host-side Whisper ingestion
- `ingest_pageindex_json.py` — Ingest PageIndex JSON
- `ingest_structure_to_qdrant.py` — Structured data ingestion
- `ingest_youtube_seeds.py` — Seed initial content
- `retry_failed_videos.py` — Retry transient failures
- `run_pageindex.py` — PageIndex orchestration
- `smart_extract_and_ingest.py` — Smart extraction with auto-decision
- `verify_ingestion_quality.py` — Quality validation post-ingest

### Operational Scripts (`scripts/ops/`)
- `backup_neo4j.py` — Neo4j graph backups
- `backup_qdrant.py` — Qdrant vector DB backups
- `cleanup_data.py` — Data cleanup routines
- `flush_cache.py` — Cache invalidation
- `full_cleanup.py` — Complete environment reset
- `heal_neo4j_poison.py` — Neo4j corruption repair
- `reset_state.py` — Full state reset

### Other Scripts
- `check_docker_health.py` — Docker health checks
- `db_rectify.py` — Database schema fixes
- `generate_all_skills.py` — Skill generation utility
- `load_test.py` — Performance load testing
- `migrate_tenant_collections.py` — Tenant data migration
- `monitoring_dashboard.py` — Metrics dashboard
- `security_audit.py` — Security audit runner
- `whatsapp_webhook.py` — WhatsApp webhook handler

## Deployment & Infrastructure

### Docker Compose
```bash
cd backend
docker compose up -d --build  # Full stack
```

Services: **backend**, **qdrant**, **redis**, **neo4j**, **jaeger**
(ollama runs on the host)

### Kubernetes / Helm
- `k8s/helm/mukthiguru/` — Helm chart for Kubernetes deployment
- `k8s/skaffold.yaml` — Skaffold configuration for local k8s development

### Railway (Production Deployment)
- **Project**: `resilient-embrace` | **Service**: `askmukthiguru-8119b0e8` | **Environment**: `production`
- **Deploy method**: Use `railway up` (tarball upload) — **NOT** `railway redeploy --from-source`
  - `railway up` uploads a tarball and deploys reliably
  - `railway redeploy --from-source` gets stuck at INITIALIZING on this repo
- **Replicas**: Set to **1 replica** in `railway.json` — 2 replicas caused second replica to fail init timeout
- **Health checks**: 
  - `/api/healthz` — intercepted by `start_railway.py` wrapper, returns 200 for 90s grace period
  - `/api/health` — real per-service health, returns `ready: false` until `startup_complete=True`
- **Docker path for CLI**: `export PATH="/Users/harshodaikolluru/.docker/bin:$PATH" && railway <cmd>`
- **Link service**:
  ```bash
  railway link --project resilient-embrace --service askmukthiguru-8119b0e8
  ```
- **View logs**: `railway logs` (shows interleaved from all deployments; use `--deployment <id>` for specific)
- **Environment variables**: Set via `railway variables --json '{"KEY": "value"}'` or dashboard
- **Key env vars for backend**: `OPENROUTER_API_KEY`, `SUPABASE_URL`, `SUPABASE_KEY`, `QDRANT_URL`, `QDRANT_API_KEY`, `REDIS_URL`, `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD`, `IS_PRODUCTION=true`

### CI/CD (`.github/workflows/`)
- `build-deploy.yml` — Build and deploy pipeline
- `dependency-check.yml` — Dependency vulnerability scanning
- `lint-test.yml` — Lint and test automation
- `security-audit.yml` — Automated security auditing

## Terminology (from SPEC_DEV.md)

| Term | Meaning |
|------|---------|
| **Stimulus RAG** | Extract key hint phrases from retrieved docs before generation |
| **CRAG** | Corrective RAG — grade docs, rewrite query if poor, loop up to 3x |
| **Self-RAG** | LLM checks its own answer for faithfulness to retrieved context |
| **CoVe** | Chain of Verification — generate sub-questions to fact-check the answer |
| **Parent-Child Retrieval** | 400-char child chunks in Qdrant, 1500-char Parent Context injected into the LLM |
| **Beautiful State** | Core teaching concept — state of calm, joy, connection |
| **Serene Mind** | 4-step guided meditation flow triggered by distress detection |
| **LettuceDetect** | Embedding + lexical faithfulness checker |
| **RAPTOR** | Recursive Abstractive Processing for Tree-based Representation |
| **HyDE** | Hypothetical Document Embedding — generate answer, then embed for retrieval |
| **PageIndex** | Hierarchical tree-based document organization |
| **LightRAG** | Graph-augmented RAG using keyword extraction and graph traversal |
| **MMR** | Maximal Marginal Relevance — diversity in retrieval |
| **RRF** | Reciprocal Rank Fusion — score fusion across multiple retrievers |
| **ColBERT** | Contextualized late interaction bi-encoder re-ranking |
| **CrossEncoder** | Full-context cross-encoder re-ranking |

## MCP Tooling

### Active Local Servers (`.mcp.json`)

| Server | Language | Purpose |
|--------|----------|---------|
| **code-review-graph** | python | Incremental knowledge graph — review, impact, architecture |
| **codegraph** | node | Live code intelligence — callers, callees, traces |
| **graphify** | python | PR analysis, pathfinding, community detection |
| **claude-mem** | node | Persistent project memory — observations, context |

Runtime requirement: Node 22 LTS strictly (Node 25.x has a WASM allocation bug that OOM-crashes codegraph); claude-mem's worker needs Bun ≥1.3.14. A git `post-commit` hook keeps these indexes synchronized automatically.

### Additional MCP Servers (ECC bundled)

A catalogue of ~30 additional servers is available in `ecc/mcp-configs/mcp-servers.json` (GitHub, Jira, Supabase, Playwright, context7, exa-web-search, sequential-thinking, etc.). Copy the ones you need into your local `.mcp.json` or global `~/.claude/mcp.json`.

### Plugins

| Plugin | What it does |
|--------|-------------|
| **caveman** | Terse output mode (`/caveman lite|full|ultra`) |

### Workflow Priority

1. **Prefer MCP tools first** over Grep/Glob/Read when you need to find symbols, trace flows, review changes, or get architecture overviews.
2. **Fall back to raw Read/Edit** only when editing a specific file or doing a quick string replacement.
3. **Update CLAUDE.md and AGENTS.md** whenever any directory structure, backend service additions, environment configuration, or core execution pipeline patterns change.

## Ponytail & Headroom Guidelines

### Ponytail Principle
- **Thin wrappers**: Prefer small, focused helper scripts or inline functions over heavy abstractions or new classes.
- **Self-Checks**: Python files should contain a runnable `if __name__ == "__main__":` block at the bottom for quick verification.
- **Optional/Stubbed Features**: Gracefully degrade or skip components if dependencies are not available on the runtime host.
- **LRU Cache Usage**: Use simple caching patterns (e.g. `lru_cache`) instead of custom state tracking classes where possible.

### Headroom Principle
- **Cost Steering**: Automatically steer LLM prompting towards brevity (`COST_STEERED_BREVITY_LIMIT` words) when context/history length is high to optimize token usage.
- **Reversible Context Compression (CCR)**: Allow the LLM to request full text for compressed text using `[RETRIEVE: <source_url>]` pattern; generation stage will intercept and swap the original text.
- **Timeout and Resource Headroom**: Always configure timeouts with safety margins (e.g. 120s timeouts for sequence calls, or 10% GPU/CUDA headroom) to avoid transient service lockups.
