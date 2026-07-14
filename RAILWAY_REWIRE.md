# Railway Backend Rewire — Point FastAPI at Lovable Cloud Supabase

The frontend now uses **Lovable Cloud Supabase** (`fynkjimvuimakgtidvuq.supabase.co`). Your Railway-hosted FastAPI backend still points at the old `ozmjeuqbholoxypfxixb`. Both must use the same DB or auth/telemetry breaks.

## What to change on Railway

Open your Railway project → `askmukthiguru-8119b0e8` service → **Variables** tab. Replace these:

| Variable | New value |
|---|---|
| `SUPABASE_URL` | `https://fynkjimvuimakgtidvuq.supabase.co` |
| `SUPABASE_ANON_KEY` | `eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImZ5bmtqaW12dWltYWtndGlkdnVxIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzgwNDQyMDIsImV4cCI6MjA5MzYyMDIwMn0.l0mmx5BJ_AWEWq7d6IAeOz4inWuvm139EVeushiecto` |
| `SUPABASE_PUBLISHABLE_KEY` | same as anon key above |
| `SUPABASE_KEY` | **(problem — see below)** |
| `SUPABASE_SERVICE_ROLE_KEY` | **(problem — see below)** |
| `SUPABASE_JWT_SECRET` | **(problem — see below)** |

## The service-role problem

Lovable Cloud **does not expose** the `service_role` key or DB password to users. Your backend currently uses `SUPABASE_SERVICE_ROLE_KEY` for:

- Writing telemetry (`chat_queries`, `chat_responses`, `trace_spans`, `retrieval_events`)
- Upserting embeddings into `kb_chunks`
- Admin operations (`list_admins`, `seed_admin.py`)
- Bypassing RLS during ingestion

**Solution: Move these writes into edge functions.** Edge functions on Lovable Cloud have implicit service-role access. Your FastAPI calls a Lovable edge function URL instead of talking to Postgres directly.

### Existing edge functions you can already call from Railway

| Edge function | Purpose | URL |
|---|---|---|
| `admin-telemetry` | Persist chat_queries / chat_responses / trace_spans | `https://fynkjimvuimakgtidvuq.supabase.co/functions/v1/admin-telemetry` |
| `memory-embed` | Embed + upsert user memory | `.../functions/v1/memory-embed` |
| `ingest-source` | KB ingestion | `.../functions/v1/ingest-source` |
| `chat-rate-limit` | Rate limit checks | `.../functions/v1/chat-rate-limit` |

Call them with `Authorization: Bearer <user_jwt>` (or the anon key for public-safe endpoints). Signed JWTs from the frontend are forwarded through your backend.

### Recommended Railway change

```python
# backend/app/config.py
SUPABASE_URL = "https://fynkjimvuimakgtidvuq.supabase.co"
SUPABASE_ANON_KEY = "<anon key above>"
# Remove SERVICE_ROLE_KEY entirely
```

Replace direct Postgres writes with `httpx.post(f"{SUPABASE_URL}/functions/v1/admin-telemetry", ...)`.

For any admin action that needs service-role bypass, add a new edge function in `supabase/functions/<name>/` — I can scaffold these on request.

## CORS

Your FastAPI already allows `*.lovable.app` (per `PROD_READINESS.md`). No change needed.

## Google OAuth

Frontend now uses **Lovable's managed Google OAuth** (no client ID needed). Your `VITE_GOOGLE_CLIENT_ID` in `.env.production` is still there for legacy Google One-Tap on the AuthPage — leave it. If you want your custom credentials used instead, add them in Lovable Cloud → Users → Auth Settings → Google.

## Custom domain (`askmukthiguru.com` via Cloudflare)

1. In Cloudflare, add CNAME: `askmukthiguru.com` → `askmukthiguru.lovable.app` (proxied off — grey cloud, orange breaks HTTPS handshake).
2. In Lovable → Project Settings → Domains, add `askmukthiguru.com`.
3. Once verified, add `https://askmukthiguru.com` to authorized redirect URLs in Google Cloud Console for the OAuth client (if using custom credentials).
4. Update FastAPI CORS `CORS_ORIGINS` to add `https://askmukthiguru.com`.
