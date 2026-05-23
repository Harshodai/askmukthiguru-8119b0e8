## Bug fixes + production-readiness audit

### Part 1 — Bugs to fix in this pass

1. **Runtime crash: `Cannot read properties of null (reading 'useEffect')` in `src/App.tsx:109`**
   Almost always caused by a duplicate React copy or React being null at import time (commonly: importing `useEffect` from the wrong package, or a circular import in something `App.tsx` pulls in). Inspect line 109 + imports, dedupe React, and verify the dev server restart resolves it. This is the highest-priority bug — the app currently doesn't mount.

2. **Broken Google logo SVG** (`src/pages/AuthPage.tsx` ~line 389)
   The 4th `<path d="...">` is malformed (`...3.47 2.18 7.07l...` is missing a command letter) and all paths use `currentColor` instead of Google's brand colors. Replace with the correct 4-path, brand-colored Google "G".

3. **"Signing you in…" flash for already-logged-in visitors**
   `handleSession` unconditionally sets `googleStep='finalizing'`. Gate it on an active Google telemetry run / `GOOGLE_STEP_KEY` flag.

4. **Telemetry mislabels run errors as `navigate` step errors** (`src/lib/authTelemetry.ts` `endAuthRun`)
   Add a `run_error` step name and use it instead of reusing `navigate`, so the dashboard's per-step error rate stays accurate.

5. **`redirectingRef` never reset on failure** (`AuthPage.tsx`)
   Wrap `handleSession` body in try/finally so a thrown error doesn't permanently block subsequent `onAuthStateChange` events.

6. **Layout shift on Google button** — keep the colored logo visible and render the spinner alongside it instead of replacing it.

### Part 2 — End-to-end "does every page open" check

Add a Playwright smoke test (`tests/e2e/page-smoke.spec.ts`) that visits each route and asserts no console errors + the expected H1/heading renders. Routes to cover:

- `/` (Index)
- `/auth` (AuthPage)
- `/reset-password`
- `/auth/diagnostics`
- `/auth/latency` (the dashboard added earlier)
- `/chat` (with mocked auth)
- `/profile` and `/profile?onboarding=true`
- `/practices` and `/practices/:slug` (one slug)
- `/privacy`, `/terms`
- `/admin/*` (with mocked admin role): dashboard, conversations, prompts, evals, settings, ask-data
- `*` (NotFound shows 404)

Each test waits for network idle, asserts no uncaught console errors, and snapshots the visible heading. Run via `npx playwright test tests/e2e/page-smoke.spec.ts`.

### Part 3 — Wider production-readiness audit

Run these checks and report findings inline (no code changes unless a fix is trivial):

- **Build & types**: `npm run build` clean, no TS errors (already relaxed in tsconfig — note this as tech debt).
- **Lint**: `npm run lint` clean.
- **Unit tests**: `npm test` — confirm Vitest suite passes; flag flaky / skipped tests.
- **Edge functions**: list functions (`sarvam-stt`, `sarvam-tts`, `chat-rate-limit`, `delete-my-account`, `export-my-data`), verify each handles CORS preflight, validates JWT, and has secrets configured. Check logs for recent 5xx via `supabase--edge_function_logs`.
- **Supabase linter**: run `supabase--linter`, list every warning, propose fixes for RLS gaps.
- **Security scan**: run `security--run_security_scan`, classify findings as must-fix vs accept.
- **Auth flow**: confirm Google + email signup/signin/reset both work end-to-end via Playwright; check the new latency dashboard renders with seeded data.
- **STT/TTS**: confirm Sarvam STT/TTS edge functions return 200 for a sample payload in en-IN, hi-IN, te-IN, ml-IN; confirm Web Speech fallback path triggers on failure.
- **Chat**: send a complex query in each supported language, verify language is preserved on the response and TTS plays in the same language.
- **Profile language**: confirm preferred language loads from profile and applies before the first chat request after a hard refresh.
- **Realtime / DB**: confirm `conversations`, `chat_messages`, `meditation_sessions` writes work under RLS for an authenticated user and are blocked for anon.
- **Performance**: check route bundle sizes, Lighthouse score on `/` and `/chat`, time-to-interactive on slow 3G.
- **SEO basics**: title <60 chars, meta description, single H1, alt text, JSON-LD where applicable on landing pages.
- **Error boundaries**: confirm an error in `ChatPage` doesn't blank the whole app.

### Part 4 — Prod-readiness confidence score

After running Part 3, deliver a 1–10 score with a short rubric breakdown:

```
Build/Types      : x/10
Tests            : x/10
Security/RLS     : x/10
Auth flow        : x/10
Edge functions   : x/10
Voice (STT/TTS)  : x/10
Performance/SEO  : x/10
Observability    : x/10
-------------------------
Overall          : x/10  →  Ship / Ship with caveats / Do not ship
```

Each sub-score is justified with the concrete findings from Part 3, plus a prioritized "must-fix before prod" list.

### Out of scope

- No refactor of the OAuth flow, dashboard layout, or session caching (already implemented in prior turns).
- No new product features.
- Backend RAG pipeline changes are not in scope unless an edge function is outright broken.
