# BACKEND_INTEGRATION.md
# Admin Console — FastAPI Integration Guide

This document covers the **four items in the Admin Console that genuinely require a running FastAPI backend**. Every other admin page (Overview, Queries + drill-down, Quality, Retrieval, Triggers, Prompts, Evals, Alerts, Logs, Admins) is fully functional client-side once you click **"Seed demo traces"** in `/admin`.

---

## Status Summary

| Feature | Frontend | Backend | Action needed |
|---|---|---|---|
| All admin pages (Overview → Admins) | ✅ Real Supabase queries | ✅ Data seeded via RPC | Click **"Seed demo traces"** |
| Telemetry Sink | ✅ Reads from Supabase | ✅ `telemetry_sink.py` exists + wired | Populate `SUPABASE_SERVICE_ROLE_KEY` |
| Ingestion API | ✅ `IngestionPage` form | ✅ `POST /api/ingest` exists | Wire `submitIngestion()` + add `VITE_BACKEND_URL` |
| AskData / NL→SQL | ✅ Button shows toast | ❌ Not implemented | Build `POST /api/admin/ask-data` |
| Dead-docs tab | ✅ `getDeadDocs()` ready | ❌ No document registry table | Add `document_registry` table at ingestion |
| Jaeger embed | ✅ `TelemetryPage` iframes it | ❌ Needs reverse proxy + CORS | Configure nginx + `VITE_JAEGER_UI_URL` |

---

## Section 1 — Telemetry Sink (ALREADY IMPLEMENTED)

The `SupabaseTelemetrySink` class is already implemented at `backend/app/telemetry_sink.py` and wired into both `chat_endpoint` (line 989) and `chat_stream_endpoint` (line 1477) in `main.py`.

### How it works

Every chat request triggers `telemetry_sink.log_query_trace(...)` as a background task. This writes to:

| Table | What gets written |
|---|---|
| `chat_queries` | `query_id`, `query_text`, `model`, `latency_ms`, `status`, `session_id` |
| `chat_responses` | `response_text`, `faithfulness`, `answer_relevancy`, `hallucination_flag`, `citations` |
| `retrieval_events` | `source_docs[]`, `scores[]`, `query_id` |
| `trace_spans` | Per-pipeline-node spans (`start_ms`, `end_ms`, `name`) |
| `trigger_events` | `trigger_name`, `trigger_type`, `query_id` |
| `safety_events` | `rule`, `details`, `query_id` |
| `app_logs` | `level`, `message`, `request_id` |

### Required env vars

```bash
# In backend/.env (already present for local Supabase)
SUPABASE_URL=http://host.docker.internal:54321
SUPABASE_KEY=<service_role_key>    # must be service_role, not anon

# For production Supabase (add this):
SUPABASE_SERVICE_ROLE_KEY=<your-service-role-key>
```

The sink prefers `SUPABASE_SERVICE_ROLE_KEY` and falls back to `SUPABASE_KEY`.

### Admin pages that light up

All of them — Overview KPIs, Queries, Retrieval, Quality, Triggers, and Logs all read from these tables.

### Verification

```bash
# 1. Make a chat request with the backend running:
curl -X POST http://localhost:8000/api/chat \
  -H "Authorization: Bearer <your-jwt>" \
  -H "Content-Type: application/json" \
  -d '{"user_message": "What is karma?", "messages": [], "session_id": "test-1"}'

# 2. Check that a row was written:
# In Supabase Studio → Table Editor → chat_queries → should show 1 new row
```

---

## Section 2 — Ingestion API (ALREADY IMPLEMENTED)

The ingestion API is already fully implemented. Two endpoints exist:

### `POST /api/ingest`

Accepts YouTube video/playlist URLs and image URLs. Runs ingestion in the background.

**Request body:**
```json
{
  "url": "https://www.youtube.com/watch?v=<video_id>",
  "max_accuracy": false
}
```

**Response:**
```json
{
  "status": "queued",
  "message": "Ingestion started",
  "source_url": "https://...",
  "chunks_indexed": 0,
  "summaries_created": 0
}
```

**Auth**: Requires a valid Supabase JWT in `Authorization: Bearer <token>`. User must have `is_superuser=true` (admin role).

### `GET /api/ingest/status`

Returns the status of the currently-running ingestion job (or last completed).

