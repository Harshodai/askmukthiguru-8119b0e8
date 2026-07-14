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
- **Mega-file component splits** (ChatMessage 1283 LoC, ChatInterface 1991 LoC, ProfilePage ~1089, SereneMindModal 981): proposed 3 times; attempted only surgically because a full split without regenerating snapshot tests risks breaking the chat state machine (streaming checkpoints in `sessionStorage`, PrePracticeGate, tour triggers, multi-device continue). Deferred behind visible polish.
- **Composer full rebuild**: current composer already uses AI Elements primitives correctly, so a rebuild would be churn. Applied token/border polish instead.
- **Sidebar slim to 260 px with grouped Today/Yesterday/Last 7d**: `conversationGrouping.ts` already groups; visual grouping in the sidebar is not yet wired.
- **Full file-level merge of `SereneMindModal` and `GuidedMeditationFlow`**: deliberately deferred. The behavioral merge (audio + provider routing) shipped instead — Serene Mind's audio experience now goes through `GuidedMeditationFlow`, so users see one player, but the two files still exist. Deleting `SereneMindModal` outright would break the YouTube-video tab, the breath-technique picker, and the `isGated` chat-flow gate that PrePracticeGate depends on. Full deletion is safe once the video tab is either dropped or ported into `GuidedMeditationFlow`.
- **Runtime TTS for meditation narration**: rejected by the user in favor of pre-recorded MP3s. The Web Speech API path is not wired up (would sound robotic).
- **Product demo videos**: not yet started; direction is now locked so it becomes the next-turn task.

## 5. Next steps (in order)

### A. Finalize the merged meditation player (this session left it 80% done)
1. Author + drop the 6 MP3 files listed in `public/audio/meditation/README.md`. Once present, they load automatically — no code change needed.
2. Add a **mute** button to `GuidedMeditationFlow` transport controls and pass `muted` as the 4th arg to `useMeditationAudio`.
3. Port the `SereneMindModal` **video** tab (YouTube embed) into `GuidedMeditationFlow` as an optional `sourceVideoId` prop, then delete `SereneMindModal` entirely. This is the file-level merge.
4. Same treatment for other meditations reachable from `PracticesPage` — extend `breathTechniques.ts` with `audioSrc` per phase (inhale/hold/exhale bell cues) or per technique (full guided track). Wire via a small variant of `useMeditationAudio` that keys on breath-phase changes instead of step index.
5. Regression test in `src/test/`: fake `HTMLMediaElement.play`, drive `GuidedMeditationFlow` through 3 steps, assert `audio.src` swaps at the boundary seconds and `pause()` is called on unmount.

### B. Product demo videos — Remotion, 30 s teaser + 90 s deep-dive per role (User + Admin) = 4 MP4s

**Setup (once):**
1. Scaffold `remotion/` per the video-creator skill: `mkdir remotion && cd remotion && bun init -y && bun install remotion @remotion/cli @remotion/renderer @remotion/bundler @remotion/transitions @remotion/google-fonts react react-dom typescript @types/react @remotion/compositor-linux-x64-musl`.
2. Fix the compositor gnu → musl overwrite + ffmpeg/ffprobe symlink dance (see video-creator skill setup section).
3. Capture live app screenshots via Playwright: `/chat` (empty + mid-conversation + streaming + wisdom card), `/profile` (hero + insights tiles), `/practices`, `/practices/serene-mind` (flame + breath ring), `/admin/overview`, `/admin/queries`, `/admin/ingestion`, `/admin/daily-teaching`. Store under `remotion/public/screens/`.
4. Generate voiceover with ElevenLabs at build time from scripts in `remotion/scripts/`. Cache MP3 in `remotion/public/vo/`.

**Compositions:**
- `user-teaser` (30 s / 900 frames @ 30 fps): "A guru, always available." → chat scene → Serene Mind flame → beautiful state → logo.
- `user-deepdive` (90 s / 2700 frames): open app → ask a question → streaming answer with citations → Serene Mind guided practice with breath ring → insights tab shows streak → wisdom card share.
- `admin-teaser` (30 s): "Doctrine. Curated. Trusted." → dashboard KPIs → ingest a YouTube URL → OKF entry auto-drafted → approve → live in chat.
- `admin-deepdive` (90 s): login → overview → ingest → moderation queue → OKF review → daily teaching publish → telemetry → publish.

**Motion system (locked):** Golden Hour palette (from `index.css` tokens), Fraunces display + Inter body, 300 ms spring entrances (`damping: 20, stiffness: 200`), 400 ms slide-wipe transitions between scenes, flame texture as a shared motif for the User videos, hairline underline as the shared motif for Admin.

**Render + publish:**
- `cd remotion && node scripts/render-remotion.mjs` for each composition → `/mnt/documents/*.mp4`.
- Upload with `lovable-assets create --file` → asset pointers under `src/assets/demos/`.
- Landing hero embeds `user-teaser.mp4` autoplay-muted; `DemoModal.tsx` gets a role toggle (User / Admin) that swaps between the two deep-dives.
- New `/demo?role=admin` route for conclave sharing (deep-dive plays inline, fullscreen button visible).

### C. After demos ship
- File-level split of the mega-components with proper snapshot regen (deferred from prior sessions).
- Sidebar visual grouping wiring.
- Multi-language narration variants (Hindi, Telugu, Malayalam) — same MP3 slot, prefixed with locale.

