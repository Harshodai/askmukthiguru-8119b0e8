# REST & Streaming API Reference

AskMukthiGuru exposes an enterprise-grade asynchronous API built on **FastAPI and Starlette**, adhering strictly to OpenAPI 3.1 specifications. The API provides endpoints for real-time conversational guidance via Server-Sent Events (SSE), first-person verbatim clip review, distributed video ingestion, administrative telemetry, and zero-knowledge memory management.

---

## 1. Global Gateway Architecture & Protocol Standards

```
┌──────────────────────────────────────────────────────────────────────────────────┐
│                             API GATEWAY PROTOCOLS                                │
├──────────────────────────────────────────────────────────────────────────────────┤
│ Base URLs:                                                                       │
│ • Local Development:  http://localhost:8000/api                                  │
│ • Production Gateway: https://askmukthiguru.com/api                              │
├──────────────────────────────────────────────────────────────────────────────────┤
│ Content Types:                                                                   │
│ • Standard Requests:  application/json                                           │
│ • Streaming Dialogue: text/event-stream (SSE)                                    │
│ • Evidence Uploads:   multipart/form-data (Max 10MB per attachment, max 5)       │
├──────────────────────────────────────────────────────────────────────────────────┤
│ Global Rate Limiting (Redis Sliding-Window Token Bucket):                        │
│ • Chat Endpoints (/api/chat, /api/chat/stream): 20 requests / minute             │
│ • Multi-modal Uploads (/api/chat/upload):       5 requests / minute              │
│ • Anonymous Seeker Quota:                      3 complimentary queries           │
└──────────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Authentication, Authorization & AAL2 Elevation

AskMukthiGuru implements a tiered security model spanning anonymous seekers, registered users, and authenticated administrators.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                       TIERED AUTHENTICATION MODEL                           │
├──────────────────────┬──────────────────────┬───────────────────────────────┤
│   ANONYMOUS SEEKER   │   REGISTERED SEEKER  │       AAL2 ADMINISTRATOR      │
├──────────────────────┼──────────────────────┼───────────────────────────────┤
│ • Header:            │ • Header:            │ • Header:                     │
│   X-Session-ID       │   Authorization:     │   Authorization:              │
│ • Progressive Quota: │   Bearer <JWT>       │   Bearer <AAL2_JWT>           │
│   3 free queries     │ • Claims:            │ • Claims:                     │
│ • Ingestion & Admin  │   sub: <user_uuid>   │   aal: "aal2"                 │
│   forbidden (401)    │   role: "authenticated"  role: "admin"               │
│ • Ephemeral state    │ • Persistent memory  │ • Admin whitelist check:      │
│                      │   vault unlocked     │   UUID in ADMIN_USER_IDS      │
└──────────────────────┴──────────────────────┴───────────────────────────────┘
```

### 2.1 TOTP MFA Authenticator Assurance Level 2 (AAL2)
Administrative routes enforce `Depends(require_aal2)` from `backend/services/auth_service.py`:
1. **JWT Verification**: Decodes Supabase JWT against configured secrets or JWKS endpoints.
2. **AAL Enforcement**: Verifies that the JWT payload contains `aal: "aal2"`, confirming that the administrator completed multi-factor authentication (TOTP or security key).
3. **Defense-in-Depth Whitelist**: When `ADMIN_USER_IDS` is configured in `backend/app/config.py`, the user’s UUID must be explicitly listed. If not matched, the gateway returns `403 Forbidden` regardless of token validity.

---

## 3. Conversational Chat Endpoints

### 3.1 Synchronous & Queued Chat: `POST /api/chat`
Main conversational endpoint supporting both synchronous execution and background task queueing.

* **Rate Limit**: 20 requests/minute
* **Headers**:
  * `Content-Type: application/json`
  * `Authorization: Bearer <token>` (Optional for anonymous seekers)
  * `X-Session-ID: <uuid>` (Mandatory for anonymous state tracking)

#### Request Body (`ChatRequest`):
```json
{
  "user_message": "How do I overcome unconscious anxiety and fear?",
  "session_id": "018d9b1a-5b4e-7f3c-9a11-8c4d2e7a1b3c",
  "language_code": "en",
  "tone_preference": "gentle",
  "attachments": [],
  "assistant_id": null
}
```

#### Synchronous Response (`200 OK` with `?wait=true`):
```json
{
  "answer": "Sri Preethaji teaches that fear arises when the mind becomes obsessively self-engaged...",
  "session_id": "018d9b1a-5b4e-7f3c-9a11-8c4d2e7a1b3c",
  "grounding_state": "verified",
  "intent": "QUERY",
  "citations": [
    {
      "citation_id": 1,
      "source_title": "The Art of Overcoming Fear",
      "video_id": "ehkqJ54DIC0",
      "guru": "sri-preethaji",
      "start_time_seconds": 125,
      "end_time_seconds": 170,
      "quote_text": "When you observe the state of fear without judgment, it dissolves..."
    }
  ],
  "route_metadata": {
    "fp_served": false,
    "rewrites_attempted": 0,
    "faithfulness_score": 0.94
  },
  "usage": {
    "prompt_tokens": 412,
    "completion_tokens": 185,
    "total_tokens": 597
  }
}
```

