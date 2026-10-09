# AskMukthiGuru — AI Spiritual Guide & Knowledge Platform

> **Active release baseline — verified 2026-08-12.** The supported frontend gate is `npm run build`; source lint is expected to have zero errors; `npm audit --omit=dev` must be clean. See the [release evidence pack](docs/operations/release-evidence-pack.md) for the complete safety, documentation, and privileged-integration checklist. Historical counts elsewhere in this document are architectural context, not live service assertions.

An AI-powered spiritual guide rooted in the teachings of **Sri Preethaji & Sri Krishnaji**. Built with a 12-layer RAG pipeline, dual-level LightRAG knowledge graph, second-brain memory vault, real-time guardrails, and cross-platform native mobile & web UI.

> **Developer Navigation**:
> - **End-to-End System Architecture (HLD & LLD)**: [docs/architecture/SYSTEM_ARCHITECTURE_HLD_LLD.md](docs/architecture/SYSTEM_ARCHITECTURE_HLD_LLD.md)
> - **Architecture & Developer Guide**: [docs/DEVELOPER_GUIDE.md](docs/DEVELOPER_GUIDE.md) & [docs/COMPLETE_BACKEND_ARCHITECTURE.md](docs/COMPLETE_BACKEND_ARCHITECTURE.md)
> - **Execution Plans & Roadmap**: [docs/plans/PLAN.md](docs/plans/PLAN.md) & [docs/plans/roadmap.md](docs/plans/roadmap.md)
> - **Audit Vault & Quality Certifications**: [audits/](audits/) (`audits/findings/`, `audits/reports/`)
> - **Deployment & Ops Runbooks**: [scripts/deploy/](scripts/deploy/) & [docs/runbooks/](docs/runbooks/)
> - **Lessons Learned & Invariants**: [lessons.md](lessons.md) & [AGENTS.md](AGENTS.md)

---

## Technical Stack & Architecture

| Component | Technology | Port / Scope |
|---|---|---|
| **Frontend** | Vite React 18 + TailwindCSS + shadcn/ui + HashRouter | `80` (Docker) / `8080` (Local) |
| **Mobile App** | Capacitor 8 (`com.askmukthiguru.app`) iOS & Android | Native WebView |
| **WhatsApp Bot** | FastAPI Webhook + Meta WhatsApp Cloud API (`whatsapp_bot/`) | `8085` / Webhook |
| **Backend** | FastAPI (Async Python 3.12, 12-Layer RAG Pipeline) | `8000` |
| **Voice Synthesis** | First-Person Sacred Wisdom Engine (Sri Krishnaji / Sri Preethaji "I" Voice) | LangGraph / Adapter |
| **Vector DB** | Qdrant (`spiritual_wisdom_contextual`: 14,033 points; `second_brain_vault`) | `6333` |
| **Knowledge Graph** | Memgraph (`memgraph/memgraph-mage`, Bolt-compatible) | `7687` (Bolt) |
| **Caching & Memory** | Redis 7 Alpine (Sliding TTL session cache & response cache) | `6379` |
| **Auth & Database** | Supabase Postgres (RLS enabled) + Supabase Auth (OAuth/Email) | Cloud / Local |
| **Observability** | OpenTelemetry + Jaeger Distributed Tracing | `16686` |

---

## Core Platform Capabilities

### 1. First-Person Sacred Wisdom Synthesis
- **Authentic "I" Voice**: Answers are delivered directly in the intimate, compassionate first-person presence of **Sri Krishnaji** and **Sri Preethaji** ("I invite you to see...", "When I speak of the Beautiful State..."), eliminating detached 3rd-person clinical analysis ("According to the teachings...").
- **Speaker Attribution & Persona Discrimination**: Automatically discerns whether Sri Krishnaji or Sri Preethaji is speaking based on canonical video discourse attribution (`services/guru_brain/persona_discriminator.py`).
- **Quote Weaver & Faithfulness**: Weaves authentic verbatim excerpts into pastoral guidance without disjointed quote dumps, strictly governed by Ontological Knowledge Framework (OKF) invariants.
- **Fail-Closed Safety Rails**: Preserves reverent spiritual boundaries while instantly rerouting acute distress, self-harm, or clinical emergencies to verified helplines.

