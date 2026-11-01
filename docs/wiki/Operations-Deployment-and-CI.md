# Operations, Deployment & CI/CD Pipeline Gates

This document outlines the deployment topology, container orchestration, automated continuous integration (CI) gates, and operational runbooks for **AskMukthiGuru**.

---

## 1. Deployment Topology & Architecture

AskMukthiGuru operates as a resilient, multi-tiered architecture orchestrated across containerized microservices and managed cloud datastores.

```text
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                   SYSTEM DEPLOYMENT TOPOLOGY                                     │
├──────────────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                                  │
│   CLIENT & EDGE TIER:                                                                            │
│   ┌───────────────────────────────────┐    ┌───────────────────────────────────┐                 │
│   │ CDN / Cloudflare                  │    │ Frontend Single-Page App (SPA)    │                 │
│   │ SSL Termination & DDoS Protection │    │ React + Vite on Nginx / Railway   │                 │
│   └───────────────────────────────────┘    └───────────────────────────────────┘                 │
│                                              │                                                   │
│                                              ▼ HTTP REST / SSE Stream (/api/*)                   │
│   COMPUTE TIER:                                                                                  │
│   ┌───────────────────────────────────┐    ┌───────────────────────────────────┐                 │
│   │ FastAPI Backend Services          │    │ Celery Distributed Workers        │                 │
│   │ Uvicorn Multi-Worker / GKE        │◄──►│ Audio extraction, ASR, embeddings │                 │
│   └───────────────────────────────────┘    └───────────────────────────────────┘                 │
│        │                   │                   │                   │                             │
│        ▼                   ▼                   ▼                   ▼                             │
│   STATE & STORAGE TIER:                                                                          │
│   ┌──────────────────┐┌──────────────────┐┌──────────────────┐┌──────────────────┐               │
│   │ Qdrant Vector DB ││ Neo4j Knowledge  ││ Redis In-Memory  ││ Supabase Postgres│               │
│   │ Port 6333 / 6334 ││ Port 7474 / 7687 ││ Port 6379        ││ RLS, Auth, Users │               │
│   │ HNSW / Int8      ││ LightRAG / OKF   ││ Cache & Broker   ││ Telemetry Ledger │               │
│   └──────────────────┘└──────────────────┘└──────────────────┘└──────────────────┘               │
│                                                                                                  │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘
```

### Environment Configurations

1. **Local Development & Staging (Docker Compose)**:
   - Primary definition: `docker-compose.yml` (repo root) and `backend/docker-compose.yml`.
   - Starts API, Celery worker, local Qdrant, Redis, and mock storage containers.
   - **Script Tree Mount Invariant (X1, X2, X28)**:
     - The repository maintains reconciled script trees between `scripts/` and `backend/scripts/`.
     - `backend/docker-compose.yml` mounts repo-root `scripts/` at `/app/scripts`.
     - Container operational scripts run safely via `bash scripts/docker-safe.sh docker compose ...`.

2. **Cloud Deployment (Railway / Cloud Run / Kubernetes)**:
   - **Backend API**: Scaled horizontally based on incoming HTTP request volume and p95 turn latency.
   - **Celery Workers**: Scaled independently to handle asynchronous batch ingestion tasks without degrading interactive chat responsiveness.
   - **Health & Readiness Endpoints**:
     - `GET /health`: Liveness probe ensuring the FastAPI event loop is responsive.
     - `GET /ready`: Readiness probe verifying active connections to Supabase, Qdrant, and Redis.

---

## 2. CI/CD Pipeline Gates

Every pull request and merge to the `main` branch must clear strict automated validation pipelines defined in `.github/workflows/`. A failure in any hard gate immediately halts deployment.

```text
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                GITHUB ACTIONS AUTOMATED CI GATES                                 │
├──────────────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                                  │
│   Git Push / Pull Request ─────────────────────────────────────────────────────────────┐         │
│     │                                                                                  │         │
│     ├─► 1. Frontend Pipeline: ESLint, TypeScript Strict, Vitest, npm audit, build      │         │
│     │                                                                                  │         │
│     ├─► 2. Backend Static Checks: compileall -q, git diff --check, secret scan         │         │
│     │                                                                                  │         │
│     ├─► 3. Production Contract Verification: inspect_runtime_artifacts, Qdrant baseline│         │
│     │                                                                                  │         │
│     ├─► 4. Security Audit & CodeQL: Bandit (-ll), pip-audit, GitHub CodeQL AST         │         │
│     │                                                                                  │         │
│     ├─► 5. Quality Evaluation Gates: Golden-25 Attribution, RAGAS Faithfulness (≥0.60) │         │
│     │                                                                                  │         │
│     └─► 6. Nightly RLS Security Gates: scripts/verify_rls_policies.py (Zero Bypasses)  │         │
│                                                                                        │         │
│   All Gates Evaluated ─────────────────────────────────────────────────────────────────┘         │
│     │                                                                                            │
│     ├─── ALL CHECKS PASSED ──► Promote to Staging / Production Release                           │
│     └─── ANY FAILURE ────────► Hard Block / Build Halted / P0 Alert Dispatched                   │
│                                                                                                  │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘
```

### Detailed Pipeline Breakdown

