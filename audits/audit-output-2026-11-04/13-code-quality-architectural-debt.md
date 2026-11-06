# 13 — Code quality, architectural debt and removal candidates

Owner: S1. Target: `origin/main@46b808fb`. Conventions: `CONVENTIONS.md`.
Related: request flow (05), security (14), reliability and cost (15), memory design (12, S3), data stores (06, S2).

## 1. Scale and method

| Metric | Value | Label |
|---|---|---|
| Tracked files | 5,499 | [V-GIT] |
| Python lines (tracked, incl. tests and scripts) | ~531,000 | [V-STATIC] |
| Runtime Python modules (excl. tests, colab, benchmarks, scripts) | 581 | [V-STATIC] AST scan |
| Python files > 1,500 lines (excl. tests) | 25 | [V-STATIC] |
| `Settings` fields / boolean flags | 679 / 184 | [V-STATIC] `app/config.py` AST |
| FastAPI handlers | 231 | [V-STATIC] |
| Backend test functions / test files | 7,413 / 780 | [V-STATIC] (docs claim "9,918 tests pass", which includes parametrisation [DOC-CLAIM]) |
| `ruff check --select E9,F` on runtime code | 0 findings | [V-STATIC] run on snapshot |
| Module-level import cycles | 0 | [V-STATIC] Tarjan SCC over 1,110 edges |
| Function-local imports | 1,465 | [V-STATIC] |
| `except Exception` in runtime code | 1,513 (70 silent swallows: `pass` / `continue` / `return None|{}|[]|False`) | [V-STATIC] |
| Markdown outside `memory/` | 11.2 MB; `lessons.md` 14,209 lines / 2.0 MB | [V-STATIC] |

Method: AST scripts in the scratchpad, `ruff`, `rg` counts, and targeted reading. Tests were not executed: no virtualenv exists and installing is out of scope.

Assessment in one paragraph: the code is not sloppy at the line level (ruff clean, no import cycles, consistent docstrings, many guards). The debt is structural. A few modules carry most of the logic in single giant functions. Every subsystem has 3–8 overlapping implementations. A 679-field configuration creates a state space nobody can test. A 2 MB lesson log and 11 MB of markdown replace design. Each layer of hardening was added beside the old layer instead of replacing it.

## 2. God modules

| File | Lines | Functions | Largest function | Label |
|---|---|---|---|---|
| `backend/services/first_person_pipeline.py` | 6,017 | 78 | `execute` line 3509, **2,145 lines** | [V-STATIC] |
| `backend/rag/nodes/generation.py` | 5,302 | 82 | `generate_answer` line 2632, 1,247 lines | [V-STATIC] |
| `backend/ingest/pipeline.py` | 4,408 | 52 | `_embed_and_index` line 3221, 375 lines | [V-STATIC] |
| `backend/app/api/admin.py` | 2,798 | 108 (91 routes) | `get_corpus_provenance`, 127 lines | [V-STATIC] |
| `backend/app/config.py` | 2,650 | 31 | 679 fields in one class | [V-STATIC] |
| `backend/rag/nodes/retrieval.py` | 2,605 | 38 | `retrieve_documents` line 1437, 1,168 lines | [V-STATIC] |
| `backend/services/memory_service_v2.py` | 1,890 | 54 | `build_personal_knowledge_graph`, 586 lines | [V-STATIC] |
| `backend/rag/nodes/intent.py` | 1,886 | 24 | `_intent_router_impl`, 517 lines | [V-STATIC] |
| `backend/services/openrouter_service.py` | 1,878 | 38 | `_call_api`, 499 lines | [V-STATIC] |
| `backend/app/pipeline/stages/first_person_bridge.py` | 1,374 | 20 | `_bridge`, 554 lines | [V-STATIC] |
| `backend/app/main.py` | 1,605 | 26 | `_background_startup_body`, 405 lines | [V-STATIC] |

## 3. Register A — code to remove

Each row: downstream dependencies, migration risk, and the verification that must pass before removal.

