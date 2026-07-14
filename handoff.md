# Handoff — AskMukthiGuru UI + Meditation Redesign

## 1. Goal
Bring `/profile`, the chat surface, and the meditation players to ChatGPT/Claude-caliber polish across web, mobile web, and Capacitor iOS/Android. Keep the Golden Hour aesthetic, HSL semantic tokens, and every existing feature. Feel native on-device.

Concrete deliverables in flight:
- **One unified meditation player** with narrated audio synced to step transitions + breath ring. (Direction locked: pre-recorded MP3s, flame + breath ring kept.)
- **Product demo videos** — two per role (User + Admin), 30 s teaser + 90 s deep-dive each = 4 MP4s total. Direction locked: **Remotion motion graphics** with composited app screenshots.

### Turn-3 additions (meditation audio sync + player merge)
- **`useMeditationAudio` hook** (`src/components/meditation/useMeditationAudio.ts`) — single `<audio>` element, cross-fades on step change, preloads the next step, silent fallback when files are missing, respects `isPlaying` + `muted`.
- **`MeditationStep` extended** with `audioSrc`. Every step in `GUIDED_STEPS` now carries `/audio/meditation/<id>.mp3`.
- **`GuidedMeditationFlow`** now consumes `useMeditationAudio(steps, currentStepIndex, isPlaying && !isComplete)` — one line integration, zero behavior regression when audio files are absent.
- **Real merge**: `SereneMindProvider` now routes the `'audio'` tab **and** all custom-teaching flows through `GuidedMeditationFlow`. `SereneMindModal` only owns the `'video'` (YouTube) tab now. From the user's perspective there is effectively one player.
- **`public/audio/meditation/README.md`** documents the 6 required MP3 filenames + duration targets + voice direction.

## 2. Current state of code
### Shipped this session set
- **Design tokens (`src/index.css`)**: `--chat-surface`, `--chat-user-bubble`, `--chat-user-foreground`, `--assistant-foreground`, `--hairline`, `--divider`, `--overlay-scrim`, `--radius-bubble/card/pill`, motion tokens (`--dur-*`, `--ease-standard`), light + dark parity.
- **Native-feel utilities**: `.safe-top`, `.safe-bottom`, `.safe-x`, `.momentum-scroll`, `.no-tap-highlight`, `.border-hairline`, `.bg-chat-user`.
- **ChatMessage**: warmer pill user bubbles via `bg-chat-user`, subtler assistant avatar, wider max-widths, 1.55 line-height. Behavior unchanged.
- **ChatInterface**: momentum-scroll + safe-x on scroll container, `space-y-5/6` between messages.
- **ChatHeader + DesktopSidebar**: `border-hairline` dividers, softer New Conversation chip, `safe-top` on both.
- **ChatComposer**: `--radius-card` corners, hairline border when idle, subtler focus shadow.
- **ProfilePage**: new flat hero (64/80px avatar, serif name, email, streak chip), scrollable pill tab rail on mobile / 7-col grid on desktop, `safe-x` wrapper.
- **ProfileStatTiles** (new, `src/components/profile/ProfileStatTiles.tsx`): flat left-aligned tiles with tabular serif numbers + 7-day SVG sparkline of practice minutes (no chart lib). Wired into Insights tab.
- **Security migration** from earlier turn: `supabase/migrations/20260714080216_b87a05f0-8df7-4370-82ad-1833dd26e6aa.sql` fixed the 4 named findings.

### Files touched
- `src/index.css`
- `src/components/chat/ChatMessage.tsx`
- `src/components/chat/ChatInterface.tsx`
- `src/components/chat/ChatHeader.tsx`
- `src/components/chat/ChatComposer.tsx`
- `src/components/chat/DesktopSidebar.tsx`
- `src/pages/ProfilePage.tsx`
- `src/components/profile/ProfileStatTiles.tsx` (new)
- `handoff.md`, `.lovable/plan.md`

### Known big files still worth splitting (deferred, not blocking)
- `ChatInterface.tsx` — 1991 LoC
- `ChatMessage.tsx` — 1283 LoC
- `ProfilePage.tsx` — ~1089 LoC
- `SereneMindModal.tsx` — 981 LoC
- `GuidedMeditationFlow.tsx` — 567 LoC

## 3. Files actively targeted next
For the meditation-player merge + audio sync:
- `src/components/chat/SereneMindModal.tsx` (keeps live, becomes the shell)
- `src/components/meditation/GuidedMeditationFlow.tsx` (fold into shell as a mode)
- `src/components/meditation/meditationSteps.ts` (add per-step `audioUrl`, `videoUrl`, `durationSec`)
- `src/components/meditation/breathTechniques.ts` (add optional narration cues)
- New: `src/components/meditation/MeditationPlayer.tsx` — unified player (audio + video optional + timeline-driven step advance)
- New: `src/components/meditation/useMeditationTimeline.ts` — single frame-driver hook, replaces the two ad-hoc timers
- `src/components/common/SereneMindProvider.tsx` (route the merged player)
- `src/pages/guides/SereneMindPracticePage.tsx` and other `/guides/*` pages that mount the flow — swap to new component

