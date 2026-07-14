# Production Readiness — Final Assessment

Target stack the user is shipping:

| Component | Host | Verdict |
|---|---|---|
| Frontend (React) | Lovable published + Cloudflare (`askmukthiguru.com`) | **GO** |
| Auth + DB + Storage | Lovable Cloud (Supabase managed) | **GO** |
| Google OAuth | Lovable managed provider | **GO** |
| Backend (FastAPI) | Railway | **GO with caveats** |
| Redis | Railway | **GO** |
| Neo4j | Railway | **GO with caveats** |
| Qdrant | Railway | **GO with caveats** |
| AI models | API-only (OpenRouter / Sarvam / Lovable AI Gateway) | **GO** |

---

## 1. Frontend (Lovable + Cloudflare) — GO

**What's ready**
- 14 locales registered in `src/i18n.ts` (6 with full translations, 8 fall back to English).
- Every heavy route lazy-loaded via `lazyWithRetry`.
- Sentry wired; Web Vitals now piped to Sentry (LCP/INP/CLS/FCP/TTFB).
- Service worker registered off preview/iframe origins.

**Action for the user**
- Cloudflare DNS: `CNAME askmukthiguru.com → askmukthiguru.lovable.app` (proxied, orange cloud).
- Cloudflare page rules: cache HTML for 5min, static assets for 30d, bypass `/auth` and `/api`.
- Publish frontend after each release from Lovable UI.

## 2. Lovable Cloud (Supabase) — GO

**What's ready**
- 37 tables, all RLS-enabled, all GRANT-ed.
- Admin auto-grant trigger wired for `kharshaengineer@gmail.com`.
- Google OAuth configured via managed provider (no Google Cloud Console needed).

**Non-negotiable caveat: no `service_role` key**
Every backend write that used to bypass RLS must now route through an edge function that validates the caller's JWT. Already migrated: `admin-telemetry`, `memory-embed`, `ingest-source`. Any remaining service-role usage on Railway is a blocker — audit Railway FastAPI code for `create_client(SUPABASE_URL, SERVICE_ROLE_KEY)` before flipping env.

## 3. Backend (FastAPI on Railway) — GO with caveats

**Caveats**
- **Cold start**: FastAPI + heavy imports (torch, sentence-transformers via reranker) is 15–30s cold. Fix by (a) shipping a slim image without local models (models are API-only per user requirement — remove `sentence-transformers`, `flashrank`, `whisper` from `requirements.txt` on the Railway image), or (b) enabling Railway's "always on" plan.
- **Healthcheck**: Railway expects `GET /api/health` < 500ms. Confirm `main.py` returns without touching Redis/Neo4j on the healthcheck path.
- **Timeout budget**: p95 target 3s. With AI-model API round-trip ~1.5s, keep retrieval+rerank server-side under 800ms (Qdrant <150ms, LightRAG <400ms, RRF+MMR <100ms, prompt build <50ms).

**Env vars to set on Railway**
```
SUPABASE_URL, SUPABASE_ANON_KEY, SUPABASE_PUBLISHABLE_KEY  (from Lovable Cloud)
REDIS_URL, QDRANT_URL, NEO4J_URI/USER/PASSWORD              (from Railway)
OPENROUTER_API_KEY / SARVAM_API_KEY / LOVABLE_API_KEY       (AI models)
CORS_ORIGINS=https://askmukthiguru.com,https://askmukthiguru.lovable.app
IS_PRODUCTION=true, ENABLE_TEST_AUTH=false
```

## 4. Redis on Railway — GO

Managed Redis, 256 MB, eviction `allkeys-lru`. Used for response cache + semantic cache. TTL 1h. No caveats.

## 5. Neo4j on Railway — GO with caveats

- Railway community edition, 1 GB RAM minimum for the current graph (11k relations / 7.5k nodes).
- Persistent volume: 5 GB is enough; snapshot weekly to `/mnt/documents/neo4j-backup-*.tgz`.
- `KNOWLEDGE_GRAPH_QUERY_ENABLED=true` is currently profitable — keep on.

## 6. Qdrant on Railway — GO with caveats

- ~2 GB storage for current ingest; give the volume 10 GB headroom.
- HNSW index; `m=16, ef_construct=100`. Query p95 must stay <150ms.
- Snapshot weekly via `scripts/ops/backup_qdrant.py`.

## 7. AI models (API-only) — GO

Primary: Lovable AI Gateway (`google/gemini-2.5-flash` for classify/summarize, `google/gemini-2.5-pro` for generate).
Fallback: OpenRouter (`meta-llama/llama-3.3-70b-instruct` free tier).
STT: Lovable AI (whisper-1). TTS: Lovable AI. Embeddings: `text-embedding-3-small` via Lovable AI.

Kill local Ollama/Sarvam-local from the Railway image — API-only is the user's stated model plan.

---

## Page-Load Latency Budget (frontend)

| Metric | Budget | Current expectation |
|---|---|---|
| LCP | ≤2500 ms | ~1800 ms (hero image preloaded, route-lazy) |
| INP | ≤200 ms | ~120 ms (no heavy sync work on interaction) |
| CLS | ≤0.10 | ~0.02 (fixed heights on layout components) |
| TTFB | ≤800 ms | Lovable CDN ~200 ms |
| Bundle (initial) | ≤200 KB gz | Verify with `bun run build && du -h dist/assets/*.js` |

Web Vitals now stream to Sentry with route + connection tags — any regression flags a `webvital.poor.*` warning event.

---

## GO / NO-GO Verdict

**GO for production**, contingent on the four user actions below. None are blocking Lovable-side work.

1. Point Cloudflare DNS at `askmukthiguru.lovable.app` (or use Lovable's built-in custom domain flow).
2. Set Railway env vars to Lovable Cloud values (§2 caveat above).
3. Audit Railway FastAPI for any `service_role` usage; move to edge functions if found.
4. Sign in once with `kharshaengineer@gmail.com` to activate admin auto-grant, then visit `/admin/self-check` and confirm all rows PASS.
