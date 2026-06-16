# Phased Plan

Scope is large. I'll execute in 4 phases, committing after each so nothing is half-done.

## Phase 1 — Frontend features (1 turn)

**Multi-device resume prompt**

- Read `profiles.last_message_id` + `last_active_at` on app mount (after auth).
- If `last_active_at` exists AND current device has no matching conversation in localStorage → show toast/modal "Continue from where you left off?" with Resume / Dismiss.
- New file: `src/components/chat/ResumePrompt.tsx`, hook `src/hooks/useResumeSession.ts`.
- Requires backend column `last_message_id` (already documented in `docs/IMPROVEMENTS_BACKEND.md`). I'll ship a Supabase migration to add it if missing.

**Web Push (VAPID, native)**

- Generate VAPID keys (one-time, locally) → store `VITE_VAPID_PUBLIC_KEY` in `.env` + `VAPID_PRIVATE_KEY` / `VAPID_SUBJECT` as Supabase secrets.
- New service worker: `public/push-sw.js` (separate from app SW — push only, no caching, per PWA skill rules).
- New component: `src/components/common/PushPermissionPrompt.tsx` — soft-asks after first meditation session (not on cold load).
- New table: `push_subscriptions(user_id, endpoint, p256dh, auth, created_at)` + RLS.
- New edge function: `push-subscribe` (stores subscription) + update existing `daily-teaching-push` to read from table.

## Phase 2 — Admin deep audit (2 turns)

For each admin page (Overview, Queries, Retrieval, Quality, Feedback, Alerts, Triggers, Telemetry, Evals, Prompts, Admins, Ingestion, Logs, DailyTeaching):

1. Open page in preview, screenshot.
2. Run SQL against the source table(s) used by the KPI.
3. Compare displayed value vs SQL truth.
4. Fix broken queries in `src/admin/hooks/useAdminData.ts` and components.
5. Add empty-state handling where data is sparse.

Deliverable: `docs/ADMIN_AUDIT_REPORT.md` listing every metric, its source SQL, the bug, the fix.

## Phase 3 — Chat UX polish (1 turn)

Quick pass on chat — review session replay + screenshot, list issues, fix top 5.

## Phase 4 — Load test + Production hosting (1 turn)

**Light smoke load test**

- New `scripts/load/smoke.sh` — uses `curl` + `hey` (or `wrk` via nix) to hit:
  - `/healthz` edge function (50 RPS, 2 min) → assert p95 < 500ms.
  - `chat-rate-limit` edge function (burst 60 req in 10s from same user) → assert 429 kicks in correctly.
- Output: `docs/LOAD_TEST_RESULTS.md` with p50/p95/p99.
- Add Shields.io badge to README pointing at `/healthz`.

**Production hosting research (India-first, cheap)**
Web search for current pricing (June 2026) across:

- Hetzner CAX/CPX (EU) + Cloudflare India PoPs
- E2E Networks (Delhi/Mumbai)
- Yotta Shakti (Mumbai)
- Railway / Render
- Azure India Central / AWS Mumbai (for comparison)

Deliverable: `docs/PRODUCTION_HOSTING_INDIA.md` with:

- Monthly cost table for 1k DAU / 10k DAU
- India p95 latency estimates
- Model serving cost (Sarvam 30B vs Lovable AI Gateway vs OpenRouter India)
- Step-by-step deploy guide for the **recommended** option
- Cost-cutting playbook (semantic cache, smaller embedding model, batch nightly digests)

## Technical details

- Backend infra changes that can't be done from Lovable (FastAPI rate-limit, RAGAS gate, etc.) stay as copy-pasteable snippets in `docs/IMPROVEMENTS_BACKEND.md` — already exists, I'll extend.
- All new Supabase tables get explicit GRANTs + RLS per project rules.
- No 3D lotus, Golden Hour palette preserved, glassmorphism intact.
- Service worker for push is messaging-only (per PWA skill: messaging workers are exempt from offline-SW guards).

## Execution order

Reply with **"go"** to start Phase 1. After each phase I'll pause briefly so you can sanity-check before I burn credits on the next one. and also the UI UX in chat page is not looking good make sure the UI is neat and clean in all devices and also the spacing is huge between the first line and below pills