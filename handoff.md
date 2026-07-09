# Session Handoff — Jul 9, 2026

## 1. Goal

Execute the **Ruthless Review** (RUTHLESS_REVIEW.md) — a self-audited plan to cut latency, remove dead code, fix safety bugs, and reduce surface area across the Mukthi Guru RAG pipeline. The review identifies **P0 (9 items)**, **P1 (5 items)**, and **P2 (3 items)** fixes, plus Part E recommendations.

**P0-P1 target**: Remove ~73 lines of dead/phantom code, fix 3 safety bugs (cache poisoning, guardrail ordering, unauthenticated endpoint), cut ~8s from P95 tier3 latency, and eliminate fabricated metrics — while passing 720+ tests.

**End game**: P0-P1 merged to `main`, branch deleted. P2 items (structural deletions, compose split) deferred.

---

## 2. Current State of Code

### Branch: `main`
All P0 (1-9) and P1 (10-14) items are merged plus stash work:

| Commit | What |
|---|---|
| `614737f2` | Stash apply — KG edge rendering (Neo4j rels), RAPTOR header filter, responsive MemoryManager |
| `bbd5caac` | Merge: ruthless P0-P1 review fixes into main |
| `bd232069` | Lessons for P0-P1 patterns |
| `8205d917` | P0-6 through P1-14 — stage order, auth, keyword removal, coalescer, compression, metrics |
| `6e870e35` | P0-5: validate MessagePayload.role to user/assistant |
| `4fd358c4` | P0-4: remove alphabetical sort before budget truncation |
| `602f39e9` | P0-3: reuse shared embedder in _okf_match |
| `9f851806` | P0-2: guardrail ordering (self_harm first), trim over-broad patterns |
| `2253b3b9` | P0-1: delete system-prompt cache |
| `a97f5ae4` | Base: benchmark + auto-flush caches |

### Test Suite
- **720 passed, 5 skipped, 1 warning** — clean (0 pre-existing failures carried forward)
- No integration tests for the cross-stage bugs (Part D item 14 deferred)

### Running Services
- Backend: `http://localhost:8000` (healthy)
- Frontend: `http://localhost:80` (Nginx proxy)
- All infra: Neo4j, Qdrant, Redis, Jaeger, Prometheus, Grafana

---

## 3. Files Actively Edited

### Production
- `backend/rag/nodes/generation.py` — removed keyword footers, factual-slot rewrites, follow-up-suggestions LLM call; added RAPTOR header regex in `_clean_inline_citations`
- `backend/app/api/chat.py` — added auth dep to `POST /api/chat/title`
- `backend/app/pipeline/stages/pipeline_builder.py` — swapped MemoryStage after OutputGuardrailStage
- `backend/app/pipeline/pipeline_coordinator.py` — removed hardcoded 1.0 metrics; uses `container.coalescer`
- `backend/app/pipeline/stages/cache_stage.py` — defensive `isinstance(final_answer, str)` guard
- `backend/app/pipeline/stages/glue_stages.py` — `.get()` defaults in ResultAssemblyStage
- `backend/app/dependencies.py` — added `self.coalescer` to ServiceContainer
- `backend/app/config.py` — `rag_context_compression_enabled=False` default
- `backend/services/memory_service_v2.py` — Neo4j ontology edge query + rendering in KG builder

### Frontend
- `src/components/profile/MemoryManager.tsx` — dynamic width via ResizeObserver, fullscreen Escape key, responsive layout (422-line diff from stash)

### Config/Infra
- `backend/docker-compose.yml` — removed `IS_PRODUCTION=false` / `ENABLE_TEST_AUTH=true` backdoor
- `.gitignore` — added `backend/data/` to prevent user data tracking
- `backend/data/feedback.jsonl` — deleted from git tracking
- `backend/data/lightrag/kv_store_llm_response_cache.json` — deleted from git tracking

### New Files
- `RUTHLESS_REVIEW.md` — the master review document (129 lines)
- `backend/tests/test_test_auth_strategy.py` — auth strategy test
- `backend/tests/test_chat_request_filter.py`, `test_generation_cache.py`, `test_generation_doc_order.py`, `test_guardrail_self_harm_priority.py`, `test_retrieval_okf_embedder.py` — ruthless review P0 tests

