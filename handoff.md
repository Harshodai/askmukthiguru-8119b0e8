# Handoff — AskMukthiGuru session (2026-07-06)

## 1. Goal we are working toward

Two intertwined threads, both explicitly "ruthless, end-to-end, no compromise on quality":

- **Reliability/latency**: get the RAG pipeline actually working end-to-end with low latency across "all kinds of answers," despite Ollama Cloud's session quota being exhausted. User explicitly authorized using NIM / Sarvam / OpenRouter as alternatives to Ollama, and gave standing authorization to work at **"full ruthless scope, cost be damned"** for the remainder of the session.
- **UI/UX quality**: the user repeatedly said the Chat UI "doesn't look/feel good" and, most recently, asked for a ruthless end-to-end UI/UX pass across the **chat page (primary)** and **all admin pages**, using a UI/UX checklist referenced from `github.com/nextlevelbuilder/ui-ux-pro-max-skill` (not an installed skill — its checklist was fetched via WebFetch and applied manually: no emoji-as-icon, cursor-pointer on clickables, 150–300ms hover transitions, 4.5:1 contrast, focus-visible states, `prefers-reduced-motion`, responsive breakpoints at 375/768/1024/1440px).
- Standing recurring instruction (repeated multiple times by the user): **append findings/fixes to `lessons.md`** after each round of work, per the convention already established there.

## 2. Current state of code

- **Frontend builds clean**: `npx tsc --noEmit` passes with zero errors after all changes.
- **Backend provider**: `LLM_PROVIDER=nim` in `backend/.env` (switched back from `ollama` since Ollama Cloud quota is exhausted; NIM has a confirmed-working key with good observed latency, ~2.5s for simple queries). Sarvam and OpenRouter are wired as fallbacks inside `backend/services/nim_service.py` (`_fallback_to_sarvam` → chains to `_fallback_to_openrouter` on failure), but NIM is the primary path.
- **A real production-risk bug was found and fixed this session**: `/chat` intermittently hard-crashed to the `RootErrorBoundary` fallback. Root cause chain:
  1. An **active stale service worker** (`public/sw.js`) was serving cached JS — confirmed via `navigator.serviceWorker.getRegistrations()`, fixed by unregistering + clearing its caches in the live preview.
  2. Even with the SW cleared, a cold dev-server's first `/chat` load still throws once (`TypeError: Cannot read properties of null (reading 'useState')` in `GuidedMeditationFlow`) then self-heals via React 18's `recoverFromConcurrentError` — a known React+Vite+`lazy()`+Suspense dev-only artifact, not itself a production bug.
  3. **The real production risk**: `App.tsx` lazy-loads all 38 routes into content-hashed chunks; the SW takes over open tabs immediately (`skipWaiting`/`clients.claim()`) with no reload prompt. After any real deploy, an already-open tab can request a chunk the server no longer has → crash, exactly matching the bug reproduced above.
  4. **Fixed**: added `src/lib/lazyWithRetry.ts` (wraps `React.lazy`, auto-reloads once on a failed dynamic import, guarded by a `sessionStorage` flag against reload loops) and switched all 38 `lazy(() => import(...))` call sites in `App.tsx` to use it. Added a `controllerchange` listener in `main.tsx` so an open tab reloads when a new SW takes control instead of running mismatched against removed assets.
- **UI/UX audit findings applied** (from three parallel background-agent audits, ~100 findings total, triaged to highest-leverage):
  - Global `prefers-reduced-motion` override added in `src/index.css` (`@layer base`) — covers every `animate-spin`/`animate-pulse`/`animate-ping` and infinite Framer Motion loop app-wide in one rule (previously only `.theme-transition` respected it).
  - Emoji-as-functional-icon replaced with lucide-react icons in: `GuidedMeditationFlow.tsx` (mood picker + Namaste/completion circles), `SereneMindModal.tsx` (`✓` → `Check`), admin `TraceDrawer.tsx` / `QualityPage.tsx` (`👍`/`👎`/`⚠` → `ThumbsUp`/`ThumbsDown`/`AlertTriangle`), `LiveFeed.tsx` (`⚠` → `AlertTriangle`), `DailyTeachingPage.tsx` (`✓ Published!` → `CheckCircle2`).
  - **False positive caught and deliberately left alone**: the 🙏 glyph in `ChatHeader.tsx` — confirmed it's a deliberate, `aria-hidden`, app-wide brand mark also used identically on the landing `Navbar.tsx`, not a stray inconsistency. Not every automated finding is a real bug — verify against the rest of the codebase first.
  - Added confirmation dialogs (shadcn `AlertDialog`, previously imported nowhere in the codebase) around three previously-unguarded destructive admin actions: `AdminsPage.tsx` "Revoke" access, `EvalsPage.tsx` delete golden question, `DailyTeachingPage.tsx` remove active teaching + per-history delete. Also added missing `aria-label`s on `EvalsPage.tsx`'s icon-only Edit/Delete buttons, and bumped one `/60` low-contrast hint text to `/80`.
- Earlier in this session (before a context compaction — see `lessons.md` for full entries): fixed a live-reproduced `langgraph.errors.InvalidUpdateError` HTTP 500 in `rag/nodes/utils.py`'s `log_metrics` fallback, fixed several circuit-breaker/429-handling bugs in `ollama_service.py`, fixed a `verify_answer` tier3_complex fast-exit that skipped faithfulness checking entirely, consolidated ad-hoc Neo4j driver construction into a shared `ServiceContainer.neo4j_driver`, and did two earlier rounds of Chat UI fixes (sidebar defaulting to collapsed, duplicate disclaimer text, FAB overlapping the greeting screen, Claude.ai-style centered redesign, English-greeting fix, particle visibility, message spacing, and an inline-actions memoization bug that leaked action buttons onto the wrong message).