For the product demo videos (once scope is confirmed):
- New: `remotion/` project under repo root, per the video-creator skill
- `src/components/landing/DemoModal.tsx` — replace/point to the rendered MP4(s)
- `public/videos/` or Lovable assets — final MP4 hosting

## 4. What has been tried and failed / deferred
- **Mega-file component splits**: proposed 3 times across sessions (ChatMessage/ChatInterface/ProfilePage into small pieces). Attempted only surgically — tokens, hero, tiles — because a full split without regenerating snapshot tests risks breaking the chat state machine (streaming checkpoints in `sessionStorage`, PrePracticeGate, tour triggers, multi-device continue). Deferred behind visible polish.
- **Composer full rebuild** (single-row, morphing send/stop, controls inside field): current composer already uses AI Elements primitives correctly, so a rebuild would be churn. Applied token/border polish instead.
- **Sidebar slim to 260 px with grouped Today/Yesterday/Last 7d**: `conversationGrouping.ts` already groups; the visual grouping in the sidebar is not yet wired. Left for next session because the existing sidebar already reads acceptable after hairline pass.
- **Meditation audio narration**: never attempted this session. There is no TTS or pre-recorded audio pipeline for meditation steps today — `SereneMindModal` uses a JS timer + visual flame; `GuidedMeditationFlow` uses a JS timer + text. Merging them without an audio source would just be a rename.
- **Product demo videos**: not started — needs script, brand direction (voice, pace, target duration), and a decision between recorded screen capture vs. Remotion motion graphics vs. hybrid. See open questions below.

## 5. Next steps (in order)

### A. Unified meditation player (Serene Mind + Guided merged)
1. Extract a `MeditationStep` type with: `id`, `title`, `instruction`, `durationSec`, `audioUrl?`, `videoUrl?`, `breathPattern?`, `visual` (`flame` | `breath-ring` | `still` | `video`).
2. Build `useMeditationTimeline({ steps, onComplete })` — one RAF-based clock that owns `elapsedSec`, `stepIndex`, `paused`, exposes `seekTo`, `pause`, `resume`, `skip`. All step transitions derive from `elapsedSec` so audio, breath-ring, and text advance from the same source of truth.
3. Build `MeditationPlayer` — presentational: renders header (title + close), hero visual (flame/breath-ring/`<Video>`), step text with cross-fade on `stepIndex` change, breath-count / timer, transport controls (pause, skip, mute), progress bar. Consumes the timeline hook.
4. Wire audio: `<audio>` element bound to the active step's `audioUrl`; on step change, cross-fade audio via 200 ms `volume` ramp; keep a single element and swap `src` to avoid iOS autoplay stalls. Preload next step audio.
5. Wire optional video: `<video muted playsInline>` behind the flame; if `videoUrl` present, hide the flame. Same source-of-truth clock.
6. Replace `SereneMindModal`'s inner content with `MeditationPlayer` and pass the Serene Mind step set. Delete the timer/breath logic from the modal.
7. Replace `GuidedMeditationFlow`'s render with the same `MeditationPlayer` and pass the guided step set. Keep the outer route/page.
8. Provider (`SereneMindProvider`) becomes the single mount for the merged player, with a `mode: 'serene-mind' | 'guided' | <techniqueId>` prop deciding which step set loads.
9. Author or upload audio narration per step. Two options:
   - **Pre-recorded MP3** in `public/audio/meditation/<step>.mp3` (best quality, fixed voice).
   - **Runtime ElevenLabs TTS** via a Supabase Edge Function (dynamic, voice-consistent, but adds latency and cost). Recommend pre-recorded for launch, TTS for future personalization.
10. Update `meditationSteps.ts` and `breathTechniques.ts` with `audioUrl` + `durationSec` fields.
11. Regression tests: `SereneMindProvider.test`, `ChatMessage.test`, and a new `MeditationPlayer` unit test that fakes RAF and asserts step advance at boundary seconds.

### B. Product demo videos
1. Pick the production approach (see open questions).
2. If Remotion motion graphics: scaffold `remotion/` per the video-creator skill, script two ~45–60 s pieces (User: land → chat → serene mind → insights; Admin: login → dashboard → ingest → moderation → publish teaching), render to `/mnt/documents/`, then upload with `lovable-assets` and reference in `DemoModal.tsx` and landing hero.
3. If screen-recorded: script + record via Playwright screen capture in the sandbox, add voiceover via ElevenLabs, mux with ffmpeg.
4. Add an in-app "Watch demo" entry point on the landing page and a `/demo?role=admin` deep link for conclaves.

## Open questions blocking step-B (please confirm)
1. **Voice for narration**: use one of the existing Mayura voices (Deepika / Ananya / Arvind), pre-record with a professional, or generate via ElevenLabs at build time?
2. **Demo video style**: (a) real screen recording of the live app with voiceover, (b) Remotion motion graphics with app screens composited in, or (c) hybrid — recorded flows with animated captions/highlights?
3. **Demo duration**: 30 s teaser for landing hero + 90 s deep-dive per role, or one 60 s per role?
4. **Meditation visuals**: keep the current flame + breath-ring, or introduce short ambient background videos (dawn sky, still water, candle) generated with `videogen--generate_video` behind the flame?
