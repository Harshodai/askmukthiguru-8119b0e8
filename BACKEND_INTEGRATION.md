# Admin Console — Backend Integration Plan

Most admin pages now read directly from Lovable Cloud (Supabase) and work
end-to-end. The four features below cannot be implemented from the React
client and require small additions to the FastAPI backend
(`backend/app/main.py`). Each section is independent — implement only what
you need.

Test order: **(1) Telemetry sink** is the prerequisite for everything else.
Without it the chat pipeline doesn't write rows to `chat_queries`/
`chat_responses`/`retrieval_events`/etc., so the admin pages stay empty
outside of the "Seed demo traces" button.

---

## 0. Shared setup (do this once)

### Env vars (add to `backend/.env`)

```bash
SUPABASE_URL=https://fynkjimvuimakgtidvuq.supabase.co
SUPABASE_SERVICE_ROLE_KEY=<from Lovable Cloud → Connectors → Backend Secrets>
SUPABASE_JWKS_URL=https://fynkjimvuimakgtidvuq.supabase.co/auth/v1/.well-known/jwks.json
```

> The service-role key bypasses RLS. Never expose it to the browser. It must
> live only on the backend.

### Install client

```bash
cd backend
pip install "supabase==2.*" "PyJWT[crypto]>=2.8"
```

### Verify

```bash
python -c "import os; from supabase import create_client; \
c = create_client(os.environ['SUPABASE_URL'], os.environ['SUPABASE_SERVICE_ROLE_KEY']); \
print(c.table('chat_queries').select('id').limit(1).execute())"
```

---

## 1. Telemetry sink — make all admin pages light up

**Lights up:** Overview, Queries, Quality, Retrieval, Triggers, Topics,
Prompts, Logs, Alerts (most pages).

Create `backend/app/telemetry_sink.py`:

```python
import os, asyncio, time, uuid
from supabase import create_client

_sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_ROLE_KEY"])

def _safe_insert(table: str, row: dict) -> None:
    try:
        _sb.table(table).insert(row).execute()
    except Exception as e:
        print(f"[telemetry] {table} insert failed: {e}")

async def record_chat_turn(*, query_id, user_id, query_text, model, prompt_version_id,
                           response_text, citations, latency_ms, prompt_tokens,
                           completion_tokens, cost_estimate, status, faithfulness,
                           answer_relevancy, context_precision, context_recall,
                           hallucination_flag, confidence, judge_reasoning,
                           retrieved_docs, retrieval_scores, spans, triggers,
                           safety_events, request_id, log_lines):
    """Fire-and-forget — wrap in asyncio.create_task() from the chat handler."""
    _safe_insert("chat_queries", {
        "id": str(query_id), "user_id": str(user_id) if user_id else None,
        "query_text": query_text, "model": model,
        "prompt_version_id": str(prompt_version_id) if prompt_version_id else None,
        "status": status, "latency_ms": latency_ms,
        "prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens,
        "cost_estimate": cost_estimate,
    })
    if response_text is not None:
        _safe_insert("chat_responses", {
            "query_id": str(query_id), "response_text": response_text,
            "citations": citations, "faithfulness": faithfulness,
            "answer_relevancy": answer_relevancy, "context_precision": context_precision,
            "context_recall": context_recall, "hallucination_flag": hallucination_flag,
            "confidence": confidence, "judge_reasoning": judge_reasoning,
        })
    if retrieved_docs:
        _safe_insert("retrieval_events", {
            "query_id": str(query_id),
            "source_docs": retrieved_docs, "scores": retrieval_scores,
        })
    for span in spans:
        _safe_insert("trace_spans", {
            "query_id": str(query_id), "span_name": span["name"],
            "start_ms": span["start_ms"], "duration_ms": span["duration_ms"],
        })
    for t in triggers:
        _safe_insert("trigger_events", {
            "query_id": str(query_id), "trigger_type": t["type"],
            "trigger_name": t["name"], "payload": t.get("payload", {}),
        })
    for s in safety_events:
        _safe_insert("safety_events", {
            "query_id": str(query_id), "rule": s["rule"], "severity": s.get("severity"),
            "action": s.get("action"), "type": s.get("type"), "excerpt": s.get("excerpt"),
        })
    for line in log_lines:
        _safe_insert("app_logs", {
            "level": line["level"], "message": line["message"],
            "context": line.get("context", {}), "request_id": request_id,
        })
```

