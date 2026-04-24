# Migration plan: UI mock → Cloud-backed

Step-by-step. Each step is independent and reversible.

## 1. Enable Lovable Cloud
Click "Connect Cloud" in the Lovable UI. This provisions Postgres + auth + storage + edge functions.

## 2. Apply the schema
Run `docs/admin/schema.sql` as a single migration. It is idempotent for the optional upgrades (pgvector, realtime publication).

## 3. Seed the first admin
Get your `auth.users.id` from the Cloud dashboard, then:
```sql
insert into user_roles (user_id, role)
values ('<your-uuid>', 'admin');
```

## 4. Replace the mock auth
Edit only `src/admin/lib/adminAuth.ts`. Replace the localStorage stub with:
```ts
const { data, error } = await supabase.auth.signInWithPassword({ email, password });
if (error) return { ok: false, error: error.message };
const { data: roleOk } = await supabase.rpc("has_role", {
  _user_id: data.user.id, _role: "admin",
});
if (!roleOk) {
  await supabase.auth.signOut();
  return { ok: false, error: "Not an admin" };
}
return { ok: true, session: { email, loggedInAt: new Date().toISOString() } };
```
`useAdminGuard` and `getAdminSession` already work via the same shape.

## 5. Replace each mock data function
`src/admin/lib/mockData.ts` — for each function, swap the body for a Supabase query. Types and signatures stay identical, so no UI code changes.

Checklist:
- [ ] `listQueries` → `supabase.from('chat_queries').select(...).match(filters)`
- [ ] `getQueryTrace` → multi-table fetch (queries + responses + retrievals + spans + triggers + feedback + safety_events + prompt_versions)
- [ ] `getKpis` → SQL view or single RPC `get_kpis(from, to)`
- [ ] `getTimeseries` → SQL view bucketed via `date_trunc`
- [ ] `listPromptVersions`, `listModels`, `listTriggers`, `listSafetyEvents`, `listTopicClusters`
- [ ] `getRetrievalHealth`, `getQualityData`
- [ ] `listEvalRuns`, `listEvalResults`, `listGoldenQuestions`, `upsertGoldenQuestion`, `deleteGoldenQuestion`
- [ ] `listIngestionRuns`, `listLogs`, `listAlertRules`, `upsertAlertRule`, `listAlertEvents`
- [ ] `listAnnotations`, `listAdmins`, `promoteAdmin`, `demoteAdmin`
- [ ] `listModelPricing`, `upsertModelPricing`
- [ ] `askData` → AI-Gateway tool-call against pre-defined query templates

## 6. Move telemetry writes to edge functions
Create `supabase/functions/telemetry/` with handlers for `recordQuery`, `recordRetrieval`, `recordResponse`, `recordTrigger`, `recordFeedback`. Use `SUPABASE_SERVICE_ROLE_KEY`. Validate input with Zod. CORS only the chat origin.

## 7. Enable Realtime on `chat_queries`
Already attempted by `schema.sql`. Verify in Cloud → Database → Replication.

## 8. Wire the cron endpoint
Add `supabase/functions/cron/index.ts` matching `/api/public/cron/{job}`, verifying HMAC over the body using `CRON_SECRET`. Point an external scheduler (cron-job.org / GitHub Actions) at it for `evals`, `alerts`, `clustering`.

## 9. Remove the DEV MODE badge
Delete the badge in `src/admin/pages/AdminLoginPage.tsx` and update `AdminTopbar` to drop the "UI PREVIEW · mock data" pill.

## 10. Drop the seed
`src/admin/lib/seed.ts` is no longer used at runtime — keep it for tests and Storybook fixtures.
