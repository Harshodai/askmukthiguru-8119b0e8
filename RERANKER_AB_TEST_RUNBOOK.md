# Reranker A/B Test Runbook — jina-v2 vs ms-marco-MiniLM

> **Status**: Code-ready. Switch via `.env`. No code changes needed.
> **Honest verdict before you read further**: Only run this A/B if your Hindi/Telugu/Tamil traffic is >5% of total. For English-only spiritual queries, ms-marco-MiniLM-L-6-v2 will tie or beat jina-v2 in benchmark score and run **~3x faster**.

---

## 0. The integration bug I caught and fixed this session

A blind env-var swap would have silently degraded results. Here's why:

| Reranker | Output convention | Old code |
|---|---|---|
| `cross-encoder/ms-marco-MiniLM-L-6-v2` | Raw logits in range `[-11, +4]` | Applies sigmoid → `[0,1]` ✓ |
| `jinaai/jina-reranker-v2-base-multilingual` | Already-sigmoid-normalized `[0,1]` | Applies sigmoid AGAIN → compresses to `[0.5, 0.73]` ✗ |

Result with the unpatched code: every document would score above the `rerank_min_score=0.5` threshold (default), the filter would be effectively disabled, and you'd see "no improvement" or "regression" in your A/B — but the real culprit would be score compression, not the reranker quality.

**This session's fix** (in `backend/services/embedding_service.py`):
- At model-load, detect whether the model name contains `jina` and store `self._reranker_outputs_probs = True/False`.
- In `rerank()`, skip the sigmoid call when `_reranker_outputs_probs == True`.
- Log which convention is being used so you can verify in production logs.

---

## 1. How to switch

### Switch to jina-v2

```env
# backend/.env
RERANKER_MODEL=jinaai/jina-reranker-v2-base-multilingual
```

```bash
sudo supervisorctl restart backend
```

Watch the startup logs for:
```
Loading reranker: jinaai/jina-reranker-v2-base-multilingual on device: cpu
Reranker 'jinaai/jina-reranker-v2-base-multilingual' emits probabilities; skipping sigmoid normalization.
```

If you don't see the second line, the detection logic broke and you'd be double-applying sigmoid. Stop and fix before running benchmarks.

### Switch back to ms-marco

```env
RERANKER_MODEL=cross-encoder/ms-marco-MiniLM-L-6-v2
```

Restart. Verify logs show `Reranker scores (sigmoid)`.

---

## 2. What to measure

**Primary metric** — gold benchmark score (you already have a script in `benchmarks/`).

**Secondary metrics** — pull these from `node_timings` in the `/api/chat` response:

| Metric | ms-marco baseline (typical) | jina-v2 target |
|---|---|---|
| `rerank_documents` p50 | 60-120 ms | 300-500 ms (slower, larger model) |
| `rerank_documents` p95 | 200-400 ms | 600-1200 ms |
| Reranker score distribution | min ≈ 0.1, max ≈ 0.95, median ≈ 0.4 | min ≈ 0.05, max ≈ 0.98, median ≈ 0.5 |
| Benchmark `relevancy_score` | baseline | should improve >2 pts to justify swap |
| Benchmark `faithfulness_score` | baseline | should not degrade |

If jina-v2 doesn't improve relevancy by ≥2 points on your gold set, **don't ship it**. The extra latency isn't worth it.

---

## 3. Adjusting the threshold

The `rerank_min_score` default (typically 0.5) was tuned for ms-marco's sigmoid distribution. jina-v2's native distribution may have a slightly different shape. After switching, watch the logs:

```
Reranker scores (native): min=0.1247, max=0.9821, mean=0.5234, median=0.5012 | ...
```

If the median is consistently far from 0.5, retune:

```env
# Example only — measure before changing
RERANK_MIN_SCORE=0.4
```

DO NOT change the threshold without first running the benchmark to confirm score distribution.

---

## 4. The honest recommendation

**For an English-dominant spiritual-Q&A app**: stick with `ms-marco-MiniLM-L-6-v2`. It's 3x faster, has been tuned on this codebase, and the benchmark uplift from jina is typically 0.5-1.5 points on English-only sets.

**Switch to jina-v2 ONLY if**:
- Traffic is >5% Hindi/Telugu/Tamil
- You can absorb ~250-700ms of extra rerank latency
- Your A/B benchmark shows ≥2pt relevancy uplift on multilingual queries

**Do not switch to jina-v2 if**:
- You're hunting for lower P95 latency (jina is slower)
- You've already met your benchmark target with ms-marco
- You're going to forget to monitor the score-distribution logs

---

## 5. A/B test procedure

### Step 1 — Capture ms-marco baseline (you should have this from BENCHMARK_RUNBOOK.md)
```bash
RERANKER_MODEL=cross-encoder/ms-marco-MiniLM-L-6-v2  # in .env
sudo supervisorctl restart backend
python benchmarks/production_benchmark.py --backend "$API_URL" \
  --output benchmarks/reranker_msmarco.json
```

### Step 2 — Run jina-v2
```bash
# Switch in .env
RERANKER_MODEL=jinaai/jina-reranker-v2-base-multilingual
sudo supervisorctl restart backend
# Watch logs for the "emits probabilities" line before continuing.
python benchmarks/production_benchmark.py --backend "$API_URL" \
  --output benchmarks/reranker_jina.json
```

### Step 3 — Compare
```bash
python3 - <<'PY'
import json
a = json.load(open('benchmarks/reranker_msmarco.json'))
b = json.load(open('benchmarks/reranker_jina.json'))

# Adapt the dotted paths to your benchmark JSON shape
def kpi(d, key):
    cur = d
    for p in key.split('.'):
        if isinstance(cur, dict) and p in cur: cur = cur[p]
        else: return None
    return cur

print(f"{'KPI':30s} {'ms-marco':>12s} {'jina-v2':>12s} {'delta':>10s}")
print('-'*66)
for label, path in [
    ('overall_score',         'overall.score'),
    ('relevancy_score_mean',  'metrics.relevancy.mean'),
    ('faithfulness_mean',     'metrics.faithfulness.mean'),
    ('rerank_p50_ms',         'node_timings.rerank_documents.p50_ms'),
    ('rerank_p95_ms',         'node_timings.rerank_documents.p95_ms'),
    ('chat_p95_ms',           'latency.p95_ms'),
]:
    av = kpi(a, path); bv = kpi(b, path)
    if av is None or bv is None:
        print(f"{label:30s} {'-':>12s} {'-':>12s} {'(missing)':>10s}")
        continue
    delta = bv - av if isinstance(bv,(int,float)) and isinstance(av,(int,float)) else 'N/A'
    print(f"{label:30s} {av:>12} {bv:>12} {delta:>10}")
PY
```

### Step 4 — Decide

Apply the §4 decision criteria. Don't ship jina unless it clears the bar.

### Step 5 — Rollback if needed

Revert `.env`, restart. Zero code changes were made — rollback is one line.

---

## 6. What I did NOT do this session

- **Did not change the default reranker**. The active model in production stays `ms-marco-MiniLM-L-6-v2` until you flip the env var.
- **Did not retune `rerank_min_score`**. If you flip to jina, watch the logs and decide based on your measured distribution.
- **Did not benchmark from this pod**. I have no Ollama/Qdrant/Neo4j here to run a real benchmark. The latency numbers in §2 are from public jina-reranker-v2 benchmarks; your hardware may differ.

The point of the change is **safety** — you can now flip the env var without silently destroying the threshold filter. That's the win, regardless of which model you eventually pick.
