# 5-Credit Closeout Plan — Audit-Driven

Most of the 9-page audit is already shipped from prior turns. Rather than re-do polish, this run **verifies** and **closes real gaps only**. Ponytail rule: if it's already on screen, don't rebuild it.

## What's already done (verified in codebase)
- Auth glass card + dark Google button (`AuthPage.tsx`)
- Google single-redirect fix (removed redundant `getSession`)
- Navbar floating glass pill (`Navbar.tsx` — `rounded-full backdrop-blur-2xl`)
- Particles dimmed + breathing (`BackgroundParticles.tsx` — opacity 0.18–0.4, mobile-capped)
- Second Brain empty state with lotus + CTA
- Chat glass modal, composer focus ring, ThinkingPills wired
- Profile stat tiles + scrollable tab rail
- Serene Mind: merged player, Preethaji audio, TTS fallback, video link
- Knowledge Graph: public, force-directed, Obsidian-style
- i18n: 6 real locales + 5 fallbacks registered; parity regression test in place
- Forgot-password: `/reset-password` route + Playwright happy-path passing

## In scope this run (~4.2 cr)

### 1. i18n coverage — close the gap, not the ocean (1.2 cr)
Subagent A reads `I18N_GAPS.md` (108 strings) → produces a **prioritized diff**: which strings are user-facing on live routes vs admin/dev. Main thread wraps only the user-facing ones with `t()` and adds keys to `en/hi/te/kn/ta/mr.json`. Deferred: bn/gu/ml/as/sa stay as English fallback (they're registered, users see English — acceptable per `I18N_STATUS.md`).

### 2. Google login — verify single redirect end-to-end (0.4 cr)
Playwright: open `/auth` → click Google → assert exactly one navigation back to app origin, no `/auth?code=...` bounce. If it bounces, patch `redirectTo` to `${origin}/auth/callback` and add a callback route that reads intended path from sessionStorage.

### 3. Forgot password — real reset email E2E (0.8 cr)
Cannot automate inbox click-through without a test mailbox. Instead:
- Use Supabase admin API via edge function to **generate a recovery link** for a test user
- Playwright: navigate to that link → submit new password → sign in with new password → assert authenticated route loads
- This exercises the real Supabase reset flow without needing IMAP

### 4. Chat design-sync sweep — one pass, three breakpoints (1.0 cr)
Playwright screenshots of `/chat` at 375/768/1280:
- Assert composer doesn't overlap thinking pills
- Assert user bubble contrast (primary/primary-foreground)
- Assert assistant messages have no bg
- Assert sidebar hidden <768px, floating toggle visible
- Fix any regressions found in the same turn (bounded to `ChatInterface`, `ChatMessage`, `ChatComposer`, `DesktopSidebar`)

### 5. LightRAG persistent volume note (0.2 cr)
Backend infra — cannot mount Railway volume from Lovable. Update `handoff_railway.md` with the exact env var (`LIGHTRAG_WORKING_DIR=/data/lightrag`) and Railway CLI command. Code already reads env var per prior turn — no code change needed.

### 6. Verification pass (0.6 cr buffer)
`bun run build`, `bun test`, Playwright suite. Report deltas.

## Explicitly deferred (not this run)
- Full 8-locale translation (bn/gu/ml/ur/or/pa/as/sa) — needs Gemini batch, ~2 cr per locale
- Admin console i18n — English-only by design
- Practice detail custom YouTube overlay, guru portrait bleed, profile aura ring — audit items P2/P3, cosmetic
- Landing "editorial hero split" — already partially shipped with `font-sacred`; further weight tuning is subjective polish

## Execution shape (one turn, heavy parallelism)
- **Subagent A**: read `I18N_GAPS.md`, classify each entry as user-facing/admin/dev, output actionable list
- **Subagent B**: audit `AuthPage.tsx` + `signInWithOAuth` call sites, confirm single-redirect or flag exact fix
- **Main thread**: wire `t()` calls, add locale keys, write Playwright specs, update handoff
- **Playwright** (one script): Google redirect count + forgot-password reset E2E + chat responsive screenshots
- Close with a delta report

## Confirm
Reply **"go"** to execute exactly this. Reply **"only i18n"** or **"only forgot-password E2E"** to narrow further. Reply **"add X"** and I swap X in for a similar-sized item.