# Admin console — make every page + drill-down actually work

## Audit (what's broken today)

I walked every page in `src/admin/pages/*` and traced its hook → `api.ts` → `mockData.ts` → Supabase. The console has three classes of breakage:

### A. Pages whose data layer returns hard-coded `[]` / `null`
`mockData.ts` currently stubs these to empty results, so the page renders but shows nothing:

| Page | Stub returning empty |
|---|---|
| Retrieval (sources / sim trend / empty / dead) | `getRetrievalHealth`, `getSimilarityTrend`, `getEmptyRetrievals`, `getDeadDocs` |
| Quality (disagreement / low-conf / RAGAS heatmap) | `getQualityData`, `getRagasHeatmap` |
| Triggers (14-day stacked area) | `getTriggerTrend` |
| Prompts (per-version metric bars) | `getPromptMetricsByVersion` |
| Overview "Top sources" tab | depends on `getRetrievalHealth` |

### B. UI reads columns that don't exist in the DB
The UI types were authored against a richer eventual schema. Today's tables are slimmer, so pages either render blank cells or silently 500:

| Table | Columns UI expects but DB lacks |
|---|---|
| `alert_rules` | `active`, `window_minutes`, `channel`, `target` (DB has `enabled` only) |
| `alert_events` | `rule_name`, `resolved_at` |
| `eval_runs` | `triggered_by`, structured `summary.{passed,total,avg_*}` |
| `golden_questions` | `active`, `expected_sources` |
| `annotations` | `label`, `notes`, `promoted_to_golden`, `response_id` |
| `safety_events` | `type`, `excerpt` (DB has `rule`, `details`) |
| `ingestion_runs` | `duration_ms`, `error_log` |
| `app_logs` | `request_id` (used to group logs) |
| `chat_queries` | already OK; `prompt_version_id` exists |

### C. Mutations that are no-ops or impossible from client
| Function | Issue |
|---|---|
| `promoteAdmin(email)` | Needs `auth.users` email lookup → must be a SECURITY DEFINER RPC |
| `demoteAdmin`, `upsertAlertRule`, `upsertGoldenQuestion`, `deleteGoldenQuestion`, `upsertModelPricing`, `activatePromptVersion` | All currently no-op or partial; need straight upsert/delete |
| `listAdmins` | Joins `auth_users:user_id(email)` which isn't a real FK → must be an RPC |
| `triggerReingest(source)` | Hits FastAPI ingestion pipeline — out of Lovable's reach |
| `askData(prompt)` | Needs LLM call against telemetry — backend |
| `submitIngestion` (Ingestion page form) | Hits FastAPI — backend |

### D. Trace drill-down
`TraceDrawer` was already hardened in the previous turn (guarded `trace.prompt`, `trace.retrieval`, `trace.response`, `trace.feedback`, `trace.triggers`). I'll verify nothing regressed and that the seed produces a clickable trace end-to-end.

---

## What I'll change

### 1. One migration — extend existing tables + add the two RPCs we need

```text
ALTER alert_rules     ADD window_minutes int, channel text, target text;
                      RENAME enabled → active (keep both via view if needed; pick rename)
ALTER alert_events    ADD rule_name text, resolved_at timestamptz
ALTER eval_runs       ADD triggered_by text DEFAULT 'manual', prompt_version_id uuid
ALTER golden_questions ADD active boolean DEFAULT true, expected_sources text[] DEFAULT '{}'
ALTER annotations     ADD label text, notes text, promoted_to_golden boolean DEFAULT false, response_id uuid
ALTER safety_events   ADD type text, excerpt text
ALTER ingestion_runs  ADD duration_ms int, error_log text
ALTER app_logs        ADD request_id text DEFAULT ''

CREATE FUNCTION public.list_admins() …            -- joins auth.users for email
CREATE FUNCTION public.promote_admin_by_email() … -- looks up auth.users
CREATE FUNCTION public.demote_admin_by_id(uuid) …

-- extend seed_admin_demo() to also seed: 1 alert rule, 1 fired event,
--   1 prompt v1+v2 with responses tagged, 1 eval run, 1 golden q,
--   1 ingestion run, 1 annotation, 1 safety event, a few app_logs
--   with a shared request_id, 1 trigger over 7 days for trend.
```

