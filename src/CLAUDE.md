# CLAUDE.md — src/ (React frontend)

Vite + React 18 + TypeScript + Tailwind + shadcn/ui. Path alias `@` → `src/`. See the root `CLAUDE.md` for backend integration and full architecture.

## Commands (run from repo root)

```bash
npm run dev                                # Vite on http://localhost:8080 (falls back to 8081/8082)
npm test                                   # Vitest, single run
npx vitest run src/test/greeting.test.ts   # one test file
npm run test:watch                         # Vitest watch mode
npm run test:e2e                           # Playwright end-to-end
npm run lint                               # ESLint
npm run build                              # production build
```

Vitest config: `vitest.config.ts` — jsdom, `globals: true`, setup file `src/test/setup.ts`, includes `src/**/*.{test,spec}.{ts,tsx}`. Tests live in `src/test/` and `src/tests/`.

## Layout

- `pages/` — route components (react-router v6, routes wired in `App.tsx`).
- `admin/` — self-contained admin dashboard sub-app with its own `pages/`, `layout/`, `lib/` (adminAuth, filtersStore), guarded by `useAdminGuard`.
- `components/ui/` — shadcn/ui primitives; extend via composition, don't fork the primitives.
- `components/chat/` — chat UI (`ChatInterface` is the orchestrating component); `components/common/` — providers and error boundaries mounted in `main.tsx`/`AppShell`.
- `lib/` — non-React logic. `aiService.ts` has three modes: `placeholder` (canned, default), `custom` (FastAPI `POST /api/chat`), `openai`. Client state persists in localStorage-backed stores (`chatStorage`, `profileStorage`, `favoritesStorage`, `meditationStorage`); server data via `integrations/supabase/client`.
- Lazy routes go through `lib/lazyWithRetry.ts` (retries chunk-load failures), not bare `React.lazy`.

This build is also what ships inside the `android/` and `ios/` Capacitor wrappers (both git-tracked at repo root). For mobile-specific build/signing/store-submission concerns, see root `CLAUDE.md`'s "Mobile & Store Release" section and `docs/MOBILE_RELEASE_RUNBOOK.md` — not this file.

## Gotchas

- Active streaming checkpoints to `sessionStorage` every 500ms under `askmukthiguru_stream_checkpoint`; cleared in `finally`, restored on mount if < 60s old — preserve this contract when touching chat streaming.
- `useProfile` re-reads localStorage after server sync; call `clearProfile()` (from `profileStorage.ts`) on sign-out.
- Suspense fallbacks use `BrandedSpinner`, never bare "Loading..." text.
- The sidebar listens for the `conversation:updated` window event to refresh; dispatch it after mutating stored conversations.
- **Backend Polling & Railway Sleep Caution**: `useChatCapabilities` and `useMetrics` hit `/api/capabilities` and `/api/metrics`. In hosted/staging environments, avoid high-frequency polling intervals, as incoming HTTP traffic resets Railway's 10-minute Serverless inactivity timer and keeps backend containers continuously active.
- **Backend Status (Sep 20, 2026)**: All services (Backend, Memgraph, Qdrant) are currently **SCALED DOWN / OFFLINE** on Railway (Redis `● Sleeping`) to eliminate idle compute costs ($0/hr). To wake up: spin up databases first (`railway redeploy --service qdrant`, `railway redeploy --service memgraph`), then backend (`railway up` or `railway redeploy --service askmukthiguru-8119b0e8`).
