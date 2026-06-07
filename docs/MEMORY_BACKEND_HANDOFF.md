# Backend implementation handoff — Mukthi Guru memory plan

This document mirrors the approved `.lovable/plan.md` for the Python backend
work. It exists because the Lovable frontend agent cannot validate Python
changes against your live Sarvam/Qdrant/Postgres stack. The host agent
(Claude Code) should apply these in order against `backend/` on your
machine and benchmark with `make eval`.

Frontend pieces of Track B6 are already shipped:
- `src/lib/memoryApi.ts` — typed client calling `${VITE_BACKEND_URL}/api/memory/*`
- `src/components/profile/MemoryManager.tsx` — Memory tab UI
- `src/lib/personalInsights.ts` — multi-source insight derivation
- `src/pages/ProfilePage.tsx` — wired Memory tab + new Recent Insights

The frontend degrades gracefully when `/api/memory/*` returns 404, so you
can ship the frontend now and turn the backend on later.

---

## TRACK A — Retrieval + latency fixes

**Files** (8 modify, 4 create)

### A1. `backend/services/embedding_service.py`
Locate `encode_single_full(self, text: str)`. It currently prepends the E5
instruction prefix *before* calling `encode_batch`, which also prepends.
Result: the prefix appears twice in production query vectors and zero
times in cache lookups against legitimately-prefixed vectors.

Change to:
```python
def encode_single_full(self, text: str) -> dict:
    return self.encode_batch([text])  # single prefix applied inside encode_batch
```
Add `backend/tests/test_embedding_no_double_prefix.py`:
```python
def test_no_double_prefix(svc):
    a = svc.encode_single_full("hello")["dense"]
    b = svc.encode_batch(["hello"])["dense"][0]
    assert a == b
```

Post-deploy: `make flush-cache` once. Cached vectors carry the double
prefix and will all miss against fresh single-prefix queries — expected,
recovers within a day.

### A2. `backend/rag/nodes.py` — `retrieve_documents`
Find the `NameError: query_tier`. Replace the bare reference with:
```python
query_tier = state.get("query_tier", "standard")
```
Add a module-level helper:
```python
def _require_state(state: GraphState, keys: list[str]) -> dict | None:
    missing = [k for k in keys if k not in state]
    if missing:
        return {"error": f"missing state keys: {missing}", "documents": []}
    return None
```
Use it at the top of every node that reads non-trivial state.

Add `backend/tests/test_retrieve_documents_contract.py`:
```python
async def test_retrieve_documents_without_query_tier(svc):
    state = {"question": "What is Deeksha?"}  # no query_tier
    out = await retrieve_documents(state)
    assert "error" not in out
    assert out.get("documents") is not None
```

### A3. `backend/rag/nodes.py` — `format_final_answer` + `extract_memory_insights`
`format_final_answer` currently suppresses `state["citations"]` when
confidence < 0.6. Remove that gate — emit citations on every response;
the consumer can choose to hide them.

Implement `extract_memory_insights`:
```python
async def extract_memory_insights(top_docs: list[Document], k: int = 3) -> list[str]:
    """One Gemini Flash call → up to k atomic 1-sentence claims from the top reranked docs."""
    if not top_docs:
        return []
    snippets = "\n---\n".join(d.page_content[:400] for d in top_docs[:5])
    prompt = (
        "From the spiritual teachings below, extract up to "
        f"{k} atomic, self-contained factual claims (one sentence each). "
        "Return as a JSON list of strings.\n\n" + snippets
    )
    llm = get_llm_for_node("extract_memory_insights")  # routes to gemini-flash
    resp = await llm.ainvoke(prompt)
    try:
        return json.loads(resp.content)[:k]
    except Exception:
        return []
```
Store the output in `state["evaluation_trace"]["insights"]` for benchmark
visibility. Track B's memory writer will consume the same function.

