# Architecture: Frontier AI Product Harness & Data Source Wirings

A production-grade architectural specification for **AskMukthiGuru**, synthesizing engineering paradigms from frontier AI companies (**Anthropic**, **Perplexity**, **Glean**, **Cursor**, **Cohere**) with strict domain safety and data-plane invariants.

---

## 1. Stack

Every layer is chosen for deterministic reproducibility, strict provenance verification, fail-closed safety, and low operational overhead:

| Layer | Choice | Why | Swap For |
|---|---|---|---|
| **Web & Client Application** | Next.js 14+ (App Router) + TypeScript + Tailwind CSS | Fast SSR/streaming, zero-layout-shift audio timestamp player, deterministic hydration. | Remix, SvelteKit |
| **API & Serving Engine** | FastAPI + Python 3.12 (Pydantic v2 + AsyncIO) | High throughput, strict typing, native integration with vector/ML pipelines, low latency async pipeline execution. | Go, Rust (Actix) |
| **Relational Database** | PostgreSQL 16 (on Neon or Supabase) | ACID compliance for source releases, rights registries, rejection ledgers, and evaluation manifests. Row-Level Security (RLS) built-in. | AWS RDS Postgres |
| **Vector Database** | Qdrant (v1.9+) | Native hybrid search (dense BGE-M3 1024-d + sparse lexical/SPLADE), scalar int8 quantization with oversampling, deterministic payload indexing, zero-downtime atomic collection alias swaps. | Milvus, Pinecone |
| **Graph Database** | Neo4j / Memgraph | High-speed 1-to-2 hop ontology traversals for doctrine concepts and discourse parent lineage in a single query roundtrip. | AWS Neptune |
| **Caching & Rate Limiting** | Redis 7+ | Token-bucket rate limiting (Lua scripts), cryptographic exact-cache storage with 24 h TTL. | DragonflyDB |
| **Embedding & Encoders** | `BAAI/bge-m3` (Pinned revision) | Multi-lingual, dual-output (dense 1024-d vectors + sparse lexical weights) eliminating dual-model drift. | Cohere Embed v3 |
| **Reranker Stack** | `BAAI/bge-reranker-v2-m3` (Cross-Encoder) + ONNX runtime | High-precision cross-attention scoring over top-k candidate chunks, sub-50ms execution on CPU. | Cohere Rerank v3 |
| **Audio & Speech Pipeline** | Dual ASR (Whisper v3 + Parakeet CTC) + ECAPA-TDNN | Sub-millisecond word alignment, speaker diarization, voiceprint cosine verification against human anchor moments. | PyAnnote Audio |
| **Background Orchestration** | Celery / Inngest with Redis broker | Idempotent multi-modal ingestion jobs, automated Qdrant snapshotting, periodic corpus drift validation. | Temporal, Dagster |
| **Hosting & Cloud Infra** | Docker Compose on Railway / Fly.io | Predictable networking, bind-mount isolation, declarative container scaling, production parity with local dev. | AWS ECS / EKS |

---

## 2. Serving Harness Architecture & Execution Graph

The serving harness coordinates inbound inquiries through an immutable, ordered sequence of stages.

### 2.1 The Pipeline Stage Chain

Order guarantees that **kill switches**, **rate limits**, **deterministic safety**, and **acute distress checks** execute *before* any cache lookups or third-party LLM calls:

```
[Inbound Request]
       │
       ▼
[01. KillSwitchStage] ──(Tripped?)──► [Return 503 System Suspended]
       │
       ▼
[02. CacheCheckStage] ──(Exact Cache Hit?)──► [Verify 6-Factor Hash] ──► [Return Cached Payload]
       │ (Miss)
       ▼
[03. RequestStateStage] ──► [Resolve TenantContext & Peer IP]
       │
       ▼
[04. InputGuardrailStage] ──(Injection/Malicious?)──► [Return 400 Safety Refusal]
       │
       ▼
[05. DistressStage] ──(Acute Self-Harm / Distress?)──► [Trigger Crisis Intervention Rail]
       │
       ▼
[06. CircuitBreakerStage] ──(Provider Outage?)──► [Degrade to Fail-Closed Offline Cache]
       │
       ▼
[07. DoctrineCacheStage] ──(Canonical Teaching?)──► [Serve Curated Doctrine Directly]
       │
       ▼
[08. SemanticRouterStage]
       │
       ├─────────────────────────────────┐
       ▼                                 ▼
 [First-Person Lane]             [General RAG Lane]
       │                                 │
       ▼                                 ▼
[Hybrid Search: Dense + Sparse + Graph Prefetch Channel]
       │
       ▼
[Cross-Encoder Reranker & MMR Diversity Deduplication]
       │
       ▼
[Verbatim Evidence Gate] ──(Unverified Speaker?)──► [Fallback to Channel Attribution]
       │
       ▼
[Parent Window Context Enrichment]
       │
       ▼
[OutputGuardrailStage] ──(Hallucination / Leakage?)──► [Enforce Verbatim Redaction]
       │
       ▼
[MemoryStage & CacheUpdateStage] ──► [Store 6-Factor Fingerprint in Redis]
       │
       ▼
[ResultAssemblyStage] ──► [Serve Response Payload]
```