| ID | Item | Evidence | Downstream dependencies | Migration risk | Verification before removal |
|---|---|---|---|---|---|
| CQ-R1 | Repo-root alias packages `app/`, `rag/`, `services/`, `ingest/` (each one `__init__.py` that rewrites `sys.modules` to `backend.*`) | `app/__init__.py:1-19`, `rag/__init__.py`, etc. [V-STATIC] | Root `pytest.ini` (`pythonpath = .`), root scripts that `import app...` | Medium: scripts run from repo root break until they set `PYTHONPATH=backend` | Run root scripts and root pytest with `PYTHONPATH=backend`; grep for `import app` outside `backend/` |
| CQ-R2 | Repo-root stub `langdetect/__init__.py` (always returns `"en"`) | `langdetect/__init__.py:9-12`; real import at `scripts/ingestion/backfill_metadata.py:202-203` [V-STATIC] | Root-level tests that relied on the stub | Low | Replace with a pytest fixture/monkeypatch; confirm no runtime path imports the stub (see CQ-005) |
| CQ-R3 | Repo-root stub `langchain_text_splitters/` | has a fail-closed guard outside pytest [V-STATIC] | root tests | Low | same as CQ-R2 |
| CQ-R4 | `ToneAdapterStage` (deliberate no-op) | `tone_adapter_stage.py:31-33` [V-STATIC]; CLAUDE.md says "do not clean it up" | `pipeline_builder.py`, `tests/test_*tone*` | Low, but CLAUDE.md forbids it today | Owner decision; remove only with the test that pins it [HUMAN] |
| CQ-R5 | Dormant modules: `app/generation/*` (150 lines), `app/streaming/*` (196), `app/verification/*` (165), `app/intake/short_circuit.py` (271), `rag/retrieval/federated_engine.py` (150), `src/lib/streaming/ResilientStreamTransport.ts` | CLAUDE.md "Dormant modules"; 0–1 runtime importers each [V-STATIC] | their tests | Low | Owner decision after graded run (CLAUDE.md) [HUMAN] |
| CQ-R6 | `app/gradio_ui.py`, `app/chat_engine.py` (627 lines, self-check only), `rag/dspy_engine.py` | 1 importer each [V-STATIC] | dspy (two packages: `dspy==3.4.0`, `dspy-ai==3.2.1`, `requirements.lock`) | Low | import-graph check; drop `dspy-ai` duplicate |
| CQ-R7 | 27 unread `Settings` fields (e.g. `sarvam_daily_budget_usd`, `semantic_router_enabled`, `llm_provider_chain`, `verifier_pass_ratio`, `persona_max_paragraphs`) | AST scan, no reader outside `config.py` [V-STATIC] | `.env.example`, docs | Low | Remove field and its `.env.example` line together |
| CQ-R8 | WhatsApp legacy HS256 signer with default `"default-dev-jwt-secret"` | `whatsapp_bot/wa_bot.py:72, 738-753`; docstring says live path no longer uses it [V-STATIC] | its tests | Low | grep callers; delete with tests |
| CQ-R9 | Tracked data backups `data/*.json` (10 MB: Neo4j dumps, Qdrant chunk backups, `security_report.json` with local paths) | `data/` [V-STATIC] | none at runtime [INF] | Low technical; rights/disclosure reasons in doc 14 SEC-005 | Move to private storage; rewrite history only by owner decision [HUMAN] |
| CQ-R10 | Loose root files that break the repo's own clean-root rule: `FIRST_PERSON_CONTEXT_HARNESS_AND_TAGGING_PLAN_2026-10-20.md`, `video_*_analysis_*.md` (2), `handoff.md`, `roadmap.md`, `lessons.md` | `ls *.md` at root [V-STATIC]; rule in CLAUDE.md "Clean Root Policy" | docs links | Low | Move under `docs/`; fix links |

## 4. Register B — refactor, simplify or consolidate

