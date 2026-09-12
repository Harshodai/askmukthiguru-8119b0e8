# Canonical Memory API Reference

REST API for the AskMukthiGuru adaptive memory system.

## Base URL

```
POST /api/chat  →  pipeline → /api/memory/canonical
```

All endpoints require a valid Supabase JWT token in the `Authorization` header.

## Authentication

```
Authorization: Bearer <supabase_jwt_token>
```

Every endpoint enforces:
1. JWT signature verification against Supabase JWKS
2. `user_id` extraction from JWT claims
3. Row-Level Security (RLS) on Postgres tables
4. Server-side `user_id` filter (defense-in-depth)

---

## Endpoints

### List Memories

```
GET /api/memory/canonical
```

Returns paginated memories for the authenticated user.

**Query Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `page` | integer | 1 | Page number (≥ 1) |
| `page_size` | integer | 20 | Results per page (1–100) |
| `memory_type` | string | — | Filter by type: `PROFILE`, `PREFERENCE`, `GOAL`, etc. |
| `status` | string | `active` | Filter by status: `active`, `deleted`, `superseded` |

**Response (200):**

```json
{
  "memories": [
    {
      "id": "uuid",
      "statement": "User lives in Mumbai, India",
      "memory_type": "PROFILE",
      "confidence": 0.9,
      "importance": 0.7,
      "sensitivity": "normal",
      "status": "active",
      "fact_key": "user:lives_in",
      "evidence_count": 3,
      "extraction_method": "llm_inferred",
      "source_conversation_id": "conv_abc123",
      "created_at": "2026-01-15T10:30:00Z",
      "updated_at": "2026-02-01T14:20:00Z",
      "last_used_at": "2026-02-01T14:20:00Z",
      "version": 2
    }
  ],
  "total": 42,
  "page": 1,
  "page_size": 20
}
```

**Errors:**

| Status | Detail |
|--------|--------|
| 400 | Invalid `memory_type` value |
| 401 | Missing or invalid JWT |
| 500 | Database error |

---

### Create Memory

```
POST /api/memory/canonical
```

Add an explicit memory. Only for user-initiated "remember that…" requests.

**Request Body:**

