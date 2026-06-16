# WHAT_TO_DO.md — Operations Runbook for Mukthi Guru

> This is the "if you only read one file, read this" operations doc.
> It tells maintainers exactly what to do for the most common scenarios:
> shipping changes, debugging failures, tuning quality, and validating accuracy.
> Source of truth for the implementation plan: `.claude/tasks/WORLD_CLASS_MUKTHIGURU.md`.

---

## TL;DR — the 90-second tour

| You want to... | Go here |
|---|---|
| Run the app locally | `docker compose up -d --build` from `backend/` |
| Change intent routing without writing code | Edit `backend/config/router_routes.yaml` |
| Add a new crisis helpline | Edit `crisis_helplines:` in `backend/config/router_routes.yaml` |
| Add a new doctrinal keyword | Edit `doctrine_keywords:` in `backend/config/router_routes.yaml` |
| Swap the LLM provider | Set `LLM_PROVIDER_CHAIN` env var |
| Run the meditation-hijack regression suite | `pytest backend/tests/test_meditation_routing.py -v` |
| Run the YAML router suite | `pytest backend/tests/test_semantic_router.py -v` |
| Run the full benchmark | `python3 backend/benchmarks/run_all.py --endpoint http://localhost:8000` |
| Inspect why a query was routed somewhere | Look for `routing_reason=` in backend logs |
| See per-stage latency for a request | `trace_id` → Jaeger UI on `:16686` |

---

## 1. Local development (full stack)

### Prerequisites
- Docker Desktop (Mac/Linux)
- Node 22 LTS (CodeGraph requires it; 25.x has a WASM bug)
- Python 3.11+
- Bun 1.3.14+

### One-command spin-up
```bash
cd backend
docker compose up -d --build
```
This starts Qdrant (`:6333`), Redis (`:6379`), Neo4j (`:7474`/`:7687`), Jaeger
(`:16686`), the FastAPI backend (`:8000`), and the Nginx-served frontend (`:80`).

### Health checks (each MUST be green before claiming "running")
```bash
curl http://localhost:8000/api/health        # backend
curl http://localhost:6333/                  # Qdrant
redis-cli ping                               # Redis (PONG)
curl http://localhost:7474                   # Neo4j browser
curl http://localhost                        # frontend
```

### Logs
```bash
docker compose logs -f backend | tail -200
docker compose logs -f --tail=50 qdrant
```

### Hot-reload
- Backend: `uvicorn` reloads on Python file change (if running outside Docker
  via `uvicorn app.main:app --reload`).
- Frontend: `vite dev` hot reloads (default port `:8080`).

---

## 2. Configuration reference

### Where each setting lives
- `backend/.env` — secrets, infra URLs, LLM keys
- `backend/config/router_routes.yaml` — intent routing, doctrine keywords, crisis helplines
- `backend/app/config.py` — Python defaults for all envs (Pydantic Settings)

### The most-edited envs
| Env var | Default | What it does |
|---|---|---|
| `LLM_PROVIDER` | `sarvam_cloud` | Switches provider family |
| `LLM_PROVIDER_CHAIN` | `anthropic:claude-sonnet-4-6,...` | Ordered fallback chain (Phase A7) |
| `EMERGENT_LLM_KEY` | empty | Universal key for emergentintegrations |
| `SARVAM_API_KEY` | empty | Sarvam Cloud key |
| `USE_SEMANTIC_ROUTER` | `true` | Toggle YAML-driven intent routing |
| `INTENT_DEMOTE_MEDITATION_ON_INTERROGATIVE` | `true` | Kills the Soul-Sync-on-Mars hijack |
| `STRIP_CANNED_FOOTER` | `true` | Removes the AI-tell footer from responses |
| `WEB_SEARCH_ENABLED` | `false` | Enable temporal-query web search |
| `WEB_SEARCH_ALLOWED_DOMAINS` | `ekam.org,theonenessmovement.org` | Comma-separated whitelist |
| `ROUTER_CONFIG_PATH` | empty | Override the YAML location |

### Never commit
- `backend/.env`
- `frontend/.env.local`
- API keys of any kind
- Anything under `keys/`, `secrets/`

---

## 3. Editing intent routing without touching Python

The router is **YAML-first**. To add or change behaviour:

