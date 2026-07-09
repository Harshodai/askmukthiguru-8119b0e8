# Session Handoff — Jul 9, 2026

## 1. Goal

Execute the **Ruthless Review** (`RUTHLESS_REVIEW.md`) — cut latency, remove dead code, fix safety bugs, reduce surface area. All P0 (9 items), P1 (5 items), and P2 (5 items + tech debt) are done. What remains is deeper structural work and Part E recommendations.

**Overall mission:** Make the Mukthi Guru RAG pipeline lean, correct, and maintainable. The ruthless review is a one-time self-audit; after this, the focus shifts to new features.

---

## 2. Current State of Code

### Branch: `main` — ahead of `origin/main` by 2 commits, working tree clean

**P0-P1 (previous session):** 14 fixes.

**P2 (through this session):** 9 items + tech debt:

| Item | Lines | Files |
|------|-------|-------|
| DeepStrategy → alias to StandardStrategy | −128 | `graph_strategies.py` |
| 6 dead graph nodes | −450 | 7 backend + 3 test files |
| Dead code after `return "standard"` | −44 | `orchestrator_utils.py` |
| Duplicate `_prepare_user_memory` | −64 | `chat.py` |
| httpx monkey-patch | −121 | `config.py` |
| Dead generation functions | −223 | `generation.py` |
| Stale audit docs | 4 files | root `ARCHITECTURE_AUDIT*`, `HARDCODING*`, `RUTHLESS_AUDIT*` |
| **Remove `backend/repos/` (624 MB)** | −1 tracked | `backend/repos/RAG-Anything` |
| **Collapse providers (7 → 2)** | −226 | `OllamaProvider`, `OpenRouterProvider`, factory, registry, tests |
| **Key rotation in SarvamHTTPGateway** | +43 | comma-separated keys, 429 rotation |

**Total:** ~2,522 lines removed, 56 added across 29 files.

### Test Suite
- **715 passed, 5 skipped (infra), 1 warning (pre-existing)** — 0 failures
- Tests adapted for collapsed provider set (factory listing, token budget, OpenRouter)
- 715 vs previous 717 = 3 tests removed for dead nodes + OllamaProvider/OpenRouterProvider provider tests; net -2 tests (some added for new provider test coverage) — wait, let me recalculate: previous was 717 passed (commit 32b1f071), today we have 715 passed. The difference: -2 tests from test_token_budget_guard (OpenRouter) and test_openrouter (OpenRouterProvider) were removed. That accounts for the delta.

### Running Services
- Backend: `http://localhost:8000`
- Frontend: `http://localhost:80` (Nginx)
- All infra: Neo4j, Qdrant, Redis, Jaeger, Prometheus, Grafana

### Git Log (recent)
```
8c706cdf P2 ruthless review: collapse providers + key rotation
257cb6ba P2 ruthless review: remove backend/repos/ (624 MB vendored third-party)
32b1f071 P2 ruthless review: structural cleanup
a55ae167 docs: session handoff for Jul 9 ruthless P0-P1
```

---

## 3. Files Actively Edited (this session)

All changes committed to `main`. New additions since previous handoff marked **NEW**.

### Backend — production (NEW this session)
| File | What changed |
|------|-------------|
| `backend/services/gateways/sarvam_http.py` | **NEW**: API key rotation — parses comma-separated `SARVAM_API_KEY`, rotates on 429 with immediate retry |
| `backend/services/llm/__init__.py` | **NEW**: Removed `OllamaProvider`, `OpenRouterProvider` exports |
| `backend/services/llm/factory.py` | **NEW**: Removed `OllamaProvider`, `OpenRouterProvider` from `LLMProviderFactory` |
| `backend/services/llm/ollama_provider.py` | **NEW**: Deleted (71 lines, dead wrapper) |
| `backend/services/llm/openrouter_provider.py` | **NEW**: Deleted (71 lines, dead wrapper) |
| `backend/services/llm_factory.py` | **NEW**: Removed ollama, openrouter from `_register_default_providers()` |
| `backend/app/dependencies.py` | **NEW**: Removed `OllamaProvider` isinstance checks; simplified to always use `SarvamFailoverService` + `_NoopTranslationProvider` when Sarvam not available |

### Backend — tests (NEW this session)
| File | What changed |
|------|-------------|
| `backend/tests/test_abstractions.py` | **NEW**: Updated `test_provider_listing` to check for `sarvam_cloud` and `nim` |
| `backend/tests/test_token_budget_guard.py` | **NEW**: Removed `OllamaProvider`/`OpenRouterProvider` imports and test cases |
| `backend/tests/test_openrouter.py` | **NEW**: Removed `OpenRouterProvider` import and `test_openrouter_provider_delegation` test |

### Backend — production (from previous session)
| File | What changed |
|------|-------------|
| `backend/rag/graph_strategies.py` | DeepGraphStrategy.build() → delegates to StandardStrategy.build(). |
| `backend/rag/nodes/verification.py` | Deleted `check_contradiction` and `explain_retrieval` |
| `backend/rag/nodes/reranking.py` | Deleted `check_context_sufficiency` |
| `backend/rag/nodes/retrieval.py` | Deleted `route_sub_queries`, `retrieve_single`, `merge_sub_results` |
| `backend/rag/nodes/__init__.py` | Removed imports for 6 dead nodes |
| `backend/rag/timeout_utils.py` | Removed dead node timeout entries |
| `backend/rag/node_llm_config.py` | Removed dead node config entries |
| `backend/rag/nodes/generation.py` | Deleted `_ensure_keywords_in_answer` and `_generate_follow_up_suggestions` |
| `backend/app/orchestrator_utils.py` | Deleted unreachable code block (44 lines) |
| `backend/app/api/chat.py` | Deleted duplicate `_prepare_user_memory` |
| `backend/app/config.py` | Removed `_init_api_key_rotator` monkey-patch |

