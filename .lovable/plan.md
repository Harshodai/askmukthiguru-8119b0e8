# Ruthless 5-Credit Plan

Your request is ~14h of design + i18n audit + E2E email test + OAuth debug + LightRAG infra. That is **not** a 5-credit job — honest estimate is 25–35 credits done well. Trying to cram it all guarantees half-broken output across everything.

Ponytail cut: ship the items that unblock trust/launch, defer polish.

## In scope (this 5-credit run)

1. **Google login single-redirect fix** — audit `AuthPage.tsx` + `redirectTo`, verify same-origin callback, remove double redirect. (~0.5 cr)
2. **Auth page dark Google button + glass card** — P0 trust fix. (~0.5 cr)
3. **Second Brain empty state** — lotus + CTA, no more void. (~0.4 cr)
4. **LightRAG persistent volume** — add `LIGHTRAG_WORKING_DIR` env, mount instructions in `handoff_railway.md`, code reads env. (~0.4 cr) -> no need of this
5. **Landing navbar → floating glass pill + hero typography split** — highest-ROI visual. (~0.8 cr)
6. **i18n audit (report only, not full translation)** — subagent scans `src/**` for hardcoded strings vs `t()`, outputs `I18N_GAPS.md` with file:line list. Actual translation of 8 fallback locales stays deferred (needs 2 cr/locale via Gemini batch). (0.6 cr)
7. **Forgot-password E2E via Playwright** — trigger reset from `/auth`, assert email enqueued in `email_send_log` via Supabase read, assert `/reset-password` renders form. Real inbox delivery **cannot** be automated here (no test mailbox); I'll verify the send path and hand you a manual 30-sec check. (~0.6 cr)
8. **Chat modal glass + composer focus ring** — quick token pass. (~0.4 cr)

Buffer: ~0.8 cr for verification (build, one Playwright screenshot sweep at 375/768/1280).

## Explicitly deferred (needs its own credits)

- Full translation of bn/gu/ml/ur/or/pa/as/sa (8 locales × Gemini batch)
- Practices hero card, guru portrait bleed, profile aura ring, KG warm canvas + node-label backend fix, practice-detail custom YouTube overlay, particle breathing animation, mood chips double-bezel, AI disclosure reframe, Plus Jakarta Sans load -> need this, this is needed
- Full multi-viewport design-sync sweep across every page -> need this, this is needed
- Real forgot-password inbox click-through (needs a test mailbox service you haven't wired) -> need this, this is needed

Say the word and I'll queue those as a follow-up.

## Execution shape (one turn, parallel where possible)

- **Subagent A** (fast): scan for i18n gaps, write `I18N_GAPS.md`.
- **Subagent B** (fast): grep `AuthPage.tsx`, `lovable.auth.signInWithOAuth` usage, `redirectTo` sites; return the exact double-redirect cause.
- **Main thread, batched**: edit AuthPage (Google button + card + spiritual copy), Navbar (glass pill), HeroSection (typography split), SecondBrain empty state, ChatInterface modal glass, LightRAG env plumbing.
- **Playwright**: forgot-password path + 3-viewport screenshot sweep of landing + auth + chat + second-brain.
- Report back with what's shipped, what the i18n gaps report says, and the OAuth root cause.

## Confirm

Reply "go" and I execute exactly this. Reply "add X" and I'll swap X in for something of similar size — total stays 5 cr. Reply "do it all anyway" and I'll warn you again then start, but quality will suffer.