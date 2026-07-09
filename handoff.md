# Session Handoff — Jul 9, 2026

## 1. Goal

Execute the **Ruthless Review** (`RUTHLESS_REVIEW.md`) — cut latency, remove dead code, fix safety bugs, reduce surface area. All P0 (9 items), P1 (5 items), and P2 (5 items + tech debt) are done. What remains is deeper structural work and Part E recommendations.

**Overall mission:** Make the Mukthi Guru RAG pipeline lean, correct, and maintainable. The ruthless review is a one-time self-audit; after this, the focus shifts to new features.

---

## 2. Current State of Code

### Branch: `main` — up to date with `origin/main`, working tree clean

**P0-P1 (previous session):** 14 fixes — cache poisoning, guardrail ordering, embedder reuse, sort order, role validation, compose backdoor, user data tracking, stage ordering, auth on title endpoint, keyword footers, follow-up suggestions, coalescer consolidation, compression default, hardcoded metrics.

**P2 (this session):** 5 structural deletions + tech debt:

| Item | Lines removed | Files |
|------|--------------|-------|
| DeepStrategy → alias to StandardStrategy | −128 | `graph_strategies.py` |
| 6 dead graph nodes | −450 | `verification.py`, `reranking.py`, `retrieval.py`, `__init__.py`, `timeout_utils.py`, `node_llm_config.py`, `validate_graph.py` + 3 test files |
| Dead code after `return "standard"` | −44 | `orchestrator_utils.py` |
| Duplicate `_prepare_user_memory` | −64 | `chat.py` |
| httpx monkey-patch | −121 | `config.py` |
| Dead generation functions | −223 | `generation.py` |
| Stale audit docs | 4 files | `ARCHITECTURE_AUDIT.md`, `ARCHITECTURE_AUDIT_CORRECTED.md`, `HARDCODING_AUDIT.md`, `RUTHLESS_AUDIT_REPORT.md` |

**Total:** 2,252 net lines removed across 19 files. 13 lines added.

### Test Suite
- **717 passed, 5 skipped (infra), 1 warning (pre-existing)** — 0 failures
- 3 tests removed alongside the dead nodes they tested (expected)
- No regressions from any structural deletion

### Running Services
- Backend: `http://localhost:8000`
- Frontend: `http://localhost:80` (Nginx)
- All infra: Neo4j, Qdrant, Redis, Jaeger, Prometheus, Grafana

### Git Log (recent)
```
32b1f071 P2 ruthless review: structural cleanup
a55ae167 docs: session handoff for Jul 9 ruthless P0-P1
614737f2 chore: apply pre-ruthless WIP stash — KG edge rendering, RAPTOR ...
bbd5caac merge: ruthless P0-P1 review fixes into main
bd232069 docs: add ruthless P0-P1 lessons to lessons.md
8205d917 ruthless P0-6 through P1-14: stage order, auth, keyword removal, ...
6e870e35 fix(schemas): drop client system messages; validate role (P0-5)
4fd358c4 fix(rag): remove alphabetical doc sort before budget truncation (P0-4)
602f39e9 fix(rag): reuse shared embedder in _okf_match (P0-3)
9f851806 fix(guardrails): self_harm before medical hard-block (P0-2)
2253b3b9 fix(rag): delete cross-contaminating system-prompt cache (P0-1)
a97f5ae4 feat(benchmark): auto-flush Redis + Qdrant caches before every run
```

---

## 3. Files Actively Edited (this session)

All changes committed to `main`. These are the files to know about for the next session:

