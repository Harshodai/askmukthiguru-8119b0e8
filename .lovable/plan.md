
# Plan: Security fixes, chat polish, admin drill-down repair, TTS verification

Four parallel tracks. Frontend-only for tracks 1–3 unless noted; track 4 also touches backend Python.

---

## 1. Security fixes (from scan)

### Frontend / Lovable Cloud (will fix in this project)
- **`src/hooks/useRequireAuth.ts`** — remove `console.log('[useRequireAuth] session:', …)` JWT leak. Gate any future debug behind `import.meta.env.DEV` with only `session?.user?.id`.
- **Edge functions** (`sarvam-stt`, `sarvam-tts`, `delete-my-account`, `export-my-data`) — stop returning `(e as Error).message`. Log full error server-side, return generic `"An internal error occurred. Please try again."` with proper CORS headers.
- **Supabase linter — `SECURITY DEFINER` callable by anon**: audit `has_role`, `whoami_diagnostics`, `ensure_profile_and_role`, `handle_new_user`. `handle_new_user` is a trigger (keep). For the other three, `REVOKE EXECUTE … FROM anon` via migration and keep `GRANT EXECUTE … TO authenticated` where needed. Update security memory to record that these are intentionally callable only by authenticated users.

### Python backend (out of this Lovable project's deploy scope — documented only)
The findings for `backend/app/main.py`, `backend/app/gradio_ui.py`, `backend/services/auth_service.py`, `backend/scripts/seed_admin.py`, and the hardcoded Sarvam key in `backend/scratch_*` / `backend/test_chunk_extraction.py` live in the separate FastAPI repo. I will:
- List them in `SECURITY_NOTES.md` at project root with exact remediation snippets (env-gated Gradio mount, JWT dep on STT/TTS, `ENABLE_TEST_AUTH` flag, generic 500 messages, env-only admin creds, Sarvam key rotation steps).
- Mark them as "tracked, fix in backend repo" in the security memory so the scanner doesn't keep re-flagging from this side.

---

## 2. Chat scrolling & thinking-pill alignment (`/chat`)

Files: `src/components/chat/ChatInterface.tsx`, `src/components/chat/MessageList.tsx`, `src/components/chat/ThinkingPills.tsx` (or wherever pills render), `src/components/chat/ChatMessage.tsx`.

- Replace ad-hoc scroll calls with a single `useAutoScroll` hook that:
  - Tracks `isNearBottom` (within 80px) via the scroll container.
  - On new message / streaming token / regenerate / edit-resubmit, scrolls to bottom only when user was near bottom (avoids yanking during scroll-back reading).
  - Uses `requestAnimationFrame` + `scrollIntoView({ block: 'end' })` on the sentinel after virtualizer commits.
- Fix post-stream gap: when streaming ends, recompute `VirtualMessageWrapper` measured height immediately (call `measure()` / drop cached `defaultHeight` for the just-finished row).
- Fix regenerate gap: ensure the old assistant row is removed in the same render tick the placeholder appears (no double-frame empty slot).
- Fix inline edit jump: after edit-resubmit, scroll to the edited user message top, not bottom, until streaming starts.
- Thinking pills alignment: render pills inside the same grid column / left-padding as guru messages (currently they sit at container left). Wrap in the same `<MessageRow role="assistant">` shell so avatar gutter + content column match.

---

## 3. Admin dashboard drill-downs + page audit

Files: `src/admin/pages/*`, `src/admin/lib/api.ts`, `src/admin/lib/filtersStore.tsx`, `src/admin/hooks/useAdminData.ts`, route table in `src/App.tsx`.

- E2E sweep every admin route (Overview, Query Tracing, Conversations, Evals, Alerts, Users, Settings, Latency, etc.) via Playwright spec `tests/e2e/admin-drilldowns.spec.ts`:
  - For each list page, click first row → assert detail route renders, no error boundary, key fields present.
  - For each metric tile, click → assert filter applied + table populated.
- Fix query tracing drill-down: the detail page likely 404s because the route param key or `getQueryTrace(id)` lookup is broken. Repair by:
  - Verifying route path matches link (`/admin/queries/:id`).
  - Fixing `api.ts:getQueryTrace` to handle the nullish-date defaults added previously (some traces had `null` from/to causing filter to drop them).
- For any admin page that fails to open, capture the error, fix imports/missing exports/lazy-load issues.
- Add a small "Drill-down health" panel on the Overview that runs the same checks at runtime in dev mode only.

---

## 4. TTS voice + metrics verification page

New route: `/diagnostics/voice-metrics` (dev + admin-gated).

- Page renders:
  1. Current speaker from profile (`useProfile`), dropdown to switch (writes via existing profile update path).
  2. "Speak sample" button — calls `useTextToSpeech().speak("Test")` and shows the actual `SpeechSynthesisUtterance.voice.name` used (proves the new speaker took effect on the next utterance, no reload needed).
  3. "Fire test meditation event" button — dispatches `askmukthiguru:meditation_completed` and shows live counters from `MeditationStats` reading.
  4. Pass/fail badges + last-event log.
- Backed by a small Vitest unit test (`src/test/voiceMetricsDiagnostics.test.tsx`) asserting the speak callback uses the latest `speaker` value after change, and that the meditation event listener increments stats.

---

## Confidence & rollout
- Security track ships first (smallest blast radius, highest value).
- Chat scroll + pills then admin drill-downs (largest surface, run Playwright before claiming done).
- TTS verification page last; it's the safety net for the earlier TTS fix.

### Out of scope
- Rewriting the virtualization library.
- Backend Python edits (documented, not changed here).
- Any new business logic in chat — pure UI/scroll behavior.
