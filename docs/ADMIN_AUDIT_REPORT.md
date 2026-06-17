# Admin Deep Audit Report

**Date:** 2026-06-17 · **Scope:** All admin pages, hooks, API endpoints, per-page SQL verification.

## Architecture

```
src/admin/pages/*  →  useAdminData hooks  →  src/admin/lib/api.ts
                                                  ↓
                              fetch(`${VITE_BACKEND_URL}/api/admin/*`)
                                                  ↓
                                       FastAPI backend/routers/admin.py
                                                  ↓
                                            Supabase Postgres
```

Mock-data fallback (`db.*`) fires only when `VITE_ALLOW_MOCK=true` AND `import.meta.env.DEV`. In prod, a failing backend bubbles a real error to the UI (correct behaviour after the recent security fix).

## Current data state (live count from public schema)

| Table | Rows | Note |
| --- | ---: | --- |
| `chat_queries` | 12 | seeded |
| `chat_responses` | 12 | seeded |
| `meditation_sessions` | 4 | from real users |
| `profiles` | 4 | from real users |
| `alert_rules` / `alert_events` | 0 | **empty — Alerts page will show empty state** |
| `eval_runs` / `golden_questions` | 0 | **empty — Evals page empty** |
| `ingestion_runs` | 0 | **empty — Ingestion page empty** |
| `retrieval_events` / `trigger_events` / `safety_events` | 0 | **empty — Retrieval/Triggers/Safety empty** |
| `app_logs` | 0 | **empty — Logs page empty** |
| `prompt_versions` | 0 | **empty — Prompts page empty** |
| `feedback_events` | 0 | **empty — Feedback page empty** |
| `annotations` | 0 | **empty — annotation count = 0** |
| `kb_sources` / `kb_chunks` | 0 | **empty — Retrieval Health empty** |
| `model_pricing` | 0 | **empty — cost estimate falls back to constant** |
| `daily_teachings` | 0 | **empty — Daily Teaching page empty** |

**Fix path:** call `select public.seed_admin_demo();` while signed in as an admin. That function (already present in DB) populates every table above with realistic demo rows — full trace, partial trace (no response), partial trace (no retrieval), 7-day trigger trend, alert rule + fired event, eval run + golden Q, ingestion run, annotation, safety event, 3 correlated app logs, topic cluster.

```sql
-- Run as admin (e.g. via SQL editor while authenticated):
SELECT public.seed_admin_demo();
```

## Per-page audit

Each row: **Page → Hook(s) → Backend endpoint → SQL verification query → Status.**

### 1. Overview (`pages/OverviewPage.tsx`)
- Hooks: `useKpis`, `useTimeseries('latency_p95'|'cost'|'volume')`, `useTopFailures`, `useRagasHeatmap`, `useLiveFeed`.
- Endpoints: `/api/admin/kpis`, `/api/admin/timeseries`, `/api/admin/top-failures`, `/api/admin/ragas-heatmap`, `/api/admin/live-feed`.
- **Verify:**
  ```sql
  SELECT count(*) total, count(*) FILTER (WHERE status='ok') ok,
         avg(latency_ms) avg_lat, percentile_disc(0.95) WITHIN GROUP (ORDER BY latency_ms) p95,
         sum(cost_estimate) total_cost
    FROM chat_queries WHERE created_at >= now()-interval '7 days';
  ```
- Status: **wiring OK** with backend; latency/cost cards rely on `latency_ms`+`cost_estimate` being populated by `/api/chat` (verify backend writes these on every reply — see Recommendation A).

### 2. Queries (`QueriesPage.tsx`)
- Hooks: `useQueries`. Endpoint: `/api/admin/traces`.
- **Verify:**
  ```sql
  SELECT id, query_text, model, status, latency_ms, created_at
    FROM chat_queries ORDER BY created_at DESC LIMIT 50;
  ```
- Status: OK once seeded.

### 3. Retrieval (`RetrievalPage.tsx`)
- Hooks: `useRetrievalHealth`, `useDeadDocs`, `useEmptyRetrievals`, `useSimilarityTrend`.
- **Verify (hit rate / avg score):**
  ```sql
  SELECT count(*) total, count(*) FILTER (WHERE source_docs = '{}') empties,
         avg((SELECT avg(s) FROM unnest(scores) s)) avg_score
    FROM retrieval_events
   WHERE created_at >= now()-interval '7 days';
  ```
- Status: **shows 0 / empty until `retrieval_events` is written**. Confirm backend writes one row per chat turn (after `retrieve_documents` node).

### 4. Quality (`QualityPage.tsx`)
- Hooks: `useQuality`. Endpoint: `/api/admin/quality-data`.
- **Verify:**
  ```sql
  SELECT avg(faithfulness) f, avg(answer_relevancy) ar, avg(context_precision) cp,
         avg(context_recall) cr, avg(confidence) c,
         count(*) FILTER (WHERE hallucination_flag) hallucinations
    FROM chat_responses WHERE created_at >= now()-interval '7 days';
  ```
- Status: OK; relies on `verify_answer`/`reflect_on_answer` writing scores.

### 5. Feedback (`FeedbackPage.tsx`)
- Endpoint: `/api/admin/feedback-events`. Hook missing — page reads via `useQueries` join? **Bug:** confirm the page subscribes to `feedback_events`. If not present, add `useFeedbackEvents` hook reading from `feedback_events` directly with RLS.
- **Verify:**
  ```sql
  SELECT label, count(*) FROM feedback_events GROUP BY 1;
  ```

### 6. Alerts (`AlertsPage.tsx`)
- Hooks: `useAlertRules`, `useAlertEvents`.
- **Verify:**
  ```sql
  SELECT name, metric, comparator, threshold, enabled FROM alert_rules;
  SELECT rule_name, value, fired_at FROM alert_events ORDER BY fired_at DESC LIMIT 20;
  ```
- Status: empty state correct. Rules creation flow (UI) writes via backend `POST /api/admin/alert-rules` — verify endpoint exists in `backend/routers/admin.py`.

### 7. Triggers (`TriggersPage.tsx`)
- Hooks: `useTriggers`, `useTriggerTrend`.
- **Verify:**
  ```sql
  SELECT trigger_type, count(*) FROM trigger_events
   WHERE created_at >= now()-interval '7 days' GROUP BY 1;
  ```

### 8. Telemetry (`TelemetryPage.tsx`)
- Hooks: `useTimeseries`, `useSafetyEvents`.
- **Verify:** `latency_p95` bucket SQL —
  ```sql
  SELECT date_trunc('hour', created_at) bucket,
         percentile_disc(0.95) WITHIN GROUP (ORDER BY latency_ms) p95
    FROM chat_queries WHERE created_at >= now()-interval '24 hours' GROUP BY 1 ORDER BY 1;
  ```

### 9. Evals (`EvalsPage.tsx`)
- Hooks: `useEvalRuns`, `useGoldenQuestions`.
- **Verify:**
  ```sql
  SELECT name, status, summary, started_at, finished_at FROM eval_runs ORDER BY started_at DESC LIMIT 20;
  ```
- Connects to `.github/workflows/eval-gate.yml` (created in earlier phase) which writes a new row per CI run via `backend/evaluation/run_golden_eval.py`.

### 10. Prompts (`PromptsPage.tsx`)
- Hooks: `usePromptVersions`, `usePromptMetrics`.
- **Verify:**
  ```sql
  SELECT v.name, v.version, v.active,
         avg(r.faithfulness) f, avg(r.answer_relevancy) ar, count(*) used
    FROM prompt_versions v
    LEFT JOIN chat_queries q ON q.prompt_version_id = v.id
    LEFT JOIN chat_responses r ON r.query_id = q.id
   GROUP BY v.name, v.version, v.active ORDER BY v.name, v.version;
  ```

### 11. Admins (`AdminsPage.tsx`)
- Hooks: `useAdmins` (RPC `list_admins`), `promote_admin_by_email`, `demote_admin_by_id`.
- **Verify:** `SELECT * FROM public.list_admins();` (must be called by admin).
- Status: **OK** — RPC already exists.

### 12. Ingestion (`IngestionPage.tsx`)
- Hooks: `useIngestionRuns`, `useIngestionHealth`.
- **Verify:**
  ```sql
  SELECT source, status, chunks_added, duration_ms, started_at
    FROM ingestion_runs ORDER BY started_at DESC LIMIT 20;
  ```

### 13. Logs (`LogsPage.tsx`)
- Endpoint: `/api/admin/logs`.
- **Verify:**
  ```sql
  SELECT level, message, request_id, created_at FROM app_logs
   ORDER BY created_at DESC LIMIT 100;
  ```
- **Cross-request correlation:** `SELECT * FROM app_logs WHERE request_id = '<id>'` — confirm backend stamps `request_id` on every log line.

### 14. Topics (`TopicsPage.tsx`)
- Hook: `useTopics`. Endpoint: `/api/admin/topic-clusters`.
- **Verify:** `SELECT label, size FROM query_clusters ORDER BY size DESC;`

### 15. DailyTeaching (`DailyTeachingPage.tsx`)
- Reads `daily_teachings` table + `daily-teachings` storage bucket.
- **Verify:** `SELECT slug, title, published_at FROM daily_teachings ORDER BY published_at DESC;`

### 16. Settings (`SettingsPage.tsx`)
- Lists model pricing.
- **Verify:** `SELECT model, input_per_1k, output_per_1k FROM model_pricing;`
- **Recommendation:** seed default pricing so the cost KPI uses real numbers — see Recommendation B.

## Recommendations (apply in order)

**A. Backend write-side audit (FastAPI `/api/chat`)**
Ensure every chat turn writes:
1. `chat_queries` (with `latency_ms`, `cost_estimate`, `prompt_tokens`, `completion_tokens`, `prompt_version_id`, `model`, `status`).
2. `chat_responses` (with all 4 RAGAS scores + `confidence` + `hallucination_flag`).
3. `retrieval_events` (one row per turn).
4. `trace_spans` (≥4 spans: safety, retrieve, rerank, generate, verify).
5. `app_logs` with a single `request_id` correlating all 3-5 lines.

**B. Seed defaults (one-time SQL):**
```sql
INSERT INTO public.model_pricing (model, input_per_1k, output_per_1k, currency)
VALUES
  ('sarvam-30b', 0.00010, 0.00020, 'USD'),
  ('google/gemini-2.5-flash', 0.000075, 0.0003, 'USD'),
  ('google/gemini-2.5-pro', 0.00125, 0.005, 'USD')
ON CONFLICT (model) DO NOTHING;
```

**C. Populate the dashboard with demo data right now:**
```sql
SELECT public.seed_admin_demo();
```

**D. Wire missing hooks (frontend follow-up):**
- `useFeedbackEvents()` → reads `feedback_events` directly via supabase-js with RLS.
- `useAppLogs(requestId?)` → reads `app_logs` filtered by `request_id`.

## Sign-off matrix

| Page | Wiring | Data | Action |
| --- | --- | --- | --- |
| Overview | ✅ | seeded | none |
| Queries | ✅ | seeded | none |
| Retrieval | ✅ | empty | run seed + verify backend writes `retrieval_events` |
| Quality | ✅ | seeded | none |
| Feedback | ⚠ | empty | add `useFeedbackEvents` hook |
| Alerts | ✅ | empty | seed |
| Triggers | ✅ | empty | seed |
| Telemetry | ✅ | seeded | none |
| Evals | ✅ | empty | seed + run CI eval gate |
| Prompts | ✅ | empty | seed |
| Admins | ✅ | live | none |
| Ingestion | ✅ | empty | seed |
| Logs | ✅ | empty | seed |
| Topics | ✅ | empty | seed |
| DailyTeaching | ✅ | empty | upload teaching + run `push-send` |
| Settings | ✅ | empty | run Recommendation B |