### A4. Latency budget
**`backend/rag/timeout_utils.py`** — keep `TimeoutBudget` but introduce
a constant `GRAPH_HARD_DEADLINE_S = 20.0`.

**`backend/rag/graph_strategies.py`** — in `StandardGraphStrategy.build`
and the streaming-invoke path, pass `RunnableConfig(timeout=GRAPH_HARD_DEADLINE_S)`
into the graph compile/invoke. This is the actual latency cliff — node
timeouts alone won't prevent the 161s p95.

Tighten `NODE_TIMEOUTS`:
```python
NODE_TIMEOUTS = {
    "intent_router": 3,
    "resolve_followup": 3,
    "decompose_query": 4,
    "grade_documents": 4,
    "check_context_sufficiency": 4,
    "navigate_knowledge_tree": 4,
    "generate_answer": 8,
    "verify_answer": 4,
    "reflect_on_answer": 4,
    "rewrite_query": 3,
}
```
Drop the `is_sarvam_cloud` 2× scaling for classifier nodes (they'll be on
Gemini Flash). Keep the scale-up for `generate_answer` and
`reflect_on_answer` only if you haven't already merged them.

For classifier nodes set `llm_max_retries=0`. Two retries on a 3s budget
turned single failed calls into 105s outliers.

### A5. Classifier model swap
**`backend/app/config.py`** — add:
```python
feature_lightweight_classifier: bool = True
feature_regex_prerouter: bool = True
node_model_overrides: dict[str, str] = {}
graph_hard_deadline_s: float = 20.0
```

**`backend/rag/node_llm_config.py`** — add a routing table; when
`feature_lightweight_classifier` and `LOVABLE_API_KEY` is set, return
`google/gemini-2.5-flash` via the Lovable AI Gateway adapter for:
`intent_router`, `resolve_followup`, `decompose_query`, `grade_documents`,
`check_context_sufficiency`, `navigate_knowledge_tree`,
`extract_memory_insights`.

Generation/verification stays on Sarvam-30B.

**`backend/services/llm_factory.py`** — add a `_gemini_flash_via_gateway()`
factory using the OpenAI-compatible client with:
```
base_url = "https://ai.gateway.lovable.dev/v1"
api_key  = os.environ["LOVABLE_API_KEY"]
model    = "google/gemini-2.5-flash"
```
Fall back to Sarvam with a WARN log if `LOVABLE_API_KEY` is missing — do
not crash.

### A6. `backend/rag/intent_prerouter.py` (new)
```python
GREETING = re.compile(r"^(hi|hello|hey|namaste|namaskaram)\b", re.I)
MEDITATION = re.compile(r"\b(start|begin|guide)\b.*\b(meditation|serene)\b", re.I)
DISTRESS = re.compile(r"\b(suicid|kill myself|end it all|hopeless|can't go on)\b", re.I)

def preroute(text: str) -> str | None:
    if DISTRESS.search(text): return "distress"
    if MEDITATION.search(text): return "meditation"
    if GREETING.search(text): return "casual"
    return None
```
Wire into `intent_router` — if `feature_regex_prerouter` and `preroute()`
returns non-None, skip the LLM call entirely.

### A7. `backend/tests/test_chat_endpoint.py`
`mock_get_container` is missing `standard_graph`, `fast_graph`,
`deep_graph`. Add them as Mock(spec=...).

### A8. `backend/benchmarks/smoke_doctrine.py` (new)
9-question CI smoke (< 30s total) covering: Deeksha, Sri Preethaji, Sri
Krishnaji, Ekam, Four Sacred Secrets, Manifest, Oneness, Beautiful State,
distress. Asserts doctrine ≥ 70% and p95 ≤ 8s. Run on every PR.

### A9. Verify Sarvam call-merge
CLAUDE.md claims `reflect_on_answer + verify_answer` are merged into one
LLM call. If they're still two separate `await llm.ainvoke()` calls in
`nodes.py`, merge them — this alone shaves 4-8s off p95.

