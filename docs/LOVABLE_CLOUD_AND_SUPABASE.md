# Lovable Cloud vs. your own Supabase — what is actually possible

**Short answer: no, you cannot move this project onto Lovable Cloud.** This project
is already wired to an **external, self-owned Supabase project** (`ozmjeuqbholoxypfxixb`).
Lovable Cloud is only offered to projects that have *no* external Supabase connection —
the two are mutually exclusive by design. Enabling Cloud would mean detaching your
Supabase project and starting a new managed one.

That is not a bug, and in your case it is the *better* outcome. Here is why, and what
"frontend and backend in sync" actually requires.

---

## 1. What you would lose by moving to Lovable Cloud

| Capability you use today | Own Supabase | Lovable Cloud |
|---|---|---|
| `service_role` key for the FastAPI backend on Railway | ✅ you hold it | ❌ never exposed |
| Direct Postgres connection (psql, `pg_dump`, migrations from CI) | ✅ | ❌ |
| `pgvector` collections managed from Python ingestion scripts | ✅ | ⚠️ edge-function only |
| Neo4j / Qdrant / LightRAG sidecars on the same private network | ✅ Railway | ❌ n/a |
| Custom auth hooks + `handle_new_user` domain allow-list trigger | ✅ | ✅ |
| Data ownership / portability for a commercial product | ✅ | ⚠️ managed |

Your backend (`backend/services/*`) writes telemetry, embeddings and KB chunks with
the service role and bypasses RLS. On Lovable Cloud every one of those writes would
have to be rewritten as an edge function. That is the migration documented in
`docs/archive/RAILWAY_REWIRE.md` — it was scoped, and it is strictly more work and
strictly less capability than what you have now.

**Recommendation: stay on your own Supabase.** Ship the product on it.

---

## 2. "Frontend and backend data in sync" — the real requirement

Sync is not a hosting question. It is a **single-source-of-truth** question. Today you
already have that: the React app and the FastAPI backend both point at
`ozmjeuqbholoxypfxixb`. The rule to hold is:

> There is exactly one Supabase project. The frontend uses the **publishable/anon**
> key with RLS. The backend uses the **service role** key server-side only. Nothing
> else writes to the database.

Verify with:

```bash
grep -r "VITE_SUPABASE_URL" .env .env.production   # frontend target
railway variables --service askmukthiguru-8119b0e8 | grep SUPABASE_URL  # backend target
```

Those two must print the same project ref. If they ever diverge, telemetry, chat
history and admin dashboards silently split-brain — the exact failure documented in
`docs/archive/RAILWAY_REWIRE.md`.

### Where edge functions still help you

Even staying on your own Supabase, edge functions are the right home for anything the
*browser* must trigger but must not be trusted to compute. Already deployed in
`supabase/functions/`:

| Function | Why it is an edge function |
|---|---|
| `admin-telemetry` | writes `chat_queries` / `chat_responses` bypassing RLS |
| `memory-embed` | holds the embedding provider key |
| `ingest-source` | server-side SSRF-guarded fetch |
| `chat-rate-limit` | authoritative per-user quota |

Add a new one whenever a client would otherwise need a privileged key. Never add one
just to proxy a read the client is already allowed to make under RLS — that is latency
with no security gain.

---

## 3. Leaked-password protection

`SUPA_auth_leaked_password_protection` cannot be fixed from code. On a self-owned
Supabase project it is a dashboard toggle backed by the HaveIBeenPwned k-anonymity API.

**Enable it here (30 seconds):**

1. Open **Authentication → Providers → Email** (or **Auth → Policies** on newer dashboards).
2. Scroll to **Password Security**.
3. Turn on **"Prevent use of leaked passwords"**.
4. Confirm **Minimum password length = 12** (already set in `supabase/config.toml`;
   the dashboard value is what the hosted project enforces).

Direct link: <https://supabase.com/dashboard/project/ozmjeuqbholoxypfxixb/auth/providers>

Once toggled, re-run the security scan and the finding clears. There is no SQL,
migration, or API call that sets this — it is project configuration, and Lovable has no
write access to your external project's auth settings.
