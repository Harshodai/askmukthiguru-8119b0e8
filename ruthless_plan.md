# Ruthless Plan — Uploaded .md Audit vs Shipped State

Source docs: `README.md`, `audit.md`, `design-system.md`, `architecture.md`,
`ai-strategy.md`, `tech-stack.md`, `trust-safety.md`, `roadmap.md` (all
user-uploaded on the "Digital Ashram" direction), plus the earlier internal
plan captured in `RUTHLESS_PLAN.md`.
Direction locked: **adapt to current Vite+React+Supabase stack** — no Next.js
/ Pinecone / Clerk migration.

Legend: ✅ shipped · 🟡 partial · ❌ not built · 🔒 deferred by user

---

## 1. Brand & Design System

| Item | Status | Notes |
|---|---|---|
| Cormorant Garamond + Inter typography | ✅ | Swapped from Playfair, hero H1 restyled. |
| Sacred-sand / saffron-gold / deep-earth / lotus-rose tokens | 🟡 | Current "Golden Hour" tokens (`--ojas-*`) are close in spirit; alias layer not added yet. |
| Full removal of `text-black` / `bg-white` / `#000` / `#FFF` | 🟡 | Recent surfaces migrated; codebase sweep still pending. |
| Ambient breath motion on hero background | 🟡 | Particles + gradient wash present; slow-breath scale not added. |
| Mandala corner motif on hero | ❌ | |
| "No account needed. Your peace is private." microcopy under hero CTA | ❌ | |

## 2. Landing Sections