### CQ-001 — Split the giant functions
| Field | Value |
|---|---|
| Pillars | P3, P1 |
| Category | Maintainability |
| Severity | P2 |
| Type | Confirmed defect (maintainability) |
| Confidence | High |
| Evidence | §2: `FirstPersonPipeline.execute` 2,145 lines; `generate_answer` 1,247; `retrieve_documents` 1,168. |
| Actual behaviour | One function holds crisis check, cache, retrieval, six gates, harness, telemetry and serving. A change in one gate needs a reader to hold 2,000 lines. |
| Expected behaviour | A pipeline of named steps (≤ 150 lines each), each with typed input and output, each unit-testable without the others. |
| Root cause | Incremental gate additions inside one function. |
| User impact | Indirect: slow, risky fixes. |
| Remediation | Extract steps from `execute` in this order: crisis/cache → retrieve → integrity/content gates → LLM gates → harness → assemble. Keep behaviour byte-identical; use the existing 1,600-line `tests/test_first_person_pipeline.py` as the oracle. |
| Acceptance criteria | No function > 200 lines in the three files; all existing FP tests green; golden-question output identical (doc 18). |
| Regression test | Snapshot test of `PipelineResult` for 50 fixed questions with mocked stores. |
| Implementation risk | Medium; mechanical but large. Pre-requisite for SYS-003. |
| Verification | [V-STATIC] |

### CQ-002 — Consolidate LLM provider abstractions
| Field | Value |
|---|---|
| Pillars | P1, P3 |
| Category | Duplication |
| Severity | P2 |
| Type | Confirmed defect |
| Confidence | High |
| Evidence | `services/`: `base_llm_service.py`, `llm/` (`backend/services/llm/base.py`, `backend/services/llm/factory.py`, 4 providers), `llm_factory.py`, `llm_gateway.py` (641), `llm_protocol.py`, `multi_provider_llm.py`, `llm_budget_guard.py`, `openrouter_service.py` (1,878), `sarvam_service.py` (1,337), `ollama_service.py` (1,091), `nim_service.py` (844), `semantic_model_router.py`, `jev_router_service.py`; container exposes `ollama`, `openrouter`, `krutrim`, `llm_gateway`, `multi_provider_llm` (`app/container.py`). `container.ollama` holds the OpenRouter provider (`container.py:191`). CLAUDE.md: "share no code, so patch the provider actually in use". |
| Actual behaviour | A fix to timeouts, retries, cost accounting or prompt caching must be made in up to four classes. |
| Expected behaviour | One provider interface (`generate`, `generate_fast`, `stream`) with one HTTP client per vendor, one retry/timeout/budget policy, one accounting hook. |
| Root cause | Provider migrations (Ollama → Sarvam → OpenRouter) kept each old class. |
| Remediation | Keep `services/llm/base.py` as the interface and `OpenRouterProvider` as the live implementation. Freeze Sarvam/Ollama/NIM behind the same interface or remove them (owner decision). Rename `container.ollama` to `container.llm`. |
| Acceptance criteria | One call path for all serve-time LLM calls; per-call metrics (`guru_llm_tokens_total`, cost) emitted from one place. |
| Regression test | Contract test run against each kept provider with a fake HTTP server. |
| Implementation risk | Medium. |
| Verification | [V-STATIC] |

### CQ-003 — Consolidate cache layers
| Field | Value |
|---|---|
| Pillars | P1, P3 |
| Severity | P2 |
| Type | Architectural risk |
| Confidence | High |
| Evidence | `services/cache_service.py`, `services/cache/` (manager, redis, memory, semantic, hot adapters, invalidation, llm_cache), `hot_cache.py`, `semantic_cache.py`, `retrieval_cache.py`, `turboquant_cache.py`, `doctrine_cache.py`, compose `gptcache-server` (zilliz/gptcache 0.1.44) [V-STATIC]. |
| Actual behaviour | At least eight cache mechanisms with separate keys and invalidation. The FP path uses only the exact cache; the general path also uses the semantic cache (0.92 similarity, 7-day TTL, `config.py:1588-1599`). |
| Expected behaviour | Two caches: an exact response cache keyed by (normalised question, language, collection version, prompt version, policy version), and an embedding cache. A semantic answer cache only if measured safe. |
| Root cause | Each latency push added a new tier. |
| Remediation | Inventory hit rates (metric `guru_cache_operations_total` exists), delete tiers with negligible hits, add version components to keys. |
| Acceptance criteria | ≤ 3 cache tiers; every key includes the collection and prompt version; invalidation test on collection switch. |
| Regression test | Cache-key version test. |
| Implementation risk | Low-medium. |
| Verification | [V-STATIC]; hit rates [LIVE-L]. |

