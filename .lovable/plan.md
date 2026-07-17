# Ruthless UI/UX Audit + Fix Pass

Three tracks. Track A is a systematic visual audit + fix sweep. Track B rebuilds notifications. Track C extracts the Serene Mind YouTube audio and wires it into the step player. All three ship in the same pass.

---

## Track A — Full-app UI/UX audit

### Routes covered

Landing (`/`), Auth (`/auth`), Chat (`/chat`), Practices (`/practices`, `/practices/:id`), Profile (`/profile`), Knowledge Graph, Spirit Guides, Reset Password, Privacy, Terms, NotFound, and the Admin sub-app (`/admin/*`).

### Method (ruthless, not vibes)

1. **Screenshot matrix via Playwright** — every route captured at 3 viewports × 2 themes = 6 shots per route (mobile 390×844, tablet 820×1180, desktop 1440×900; light + dark). Saved under `/tmp/audit/<route>/<device>-<theme>.png` and reviewed with `code--view`. For interactive states (open modal, open sidebar, toast visible, streaming message, meditation mid-flow, error state) capture extra frames.
2. **Automated checks in the same pass**: axe-core injected via Playwright for a11y violations, computed contrast on text/foreground pairs, console-error capture, layout-shift observation on route enter, focus-ring visibility on tab traversal, tap-target size (44×44) on mobile.
3. **Findings log** written to `docs/UI_AUDIT_2026-07-17.md` — one row per issue: route, device, theme, severity (P0 broken / P1 polish / P2 nit), screenshot path, proposed fix.
4. **Fix in severity order**, re-screenshot the same frame after the fix, diff mentally, move on. P2 nits only fixed after P0/P1 are clean.

### Known likely findings (pre-loaded, will be verified in step 1)

- Toasts (rebuilt in Track B).
- `h-screen` usages that clip on iOS Safari — swap to `h-dvh`.
- Icon-only buttons missing `aria-label` (shadcn `size="icon"` variants).
- Focus-visible rings missing or invisible on dark theme buttons/inputs.
- Chat composer submit crowding the textarea edge on narrow screens.
- Landing hero + Practices cards not respecting reduced-motion.
- Auth page form spacing on mobile.
- Admin tables overflow horizontally on tablet.
- Meditation flame animation using `backdropFilter` (expensive on low-end mobile).
- Any `text-gray-*` / `bg-white` hardcoded classes that break dark mode → swap to semantic tokens.

### Constraints

- Never hardcode colors — only semantic tokens from `index.css`.
- Never rebuild Radix keyboard/focus behavior by hand.
- Motion respects `prefers-reduced-motion`.
- No changes to business logic, RAG pipeline, or backend from this track — presentation only.

---

## Track B — Notification / toast redesign (Warm Sacred)

Rebuild the toast surface to match brand — the current "Reset Complete" style is the reference of what NOT to ship.

### Design spec

- **Palette (from your pick)**: amber `#F59E0B`, ink `#0F172A`, gold `#FBBF24`, cream `#FEF3C7`. Mapped to semantic tokens `--toast-bg`, `--toast-fg`, `--toast-accent`, `--toast-glow`. Light + dark variants both defined.
- **Structure**: 56px-min height, 16px radius, 1px hairline border in `--toast-accent/20`, layered gold glow shadow (`0 8px 32px hsl(var(--toast-glow)/0.25)`), backdrop `bg-toast-bg/95` with subtle noise texture.
- **Iconography**: small flame glyph (reusing the Serene Mind flame SVG) leading the title. Severity encoded by the flame's tint, not by an alarming red/green — success = gold, info = warm cream, warning = amber, error = deep amber with subtle pulse (not a jarring red).
- **Typography**: title in the display serif at 15px/1.2 with `-0.01em` tracking; description in body sans at 13px/1.5 in `--toast-fg/75`.
- **Motion**: spring-in from bottom-right on desktop, from top on mobile; damping 22, stiffness 260. Exit is a soft fade + 4px drift, 180ms. Respects reduced-motion.
- **Placement**: bottom-right desktop, top-center mobile, safe-area-inset aware.
- **Action affordance**: optional single ghost button with underline-on-hover, no filled CTAs inside toasts.
- **Stacking**: max 3 visible, older ones collapse into a compact stack with a count chip.

### Implementation