#### Asynchronous Queued Response (`202 Accepted`):
When queue mode is enabled (default), the gateway responds immediately with job metadata:
```json
{
  "status": "queued",
  "job_id": "job_94a7e2b1",
  "poll_url": "/api/chat/status/job_94a7e2b1",
  "stream_url": "/api/chat/stream/job_94a7e2b1"
}
```

---

### 3.2 Real-Time Streaming Chat: `POST /api/chat/stream` & `GET /api/chat/stream/{job_id}`
Establishes a Server-Sent Events (SSE) stream delivering token-by-token text, status updates, and citation markers.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          SSE STREAMING LIFECYCLE                            │
├─────────────────────────────────────────────────────────────────────────────┤
│ Client                                              FastAPI Gateway         │
│   │                                                        │                │
│   │ ─── POST /api/chat/stream (Payload) ─────────────────► │                │
│   │                                                        │ (Enqueues job) │
│   │ ◄── 202 Accepted { "stream_url": "/api/..." } ──────── │                │
│   │                                                        │                │
│   │ ─── GET /api/chat/stream/{job_id} ───────────────────► │                │
│   │ ◄── 200 OK (text/event-stream) ─────────────────────── │                │
│   │                                                        │                │
│   │ ◄── event: status \ndata: {"stage": "searching"} ───── │                │
│   │ ◄── event: status \ndata: {"stage": "reranking"} ───── │                │
│   │ ◄── event: citation \ndata: {"id": 1, "video_id": ...} │                │
│   │ ◄── event: token \ndata: "Sri Preethaji teaches" ───── │                │
│   │ ◄── event: token \ndata: " that anxiety..." ────────── │                │
│   │ ◄── event: done \ndata: {"grounding_state": "ok"} ──── │                │
│   ▼                                                        ▼                │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### SSE Event Specifications:

| Event Type | Data Payload Schema | Description |
|---|---|---|
| `event: status` | `{"stage": string, "node": string, "step": int, "total": int}` | Live LangGraph pipeline node progress for `ThinkingPills` |
| `event: token` | `<string_token>` | Incremental synthesized token chunk |
| `event: citation` | `{"citation_id": int, "title": string, "video_id": string, "start": int}` | Resolved citation payload for client citation chips |
| `event: done` | `{"grounding_state": string, "total_tokens": int, "latency_ms": float}` | Terminal event terminating stream processing |
| `event: error` | `{"detail": string, "code": string}` | Pipeline failure or circuit breaker trip notice |

---

## 4. First-Person Verbatim Serving Endpoints

Endpoints powering the zero-hallucination verbatim spoken wisdom pipeline.

### 4.1 Owner-Only Local Review Status: `GET /api/first-person/local-review/status`
* **Access**: Local environment only (`FIRST_PERSON_LOCAL_REVIEW_ENABLED=true` and `IS_PRODUCTION=false`).
* **Response (`200 OK`)**:
```json
{
  "local_review_enabled": true,
  "is_production": false,
  "collection": "first_person_v10",
  "points_count": 4197,
  "serving_contract": "fp-context-v1",
  "evidence_policy": "automated_evidence_candidate",
  "canonical_labels": [
    "REVIEW CANDIDATE — NOT PUBLIC RELEASE",
    "AUTOMATED EVIDENCE — NOT HUMAN-CERTIFIED ATTRIBUTION"
  ],
  "contract_checksum_valid": true
}
```

### 4.2 Local Review Query: `POST /api/first-person/local-review/query`
* **Request Body**:
```json
{
  "query": "What is the true nature of suffering?",
  "guru_filter": "sri-preethaji",
  "max_spans": 2
}
```
* **Response**: Returns unparaphrased transcript spans with ECAPA speaker verification scores, acoustic window offsets, and canonical warning headers.

### 4.3 Public Query Gate: `POST /api/first-person/query`
* **Production Status**: Gated with `503 Service Unavailable` per public release blocker NO-GO status until human-certified acoustic verification (B7) is completed.

---

## 5. Administrative Telemetry & Management Endpoints

All administrative routes require **AAL2 authenticated session headers**.

### 5.1 Seeker Query History: `GET /api/admin/queries`
* **Query Parameters**:
  * `limit` (default: 50, max: 200)
  * `offset` (default: 0)
  * `intent_filter` (`QUERY`, `DISTRESS`, `CASUAL`, `COMPARATIVE`)
  * `grounding_filter` (`verified`, `abstained`, `system_error`)
* **Response**: Paginated list of anonymized seeker queries, pipeline execution times, faithfulness scores, and assigned intents.