### CQ-004 — Consolidate memory subsystems (design owned by S3, doc 12)
Evidence: `memory_service.py`, `memory_service_v2.py` (1,890), `layered_memory/`, `canonical_memory/` (27 files incl. `red_team.py`, `simulation.py`, `shadow.py`, `canary.py`, `FINAL_STATUS.md`), `services/memory/` (OKF + episodic), `memory_outbox.py`, `memory_source.py`, Second Brain vault [V-STATIC]. Severity P2, Architectural risk. Remediation and target design: doc 12.

### CQ-005 — Root stub `langdetect` silently mislabels language when it shadows the real package
| Field | Value |
|---|---|
| Pillars | P3 |
| Severity | P2 |
| Type | Probable defect |
| Confidence | Medium |
| Evidence | `langdetect/__init__.py` returns `"en"` for every input and has no guard; `langchain_text_splitters/__init__.py` next to it has a fail-closed guard for exactly this reason. Real consumer: `scripts/ingestion/backfill_metadata.py:202-203`. |
| Actual behaviour | Any process with the repo root on `sys.path` (root `pytest`, `python -m scripts...`) gets the stub. |
| Expected behaviour | A test double never shadows a runtime dependency. |
| Remediation | Delete the stub (CQ-R2); use monkeypatch in tests. |
| Acceptance criteria | `python -I -c "import langdetect; print(langdetect.__file__)"` from repo root resolves to site-packages. |
| Implementation risk | Low. |
| Verification | [V-STATIC]; whether past ingestion runs used the stub [LIVE-L] (cross-ref S2, doc 06). |

### CQ-006 — Broad exception handling hides faults
| Field | Value |
|---|---|
| Pillars | P1, P3 |
| Severity | P2 |
| Type | Confirmed defect (pattern) |
| Confidence | High |
| Evidence | 1,513 `except Exception` in runtime code; 70 silent swallows (top files: `app/api/health.py` 4, `services/qdrant/indexer.py` 3, `services/kg_algorithms.py` 3, `app/unified_observability.py` 3, `services/llm_gateway.py` 2, `services/circuit_breaker.py` 2, `services/canonical_memory/retriever.py` 2, `services/cache/semantic_adapter.py` 2); 62 `noqa: BLE001`. |
| Actual behaviour | Many components "fail open" or degrade without a metric. SYS-001 is one consequence. |
| Expected behaviour | Every broad catch either re-raises, returns a typed failure, or increments a named counter. Safety- and voice-relevant paths fail closed. |
| Remediation | Add a ruff rule set (`BLE`, `S110`, `SIM105`) with a baseline file; fix silent swallows first; require a metric on each degrade path. |
| Acceptance criteria | 0 silent swallows in `app/`, `rag/`, `services/first_person_*`; every degrade path has a counter. |
| Regression test | ruff in CI with the new rules. |
| Implementation risk | Low per site; large total. |
| Verification | [V-STATIC] |

### CQ-007 — Cycles are hidden by 1,465 function-local imports
Evidence: 0 module-level cycles, 1,465 imports inside functions; `rag/pipeline_registry.py:16-21` documents the cycle `graph_strategies → pipeline_registry → app.pipeline.stages → … → graph_strategies` [V-STATIC]. Severity P2, Architectural risk. Remediation: define a layer order (`domain` → `services` → `rag` → `app.pipeline` → `app.api`) and enforce it with `import-linter` (open source). Acceptance: contracts pass with ≤ 50 justified lazy imports. Risk: medium.

