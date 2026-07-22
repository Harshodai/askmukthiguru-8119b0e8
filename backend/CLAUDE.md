# CLAUDE.md — backend/

Folder-level guidance for the FastAPI backend. The root `CLAUDE.md` documents the full RAG graph node-by-node; this file covers what you need while editing backend code. Python 3.12 (`.python-version`), venv at `backend/.venv/`.

## Commands (run from backend/)

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload   # run API (needs infra below)
docker compose up -d qdrant redis neo4j jaeger              # infra only; Ollama runs on the host
docker compose up -d --build                                # full stack incl. backend

.venv/bin/pytest                          # all tests
.venv/bin/pytest tests/test_nodes.py      # one file
.venv/bin/pytest tests/test_nodes.py -k name_fragment      # one test
```

Benchmarks: `benchmarks/RUN_ME.sh` (needs the live Docker stack; normally run by the user, not automated). Individual scripts: `python3 benchmarks/ruthless_benchmark.py --endpoint http://localhost:8000`.

## Request flow (chat)

`POST /api/chat` → `app/orchestrator.py` (sync) or `app/stream_orchestrator.py` (SSE) → `app/pipeline/pipeline_coordinator.py:PipelineCoordinator.execute()` → `StageRunner` runs the ordered stage chain from `app/pipeline/stages/pipeline_builder.py`:

```
CacheCheck → CircuitBreaker → RequestState → InputGuardrail → DoctrineCache
→ CasualShortCircuit → Distress → Graph → MeditationGen → Translation
→ Memory → OutputGuardrail → CacheUpdate → ResultAssembly
```

- Stages are pure functions over a `PipelineContext` (`app/pipeline/stages/context.py`), unit-testable in isolation; they reach services via `ctx.container` and coordinator helpers via `ctx.coordinator`.
- `GraphStage` executes the LangGraph: `rag/graph.py` is a thin facade over `rag/graph_strategies.py` (Fast/Standard/Deep); nodes live in `rag/nodes/`. The node data contract is the `GraphState` TypedDict in `rag/states.py` (carries `request_id` for log correlation).

## Hard rules

- `app/dependencies.py` is the composition root (`ServiceContainer`). Get services via `get_container()`; never instantiate services in route handlers or nodes.
- Config only via `from app.config import settings` (pydantic-settings, loaded from `backend/.env`). Never read env vars directly.
- `LLM_PROVIDER` selects the LLM backend: `sarvam_cloud` (default, `SARVAM_API_KEY`), `ollama` (`OLLAMA_BASE_URL`), `openrouter` (`OPENROUTER_API_KEY`). Caching adapters live in `services/cache/` (redis/semantic/memory/hot-cache behind `factory.py`).
- Inference must stay local/free-tier and dependencies open source; keep the anti-hallucination guarantees (guardrails, distress detection, verification thresholds, doctrinal keyword injection) intact when refactoring.

## OKF knowledge layer

`memory/okf/` is a [Google Open Knowledge Format v0.1](https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md) **doctrine bundle** — the gurus' teachings and nothing else. Every entry is embedded and injected verbatim into answers, so anything you put here is quoted to a seeker as doctrine.

`OKFStore.list_entries()` is the single load-time gate (used by the compiler and the admin API). It enforces three invariants, all covered by `tests/test_okf_doctrine_only.py`:
1. `type` ∈ `DOCTRINE_TYPES` (`teaching|practice|glossary|qa|reflection`) — a `runbook` never reaches the answer path. Engineering notes go in `docs/engineering-notes/`.
2. non-empty `source` — an uncitable entry cannot be attributed by `format_final_answer`.
3. no extraction artifacts — `OKFQualityFilter` rejects RAPTOR headers, `_(Source: unknown)_`, and the extraction LLM's prompt commentary.

`compiler.py` embeds `title + description` (OKF-recommended field), not the bare title.

`memory/okf/` lives at the **repo root**, not under `backend/`. Import `OKF_DIR` / `STAGING_DIR` from `services/memory/okf_store.py` — never re-derive the path. Inside the image `backend/` *is* `/app`, so `Path(__file__).parents[3]` and `_BACKEND.parent` both resolve to `/`; that is how `compiler.py` and the extractor each ended up writing to `/memory/okf/` while retrieval read `/app/memory/okf/`.

`OKFStore.list_entries()` uses `rglob` — the teacher-subdir layout (`sri-preethaji/`, `sri-krishnaji/`, `shared/`) requires recursion — and keeps `staging/` and `_scripts/` out with an explicit `_excluded_parts` filter (`okf_store.py`). The **filter, not glob depth, is the review gate**: `staging/` holds unreviewed, LLM-generated doctrine that `extract_okf(auto_approve=False)` writes after every ingested video, and it must never reach `compiled.json`. Never remove that filter; and never revert to a non-recursive `glob` (it would silently drop every teacher-subdir teaching). See `tests/test_okf_pipeline_integrity.py`.

One extractor only: `backend/scripts/extract_okf_from_stores.py` (imported by `ingest/pipeline.py:244`, `tasks/okf_extract_tasks.py:43`, `app/api/admin.py:699`). Its LLM chain must keep all three fallbacks — multi-provider → OpenRouter → Ollama — or extraction raises under `LLM_PROVIDER=ollama`.

After changing OKF entries, recompile **and restart** the backend: `_OKF_CACHE` in `rag/nodes/retrieval.py` is a per-process cache.

## Conventions

- New Python modules end with a runnable `if __name__ == "__main__":` self-check block.
- Degrade gracefully when an optional dependency is missing on the host (skip, don't crash).
- Timeouts always carry safety margins (see `rag/timeout_utils.py`); benchmark-tuned values come from `.env.optimized`.

## Ops scripts

- `scripts/ops/hallucination_anomaly.py` — daily CI/cron check for hallucination rate spike and faithfulness p50 drop. Reads from Supabase `chat_responses` table; exits non-zero on anomaly. Thresholds are env-driven via `ANOMALY_HALLUCINATION_RATE_THRESHOLD`, `ANOMALY_FAITHFULNESS_P50_THRESHOLD`, `ANOMALY_LOOKBACK_DAYS` (defaults in `app.config`).