### 2. LightRAG & Knowledge Base Ingestion
- **Qdrant Vector Base (`spiritual_wisdom_contextual`)**: 14,033 points covering books, YouTube discourses, meditations, and lectures.
- **Memgraph Knowledge Graph**: 6,430+ nodes and 4,188+ relationships for dual-level entity and concept traversal.
- **Contextual Re-ingest Engine**: Reconstructs full discourses, re-chunks with contextual grounding, and populates `spiritual_wisdom_contextual`.

### 3. Second Brain Vault & Personalization Memory
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

### 4. 12-Layer RAG Pipeline
1. **Zero-Shot Input Rail**: Safety and intent guardrails via Instructor.
2. **Semantic Pre-Router**: Zero-LLM embedding-based query routing.
3. **Intent Classification**: Identifies casual, distress, meditation, or philosophical queries.
4. **Query Decomposition**: Multi-hop query splitting for complex questions.
5. **Parent-Child & Knowledge Tree Navigation**: Contextual hierarchy retrieval.
6. **Hybrid Search**: Qdrant dense vector search + LightRAG graph traversal (Memgraph).
7. **Cross-Encoder Reranking**: `bge-reranker-v2-m3` (GPU/MPS) or `mmarco-mMiniLMv2-L12-H384-v1` (CPU).
8. **CRAG Document Grading**: Filters irrelevant retrieved contexts.
9. **Guru Tone Adapter**: Adapts responses to Sri Preethaji / Sri Krishnaji voice personas.
10. **Context-Aware Generation**: Bounded conversation memory injection.
11. **Chain of Verification (CoVe)**: Verification of factual claims.
12. **Self-RAG Faithfulness & Output Rail**: Final quality gate and safety filter.

### 5. Multi-Channel Experience (Web, Mobile, WhatsApp)
- **Web App**: React 18 + TailwindCSS + shadcn/ui with interactive Obsidian-style knowledge graph (`/knowledge-graph`).
- **Native Mobile (Capacitor 8)**: iOS & Android apps (`com.askmukthiguru.app`) with native deep links and push notifications.
- **WhatsApp Assistant**: Dedicated bot (`whatsapp_bot/`) connecting users directly to spiritual wisdom on WhatsApp.

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
| `make flush-cache` | Clear Redis response/semantic/first-person caches and the Qdrant semantic cache, then restart the backend |
| `make verify-cache-empty` | Prove those caches are empty. Exit 0 = empty, 1 = something cached, 2 = Redis/Qdrant unreachable (unreachable is not empty). Add `VERIFY_CACHE_ARGS="--redis-via docker"` when Redis is password-protected and not reachable from the host |
| `bash scripts/prelaunch.sh` | Pre-launch gate against your local Docker stack; fails with named `PRELAUNCH-Exxx` errors before building |

### 2. Running Full Docker Stack

First create `backend/.env` (`cp backend/.env.example backend/.env`). Docker Compose
**refuses to start** (it prints the variable name) unless these are set to non-empty values:

| Variable | Used for |
|---|---|
| `NEO4J_PASSWORD` | Memgraph/graph database login (the name is kept for the Neo4j-compatible driver) |
| `REDIS_PASSWORD` | Redis `--requirepass`, health check and the backend `REDIS_URL` |
| `JWT_SECRET` | Backend token signing |
| `CORS_ORIGINS` | Allowed browser origins, for example `http://localhost:8080` |