### Add a new intent route
```yaml
# backend/config/router_routes.yaml
routes:
  - name: GRATITUDE
    priority: 550
    threshold: 0.74
    utterances:
      - "Thank you so much for this guidance"
      - "I am so grateful for your wisdom"
      - "Bless you for the teaching today"
```
Then add the route → graph-intent mapping in
`backend/rag/nodes/intent.py:_map_router_route_to_intent` (one line):
```python
"GRATITUDE": ("CASUAL", "tier2_simple", False),
```

### Tighten a route (false positives)
- Raise its `threshold` (e.g. 0.74 → 0.78).
- Add `exclude_if_interrogative: true` if the route should never fire on a "?" query.
- Add `require_imperative: true` if the route requires explicit action verbs.

### Loosen a route (false negatives)
- Lower its `threshold`.
- Add more `utterances` covering missed phrasings.
- Add a high-precision `regex:` pattern as a safety net.

### Re-run tests after any YAML change
```bash
cd backend && pytest tests/test_semantic_router.py -v
```

---

## 4. Debugging a bad answer

### Step 1 — get the trace_id
Every `/api/chat` response includes `trace_id`. Search logs:
```bash
docker compose logs backend | grep <trace_id>
```

### Step 2 — find the routing_reason
Look for `routing_reason=...`. Possible values:
- `regex_prerouter` — the regex preroute fired (likely SAFETY, DISTRESS, or CASUAL)
- `semantic_router_regex` — YAML router regex fired
- `semantic_router_embedding` — YAML router embedding match fired
- `heuristic_capability`, `heuristic_simple` — legacy heuristic fastpath
- `cache_hit` — semantic-cache replay (the answer is from a previous run!)
- `serene_mind_keyword_distress` — distress detector promoted the query
- `temporal_query_heuristic` — temporal pattern detected, web search enabled
- `semantic_router_fallback` — exception path, default classification used

### Step 3 — check per-stage timings
```bash
docker compose logs backend | grep <trace_id> | grep "stage="
```
Look for any stage with `latency_ms` > 10× the median for that stage.

### Step 4 — the meditation-hijack regression
If the answer is *"The meditation is complete..."* and the query wasn't a
meditation request, you've hit the regression we patched in Phase A1.1.
Verify the fix is in place:
```bash
pytest backend/tests/test_meditation_routing.py -v
```
All non-skipped tests must pass.

### Step 5 — open Jaeger
`http://localhost:16686` → service `mukthi-guru-backend` → search by trace_id.

---

## 5. Quality / accuracy work

### The two benchmarks you actually need
1. **`backend/benchmarks/native_eval.py`** — Ragas-style: context precision +
   answer faithfulness, runs against your local Ollama / Sarvam.
2. **`scripts/benchmarks/askmukthiguru_ruthless_benchmark.py`** — end-to-end
   over the live HTTP endpoint. This is what produced `results/query_results.json`.

### Read the benchmark output critically
- Cache hit rate ≥ 80% → headline pass rate is **inflated**. Run with cache
  disabled to get the real number:
  ```bash
  SEMANTIC_CACHE_ENABLED=false python3 scripts/benchmarks/askmukthiguru_ruthless_benchmark.py
  ```
- Keyword-only PASS/FAIL is too crude. The LLM-as-judge evaluator
  (Phase A2, see `.claude/tasks/WORLD_CLASS_MUKTHIGURU.md`) is the real
  signal. Use composite score across (groundedness, doctrine, tone,
  citation, refusal) before claiming an accuracy number.

### What "97% accuracy" really means here
Defined as composite ≥0.97 across these LLM-judged dimensions on a 200-question
stratified set (Phase E exit criterion):
- groundedness — every claim cited
- doctrinal consistency — Preethaji-Krishnaji-Ekam tradition
- tone — guru-like, no AI-tells
- citation correctness — cited source actually says it
- refusal correctness — adversarial / out-of-domain handled right

Anything less and the claim is marketing, not engineering.

### Eval rubric is in `RAG_QUALITY.md`
See that doc for the full eval methodology, including the recommended
adversarial set composition and the doctrinal consistency classifier.

---

## 6. The standard "no hardcoding" rule

If you find yourself typing one of these in code, **stop and put it in YAML or .env instead**:

- A list of keyword strings → `router_routes.yaml`
- A threshold (0.7, 0.92, etc.) → `app/config.py` Settings field
- A model name (`claude-sonnet-4-6`, `sarvam-30b`) → `LLM_PROVIDER_CHAIN` env
- A URL (Supabase, Qdrant, YouTube) → env var
- A magic number (timeout, max retries, step count) → Settings field
- A prompt string that varies by intent → `prompts.py` constant (referenced by name)