### Track A exit gate (`make eval`, ALL required)
- Doctrine ≥ 70%, citations ≥ 60%, p95 ≤ 8s, faithfulness ≥ 70%
- LightRAG branch fires on ≥ 40% of entity queries
- Zero NameError/KeyError across 100 runs

---

## TRACK B — Memory layer (parallel to A, behind toggle)

### B1. Infrastructure
**`backend/docker-compose.yml`** — add:
```yaml
postgres:
  image: pgvector/pgvector:pg16
  environment:
    POSTGRES_DB: mukthi_memory
    POSTGRES_USER: mukthi
    POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-mukthi_dev}
  volumes:
    - postgres_data:/var/lib/postgresql/data
  ports: ["5432:5432"]
  command: >
    postgres -c maintenance_work_mem=256MB
             -c shared_buffers=512MB

volumes:
  postgres_data:
```

**Alembic migration** `backend/alembic/versions/0001_memory_tables.py`:
```sql
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE guru_core_memory (
  user_id UUID PRIMARY KEY,
  profile JSONB NOT NULL DEFAULT '{}'::jsonb,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE guru_memories (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL,
  claim TEXT NOT NULL,
  embedding vector(1024) NOT NULL,
  source_message_id TEXT,
  source TEXT NOT NULL DEFAULT 'extracted', -- 'extracted' | 'explicit'
  confidence FLOAT NOT NULL DEFAULT 0.7,
  last_seen TIMESTAMPTZ NOT NULL DEFAULT now(),
  decay_score FLOAT NOT NULL DEFAULT 1.0,
  soft_deleted BOOLEAN NOT NULL DEFAULT false,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX guru_memories_user_active_idx
  ON guru_memories(user_id, soft_deleted) WHERE NOT soft_deleted;
CREATE INDEX guru_memories_embedding_idx
  ON guru_memories USING hnsw (embedding vector_cosine_ops);

CREATE TABLE guru_session_summaries (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL,
  conversation_id TEXT NOT NULL,
  summary TEXT NOT NULL,
  topics TEXT[] NOT NULL DEFAULT '{}',
  sentiment_traj JSONB,
  closed_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX guru_summaries_user_idx ON guru_session_summaries(user_id, closed_at DESC);

-- Optional safety: extraction queue for background-task retries
CREATE TABLE guru_memory_extraction_queue (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL,
  message_id TEXT NOT NULL,
  payload JSONB NOT NULL,
  attempts INT NOT NULL DEFAULT 0,
  last_error TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  completed_at TIMESTAMPTZ
);
```

### B2. `backend/services/memory_service.py` (new)
Async service over `asyncpg`. Key methods (signatures only):
```python
class MemoryService:
    async def get_core(self, user_id: UUID) -> str: ...           # ≤200 tokens
    async def search_semantic(self, user_id: UUID, q_vec: list[float], k: int = 3) -> list[Memory]: ...
    async def recent_summaries(self, user_id: UUID, n: int = 2) -> list[str]: ...
    async def extract_and_write(self, user_id: UUID, message_id: str, turn: dict) -> None: ...
    async def update_core(self, user_id: UUID) -> None: ...       # nightly only
    async def summarize_session(self, conversation_id: str) -> None: ...
    async def forget(self, memory_id: UUID, user_id: UUID) -> None: ...
    async def add_explicit(self, user_id: UUID, text: str) -> Memory: ...
```
Retrieval ranking: `cosine_sim + 0.3 * recency_boost` where
`recency_boost = max(0, 1 - days_since_last_seen / 30)`.
Dedup on write: if cosine to any of the user's last-30-day memories > 0.92,
merge into the highest-confidence row instead of inserting.

### B3. Graph wiring
**`backend/rag/states.py`** — add `memory_context: str | None` to `GraphState`.

