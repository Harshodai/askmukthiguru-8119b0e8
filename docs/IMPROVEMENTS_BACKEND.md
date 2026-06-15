# Backend Improvements — Copy/Paste Implementation Guide

Everything below is **local-first**. None of it requires Lovable. Apply in your
repo, commit, push to GitHub, and let your existing `build-deploy.yml` workflow
ship it. This document is the canonical source for the items requested:

- per-user token-bucket rate limit (deeper than current sliding-window edge fn)
- `/healthz` aggregate + README badge wiring
- eval-gate workflow (already added: `.github/workflows/eval-gate.yml`)
- multi-device session continuity
- Bhakti analytics (meditation heatmap, streaks, recalled teachings)
- Web Push daily Krishnaji teaching
- CoVe re-enable selectively for `tier3_deep`
- answer-source diversity guard
- doctrine cache warmup (top 200 queries)
- memory-extract → background cron job
- lazy YouTube citation thumbnails

---

## 1. Per-user token-bucket chat rate limit (FastAPI middleware)

Current `supabase/functions/chat-rate-limit` is a sliding window per-edge-instance.
For the **FastAPI** backend (which is where production chat actually lands), add a
proper Redis token-bucket middleware. Drop this into `backend/app/middleware/rate_limit.py`:

```python
# backend/app/middleware/rate_limit.py
from __future__ import annotations
import time
from typing import Awaitable, Callable
from fastapi import Request, Response, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
import redis.asyncio as redis

LUA_TOKEN_BUCKET = """
local key       = KEYS[1]
local capacity  = tonumber(ARGV[1])
local refill    = tonumber(ARGV[2])  -- tokens per second
local now       = tonumber(ARGV[3])
local cost      = tonumber(ARGV[4])
local data      = redis.call('HMGET', key, 'tokens', 'ts')
local tokens    = tonumber(data[1]) or capacity
local ts        = tonumber(data[2]) or now
local delta     = math.max(0, now - ts)
tokens          = math.min(capacity, tokens + delta * refill)
local allowed   = 0
if tokens >= cost then
  tokens = tokens - cost
  allowed = 1
end
redis.call('HMSET', key, 'tokens', tokens, 'ts', now)
redis.call('EXPIRE', key, math.ceil(capacity / refill) * 2)
return {allowed, tokens}
"""

class TokenBucketMiddleware(BaseHTTPMiddleware):
    """Per-user (falls back to per-IP) token bucket on /api/chat.
    Defaults: 20 tokens, refill 20/min (~1 every 3s)."""
    def __init__(self, app, redis_url: str, capacity: int = 20, refill_per_sec: float = 20/60):
        super().__init__(app)
        self.r = redis.from_url(redis_url, decode_responses=True)
        self.capacity = capacity
        self.refill = refill_per_sec
        self.script = self.r.register_script(LUA_TOKEN_BUCKET)

    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]):
        if not request.url.path.startswith("/api/chat"):
            return await call_next(request)
        # Identify subject: prefer authenticated user_id, fallback to first XFF IP
        subject = request.headers.get("x-user-id") or request.client.host
        key = f"rl:chat:{subject}"
        allowed, remaining = await self.script(keys=[key], args=[self.capacity, self.refill, time.time(), 1])
        if not int(allowed):
            raise HTTPException(status_code=429, detail={"error": "rate_limited", "remaining": 0})
        resp = await call_next(request)
        resp.headers["X-RateLimit-Remaining"] = str(int(remaining))
        return resp
```

Wire in `backend/app/main.py`:

```python
from app.middleware.rate_limit import TokenBucketMiddleware
app.add_middleware(TokenBucketMiddleware, redis_url=settings.REDIS_URL, capacity=20, refill_per_sec=20/60)
```

---

## 2. `/healthz` README badge

`supabase/functions/healthz` is already added. The function supports
`?format=shield` for [shields.io endpoint] badges. Add to repo README:

```markdown
[![status](https://img.shields.io/endpoint?url=https%3A%2F%2Ffynkjimvuimakgtidvuq.supabase.co%2Ffunctions%2Fv1%2Fhealthz%3Fformat%3Dshield)](https://askmukthiguru.lovable.app)
```

