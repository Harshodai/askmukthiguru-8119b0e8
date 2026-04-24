
# Admin Observability Dashboard — UI-First Build Plan

## Scope (locked from your answers)

- **UI only first**, no Lovable Cloud yet. All data comes from a typed mock layer that mirrors the eventual schema 1:1, so swapping to real Cloud later is a drop-in change.
- **Stack correction**: actual project is React 18 + Vite + `react-router-dom` + Recharts + shadcn (NOT TanStack Start). All routes/auth/data hooks redesigned around this.
- **Everything in the plan** in scope, plus the four explicit additions: View-trace drawer, global date-range picker, Queries filters (prompt/model/min judge score), Export-trace button (JSON + CSV).
- **Docs**: full backend integration docs written into the repo so the askmukthiguru chat backend can wire in later.

---

## 1. Auth model (UI-only phase)

- New route `/admin/login` — isolated page (no app shell, no chat header).
- Mock auth via `localStorage` key `admin_session` with a hardcoded dev credential (`admin / admin` for now, surfaced on the login screen with a "DEV MODE" badge).
- `useAdminGuard()` hook redirects to `/admin/login` if the session flag is missing.
- All this is structured so that when Cloud is enabled later, only `src/admin/lib/adminAuth.ts` changes — the guard/hook signatures stay identical. Real implementation will use Supabase auth + `user_roles` table + `has_role()` security-definer RPC (industry-standard, RLS-safe).

---

## 2. Mock data layer (the seam that becomes Cloud later)

Single module `src/admin/lib/mockData.ts` exposes a typed API that mirrors the eventual server functions:

```
listQueries({ from, to, promptVersion, model, minJudgeScore, search, limit })
getQueryTrace(queryId)            // returns spans, retrievals, response, judge, triggers, prompt
getKpis({ from, to })
getTimeseries({ metric, from, to, bucket })
listPromptVersions() / listModels()
listTriggers({ from, to })
listSafetyEvents({ from, to })
listEvalRuns() / getEvalRun(id)
listIngestionRuns() / listLogs() / listAlertRules() / listFiredAlerts()
listTopicClusters() / listAdmins()
askData(question)                  // returns { sql, rows } from a small local rule-based stub
```

A seed generator produces ~500 deterministic chat queries spanning the last 30 days with realistic distributions: latencies (p50 ~900ms, p95 ~3.4s), 8% hallucination rate, 12% serene_mind triggers, 4 prompt versions, 3 models, 6 source docs, 8 topic clusters. Same seed → same data, so screenshots stay reproducible.

Types live in `src/admin/types.ts` and exactly match the SQL schema in section 6 of the plan. When Cloud is enabled later, we replace the body of each mock function with a `supabase.from(...)` call — types unchanged.

---

## 3. Routes (react-router-dom, added above the catch-all in `App.tsx`)

| Path | Component |
|---|---|
| `/admin/login` | `AdminLoginPage` |
| `/admin` | `AdminLayout` wrapping all of the below as nested routes |
| `/admin` (index) | `OverviewPage` |
| `/admin/queries` | `QueriesPage` |
| `/admin/quality` | `QualityPage` |
| `/admin/retrieval` | `RetrievalPage` |
| `/admin/triggers` | `TriggersPage` |
| `/admin/topics` | `TopicsPage` |
| `/admin/prompts` | `PromptsPage` |
| `/admin/evals` | `EvalsPage` |
| `/admin/ingestion` | `IngestionPage` |
| `/admin/logs` | `LogsPage` |
| `/admin/alerts` | `AlertsPage` |
| `/admin/settings` | `SettingsPage` |
| `/admin/admins` | `AdminsPage` |

`AdminLayout` renders an isolated shell (its own sidebar + topbar) — does NOT use `AppShell`, `Navbar`, or `SafetyDisclaimer`. The end-user app shell is unchanged.

---

## 4. Global controls (top bar of admin shell)

- **Date-range picker** (shadcn calendar in popover, presets: Last 1h / 24h / 7d / 30d / Custom). Stored in `useAdminFiltersStore` (Zustand-style via React context — no new dep). Every page reads `{ from, to }` from this store; KPIs/charts/tables refetch via React Query when it changes.
- **Refresh** button (manual invalidate).
- **Environment badge** ("UI PREVIEW — mock data" until Cloud is wired).
- **Logout** (clears `admin_session`).

---

## 5. Pages — what each shows

