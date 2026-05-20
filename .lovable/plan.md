## Goal

Make the multilingual `/chat` experience production-ready end-to-end: language is loaded from the user's profile before the first request, Sarvam STT/TTS work through secure edge-function proxies, the UI never fails silently when a voice is missing, and there's an automated browser smoke test to prove the whole flow works.

## Phase 1 — Audit & status report on prior fixes

Read & summarize the actual state of:
- `useProfile` + `ChatInterface` language wiring (does language hit `setAILanguage` before the first request, or only on a later effect tick?)
- `LANGUAGES` array vs. what's rendered in `LanguageSelector` (user reports "only some languages") — confirm scroll/overflow on small viewports
- `useTextToSpeech` Sarvam fallback path (currently calls `/api/speech/tts` against an external backend that isn't deployed → silent failure in prod)
- `useSpeechRecognition` (Web Speech only, no Sarvam streaming)
- `handle_new_user` trigger vs. `ensure_profile_and_role` RPC — is `display_name` reliably populated for Google sign-ins?

Deliver as a short written report (no code changes in this phase).

## Phase 2 — Profile language load order (race fix)

Change `ChatInterface` so the **first** chat request always uses the profile's `preferred_language`:

- Block the input/composer until `useProfile` resolves (skeleton state), OR
- Initialize `aiService.currentLanguage` synchronously from a `localStorage` mirror of the last-known profile language, then reconcile on profile load.

`profileStorage.ts` already mirrors to localStorage — wire it into `aiService` module init so refresh never starts in `en` by accident.

## Phase 3 — Sarvam edge-function proxies (STT + TTS)

Two new Supabase edge functions (require `SARVAM_API_KEY` secret — will prompt):

- `supabase/functions/sarvam-tts/index.ts` — POST `{ text, target_language_code, speaker? }` → returns `{ audio: base64 }`. Proxies to `https://api.sarvam.ai/text-to-speech`. JWT-verified, rate-limited per user.
- `supabase/functions/sarvam-stt/index.ts` — POST multipart `{ audio: Blob, language_code }` → returns `{ transcript, detected_language }`. Proxies to `https://api.sarvam.ai/speech-to-text`. JWT-verified.

Update `useTextToSpeech.ts` to call `supabase.functions.invoke('sarvam-tts', …)` instead of the dead `/api/speech/tts` path.

## Phase 4 — Sarvam mic streaming with detected language

New `useSarvamSpeech` hook:
- Uses `MediaRecorder` to capture mic audio.
- On stop, posts the blob to `sarvam-stt` edge function with the currently selected `language_code`.
- Returns `{ transcript, detectedLanguage }`.
- `ChatInterface` prefers `useSarvamSpeech` when the selected language isn't `en`; falls back to existing `useSpeechRecognition` (Web Speech) for `en`.

## Phase 5 — Automatic language detection with confirmation

When STT returns a `detectedLanguage` that differs from the active language:
- Render a confirmation toast: *"Detected Hindi (हिन्दी) — switch?"* with **Switch** / **Keep English** actions.
- On **Switch**: call `handleLanguageChange(detected)` (persists to profile, restarts STT, swaps TTS).
- On **Keep**: do nothing; remember the dismissal for the current session so it doesn't re-prompt every turn.

## Phase 6 — Graceful no-voice fallback UX

Today the failure path is a silent `console.error`. Replace with:
- `useTextToSpeech` exposes `error` already — surface it via a `sonner` toast in `ChatInterface` whenever it changes: *"Voice playback isn't available for {language}. Showing text only."*
- Disable the TTS toggle (with a tooltip) when both the Web Speech voice list and the Sarvam edge function are unavailable for the selected language.
- Same treatment for mic: if neither Web Speech nor Sarvam STT is reachable, disable the mic button and show *"Voice input isn't available for {language} in this browser."*

## Phase 7 — Language picker visibility fix

User reports only some languages show. Likely causes: viewport-clipped popover, missing `overflow-y-auto` on small screens, or z-index stacking under header. Fix:
- Ensure dropdown panel is fully scrollable with `max-h-[60vh] sm:max-h-80` (already present — verify it actually scrolls past `mai`/`sat`/`brx` on the user's 935×769 viewport).
- Add a sticky search input at the top of the dropdown when language count > 10 for faster selection.

## Phase 8 — End-to-end browser smoke test

Use the in-sandbox `browser--*` tools to:
1. Navigate to `/auth`, sign in (Google flow can't run headless; instead seed a test session via `supabase.auth.signInWithPassword` against a seeded test user, or skip auth and test as anonymous fallback).
2. Open language picker, select Telugu.
3. Type a complex query, send via `Ctrl+Enter`.
4. Verify the request payload includes `language: "te"`.
5. Enable TTS, verify either a Web Speech utterance or a Sarvam audio response plays (or the fallback toast appears).
6. Reload, confirm language is still Telugu.

Run via `code--exec` of a Playwright-like script using the `browser--act` tool sequence, capture screenshots into `/mnt/documents/e2e/` for review.

## Phase 9 — Prior-fixes verification report

Re-read `docs/ROADMAP.md`, run `bunx vitest run`, and produce a short table:
| Issue | Status | Evidence |
| ----- | ------ | -------- |
| White-screen on /chat | ✅ | RootErrorBoundary mounted |
| Google profile name missing | ⚠️ / ✅ | depends on `ensure_profile_and_role` audit |
| Sidebar lag from stream saves | ✅ | `saveConversation(c, notify=false)` |
| Sarvam mic + language | ✅ (after this plan) | edge functions deployed |
| Keyboard shortcuts | ✅ | `useChatShortcuts` |
| Mobile swipe sidebar | ✅ | `useSwipeGesture` |

## Technical details

- **Secrets needed**: `SARVAM_API_KEY` (will prompt via `secrets--add_secret`).
- **Edge functions**: both deployed with `verify_jwt = true` and per-user rate-limiting via `chat-rate-limit` pattern already in repo.
- **No DB migrations** required — `profiles.preferred_language` already accepts arbitrary `text`.
- **Touch points**: ~8 files (`src/hooks/useTextToSpeech.ts`, `src/hooks/useSarvamSpeech.ts` *new*, `src/components/chat/ChatInterface.tsx`, `src/components/chat/LanguageSelector.tsx`, `src/lib/aiService.ts`, `src/lib/profileStorage.ts`, `supabase/functions/sarvam-tts/index.ts` *new*, `supabase/functions/sarvam-stt/index.ts` *new*).
- **Tests**: extend `useTextToSpeech.test.ts` with a no-voice fallback case; add `useSarvamSpeech.test.ts`; add `LanguageSelector` scroll test.

## Out of scope

- Replacing FastAPI backend (`backend/`) — Sarvam access stays via Supabase edge proxies for now.
- Real Sarvam *streaming* WebSocket (their REST API is sufficient for sub-3s clips; streaming can be a follow-up).
- Translating UI chrome strings (i18n of menus/buttons) — only chat content language switches.
