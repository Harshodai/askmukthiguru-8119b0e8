# Benchmark Runbook — Phase-1 Optimization Verification

> **Audience**: You (running benchmarks on your own infrastructure).
> **Goal**: Quantify the impact of the three changes applied in this session.
> **Time budget**: ~30 minutes including warm-up.

---

## What was changed

| Change | File | Expected impact |
|---|---|---|
| `classify_intent` → fast model | `backend/services/ollama_service.py` | `intent_router` p50 drops 14-30s → <1s |
| `classify_intent_and_complexity` combined | `backend/services/ollama_service.py` + `backend/rag/prompts.py` + `backend/services/llm/ollama_provider.py` | One LLM call instead of two in intent_router |
| Semantic cache: N GETs → 1 MGET | `backend/services/semantic_cache.py` | Cache lookup network time drops from N×RTT to 1×RTT |

**Prerequisite**: `MODEL_FOR_CLASSIFICATION` in `backend/.env` must point at a small/fast model (recommended: `llama3.2:3b`). If it's still `deepseek-r1:7b`, the speedup will be ~0.

---

## Step 1 — Capture baseline (if you didn't already)

```bash
cd /app/external/askmukthiguru/backend
git stash                         # temporarily revert this session's changes
python benchmarks/production_benchmark.py \
  --backend "$API_URL" \
  --output benchmarks/baseline.json
git stash pop                     # reapply the changes
```

If you already have a baseline from before the session, skip this and use that file.

---

## Step 2 — Pull the fast model on the Ollama host

```bash
# SSH to Ollama host
ollama pull llama3.2:3b
ollama list | grep llama3.2
```

Confirm `backend/.env`:
```env
MODEL_FOR_CLASSIFICATION=llama3.2:3b
MODEL_FOR_GENERATION=deepseek-r1:7b   # keep unchanged
LLM_TIMEOUT=60
```

Restart the backend:
```bash
sudo supervisorctl restart backend
```

Wait 30s for `ChatOllama` warmup, then continue.

---

## Step 3 — Single-query smoke test

```bash
# Get a JWT from a logged-in browser tab:
#   await supabase.auth.getSession().then(s => s.data.session.access_token)
export JWT="<paste>"
export API_URL="https://your-backend.com"

curl -sw "\n--- TIMING %{time_total}s ---\n" \
  -X POST "$API_URL/api/chat" \
  -H "Authorization: Bearer $JWT" \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [],
    "user_message": "What is the Beautiful State?",
    "session_id": "rbench-1",
    "meditation_step": 0,
    "language": "en"
  }' | tee /tmp/r1.json | python3 -c "
import sys, json
r = json.loads(open('/tmp/r1.json').read().split('--- TIMING')[0])
print('query_tier      :', r.get('query_tier'))
print('intent          :', r.get('intent'))
print('latency_ms      :', r.get('latency_ms'))
print('node_timings    :')
for k, v in sorted((r.get('node_timings') or {}).items(), key=lambda x: -x[1]):
    print(f'  {k:30s} {v:>8} ms')
"
```

**Pass criteria**:
- `query_tier == "fast"` (this query matches the fast pattern)
- `node_timings["intent_router"] < 2000` ms (was 14000-30000)
- `latency_ms < 15000` warm

**Fail diagnosis**:
- If `intent_router` is still slow: confirm `MODEL_FOR_CLASSIFICATION` actually points to the fast model and that the model is loaded (`ollama list`).
- If `query_tier == "standard"`: the regex in `select_graph_for_query` didn't match. Try a clearer "what is X?" prompt.
- If 401: JWT expired; re-fetch from the browser.

---

## Step 4 — Run the full benchmark suite

```bash
cd /app/external/askmukthiguru/backend
python benchmarks/production_benchmark.py \
  --backend "$API_URL" \
  --output benchmarks/results_phase1.json
```

This will take 5-15 minutes. Don't kill it.

---

## Step 5 — Compare baseline vs phase-1

If your repo has `benchmarks/compare_results.py`:
```bash
python benchmarks/compare_results.py \
  --before benchmarks/baseline.json \
  --after  benchmarks/results_phase1.json
```