### 2.2 Invariant Guarantees & Gate Policies

1. **Answer Text is Evidence, Directness is Metadata (Invariant Oct 27, 2026):**
   - The response `answer` / `teaching` body contains strictly verbatim quotes in source order plus permitted speaker attribution.
   - Whether a quote directly answers the inquiry or is merely topical is carried entirely in structured metadata: `status="weak_match"`, `is_direct_answer=False`, and `verification["direct"]=False`.
   - Never prepend editorial headers (e.g. "Related, not a direct answer") into the quote body.
2. **Cryptographic Exact Cache Fingerprinting (Invariant X13):**
   - The exact cache key is not just the query text. It is a SHA-256 hash computed over 6 cryptographic dimensions:
     ```
     cache_key = sha256(
         query_normalized +
         prompt_template_sha256 +
         model_revision +
         collection_version +
         rights_register_sha256 +
         serving_policy_fingerprint
     )
     ```
   - Changing any underlying model, prompt, or rights document immediately invalidates stale cache entries without requiring a dangerous global cache purge.
3. **Transport Jitter vs. Congestion Retry (Invariant Oct 27, 2026):**
   - Relevance scorer network calls are retried at most **once**, and *only* if the initial failure was fast (< 50% of `FIRST_PERSON_RELEVANCE_TIMEOUT_S`). Fast drops represent transient network jitter; timeout exhaustion represents upstream congestion where retrying would double latency.
   - If retries fail, the turn fails closed to `abstain_reason="relevance_indeterminate"`.
4. **Master Posture: Retrieval-Only Default (Invariant X24):**
   - Production operates strictly in `FIRST_PERSON_MODE=retrieval_only`.
   - LLM generation of spiritual teachings is strictly prohibited. Synthetic prose may only be used for structural glue (formatting citations, conversational greetings outside doctrine).

---

## 3. Data Source Wirings & Multi-Modal Ingestion Plane

The data plane ingests diverse spiritual media into immutable, verifiable vector and graph representations.

### 3.1 Multi-Modal Ingestion Pipeline

```
[Raw Sources: YouTube Videos, Transcribed Discourses, Scanned Texts]
                         │
                         ▼
           [Source Provenance Ingestion]
            - Recorded in public.source_releases
            - Content SHA-256 Checksum Computed
                         │
                         ▼
           [Pre-Ingest Rights Validation Gate]
            ├─ Licensed ──► Proceed to Extraction
            └─ Unverified/Revoked ──► Quarantine in public.corpus_gate_rejections
                         │
                         ▼
      ┌──────────────────┴──────────────────┐
      ▼                                     ▼
[Audio / Video Stream]               [Text / Discourse Stream]
      │                                     │
      ├─ Dual ASR Processing:               ├─ Layout Analysis & OCR
      │  ├─ Whisper v3 (Large)              ├─ Verse & Boundary Snapping
      │  └─ Parakeet CTC (Fast check)       ├─ Adaptive Chunking (adaptive_v1)
      ├─ Word-Level Timestamp Alignment     └─ Hierarchical Summary (RAPTOR)
      ├─ ECAPA-TDNN Diarization
      └─ Voiceprint Verification
         (Cosine vs Anchor Moments >= 0.75)
                         │
                         ▼
           [Deterministic Point Generation]
            - point_id = uuid5(NAMESPACE_URL, f"{url}:{idx}:{sha256}")
            - parent_id = uuid5(NAMESPACE_URL, f"{url}:{parent_sha256}")
            - chunker_version = "boundary_v1:target_1200"
                         │
                         ▼
           [Dual-Lane Embedding & Graph Indexing]
            ├─ Dense Vector: BAAI/bge-m3 (1024-dim, scalar int8)
            ├─ Sparse Vector: Lexical / SPLADE tokens
            └─ Graph Nodes: Neo4j spiritual concept relationships
                         │
                         ▼
           [Staging Collection: corpus_vN_staging]
                         │
                         ▼
           [Offline Validation & Gate Checks]
            - Optimizer health == 1
            - Drift points == 0
            - 100% Evaluation Suite Execution
                         │
                         ▼
           [Atomic Alias Cutover (Zero Downtime)]
            qdrant.update_collection_aliases([
                CreateAlias(collection="corpus_vN", alias="production_corpus"),
                DeleteAlias(alias="production_corpus", collection="corpus_v{N-1}")
            ])
```

