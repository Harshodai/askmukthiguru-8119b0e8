# Plan: Unblock Published Link + Google Auth Dedup + Chat UX Overhaul

## Phase 0 — CRITICAL: Fix white-screen on published / preview link

**Blocker:** User cannot share the published URL — it renders a white screen every time. This is the highest priority. Until this works there is no point shipping UX polish.

Diagnosis steps (executed before any other change):

1. Open the published URL (`https://askmukthiguru.lovable.app`) and the preview URL in the browser tool; capture `read_console_logs` and `read_network_requests` to find the actual runtime error (likely one of: missing `VITE_BACKEND_URL` causing an unhandled throw at module init, `useLocation` / context-provider mismatch, a bad import, or an SSR-style env access).
2. Check `src/main.tsx` and `src/App.tsx` for any top-level code that throws when env vars are missing — wrap them in safe defaults so the bundle always boots.
3. Wrap the root tree in a **global ErrorBoundary** (`src/components/common/RootErrorBoundary.tsx`) so any future render crash shows a branded "Something went wrong — Reload" screen instead of a white page.
4. Confirm `BrowserRouter` wraps all components that call `useLocation` (including `Toaster`/`Sonner`, `SessionExpiredHandler`, `CookieConsentBanner`).
5. Verify `index.html` has the noscript + loading fallback so the user sees something even before React mounts.
6. Re-test published URL on mobile + desktop viewports after fix; confirm landing renders, `/chat` redirects to `/auth`, and `/auth` shows the form.

Acceptance: published link loads to a real UI on a logged-out browser within 3s, no console errors, sharable.

## Phase 1 — Google sign-in → single profile, role always seeded

1. **DB migration** — `ensure_profile_and_role()` SECURITY DEFINER RPC: idempotent upsert into `profiles` (display_name from `raw_user_meta_data.full_name || name`, avatar from `avatar_url || picture`) + insert default `'user'` role. Backfills any historical user missing a profile/role.
2. **Client** — Call this RPC from `onAuthStateChange` on `SIGNED_IN` in `App.tsx` and post-sign-in in `AuthPage.tsx` (email + Google). Toast on failure with link to `/auth/diagnostics`.
3. Deduplication is already enforced by `profiles.id = auth.users.id` PK; Supabase keys Google identities by email so the same Google account never produces two `auth.users` rows.
4. Test: `src/test/ensureProfileAndRole.test.ts`.

## Phase 2 — ChatGPT / Claude-style left sidebar

Rewrite `DesktopSidebar.tsx`:

- 260px expanded / 56px icon-rail collapsed, smooth width transition.
- Top: brand mark + collapse toggle + full-width "New chat" button.
- Search input filtering titles.
- Grouped sections: **Today / Yesterday / Previous 7 days / Older** by `updated_at`.
- Conversation row: truncate title, hover-reveal rename + delete (no clutter).
- Bottom-pinned user card: avatar + email + menu (Profile, Settings, Sign out).
- Mobile: `Sheet` from left, opens via header button **and** left-edge swipe (D20).

Mirror grouping in `MobileConversationSheet.tsx`.

## Phase 3 — Chat UX roadmap items (frontend-only)

| ID | Item | Implementation |
|----|------|----------------|
| D17 | Partial-stream persistence | Debounced 500 ms `saveConversation` during streaming loop in `ChatInterface.tsx`; resume on reload |
| D18b | Regenerate response | Button on last guru message → re-runs last user turn, replaces message; uses new `AbortController` plumbing in `aiService.ts` |
| D19 | Keyboard shortcuts | New `useChatShortcuts.ts`: ⌘/Ctrl+Enter submit, ⌘/Ctrl+/ focus, ⌘/Ctrl+B sidebar, ⌘/Ctrl+Shift+O new chat |
| D20 | Mobile swipe-from-left | New `useSwipeGesture.ts`; opens sidebar on >60px swipe |
| D21 | Mic tooltip pulse | First 3 sessions counter in `localStorage` |

