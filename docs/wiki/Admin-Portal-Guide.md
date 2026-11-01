# Admin Portal & Operator's Guide

The **AskMukthiGuru Admin Portal** provides administrators, spiritual content curators, and ML engineers with a unified control plane for corpus ingestion, spiritual doctrine curation (OKF), RAG execution tracing, safety observability, and system configuration.

---

## 1. Portal Architecture & Navigation

The admin interface is built as a protected single-page application within the React frontend, hosted under the `/admin` route namespace (`src/admin/`).

```text
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                   ADMIN PORTAL ARCHITECTURE                                      │
├──────────────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                                  │
│   [ Admin Shell & Topbar: AdminShell.tsx / AdminTopbar.tsx ]                                     │
│     │                                                                                            │
│     ├─► 1. Overview (/admin): KPI Telemetry, Timeseries Charts, Live Query Feed                  │
│     │                                                                                            │
│     ├─► 2. Ingestion (/admin/ingestion): Celery Jobs Queue, Speaker Attribution, Video Approval  │
│     │                                                                                            │
│     ├─► 3. Content (/admin/content): OKF Manager, Daily Teachings & Tips, Topics Matrix          │
│     │                                                                                            │
│     ├─► 4. Queries & Tracing (/admin/queries): Insight Analytics, Retrieval Waterfall, Quality   │
│     │                                                                                            │
│     ├─► 5. RAG Flow (/admin/rag-flow): Interactive ReactFlow LangGraph Pipeline Simulator        │
│     │                                                                                            │
│     └─► 6. System & RBAC (/admin/admins, /admin/settings): User Roles, Guardrails, Global Config │
│                                                                                                  │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘
```

### Safety & Crash Isolation Invariants

- **Runtime Feature Flag**: The portal is gated at runtime via `VITE_ADMIN_PORTAL_ENABLED`. In public production deployments where this is disabled, admin chunks remain unmounted and unreachable.
- **Route-Level Suspense & Error Boundaries**: Per repository pattern `P1-AI-19`, each admin child route is wrapped in an individual `<Suspense>` boundary and `<AdminErrorBoundary>`. A rendering failure in a complex chart or telemetry waterfall isolates locally and never crashes the entire admin shell.

---

## 2. Overview Telemetry (`/admin`)

The **Overview Dashboard** (`src/admin/pages/OverviewPage.tsx`) provides high-level system health metrics, real-time query throughput, and cost analytics.

### Key Performance Indicators (KPIs)

- **Active Sessions & User Queries**: Rolling 24-hour and 7-day query volumes.
- **Latency (p50 / p95 / p99)**: End-to-end response times segmented by pipeline stage (Retrieval, Rerank, Generation).
- **Faithfulness & Grounding Rate**: Percentage of answers passing factual grounding checks without hallucination.
- **Token Expenditure & Cost**: Real-time spending across LLM providers (Sarvam, OpenRouter, NIM, Anthropic).
- **Crisis Triage Volume**: Real-time count of queries preempted by the **Serene Mind** safety rail and routed to **Tele-MANAS (14416)**.

### Live Telemetry Tools

- **Timeseries Charts (`TimeseriesChart.tsx`)**: Visual trends for cache hit ratios, error rates, and token consumption.
- **Real-Time Feed (`LiveFeed.tsx`)**: Live query stream showing anonymized user intents, pipeline strategy used (`standard`, `fast`, `deep`), response latencies, and output verification scores.

---

## 3. Ingestion Staging & Review Queues (`/admin/ingestion`)

The Ingestion section coordinates data pipeline workflows across four dedicated tabs:

### 1. Ingestion Queue (`Queue` Tab / `JobsPage.tsx`)
- Displays real-time Celery background tasks running audio transcription, chunking, and embedding.
- Tracks task status (`pending`, `processing`, `succeeded`, `failed`, `retrying`).
- Enables manual job re-triggering and detailed worker trace inspection.

### 2. Speaker Attribution (`Attribution` Tab / `SpeakerAttributionPage.tsx`)
- **Voiceprint Clustering Viewer**: Displays audio windows clustered by ECAPA-TDNN acoustic embeddings.
- **Speaker Assignment**: Identifies segments spoken by Sri Preethaji, Sri Krishnaji, or dialogue guests.
- **Verification Controls**: Allows curators to promote unverified segments or flag acoustic conflicts for quarantine in `deterministic_id_collision_quarantine`.

### 3. Video Approval (`Video Approval` Tab / `VideoApprovalPage.tsx`)
- **Rights Verification**: Inspects videos against the curated rights register (`docs/rights/CONTENT-RIGHTS.md`).
- **Transcript Preview & Boundary Check**: Displays ASR output alongside YouTube video playback to verify timestamp slice alignment (`audio_start_ms`, `audio_end_ms`).
- **Release Gating**: Approves content for promotion from staging into the active serving collection.

### 4. Cache Management (`Cache` Tab / `CachePage.tsx`)
- Monitors Redis exact match cache and semantic vector cache.
- Displays cache hit rates and memory utilization per namespace.
- Provides granular invalidation controls (invalidate by video ID, doctrine term, or collection).

---

## 4. OKF Manager (`/admin/content?tab=okf`)

The **OKF Manager** (`src/admin/pages/OkfManager.tsx`) oversees the **Ontological Knowledge Framework** (`memory/okf/`), serving as the gatekeeper for spiritual doctrine.

