# Railway production status and cost controls (2026-09-20)

Status: reference (content dated, moved verbatim, not re-verified). Owner: project owner. Last verified: not re-verified as of 2026-10-22.

Moved verbatim from `backend/CLAUDE.md` (token-optimizer pass, 2026-10-22). Railway stays scaled down until the owner says otherwise.

## Railway Production & Cost Controls (Sep 20, 2026)

- **Status**: **ALL SERVICES SCALED DOWN / OFFLINE (Compute cost = $0/hour)** via `railway down --service <name> --yes` on `askmukthiguru-8119b0e8`, `memgraph`, and `qdrant`. Managed `Redis` is `● Sleeping`.
- **Data Volumes**: Intact and ready (`qdrant-volume`, `memgraph-volume`, `redis-volume`).
- **Memory Footprint When Running**: Active backend memory is **~1.81 GB RAM** (loads ONNX BGE-M3 560MB, ONNX Reranker 570MB, ModernBERT LettuceDetect 350MB, MiniLM 90MB, Python/LangGraph 250MB). Combined with Qdrant (~1.33 GB) and Memgraph (~0.57 GB / 570.6 MiB / 1 GiB limit), baseline active RAM is ~3.72 GB (~$37-$42/month at Railway's $10/GB/month pricing).
- **How to Spin Up Services (When Ready)**:
  1. Databases:
     ```bash
     railway redeploy --service qdrant
     railway redeploy --service memgraph
     # Redis wakes up automatically upon receiving connections
     ```
  2. Backend:
     ```bash
     railway up
     # OR: railway redeploy --service askmukthiguru-8119b0e8
     ```
- **Next Steps**:
  1. Frontend request throttling: prevent `/api/capabilities` and `/api/metrics` from continuously waking Railway when testing.
  2. Run batch benchmarks (`benchmarks/RUN_ME.sh` or `evaluation/bench.py`) locally or against temporary redeploy.
- **Mandatory Railway Env Vars**: `FORWARDED_ALLOW_IPS=10.0.0.0/8` (startup fail-closed guard) and `PYTHON_MEMORY_LIMIT_MB=0` (disables virtual RLIMIT_DATA cap to prevent thread allocation failure and OOM during ONNX model cold load).