### 3.2 Data Plane Invariants (Invariant X40 & X41)

1. **Register → Stamp → Filter → Enforce:**
   - Rights status originates solely from the curated rights register (`docs/rights/CONTENT-RIGHTS.md` and `public.source_releases`).
   - Ingestion stamps `domain_rights_status="licensed"` onto point payloads.
   - Retrieval queries enforce `filter: { domain_rights_status: { equals: "licensed" } }`.
   - Missing or unverified rights are *never* defaulted to "licensed".
2. **Chunker Version Strictness:**
   - Every point payload must declare its exact chunker class (e.g. `boundary_v1:target_1200`, `adaptive_v1`, `recursive_v1`).
   - Historical unversioned points are explicitly stamped `"unknown_legacy"`. Ingestion tools never backfill or synthesize hypothetical chunker classes.
   - Proposition chunking is permanently retired (Decision D3).
3. **Persistent Rejection Ledgers:**
   - All items rejected by quality or rights gates are recorded in `public.corpus_gate_rejections` with source URL, release version, rejection reason, and raw error payload.
4. **Human Review Packets for Speaker Conflicts:**
   - Speaker diarization conflicts are quarantined in `deterministic_id_collision_quarantine` and exported to immutable review packets in `docs/reviews/2026-11-14-human-gates/`.
   - Blank decision rows can only be signed off by authorized human reviewers; automated agents are barred from resolving speaker conflicts.

---

## 4. Database Schema (PostgreSQL)

See full DDL in `replica/schema.sql`.

Key architectural tables:
- `public.source_releases`: Canonical catalog of all ingested source assets, content hashes, and licensing rights.
- `public.content_rights_register`: Granular intellectual property permissions, territory restrictions, and expiration rules.
- `public.corpus_gate_rejections`: Append-only audit ledger of every chunk rejected during ingestion.
- `public.serving_cache_fingerprints`: Cryptographic mapping of 6-factor request hashes to served payloads.
- `public.human_review_packets`: Human-in-the-loop review queue for speaker conflicts and rights sign-offs.
- `public.eval_runs` & `public.eval_case_results`: Evaluation tracking ledger recording collection fingerprints and scores.

---

## 5. API Contracts & Service Wirings

All external interactions use authenticated, standardized REST and streaming protocols:

| Method & Path | Purpose | Caller | Input Payload | Output Payload | Flow |
|---|---|---|---|---|---|
| `POST /api/chat` | Main conversational query endpoint | Web Seeker UI | `{ query, session_id?, guru_preference?, lang? }` | `{ answer, citations, is_direct, status, audio_clip }` | F01 (Seeker Query) |
| `GET /api/chat/stream` | Server-Sent Events (SSE) streaming | Web Seeker UI | Query params: `session_id`, `token` | Text chunks, citation events, done event | F01 (Streaming Query) |
| `POST /api/feedback` | User response ratings & feedback | Web Seeker UI | `{ message_id, rating, thumbs_down_reason? }` | `{ status: "ok" }` | Continuous Learning |
| `GET /api/source/audio-slice` | Fetch verified audio slice stream | Audio Player | `{ source_id, start_ms, end_ms }` | Audio PCM/MP3 stream with range headers | S02/S04 (Audio Play) |
| `POST /api/ingest/youtube` | Trigger YouTube video ingestion | Ops / Cron Job | `{ video_url, channel_id, rights_clearance_id }` | `{ job_id, status: "queued" }` | F02 (Ingest Stream) |
| `GET /api/admin/corpus/health` | Health & invariant telemetry probe | Ops Monitoring | None (Admin Bearer Token) | `{ optimizer_ok, drift_count, snapshot_age }` | S06 (Health Probe) |
| `POST /api/admin/reviews/resolve` | Sign off human review packet | Human Reviewer | `{ packet_id, decision, signature_hash }` | `{ status: "resolved", promoted: bool }` | F03 (Review Sign-Off) |