### 5.2 Distributed Tracing: `GET /api/admin/traces`
* **Query Parameters**: `trace_id`, `min_duration_ms`
* **Response**: OpenTelemetry span hierarchy detailing execution durations across Redis cache lookups, Qdrant hybrid searches, Neo4j Cypher queries, and LLM inference calls.

### 5.3 Stage Latency Profiler: `GET /api/admin/pipeline/stage-latencies`
* **Response**: Percentile latency breakdown ($p50, p95, p99$) across all 12 pipeline stages:
```json
{
  "time_window": "last_24h",
  "stages": {
    "guardrails": { "p50_ms": 12.4, "p95_ms": 28.1, "p99_ms": 45.0 },
    "intent_routing": { "p50_ms": 45.2, "p95_ms": 82.0, "p99_ms": 110.5 },
    "hybrid_retrieval": { "p50_ms": 115.0, "p95_ms": 195.4, "p99_ms": 320.0 },
    "cross_rerank": { "p50_ms": 85.3, "p95_ms": 140.2, "p99_ms": 210.0 },
    "llm_generation": { "p50_ms": 850.0, "p95_ms": 1420.0, "p99_ms": 2100.0 },
    "grounding_check": { "p50_ms": 180.0, "p95_ms": 310.0, "p99_ms": 450.0 }
  }
}
```

### 5.4 OKF Doctrine Staging Management: `/api/admin/okf/*`
* `GET /api/admin/okf/staging`: Lists extracted 5-node transformation arcs awaiting human review.
* `POST /api/admin/okf/approve`: Promotes a candidate arc into `memory/okf/compiled.json`.
* `POST /api/admin/okf/reject`: Rejects a candidate with mandatory rejection reason, recorded into `corpus_gate_rejections`.

---

## 6. Video Ingestion & Quality Gate Endpoints

Endpoints orchestrating the asynchronous YouTube extraction and indexing pipeline.

### 6.1 Enqueue Video Ingestion: `POST /api/ingest/video`
* **Auth**: Requires AAL2 Admin.
* **Request Body**:
```json
{
  "video_url": "https://www.youtube.com/watch?v=ehkqJ54DIC0",
  "primary_guru": "sri-preethaji",
  "rights_status": "licensed",
  "rights_reference": "CONTENT-RIGHTS.md#license-004",
  "run_raptor": true
}
```
* **Response (`202 Accepted`)**:
```json
{
  "job_id": "ingest_88fa10b",
  "status": "queued",
  "video_id": "ehkqJ54DIC0",
  "estimated_duration_minutes": 45
}
```

### 6.2 Ingestion Job Status: `GET /api/ingest/jobs`
* **Response**: Lists active Celery background tasks with real-time progression:
  * `downloading_audio`
  * `transcribing_whisper`
  * `acoustic_speaker_verification`
  * `chunking_boundary_v1`
  * `indexing_qdrant`
  * `completed` / `rejected`

### 6.3 Approve Staged Video: `POST /api/admin/videos/{video_id}/approve`
* Approves staged video chunks for promotion into production vector and graph collections.

---

## 7. HTTP Status Codes & Error Protocol

| HTTP Status | Meaning | Typical Trigger |
|---|---|---|
| `200 OK` | Success | Synchronous chat result, query history, health status |
| `202 Accepted` | Asynchronous Job Enqueued | Background chat execution, video ingestion tasks |
| `400 Bad Request` | Malformed Request | Invalid JSON syntax, unrecognized parameters |
| `401 Unauthorized` | Missing Authentication | Missing Bearer token or invalid anonymous session |
| `403 Forbidden` | Insufficient Privileges | Missing AAL2 elevation, non-whitelisted admin UUID |
| `408 Request Timeout` | Processing Timeout | File attachment extraction exceeded 45s threshold |
| `413 Payload Too Large`| Attachment Limit Exceeded| File $> 10\text{MB}$ or $> 5$ attachments submitted |
| `422 Unprocessable` | Schema Validation Error | Missing mandatory fields (e.g. `user_message`) |
| `429 Too Many Requests`| Rate Limit Exceeded | Client exceeded 20 req/min or anonymous daily budget |
| `500 Server Error` | Unhandled Exception | Internal runtime failure; logged to OpenTelemetry |
| `503 Unavailable` | Circuit Breaker Open / NO-GO| Provider circuit tripped or gated first-person route |

---

## 8. Related Wiki Documentation

* [System Architecture Overview](Architecture-Overview) — Container networking, ports, and reverse proxy routing.
* [12-Layer RAG Pipeline](Architecture-RAG-Pipeline) — LangGraph state machine and SSE event emission mechanics.
* [First-Person Serving Architecture](Architecture-First-Person-Serving) — B4 serving contracts and speaker verification endpoints.
* [Memory & Second Brain Vault](Memory-Second-Brain-Vault) — User memory schemas and bi-temporal persistence.