### CQ-008 — Test suite volume overstates protection
| Field | Value |
|---|---|
| Pillars | P3, P6 |
| Severity | P2 |
| Type | Confirmed defect (test design) |
| Confidence | Medium |
| Evidence | 7,413 test functions; 440 of 780 files use mocks; 112 test functions assert on source text (`inspect.getsource`, `.read_text()` then `in src`), e.g. `tests/test_first_person_bridge.py`, `tests/test_okf_pipeline_integrity.py`, `tests/test_chat_readiness_guard.py`; 43 tests assert only mock calls; 104 skip/xfail markers. |
| Actual behaviour | Source-text tests pin implementation strings, so refactors (CQ-001) fail tests that would pass on behaviour. Mock-only tests prove call order, not outcomes. No test proves the end-to-end FP answer on real stores (stores are not in CI). |
| Expected behaviour | Behaviour tests at stage and pipeline level; a small set of contract tests on real containers in CI (Qdrant + Redis test containers with a fixture collection). |
| Remediation | (1) Tag source-text tests and replace them during CQ-001. (2) Add a fixture Qdrant collection (≤ 200 points, public-safe) and run FP pipeline tests against it in CI. |
| Acceptance criteria | Source-text assertions < 20; one CI job runs the FP pipeline against real Qdrant + Redis containers. |
| Implementation risk | Medium. |
| Verification | [V-STATIC]; tests not executed here. |

### CQ-009 — Documentation volume is a maintenance and token cost; key docs drift
| Field | Value |
|---|---|
| Pillars | P3, P4 |
| Severity | P2 |
| Type | Confirmed defect |
| Confidence | High |
| Evidence | `lessons.md` 14,209 lines / 2.0 MB; `docs/plans/PROD_READINESS_TASK_LIST_2026-10-11.md` 408 KB; 483 markdown files under `docs/`, 166 at `docs/` top level; 11.2 MB markdown outside `memory/`; `CLAUDE.md` + `AGENTS.md` = 106 KB, loaded into agent sessions. The task list itself names "Too many documents, no single list" as cause #8 [DOC-CLAIM] line 191. CLAUDE.md pipeline order is stale vs `pipeline_builder.py:46-94` (§05). CLAUDE.md quotes relevance budget 12 s; code default is 25 s (`config.py:480`). |
| Actual behaviour | Truth is spread across thousands of dated paragraphs. Agents spend tokens reconciling them; stale statements survive. |
| Expected behaviour | Short living docs (architecture, runbooks, ADRs) generated or checked against code; history archived. |
| Remediation | Freeze `lessons.md`; move to `docs/archive/`. Keep a ≤ 15 KB `CLAUDE.md` of invariants that each map to a guard test. Add a CI check that the pipeline order in docs matches `build_default_pipeline()`. |
| Acceptance criteria | Root `CLAUDE.md` ≤ 15 KB; doc-vs-code check for pipeline order and key flag defaults in CI. |
| Implementation risk | Low. |
| Verification | [V-STATIC] |

### CQ-010 — Configuration surface is too large to test
| Field | Value |
|---|---|
| Pillars | P1, P3 |
| Severity | P2 |
| Type | Architectural risk |
| Confidence | High |
| Evidence | 679 fields, 184 booleans in one `Settings` class; 27 fields with no reader; 23 names read through `getattr(settings, "x", default)` that are not declared (e.g. `qdrant_timeout` in `services/qdrant/client.py:102`, `llm_generate_timeout` in `ingest/pipeline.py:373`, `upload_dir` in `ingest/pipeline.py:781`, `supabase_service_role_key` in `scripts/ops/eu_ai_act_backfill.py:255`); `model_config` uses `extra="ignore"` (`config.py:52-55`). |
| Actual behaviour | An operator can set `QDRANT_TIMEOUT` and nothing changes; the default silently wins. 2^184 flag combinations exist; only a few are tested. |
| Expected behaviour | Typed config split by component; every field has a reader; unknown env keys with the app prefix fail at startup in production. |
| Remediation | (1) Declare or delete the 23 undeclared names. (2) Delete the 27 unread fields. (3) Group into nested models (`FirstPersonSettings`, `LLMSettings`, `CacheSettings`...). (4) Define 3 supported profiles (local, staging, production) and test only those. |
| Acceptance criteria | AST check in CI: 0 undeclared `getattr(settings, ...)`, 0 unread fields. |
| Implementation risk | Low-medium. |
| Verification | [V-STATIC] |

### CQ-011 — `asyncio.run` inside Celery tasks
Evidence: `tasks/memory_outbox_tasks.py:264`, `tasks/layered_memory_tasks.py:44`, `tasks/web_ingest_tasks.py:36,71`, `tasks/okf_extract_tasks.py:69`, `tasks/ingest_tasks.py` base class [V-STATIC]. The serve path already learned that per-call loops break shared async clients ("Event loop is closed", `first_person_pipeline.py:1422-1426`). Severity P3, Probable defect. Remediation: one worker-level event loop per Celery process, or sync clients in tasks. Acceptance: task tests that run two consecutive tasks in one worker process sharing a Redis client.