### 1. Main Hard Gates (`.github/workflows/main-hard-gates.yml`)

The primary pre-merge gate consisting of four concurrent jobs:

- **`frontend` Job**:
  - `npm run lint`: Enforces ESLint rules and TypeScript strict mode.
  - `npm run typecheck`: Validates full React type safety without implicit `any`.
  - `npm test -- --run`: Executes complete Vitest unit and component test suites.
  - `npm run build`: Validates asset bundling and tree-shaking cleanliness.
  - `npm audit --omit=dev --audit-level=high`: Blocks builds with high or critical npm vulnerabilities.

- **`backend-static` Job**:
  - `python -m compileall -q backend`: Compiles all Python modules to catch syntax errors or invalid imports across Python 3.12.
  - `git diff --check`: Disallows trailing whitespace and git conflict markers.
  - `python scripts/security_audit.py --report`: Rejects accidental commits of API keys, private certificates, or development tokens.

- **`repository-production-contract` Job**:
  - Validates critical source paths (`backend/app/config.py`, `backend/app/chat_uploads.py`, `docs/production/PRODUCTION_READINESS.md`).
  - **Qdrant Baseline Non-Degeneracy Check**: Verifies `memory/qdrant_quality_baseline.json`. Ensures baseline `mean_ndcg > 0.0`. A baseline with zero discriminative capability fails the build immediately.
  - **Runtime Artifacts Integrity**: Executes `inspect_runtime_artifacts()`, asserting that all required runtime files exist and pass integrity checks.

- **`load-evidence-policy` Job**:
  - Enforces that nightly load workflows cannot pass vacuously when services are unreachable. Validates that `ALLOW_UNREACHABLE_SUCCESS` hard-fails builds that lack real execution evidence.

---

### 2. Security Audits & CodeQL (`security-audit.yml`, `codeql.yml`)

- **Dependency Vulnerability Scanning**: Runs `pip-audit` against `backend/requirements.txt` and `requirements.lock`.
- **AST Security Linter**: Runs `bandit -ll --ini backend/.bandit` to identify security antipatterns (e.g., hardcoded bind addresses, insecure hashing, dangerous shell invocations).
- **GitHub CodeQL**: Deep semantic code analysis scanning for data leakage, path traversals, and injection risks.
- **CSP Security Check**: Enforces `L-CI-CSP-SECURITY-GATE-1` ensuring no loopback IP addresses (`127.0.0.1`, `localhost`) exist in production Nginx headers.

---

### 3. Evaluation & Golden Question Gates (`eval-gate.yml`, `golden25-gate.yml`)

- **Retrieval Regression Gate**: Evaluates search quality against curated benchmark queries. If mean nDCG drops by more than $0.02$ compared to baseline, the gate blocks promotion.
- **RAGAS Evaluation Gate**: Assesses RAG output along three dimensions:
  - **Faithfulness**: Are all claims grounded in the retrieved teaching excerpts? (Fails if mean faithfulness $< 0.60$).
  - **Answer Relevance**: Does the generated answer directly address the seeker's query?
  - **Hallucination Anomaly Detection**: Unattributed philosophical claims trigger automated PR rejection.

---

### 4. Nightly Row-Level Security Gate (`nightly-rls.yml`)

- Executes `scripts/verify_rls_policies.py` against a staging Supabase instance.
- **Security Probing**: Simulates anonymous (`anon`) and authenticated user tokens attempting unauthorized SELECT/INSERT/DELETE queries on protected tables (`corpus_gate_rejections`, `canonical_memories`, `admin_audit_logs`).
- Any permission bypass causes an immediate P0 notification to on-call engineers.

---

## 3. Operational Procedures

Detailed step-by-step procedures are documented in [Troubleshooting and Runbooks](Troubleshooting-and-Runbooks):
- **Zero-Downtime Qdrant Reindexing**: Versioned collection builds and atomic alias promotion.
- **YouTube Embed Error 153 Resolution**: Referrer policy and origin encoding fixes.
- **Cross-User RLS Policy Verification**: Multi-user isolation verification.
- **Docker Safe Execution**: Bypassing macOS keychain credential helper hangs.
- **Celery AsyncTask Event Loop Collision**: Resolving nested event loop crashes.
- **Neo4j / Memgraph Backup & Restore**: Bolt-based migration and cross-tree layout checks.

---

## 4. Monitoring, Alerting & On-Call Triage

Configured thresholds for PagerDuty and Slack alerts:
- **P0**: Chat endpoint error rate $> 2\%$ over a 5-minute rolling window.
- **P0**: Failure or bypass of the **Serene Mind** crisis triage stage.
- **P1**: p95 turn latency $> 2500$ ms for 10 consecutive minutes.
- **P1**: Qdrant vector retrieval timeouts or connection drops.
- **P2**: Ingestion worker queue lag $> 500$ pending jobs.

---

## 5. Related Documentation

* [System Architecture Overview](Architecture-Overview)
* [Corpus Ingestion Pipeline](Architecture-Ingestion)
* [Admin Portal Guide](Admin-Portal-Guide)
* [Quality Benchmarks & Evaluation](Quality-Evaluation-and-Benchmarks)
* [Troubleshooting Runbooks & Diagnostics](Troubleshooting-and-Runbooks)
