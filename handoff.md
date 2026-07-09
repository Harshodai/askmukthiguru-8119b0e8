# Session Handoff — Jul 9, 2026

## 1. Goal

Execute the **Ruthless Review** (`RUTHLESS_REVIEW.md`) — cut latency, remove dead code, fix safety bugs, reduce surface area. All P0 (9 items), P1 (5 items), P2 (5 items + tech debt) are complete across multiple sessions.

**Overall mission:** Make the Mukthi Guru RAG pipeline lean, correct, and maintainable. After this, focus shifts to new features.

---

## 2. Current State of Code

### Branch: `main` — up to date with `origin/main`, working tree clean

### What was done this session (5 items):

| Item | Files Changed |
|------|-------------|
| Reranker upgrade → `BAAI/bge-reranker-v2-m3` | `config.py`, `docker-compose.yml`, `download_models.py` |
| Docker compose — all services default (no profiles) | `docker-compose.yml` (reverted `profiles: ["ops"]`, restored depends_on) |
| Llama Guard 3 1B handler | `guardrails/llama_guard_handler.py` (new, 195 lines), `chain.py`, `config.py` |
| In-graph cache duplicate check removed | `retrieval.py` (−12 lines) |
| Llama Guard OTEL tracing | `llama_guard_handler.py` (rag_span for input/output) |
| Makefile: model pre-download target | `Makefile` (added `docker-pull-models`) |

**Key decisions:**
- **No docker profiles** — all services start by default. Simple `docker compose up -d --build` for the full stack.
- **Ollama + OpenRouter kept** — provider collapse reverted. All 4 providers registered: sarvam_cloud, nim, ollama, openrouter.
- **Llama Guard model is gated** — requires `huggingface-cli login` with accepted Meta license. Falls back gracefully to lightweight regex if unavailable.
- **Reranker is CrossEncoder API** — `BAAI/bge-reranker-v2-m3` works with `sentence-transformers.CrossEncoder`. FlashRank path is unaffected (uses its own ONNX models).

### Previous sessions (P0-P2 items):
- 14 P0-P1 bug fixes (system-prompt cache, guardrail ordering, auth backdoor, etc.)
- 7 P2 structural items (dead code removal, strategy aliasing, cache cleanup)
- ~2,450 lines removed, ~225 added across 35+ files
- Support for API key rotation (comma-separated, 429 retry)

### Test Suite
- **717 passed, 5 skipped (infra), 1 warning (pre-existing)** — 0 failures
- Full suite completes in ~14s

### Running Services
- Backend: `http://localhost:8000`
- Frontend: `http://localhost:80` (Nginx)
- All infra: Neo4j, Qdrant, Redis, Jaeger, Prometheus, Grafana

### Git Log
```
5e5af72f P2: model pre-download, all-services default, Llama Guard tracing, Makefile update
84fa955a P2 ruthless review: reranker upgrade, compose profiles, Llama Guard, cache cleanup
8c706cdf P2 ruthless review: collapse providers + key rotation
257cb6ba P2 ruthless review: remove backend/repos/ (624 MB vendored third-party)
32b1f071 P2 ruthless review: structural cleanup
a55ae167 docs: session handoff for Jul 9 ruthless P0-P1
```

---

## 3. Files Actively Edited (this session)

### Production code
| File | Change |
|------|--------|
| `backend/app/config.py` | `reranker_model` → `BAAI/bge-reranker-v2-m3`; `guardrails_provider` doc updated |
| `backend/docker-compose.yml` | Reverted profiles; all services default; `RERANKER_MODEL` env var updated |
| `backend/guardrails/llama_guard_handler.py` | **NEW** — `transformers` pipeline wrapping `meta-llama/Llama-Guard-3-1B`, category→topic mapping, graceful gated-model fallback, OTEL tracing spans |
| `backend/guardrails/chain.py` | Added `llama_guard` provider → chain: Lightweight → LlamaGuard → NeMo |
| `backend/rag/nodes/retrieval.py` | Removed in-graph semantic cache check (12 lines) — `CacheCheckStage` is single authority |
| `backend/scripts/download_models.py` | Pre-download `BAAI/bge-reranker-v2-m3` instead of old CrossEncoder |
| `Makefile` | Added `docker-pull-models` target for pre-build model cache |