Audit checklist before merging a PR:
```bash
# 1. Grep for new hardcoded keyword lists
grep -nE "^(_[A-Z_]+_PATTERNS|_[A-Z_]+_RE)\s*=\s*\[" backend/ | grep -v config/ | grep -v test
# 2. Grep for new hardcoded model strings
grep -nE "\"(claude|gpt|sarvam|gemini)-[a-z0-9.-]+\"" backend/ | grep -v config.py | grep -v test
# 3. Grep for hardcoded crisis numbers
grep -nE "9152987821|9820466726|988|741741" backend/ | grep -v config/ | grep -v test
# Each must return EMPTY or only point to config files.
```

---

## 7. LLM provider switching

The unified gateway (Phase A7) reads `LLM_PROVIDER_CHAIN` and tries each entry
in order on transient failure. Format: `provider:model,provider:model,...`.

### Recommended default (Jan 2026)
```
LLM_PROVIDER_CHAIN=anthropic:claude-sonnet-4-6,anthropic:claude-haiku-4-5-20251001,openai:gpt-5.4
```

### To switch to Sarvam-only
```
LLM_PROVIDER=sarvam_cloud
SARVAM_API_KEY=<your-key>
```

### To use Emergent universal key
```
EMERGENT_LLM_KEY=sk-emergent-XXXX
LLM_PROVIDER_CHAIN=anthropic:claude-sonnet-4-6
```

Key budget running low → Profile → Universal Key → Add Balance / Enable auto top-up.

---

## 8. Web search — real-time / temporal queries

Web search is **opt-in** and gated by `WEB_SEARCH_ENABLED=true`.

### How it fires
A query is sent through the YAML router. If it matches the `TEMPORAL` route
(events, schedules, "this month", "upcoming"), `needs_web_search=true` is set in
the graph state. The `web_search_node` runs in parallel with the standard
vector retrieval and merges results in `enrich_context`.

### Adding a temporal pattern
Just edit `router_routes.yaml` → `routes: - name: TEMPORAL: utterances:`.
**Do not** add to any hardcoded list in Python.

### Adding allowed domains
```bash
# in backend/.env
WEB_SEARCH_ALLOWED_DOMAINS=ekam.org,theonenessmovement.org,onenessuniversity.org
```

### Provider choice
- `WEB_SEARCH_PROVIDER=duckduckgo` (default, no API key)
- `WEB_SEARCH_PROVIDER=searxng` + `SEARXNG_URL=http://...` (self-hosted privacy-preserving)

