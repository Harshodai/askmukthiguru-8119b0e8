## Memory architecture — recommendation with tradeoffs

[Likely] None of the three reference systems map cleanly onto Mukthi Guru. Letta's archival memory is over-engineered for a spiritual chat (no tool-calling agent loop), Mem0 alone loses session continuity, and LangMem's three-store split is bureaucratic for a single-domain app. The right answer is **a deliberate hybrid of all three**, picking the cheapest layer that solves each retrieval need.

### Tradeoff matrix

| System | Strength | Weakness for us | What we steal |
|---|---|---|---|
| **Mem0** | Atomic claim extraction, vector dedup, decay scoring. Cheapest read path. | No session-level abstraction. Forgets "what we discussed last Tuesday". | Atomic memory store + extractor + decay |
| **Letta/MemGPT** | In-context "core block" always present + paged archival. Best for stable user facts. | Archival pager is wasted complexity when token budget is small. | Core block pattern (always-in-prompt) + soft eviction |
| **LangMem** | Clean semantic/episodic/procedural split. Strong for multi-skill agents. | Procedural is meaningless here (one skill: spiritual guidance). | Episodic session summaries only |

### Final architecture: 3-tier hybrid

```text
┌─────────────────────────────────────────────────────────┐
│  CORE BLOCK (Letta-style)                               │
│  always in prompt · ≤200 tokens · 1 row per user        │
│  {name, language, practice_level, dominant_themes[]}    │
└─────────────────────────────────────────────────────────┘
              ▲ rewritten by dreamer nightly
┌─────────────────────────────────────────────────────────┐
│  SEMANTIC MEMORIES (Mem0-style)                         │
│  retrieved per turn · top-K=3 · ≤450 tokens             │
│  atomic claims · BGE-M3 1024d · cosine + recency boost  │
│  decay 0.97/day · dedup at cos>0.92 · soft-delete <0.1  │
└─────────────────────────────────────────────────────────┘
              ▲ written by extractor (background task)
┌─────────────────────────────────────────────────────────┐
│  EPISODIC SUMMARIES (LangMem-style)                     │
│  recent N=2 · ≤180 tokens · 1 row per conversation      │
│  rolling summary · topic tags · sentiment trajectory    │
└─────────────────────────────────────────────────────────┘
              ▲ written on conversation close/idle 30min
```

**Token budget per turn (read path):** ~830 tokens injected as `USER MEMORY` block. Hard-capped; truncation order is episodic → semantic → core.

[Certain] Three-tier is the minimum that handles all of: stable identity, evolving practice, and "remember last week". Dropping any tier creates a known recall failure mode.

---

## Storage decision: self-hosted Postgres + pgvector next to FastAPI

[Certain] Not Lovable Cloud (per your direction), not Qdrant (loses relational queries, RLS-style scoping, transactional writes), not SQLite (HNSW perf cliff >100k rows). Add a `postgres:16` + `pgvector/pgvector:pg16` service to `backend/docker-compose.yml`. Sits alongside qdrant/neo4j/redis. Single source of truth, owned by FastAPI, accessed via `asyncpg`. Frontend never touches it directly — only through Python `/api/memory/*` endpoints (parity with how chat already works).

Embeddings reuse the existing `EmbeddingService` (BGE-M3, 1024d) so memory and corpus share one model. Zero new embedding cost, zero new dependency.

---

## Plan structure: two parallel tracks, no cross-blocking

[Likely] You asked for memory not gated on Phase 1. Doing them parallel is correct *only* if they share zero files. They mostly do, but the conflicts are tractable:

| File | Track A touches | Track B touches | Resolution |
|---|---|---|---|
| `rag/nodes.py` | fixes 1-4 | adds `inject_memory_context` node | B adds new node fn at end; no merge conflict |
| `rag/graph.py` | none | wires memory node | B-only |
| `app/config.py` | adds 5 flags | adds 4 flags | additive; merge clean |
| `app/main.py` | none | background task for write | B-only |
| `services/embedding_service.py` | parity fix | read-only consumer | A-only |