### Why the IngestionPage form is a no-op

`IngestionPage` calls `triggerReingest(source)` from `mockData.ts`, which is a no-op. To wire it end-to-end:

**Step 1**: Add `VITE_BACKEND_URL` to `.env.local`:
```bash
VITE_BACKEND_URL=http://localhost:8000
```

**Step 2**: Replace `triggerReingest` in `src/admin/lib/mockData.ts`:
```typescript
export async function triggerReingest(url: string): Promise<void> {
  const { data: { session } } = await supabase.auth.getSession();
  const token = session?.access_token;
  const resp = await fetch(`${import.meta.env.VITE_BACKEND_URL}/api/ingest`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "Authorization": `Bearer ${token}`,
    },
    body: JSON.stringify({ url, max_accuracy: false }),
  });
  if (!resp.ok) throw new Error(await resp.text());
}
```

### Verification

```bash
# Obtain JWT first (local Supabase):
TOKEN=$(curl -s -X POST "http://localhost:54321/auth/v1/token?grant_type=password" \
  -H "apikey: <anon-key>" \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@example.com","password":"yourpassword"}' | jq -r '.access_token')

curl -X POST http://localhost:8000/api/ingest \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://www.youtube.com/watch?v=<video_id>"}'
# Expected: {"status":"queued","message":"Ingestion started",...}
```

---

## Section 3 — AskData / NL→SQL (NOT YET IMPLEMENTED)

The **AskData** button currently returns a static string:
`"AskData requires the FastAPI backend. See BACKEND_INTEGRATION.md → AskData."`

To implement it:

### Step 1: Add endpoint to `backend/app/main.py`

```python
class AskDataRequest(BaseModel):
    question: str = Field(..., description="Natural language question about admin KPIs")

@app.post("/api/admin/ask-data", tags=["Admin"])
async def ask_data_endpoint(
    body: AskDataRequest,
    user: dict = Depends(get_current_user_from_supabase),
    container: ServiceContainer = Depends(get_container),
) -> dict:
    """NL→KPI insight endpoint for admin dashboard."""
    if not user.get("is_superuser", False):
        raise HTTPException(status_code=403, detail="Admin access required")

    # Example: fetch recent KPI context, call LLM, return markdown answer
    # kpi_context = await build_kpi_context(container)
    # prompt = f"KPI Context:\n{kpi_context}\n\nQuestion: {body.question}\n\nAnswer in markdown:"
    # answer = await container.llm.chat(prompt)
    # return {"answer": answer}
    raise NotImplementedError("AskData endpoint — implement above pattern")
```

### Step 2: Wire frontend in `src/admin/lib/mockData.ts`

```typescript
export async function askData(question: string): Promise<string> {
  const { data: { session } } = await supabase.auth.getSession();
  const token = session?.access_token;
  const resp = await fetch(`${import.meta.env.VITE_BACKEND_URL}/api/admin/ask-data`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "Authorization": `Bearer ${token}`,
    },
    body: JSON.stringify({ question }),
  });
  if (!resp.ok) throw new Error(await resp.text());
  const data = await resp.json();
  return data.answer;
}
```

### Required env vars
```bash
# .env.local (frontend)
VITE_BACKEND_URL=http://localhost:8000
```

### Admin page that lights up
Settings page → "Ask Data" input field.

---

## Section 4 — Dead-Docs Registry (NOT YET IMPLEMENTED)

The **Retrieval page → Dead Docs tab** calls `getDeadDocs()` which returns `[]` with:
```
// Requires document_registry table populated by ingestion — see BACKEND_INTEGRATION.md
```

A "dead doc" is one that exists in the index but has zero retrieval hits in recent queries.

### Step 1: Create migration

```sql
-- supabase/migrations/<timestamp>_document_registry.sql
CREATE TABLE IF NOT EXISTS public.document_registry (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  source_url  text NOT NULL UNIQUE,
  title       text,
  doc_type    text,           -- 'youtube', 'image', 'pdf'
  chunks      integer DEFAULT 0,
  created_at  timestamptz DEFAULT now(),
  last_seen   timestamptz DEFAULT now()
);

CREATE INDEX ON public.document_registry (source_url);
ALTER TABLE public.document_registry ENABLE ROW LEVEL SECURITY;
CREATE POLICY "admins_only" ON public.document_registry
  USING (public.has_role(auth.uid(), 'admin'::public.app_role));
GRANT SELECT, INSERT, UPDATE ON public.document_registry TO service_role;
```