- Migrate the app onto `sonner` as the single toast surface (already installed). Delete the legacy `useToast` + `<Toaster />` wiring once every callsite is moved. Callsites will be found with `rg "useToast\|toast\(" src` and rewritten to `import { toast } from "sonner"`.
- Custom Sonner theme lives in `src/components/ui/sonner.tsx` with the tokens above.
- Add a tiny helper `src/lib/notify.ts` exposing `notify.success`, `.info`, `.warning`, `.error`, `.promise` so callsites read as intent, not styling.
- Snapshot test 4 states (success/info/warning/error) via Playwright in light + dark.

---

## Track C — Serene Mind audio: extract + merge with steps

Goal: the guided meditation player plays Sri Preethaji's actual voice from the Serene Mind YouTube video, synced to the on-screen steps + flame + breath ring. YouTube tab in `SereneMindModal` still exists for users who want the full video; the audio track is what merges into the step player.

### Steps

1. **Locate the source URL** — read `src/components/chat/SereneMindModal.tsx` and `src/components/meditation/*` to find the YouTube ID currently embedded. If more than one candidate exists, list them and pick the canonical Serene Mind one (the ~3-minute Preethaji guided practice).
2. **Extract audio in the sandbox**:
  ```
   yt-dlp -x --audio-format mp3 --audio-quality 0 -o /tmp/serene-mind-full.mp3 "<YouTube URL>"
  ```
   (yt-dlp is available via `nix run nixpkgs#yt-dlp`; ffmpeg is preinstalled.)
3. **Detect step boundaries** in the extracted audio. Two-stage approach:
  - First pass: `ffmpeg silencedetect` (`-af silencedetect=noise=-30dB:d=0.6`) to find natural pauses between the 6 movements (arrive → observe-body → observe-breath → observe-sound → compassion → complete).
  - Second pass: cross-check against the durations already declared in `meditationSteps.ts` (20/45/60/45/45/10s = 225s). If the detected boundaries land within ±10% of those durations, accept them. Otherwise, use the declared durations as-is and let the audio play through — the flame + text carry the sync visually.
4. **Slice** with `ffmpeg -ss ... -to ... -c copy` into six files: `arrive.mp3`, `observe-body.mp3`, `observe-breath.mp3`, `observe-sound.mp3`, `compassion.mp3`, `complete.mp3`. Normalize each to -16 LUFS with `ffmpeg -af loudnorm=I=-16:LRA=11:TP=-1.5` for consistent playback level.
5. **Upload to CDN** using `lovable-assets create --file <file> --filename <name>` for each of the six clips. Write the six `.asset.json` pointers to `src/assets/meditation/`. This avoids bloating the repo with ~3MB of audio.
6. **Wire into steps** — update `src/components/meditation/meditationSteps.ts` to set `audioSrc` on each step from the imported `.asset.json` URL. `useMeditationAudio` already handles fade-in / fade-out / preload of the next clip, so no hook changes are needed. Verify by running the meditation flow end-to-end via Playwright and checking that (a) audio starts on step change, (b) it fades cleanly, (c) mute button silences it, (d) if audio fails, TTS fallback still fires.
7. **Regenerate the last step's duration** if step 6 boundary detection reveals the "complete" narration runs longer than 10s — bump it and update `TOTAL_DURATION_SECONDS` derivation (already automatic).

### If extraction fails or the video is unavailable

Fall back to keeping the current Web Speech TTS path and leave `audioSrc` unset. Do not ship silent steps.

---

## Deliverables

- `docs/UI_AUDIT_2026-07-17.md` — findings + before/after screenshot paths.
- Updated components across the routes listed in Track A (presentation only).
- New `src/lib/notify.ts` + reworked `src/components/ui/sonner.tsx`; legacy `use-toast` callsites migrated; legacy `<Toaster />` removed if fully unused.
- Six `.asset.json` pointers under `src/assets/meditation/` and `meditationSteps.ts` wired to them.
- Playwright screenshots in `/tmp/audit/` for spot-check.

## Out of scope (explicit)

- Backend/RAG changes, admin data model changes, auth flow changes, new features. Presentation + notifications + meditation audio only.
- The full end-to-end product demo videos from earlier turns — deferred; this pass is about polish, not marketing assets.
- ElevenLabs voice cloning — the user chose YouTube extraction instead.
- Give me .md files on what needs to be done as well and also atlast add whats missing in this before giving this to users

## Confirmation I need before I switch to build mode

- The canonical Serene Mind YouTube URL, if it's not already the one currently embedded in `SereneMindModal`. If you say "use whatever is in the modal", I'll pick that one and proceed.