### Guardrails (defense-in-depth, already implemented)
1. Input sanitization (`web_search_guardrails.sanitize_query`)
2. Length validation, blocked pattern check, repetition check
3. Rate limiting (per-user, default 10 queries/60s)
4. SSRF prevention (block private IPs, file://, non-HTTP)
5. Domain whitelist enforcement
6. Content sanitization (strip HTML, JS)
7. Safety scoring (suspicious patterns, freshness)
8. Deduplication (URL + Jaccard title similarity)
9. Audit logging

### Disabling web search for an environment
```
WEB_SEARCH_ENABLED=false
```
The TEMPORAL route will still classify but the web-search node will return [].

---

## 9. Persona / prompt management

### Where the system prompt lives
`backend/rag/prompts.py` — `GURU_SYSTEM_PROMPT`. All other prompts are also there.

### When you change the system prompt
1. Run the persona regression set (10 stratified queries) before/after and
   eyeball them side by side.
2. Run the LLM-judge eval (Phase A2) — composite score on tone must not regress.
3. Verify the "AI-tell" patterns are absent:
   ```bash
   grep -nE "As an AI|Based on what I found in the teachings|I am an AI|though I recommend exploring" backend/rag/prompts.py backend/rag/nodes/generation.py
   ```
   Should return nothing (except in legacy/disabled paths gated behind
   `strip_canned_footer=False`).

### When you add a new prompt
- Add it to `prompts.py` as a named constant.
- Reference it by name from node code; **never inline a multi-line prompt string in nodes/**.

---

## 10. Memory / context

### Session ID normalization
The orchestrator normalizes browser-side IDs to stable UUIDs via
`rag.memory.normalize_session_id`. Don't bypass this — Supabase memory tables
key on the normalized ID.

### Per-user memory write
On every successful answer, `PipelineCoordinator._save_memory` writes:
- `user_id`, `session_id`, `user_msg`, `final_answer`, `intent`,
  `meditation_step`, `citations`, `distress_level`.
- 200ms hard budget. If write times out, the user-facing response still goes
  out — memory is best-effort.

### Reading memory back
`memory_service.get_compact_context(user_id, session_id)` returns a small
USER PROFILE & CORE FACTS block + recent thread block. Injected into the RAG
context for the generation prompt.

---

## 11. Crisis / safety paths (DO NOT WEAKEN)

The DISTRESS path is a **non-negotiable** quality bar.

### What must always work
- An acute distress query (e.g. `"I want to end my life"`) MUST:
  1. Match the SAFETY_VIOLATION regex layer (highest priority).
  2. Return a response that leads with crisis helpline contacts.
  3. Never be served from semantic cache.
  4. Be telemetry-logged as `event=distress_crisis_triggered`.

### Regression test
The benchmark MUST contain at least one acute-distress query per release.
Currently lives in `backend/benchmarks/question_bank.py` under
`safety_violation` / `crisis_helplines`.

### Editing the helpline list
Edit `crisis_helplines:` in `router_routes.yaml`. The DISTRESS handler renders
them into the response at runtime from that list, **not** from hardcoded
strings.

---

## 12. Release checklist

Before tagging a release:

- [ ] `pytest backend/tests/` passes (no skipped tests caused by missing deps in CI)
- [ ] `vitest src/tests/` passes
- [ ] `pytest backend/tests/test_meditation_routing.py` — meditation hijack regression
- [ ] `pytest backend/tests/test_semantic_router.py` — YAML routing regression
- [ ] `python3 backend/benchmarks/run_all.py --endpoint http://localhost:8000` — no PASS→FAIL drops
- [ ] Run cache-disabled benchmark; non-cached pass rate did not regress
- [ ] Manual smoke: 5 queries across categories (factual, distress, adversarial, casual, Hinglish)
- [ ] Hardcode audit script (section 6) returns empty
- [ ] CHANGELOG updated
- [ ] `.claude/tasks/WORLD_CLASS_MUKTHIGURU.md` execution log appended

---

## 13. When the user reports a bug

### Triage flow
1. Get the exact query and the trace_id (frontend should surface it; backend logs have it).
2. Reproduce locally with the same query.
3. Find the `routing_reason` in the logs.
4. Check whether the bug is:
   - a routing bug (YAML route fired wrong → fix in YAML)
   - a retrieval bug (no relevant docs returned → check Qdrant, re-ingest if needed)
   - a generation bug (prompt produced wrong text → fix in `prompts.py`)
   - a verification bug (CoVe / Self-RAG flagged a good answer → tune threshold)
5. Add the failing query to the regression set in `question_bank.py`.
6. Ship the fix + the regression test in the same PR.

### "Bug fix without a regression test" → reject the PR
Every accepted bug fix MUST add the failing case to `question_bank.py` or a
unit test. Otherwise the same bug reappears.

---

## 14. Things that have already been done (so don't re-do them)

- ✅ Meditation hijack patched in 4 layers: `intent.py` LLM-classification demote, `intent_prerouter.py` regex tightening, `meditation.py` Null-Object format response, `handle_meditation` safety net. Regression suite in `tests/test_meditation_routing.py`.
- ✅ Canned `*Note: Based on what I found in the teachings...*` footer is now stripped by default (`strip_canned_footer=True`).
- ✅ YAML-driven SemanticRouter is wired into `intent.py` and consumes `backend/config/router_routes.yaml`.
- ✅ Crisis helplines, doctrine keywords, interrogative stems, imperative verbs are all in YAML, not code.
- ✅ Web search is correctly gated by the YAML `TEMPORAL` route (when `USE_SEMANTIC_ROUTER=true`).

## 15. Things still to do (Phase B onward)

See `.claude/tasks/WORLD_CLASS_MUKTHIGURU.md`.

- LLM-judge evaluator (Phase A2)
- Unified LLMGateway with Claude Sonnet 4-6 (Phase A7)
- Rewrite `GURU_SYSTEM_PROMPT` (Phase B1)
- Doctrinal consistency classifier (Phase B3)
- NotebookLM-style inline citation chips UI (Phase C1)
- Source pinning toggle (Phase C2)
- LangGraph parallel branches (Phase D1)
- Per-node `asyncio.wait_for` timeout (Phase D4)
- 200-question stratified eval set (Phase E1)
- DeepEval-based composite scoring (Phase E2)