---

## 4. Everything We Tried and Failed

### P0-P1 — Fixed (14 items)
| # | Bug | Fix | Effect |
|---|-----|-----|--------|
| 1 | System-prompt cache poisoning | Deleted `llm_cache` block from `generation.py` | Test count unchanged |
| 2 | Guardrail ordering (self_harm after medication) | Moved self_harm above medication/lithium regex | 680→696 |
| 3 | `_okf_match` builds fresh embedder per query | One-line: `OKFMatch.use_db_service` | 696→701 |
| 4 | Alphabetical doc sort before budget truncation | Removed `sort_documents_by_position` import | 701→703 |
| 5 | Client `system` messages bypass guardrails | Pydantic validator on `MessagePayload.role` | 703→709 |
| 6 | Compose ships auth backdoor | Removed env vars from docker-compose.yml | — |
| 7 | User data git-tracked | `git rm` + `.gitignore` for `backend/data/` | — |
| 8 | MemoryStage runs before OutputGuardrail | Swapped lines in pipeline_builder.py | — |
| 9 | `/api/chat/title` unauthenticated | Added `get_current_user_from_supabase` dep | — |
| 10 | Keyword footers (wasted LLM call) | Removed 2 function calls from generation.py | — |
| 11 | Follow-up suggestions (extra LLM call per turn) | Replaced LLM block with `[]` | — |
| 12 | Multiple coalescer instances | Added to ServiceContainer, tests use `_InMemoryCoalescer` | — |
| 13 | Context compression on by default | `True→False` in config.py | — |
| 14 | Hardcoded 1.0 metrics | Removed 3 lines from pipeline_coordinator.py | — |

### P2 — Fixed (5 items + tech debt)
| # | Item | Approach | Lines removed |
|---|------|----------|--------------|
| 1 | DeepStrategy is byte-identical to StandardStrategy | Replace 138-line class body with 3-line delegation to `StandardStrategy.build()` | −128 |
| 2 | 6 dead graph nodes with zero `add_node` refs | Delete function definitions + imports + config + tests | −450 |
| 3 | Unreachable code after `return "standard"` | Delete lines 256-300 in orchestrator_utils.py | −44 |
| 4 | Duplicate `_prepare_user_memory` | Delete lines 67-131 in chat.py (zero call sites) | −64 |
| 5 | httpx global monkey-patch | Delete `_init_api_key_rotator` function + module-level call | −121 |
| T1 | Dead generation function definitions | Delete `_ensure_keywords_in_answer` and `_generate_follow_up_suggestions` | −223 |
| T2 | 4 stale audit docs | Delete; keep `RUTHLESS_REVIEW.md` as canonical | −4 files |

### Failed attempts (all sessions)
1. **`MagicMock(spec=ServiceContainer)` in tests** — spec prevents setting `coalescer`. Removed `spec=` from mocks.
2. **Bare `AsyncMock()` as coalescer** — `.get_or_run` returns coroutine object instead of result. Used real `_InMemoryCoalescer` instead.
3. **Rebase onto remote `ruthless-review-p0-p1`** — history diverged (different P0-2 amend on remote). Force-pushed local branch, then merged to main.
4. **Stash `stash@{1}` prompts.py deletion** — `prompts.py` already replaced by `prompts/` package. Stash was a no-op. Dropped it.
5. **`--timeout=120` flag in pytest** — `pytest-timeout` plugin not installed in venv. Dropped the flag; tests complete in ~18s without it.

---

## 5. Next Steps

### ✅ Completed (this session)
1. **Remove `backend/repos/`** (624 MB vendored) — `git rm -r --cached`, already in `.gitignore`.
2. **Collapse providers (7 → 2)** — Sarvam + NIM only. Deleted `OllamaProvider`, `OpenRouterProvider` wrappers. Simplified factory/registry/dependencies.
3. **API key rotation** — in `SarvamHTTPGateway`: comma-separated keys, rotates on 429 with immediate retry (same self-healing pattern as 400 tier limit).

### Up next (choose your priority)

1. **Split compose into `serve`/`ops` profiles** — `serve` profile: backend + qdrant + redis (~4 GB). `ops` profile: neo4j + jaeger + prometheus + grafana (+8 GB). Users doing simple chat don't need the ops stack.

2. **Upgrade reranker** — `BAAI/bge-reranker-v2-m3` is multilingual and `FlagEmbedding` is already a dependency. Config + model swap, no new deps.

3. **Replace regex guardrails with Llama Guard 3 1B** — eliminates the ordering bug class (P0-2). Keep a thin regex for the spiritual allow-list.

### Technical debt
- 3 integration tests unwritten (prompt-cache isolation, self-harm+medication→helplines, coalescer follower). Requires live infra (Neo4j, Redis, Qdrant).
- Unify two-stage cache key — in-graph semantic re-check (`retrieval.py:747`) vs pipeline cache (`cache_stage.py`) use different key shapes, so they never hit. Unify or delete the in-graph one.
