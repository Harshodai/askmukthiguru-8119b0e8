# Architecture

```text
End-user chat (askmukthiguru, brought in later)
        │
        ▼
 telemetry write API  ──►  Postgres (RLS-locked, service role only)
        │                        ▲
        ▼                        │ admin SELECT
 async judge (Lovable AI)  ──────┘   (via has_role)

Admin browser
        │
        ▼
 /admin/login   →   _admin layout (role-guarded)   →   admin pages
```

## Isolation

- `/admin/*` renders a separate shell — no `Navbar`, no `SafetyDisclaimer`, no `SereneMindProvider`. See `src/App.tsx` (`EndUserApp` switches on `pathname.startsWith("/admin")`).
- The end-user `ThemeProvider`/`ReminderProvider`/`SereneMindProvider` are **not** mounted inside `/admin`. This prevents accidentally surfacing admin chrome to end-users and vice versa.

## Security posture (when Cloud is enabled)

1. Same Supabase auth backend, distinct `/admin/login` page.
2. Roles in a separate `user_roles` table — never on `profiles`.
3. `has_role(uid, 'admin')` is a `SECURITY DEFINER` SQL function (industry-standard pattern; avoids RLS recursion).
4. Every telemetry table has RLS enabled. Default policy denies all client reads. Admin-only `select` policy uses `has_role(auth.uid(), 'admin')`.
5. Writes happen only from server functions with the service role — never from the browser.
6. Public cron endpoints are protected by HMAC over the request body using `CRON_SECRET`.

## Data model

12 telemetry tables grouped as:

- **Core**: `chat_sessions`, `chat_queries`, `retrieval_events`, `chat_responses`, `prompt_versions`
- **Tracing**: `trace_spans` (OTel-inspired, not OTel-protocol)
- **Quality**: `user_feedback`, `safety_events`, `annotations`
- **Evals**: `golden_questions`, `eval_runs`, `eval_results`
- **Ops**: `ingestion_runs`, `app_logs`, `model_pricing`, `query_clusters`, `alert_rules`, `alert_events`
- **Auth**: `user_roles` + `has_role()`

See `schema.sql` for the exact migration.