### Documentation
- `AGENTS.md` — updated with ruthless review execution context
- `lessons.md` — 7 new lessons (stage ordering, auth, keyword footers, coalescer mocks, compression, spec removal, etc.)

---

## 4. Everything We Tried and Failed

### Fixed (with what worked)
1. **P0-1 cache poisoning** — deleted `llm_cache` block from generation.py → test count unchanged
2. **P0-2 guardrail ordering** — moved self_harm above medication/lithium regex → test_count 680→696
3. **P0-3 embedder reuse** — one-line change `OKFMatch.use_db_service` → 696→701
4. **P0-4 sort order** — `from rag.nodes.retrieval import sort_documents_by_position` removed → 701→703
5. **P0-5 role validation** — Pydantic validator on `MessagePayload.role` → 703→709
6. **P0-6 compose backdoor** — removed env vars from docker-compose.yml
7. **P0-7 user data** — git rm + gitignore for `backend/data/`
8. **P0-8 stage order** — swapped lines in pipeline_builder.py + test assertion
9. **P0-9 auth** — added `user: dict = Depends(get_current_user_from_supabase)` to title endpoint
10. **P1-10 keyword footers** — removed 2 function calls from generation.py → test updated
11. **P1-11 follow-up suggestions** — replaced LLM block with `[]` → test updated
12. **P1-12 coalescer consolidation** — added to ServiceContainer, tests use `_InMemoryCoalescer`
13. **P1-13 compression default** — `True→False` in config.py
14. **P1-14 hardcoded metrics** — removed 3 lines from pipeline_coordinator.py

### Failed attempts (and why)
1. **`MagicMock(spec=ServiceContainer)` in tests** — spec prevents setting `coalescer` attribute. Fixed: removed `spec=` from test mocks.
2. **Bare `AsyncMock()` as coalescer** — `.get_or_run` didn't invoke the coroutine, returned coroutine object → CacheUpdateStage failed. Fixed: use real `_InMemoryCoalescer`.
3. **Rebase onto remote `ruthless-review-p0-p1`** — history had diverged (different P0-2 amend on remote). Fixed: force-push local branch, then merge to main.
4. **Stash `stash@{1}` prompts.py deletion** — `prompts.py` already replaced by `prompts/` package (the directory exists). The stash deletion was a no-op. Dropped the stash.

---

## 5. Next Steps (What I Would Do)

### Immediate (P2 — next session)
1. **Delete Deep strategy** (alias to Standard per review) — `graph_strategies.py`
2. **Remove 6 dead graph nodes** — 0 `add_node` refs: `check_contradiction`, `explain_retrieval`, `check_context_sufficiency`, `retrieve_single`, `merge_sub_results`, `route_sub_queries`
3. **Delete dead code** — unreachable `return "standard"` in `orchestrator_utils.py:254`, duplicate `_prepare_user_memory` in `chat.py:67`
4. **Remove httpx monkey-patch** from `config.py:668` — move rotation into provider client
5. **Collapse providers** (7 → 1–2 active) or feature-flag the unused ones
6. **Remove `backend/repos/`** (624 MB vendored third-party) from working tree; pin via `requirements.txt`

### Medium-term (Part E recommendations)
7. **Upgrade reranker to `BAAI/bge-reranker-v2-m3`** — multilingual, `FlagEmbedding` already a dep
8. **Replace regex guardrails with Llama Guard 3 1B** — eliminates ordering bugs
9. **Add `promptfoo` for adversarial testing** — would have caught P0-2
10. **Add `DeepEval` for CI metric gates** — fail build on faithfulness regression
11. **Unify two-stage cache key** — in-graph semantic re-check (retrieval.py:747) vs pipeline cache use different key shapes

### Technical debt to track
- `_ensure_keywords_in_answer` and `_generate_follow_up_suggestions` **function definitions** remain in `generation.py` — only call sites removed. Delete the dead functions.
- Three integration tests from P1-14 still unwritten (prompt-cache isolation, self-harm+medication → helplines, coalescer follower)
- RUTHLESS_REVIEW.md should be reconciled with the 4 overlapping audit docs (`ARCHITECTURE_AUDIT.md`, `ARCHITECTURE_AUDIT_CORRECTED.md`, `HARDCODING_AUDIT.md`, `RUTHLESS_AUDIT_REPORT.md`)