For the FastAPI backend deep-health (Qdrant + Redis + Ollama), add `backend/app/api/health.py`:

```python
from fastapi import APIRouter, status
from app.dependencies import get_container
import asyncio, time

router = APIRouter()

async def _timed(name, coro):
    s = time.perf_counter()
    try:
        await asyncio.wait_for(coro, timeout=2.0)
        return {"name": name, "ok": True, "latency_ms": int((time.perf_counter() - s) * 1000)}
    except Exception as e:
        return {"name": name, "ok": False, "error": str(e)[:120]}

@router.get("/healthz")
async def healthz():
    c = get_container()
    checks = await asyncio.gather(
        _timed("qdrant", c.qdrant.client.get_collections()),
        _timed("redis", c.cache.redis.ping()),
        _timed("ollama", c.ollama.health()),
    )
    ok = all(x["ok"] for x in checks)
    return ({"ok": ok, "checks": checks},
            status.HTTP_200_OK if ok else status.HTTP_503_SERVICE_UNAVAILABLE)
```

---

## 3. Eval-gate workflow

Already added: `.github/workflows/eval-gate.yml` + `backend/evaluation/golden_dataset.json` +
`backend/evaluation/run_golden_eval.py`. Expand the dataset to **50–100 disciple questions**
before flipping the workflow to `required` in branch protection. Required GitHub secrets:

- `BACKEND_URL` — public URL of staging backend (e.g. `https://api.askmukthiguru.com`)
- `BACKEND_TOKEN` — service token for `/api/chat`
- `LOVABLE_API_KEY` — only needed if RAGAS calls the gateway for judge LLM

---

## 4. Multi-device session continuity

### 4a. Migration — add `last_message_id` per user

```sql
-- supabase/migrations/2026XXXX_user_session_continuity.sql
ALTER TABLE public.profiles
  ADD COLUMN IF NOT EXISTS last_conversation_id uuid REFERENCES public.conversations(id) ON DELETE SET NULL,
  ADD COLUMN IF NOT EXISTS last_message_id uuid REFERENCES public.chat_messages(id) ON DELETE SET NULL,
  ADD COLUMN IF NOT EXISTS last_active_at timestamptz;

CREATE OR REPLACE FUNCTION public.touch_user_last_message()
RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
BEGIN
  UPDATE public.profiles
     SET last_conversation_id = NEW.conversation_id,
         last_message_id = NEW.id,
         last_active_at = now()
   WHERE id = NEW.user_id;
  RETURN NEW;
END $$;

CREATE TRIGGER trg_touch_last_message
AFTER INSERT ON public.chat_messages
FOR EACH ROW EXECUTE FUNCTION public.touch_user_last_message();
```

### 4b. Frontend — prompt on new device

Detect "new device" via `localStorage` token absence; if `profile.last_active_at`
> local last-seen, show modal: *"Continue from where you left off on another device?"*
Wire into `src/pages/ChatPage.tsx` after auth resolves.

---

## 5. Bhakti analytics (private)

Tables already exist (`meditation_sessions`). Add SQL for streaks + heatmap:

```sql
-- views (RLS auto-enforces via underlying table policies)
CREATE OR REPLACE VIEW public.v_meditation_heatmap AS
SELECT user_id, date_trunc('day', started_at)::date AS day, COUNT(*) AS sessions, SUM(duration_seconds) AS seconds
FROM public.meditation_sessions GROUP BY 1,2;

CREATE OR REPLACE FUNCTION public.meditation_streak(p_user uuid)
RETURNS int LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public AS $$
  WITH days AS (
    SELECT DISTINCT date_trunc('day', started_at)::date d
    FROM public.meditation_sessions WHERE user_id = p_user
  ), s AS (
    SELECT d, d - (row_number() OVER (ORDER BY d))::int AS grp FROM days
  )
  SELECT COALESCE(MAX(cnt), 0) FROM (SELECT COUNT(*) cnt FROM s GROUP BY grp) z;
$$;
```