Else, quick diff in Python:
```bash
python3 - <<'PY'
import json
b = json.load(open('benchmarks/baseline.json'))
a = json.load(open('benchmarks/results_phase1.json'))

# Adapt these field names if your benchmark JSON shape differs
def kpi(d, key, default=None):
    # Walk a dotted path
    cur = d
    for p in key.split('.'):
        if isinstance(cur, dict) and p in cur: cur = cur[p]
        else: return default
    return cur

keys = [
    ('overall_score',            'overall.score'),
    ('p50_latency_ms',           'latency.p50_ms'),
    ('p95_latency_ms',           'latency.p95_ms'),
    ('timeout_rate',             'errors.timeout_rate'),
    ('intent_router_ms',         'node_timings.intent_router.mean_ms'),
    ('decompose_query_ms',       'node_timings.decompose_query.mean_ms'),
    ('grade_documents_ms',       'node_timings.grade_documents.mean_ms'),
    ('cache_hit_rate',           'cache.hit_rate'),
]
print(f"{'KPI':30s} {'before':>12s} {'after':>12s} {'delta':>12s}")
print('-'*68)
for label, path in keys:
    bv = kpi(b, path)
    av = kpi(a, path)
    if bv is None or av is None:
        print(f"{label:30s} {'-':>12s} {'-':>12s} {'(missing)':>12s}")
        continue
    delta = av - bv if isinstance(av, (int, float)) and isinstance(bv, (int, float)) else None
    print(f"{label:30s} {bv:>12} {av:>12} {('+'+str(delta) if delta and delta>0 else str(delta)):>12}")
PY
```

**Pass criteria for Phase-1**:
- `intent_router_ms` mean drops by **>10x** (was the goal)
- `p50_latency_ms` improves by at least 5 seconds on fast-tier queries
- `timeout_rate` does NOT regress (fast classification should reduce timeouts, not cause them)
- `overall_score` should improve marginally; large gains require Phases 2-6 (see `REFERENCE_DEVELOPMENT_GUIDE.md`)

---

## Step 6 — Cache MGET validation

```python
# In a Python REPL with the backend env loaded
import time
from services.semantic_cache import SemanticCacheService
from app.config import settings

# Wire it like dependencies.py does
import redis
# (You'll need the embedder too; easiest is to run inside a backend shell)

# After populating ~50 entries:
t = time.time()
result = svc.get("a query the user has asked before")
print(f"get latency: {(time.time()-t)*1000:.1f} ms")
```

**Pass criteria**: <50ms warm even with 500 entries. The Python cosine scan dominates above ~200 entries — if that becomes a problem, see `REFERENCE_DEVELOPMENT_GUIDE.md §2.4` (Qdrant ANN cache).

---

## Step 7 — Parse-failure fallback validation

Confirm that if the fast model returns garbage, the system gracefully falls back to two sequential calls.

```python
# Mock _generate_fast to return junk:
from unittest.mock import patch
import asyncio
from services.ollama_service import OllamaService
svc = OllamaService()

async def junk(*args, **kwargs):
    return "I am a confused LLM"

# This should trigger the fallback two-call path
with patch.object(svc, '_generate_fast', side_effect=[junk(), 'FACTUAL', 'simple']):
    res = asyncio.run(svc.classify_intent_and_complexity("What is X?"))
    print(res)  # Should still return a valid {"intent": ..., "complexity": ...}
```

Actually simpler — manually trigger by making the combined prompt produce unparseable output. The fallback path uses the legacy `classify_intent` + `classify_complexity`. Both are tested by every benchmark run already.

---

## What "success" looks like after this session

You should see one of these three outcomes:

### Outcome A — Big win (most likely if MODEL_FOR_CLASSIFICATION was deepseek-r1:7b before)
- `intent_router` p50: 18000ms → 600ms
- Overall p95 latency: 154s → ~110s
- Timeouts on fast-tier queries: gone

### Outcome B — Modest win (if classification was already on a small model)
- `intent_router` p50: 800ms → 400ms
- Overall p95 latency: marginal improvement
- The bigger blockers are now `decompose_query` and `retrieve_documents` — see `REFERENCE_DEVELOPMENT_GUIDE.md §2.3`

### Outcome C — No win
- Something is misconfigured. Check:
  1. Did `supervisorctl restart backend` actually pick up the new code?
  2. Is the fast model actually loaded? (`ollama list` on the host)
  3. Are you hitting the right backend? (`$API_URL` correct?)
  4. Did `MODEL_FOR_CLASSIFICATION` change in the running process? (Check via `/api/health` if it exposes it, else `env` inside the container.)

---

## What NOT to expect from this session

- ❌ The plan's "55% → 98% benchmark score" is **NOT** achievable from Phase-1 alone. That requires Phases 2-6.
- ❌ Faithfulness or doctrine accuracy will not change — those are generation/verification problems, not classification problems.
- ❌ Concurrent-user capacity will not change — that requires connection pooling and Ollama instance scaling.

Phase-1 is necessary, not sufficient. Read `REFERENCE_DEVELOPMENT_GUIDE.md` next.

---

## Rollback

If something breaks:

```bash
cd /app/external/askmukthiguru
git status                        # see what changed
git diff backend/services/ollama_service.py
git diff backend/services/semantic_cache.py
git diff backend/services/llm/ollama_provider.py
git diff backend/rag/prompts.py

# To revert ONLY this session's changes:
git checkout backend/services/ollama_service.py \
              backend/services/semantic_cache.py \
              backend/services/llm/ollama_provider.py \
              backend/rag/prompts.py
sudo supervisorctl restart backend
```

The changes are isolated to four files. Reverting is safe.
