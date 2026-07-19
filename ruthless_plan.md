# Ruthless Plan — Digital Ashram × Current Stack

Source: user-uploaded `README.md`, `audit.md`, `design-system.md`, `architecture.md`,
`ai-strategy.md`, `tech-stack.md`, `trust-safety.md`, `roadmap.md`.
Direction chosen (this turn): **adapt to current Vite+React+Supabase stack** — cherry-pick
wins from the plan without a Next.js/Pinecone/Clerk migration. The AI persona, RAG
pipeline, safety copy, and IA already live in `backend/` + `src/` and must not regress.

## 1. Audit vs shipped state

| Plan item | Shipped? | Notes |
|---|---|---|
| Palette: sacred-sand / saffron-gold / deep-earth / lotus-rose | Partial | Current "Golden Hour" (`--ojas-gold`, warm sand bg) is close in spirit; needs a `--sacred-sand`/`--saffron-gold`/`--deep-earth` alias set + wider use of warm serifs. |
| Typography: Cormorant Garamond + Inter | **Done this turn** | Playfair Display swapped for Cormorant Garamond in `index.html` + `tailwind.config.ts`. Hero H1 now `font-sacred` with lighter weight, tighter leading. |
| Hero: full-viewport, sacred tone, pulse CTA, mandala corner | Partial | Full-dvh hero exists with particles + gradient; missing mandala-corner motif + "No account needed. Your peace is private." microcopy. |
| Section: State Check-In (interactive mood → route to chat) | **Missing** | Highest-impact net-new landing feature per the plan. |
| Section: The Masters / social proof stats (30M, TED, bestseller) | Partial | `MeetTheGurusSection` exists — needs the four hard-stats row. |
| Section: How It Guides You (3-step journey) | Present | `HowItWorksSection`. Copy audit pending. |
| Section: Sample Wisdom carousel | Missing | |
| Section: Trust & Safety pillars (dark section) | Partial | `SafetyDisclaimer` exists; no dedicated dark pillar section. |
| /chat immersive interface | Present | `ChatInterface` already AI-Elements-adjacent, Preethaji-voice audio just wired. |
| /wisdom library | Missing | Would replace "Favorites" concept; deferred. |
| /soul-sync meditation portal | Present as `/practices` + `SereneMindProvider` | Naming differs; keep current route. |
| /retreats page | Missing | Deferred — needs Ekam event data source. |
| AI persona (Mukthi Guru voice, forbidden patterns, attribution rules) | Backend-shipped | Enforced in `backend/rag/prompts.py` + OKF doctrine. |
| Guardian modal / crisis disclaimer / India helplines | Shipped | `SafetyDisclaimer`, distress detector, `SereneMindModal`. |
| Cormorant heading for chat bubbles / editorial gravitas | Missing | Optional polish — assistant text stays sans (readability). Reserved for section headings and pull-quotes. |
| Ambient breathing motion on landing background | Partial | `FloatingParticles` + gradient wash present. No slow-breath scale on the hero background image. |
| Cookie / consent banner | Shipped | `CookieConsentBanner`. |
| Sitemap + JSON-LD (Org/WebSite/WebApp) + FAQ schema on guides | Shipped | Prior SEO passes. |
| Multi-language (English, Hindi, Telugu, Malayalam) | Shipped | i18n. |
| Serene Mind meditation w/ Preethaji audio + step sync | **Shipped** | 6 steps point at one continuous track from YouTube extraction, TTS fallback via `audioFailed` flag guards missing/broken clips. |
| PWA icon-192 real asset | Shipped | Previous turn. |
| Publish Track 2FA + admin audit log page + demo videos + WhatsApp handoff | Not shipped | Explicitly deferred earlier by user; still open. |
| Full a11y + multi-viewport screenshot sweep via Playwright | Not shipped | Deferred. |

## 2. Non-negotiables (per uploaded plan)

- **Never** claim to be Sri Preethaji/Krishnaji or to transmit Deeksha. Enforced in the
  backend prompt; must remain in every AI-persona test.
- **Never** use `#000000` or `#FFFFFF` — use `--deep-earth` / `--sacred-sand` equivalents.
  Sweep pending for hard-coded `text-black` / `bg-white`.
- **Never** move to a Next.js / Pinecone / Clerk / Plausible stack — user answered
  "adapt to current stack" this turn.

## 3. Ruthless slice order (execution queue)

Each slice sized to one turn, verifiable via preview + build.

1. **[shipped this turn]** Typography port + hero H1 restyle + toast type fix.
2. **State Check-In section** — 4-mood chip row above the fold; click → routes to
   `/chat?intent=<mood>` and pre-seeds the composer. Highest audience-facing lift per
   audit §1 and architecture §2.2.
3. **Palette alias layer** — add `--sacred-sand / --deep-earth / --saffron-gold /
   --lotus-rose / --pale-gold` HSL tokens on top of existing Golden Hour tokens; do NOT
   rename existing tokens. Then adopt `--sacred-sand` on `<body>` and `--saffron-gold`
   on primary CTAs. Zero regression risk.
4. **Mandala corner + microcopy** — SVG mandala at 6% opacity top-right of hero;
   "No account needed. Your peace is private." microcopy under CTA.
5. **The Masters stat row** — 4 stats (30M lives · #1 bestseller · TED speaker ·
   800K Ekam attendees) between hero and How It Works.
6. **Sample Wisdom carousel** — 5 hand-curated attributed teachings from OKF doctrine.
7. **Trust & Safety pillar section** — dark band (`--deep-earth` bg) with 3 pillars:
   Sacred Privacy · Honest Attribution · Crisis Support. Links to /privacy, /terms,
   iCall/Vandrevala numbers already in `SafetyDisclaimer`.
8. **Ambient breath motion on hero image** — slow 8s scale 1.00 ↔ 1.03 with reduced-motion
   respect.
9. **Landing copy pass** — replace remaining generic microcopy with plan-approved phrasing
   from `architecture.md` §2 and `trust-safety.md` §2.
10. **Deferred bundle** (previously requested, still open):
    - Full user + admin demo videos on landing
    - 2FA for users
    - Admin audit log page
    - WhatsApp deep-link handoff flow
    - Playwright multi-viewport a11y sweep

## 4. Verifications kept green

- TTS fallback contract: `useMeditationAudio` sets `audioFailed` on `<audio> onerror`;
  `useMeditationTTS` speaks the instruction only when `audioFailed || !audioSrc`.
  Regression-guarded by `src/test/useMeditationTTS.test.ts`.
- Serene Mind: all six steps carry the same Preethaji URL so the single continuous
  track plays across step advances (`useMeditationAudio` "same src" short-circuit).
- No hard-coded Supabase URLs / project IDs in user-facing copy.
- Admin routes stay `noindex` via `usePageMeta({ noindex: true })`.

## 5. What the plan explicitly rejects (do not resurrect)

- Purple/indigo gradients on white (`audit.md` §🔴1).
- Slack-clone chat with avatars + sidebar (`audit.md` §🔴2).
- Generic Inter-for-everything typography (`audit.md` §🟡4).
- "As an AI language model…" refusals in the persona (`ai-strategy.md` §1).
- Storing chat conversations for model training (`trust-safety.md` §3).