Also set `SUPABASE_ANON_KEY`: it is baked into the frontend image at build time and compose
does **not** stop you if it is empty (sign-in then fails quietly). `scripts/prelaunch.sh`
checks it. `OPENROUTER_API_KEY` is needed for answers while `LLM_PROVIDER=openrouter`.
Generate secrets with `python3 -c 'import secrets; print(secrets.token_urlsafe(32))'`.

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
- **Jaeger Tracing**: [http://localhost:16686](http://localhost:16686)

### 3. Local Development Without Docker Containers

To run services locally on host machine:

```bash
# 1. Start core infrastructure containers only (Qdrant, Memgraph, Redis)
cd backend && bash ../scripts/docker-safe.sh docker compose up -d qdrant memgraph redis

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

The repository follows clean repo maintenance standards with assembled modular directories:

```
askmukthiguru/
├── audits/                        # Consolidated audit findings, reports, work, and scripts
│   ├── findings/                  # Track A-F audit findings
│   ├── releases/                  # Release verification reports & certifications
│   ├── reports/                   # Production audit reports, issues, and JSON metrics
│   ├── scripts/                   # Audit execution and report generators
│   └── work/                      # Targeted hardening logs and reviews
├── backend/                       # FastAPI Python application & RAG engine
│   ├── app/                       # Routes, config, dependencies, middleware
│   ├── rag/                       # 12-layer RAG nodes, prompts, graph strategies
│   ├── services/                  # Qdrant, Memgraph, LightRAG, Second Brain services
│   ├── scripts/ops/               # Automated maintenance & TTL cleanup scripts
│   └── tests/                     # Pytest suite (edge cases, quality gate, nodes)
├── src/                           # React 18 Frontend Application (Vite + Tailwind + shadcn)
│   ├── components/                # UI components (Chat, KG visualizer, Admin)
│   ├── pages/                     # App page views
│   └── lib/                       # API clients, backend URL resolvers
├── docs/                          # Unified Documentation Vault
│   ├── architecture/              # System architecture & DESIGN.md
│   ├── assets/                    # Screenshots and UI assets
│   ├── demo/                      # Video demonstration scripts
│   ├── handoffs/                  # Engineering handoff notes & checkpoints
│   ├── media/                     # Official launch demo video
│   ├── plans/                     # PLAN.md, PRE_LAUNCH_*, roadmap.md, tasks.md, todo.md
│   ├── releases/                  # RELEASE_CHECKLIST.md, DEPLOYMENT_SUMMARY.txt
│   ├── research/                  # Research notes & technical evaluations
│   ├── rights/                    # CONTENT-RIGHTS.md
│   ├── runbooks/                  # Operational runbooks (Benchmark, Credentials, AB Test)
│   └── wiki/                      # Complete system wiki & guides
├── evals/                         # Consolidated evaluation & benchmark suite
│   ├── benchmarks/                # ONNX analysis and validation reports
│   └── results/                   # Evaluation results and JSON structures
├── infrastructure/                # All infrastructure & orchestration specs
│   ├── cron/                      # Scheduled maintenance jobs
│   ├── grafana/ & prometheus/     # Metrics & monitoring
│   └── k8s/                       # Kubernetes manifests, Helm charts, and Minikube setup
├── memory/                        # OKF scaffolding & curated knowledge framework
├── scripts/                       # Deployment, ingestion, and operational tooling
│   ├── deploy/                    # deploy.sh, deploy_all.sh, deploy_railway.sh
│   ├── ingestion/                 # High-throughput LightRAG and corpus ingestion
│   └── ops/                       # start_local.sh, migrate_data.sh, cleanup tools
├── supabase/                      # Database migrations, RLS policies, and seed
├── tests/                         # E2E Playwright test suite
├── whatsapp_bot/                  # Meta WhatsApp Cloud API assistant service
│
│   # Root Metadata & Configs
├── AGENTS.md / CLAUDE.md / GEMINI.md  # Multi-agent directives and invariants
├── lessons.md                     # Institutional invariants & incident ledger
├── README.md / SECURITY.md / SETUP.md # Core repository guides
├── Dockerfile / frontend.Dockerfile   # Production container definitions
├── docker-compose.prod.yml / nginx.conf # Container orchestration & web server config
└── Makefile                       # Developer command orchestrator
```

---

## Environment Variables Configuration

Populate key environment variables in `backend/.env`:

| Variable | Description | Example / Default |
|---|---|---|
| `LLM_PROVIDER` | Active LLM provider (`openrouter`, `sarvam_cloud`, `ollama`) | `openrouter` (live default since 2026-09-12) |
| `OPENROUTER_API_KEY` | Key for OpenRouter inference & LightRAG graph extraction | `sk-or-v1-...` |
| `OPENROUTER_PROVIDER_SORT` | Optional server-side provider ordering (`latency`, `throughput`, or `price`); empty preserves normal OpenRouter load balancing | empty |
| `OPENROUTER_PREFERRED_MAX_LATENCY_P90` | Optional soft provider preference for p90 latency in seconds; requires provider sorting | `0` (disabled) |
| `OPENROUTER_PREFERRED_MIN_THROUGHPUT_P90` | Optional soft provider preference for p90 throughput in tokens/second; requires provider sorting | `0` (disabled) |
| `SARVAM_API_KEY` | Key for Sarvam 30B Indian multilingual LLM & STT | `sarvam-...` |
| `FORWARDED_ALLOW_IPS` | Non-wildcard proxy allowlist for Railway's `start_railway.py` (uvicorn `forwarded_allow_ips`; startup fails when missing or `*`). Not needed for docker compose (plain uvicorn). | `10.0.0.0/8` (Railway) |
| `NIM_API_KEY` | Key for Nvidia NIM API catalog (low latency) | `nvapi-...` |
| `SUPABASE_URL` | Supabase project URL | `https://your-project.supabase.co` |
| `SUPABASE_KEY` | Supabase service-role key | `eyJ...` |
| `QDRANT_URL` | Vector database endpoint | `http://localhost:6333` |
| `NEO4J_URI` | Graph store Bolt URI (Memgraph; `MEMGRAPH_URI` is the preferred alias) | `bolt://localhost:7687` |
| `REDIS_URL` | Redis cache URI | `redis://localhost:6379/0` |
| `REDIS_CACHE_MAX_KEYS` | Maximum new exact-query cache keys in the `mukthiguru:cache:*` namespace; `0` disables the ceiling | `10000` |
| `REDIS_CACHE_TELEMETRY_INTERVAL_SECONDS` | Minimum interval between namespace cardinality/TTL scans | `60` (minimum `5`) |
| `CELERY_QUEUES` | Comma-separated allowlisted queues for a worker profile; use a maintenance-only profile only after queue/SLA measurement | `ingestion,embedding,indexing,okf,memory` |
| `CELERY_CONCURRENCY` | Celery worker process concurrency, validated from `1` to `32` | `2` |
| `WEB_SEARCH_TIMEOUT_SECONDS` | Maximum time for one live-search provider call before fail-open fallback | `12` (maximum `30`) |
| `RAG_USE_HYDE` | Global hypothetical-document generation switch; adds a provider round trip on eligible complex requests | `true` (runtime-compatible default) |
| `RAG_INDIC_USE_HYDE` | Opt-in HyDE for non-English/Indic requests; keep off until held-out quality evidence justifies the added tail | `false` |
| `RAG_MAX_REWRITES` | Global CRAG rewrite retry cap | `2` (runtime-compatible default) |
| `RAG_INDIC_MAX_REWRITES` | Independent CRAG retry cap for non-English/Indic requests | `1` |
| `LATENCY_BENCHMARK_CACHE_DISABLED` | Local-only benchmark switch that bypasses all application cache reads and writes; use only when measuring uncached latency | `false` |
| `RAG_RETRIEVAL_EXPANSION_SOFT_WAIT_SECONDS` | Maximum post-primary-retrieval wait for optional LLM query expansion; slow planner work is cancelled and primary retrieval remains authoritative | `0.35` (maximum `5`) |
| `FIRST_PERSON_CHAT_BRIDGE_ENABLED` | Kill-switch for `FirstPersonBridgeStage` (verbatim first-person answers inside `/api/chat`); code default is `true`, but root `.env` sets `false` for local production until an empirically-fitted abstention gate exists (2026-09-30 audit: zero-abstention threshold served out-of-corpus queries as teacher discourse) | `false` (root `.env`) / `true` (code default) |

---

## Ephemeral chat attachments

The chat composer accepts text and office documents (`.txt`, Markdown, CSV/TSV, JSON, XML, HTML, YAML, DOCX, PPTX, XLSX), PDFs, images, audio, and video. Each selected file is sent to `POST /api/chat/upload`, where the backend applies a 10 MB per-file cap and 50 MB combined cap, extracts bounded evidence using PDF/OOXML text extraction, OCR, or local Whisper transcription, and returns an `attachment_context` value for the next chat turn. Upload bytes are not persisted or indexed automatically. The subsequent `/api/chat` or `/api/chat/stream` request carries that context separately from `user_message`; the RAG generation prompt marks it as untrusted evidence and shared caches/coalescing are bypassed or scoped by an attachment digest.

The upload path is intentionally an extraction MVP, not a corpus-ingestion shortcut. Durable indexing, page/frame citations, malware scanning, resumable uploads, and asynchronous job status remain separate production hardening work and require explicit design before enabling persistence.

## License & Author

Developed by Harshodai Kolluru. Built with AI pair-programming assistance (Anthropic Claude, Google Gemini, GitHub Copilot, and Lovable).
All rights reserved.

## Security & Release Readiness (Jul 31, 2026)

### AAL2 / MFA Step-Up
- **Frontend**: `useRequireAuth` / `useAdminGuard` call `supabase.auth.mfa.getAuthenticatorAssuranceLevel()` on every session load and redirect to `/auth/mfa` when aal2 is required. `MFAChallengePage` falls back to verified TOTP factors from the session.
- **Backend**: `require_aal2` dependency (`backend/services/auth_service.py`) + probe route `GET /api/health/mfa` (tested by `backend/tests/test_aal2_dependency.py`, 12 tests). Test auth backdoor honors `X-Test-Aal` header.

### Row-Level Security
- Migration `supabase/migrations/20260728103548_85070891-f7bf-4835-94db-4246463b3813.sql` (UPDATE `WITH CHECK`) + idempotent `20260730000000_verify_rls_with_check.sql`.
- Cross-user verification: `backend/scripts/verify_rls_policies.py` (ephemeral Alice/Bob via Admin API, 12 probes) — runs nightly against prod via `.github/workflows/nightly-rls.yml` (set repo secrets `SUPABASE_URL`/`SUPABASE_SERVICE_ROLE_KEY` first).
- E2E: `tests/e2e/rls-cross-user.spec.ts` (UI deep-link isolation + REST probe).
- Supabase dashboard (Pro): Auth → Providers → Email → **Prevent the use of leaked passwords** (HIBP); verify with `backend/scripts/verify_leaked_password_protection.py`.

### Metrics Parity (UI ↔ Backend)
- Shared contract: `backend/app/schemas/metrics.py` (pydantic) ↔ `src/lib/metricsSchema.ts` (zod), parity tested by `src/test/metricsSchema.test.ts`.
- `GET /api/metrics` (auth, RLS-scoped client, anonymous → zeroed payload) consumed by `src/hooks/useMetrics.ts` (60s TTL cache, refetch on `conversation:updated`).

### Proactive Healing Courses (Streak-Based)
- `backend/services/healing_course_service.py`: assigns a healing course only on distress streaks — ≥2 consecutive turns, ≥3-of-5 frequency, escalating severity, or same SufferingSignal ≥2× in 24h; never duplicates an active course (`user_course_progress`).
- API: `POST /api/healing-course/assign`, `POST /api/healing-course/progress`.
- UI: `src/components/chat/HealingPathCard.tsx` shows the card with dismissal and assignment.

### Langhanam Unified Guru Voice (Default-On)
- `langhanam_voice_enabled=true` by default (`backend/app/config.py`); `GURU_VOICE_MODE=prompt|adapter` selects variant; benchmark `backend/benchmarks/guru_voice_benchmark.py` gates flipping the flag at ≥4.0/5.0 (needs a live LLM run). Reference voice: `backend/services/guru_voice_langhanam.py` (Langhanam transcript excerpt).