→ Safe to parallelize. One developer (or agent run) per track.

---

## Track A — Retrieval + latency (1-2 days, no flag)

Identical to my prior draft, condensed:

1. **Parity fix** — `encode_single_full` passes raw text; unit test no-double-prefix.
2. **Contract** — fix `query_tier` NameError; `_require_state` helper.
3. **Citations + insights** — emit citations unconditionally; implement `extract_memory_insights` (used by Track B).
4. **Latency** — 20s graph deadline, `NODE_TIMEOUTS` tightened, `llm_max_retries=0` on classifiers.
5. **Classifier swap** — Gemini Flash via Lovable AI Gateway for 6 classifier nodes (Sarvam stays for generation/verification).
6. **Regex pre-router** — bypass LLM for greeting/meditation/distress.
7. **Test fixture fix** — `mock_get_container` includes 3 graph strategies.
8. **Cache flush op** — `make flush-cache` after deploy.

**Exit metrics (informational only — does NOT gate Track B):** doctrine ≥70%, citations ≥60%, p95 ≤8s, faithfulness ≥70%.

---

## Track B — Memory layer (3-4 days, behind toggle)

### B1. Infra (`backend/docker-compose.yml`, new migration)
- Add `postgres:16` service + `pgvector/pgvector:pg16` image. Volume `postgres_data`.
- Alembic migration creates 3 tables, HNSW indexes on embedding columns, role-scoped access (no RLS — single-tenant from FastAPI's view).

```text
guru_core_memory(user_id PK, profile JSONB, updated_at)
guru_memories(id, user_id, claim TEXT, embedding vector(1024),
              source_message_id, confidence FLOAT, last_seen TS,
              decay_score FLOAT, soft_deleted BOOL, created_at)
              INDEX hnsw(embedding vector_cosine_ops) + btree(user_id, soft_deleted)
guru_session_summaries(id, user_id, conversation_id, summary TEXT,
                       topics TEXT[], sentiment_traj JSONB, closed_at)
```

### B2. `services/memory_service.py` (new)
Three readers + three writers + maintenance:
- `get_core(user_id) -> str` (≤200 tokens)
- `search_semantic(user_id, query_vec, k=3) -> list[Memory]` (cosine + 0.3·recency_boost)
- `recent_summaries(user_id, n=2) -> list[str]`
- `extract_and_write(user_id, message_id, turn)` → Gemini Flash extracts ≤3 atomic claims → BGE-M3 embed → dedup → insert
- `update_core(user_id)` (nightly only — rewrites core block from top-30 memories)
- `summarize_session(conversation_id)` (on close/idle)
- `forget(memory_id)`, `add_explicit(user_id, text)`

### B3. Graph wiring (`rag/nodes.py`, `rag/graph.py`)
- New node `inject_memory_context` — runs after `intent_router`, before `decompose_query`. Parallel fan-out to core/semantic/episodic. Result lands in `GraphState.memory_context`.
- New node `memory_relevance_gate` — skips injection for pure doctrine queries (uses intent classification). Saves tokens on the 60% of queries that don't need user context.
- `context_engineer` adds `USER MEMORY` block to prompt with explicit instruction: "Reference these only when relevant to the user's question."
- After `format_final_answer`, FastAPI `BackgroundTask` calls `extract_and_write`.

### B4. Maintenance (`backend/scripts/dream_memories.py`, cron)
- Nightly 03:00 IST.
- Dedup pass (cos>0.95 merge into highest-confidence row).
- Decay (`decay_score *= 0.97`).
- Soft-delete (score<0.1 AND last_seen>90d).
- Core block rewrite from top-30 surviving memories (single Gemini Flash call).
- HNSW reindex if write-volume threshold exceeded.

### B5. API (`backend/app/routers/memory.py` new)
- `GET /api/memory/list` — paginated, user-scoped, excludes soft-deleted.
- `POST /api/memory/forget` — soft-delete by id.
- `POST /api/memory/add` — explicit user-added memory (skips extractor).
- `GET /api/memory/core` — show current core block (transparency).
- All endpoints require Supabase JWT, validated server-side.

### B6. Frontend (`src/lib/memoryApi.ts`, `src/components/MemoryManager.tsx`, `src/lib/personalInsights.ts`)
- Settings tab "Memory" — list, forget, add. Behind `feature_memory_ui`.
- `personalInsights.ts` rewritten to consume `/api/memory/list` + `meditation_sessions` table:
  - "You've practiced 4× this week vs 1× last week" (practice rhythm)
  - "You mentioned anxiety about work 3× — has it shifted?" (memory echo)
  - "You tend to meditate in the evening" (time-of-day)
  - "Your mood scores trended up after Serene Mind on Tuesday" (mood delta)
- Replaces current generic insights entirely.

### B7. Feature flags (`backend/app/config.py`)
```
feature_memory_enabled: bool = False    # master read switch
feature_memory_write: bool = False      # background extractor
feature_memory_ui: bool = False         # frontend tab
memory_token_budget: int = 830          # hard cap
memory_skip_intents: list = ["doctrine_lookup", "casual"]
```

Default OFF. Enable in staging after Track A + B both land. Production rollout: write-only for 7 days (populate store), then read-on for 10% canary, then 100%.

### B8. Exit gate (separate from Track A)
- Personalized-recall benchmark: 20-query suite asking "what did I tell you about X". ≥80% correct.
- p95 latency delta with memory ON vs OFF: ≤200ms.
- Token usage delta: ≤900 tokens/turn average.
- No doctrine accuracy regression from Track A baseline.

---

## Technical notes

**Files — Track A (8)**
Modify: `backend/services/embedding_service.py`, `backend/rag/nodes.py`, `backend/rag/timeout_utils.py`, `backend/rag/graph_strategies.py`, `backend/rag/node_llm_config.py`, `backend/services/llm_factory.py`, `backend/app/config.py`, `backend/tests/test_chat_endpoint.py`
Create: `backend/rag/intent_prerouter.py`, `backend/tests/test_embedding_no_double_prefix.py`, `backend/tests/test_retrieve_documents_contract.py`, `backend/benchmarks/smoke_doctrine.py`

**Files — Track B (12)**
Modify: `backend/docker-compose.yml`, `backend/app/dependencies.py`, `backend/app/main.py`, `backend/app/config.py`, `backend/rag/nodes.py`, `backend/rag/graph.py`, `backend/rag/states.py`, `backend/rag/prompts.py`
Create: `backend/services/memory_service.py`, `backend/app/routers/memory.py`, `backend/scripts/dream_memories.py`, `backend/alembic/versions/XXX_memory_tables.py`, `src/lib/memoryApi.ts`, `src/components/MemoryManager.tsx`, rewrite `src/lib/personalInsights.ts`, `backend/tests/test_memory_service.py`, `backend/tests/test_memory_endpoints.py`, `backend/benchmarks/personalized_recall.py`

**Risks**
1. [Likely] Postgres added to docker-compose increases dev-env memory by ~200MB. Acceptable.
2. [Likely] Sarvam-30B `generate_answer` 4-8s floor remains. p95 ≤8s requires CLAUDE.md's claimed `reflect_on_answer + verify_answer` merge to actually be in code — verify in nodes.py before benchmarking, fix if not.
3. [Certain] Cache flush after Track A drops hit rate to 0% briefly.
4. [Guessing] Background `extract_and_write` failure could silently lose memories. Mitigation: write to `guru_memory_extraction_queue` table first, mark complete on success, retry-loop in dreamer for failures.
5. [Likely] Pgvector HNSW with 1024d vectors needs `maintenance_work_mem >= 256MB` for index builds beyond ~50k rows. Bake into postgres service config.

**Out of scope**
- Anonymous user memory (auth required)
- Cross-language memory translation
- Memory sharing between users
- Mem0 graph mode (Neo4j-backed relational memory)
- Replacing Sarvam-30B for generation
- Procedural memory (LangMem's 3rd tier) — single-skill app doesn't need it
- Re-ingestion / sparse backfill (proven unnecessary by Phase 0.5)