All `GRANT`s, RLS unchanged (admin-only).

### 2. Rewrite the stubs in `src/admin/lib/mockData.ts`

Real Supabase queries for:
- `getRetrievalHealth` → aggregate `retrieval_events` + `chat_responses.faithfulness` per source
- `getSimilarityTrend` → bucketize `retrieval_events.scores[0]`
- `getEmptyRetrievals` → `retrieval_events` where `array_length(source_docs)=0`
- `getDeadDocs` → returns `[]` with a comment (needs document registry — backend doc)
- `getQualityData` → disagreement (feedback rating vs faithfulness), low-confidence list
- `getRagasHeatmap` → bucketize `chat_responses.{faithfulness,relevancy,precision,recall}`
- `getTriggerTrend` → bucketize `trigger_events` grouped by `trigger_name` over N days
- `getPromptMetricsByVersion` → group `chat_responses` joined to `chat_queries.prompt_version_id`
- `upsertAlertRule`, `upsertGoldenQuestion`, `deleteGoldenQuestion`, `upsertModelPricing` → real upserts/deletes
- `promoteAdmin`, `demoteAdmin`, `listAdmins` → call the new RPCs
- `triggerReingest`, `askData` → keep as no-op + `toast.info("Backend required — see BACKEND_INTEGRATION.md")`

### 3. New file `BACKEND_INTEGRATION.md`

Step-by-step for the four things Lovable cannot do client-side:
1. **Telemetry sink** — FastAPI `chat` handler writing into `chat_queries`, `chat_responses`, `retrieval_events`, `trace_spans`, `trigger_events`, `safety_events`, `app_logs` via `SUPABASE_SERVICE_ROLE_KEY`. Includes the exact `telemetry_sink.py` module skeleton.
2. **Ingestion API** — `POST /api/ingest`, `GET /api/ingest/status` contract used by `IngestionPage`. Required env: `BACKEND_URL`, JWT verification using `SUPABASE_JWKS`.
3. **AskData / NL→SQL** — backend endpoint that takes the KPI context + question, calls Lovable AI Gateway, returns markdown. Sample FastAPI route.
4. **Document registry for dead-docs** — `document_registry` table populated at ingestion time; query in `getDeadDocs`.
5. **Jaeger embed** — the `TelemetryPage` already iframes `VITE_JAEGER_UI_URL`; doc the reverse-proxy + CORS settings.

Each section: env vars, table schema needed, exact endpoint signature, curl test command, expected admin page that lights up.

### 4. Verification

After migration runs and the seed RPC is re-executed:
- Click "Seed demo traces" → invalidate React Query → every list page should show ≥1 row.
- Open Queries → click row → drawer shows spans, retrieval, response, judge bars, triggers.
- Open Prompts → bar chart renders v1/v2 metrics.
- Open Retrieval → sources tab populated, sim trend chart has points.
- Open Quality → RAGAS heatmap renders, low-conf list has the partial-trace row.
- Open Triggers → 7-day stacked area shows data.
- Open Alerts → rule list + fired event row.
- Open Evals → run row + 1 golden question.
- Open Logs → grouped-by-request-id button works.
- Open Admins → current admin email shown via `list_admins()` RPC.
- Ingestion + AskData + Reingest → show "Backend required" toast (expected).

### 5. Files

- `supabase/migrations/<ts>_admin_console_completeness.sql` (new)
- `src/admin/lib/mockData.ts` (rewrite stubs)
- `BACKEND_INTEGRATION.md` (new, at repo root)
- `src/admin/types.ts` (only widen `AlertRule.active`/`enabled` union if needed — no breaking changes)

### Out of scope

- Building the FastAPI endpoints themselves (documented instead).
- Re-skinning any admin page.
- Touching `/chat` or auth flow.

Approve and I'll execute the migration first, then the code + doc in one batch.
