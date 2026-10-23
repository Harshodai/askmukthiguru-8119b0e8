# Core-Safe Program Board
**Maintained by:** Orchestrator
**Last Updated:** 2026-10-20

## 1. Node Status Matrix

| Node | Name | Status | Dependencies | Path Allowlist | Evidence Path |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **G0** | Truth and Baseline | `IN_PROGRESS` | None | `audits/evidence/G0/`, `docs/plans/`, `roadmap.md`, `README.md`, `audits/evidence/feature_list.json`, `audits/evidence/progress.md`, `docs/ROADMAP.md` | `audits/evidence/G0/` |
| **H0** | Harness Charter & Assumptions | `TODO` | G0 | `docs/plans/harness-assumptions.md` | `audits/evidence/H0/` |
| **H1** | Build Harness & Evaluator | `TODO` | G0, H0 | `scripts/guards/`, `audits/evidence/` | `audits/evidence/H1/` |
| **G1** | Core Contract Pack (P1–P5) | `TODO` | G0, H1 | `backend/tests/`, `scripts/guards/` | `audits/evidence/G1/` |
| **H2** | Eval Harness | `TODO` | G0, G1, H0 | `evals/`, `backend/evaluation/` | `audits/evidence/H2/` |
| **H3** | Runtime Context & Injection Defence | `TODO` | G1, G4 | `backend/services/first_person/`, `backend/rag/` | `audits/evidence/H3/` |
| **H4** | Tracing & Replay | `TODO` | G1 | `backend/app/telemetry/`, `scripts/ops/` | `audits/evidence/H4/` |
| **G2** | Safety Net & Rollback | `TODO` | G1 | `scripts/ops/`, `backend/scripts/ops/` | `audits/evidence/G2/` |
| **G3** | Watchdog & External Monitor | `TODO` | G2, H4 | `scripts/ops/watchdog/` | `audits/evidence/G3/` |
| **G4** | Latency Profiling & Parity | `TODO` | G1, H2 | `backend/rag/`, `backend/services/` | `audits/evidence/G4/` |
| **G5** | Teacher Registry | `TODO` | G1 | `backend/config/teachers.yaml`, `backend/services/` | `audits/evidence/G5/` |
| **G6** | Data Quality & Boundary Polish | `TODO` | G0 | `backend/ingest/verbatim/`, `scripts/ingestion/` | `audits/evidence/G6/` |
| **G7** | Auto-Memory (Consented & Sandboxed) | `TODO` | G1 | `backend/services/memory/`, `backend/services/memory_service_v2.py` | `audits/evidence/G7/` |
| **G8** | Graph as Clip Index (Ablation) | `TODO` | G1, H3 | `backend/rag/nodes/atomic_graphrag.py` | `audits/evidence/G8/` |
| **G9** | Calibration & Conformal Bounds | `BLOCKED_HUMAN` | G6 | `backend/evaluation/gold/` | `audits/evidence/G9/` |
| **G10** | Profile-First UI & Journey | `TODO` | G1 | `src/pages/`, `src/components/`, `src/test/` | `audits/evidence/G10/` |
| **H5** | Feature-by-Feature Rules | `TODO` | H2, H3, H4, G5, G7, G8 | `backend/`, `src/` | `audits/evidence/H5/` |
| **G11** | Live Docker Verification & Query Report | `TODO` | G3, G4, G5, G7, G8, G10, H5 | `audits/evidence/G11/` | `audits/evidence/G11/` |
| **G12** | Program Closure & Docs Finalization | `TODO` | G11 | `docs/`, `CLAUDE.md`, `lessons.md` | `audits/evidence/G12/` |

---

## 2. Invariant Gates (The 5 Core Promises)
- **P1 Safety:** Offline non-LLM crisis response. Tele-MANAS before 112.
- **P2 Truth:** Teacher answers are exact recorded words (`model_used=None`). OKF/KG never cited as speech.
- **P3 Integrity:** `sha256(verbatim_text) == transcript_hash`, speaker allowlist, clean boundaries.
- **P4 Privacy:** No user ID in cache keys. Zero cross-tenant/cross-user leak.
- **P5 Availability:** Graceful degrade on store or service outage (Redis, Memgraph, Qdrant, LLM).