## 3. Files actively being edited (per `git status`)

Frontend (this UI/UX round):
- `src/App.tsx` — all 38 lazy routes switched to `lazyWithRetry`
- `src/lib/lazyWithRetry.ts` — **new file**, untracked
- `src/main.tsx` — added SW `controllerchange` reload listener
- `src/index.css` — global `prefers-reduced-motion` override
- `src/components/meditation/GuidedMeditationFlow.tsx` — emoji → icons
- `src/components/chat/SereneMindModal.tsx` — emoji → icon
- `src/admin/components/{LiveFeed,TraceDrawer}.tsx`, `src/admin/pages/{AdminsPage,DailyTeachingPage,EvalsPage,QualityPage}.tsx` — emoji → icons + AlertDialog confirmations + aria-labels

Also dirty from earlier in this session (not re-touched this round, see `lessons.md` for context): `src/components/chat/{ChatComposer,ChatInterface,ChatMessage,InlineActions,MessageList}.tsx`, `src/components/common/ui/BackgroundParticles.tsx`, `src/lib/greeting.ts`, `src/test/chat/transport.test.ts`, `src/test/components/ChatInterface.test.tsx`, `src/test/greeting.test.ts`.

Backend, dirty from earlier in this session (see `lessons.md`): `backend/app/pipeline/stages/graph_stage.py`, `backend/benchmarks/{native_eval,ruthless_benchmark}.py`, `backend/ingest/pipeline.py`, `backend/rag/states.py`, `backend/scripts/ops/reprocess_contextual.py`, `backend/services/nim_service.py`, `backend/tests/{test_abstractions,test_ollama_rate_limit}.py`.

Untracked, unrelated to this session's edits (pre-existing or ecc-scaffolding, not reviewed): `backend/CLAUDE.md`, `src/CLAUDE.md`, `backend/tests/test_graph_stage_fixes.py`, `scripts/ui-explore.mjs`, `scripts/ui-sending.mjs`, `.kiro/steering/caveman.md`, `.python-version`, `backups/`, `data/dump/`, `openwiki/.last-update.json`.

`lessons.md` has a dated entry for every round of work described above — it is the fullest record of what changed and why.

## 4. Everything tried and failed (or partially failed)

- **Tried**: assuming the `/chat` crash was a code bug in `GuidedMeditationFlow` itself. **Failed to find one** — the component's hook usage is correct, JSX usage (`<GuidedMeditationFlow ... />`) is correct, no duplicate `react` package exists in `node_modules` (checked directly). The crash was environmental (stale SW + a dev-only React/Suspense race), not a logic bug in that file.
- **Tried**: `rm -rf node_modules/.vite` (clear Vite's dependency pre-bundle cache) as the fix. **Did not fully resolve it** — the crash still occurred once on the next fresh load; it was the stale service worker + React's built-in retry, not a stale-deps-cache issue, that explained the behavior.
- **Tried**: assuming the landing-page brand glyph (🙏 in `ChatHeader.tsx`) was a bug per the automated audit. **Correctly stopped short of "fixing" it** after checking `Navbar.tsx` and finding the same glyph used the same way — it's intentional, not left half-fixed, just deliberately not touched.
- **Did not attempt**: live-clicking the admin `AlertDialog` confirmations in the browser — the admin console requires a real Supabase login with no dev bypass (confirmed: `useAdminGuard.ts` has no `VITE_*`/dev-bypass flag). Verification for admin pages this round is **type-check only** (`tsc --noEmit` clean), not visually confirmed live.
- **Did not attempt**: fixing the remaining ~70 lower-severity findings from the three background audits (loading/error-state ambiguity on `TelemetryPage`/`QualityPage`/`AlertsPage`/`TriggersPage`; no pagination/virtualization on `FeedbackPage`; no back-navigation between `GuidedMeditationFlow`'s reflection steps; unverified `overflow-x-auto` wrapping on several dense admin tables; `AdminShell`'s sidebar has zero responsive/mobile collapse). These were explicitly deferred, not silently dropped — logged in `lessons.md`.
- **Not re-verified since the provider switch**: the user's explicit ask "I want everything to be working and with less latency all kinds of answers should be obtained" after switching `LLM_PROVIDER` back to `nim` was acted on (`.env` change + `docker compose up -d --build backend`, confirmed exit 0) but **no fresh end-to-end live chat query has been sent to confirm NIM is now serving correct, low-latency answers post-rebuild** in this window — the last live-verified NIM query was earlier in the session, before switching to Ollama and back.

## 5. Next step

1. **Fire a live end-to-end chat query** against the rebuilt NIM-backed backend (a real doctrine question, not a health check) and report actual latency + correctness back — this is the one explicitly-requested item that was acted on but never re-confirmed live.
2. **Live-verify the admin `AlertDialog` fixes** by logging into `/admin/login` with real credentials and clicking through Revoke / Delete golden question / Delete teaching to confirm the dialogs render and the underlying mutations still fire correctly — this round's admin changes are only type-checked, not click-tested.
3. If continuing the UI/UX ruthless pass: tackle the deferred loading/error-state ambiguity on `TelemetryPage`/`QualityPage`/`AlertsPage`/`TriggersPage` next — it's the highest-severity remaining category (an admin investigating an incident could mistake "still loading" for "genuinely zero events").
4. Consider splitting `ChatInterface.tsx` (1942 lines — noted twice now in `lessons.md` as ~2.4x over the project's own 800-line file guideline) before further chat-page UI work; duplicate-JSX and stale-closure bugs found this session (duplicate disclaimer, FAB overlap, inline-actions memo leak) all trace back to this file's size.
