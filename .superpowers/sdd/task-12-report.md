# Task 12 Report — HealingPathCard streak-based integration

**Status: DONE**

## Summary

The chat now surfaces a healing course card based on **streak/repeated distress
patterns** (backend-recommended `recommended_course` preferred; local text-only
streak detector as fallback) instead of a single distress signal. A single
distress message no longer shows the card.

## Files changed

| File | Change |
| --- | --- |
| `src/components/chat/HealingPathCard.tsx` | Added `recommendedCourse` prop (per brief), `userTurnHistory` prop, exported `detectCourseTrigger()` local streak detector, fire-and-forget `/api/healing-course/assign` POST, dismissal reset on course change, reason line display |
| `src/components/chat/ChatInterface.tsx` | `recommendedCourse` state + `mapRecommendedCourse()` (backend payload → card prop shape, title resolved from local catalog), `userTurnHistory` memo from messages, set from streaming `done` chunk and non-streaming response, reset on new/incognito/select conversation, props passed to card |
| `src/components/chat/HealingPathCard.test.tsx` | New — 17 vitest tests (13 detector + 4 card render) |
| `src/lib/chat/types.ts` | `RecommendedCourse` interface; `recommendedCourse` on `AIResponse` + `done` StreamChunk |
| `src/lib/chat/transport.ts` | Maps `data.recommended_course` (direct + queue-poll paths) |
| `src/lib/chat/streaming.ts` | Maps `meta.recommended_course` in done chunk |
| `src/lib/chat/index.ts` | Re-exports `RecommendedCourse` type |

## Behavior

- **Course selection priority**: active enrolled course → backend
  `recommendedCourse.slug` → local streak trigger → nothing.
- **Local streak detector** (`detectCourseTrigger`, mirrors
  `services/healing_course_service.py` pattern order with text-only proxies):
  1. `escalation` — last 3 turns all distressed with ≥2 distinct signals
     (closest text-only proxy for rising severity; severity levels are
     backend-only)
  2. `freq_3_of_5` — ≥3 distressed turns in last 5
  3. `consecutive_2` — ≥2 consecutive distressed turns at the tail
  4. `repeated_signal` — same signal ≥2× within 24h
- **Single signal → no card** (key behavioral change per dispatch).
- **Assign POST** (`/api/healing-course/assign`, Bearer token when available,
  ref-guarded once per course, errors swallowed): persists backend assignment
  when a course shows for an un-enrolled seeker. History built from recent
  turns with `{distress_level, signal, timestamp}` per the endpoint contract.
- Dismiss/complete interactions unchanged; dismissal resets when a *different*
  course is recommended.

## Verification

- `npx tsc --noEmit` — clean.
- `npx vitest run src/components/chat/HealingPathCard.test.tsx` — 17/17 pass.
- Full `src/components/chat/` + `src/test/` run: 246 pass / 8 fail — all 8
  failures confirmed **pre-existing** via stash comparison (ChatInterface
  type-and-send, ChatMessage feedback tags ×3, LanguageSelector ×2, i18n
  parity ×2, mood-check-in) — fail identically without these changes.
- ESLint unusable repo-wide (environmental: minimatch/brace-expansion crash in
  ESLint 9.32 config load — also crashes on untouched files); not caused by
  this task.

## Notes for reviewers

- **Scope note**: brief named only the two component files, but consuming
  `recommended_course` from the chat response required minimal additive
  plumbing in the chat transport layer (`types.ts`, `transport.ts`,
  `streaming.ts`, `index.ts`). No backend, no `ProfilePage`, no metrics files
  touched.
- Backend payload `{slug, signal, pattern, reason}` (from
  `trigger_payload`) is mapped to the brief's prop shape
  `{slug, title, reason, trigger_signal}` in ChatInterface.
- `distressFlagged` prop kept in the interface for API compat but no longer
  used (nothing passes it; single-turn flag is out of scope of streak behavior).