### CQ-012 — Twenty-one `first_person_*` service modules plus the bridge
Evidence: `services/first_person_{context_harness,context_selector,context_store,evidence_policy,facet_planner,graph_expansion,ingest_service,local_review,pipeline,public_projection,release,rights,safety_policy,serving_contract,set_selector,store,video_decisions,video_review}.py` and others [V-STATIC]. Many are flag-gated off by default (harness, selector, facet split, graph expansion). Severity P2, Architectural risk. Remediation: after CQ-001, group into a package `services/first_person/` with sub-modules `retrieve`, `gates`, `harness`, `serve`, `governance`; delete experiments that lose the graded comparison.

### CQ-013 — Sync dependency in a FastAPI `Depends`
`_get_container_safely` (sync) is used in 3 `Depends(...)` in `app/api/compliance.py` [V-STATIC]. This violates the repo's own L-DOCKER-18 invariant (CLAUDE.md). Severity P3, Confirmed defect. Fix: make it `async def`. Test: extend the existing AST guard to scan all routers.

### CQ-014 — Misleading names
`container.ollama` is the OpenRouter provider (`container.py:191`); FP HyDE calls `getattr(container, "ollama")` (`first_person_bridge.py:823`). Severity P3. Rename with a deprecation alias.

## 5. Register C — code that should remain

| Component | Why keep | Label |
|---|---|---|
| Stage chain (`app/pipeline/stages/*`, `StageRunner`, `PipelineContext`) | Clear ordering, safety-first, unit-testable stages | [V-STATIC] |
| Registry router (`rag/pipeline_registry.py`) | Static topology, live kill-switch, small | [V-STATIC] |
| Static abstain path (`first_person_bridge._abstain`) | Honest, no LLM, localised copy | [V-STATIC] |
| Admission control with crisis never-shed pool (`chat.py:278-325`) | Correct priority semantics | [V-STATIC] |
| Anon HMAC sessions + quota port/adapters | Sound design; Redis is the only multi-replica-safe adapter | [V-STATIC] |
| Auth service: AAL2 for admin, `user_roles` check, service-role tokens not superuser over HTTP (`auth_service.py:454-470`) | Correct least-privilege | [V-STATIC] |
| OpenRouter budget reservation guard (`app/openrouter_budget.py`) | Atomic Lua reservation, refunds, bounded fallback | [V-STATIC] — needs default ON (SYS-004) |
| Production validators in `Settings` (`config.py:2347-2620`) | Fail-closed startup for missing secrets | [V-STATIC] |
| Prometheus metrics (87) and alert rules (14) | Good base; add outcome metrics (doc 15) | [V-STATIC] |
| `lesson_guards.py`, gitleaks, tracked-env-file test | Turn rules into checks | [V-STATIC] |
| Account deletion edge function (fails closed if backend purge fails) | Correct DPDP direction | [V-STATIC] |
| Supabase RLS on all 83 created tables | Correct default | [V-STATIC]; live state [LIVE-R] |

## 6. New components genuinely needed

| Component | Why | Size |
|---|---|---|
| One LLM gateway (interface + OpenRouter impl + policy) | CQ-002, cost and timeout control | M |
| Async FP pipeline with step objects | CQ-001, SYS-003 | L |
| Route decision component with labelled eval | SYS-002 | M |
| Fixture-store CI job (Qdrant + Redis containers) | CQ-008 | M |
| Outcome telemetry ("served and useful") | doc 15 §7 | M |
| Config profiles + config lint | CQ-010 | S |
| Import-layer contracts (`import-linter`) | CQ-007 | S |

## 7. Coverage

Measured with scripts: all runtime Python (AST), all `Settings`, all routes, all tests (counts only). Read: the files cited above, in parts. Not read: `ingest/*` bodies (S2), `rag/nodes/*` bodies (S3), frontend (S4), `benchmarks/`, `colab/`, `scripts/` beyond the cited lines.