### Wire it into the chat handler

In the chat handler in `backend/app/main.py`, after the LangGraph run
returns the final state, schedule the telemetry write so it does not
block the response:

```python
import asyncio, uuid
from app.telemetry_sink import record_chat_turn

@router.post("/api/chat")
async def chat_handler(req, current_user = Depends(...)):
    query_id = uuid.uuid4()
    request_id = req.headers.get("x-request-id") or uuid.uuid4().hex[:12]
    started = time.time()
    state = await graph.ainvoke({...})
    latency_ms = int((time.time() - started) * 1000)

    asyncio.create_task(record_chat_turn(
        query_id=query_id, user_id=current_user.id,
        query_text=req.user_message, model=state["model_used"],
        prompt_version_id=state.get("prompt_version_id"),
        response_text=state["answer"], citations=state.get("citations", []),
        latency_ms=latency_ms, prompt_tokens=state["prompt_tokens"],
        completion_tokens=state["completion_tokens"],
        cost_estimate=state.get("cost", 0),
        status="ok",
        faithfulness=state["judge"]["faithfulness"],
        answer_relevancy=state["judge"]["answer_relevancy"],
        context_precision=state["judge"]["context_precision"],
        context_recall=state["judge"]["context_recall"],
        hallucination_flag=state["judge"]["hallucination_flag"],
        confidence=state["judge"]["confidence"],
        judge_reasoning=state["judge"]["reasoning"],
        retrieved_docs=[d["source"] for d in state.get("retrieved", [])],
        retrieval_scores=[d["score"] for d in state.get("retrieved", [])],
        spans=state.get("spans", []),
        triggers=state.get("triggers", []),
        safety_events=state.get("safety_events", []),
        request_id=request_id,
        log_lines=state.get("log_lines", []),
    ))
    return state["answer"]
```

### Verify

1. Send one chat message from the production frontend.
2. In Lovable Cloud → Backend → Tables → `chat_queries`, row count should
   increase by 1 within 2 s.
3. Open `/admin` → Overview KPIs should reflect the new row.

---

## 2. Ingestion API — make the Ingestion page submit + show progress

**Lights up:** Ingestion page form, "Re-ingest" buttons.

The frontend already calls:

- `POST /api/admin/ingest` — body `{ url: string, max_accuracy: boolean }`
- `GET  /api/admin/ingest/status` — returns `Record<url, { status, message, progress }>`

Both must be JWT-protected. Implement in FastAPI:

```python
from fastapi import APIRouter, Depends, HTTPException
from app.dependencies import get_container
from app.auth import require_admin  # JWT verify via SUPABASE_JWKS_URL

router = APIRouter(prefix="/api/admin", dependencies=[Depends(require_admin)])

@router.post("/ingest")
async def submit_ingest(body: dict):
    container = get_container()
    job_id = await container.ingestion.enqueue(body["url"], body.get("max_accuracy", False))
    return {"ok": True, "job_id": job_id, "message": "Ingestion queued"}

@router.get("/ingest/status")
async def ingest_status():
    container = get_container()
    return container.ingestion.snapshot()  # { url: { status, message, progress } }
```

At completion, insert into `ingestion_runs` with `source`, `status`,
`chunks_added`, `duration_ms`, optional `error_log`. The Ingestion page
will refresh automatically.

### Verify

```bash
curl -X POST https://<backend>/api/admin/ingest \
  -H "Authorization: Bearer $JWT" \
  -H "Content-Type: application/json" \
  -d '{"url":"https://youtu.be/abc","max_accuracy":false}'
```

---

## 3. AskData (NL → analytics) on the Overview page

**Lights up:** the AskDataPanel chat input on Overview.

Frontend currently calls `db.askData(prompt)` which returns a stub string.
Replace the body of `askData()` in `src/admin/lib/mockData.ts` with a fetch
to the backend, then implement:

```python
@router.post("/ai/ask-data")
async def ask_data(body: dict):
    question = body["question"]
    kpi_context = body.get("kpi_context", "")
    # Use Lovable AI Gateway (preferred — no separate key needed)
    from openai import AsyncOpenAI
    client = AsyncOpenAI(
        base_url="https://ai.gateway.lovable.dev/v1",
        api_key=os.environ["LOVABLE_API_KEY"],
    )
    sys = ("You are an analytics assistant. Given the KPI snapshot, answer "
           "the question in 2-4 markdown sentences. Be concrete.")
    r = await client.chat.completions.create(
        model="google/gemini-2.5-flash",
        messages=[
            {"role": "system", "content": sys},
            {"role": "user", "content": f"KPIs:\n{kpi_context}\n\nQ: {question}"},
        ],
    )
    return {"answer": r.choices[0].message.content}
```