```json
{
  "statement": "I prefer guided meditations over silent ones",
  "memory_type": "PREFERENCE",
  "confidence": 1.0,
  "importance": 0.8,
  "sensitivity": "normal",
  "fact_key": "user:prefers_meditation_style"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `statement` | string | yes | Natural-language fact (2–1000 chars) |
| `memory_type` | string | no | Default: `USER_EXPLICIT` |
| `confidence` | float | no | 0.0–1.0, default: 1.0 |
| `importance` | float | no | 0.0–1.0, default: 0.8 |
| `sensitivity` | string | no | `normal`, `sensitive`, `highly_sensitive` |
| `fact_key` | string | no | Dedup namespace (e.g., `user:lives_in`) |

**Valid `memory_type` values:**

`PROFILE`, `PREFERENCE`, `COMMUNICATION_STYLE`, `GOAL`, `PROJECT`, `INTEREST`, `RELATIONSHIP`, `USER_EXPLICIT`, `TEMPORARY_CONTEXT`, `REFLECTION`

**Response (201):**

```json
{
  "id": "uuid",
  "statement": "I prefer guided meditations over silent ones",
  "memory_type": "PREFERENCE",
  "confidence": 1.0,
  "importance": 0.8,
  "sensitivity": "normal",
  "status": "active",
  "fact_key": "user:prefers_meditation_style",
  "evidence_count": 1,
  "extraction_method": "user_explicit",
  "source_conversation_id": null,
  "created_at": "2026-01-15T10:30:00Z",
  "updated_at": "2026-01-15T10:30:00Z",
  "last_used_at": null,
  "version": 1
}
```

**Errors:**

| Status | Detail |
|--------|--------|
| 400 | Invalid `memory_type` or `sensitivity` |
| 401 | Missing or invalid JWT |
| 500 | Database error |

---

### Update Memory

```
PUT /api/memory/canonical/{memory_id}
```

Edit an existing memory's statement. Supports optimistic concurrency via `version`.

**Path Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `memory_id` | uuid | Memory ID |

**Request Body:**

```json
{
  "statement": "User lives in Bangalore, India",
  "version": 2
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `statement` | string | yes | Updated fact (2–1000 chars) |
| `version` | integer | no | Expected current version for optimistic concurrency |

**Response (200):**

Returns the updated `CanonicalMemoryResponse`.

**Errors:**

| Status | Detail |
|--------|--------|
| 400 | Invalid UUID |
| 401 | Missing or invalid JWT |
| 404 | Memory not found or not owned by user |
| 409 | Version conflict (memory modified by another process) |
| 500 | Database error |

---

### Forget Memory (Single)

```
DELETE /api/memory/canonical/{memory_id}
```

Soft-delete a specific memory by setting `status='deleted'`. Writes an audit event.

**Path Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `memory_id` | uuid | Memory ID |

**Response (200):**

```json
{
  "status": "ok",
  "message": "Memory forgotten",
  "memory_id": "uuid"
}
```

**Errors:**

| Status | Detail |
|--------|--------|
| 400 | Invalid UUID |
| 401 | Missing or invalid JWT |
| 404 | Memory not found or not owned by user |
| 500 | Database error |

---

### Forget All Memories

```
DELETE /api/memory/canonical
```

Hard-delete all canonical memories for the authenticated user. Propagates to:
1. `canonical_memories` (Postgres)
2. `canonical_memory_vectors` (Qdrant)
3. `canonical_memory_events` (consolidated audit event)

**Response (200):**

```json
{
  "status": "completed",
  "deleted": 42,
  "failures": []
}
```

If partial failure occurs:

```json
{
  "status": "partial_failure",
  "deleted": 40,
  "failures": ["qdrant_vectors"]
}
```

**Errors:**

| Status | Detail |
|--------|--------|
| 401 | Missing or invalid JWT |
| 500 | Database error |

---

### Why Was This Remembered?

```
GET /api/memory/canonical/reasons
```

Returns provenance metadata for the user's memories. Shows why each memory was created.

**Query Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `limit` | integer | 20 | Max results (1–100) |

**Response (200):**

```json
[
  {
    "memory_id": "uuid",
    "statement": "User lives in Mumbai, India",
    "memory_type": "PROFILE",
    "confidence": 0.9,
    "extraction_method": "llm_inferred",
    "evidence": "I live in Mumbai.",
    "source_conversation_id": "conv_abc123",
    "source_turn_index": 3,
    "created_at": "2026-01-15T10:30:00Z",
    "last_confirmed_at": "2026-02-01T14:20:00Z",
    "evidence_count": 3
  }
]
```

---

### Consent Management

```
POST /api/memory/consent
```

Record a revocable, versioned consent receipt.

**Request Body:**

```json
{
  "granted": true,
  "consent_version": "memory-v1"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `granted` | boolean | yes | `true` to grant, `false` to revoke |
| `consent_version` | string | no | Version identifier, default: `memory-v1` |

**Response (200):**

```json
{
  "status": "granted",
  "receipt_id": "uuid",
  "consent_version": "memory-v1",
  "pending_outbox_rows_deleted": 0
}
```

When consent is revoked, all pending outbox rows are deleted.

**Consent Scopes:**

| Scope | Default | Behavior |
|-------|---------|----------|
| `extraction` | Denied (opt-in) | Must be granted before memories are created |
| `retrieval` | Granted (opt-out) | Can be revoked to stop memory retrieval |
| `sharing` | Granted (opt-out) | Can be revoked to stop cross-service sharing |
| `analytics` | Granted (opt-out) | Can be revoked to stop analytics |

---

### GDPR Export

```
GET /api/memory/export
```

Returns all memories, consent receipts, and audit events as a downloadable JSON payload.

**Response (200):**

```json
{
  "user_id": "uuid",
  "exported_at": "2026-02-01T14:20:00Z",
  "memories": [
    {
      "id": "uuid",
      "statement": "User lives in Mumbai, India",
      "memory_type": "PROFILE",
      "confidence": 0.9,
      "importance": 0.7,
      "sensitivity": "normal",
      "status": "active",
      "extraction_method": "llm_inferred",
      "created_at": "2026-01-15T10:30:00Z",
      "updated_at": "2026-02-01T14:20:00Z"
    }
  ],
  "consent_receipts": [
    {
      "id": "uuid",
      "scope": "extraction",
      "granted": true,
      "consent_version": "memory-v1",
      "created_at": "2026-01-15T10:00:00Z"
    }
  ],
  "audit_events": [
    {
      "id": "uuid",
      "memory_id": "uuid",
      "event_type": "CREATED",
      "actor": "llm",
      "reason": "Extracted from conversation",
      "created_at": "2026-01-15T10:30:00Z"
    }
  ],
  "total_memories": 42
}
```

---

## Error Handling

All errors return JSON:

```json
{
  "detail": "Human-readable error message"
}
```

Common status codes:

| Status | Meaning |
|--------|---------|
| 400 | Invalid request (bad UUID, invalid type, etc.) |
| 401 | Missing or invalid JWT token |
| 403 | Forbidden (user doesn't own the resource) |
| 404 | Resource not found |
| 409 | Conflict (version mismatch) |
| 500 | Internal server error |
| 501 | Feature not available (database not connected) |
| 503 | Service unavailable (consent service down) |

---

## Rate Limiting

Memory endpoints are subject to per-user rate limiting:
- Anonymous users: 5 messages per 24-hour window
- Authenticated users: Standard rate limits apply

## Security Notes

- Every endpoint validates JWT signature and extracts `user_id`
- RLS policies enforce row-level access on all Postgres tables
- Server-side `user_id` filter provides defense-in-depth against RLS bypass
- Prompt injection patterns are detected and blocked in the extraction pipeline
- Memory content is never logged with user-identifiable information
- Sensitive memories require explicit consent before creation