| Section | Status | Notes |
|---|---|---|
| Hero (full-viewport, pulse CTA) | ✅ | |
| Meet the Masters | 🟡 | Section exists; 4-stat social-proof row (30M · #1 bestseller · TED · 800K Ekam) missing. |
| How It Guides You (3-step journey) | ✅ | `HowItWorksSection`. |
| State Check-In (mood chips → `/chat?intent=…`) | ❌ | Highest-impact plan feature not started. |
| Sample Wisdom carousel (5 attributed teachings) | ❌ | |
| Trust & Safety pillars (dark band) | 🟡 | `SafetyDisclaimer` exists; dedicated dark pillar section missing. |
| Cookie/consent banner | ✅ | |
| SEO: sitemap, JSON-LD, FAQ schema, canonicals | ✅ | Prior SEO passes. |

## 3. Chat / Guru Interface

| Item | Status | Notes |
|---|---|---|
| Immersive `/chat` (AI-Elements-style) | ✅ | |
| Thinking status pills w/ rotating labels | ✅ | `useThinkingStatus` wired into `ThinkingPills`. |
| Warm auto-retry error copy | ✅ | `chatErrorBus`. |
| Cold-start "Guru is waking up" banner | ✅ | `useBackendHealth`. |
| Exponential backoff (429/504) | ✅ | `fetchWithRetry`. |
| Voice input (STT) in composer | ✅ | `useVoiceInput` + `/api/speech/stt`. |
| TTS read-aloud of assistant messages | ✅ | Wired via `ChatMessage`. |
| Persona rules (no "as an AI", Deeksha guardrails) | ✅ | Enforced in `backend/rag/prompts.py`. |
| WhatsApp deep-link handoff | 🔒 | Deferred. |
| Slack-clone avatars/sidebar (rejected by audit) | ✅ removed | Sidebar slim, no per-message avatars. |

## 4. Serene Mind (Meditation)

| Item | Status | Notes |
|---|---|---|
| 6-step Preethaji-voiced protocol | ✅ | `meditationSteps.ts` — all steps point at one continuous track. |
| Merged audio+video player | ✅ | `SereneMindProvider` routes 'audio' → `GuidedMeditationFlow`. |
| Audio actually playing in preview | ✅ **fixed this turn** | Removed `crossOrigin='anonymous'` from `useMeditationAudio` — the Lovable asset CDN doesn't send CORS headers, so the flag was silently blocking every `<audio>` load. |
| Web Speech API TTS fallback when clip missing/broken | ✅ | `useMeditationTTS` gated on `audioFailed \|\| !audioSrc`. Regression test in `src/test/useMeditationTTS.test.ts`. |
| YouTube source link visible in player | ✅ **added this turn** | "Watch Sri Preethaji guide this practice on YouTube" under player controls in `GuidedMeditationFlow`. |
| Mute toggle | ✅ | |
| Resume-in-progress w/ 24 h TTL | ✅ | `serene_mind_resume_v1` localStorage key. |
| Reflection flow (mood → journal → gratitude) | ✅ | |

## 5. IA / Routes (from `architecture.md`)

| Route | Status |
|---|---|
| `/` landing | ✅ |
| `/chat` | ✅ |
| `/profile` | ✅ (redesigned) |
| `/practices` (== plan's `/soul-sync`) | ✅ Named differently on purpose. |
| `/wisdom` library | ❌ Deferred. |
| `/retreats` | ❌ Deferred — no Ekam event source. |
| `/about` | 🟡 Content lives in landing; no dedicated page. |
| `/privacy`, `/terms` | ✅ |
| Admin sub-app | ✅ `noindex`. |

## 6. Trust, Safety, Security

| Item | Status |
|---|---|
| Guardian modal / crisis disclaimer / India helplines | ✅ |
| Distress detector w/ compassionate teachings | ✅ |
| RLS on every public table + explicit GRANTs | ✅ |
| `has_role` SECURITY DEFINER pattern | ✅ |
| Password policy ≥12 | ✅ |
| SSRF-safe ingest (manual redirect + private-IP block) | ✅ |
| 2FA for users | 🔒 Deferred. |
| Admin audit log page | 🔒 Deferred. |

## 7. Ops / SEO / PWA

| Item | Status |
|---|---|
| `icon-192.png` / `icon-512.png` real PNGs | ✅ |
| Sitemap + robots + canonical | ✅ |
| Multi-language (en/hi/te/ml) | ✅ |
| Web push registration | ✅ |
| Lighthouse perf audit clean | 🟡 Retest after this turn. |

## 8. Rejected by plan — must not resurrect

- Purple/indigo gradients on white (`audit.md` §🔴1).
- Slack-clone chat with per-message avatars + persistent sidebar.
- Inter-for-everything default typography.
- "As an AI language model…" refusals.
- Storing chat conversations for model training.
- Claiming to be Sri Preethaji/Krishnaji or to transmit Deeksha.
- Using pure `#000000` / `#FFFFFF`.

## 9. Fixed this turn

1. **Serene Mind audio silence** — dropped `crossOrigin='anonymous'` in `useMeditationAudio.ts`. The asset CDN (`/__l5e/assets-v1/…`) returns MP3 without CORS headers; the anonymous flag was making every step hit `onerror` and go silent (TTS fallback only fires when the browser has already tried and failed a load — but on some browsers the failure isn't reported cleanly, so nothing played at all).
2. **Missing YouTube link** — added a "Watch Sri Preethaji guide this practice on YouTube" link under the player controls, pointing at the canonical `igSp4H0OWLE` recording (same source the audio was extracted from).
3. **Verified STT + TTS wiring** — `useVoiceInput` still hitting `/api/speech/stt`; `useMeditationTTS` still guarded by `audioFailed || !audioSrc`. No regression.

## 10. Next ruthless slice (one turn each)

1. **State Check-In section** on landing — 4 mood chips above the fold, deep-linking `/chat?intent=<mood>` and pre-seeding the composer.
2. **Palette alias layer** — add `--sacred-sand`, `--deep-earth`, `--saffron-gold`, `--lotus-rose`, `--pale-gold` HSL tokens on top of existing Golden Hour tokens without renaming anything.
3. **Masters social-proof stat row** — 4 stats between hero and How It Works.
4. **Sample Wisdom carousel** — 5 hand-curated OKF-attributed teachings.
5. **Trust & Safety pillar band** — dark section with 3 pillars linking `/privacy`, `/terms`, and crisis numbers.
6. **Mandala corner + hero microcopy**.
7. **Ambient hero breath motion** (respect `prefers-reduced-motion`).
8. Deferred bundle (still 🔒): 2FA, admin audit log, WhatsApp handoff, product-demo videos, Playwright a11y sweep.