---

## 6. The Parts That Bite (Failure Modes & Defenses)

1. **Exact-Cache Poisoning:**
   - *Risk:* An unverified answer or outdated doctrine is cached and served to subsequent seekers for 24 hours.
   - *Defense:* The 6-factor hash explicitly binds `model_revision`, `prompt_template_hash`, and `rights_register_sha256`. A deployment or rights revocation instantly creates new cache keys without dangerous manual flushes.
2. **Audio Alignment Stubs (Zero-Byte WAV Defect):**
   - *Risk:* ASR ingestion reads corrupted or zero-byte audio files (historical 86-byte WAV stubs), creating fake duration coordinates.
   - *Defense:* Pre-flight audio validation verifies real PCM byte length, audio headers, and waveform energy before calling Whisper/Parakeet.
3. **Relevance Scorer Congestion Cascades:**
   - *Risk:* Cross-encoder rerankers or LLM evaluators experience network lag, causing request queues to pile up and exceed timeouts.
   - *Defense:* Transport jitter retry is limited to a single attempt that failed quickly (< 50% timeout). Slower stalls immediately abort and fail closed to `relevance_indeterminate`.
4. **Vector ID Drift on Re-Ingestion:**
   - *Risk:* Re-running ingestion over existing videos produces different vector IDs, causing orphaned records and index bloat.
   - *Defense:* Deterministic UUID5 generation guarantees that identical transcript content maps to byte-identical point and parent UUIDs across repeated runs.
5. **Acute Distress & Safety Bypass:**
   - *Risk:* An injection prompt attempts to bypass safety filters to elicit harmful or sensitive advice.
   - *Defense:* `DistressStage` and `InputGuardrailStage` execute *before* `CircuitBreakerStage` and before any doctrine cache lookup, ensuring emergency compassion rails cannot be circumvented.

---

## 7. Phased Build Order

### Milestone 1: Vertical Slice (The Core Invariant Loop)
- **Scope:** Basic chat endpoint with Kill Switch, Input Guardrails, Retrieval-Only Qdrant Search, and Verbatim Quote formatting.
- **Artifacts:** `backend/app/main.py`, `backend/app/pipeline/stages/`, `backend/services/qdrant/client.py`.
- **Exit Criteria:** End-to-end question answering returning strict verbatim quotes with zero synthetic prose.

### Milestone 2: Multi-Modal Ingestion & Provenance Hardening
- **Scope:** Dual ASR pipeline (Whisper + Parakeet), ECAPA voiceprint verification, deterministic chunking (`boundary_v1`), and persistent rejection logging.
- **Artifacts:** `backend/ingest/`, `backend/services/provenance.py`, `public.corpus_gate_rejections` table.
- **Exit Criteria:** Idempotent re-ingestion of video transcripts with 100% byte-identical point IDs and logged rejections.

### Milestone 3: Exact-Cache Cryptography & Serving Contracts
- **Scope:** 6-factor cache fingerprinting in Redis, transport jitter retry policies, and metadata directness separation.
- **Artifacts:** `backend/services/first_person_serving_contract.py`, `backend/app/pipeline/stages/cache_stage.py`.
- **Exit Criteria:** Verified cache invalidation upon model/prompt hash updates; zero cache poisoning.

### Milestone 4: Blue-Green Index Promotion & Observability
- **Scope:** Zero-downtime Qdrant alias cutover scripts, operator health dashboard (`/api/admin/corpus/health`), and automated snapshot audits.
- **Artifacts:** `scripts/ops/promote_collection_alias.py`, `scripts/ops/verify_corpus_invariants.py`.
- **Exit Criteria:** Live collection alias swap without dropping in-flight search requests; automated detection of index drift.