```text
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                     OKF MANAGER INTERFACE                                        │
├──────────────────────────────────────────────────────────────────────────────────────────────────┤
│ [Active Concepts (820)]      [Review Queue (14)]        [Recompile OKF Bundle]                   │
├──────────────────────────────────────────────────────────────────────────────────────────────────┤
│ Title: Ahankara And Identification                  Type: teaching                               │
│ Teacher: Sri Preethaji & Sri Krishnaji              Status: [✓ human:editor]                     │
│ Source: https://www.youtube.com/watch?v=ehkqJ54DIC0                                              │
├──────────────────────────────────────────────────────────────────────────────────────────────────┤
│ Verbatim Excerpt:                                                                                │
│ "The second layer in this matrix of the mind is ahankara, sense of ego itself, whose primary     │
│ purpose is to identify..."                                                                       │
├──────────────────────────────────────────────────────────────────────────────────────────────────┤
│ Actions: [Edit Markdown]      [Compare to Transcript]      [Promote / Reject]                    │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘
```

### Review Queue Workflow
1. Extractor tools deposit machine-parsed concepts into `memory/okf/staging/`.
2. Content curators verify timestamp accuracy, speaker identity, and quote fidelity against the original video.
3. Once approved, the curator triggers **Recompile OKF Bundle**, invoking `compile_okf()` to regenerate `memory/okf/compiled.json`.

---

## 5. Daily Teachings & Contemplation Tips (`/admin/content?tab=teachings`)

Manages daily contemplative cards, wisdom tips, and notifications delivered to the mobile and web chat interfaces:
- **ThinkingPills Integration**: In accordance with `L-THINKING-PILLS-SACRED-TEACHING-1`, authentic sacred teachings curated here are loaded during query contemplation, elevating seekers with authentic wisdom while the pipeline synthesizes answers.
- **Language Localization**: Curates parallel translations in Hindi, Telugu, Tamil, and English.
- **Publishing Schedule**: Assigns daily release dates and holiday-specific spiritual contemplations (e.g., Ekam World Peace Festival).

---

## 6. Queries & Span Waterfall Tracing (`/admin/queries`)

The Queries view allows engineers to debug query resolution at microscopic depth:
- **Span Waterfall (`SpanWaterfall.tsx`)**: Renders millisecond-level execution spans for intent classification, Qdrant hybrid retrieval, Neo4j graph queries, cross-encoder reranking, and LLM token generation.
- **Document Grading Inspector**: Displays chunks retrieved by Qdrant alongside relevance grading decisions (`RELEVANT` vs `IRRELEVANT`) made by the Document Grader node.
- **Verification Score**: Displays hallucination and citation fidelity scores computed by the verification gate.

---

## 7. RAG Flow Simulator (`/admin/rag-flow`)

The **RAG Flow Simulator** (`src/admin/pages/RAGFlowPage.tsx`) provides an interactive ReactFlow canvas (`@xyflow/react`) mapping AskMukthiGuru's 12-layer LangGraph orchestration pipeline.

```text
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                               RAG FLOW SIMULATOR (STANDARD STRATEGY)                             │
├──────────────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                                  │
│   [ Intent Router ] ───► [ Query Rewrite ] ───► [ Hybrid Retrieval ] ───► [ Document Grader ]    │
│                                                                                   │              │
│   [ Verification Gate ] ◄─── [ Synthesis Generator ] ◄─── [ Cross-Encoder Rerank ]◄┘              │
│                                                                                                  │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘
```

### Operator Capabilities
- **Strategy Switching**: Toggle between `standard` (full multi-stage verification), `fast` (low-latency streaming), and `deep` (multi-hop graph synthesis).
- **Node Inspection**: Click any node to inspect real-time p50/p95 latency metrics, failure counts, and algorithmic parameters.
- **Live Dry-Run**: Enter custom test prompts to observe branch traversal, CRAG rewrite loops, and fallback pathways in a sandboxed execution session.

---

## 8. Security, RBAC & Configuration (`/admin/admins`, `/admin/settings`)

### Role-Based Access Control (RBAC)

The portal implements three administrative tiers managed in `AdminsPage.tsx`:

| Role | Privileges | Target Users |
|:---|:---|:---|
| **Super Admin** | Full access: User management, API key rotation, global configuration, database reindexing, and cache flushing. | Lead DevOps & Engineering Owners |
| **Curator / Reviewer** | Content approval: OKF review queue, video transcript approval, daily teaching scheduling, and quality auditing. | Monastic Editors & Content Curators |
| **Operator / Auditor** | Read-only access: Query telemetry, trace waterfall inspection, and evaluation reports. | QA Engineers & Support Team |

### Security Controls
- **Supabase Authentication**: Admin logins require multi-factor authenticated Supabase service accounts.
- **Row-Level Security (RLS)**: Enforced via `scripts/verify_rls_policies.py` ensuring admin mutations require valid JWT admin claims.
- **Audit Logging**: Every content approval, rejection, prompt update, and cache flush is written to `admin_audit_logs` with admin email, timestamp, and IP address.

---

## 9. Related Documentation & Runbooks

* [Architecture: Overview](Architecture-Overview)
* [Corpus Ingestion Architecture](Architecture-Ingestion)
* [Spiritual Teachings & OKF](Domain-Teachings-and-OKF)
* [Operations, Deployment & CI Gates](Operations-Deployment-and-CI)
* [Troubleshooting Runbooks & Diagnostics](Troubleshooting-and-Runbooks)
