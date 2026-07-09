# Session Handoff — Jul 9, 2026 (P2 complete)

## 1. Goal

Execute the **Ruthless Review** (RUTHLESS_REVIEW.md) — a self-audited plan to cut latency, remove dead code, fix safety bugs, and reduce surface area across the Mukthi Guru RAG pipeline.

**Phase 1 (P0-P1)**: Removed ~73 lines of dead/phantom code, fixed 3 safety bugs, cut ~8s from P95 tier3 latency, eliminated fabricated metrics.

**Phase 2 (P2)**: Structural cleanup — alias Deep→Standard, remove 6 dead graph nodes + 45 lines unreachable code + duplicate function + httpx monkey-patch + 2 dead generation functions + 4 stale audit docs. **2,252 net lines removed** across 19 files.

---

## 2. Current State of Code

### Branch: `main`
All P0-P2 items are merged:

| Commit | What |
|---|---|
| `614737f2` | Stash apply — KG edge rendering (Neo4j rels), RAPTOR header filter, responsive MemoryManager |
| `bbd5caac` | Merge: ruthless P0-P1 review fixes into main |
| _current_ | P2: Deep alias, 6 dead nodes, httpx monkey-patch, dead code, stale docs |
| `bd232069` | Lessons for P0-P1 patterns |
| `8205d917` | P0-6 through P1-14 — stage order, auth, keyword removal, coalescer, compression, metrics |
| `6e870e35` | P0-5: validate MessagePayload.role to user/assistant |
| `4fd358c4` | P0-4: remove alphabetical sort before budget truncation |
| `602f39e9` | P0-3: reuse shared embedder in _okf_match |
| `9f851806` | P0-2: guardrail ordering (self_harm first), trim over-broad patterns |
| `2253b3b9` | P0-1: delete system-prompt cache |
| `a97f5ae4` | Base: benchmark + auto-flush caches |

### Test Suite
- **717 passed, 5 skipped, 1 warning** — clean (0 pre-existing failures; 3 tests removed alongside deleted dead nodes)

### Running Services
- Backend: `http://localhost:8000` (healthy)
- Frontend: `http://localhost:80` (Nginx proxy)
- All infra: Neo4j, Qdrant, Redis, Jaeger, Prometheus, Grafana

---

## 3. P2 Changes Summary

### Structural deletions
| P2 Item | Files changed | Lines removed |
|---------|---------------|---------------|
| 1. DeepStrategy → alias | `graph_strategies.py` | −128 |
| 2. 6 dead graph nodes | 10 files (definitions, config, tests) | −450 |
| 3. Dead code after `return "standard"` | `orchestrator_utils.py` | −44 |
| 4. Duplicate `_prepare_user_memory` | `chat.py` | −64 |
| 5. httpx monkey-patch | `config.py` | −121 |
| Tech: dead gen functions | `generation.py` | −223 |

### Config/Infra
- Stale audit docs deleted: `ARCHITECTURE_AUDIT.md`, `ARCHITECTURE_AUDIT_CORRECTED.md`, `HARDCODING_AUDIT.md`, `RUTHLESS_AUDIT_REPORT.md`
- Remaining: `RUTHLESS_REVIEW.md` (canonical), `lessons.md`, `handoff.md`

### Dead nodes removed
`check_contradiction`, `explain_retrieval`, `check_context_sufficiency`, `retrieve_single`, `merge_sub_results`, `route_sub_queries` — none wired into any graph strategy (verified: 0 `add_node` refs).

### What was intentionally deferred
- Provider collapse (7→1-2) — bigger architectural decision
- `backend/repos/` removal — needs git filtering
- Compose `serve`/`ops` split — infra refactor
- 3 integration tests for P1-14 — requires live infra

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

## 5. Next Steps (Next Session)

### Structural (deferred from P2)
1. **Collapse providers** (7 → 1–2 active) or feature-flag the unused ones — keep NIM + one cloud fallback, delete the rest
2. **Remove `backend/repos/`** (624 MB vendored third-party) from working tree; pin via `requirements.txt`
3. **Split compose** into `serve`/`ops` profiles — Qdrant+Redis+backend for serving, Neo4j+Jaeger+etc for ops

### Medium-term (Part E recommendations)
4. **Upgrade reranker to `BAAI/bge-reranker-v2-m3`** — multilingual, `FlagEmbedding` already a dep
5. **Replace regex guardrails with Llama Guard 3 1B** — eliminates ordering bugs
6. **Add `promptfoo` for adversarial testing** + **DeepEval** for CI metric gates
7. **Unify two-stage cache key** — in-graph semantic re-check vs pipeline cache use different key shapes

### Technical debt
- 3 integration tests from P1-14 unwritten (prompt-cache isolation, self-harm+medication → helplines, coalescer follower)
- Move API key rotation from deleted monkey-patch into the one active provider client
