# AskMukthiGuru — AI Spiritual Guide & Knowledge Platform

[![Backend Health](https://img.shields.io/endpoint?url=https%3A%2F%2Ffynkjimvuimakgtidvuq.supabase.co%2Ffunctions%2Fv1%2Fhealthz%3Fformat%3Dshield)](http://localhost:8000/api/healthz)

An AI-powered spiritual guide rooted in the teachings of **Sri Preethaji & Sri Krishnaji**. Built with a 12-layer RAG pipeline, dual-level LightRAG knowledge graph, second-brain memory vault, real-time guardrails, and cross-platform native mobile & web UI.

> **Developer Navigation**:
> - **Architecture & Developer Guide**: [docs/DEVELOPER_GUIDE.md](docs/DEVELOPER_GUIDE.md) & [docs/COMPLETE_BACKEND_ARCHITECTURE.md](docs/COMPLETE_BACKEND_ARCHITECTURE.md)
> - **Prioritized Backlog & System Status**: [docs/ROADMAP.md](docs/ROADMAP.md)
> - **Operational Runbooks**: [docs/runbooks/](docs/runbooks/) (`BENCHMARK_RUNBOOK.md`, `CREDENTIALS_GUIDE.md`, `STREAM_PROTOCOL.md`)
> - **Lessons Learned & Invariants**: [lessons.md](lessons.md) & [AGENTS.md](AGENTS.md)

---

## Technical Stack & Architecture

| Component | Technology | Port / Scope |
|---|---|---|
| **Frontend** | Vite React 18 + TailwindCSS + shadcn/ui + HashRouter | `80` (Docker) / `8080` (Local) |
| **Mobile App** | Capacitor 8 (`com.askmukthiguru.app`) iOS & Android | Native WebView |
| **Backend** | FastAPI (Async Python 3.12, 12-Layer RAG Pipeline) | `8000` |
| **Vector DB** | Qdrant (`spiritual_wisdom`: 89,053 points, `second_brain_vault`) | `6333` |
| **Knowledge Graph** | Neo4j 5.17 (LightRAG 7,601 concept & transformation arc nodes) | `7474` (HTTP) / `7687` (Bolt) |
| **Caching & Memory** | Redis 7 Alpine (Sliding TTL session cache & response cache) | `6379` |
| **Auth & Database** | Supabase Postgres (RLS enabled) + Supabase Auth (OAuth/Email) | Cloud / Local |
| **Observability** | OpenTelemetry + Jaeger Distributed Tracing | `16686` |

---

## Core Platform Capabilities

### 1. LightRAG & Knowledge Base Ingestion
- **Qdrant Vector Base (`spiritual_wisdom`)**: Ingested 89,053 items covering books, 450+ YouTube discourses, meditations, and lectures.
- **Neo4j Knowledge Graph**: 7,601 nodes (7,498 base concept nodes + 103 OKF 5-node transformation arc nodes).
- **High-Throughput Auto-Scaling Ingestion**: `scripts/ingest_lightrag_data.py` directly scrolls Qdrant payloads with `asyncio` worker pools, fast LLM timeouts, and atomic `.tmp` -> `.json` checkpointing (`data/lightrag_checkpoint.json`).
- **Contextual Re-ingest Engine**: Reconstructs full documents, re-chunks with contextual grounding, and populates `spiritual_wisdom_contextual`.

### 2. Second Brain Vault & Personalization Memory
- **Second Brain Vault (`second_brain_vault`)**: Multi-tenant collection in Qdrant indexed with `user_id` keyword filters. User notes live encrypted in Postgres (`user_brain_nodes`), vectors in Qdrant.
- **User Familiarity Classification**: `classify_user_familiarity` dynamically adapts response tone across 3 tiers:
  - **Seeker**: Clear, accessible explanations of Sanskrit and spiritual terms.
  - **Practitioner**: Balanced guidance focusing on meditation techniques and internal state shift.
  - **Advanced Meditator**: Deep philosophical terms and neurobiological insights.
- **3-Tier Memory Retention & Automated Cleanup**:
  - *Tier 1 (Ephemeral)*: Redis 15-minute sliding TTL (`EPHEMERAL_TTL = 900`).
  - *Tier 2 (Transient)*: 90-day retention for chat logs and query telemetry.
  - *Tier 3 (User Core Vault)*: Protected user core memory. Inactive accounts (>365 days) automatically purged via `scripts/ops/cleanup_inactive_user_data.py`.
- **GDPR Privacy Controls**: Full user control via `DELETE /api/memory/reflections` and `POST /api/memory/forget`.

### 3. 12-Layer RAG Pipeline
1. **Zero-Shot Input Rail**: Safety and intent guardrails via Instructor.
2. **Semantic Pre-Router**: Zero-LLM embedding-based query routing.
3. **Intent Classification**: Identifies casual, distress, meditation, or philosophical queries.
4. **Query Decomposition**: Multi-hop query splitting for complex questions.
5. **Parent-Child & Knowledge Tree Navigation**: Contextual hierarchy retrieval.
6. **Hybrid Search**: Qdrant dense vector search + LightRAG Neo4j graph traversal.
7. **Cross-Encoder Reranking**: `bge-reranker-v2-m3` (GPU/MPS) or `mmarco-mMiniLMv2-L12-H384-v1` (CPU).
8. **CRAG Document Grading**: Filters irrelevant retrieved contexts.
9. **Guru Tone Adapter**: Adapts responses to Sri Preethaji / Sri Krishnaji voice personas.
10. **Context-Aware Generation**: Bounded conversation memory injection.
11. **Chain of Verification (CoVe)**: Verification of factual claims.
12. **Self-RAG Faithfulness & Output Rail**: Final quality gate and safety filter.

### 4. Interactive Obsidian-Style Knowledge Graph
- Accessible on `/knowledge-graph` for all visitors.
- Features force-directed 2D/3D graph visualization with glow effects, node dragging, zoom, and live search.
- Includes automatic fallback to cached demo data if graph backend is cold.

### 5. Native Mobile Experience (Capacitor 8)
- Single codebase targeting Web, iOS, and Android (`com.askmukthiguru.app`).
- Uses `HashRouter` inside Capacitor WebView (`https://localhost/`) for seamless client-side routing.
- Integrated Push Notifications (`@capacitor/push-notifications` -> FCM & APNs).
- Google & Apple OAuth native deep link handling (`com.askmukthiguru.app://auth-callback`).

---

## Quickstart & Local Development

### 1. Makefile Commands (Recommended)

| Command | Description |
|---|---|
| `make dev` | Start local backend (`start_local.sh`) and frontend dev servers |
| `make test` | Run backend unit and integration test suite |
| `make lint` | Run Ruff linter on backend |
| `make format` | Format code with Ruff |
| `make docker-up` | Build and start full Docker stack |
| `make docker-rebuild-web` | Rebuild and restart stateless frontend & backend services |
| `make docker-down` | Stop all running Docker services |
| `make flush-cache` | Clear Redis response cache and semantic caches |

### 2. Running Full Docker Stack

Ensure Docker Desktop is running on macOS, then execute:

```bash
# Set Docker binary PATH and run docker compose via safe script (bypasses keychain issues)
cd backend && bash ../scripts/docker-safe.sh docker compose up -d --build
```

Access local endpoints:
- **Main Web Application**: [http://localhost](http://localhost)
- **Admin Dashboard**: [http://localhost/admin](http://localhost/admin)
- **Knowledge Graph UI**: [http://localhost/knowledge-graph](http://localhost/knowledge-graph)
- **FastAPI Backend Health**: [http://localhost:8000/api/health](http://localhost:8000/api/health)
- **Neo4j Browser**: [http://localhost:7474](http://localhost:7474)
- **Jaeger Tracing**: [http://localhost:16686](http://localhost:16686)

### 3. Local Development Without Docker Containers

To run services locally on host machine:

```bash
# 1. Start core infrastructure containers only (Qdrant, Neo4j, Redis)
cd backend && bash ../scripts/docker-safe.sh docker compose up -d qdrant neo4j redis

# 2. Run backend FastAPI server (in terminal 1)
cd backend
.venv/bin/uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# 3. Run frontend Vite server (in terminal 2)
npm install
npm run dev
```

*Note: `backend/app/config.py` automatically normalizes container hostnames (`http://qdrant:6333` -> `http://localhost:6333`) when executing directly on host Python outside Docker.*

---

## Data Ingestion & Maintenance Runbook

### Running LightRAG Batch Ingestion
To resume or execute full LightRAG knowledge graph ingestion directly from Qdrant:

```bash
CONCURRENCY_WORKERS=8 backend/.venv/bin/python scripts/ingest_lightrag_data.py
```

- Progress is stored atomically in `data/lightrag_checkpoint.json`.
- Logs stream to stdout and append to `data/lightrag_ingestion.log`.

### Automated Inactive User Memory Cleanup
To purge inactive user data (>365 days inactive):

```bash
backend/.venv/bin/python backend/scripts/ops/cleanup_inactive_user_data.py --days 365
```

---

## Directory & Repository Structure

```
askmukthiguru/
├── backend/                       # FastAPI Python application
│   ├── app/                       # Routes, config, dependencies, middleware
│   ├── rag/                       # 12-layer RAG nodes, prompts, graph strategies
│   ├── services/                  # Qdrant, Neo4j, LightRAG, Second Brain services
│   ├── scripts/ops/               # Automated maintenance & TTL cleanup scripts
│   └── tests/                     # Pytest suite (edge cases, quality gate, nodes)
├── src/                           # React 18 Frontend Application
│   ├── components/                # UI components (Chat, KG visualizer, Admin)
│   ├── pages/                     # App page views
│   └── lib/                       # API clients, backend URL resolvers
├── docs/                          # Comprehensive Documentation
│   ├── runbooks/                  # Operational runbooks (Benchmark, Credentials, AB Test)
│   ├── archive/                   # Historical audit reports & completed plans
│   ├── COMPLETE_BACKEND_ARCHITECTURE.md
│   ├── DEVELOPER_GUIDE.md
│   └── ROADMAP.md
├── scripts/                       # High-level data ingestion & eval scripts
│   └── ingest_lightrag_data.py   # High-throughput LightRAG Qdrant scroll script
├── handoff.md                     # Latest session status & operational handoff
├── lessons.md                     # Lessons learned & architectural invariants
└── Makefile                       # Developer command orchestrator
```

---

## Environment Variables Configuration

Populate key environment variables in `backend/.env`:

| Variable | Description | Example / Default |
|---|---|---|
| `LLM_PROVIDER` | Active LLM provider (`sarvam_cloud`, `openrouter`, `nim`, `ollama`) | `nim` / `sarvam_cloud` |
| `OPENROUTER_API_KEY` | Key for OpenRouter inference & LightRAG graph extraction | `sk-or-v1-...` |
| `SARVAM_API_KEY` | Key for Sarvam 30B Indian multilingual LLM & STT | `sarvam-...` |
| `NIM_API_KEY` | Key for Nvidia NIM API catalog (low latency) | `nvapi-...` |
| `SUPABASE_URL` | Supabase project URL | `https://your-project.supabase.co` |
| `SUPABASE_KEY` | Supabase service-role key | `eyJ...` |
| `QDRANT_URL` | Vector database endpoint | `http://localhost:6333` |
| `NEO4J_URI` | Neo4j Bolt protocol URI | `bolt://localhost:7687` |
| `REDIS_URL` | Redis cache URI | `redis://localhost:6379/0` |

---

## License & Author

Developed by Google DeepMind team pair-programmed with AskMukthiGuru engineering. All rights reserved.
