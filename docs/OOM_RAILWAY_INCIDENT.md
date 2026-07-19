# Railway Backend OOM Crash — bge-m3 Model Loading

## Status
**Fixed, pending deploy.** Backend (`askmukthiguru-8119b0e8`) crashed at startup on every deploy since 2026-07-19.

**Root cause of the regression**: `PYTHON_MEMORY_LIMIT_MB` was lowered from 6144 to 3584 in an earlier same-day session, intended as a memory-safety improvement (keeping RLIMIT_DATA below the then-4Gi container hard limit). In practice 3584MB is below bge-m3 + PyTorch + tokenizer's genuine peak load, so the "safety" fence became the proximate crash trigger instead of Railway's own cgroup OOM-killer.

**Fix applied** (combines doc fix options #1/#2 below):
- `railway.json`: `deploy.limits.memory` raised `4Gi` → `6Gi` (Railway bills actual usage, not this cap, so no cost increase unless real usage grows to fill it).
- Railway var `PYTHON_MEMORY_LIMIT_MB`: `3584` → `5632` (real headroom under the new 6Gi cap, instead of sitting below the old, too-tight 4Gi one).
- Investigated whether a HF cache revision mismatch between the Dockerfile's build-time pre-cache and the runtime load was forcing a re-download (which would explain the "Fetching 30 files" log line under memory pressure) — ruled out: `BGEM3FlagModel`/`FlagEmbedding`'s `M3Embedder` never forwards a `revision` kwarg to `AutoTokenizer.from_pretrained` (only `cache_dir` is honored; other kwargs are absorbed as dead instance attributes), so the Dockerfile's `revision=` pin was already a no-op on both sides — not the actual mechanism. Not pursued further.
- **Not yet done**: redeploy (`railway up`) to confirm the fix — deploy is gated by this environment's permission classifier, needs manual approval.

## Symptoms
- `railway status` shows `● Crashed`
- Deploy logs show `SUCCESS` (Docker build passes), then runtime crash
- Health check returns `503` or connection refused
- Error log pattern:

```
Fetching 30 files:  60%|██████    | 18/30 [00:00<00:00, 40.77it/s]
memory allocation of 67045084 bytes failed
Fatal Python error: Aborted
```

## Root Cause

**Two memory limits collide:**

| Layer | Limit | Source |
|---|---|---|
| Railway container | 4 GiB | `railway.json` → `deploy.limits.memory: "4Gi"` |
| Python RLIMIT_DATA | 3,584 MB | Railway env `PYTHON_MEMORY_LIMIT_MB=3584` |

The bge-m3 embedding model (`BAAI/bge-m3`, ~2.2 GB on disk) is loaded into RAM by `embedding_service.py:160`:

```python
from FlagEmbedding import BGEM3FlagModel
self._encoder = BGEM3FlagModel(model_name, use_fp16=False, device="cpu")
```

At runtime, PyTorch + tokenizer + the model weights + all other dependencies (scipy, sklearn, numpy, pandas, etc.) exceed 3,584 MB. The allocation of a 67 MB buffer triggers `SIGABRT` from `RLIMIT_DATA`.

## Why It Worked Before

The previous successful deployment (`f619ca1`, Jul 18) also crashed multiple times — Railway's `restartPolicyMaxRetries: 5` eventually produced a run that loaded successfully (likely when the HF Hub download served cached chunks faster, reducing peak memory). The current deploy exhausted all 5 retries.

## What We Changed

Only frontend code (`src/components/chat/ChatInterface.tsx`) — unrelated to this crash. The Railway Docker image is identical to the Jul 18 build except for a `BUILD BUSTER` comment in `start_railway.py` and a trailing newline in `main.py`.

## Files Involved

| File | Role |
|---|---|
| `backend/services/embedding_service.py` | `_load_encoder()` at L160 loads BGEM3FlagModel |
| `backend/app/main.py` | RLIMIT_DATA set at L43–55 from `PYTHON_MEMORY_LIMIT_MB` |
| `railway.json` | Container memory `4Gi` at L20 |
| `backend/Dockerfile.railway` | Pre-caches model at build time (L46–48) |
| `backend/start_railway.py` | ASGI wrapper, `_run_real_lifespan()` triggers container build which loads model |

## Potential Fixes (not yet attempted)

1. **Reduce RLIMIT_DATA headroom**: Set `PYTHON_MEMORY_LIMIT_MB=5120` (uses more of the 4Gi Railway limit; but Railway's hard limit is 4Gi so Python's soft limit can't exceed it — RLIMIT_DATA may be redundant here).
2. **Bump Railway memory**: Change `railway.json` → `memory: "8Gi"` (cost increase).
3. **Switch to smaller model**: Use `intfloat/multilingual-e5-small` (384-dim, ~0.5 GB) or `BAAI/bge-small-en-v1.5` (384-dim) as the primary model. Requires rebuilding the Qdrant collection (dimension change).
4. **Lazy model loading with disk offload**: Use `low_cpu_mem_usage=True` or `device_map="auto"` with CPU offload to reduce peak RAM.
5. **Remove RLIMIT_DATA entirely**: Railway's container cgroup already enforces the 4Gi hard limit; the Python `RLIMIT_DATA` of 3,584 MB adds a second, stricter fence that triggers first. Remove it and let the container OOM-killer handle overshoot.
6. **Disable bge-m3 and use the fallback chain**: The `_ensure_encoder()` fallback chain already supports `intfloat/multilingual-e5-small` (384-dim), `BAAI/bge-small-en-v1.5` (384-dim), `sentence-transformers/all-MiniLM-L6-v2` (384-dim). But Qdrant's collection is 1024-dim — a dimension mismatch makes queries fail with "Vector dimension error" (the Jul 16 incident). Fix requires either recreating the collection or changing `EMBEDDING_DIMENSION`.

## Reproduction
```bash
railway up --service askmukthiguru-8119b0e8
railway logs --service askmukthiguru-8119b0e8 <deployment-id>
```
