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

## Gotchas

- Active streaming checkpoints to `sessionStorage` every 500ms under `askmukthiguru_stream_checkpoint`; cleared in `finally`, restored on mount if < 60s old — preserve this contract when touching chat streaming.
- `useProfile` re-reads localStorage after server sync; call `clearProfile()` (from `profileStorage.ts`) on sign-out.
- Suspense fallbacks use `BrandedSpinner`, never bare "Loading..." text.
- The sidebar listens for the `conversation:updated` window event to refresh; dispatch it after mutating stored conversations.
