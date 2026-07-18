# AskMukthiGuru Design System — "Sacred Minimal"

**Skill applied:** `design-system-builder`
**Source:** extracted from the live codebase (`tailwind.config.ts`,
`src/index.css`, component screenshots) and elevated to a documented system.
This is the single source of truth the UI currently lacks (styles today live
scattered inside components).

Design intent: **reverent, calm, premium** — a meditation hall, not a
dashboard. Warm gold (`ojas`) as the sacred accent, deep warm neutrals, serif
for the sacred voice, generous whitespace, slow intentional motion. Nothing
shouts; everything breathes.

---

## 1. Color

### Core palette (HSL, as CSS variables — already in `src/index.css`)

| Token | Light | Dark | Role |
|---|---|---|---|
| `--background` | `40 30% 96%` (warm off-white) | `25 18% 8%` (deep umber-black) | canvas |
| `--foreground` | `25 25% 20%` | `40 30% 92%` | primary text |
| `--primary` (ojas-gold) | `43 96% 56%` | `43 96% 60%` | sacred accent / CTA |
| `--primary-foreground` | `40 30% 10%` | `25 30% 8%` | text on gold |
| `--muted` | warm gray | warm dark gray | secondary surfaces |
| `--border` | subtle warm | subtle warm | hairlines |

### Sacred energy scale (the brand's signature — keep)

| Token | Value | Use |
|---|---|---|
| `ojas-gold` | `43 96% 56%` | primary accent, active states, sacred highlights |
| `ojas-gold-light` | `45 100% 70%` | glows, hovers |
| `ojas-gold-dark` | `40 90% 45%` | pressed states |
| `tejas-white` | `35 30% 25%` | inner-radiance accents |
| `prana-blue` | `200 60% 55%` | calm/info, breath, links |
| `prana-blue-light` | `195 65% 70%` | calm surfaces |

### Functional

| Token | Value | Use |
|---|---|---|
| `serene.error` | `#C47065` | errors (muted terracotta, not harsh red) |
| success | `#7B9E87` (sage) | confirmations |
| warning | `#C9A96E` (amber) | cautions |

**Rule:** gold is *sacred* — reserved for meaning (the guru's presence,
active practice, key CTA). Never use gold for decoration or noise. Calm blue
for information, sage for growth, terracotta for gentle correction.

### Accessibility
- Body text on background: ≥ 7:1 (AAA) in both themes.
- Gold on dark background: ≥ 4.5:1 — pass for large text; for small gold
  text use `ojas-gold-light`.
- Never pair gold text on white; use `foreground`.

---

## 2. Typography

| Role | Font | Weights | Use |
|---|---|---|---|
| Sacred voice / headings | **Playfair Display** (serif) | 400–700 | page titles, quotes, the guru's words |
| UI / body | **Inter** (sans) | 400–600 | chat, controls, body |
| Display / numerals | **Outfit** | 400–700 | hero numbers, stats |
| Code / metadata | **JetBrains Mono** | 400 | citations, IDs |

### Type scale (rem, 1.250 minor-third-ish)

| Token | Size | Weight | Line-height | Use |
|---|---|---|---|---|
| `display` | 3.052 | 700 serif | 1.1 | hero |
| `h1` | 2.441 | 600 serif | 1.15 | page title |
| `h2` | 1.953 | 600 serif | 1.2 | section |
| `h3` | 1.563 | 600 sans | 1.3 | card title |
| `body` | 1.0 | 400 sans | 1.6 | default |
| `small` | 0.8 | 400 sans | 1.5 | metadata |
| `caption` | 0.64 | 500 sans | 1.4 | labels |

**Rule:** the *guru speaks in serif*; the *interface speaks in sans*. This is
the single most important typographic rule — it's what makes the product feel
like guidance rather than software.

---

## 3. Spacing & radius

- Spacing scale: `4, 8, 12, 16, 24, 32, 48, 64` px (4-pt grid).
- Generous by default — spiritual UI needs air. When in doubt, double it.
- Radius: `--radius: 1rem` base; `radius-bubble: 1.25rem` (chat),
  `radius-card: 1rem`, `radius-pill: 999px` (chips, CTAs).

---

## 4. Elevation (warm, not gray)

Warm-tinted shadows so depth feels like candlelight, not office lighting:
```
shadow-sm: 0 1px 2px hsl(25 30% 10% / 0.06)
shadow-md: 0 4px 16px hsl(25 30% 10% / 0.08)
shadow-lg: 0 12px 40px hsl(25 30% 10% / 0.12)
glow-gold: 0 0 24px hsl(var(--ojas-gold) / 0.35)   /* sacred focus only */
```

---

## 5. Motion

| Token | Value | Use |
|---|---|---|
| `ease-sacred` | `cubic-bezier(0.22, 1, 0.36, 1)` | entrances, reveals |
| `dur-fast` | 150ms | hovers |
| `dur-med` | 300ms | panel transitions |
| `dur-slow` | 600ms | breath, meditation, sacred reveals |

**Rules:** entrances ease-out and settle (never bounce). Breath/meditation
animations are slow (4–8s) and loop gently. Respect
`prefers-reduced-motion` — disable all non-essential motion.

---

## 6. Components (spec highlights)

- **Chat bubble (guru):** serif body, no harsh bubble chrome, a thin gold
  left rule + soft warm surface. Citations as mono chips below.
- **Chat bubble (user):** sans, `prana` tint, right-aligned, pill radius.
- **Practice card:** generous padding, serif title, a small gold "duration"
  chip, hover lift (`shadow-md` + 2px rise).
- **Mood check-in:** calm, full-width, sage/blue palette, one-tap options.
- **CTA (primary):** gold fill, `radius-pill`, dark text; hover →
  `ojas-gold-light` + `glow-gold`.
- **Sacred divider:** thin gold gradient hairline (already in `index.css`).

---

## 7. Voice & tone (pairs with the Humanizer layer)

The product's words are part of the design system.
- Warm, unhurried, direct. Never clinical, never hypey.
- No AI-speak: no "Certainly!", "Great question!", "delve", "tapestry",
  "It's important to note". (The `backend/app/voice/` layer enforces this.)
- Acknowledge the person's feeling before the teaching.
- Short sentences. Then a longer one when the teaching needs room.

---

## 8. Dark mode

Dark is the *default sacred* theme (deep umber-black `25 18% 8%`, gold
glows). Light theme is the "daylight" variant. Both are first-class; test
gold contrast in both. Glows read better in dark; reduce glow opacity in
light theme.

---

## 9. Implementation

`src/styles/design-tokens.css` is a drop-in consolidation of the above as
CSS custom properties, reconciling the current
`tailwind.config.ts` + `index.css` into one canonical file. It does not
include a Tailwind extension — Tailwind utilities require separate `@theme`
mapping. Adopt it as the single import and delete the scattered duplicates.