### How each change works

**Reranker:** Config-only swap. `CrossEncoder('BAAI/bge-reranker-v2-m3')` loads at runtime. Pre-downloaded at Docker build time by `download_models.py`. Both FlashRank (ONNX, fast path) and CrossEncoder (fallback for complex queries) paths unchanged.

**Docker compose:** All 10 services start by default. Neo4j + Jaeger + Prometheus + Grafana run alongside backend, Redis, Qdrant. `docker compose up -d --build` starts everything.

**Llama Guard:** Config-driven via `GUARDRAILS_PROVIDER=llama_guard`. On init, tries to load `meta-llama/Llama-Guard-3-1B` via transformers. If gated/missing, logs a clear message and falls back to `lightweight` (regex). Chain order: Lightweight (length, spiritual allowlist, emotional wellness, harmful patterns) → Llama Guard (safety classification → topic map → block response) → NeMo (if available). OTEL spans: `llama_guard_input` / `llama_guard_output` with `unsafe` and `categories` attributes.

**Cache unification:** The in-graph semantic cache check in `retrieval.py` was a duplicate that used raw query text as key while the pipeline `CacheCheckStage` uses `lang:query` composite keys. Removed the in-graph check — `CacheCheckStage` is the single cache authority.

**Makefile:** `make docker-pull-models` runs `download_models.py` to pre-populate the HuggingFace cache before building Docker images.

---

## 4. Everything We Tried and Failed

### P0-P1 — Fixed (14 items, earlier sessions)
| # | Bug | Fix |
|---|-----|-----|
| 1 | System-prompt cache poisoning | Deleted `llm_cache` block from `generation.py` |
| 2 | Guardrail ordering (self_harm after medication) | Moved self_harm above medication regex |
| 3 | `_okf_match` builds fresh embedder per query | One-line: `OKFMatch.use_db_service` |
| 4 | Alphabetical doc sort before budget truncation | Removed `sort_documents_by_position` import |
| 5 | Client `system` messages bypass guardrails | Pydantic validator on `MessagePayload.role` |
| 6 | Compose ships auth backdoor | Removed env vars from docker-compose.yml |
| 7 | User data git-tracked | `git rm` + `.gitignore` for `backend/data/` |
| 8 | MemoryStage runs before OutputGuardrail | Swapped lines in pipeline_builder.py |
| 9 | `/api/chat/title` unauthenticated | Added `get_current_user_from_supabase` dep |
| 10 | Keyword footers (wasted LLM call) | Removed 2 function calls from generation.py |
| 11 | Follow-up suggestions (extra LLM call per turn) | Replaced LLM block with `[]` |
| 12 | Multiple coalescer instances | Added to ServiceContainer, tests use `_InMemoryCoalescer` |
| 13 | Context compression on by default | `True→False` in config.py |
| 14 | Hardcoded 1.0 metrics | Removed 3 lines from pipeline_coordinator.py |

### P2 — Fixed (earlier sessions)
| # | Item | Lines removed |
|---|------|-------------|
| 1 | DeepStrategy → StandardStrategy alias | −128 |
| 2 | 6 dead graph nodes | −450 |
| 3 | Unreachable code after `return "standard"` | −44 |
| 4 | Duplicate `_prepare_user_memory` | −64 |
| 5 | httpx global monkey-patch | −121 |
| T1 | Dead generation functions | −223 |
| T2 | 4 stale audit docs | −4 files |