**Overview** — 8 KPI cards (queries, p50/p95 latency, hallucination %, serene_mind trigger %, thumbs-up %, est. cost, error rate). 2 time-series charts (volume, latency p50/p95). 3 top-N lists (queries, sources, failures). Live feed tab (polls mock every 3s for now). AskDataPanel (rule-based stub answering 6 canned questions like "top hallucinating prompt last 7 days").

**Queries** — Filter bar (search, prompt version, model, min judge score 0–1 slider, status). Table (time, query preview, model, prompt v, latency, judge score, hallucination badge, feedback). Row click → **TraceDrawer**.

**TraceDrawer** (the headline addition):
- Header: query text, timestamp, copy-id button, Export ▼ (JSON / CSV).
- **Span Waterfall** (custom Recharts horizontal bar component) — embed → vector_search → rerank → llm → judge with start offsets and durations.
- **Prompt & Model**: prompt name + version (linked to Prompts page), model id, token counts, est. cost.
- **Judge scores**: 4 RAGAS bars (faithfulness, answer_relevancy, context_precision, context_recall), hallucination flag, judge reasoning text.
- **Retrieved chunks**: ranked list with similarity scores, source doc, snippet.
- **Final response**: rendered with citations.
- **Triggers**: serene_mind etc.
- **Feedback**: rating + comment if any.
- "Promote to golden dataset" and "Add annotation" buttons (no-op toast in UI phase).

**Export trace** — `src/admin/lib/exportTrace.ts`:
- JSON: full trace object pretty-printed, filename `trace_{queryId}_{ts}.json`.
- CSV: flat tabular form, three sections (metadata, spans, retrievals) concatenated with section headers; download via Blob + anchor.

**Quality** — RAGAS heatmap (4 metrics × time buckets), judge-vs-user disagreement queue (judge says fine but user thumbs-down, or vice versa), low-confidence list, **Safety** tab (prompt_injection / pii / toxicity events), Annotations tab.

**Retrieval** — Hit rate KPI, empty-retrieval queries, top sources table, dead docs (sources never retrieved in window), avg similarity trend, per-source faithfulness contribution bar.

**Triggers** — Per-trigger counts + 30-day trend (highlights `serene_mind`), breakdown by intent, drill-down → filtered Queries page.

**Topics** — Bubble chart (Recharts ScatterChart with size encoding): size = volume, color = avg faithfulness, label = cluster name. Click bubble → drill-down list.

**Prompts** — Version registry table, activate/rollback buttons (UI-only), side-by-side diff (two `<pre>` blocks with line-level highlighting via simple LCS), per-version metric comparison chart.

**Evals** — Golden dataset CRUD (table + dialog form, persisted to mock store), run history table, regression diff vs prior run (delta arrows on each metric).

**Ingestion** — Recent runs table, failure log expanded inline, source health KPIs, "Trigger re-ingest" stub button.

**Logs** — Filter bar (level, search, time), virtualized log list, request-id click groups all logs for that trace.

**Alerts** — Rule builder (name, metric dropdown, comparator, threshold, window, channel), fired-alerts history table. Pre-seed 5 example rules: hallucination >15%, p95 >5s, error rate >2%, cost spike, retrieval hit <80%.

**Settings** — Retention policy slider, PII redaction toggle, Export buttons (CSV of any table), `model_pricing` editor table.

**Admins** — Promote by email, demote, list. UI-only (writes to mock store).

---

## 6. Components built once, reused

`src/admin/components/`:
`AdminShell`, `AdminSidebar`, `AdminTopbar`, `DateRangePicker`, `KpiCard`, `TimeseriesChart`, `Heatmap`, `BubbleChart`, `SpanWaterfall`, `TraceDrawer`, `QueriesFilterBar`, `JudgeScoreBars`, `HallucinationBadge`, `LogStream`, `PromptDiff`, `EvalRunComparison`, `AlertRuleBuilder`, `AskDataPanel`, `LiveFeed`, `EnvBadge`, `ExportMenu`, `EmptyState`, `MetricDelta`.

All built with shadcn primitives already in the project. No new deps required (recharts, date-fns, zod, react-hook-form, lucide-react are all present).

---

## 7. Docs written into the repo

Folder `docs/admin/` (all new):

