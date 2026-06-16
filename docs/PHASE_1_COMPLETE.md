# Phase 1 — Frontend Features Shipped

## What's live

### 1. Multi-device resume prompt (`src/pages/ChatPage.tsx`)
- On `/chat` load, reads `profiles.last_active_at` + `last_conversation_id`.
- Compares to `localStorage.askmukthiguru_last_seen`.
- If server activity is newer → shows "Continue on this device?" dialog with Resume / Stay buttons.
- Write-back happens in `ChatInterface.tsx` whenever messages update (fire-and-forget).

### 2. PWA Web Push (VAPID, native)
- `public/push-sw.js` — push-only service worker (no caching, isolated from any future app-shell SW per Lovable PWA skill).
- `src/hooks/useWebPush.ts` — registers SW, subscribes to PushManager, upserts to `push_subscriptions` table.
- `src/components/common/PushPermissionPrompt.tsx` — soft toast after 4s, dismiss cooldown 7 days, only shown if `permission !== 'denied'` and not already subscribed. Wired into `App.tsx`.
- `supabase/functions/push-send/index.ts` — broadcasts to all (or one) user's subscriptions; cleans up stale 404/410 endpoints automatically.

### 3. Chat spacing fix
- Tightened gap between welcome message and starter pills: `pt-4 space-y-4` → `mt-1 space-y-2.5`.
- Smaller pill padding & font for mobile breathing room.

### 4. Database
- `profiles.last_conversation_id`, `last_message_id`, `last_active_at`, `last_device_id` columns added.
- `push_subscriptions` table with RLS (own rows only).
- `pending_extractions` queue table for memory-extract-drain (fixes prior TS error).

## What you must do before push notifications work

1. **Generate VAPID keys** locally (one-time):
   ```bash
   npx web-push generate-vapid-keys --json
   ```
2. **Add secrets** (I will prompt you in the next step):
   - `VAPID_PUBLIC_KEY` — paste the `publicKey` from step 1
   - `VAPID_PRIVATE_KEY` — paste the `privateKey`
   - `VAPID_SUBJECT` — e.g. `mailto:hello@askmukthiguru.app`
3. **Add to `.env.local` for the frontend** (so the browser can subscribe):
   ```
   VITE_VAPID_PUBLIC_KEY=<same publicKey>
   ```
4. **Test broadcast** via:
   ```bash
   curl -X POST https://<project>.supabase.co/functions/v1/push-send \
     -H "Content-Type: application/json" \
     -d '{"title":"Test","body":"Hello disciple","url":"/chat"}'
   ```
5. **Schedule daily teaching** (optional, via pg_cron — see `docs/IMPROVEMENTS_BACKEND.md`).

## Next phases queued

- Phase 2: Admin deep audit (per-page SQL verification)
- Phase 3: Chat UX polish pass
- Phase 4: Load test + India hosting research → `docs/PRODUCTION_HOSTING_INDIA.md`