"Most-recalled teachings" — already available via `guru_memories.recall_count`.
Surface in `src/pages/ProfilePage.tsx` as a small leaderboard.

---

## 6. Daily Krishnaji teaching — Web Push

PWA service worker is registered. Add VAPID push:

```bash
npm i web-push
```

### 6a. Subscription table

```sql
CREATE TABLE public.push_subscriptions (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  endpoint text NOT NULL UNIQUE,
  p256dh text NOT NULL,
  auth text NOT NULL,
  created_at timestamptz DEFAULT now()
);
GRANT SELECT, INSERT, DELETE ON public.push_subscriptions TO authenticated;
GRANT ALL ON public.push_subscriptions TO service_role;
ALTER TABLE public.push_subscriptions ENABLE ROW LEVEL SECURITY;
CREATE POLICY "self" ON public.push_subscriptions FOR ALL
  USING (user_id = auth.uid()) WITH CHECK (user_id = auth.uid());
```

### 6b. Edge function `daily-teaching-push`

```ts
// supabase/functions/daily-teaching-push/index.ts
import webpush from 'npm:web-push@3.6.7';
import { createClient } from 'https://esm.sh/@supabase/supabase-js@2.45.0';

webpush.setVapidDetails(
  'mailto:hello@askmukthiguru.com',
  Deno.env.get('VAPID_PUBLIC_KEY')!,
  Deno.env.get('VAPID_PRIVATE_KEY')!,
);

Deno.serve(async () => {
  const sb = createClient(Deno.env.get('SUPABASE_URL')!, Deno.env.get('SUPABASE_SERVICE_ROLE_KEY')!);
  const { data: teaching } = await sb.from('daily_teachings')
    .select('caption, image_url').order('publish_date', { ascending: false }).limit(1).single();
  const { data: subs } = await sb.from('push_subscriptions').select('*');
  const payload = JSON.stringify({ title: "Today's Teaching", body: teaching?.caption ?? '', image: teaching?.image_url });
  await Promise.allSettled((subs ?? []).map((s) =>
    webpush.sendNotification({ endpoint: s.endpoint, keys: { p256dh: s.p256dh, auth: s.auth } }, payload)
  ));
  return new Response('ok');
});
```

### 6c. Schedule (08:00 IST = 02:30 UTC)

```sql
SELECT cron.schedule('daily-teaching', '30 2 * * *',
  $$ SELECT net.http_post(
    url:='https://fynkjimvuimakgtidvuq.supabase.co/functions/v1/daily-teaching-push',
    headers:='{"apikey":"<ANON_KEY>","Content-Type":"application/json"}'::jsonb,
    body:='{}'::jsonb) $$);
```

Add secrets: `VAPID_PUBLIC_KEY`, `VAPID_PRIVATE_KEY` (generate with `npx web-push generate-vapid-keys`).

---

## 7. Re-enable CoVe selectively for `tier3_deep`

In `backend/rag/nodes/verification.py`:

```python
async def verify_answer(state: GraphState) -> dict:
    # ... existing LettuceDetect block ...
    if state.get("query_tier") == "tier3_deep":
        cove = await _cove_subquestion_check(state["query"], state["answer"], state["documents"])
        if cove.faithfulness < 0.7:
            return {"verification_status": "needs_correction", "cove_report": cove.dict()}
    return {"verification_status": "valid"}
```

Keep tier1/tier2 on LettuceDetect-only (their current fast path).

---

## 8. Answer-source diversity guard

`backend/rag/nodes/utils.py` (called from `format_final_answer`):

```python
def enforce_source_diversity(citations: list[dict], min_distinct: int = 2) -> list[dict]:
    """Reject responses whose top-3 citations all come from the same source video."""
    top = citations[:3]
    sources = {c.get("source_id") or c.get("video_id") for c in top}
    if len([s for s in sources if s]) < min_distinct:
        # promote the next citation from a different source
        for c in citations[3:]:
            sid = c.get("source_id") or c.get("video_id")
            if sid and sid not in sources:
                citations.insert(2, c)
                citations = citations[:3] + [x for x in citations[3:] if x is not c]
                break
    return citations
```

