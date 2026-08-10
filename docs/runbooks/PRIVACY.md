# Runbook: Frontend Privacy — Sentry Replay Masking & Meditation Resume Purge (P1-FE-14 / P1-FE-15)

> **Status:** Code-deliverable scope shipped. Both findings are resolved in
> the `ruthless-audit-remediation` worktree (commits listed in
> `.superpowers/sdd/p1-fe-14-15-report.md`). This runbook documents the
> decisions, the privacy rationale, and the operational knobs.

## Purpose

AskMukthiGuru is a spiritual wellness app. Users share personal and
spiritual questions with the Guru in chat, and write reflections/journal
entries after meditation. Two frontend findings exposed that content:

- **P1-FE-14** — Sentry error replays (`replaysOnErrorSampleRate: 0.5`)
  captured the DOM, including the chat UI, with no masking.
- **P1-FE-15** — the Serene Mind mid-session resume payload
  (`serene_mind_resume_v1`, localStorage, 24 h TTL) survived sign-out and
  was re-offered to the next user on a shared device ("resume?" prompt with
  the previous user's step/session state).

## What shipped

### P1-FE-14 — Sentry replay masking (`src/lib/sentry.ts`)

The Sentry Replay integration is now created with privacy masking:

```ts
Sentry.replayIntegration({
  maskAllText: true,
  blockAllMedia: true,
  maskInputs: ['textarea', 'input'],
})
```

- `maskAllText` — all text nodes are replaced with `*` in replay frames;
  chat bubbles, step instructions, journal text, and greetings never appear
  in recordings.
- `blockAllMedia` — images/video (avatars, YouTube embed) are blocked.
- `maskInputs` — textarea/input values (journal, gratitude, chat composer)
  are masked even if `maskAllText` is ever relaxed.
- Sample rates are **unchanged** (`replaysSessionSampleRate: 0`, `replaysOnErrorSampleRate: 0.5`) — masking, not disabling, was the chosen stance.
- Sentry init remains gated on `VITE_SENTRY_DSN` + production build
  (P1-FE-5 contract — do not regress).

### P1-FE-15 — Meditation resume purge on sign-out

- New tiny module `src/lib/meditationResume.ts` owns the key constant
  `MEDITATION_RESUME_KEY` and `clearMeditationResume()`. It has no
  component dependencies, so auth/lib modules can purge without importing
  the meditation UI graph.
- `GuidedMeditationFlow.tsx` now imports the key/clearer from that module
  (single source of truth).
- Purge points (both are idempotent no-ops when nothing is stored):
  1. `supabase.auth.signOut` monkey-patch in
     `src/components/common/SessionExpiredHandler.tsx` — the app-wide
     sign-out choke point (UserMenu, ProfilePage, AuthPage, MFAChallenge,
     useRequireAuth, admin all call through it).
  2. `clearProfile()` in `src/lib/profileStorage.ts` — the documented
     sign-out cleanup hook (src/CLAUDE.md: "call `clearProfile()` on
     sign-out").

## Privacy rationale / GDPR stance

- Chat and meditation content is **personal/special-category data**; the
  user has a right to forget. No playback mechanism must retain or display
  it after the fact.
- Replay masking keeps error debugging functional while guaranteeing chat
  content never leaves the browser in readable form.
- The resume payload is purged on **every** sign-out, so a shared device
  can never surface user A's session state to user B. The 24 h TTL remains
  for the single-user case (unexpected close → resume) but sign-out is a
  hard boundary.
- The audit found **no other cross-user 24 h resume keys**: the only other
  persistent cross-user keys are `askmukthiguru_profile`
  (`clearProfile`-purged), chat history stores (user-scoped conversations),
  and device-level prefs (sidebar, cookie consent, tour flags). Remaining
  per-session state uses `sessionStorage` (per-tab, cleared on tab close).

## Operational knobs

| Need | Action |
|---|---|
| Disable replay entirely (last resort) | Set `replaysOnErrorSampleRate: 0` and `replaysSessionSampleRate: 0` in `src/lib/sentry.ts`, or drop the `replayIntegration` call. |
| Disable Sentry wholesale | Remove `VITE_SENTRY_DSN` from the production env (existing P1-FE-5 gate). |
| Loosen masking | Remove `maskAllText`/`blockAllMedia`/`maskInputs` — **do not** without a privacy review. |
| Extend sign-out purge to another key | Add the key to `clearMeditationResume()` or the module; wire the same call at the purge points. |

## Verification

- Unit: `npx vitest run src/test/GuidedMeditationFlow-signout.test.tsx`
  (purge + wiring) and `npx vitest run src/test/sentry-init.test.tsx` and
  `src/test/SessionExpiredHandler.test.tsx` (regression — replay options
  and sign-out patch must not break existing contracts).
- Manual: sign in → start Serene Mind → close mid-session → sign out →
  sign in as a different user → open Serene Mind: **no** resume prompt.

## Rollback

`git revert` the two P1-FE commits (`fix(P1-FE-14): …`, `fix(P1-FE-15): …`).
Both are additive; reverting restores the pre-fix behavior.

## Cross-references

- `src/lib/sentry.ts` — masking options (P1-FE-14).
- `src/lib/meditationResume.ts` — key + purge helper (P1-FE-15).
- `src/components/common/SessionExpiredHandler.tsx`, `src/lib/profileStorage.ts` — purge wiring.
- `.superpowers/sdd/p1-fe-14-15-report.md` — implementation report.