- **`README.md`** — what the admin area is, who can access it, current phase (UI mock).
- **`architecture.md`** — diagram (ASCII) of telemetry flow, data model overview, isolation between admin and end-user UI, security posture.
- **`schema.sql`** — the full migration from your plan (every table + RLS + has_role + indexes), ready to run when Cloud is enabled. Notes which extensions to test (pgvector, pg_cron, realtime publication) with `DO` blocks that fail gracefully.
- **`backend-integration.md`** — for the askmukthiguru chat code:
  - the 5-line wiring (`recordQuery` → `withSpan` → `recordRetrieval` → `recordResponse` → `recordTrigger`)
  - service-role write pattern (server-only, never client)
  - judge prompt + tool-call schema (the exact JSON tool spec for `google/gemini-2.5-flash` returning all 4 RAGAS scores + safety in one call)
  - span naming convention (`embed | vector_search | rerank | llm | judge | guardrails`)
  - cost calc formula using `model_pricing` table
  - PII redaction rules before persisting `query_text` / `response_text`
- **`evals.md`** — golden dataset format, how to add questions, how the regression diff works, how to wire an external scheduler (cron-job.org, GitHub Actions, or upgrade to `pg_cron`) to the eventual `/api/public/cron/{job}` endpoint with HMAC verification.
- **`alerts.md`** — rule semantics, evaluator pseudocode, channel adapters (email, webhook, Slack).
- **`migration-plan.md`** — step-by-step from UI-mock → Cloud-backed:
  1. Enable Lovable Cloud
  2. Run `schema.sql`
  3. Seed first admin in `user_roles`
  4. Replace each function in `src/admin/lib/mockData.ts` with the real Supabase query (file-by-file checklist)
  5. Swap mock auth in `adminAuth.ts` for Supabase auth + `has_role`
  6. Move telemetry writes to edge functions (service-role)
  7. Enable Realtime on `chat_queries`
  8. Wire the cron endpoint
- **`deep-research.md`** — annotated references for every concept used: RAGAS (faithfulness / answer_relevancy / context_precision / context_recall definitions and judge-prompt patterns), CRAG, Self-RAG, CoVe, Stimulus RAG, OTel-inspired tracing, hallucination detection via LLM-as-judge, prompt-injection detection patterns, golden-dataset regression testing, semantic clustering with k-means over embeddings, Supabase RLS + security-definer pattern, why role-storage on a separate table prevents privilege escalation. Each section: 3–5 sentence summary + 2–4 authoritative links (papers / docs).

---

## 8. Files created (summary)

**Pages**: `src/admin/pages/` — 14 page files listed in section 3.

**Layout & shared**: `src/admin/layout/AdminShell.tsx`, `AdminSidebar.tsx`, `AdminTopbar.tsx`, `AdminLoginPage.tsx`.

**Components**: `src/admin/components/` — ~22 components from section 6.

**Lib**: `src/admin/lib/` — `adminAuth.ts`, `mockData.ts`, `seed.ts`, `exportTrace.ts`, `filtersStore.tsx` (context), `useAdminGuard.ts`, `formatters.ts`.

**Types**: `src/admin/types.ts`.

**Hooks**: `src/admin/hooks/` — `useKpis`, `useQueries`, `useQueryTrace`, `useTimeseries`, `useDateRange`, etc. (React Query wrappers around `mockData`).

**Routing**: edits to `src/App.tsx` to add `/admin/login` and `/admin/*` above the catch-all, wrapped so the end-user `AppShell`/disclaimer don't appear inside `/admin`.

**Docs**: `docs/admin/` — 7 markdown files from section 7.

**Tests** (vitest): `src/admin/lib/exportTrace.test.ts` (JSON+CSV correctness), `src/admin/lib/mockData.test.ts` (filter combinations), `src/admin/components/SpanWaterfall.test.tsx` (renders spans in time order).

---

## 9. Build order

1. Types + mock data + seed + filters store + admin auth stub.
2. AdminShell + login + guard + routing wired into `App.tsx`.
3. Date-range picker + KPI/timeseries primitives.
4. Overview + Queries + TraceDrawer + Export (the highlighted additions land here).
5. Quality + Retrieval + Triggers + Topics.
6. Prompts + Evals + Ingestion + Logs + Alerts + Settings + Admins.
7. AskDataPanel + LiveFeed polish.
8. All `docs/admin/*.md` files.
9. Tests + final build/lint/test green check.

---

## 10. Explicitly NOT in this phase

- No Lovable Cloud, no real auth, no real telemetry writes, no judge calls, no edge functions, no migrations applied. All of that is documented in `migration-plan.md` ready to flip on later.
- No edits to existing end-user routes (`/`, `/chat`, `/practices`, `/profile`). The admin area is fully isolated under `/admin`.
- No new npm dependencies.
