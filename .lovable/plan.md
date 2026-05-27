# Admin console + chat polish plan

## Root cause (what I found during exploration)

1. **Admin pages are mostly empty / broken** because the database only has 6 tables (`profiles`, `user_roles`, `conversations`, `chat_messages`, `meditation_sessions`, `daily_teachings`). Every admin query hits non-existent tables (`chat_queries`, `chat_responses`, `retrieval_events`, `trace_spans`, `prompt_versions`, `app_logs`, `alert_*`, `eval_*`, `ingestion_runs`, `golden_questions`, `model_pricing`, `query_clusters`, `safety_events`, `trigger_events`, `user_profiles`, `annotations`). Supabase silently returns errors → pages render empty / crash on `.length` on undefined.
2. **Drill-down crashes on missing rows** even though `getQueryTrace` now uses `maybeSingle()` — `TraceDrawer` still dereferences `trace.response.citations.length`, `trace.retrieval.source_docs.map`, `trace.query.id`, `trace.prompt.name` without guards when the table doesn't exist or the row is partial.
3. **Thinking pill misalignment**: assistant bubble is laid out as `avatar(28px) + gap(10px) + bubble`, so the bubble's left edge sits at 38px. Pill uses `pl-12` (48px) → 10px off, and on mobile it has `pl-0` so it jumps left entirely. Pill also has no avatar gutter, so width and indentation never match assistant column.

## Scope

### Track A — Database (Lovable Cloud migration)
Create the admin telemetry schema in one migration:

- Tables: `chat_queries`, `chat_responses`, `retrieval_events`, `trace_spans`, `trigger_events`, `safety_events`, `prompt_versions`, `alert_rules`, `alert_events`, `annotations`, `app_logs`, `eval_runs`, `eval_results`, `golden_questions`, `ingestion_runs`, `model_pricing`, `query_clusters`, `user_profiles`, `feedback_events`.
- For each: `GRANT SELECT, INSERT, UPDATE, DELETE … TO authenticated`, `GRANT ALL … TO service_role`, `ENABLE ROW LEVEL SECURITY`, plus admin-only RLS using existing `public.has_role(auth.uid(), 'admin')`. Insert policy for `service_role` only (backend writes).
- Seed a tiny dev fixture (3 queries: one full trace, one missing response, one missing retrieval) gated behind a `seed_admin_demo()` SECURITY DEFINER function that only runs when caller is admin.

### Track B — Frontend hardening
- `TraceDrawer.tsx`: guard every `trace.response`, `trace.retrieval`, `trace.prompt`, `trace.query`, `trace.triggers`, `trace.feedback`, `citations`, `source_docs`, `spans` access. Render explicit empty-state cards ("No response recorded", "No retrieval recorded", "No spans") instead of crashing.
- `mockData.ts`: catch Supabase errors per query so one missing table doesn't blank the whole page; return `[]` with a logged warning.
- Each admin page (`OverviewPage`, `QueriesPage`, `QualityPage`, `RetrievalPage`, `TriggersPage`, `TopicsPage`, `PromptsPage`, `EvalsPage`, `IngestionPage`, `LogsPage`, `TelemetryPage`, `AlertsPage`, `SettingsPage`, `AdminsPage`, `FeedbackPage`, `DailyTeachingPage`): wrap in `AdminErrorBoundary`, ensure `EmptyState` renders on `[]`, fix any unguarded `.map`/`.length` against possibly-null data.
- `useAdminData` hooks: switch to `useQuery` with `retry: false` and surface error toasts instead of infinite loading.

### Track C — Thinking pill alignment (chat)
Re-skin `ThinkingPills.tsx` to share the assistant-row geometry:
- Wrap in the same `flex items-start gap-2.5 justify-start` shell with a 28px avatar slot (faded Sparkles icon) so the pill body starts at the exact same x as the assistant bubble.
- Drop `pl-0 sm:pl-12`; rely on the shared shell padding from `MessageList`.
- Constrain to `max-w-[85%] sm:max-w-[75%]` to match bubble width.
- Mobile: avatar visible so left edge matches assistant.

### Track D — E2E + unit tests
- New `tests/e2e/admin-pages-smoke.spec.ts`: log in as admin, visit every admin route, assert no console error and either data or empty-state is visible.
- New `tests/e2e/admin-trace-drilldown.spec.ts`: seed via `seed_admin_demo()`, open Queries page, click each of the 3 fixtures, assert drawer renders spans / chunks / response for the full trace, and renders empty-state strings for the partial traces, without crashing.
- New `tests/e2e/chat-thinking-pill.spec.ts`: send a query, capture bounding box of the pill and of the next assistant bubble, assert `Math.abs(pill.left - bubble.left) < 2px`.
- Vitest: extend `mockData.test.ts` with a "missing response row" case asserting `getQueryTrace` returns `null`-shaped fields without throwing.

## Backend steps you need to do (FastAPI side)

Once Track A migration lands, your backend has to start writing trace rows to Supabase. Concrete checklist:

1. Add `SUPABASE_SERVICE_ROLE_KEY` to `backend/.env` (already in Lovable secrets — copy locally).
2. `pip install supabase==2.*` in `backend/requirements.txt`.
3. Create `backend/app/telemetry_sink.py` with a single `SupabaseTelemetrySink` class using `create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)`.
4. In `app/main.py` chat handler, after the LangGraph run completes, insert one row each into:
   - `chat_queries` (id=request_id, user_id, query_text, model, latency_ms, prompt_tokens, completion_tokens, cost_estimate, status, created_at)
   - `chat_responses` (query_id=request_id, response_text, citations jsonb, faithfulness, answer_relevancy, context_precision, context_recall, hallucination_flag, confidence, judge_reasoning)
   - `retrieval_events` (query_id, source_docs text[], scores numeric[])
   - `trace_spans` (query_id, span_name, start_ms, duration_ms) — one row per LangGraph node from `state['span_log']`.
   - `trigger_events` / `safety_events` when the rails or detectors fire.
5. Wrap inserts in a background task (`asyncio.create_task`) so telemetry never blocks the user response.
6. Restart backend with `make docker-rebuild-web`. Verify in Supabase: `select count(*) from chat_queries;` grows after each chat.
7. (Optional) Mirror Python logs into `app_logs` via a logging handler so the admin Logs page populates.

After step 6 every admin page should populate with real data and the drill-down passes the E2E.

## Out of scope
- Re-architecting the existing chat scrolling / inline edit work.
- Building new admin features (golden-question editor, alert evaluator) — only making existing pages render reliably.
- Backend Python changes — I will only document what you need to do (above), not edit Python files.

## Files touched
- `supabase/migrations/<ts>_admin_telemetry.sql` (new, single migration)
- `src/admin/components/TraceDrawer.tsx`
- `src/admin/lib/mockData.ts`, `src/admin/lib/mockData.test.ts`
- `src/admin/pages/*.tsx` (defensive guards + EmptyState only)
- `src/admin/hooks/useAdminData.ts`
- `src/components/chat/ThinkingPills.tsx`
- `src/test/ThinkingPills.test.tsx`
- `tests/e2e/admin-pages-smoke.spec.ts` (new)
- `tests/e2e/admin-trace-drilldown.spec.ts` (new)
- `tests/e2e/chat-thinking-pill.spec.ts` (new)

## Verification
1. Run new Vitest + Playwright suites (must be green).
2. Manually click every admin page in preview — none blank, none console errors.
3. Open drill-down on full + partial traces — both render without crash.
4. Inspect chat: pill left-edge aligns to assistant bubble within 2px on both mobile (375px) and desktop (1280px).