### Step 2: Write to it after ingestion completes

In `backend/app/main.py` after the ingestion pipeline finishes:

```python
# After chunks_indexed is known:
telemetry_sink.client.table("document_registry").upsert({
    "source_url": url,
    "title": video_title or url,
    "doc_type": "youtube" if is_yt else "image",
    "chunks": chunks_indexed,
    "last_seen": datetime.utcnow().isoformat(),
}, on_conflict="source_url").execute()
```

### Step 3: Implement `getDeadDocs` in `src/admin/lib/mockData.ts`

```typescript
export async function getDeadDocs(range?: { from?: Date; to?: Date }): Promise<any[]> {
  const { data: docs } = await fromUntyped("document_registry").select("source_url, title");
  if (!docs || docs.length === 0) return [];

  let q = fromUntyped("retrieval_events").select("source_docs");
  if (range?.from) q = q.gte("created_at", range.from.toISOString());
  if (range?.to)   q = q.lte("created_at", range.to.toISOString());
  const { data: events } = await q;

  const hitSources = new Set(
    ((events || []) as any[]).flatMap((e: any) => e.source_docs || [])
  );

  return (docs as any[])
    .filter((d: any) => !hitSources.has(d.source_url))
    .map((d: any) => ({ source_url: d.source_url, title: d.title || d.source_url }));
}
```

### Admin page that lights up

**Retrieval → Dead Docs tab** — shows documents indexed but never retrieved.

---

## Section 5 — Jaeger Embed (CONFIGURATION ONLY)

`TelemetryPage` already renders:
```tsx
<iframe src={import.meta.env.VITE_JAEGER_UI_URL || "http://localhost:16686"} ... />
```

The iframe is blocked by browsers if Jaeger doesn't send correct CORS + CSP headers.

### Step 1: Verify Jaeger is running

```bash
curl -s http://localhost:16686/api/services | jq .
# Expected: {"data":["mukthi-guru-backend"],...}
```

### Step 2: Set env var in `.env.local`

```bash
VITE_JAEGER_UI_URL=http://localhost:16686
```

For production:
```bash
VITE_JAEGER_UI_URL=https://your-domain.com/jaeger
```

### Step 3: Add Jaeger to `backend/docker-compose.yml` (if not already present)

```yaml
  jaeger:
    image: jaegertracing/all-in-one:1.55
    container_name: mukthiguru-jaeger
    ports:
      - "6831:6831/udp"   # Agent UDP
      - "16686:16686"     # Web UI
      - "14268:14268"     # Collector HTTP
    environment:
      - COLLECTOR_OTLP_ENABLED=true
    restart: unless-stopped
```

### Step 4: Nginx reverse proxy with CORS (production only)

```nginx
location /jaeger/ {
    proxy_pass http://jaeger:16686/;
    proxy_set_header Host $host;

    # Allow admin frontend to embed via iframe:
    add_header Access-Control-Allow-Origin "https://your-admin-domain.com" always;
    add_header X-Frame-Options "ALLOW-FROM https://your-admin-domain.com" always;
    add_header Content-Security-Policy "frame-ancestors 'self' https://your-admin-domain.com" always;
}
```

### Admin page that lights up

**Telemetry page** — full Jaeger UI embedded for distributed tracing of all RAG pipeline spans.

---

## Quick Reference

| Admin Page | Needs Backend? | Action |
|---|---|---|
| Overview | No | Seed demo traces |
| Queries + Drill-down | No | Seed demo traces |
| Quality | No | Seed demo traces |
| Retrieval (sources, sim, empty) | No | Seed demo traces |
| **Retrieval (dead docs)** | **Yes** | Section 4 |
| Triggers | No | Seed demo traces |
| Prompts | No | Seed demo traces |
| Evals | No | Seed demo traces |
| Alerts | No | Seed demo traces |
| Logs | No | Seed demo traces |
| Admins | No | Seed demo traces |
| **Ingestion submit** | **Yes** | Section 2 |
| **AskData** | **Yes** | Section 3 |
| **Telemetry (Jaeger)** | **Yes** | Section 5 |