**`backend/rag/nodes.py`** — new nodes:
- `inject_memory_context` (after `intent_router`, before `decompose_query`):
  parallel fan-out to `get_core` / `search_semantic` / `recent_summaries`,
  truncate to 830 tokens, store in `state["memory_context"]`.
- `memory_relevance_gate`: skip injection when intent is in
  `settings.memory_skip_intents` (e.g. `doctrine_lookup`, `casual`).

**`backend/rag/prompts.py`** — `context_engineer` appends a `USER MEMORY`
block to the system prompt:
```
USER MEMORY (reference only when relevant to the question):
{memory_context}
```

**`backend/app/main.py`** — after `format_final_answer`, schedule
`memory_service.extract_and_write(...)` as `BackgroundTask`. Never blocks
the response. On exception, the task writes to
`guru_memory_extraction_queue` for the dreamer to retry.

### B4. `backend/scripts/dream_memories.py` (new, cron 03:00 IST)
- Dedup pass (cos > 0.95 merge)
- Decay: `decay_score *= 0.97` for all non-deleted rows
- Soft-delete where `decay_score < 0.1 AND last_seen > now() - 90 days`
- Rewrite `guru_core_memory.profile` from top-30 surviving memories (single
  Gemini Flash call returning JSON)
- Retry items from `guru_memory_extraction_queue` (cap 3 attempts)
- `REINDEX INDEX CONCURRENTLY guru_memories_embedding_idx` if write-count
  since last reindex > 5000

### B5. `backend/app/routers/memory.py` (new)
```
GET  /api/memory/list?page=&page_size=     → MemoryListResponse
POST /api/memory/forget    body { memory_id }
POST /api/memory/add       body { text }
GET  /api/memory/core      → CoreMemory | 404
```
All endpoints require Supabase JWT (validate `Authorization: Bearer …`
via `supabase.auth.get_user(token)`), then scope queries to that user_id.
Mount under `app.main`.

### B6. Frontend — DONE
- `src/lib/memoryApi.ts`
- `src/components/profile/MemoryManager.tsx`
- `src/lib/personalInsights.ts`
- `src/pages/ProfilePage.tsx` (Memory tab + new Recent Insights)

### B7. Feature flags (`backend/app/config.py`)
```python
feature_memory_enabled: bool = False    # master read switch
feature_memory_write: bool = False      # background extractor
feature_memory_ui: bool = False         # frontend tab visibility (frontend
                                        # currently always shows; gate via
                                        # backend env or remove tab)
memory_token_budget: int = 830
memory_skip_intents: list[str] = ["doctrine_lookup", "casual"]
```

Rollout: write-only for 7 days (populate the store) → read-on for 10%
canary → 100%.

### B8. Exit gate
- New benchmark `backend/benchmarks/personalized_recall.py`: 20 queries
  asking "what did I tell you about X" — ≥ 80% correct
- p95 delta (memory ON vs OFF) ≤ 200ms
- Token usage delta ≤ 900 tokens/turn avg
- No doctrine accuracy regression vs Track A baseline

---

## Notes for the host agent

1. The frontend `memoryApi` sends `Authorization: Bearer <supabase_jwt>`.
   Your FastAPI router must validate that exact format.
2. The frontend treats 404 from `/api/memory/*` as "feature not deployed
   yet" and shows a graceful message. You can ship A without B.
3. The `feature_memory_ui` backend flag is not currently consumed by the
   frontend — if you need to fully hide the Memory tab, either remove the
   `<TabsTrigger value="memory">` block in `ProfilePage.tsx` or expose
   the flag through an `/api/config` endpoint and conditionally render.
4. BGE-M3 produces 1024-dim vectors. Memory column is `vector(1024)`. Do
   not mix in OpenAI 1536-dim embeddings.
5. `LOVABLE_API_KEY` is required for the Gemini Flash classifier swap and
   the nightly core-block rewrite. Provision via `lovable_api_key--create`
   if missing; the frontend never sees it.