For richer analytics (NL→SQL over `chat_queries`), have the model emit a
read-only SQL string, validate against an allow-list of tables, and execute
via the service-role client.

---

## 4. Dead-docs detection (Retrieval page → Dead tab)

**Lights up:** Retrieval page → "Dead docs" tab.

`getDeadDocs()` currently returns `[]` because there is no document
registry. Add one:

```sql
CREATE TABLE public.document_registry (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  source text NOT NULL UNIQUE,
  title text,
  ingested_at timestamptz NOT NULL DEFAULT now(),
  last_retrieved_at timestamptz
);
GRANT SELECT ON public.document_registry TO authenticated;
GRANT ALL    ON public.document_registry TO service_role;
ALTER TABLE public.document_registry ENABLE ROW LEVEL SECURITY;
CREATE POLICY "admins read document_registry" ON public.document_registry
  FOR SELECT TO authenticated USING (public.has_role(auth.uid(), 'admin'));
```

The ingestion pipeline upserts a row per source; `record_chat_turn`
updates `last_retrieved_at` for each retrieved source. Then replace
`getDeadDocs` in `mockData.ts`:

```ts
export async function getDeadDocs(range?: { from?: Date }) {
  const cutoff = range?.from?.toISOString() ?? new Date(Date.now() - 30 * 86400000).toISOString();
  const { data } = await fromUntyped("document_registry")
    .select("source, title, last_retrieved_at")
    .or(`last_retrieved_at.is.null,last_retrieved_at.lt.${cutoff}`)
    .order("last_retrieved_at", { ascending: true, nullsFirst: true });
  return (data || []).map((d: any) => ({ source: d.source }));
}
```

---

## 5. Telemetry page (Jaeger embed)

The `TelemetryPage` already iframes `import.meta.env.VITE_JAEGER_UI_URL`
(defaults to `http://localhost:16686`). For production:

1. Reverse-proxy Jaeger behind nginx on a TLS subdomain (e.g.
   `https://jaeger.askmukthiguru.com`).
2. Set `Content-Security-Policy: frame-ancestors https://askmukthiguru.lovable.app`
   on the Jaeger response.
3. Set the env var on the frontend host: `VITE_JAEGER_UI_URL=https://jaeger.askmukthiguru.com`.

Without these, the iframe will be blocked by `X-Frame-Options`.

---

## Page-by-page verification matrix

| Page | Status today | Lights up after |
|---|---|---|
| Overview KPIs + charts | ✅ works (Lovable Cloud) | Telemetry sink populates real data |
| Queries list + drill-down | ✅ works | Telemetry sink |
| Quality (RAGAS, low-conf, disagreement) | ✅ works | Telemetry sink |
| Retrieval (sources, sim trend, empty) | ✅ works | Telemetry sink |
| Retrieval (dead tab) | ⚠ always empty | Section 4 (document_registry) |
| Triggers | ✅ works | Telemetry sink |
| Topics | ✅ works (uses `query_clusters` — populate via batch job) | — |
| Prompts | ✅ works | Telemetry sink (so per-version metrics are non-zero) |
| Evals | ✅ works | Insert real runs from your eval pipeline |
| Ingestion (read) | ✅ works | Backend writes `ingestion_runs` |
| Ingestion (submit + status) | ⚠ requires backend | Section 2 |
| Logs | ✅ works | Telemetry sink emits `app_logs` |
| Telemetry (Jaeger) | ⚠ blocked by CSP | Section 5 |
| Alerts | ✅ works | Backend rule-evaluator writes to `alert_events` |
| Daily Teaching | ✅ works (Storage) | — |
| Feedback | ✅ works (localStorage) | — |
| Admins (list/promote/demote) | ✅ works (RPCs) | — |
| Settings (retention, exports) | ✅ works | — |
| AskData panel | ⚠ stub string | Section 3 |

Anything ⚠ above renders without crashing — it just shows an empty state
or a "Backend required" message until the corresponding section is
implemented.