---

## 9. Doctrine cache warm-up (top 200 queries)

`backend/scripts/warm_doctrine_cache.py` — already scaffolded; expand the seed list
to 200 entries grouped by topic (Beautiful State, suffering, relationships, deeksha,
serene mind, dharma, etc.). Add nightly cron:

```yaml
# .github/workflows/cache-warm.yml
on:
  schedule: [{cron: '0 1 * * *'}]
jobs:
  warm:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: {python-version: '3.11'}
      - run: pip install httpx
      - run: python backend/scripts/warm_doctrine_cache.py --backend ${{ secrets.BACKEND_URL }}
```

---

## 10. Memory extraction → true background job

Today: `memory-extract` is invoked fire-and-forget after every chat reply. Replace
with a `pending_extractions` table + cron drain:

```sql
CREATE TABLE public.pending_extractions (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  conversation_id uuid NOT NULL,
  message_id uuid NOT NULL,
  payload jsonb NOT NULL,
  status text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','processing','done','failed')),
  attempts int NOT NULL DEFAULT 0,
  last_error text,
  created_at timestamptz DEFAULT now(),
  processed_at timestamptz
);
CREATE INDEX ON public.pending_extractions (status, created_at);
GRANT SELECT, INSERT, UPDATE ON public.pending_extractions TO service_role;
ALTER TABLE public.pending_extractions ENABLE ROW LEVEL SECURITY;
```

Frontend `aiService.ts`: change `supabase.functions.invoke('memory-extract', ...)`
→ a single `supabase.from('pending_extractions').insert(...)` (no network wait).

Cron edge function `memory-extract-drain` runs every minute, takes 50 rows
`FOR UPDATE SKIP LOCKED`, processes, marks done. Removes one round-trip from
every chat reply (~80–150 ms saved per turn).

```sql
SELECT cron.schedule('memory-drain', '* * * * *',
  $$ SELECT net.http_post(
    url:='https://fynkjimvuimakgtidvuq.supabase.co/functions/v1/memory-extract-drain',
    headers:='{"apikey":"<ANON_KEY>"}'::jsonb, body:='{}'::jsonb) $$);
```

---

## 11. Lazy YouTube citation thumbnails

In the React citation component, replace eager `<iframe>` with click-to-load:

```tsx
const YouTubeCitation = ({ videoId, title }: { videoId: string; title: string }) => {
  const [play, setPlay] = useState(false);
  if (play) {
    return <iframe src={`https://www.youtube.com/embed/${videoId}?autoplay=1`}
      title={title} className="w-full aspect-video rounded-lg" allow="autoplay" />;
  }
  return (
    <button onClick={() => setPlay(true)} className="relative w-full aspect-video group">
      <img src={`https://i.ytimg.com/vi/${videoId}/mqdefault.jpg`} loading="lazy"
           alt={title} className="w-full h-full object-cover rounded-lg" />
      <span className="absolute inset-0 flex items-center justify-center bg-black/40 group-hover:bg-black/20 rounded-lg">
        <PlayCircle className="w-12 h-12 text-white drop-shadow-lg" />
      </span>
    </button>
  );
};
```

Drops ~250 KB per citation on first paint.

---

## Deploy checklist (no Lovable required)

1. `git add -A && git commit -m "feat: world-class hardening pass"`
2. `git push` — GitHub Actions runs `lint-test.yml`, `eval-gate.yml`, `build-deploy.yml`
3. For Supabase Edge Functions (`healthz`, `daily-teaching-push`, `memory-extract-drain`):
   `supabase functions deploy healthz daily-teaching-push memory-extract-drain --project-ref fynkjimvuimakgtidvuq`
4. Apply migrations: `supabase db push`
5. Schedule cron jobs (run the SQL `SELECT cron.schedule(...)` blocks once via psql)
6. Add VAPID secrets via `supabase secrets set VAPID_PUBLIC_KEY=… VAPID_PRIVATE_KEY=…`

Confirm `/healthz` badge turns **green** and the eval-gate workflow passes on
the next PR. Then mark it required in branch protection.