### This session
| Item | Status | Detail |
|------|--------|--------|
| Reranker → `BAAI/bge-reranker-v2-m3` | ✅ Done | Config swap + download_models.py |
| Docker compose profiles | ❌ Reverted | User wanted all services up by default. Removed `profiles: ["ops"]`. |
| Llama Guard 3 1B handler | ✅ Done | New handler + chain integration + tracing |
| In-graph cache duplicate removed | ✅ Done | −12 lines in retrieval.py |
| Makefile model pre-download | ✅ Done | `make docker-pull-models` target added |

### Failed attempts (all sessions)
1. **`MagicMock(spec=ServiceContainer)`** — spec prevents setting `coalescer`. Removed `spec=`.
2. **Bare `AsyncMock()` as coalescer** — `.get_or_run` returns coroutine object. Used `_InMemoryCoalescer`.
3. **Rebase onto remote `ruthless-review-p0-p1`** — history diverged. Force-pushed local branch, merged to main.
4. **Stash `stash@{1}` prompts.py deletion** — no-op (already replaced by `prompts/` package). Dropped.
5. **`--timeout=120` in pytest** — `pytest-timeout` not installed. Tests complete in ~14s without it.
6. **Docker compose profiles** — user feedback: "I need all services to be up." Reverted to all-default.

### Known limitations
1. **Llama Guard model is gated** — `meta-llama/Llama-Guard-3-1B` requires HuggingFace login with accepted license. Falls back gracefully to lightweight regex handler. To enable: `huggingface-cli login` + `GUARDRAILS_PROVIDER=llama_guard` in `.env`.
2. **3 integration tests exist as unit tests** — `test_generation_cache.py` (prompt-cache), `test_guardrail_self_harm_priority.py` (self-harm→helplines), `test_coalescer.py` (coalescer concurrency). True end-to-end tests need Docker CI infra.
3. **Reranker model download at build time** — `download_models.py` runs during `docker build`. Adds ~2GB to image. The model cache volume (`hf_model_cache`) prevents re-download on rebuilds.
4. **Key rotation in streaming path not implemented** — HTTP gateway (`SarvamHTTPGateway`) rotates keys on 429. Streaming path (`SarvamCloudService`) does not. Explicitly deferred.

---

## 5. Next Step You Would Take

If continuing, here's the priority order:

### Immediate (if you want to use Llama Guard):
1. **`huggingface-cli login`** — authenticate with a token that has accepted the Meta Llama Guard 3 1B license at hf.co/meta-llama/Llama-Guard-3-1B
2. **Set `GUARDRAILS_PROVIDER=llama_guard`** in your `backend/.env` — after that, all safety classification goes through the transformer model instead of regex
3. **Rebuild Docker** — `make docker-up` picks up the env var

### Before shipping to production:
1. **Verify the reranker works end-to-end** — run `make docker-up`, send a chat query, check logs for `Loading reranker: BAAI/bge-reranker-v2-m3`. The model loads lazily on first reranking, so the first complex query will be slow (~5s load time).
2. **Benchmark TTFT** — `cd backend && .venv/bin/python benchmarks/ruthless_benchmark.py --endpoint http://localhost:8000`. Compare against prior runs to ensure the new reranker didn't regress latency.
3. **Set up CI integration tests** — if you add a CI pipeline with Docker services, write true end-to-end tests through the HTTP chat endpoint to cover cache hit/miss paths and coalescer behavior under load.

### Medium-term:
1. **Key rotation for streaming** — `SarvamCloudService.stream_chat()` in `services/sarvam_cloud.py` handles streaming completions and does not rotate API keys on 429. Add the same comma-separated rotation pattern.
2. **Reranker warm-up in entrypoint** — add `embedder._ensure_reranker()` to the startup sequence or warm_cache.py so the first real query doesn't pay the lazy-load penalty.
3. **Open-weight guardrail model** — if the gated Llama Guard license is a blocker, consider `ProtectAI/distilroberta-base-rejection-classifier` or fine-tune a small BERT classifier on your topic categories. Swap the model name in `llama_guard_handler.py`.