### Backend — production
| File | What changed |
|------|-------------|
| `backend/rag/graph_strategies.py` | DeepGraphStrategy.build() → delegates to StandardStrategy.build(). ~128 lines removed. |
| `backend/rag/nodes/verification.py` | Deleted `check_contradiction` and `explain_retrieval` functions |
| `backend/rag/nodes/reranking.py` | Deleted `check_context_sufficiency` function |
| `backend/rag/nodes/retrieval.py` | Deleted `route_sub_queries`, `retrieve_single`, `merge_sub_results` functions |
| `backend/rag/nodes/__init__.py` | Removed imports and `__all__` entries for all 6 dead nodes |
| `backend/rag/timeout_utils.py` | Removed dead node timeout entries; removed `explain_retrieval` from scale-up condition |
| `backend/rag/node_llm_config.py` | Removed dead node config entries |
| `backend/rag/nodes/generation.py` | Deleted `_ensure_keywords_in_answer` (136 lines) and `_generate_follow_up_suggestions` (81 lines) |
| `backend/app/orchestrator_utils.py` | Deleted unreachable code block after `return "standard"` (44 lines) |
| `backend/app/api/chat.py` | Deleted duplicate `_prepare_user_memory` function (64 lines, zero call sites) |
| `backend/app/config.py` | Removed `_init_api_key_rotator` monkey-patch (121 lines) |

### Backend — tests/benchmarks
| File | What changed |
|------|-------------|
| `backend/tests/test_tiered_routing_streaming.py` | Removed dead node tests (`check_context_sufficiency`, `check_contradiction`, `explain_retrieval`) |
| `backend/tests/test_nodes.py` | Removed `test_explain_retrieval_node` |
| `backend/tests/test_crag_confidence_skip.py` | Removed `test_sufficiency_skipped_when_rerank_confident` |
| `backend/benchmarks/validate_graph.py` | Removed dead nodes from exclusion set |

### Root — docs
| File | What changed |
|------|-------------|
| `ARCHITECTURE_AUDIT.md` | Deleted |
| `ARCHITECTURE_AUDIT_CORRECTED.md` | Deleted |
| `HARDCODING_AUDIT.md` | Deleted |
| `RUTHLESS_AUDIT_REPORT.md` | Deleted |
| `RUTHLESS_REVIEW.md` | **Kept** — this is the canonical audit document |

### Documentation
| File | What changed |
|------|-------------|
| `lessons.md` | Added 5 P2 lessons (dead node sweep, Deep alias, monkey-patch removal, stale docs, dead function bodies) |
| `handoff.md` | This file |

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

### Immediate (next session)

1. **Move API key rotation into one provider client** — the httpx monkey-patch was deleted (P2-5), but rotation logic needs to live somewhere. Pick the active provider (NIM or Sarvam Cloud), add a client-level key rotator that on 429 swaps to the next comma-separated key. Test with `BENCHMARK_SECRET`.

2. **Collapse providers (7 → 1-2)** — `LLM_PROVIDER` supports nim, sarvam_cloud, openrouter, ollama, krutrim, and 3 more. Delete unused provider classes; make the selection a config toggle with one active + one fallback. Keeps code readable and eliminates dead provider init paths.

3. **Remove `backend/repos/`** (624 MB vendored third-party) — this is a vendored directory checked into git. Use `git rm -r --cached backend/repos/` and add to `.gitignore`. Pin the actual dependencies via `requirements.txt` / `pyproject.toml` instead.

### Medium-term (Part E)

4. **Split compose into `serve`/`ops` profiles** — `serve` profile: backend + qdrant + redis (~4 GB). `ops` profile: neo4j + jaeger + prometheus + grafana (+8 GB). Users doing simple chat don't need the ops stack.

5. **Upgrade reranker** — `BAAI/bge-reranker-v2-m3` is multilingual and `FlagEmbedding` is already a dependency. Config + model swap, no new deps.

6. **Replace regex guardrails with Llama Guard 3 1B** — eliminates the ordering bug class (P0-2). Keep a thin regex for the spiritual allow-list.

### Technical debt
- 3 integration tests unwritten (prompt-cache isolation, self-harm+medication→helplines, coalescer follower). Requires live infra (Neo4j, Redis, Qdrant).
- Unify two-stage cache key — in-graph semantic re-check (`retrieval.py:747`) vs pipeline cache (`cache_stage.py`) use different key shapes, so they never hit. Unify or delete the in-graph one.