## Phase 4 — Other ROADMAP items shippable this run (no backend infra)

- **C12** Daily-teaching webp + `srcset` via Supabase Storage transforms.
- **C13** Prefetch `/chat` chunk + warm `supabase.auth.getSession()` from landing.
- **G26** `react-helmet-async` per-route SEO (Landing, Chat, Practices, Privacy, Terms) + branded OG image.
- **G28** JSON-LD Organization + FAQPage on landing.

## Phase 5 — Items moved to ROADMAP (cannot ship from Lovable sandbox)

These need the FastAPI backend, Qdrant, Ollama, CI infra, or external keys — Lovable sandbox can't run/verify them. I'll **append/update** them in `docs/ROADMAP.md` with clear ownership notes so nothing is forgotten:

- **A2** Wire `chat-rate-limit` edge function into the Python `/api/chat/stream` path (backend change).
- **A3** PII redaction middleware in FastAPI logs.
- **B6** RAGAS thresholds in `make eval` + CI gate.
- **B7** Citation grounding — drop URLs absent from retrieved chunk metadata (Python `rag/nodes.py`).
- **B8** Semantic-cache hit-rate KPI surface in admin.
- **B9** A/B prompt shadow mode.
- **B10** Memory eval set.
- **C10** TTFT/total-latency/tok-s metrics on `/api/chat/stream`.
- **E22** Web-push (VAPID + `pg_net`).
- **H30** PWA via `vite-plugin-pwa` with `/~oauth` denylist (can be done in Lovable but requires testing on installed PWA).
- **I31** `i18next` en/hi/te/ml bundles.
- **J32** Sentry + PostHog (needs DSN/keys from user).
- **J33** `trace_id` propagation in SSE `done` event (backend change).
- **J34** Down-vote → `golden_questions` nightly job (backend).
- **K35** Playwright e2e.
- **K37** Backend pytest coverage gate.
- **L38–L40** Token budget, embedding cache, Ollama warmup (backend).
- **Out of scope:** Meta/Facebook OAuth (Lovable Cloud unsupported).

Each backend item gets a `> Owner: backend repo` note in ROADMAP so it's clear it must be done outside Lovable.

## Technical Details

**Files to create**
- `src/components/common/RootErrorBoundary.tsx`
- `src/hooks/useChatShortcuts.ts`, `src/hooks/useSwipeGesture.ts`
- `src/components/seo/SEO.tsx` (helmet wrapper)
- `supabase/migrations/<ts>_ensure_profile_and_role.sql`
- Tests: `ensureProfileAndRole.test.ts`, `useChatShortcuts.test.ts`, `DesktopSidebar.groups.test.tsx`, `RootErrorBoundary.test.tsx`

**Files to modify**
- `src/main.tsx` — mount `RootErrorBoundary`, safe env access.
- `src/App.tsx` — `HelmetProvider`, `ensure_profile_and_role` on `SIGNED_IN`, ensure all `useLocation` consumers are inside `BrowserRouter`.
- `src/pages/AuthPage.tsx` — call RPC + diagnostics toast.
- `src/components/chat/DesktopSidebar.tsx`, `MobileConversationSheet.tsx` — rewrite.
- `src/components/chat/ChatInterface.tsx`, `ChatMessage.tsx`, `ChatHeader.tsx` — partial save, regenerate, shortcuts, swipe, mic tooltip.
- `src/lib/aiService.ts` — `AbortSignal` support.
- `src/components/chat/DailyTeaching.tsx` — webp/srcset.
- `src/components/landing/HeroSection.tsx` — prefetch + session warm.
- `docs/ROADMAP.md` — move backend items into clearly labelled "Backend repo" section.

**Execution order:** Phase 0 first (verify with browser tool), then 1 → 2 → 3 → 4, then ROADMAP edits, then publish and verify the live link.