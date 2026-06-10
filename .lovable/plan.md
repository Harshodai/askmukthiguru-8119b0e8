# /chat Polish + Auth, Memory, Admin, 2FA

Scope is ruthlessly trimmed: visible chat UX first, then auth/admin/memory/2FA. No backend pipeline changes.

## 1. Chat UI overhaul (`ChatInterface`, `ChatMessage`, `MessageList`, `ChatHeader`, `ChatComposer`, `ThinkingPills`)

- **ThinkingPill font**: switch from default to the app's display/body token (`font-serif`/`font-display` per `tailwind.config.ts`); match weight, tracking, and color of guru bubbles.
- **Edit message UX**: replace inline textarea swap with a contained editor card — preserves bubble width, shows Save/Cancel + ⌘↵ hint, autosizes, focuses end-of-text, Esc cancels, optimistic update, re-runs only the affected turn (truncate downstream, regenerate).
- **Up-arrow recall**: in composer, when input is empty and caret at start, ArrowUp loads the last user message into the draft (cycles through history with repeated ArrowUp/ArrowDown). Currently not wired — add a `useMessageHistory` hook.
- **Suggested questions alignment**: change from left-justified ragged grid to a centered wrap with equal-height chips, max 3 per row on desktop, single-column on mobile, consistent padding and gap. Anchor to the empty-state container, not the message list.
- **Header upgrade**: increase header height (56 → 72px), larger guru avatar (40 → 48px), tighter two-line title (guru name + subtle "Beautiful State companion" subtitle), persistent model/memory indicator pill on the right, sticky with soft backdrop blur.

## 2. Google sign-in stuck on "Returning from Google…"

The 4-step progress UI (Returning → Connect → Authorize → Sign in) never advances past Authorize even when the Supabase session is set. Root cause: the post-redirect handler waits for an event that doesn't fire under the managed OAuth flow (tokens are set synchronously by `lovable.auth.signInWithOAuth`).

Fix in `AuthPage.tsx` / OAuth callback handler:

- After redirect, immediately poll `supabase.auth.getSession()` (with `onAuthStateChange` as a fallback listener).
- Drive the 4-step indicator from real signals: URL has `code`/hash → Connect ✓; session present → Authorize ✓; profile RPC `ensure_profile_and_role` ok → Sign in ✓; then `navigate(redirectPath)`.
- Add a 6s hard timeout that surfaces a "Continue" button calling `getSession()` + manual redirect, plus a toast with the failure reason.

## 3. Admin seed + creds

- Run a one-off SQL migration: insert `kharshaengineer@gmail.com` into `auth.users` if missing (via `promote_admin_by_email` RPC if user exists), then upsert `user_roles(user_id, 'admin')`.
- Since we can't set passwords from migrations safely, use the existing `backend/scripts/seed_admin.py` flow and surface the creds in chat: email `kharshaengineer@gmail.com`, password `Admin@123456` (already in seeder default). User must run the seeder once locally; alternative is to set the password via Cloud → Users.
- Verify `/admin` route guard uses `verifyAdminSession()` (JWT + `has_role` RPC) — already correct in `src/admin/lib/adminAuth.ts`; just confirm the route is reachable post-login.

## 4. Memory layer full E2E integration

Backend endpoints exist (`/api/memory/core|list|summaries|relevant|conversations`) and `memoryApi.ts` wraps them. Remaining gaps:

- **Chat header memory pill**: small "Memory: on · N facts" indicator that opens a popover listing the top relevant memories used for the current thread (calls `/api/memory/relevant` with last user message).
- **Per-message provenance**: when a guru message used retrieved memories, show a collapsible "Recalled from your reflections" chip under the bubble.
- **Profile MemoryManager**: add tabs (Core · Memories · Summaries · Conversations) instead of stacked cards; add manual "Add fact" and "Forget" actions wired to `POST /api/memory/add` and `DELETE /api/memory/:id`.
- **Auth-aware**: hide memory UI for anonymous users; show "Sign in to enable memory" CTA.
- **Error UX**: if any memory endpoint 404s, degrade silently per surface (no global toast spam).

## 5. Two-Factor Authentication

Supabase Auth supports TOTP MFA natively. Add:

- `SecuritySettings` panel in Profile → "Two-factor authentication" section.
- Enroll flow: `supabase.auth.mfa.enroll({ factorType: 'totp' })` → render QR + secret → user enters 6-digit code → `mfa.challenge` + `mfa.verify`.
- List/unenroll existing factors via `mfa.listFactors` and `mfa.unenroll`.
- On sign-in, detect `AAL1` and prompt for second factor before granting access to `/chat` and `/admin`.
- Admin route additionally requires `AAL2` for sensitive actions.

## 6. Additional improvements (token-optimized scope)

- **Composer**: shift+enter newline, enter to send, mobile-safe IME composition guard, attachment-disabled state with tooltip.
- **Streaming**: visible "Stop generating" button while `streaming`; preserves partial answer.
- **Scroll**: sticky-to-bottom only when user is within 100px of bottom; otherwise show "↓ New message" pill.
- **Accessibility**: aria-live="polite" on streaming guru bubble; focus-visible rings on all interactive chat elements; reduced-motion respects ThinkingPill animation.
- **Empty state**: replace generic copy with a warmer 2-line invitation + 3 curated starter prompts (rotates daily via `useDailyTeaching`).
- **Error toasts**: dedupe identical errors within 5s; "Retry" action on backend-unreachable.
- **Performance**: memoize `MessageList` group computation; defer markdown render for off-screen bubbles (already partially via `VirtualMessageWrapper`).

## Out of scope (explicit)

- No RAG pipeline / backend node changes.
- No new auth providers beyond Google + email.
- No design-direction prototypes — applying existing Golden Hour tokens.

## Technical notes

- Files touched: `src/components/chat/*`, `src/pages/AuthPage.tsx`, `src/pages/ProfilePage.tsx`, `src/components/profile/MemoryManager.tsx`, `src/lib/memoryApi.ts`, `src/hooks/useMessageHistory.ts` (new), `src/components/auth/MfaEnroll.tsx` (new), `src/components/auth/MfaChallenge.tsx` (new), one Supabase migration to ensure admin role row exists.
- No new dependencies required; `otplib`/QR via existing `qrcode.react` if not present add `qrcode.react` only.
- Tests: extend `aiServiceStreaming.test.ts` for stop-generation; add `useMessageHistory.test.ts`; MFA enroll happy-path test.
- Give me a documentation of what can be done from backend side as well, this entire thing should be working end to end without any issues

## Validation

- Manual: Google sign-in → lands on `/chat` within 3s; ArrowUp recalls; edit message regenerates; admin login → `/admin` works; enroll TOTP → sign out → sign in requires code; memory pill shows facts.
- Build + vitest run clean (zero-warning policy).