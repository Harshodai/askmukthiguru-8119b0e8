# AskMukthiGuru Design System

## 1. Visual Theme & Atmosphere

AskMukthiGuru's design is warm and spiritual — a sanctuary space that evokes peace, calm, and the "Beautiful State" central to Sri Preethaji & Sri Krishnaji's teachings. The interface pairs a saffron-gold primary (`--ojas-gold: 43 96% 56%`) with a spiritual blue secondary (`--prana-blue: 200 60% 55%`), sitting on warm golden-hour backgrounds. The aesthetic is devotional rather than clinical — closer to a meditation room than a productivity dashboard.

The canvas is warm off-white (`--background: 40 30% 96%`) — softer than pure white, carrying a subtle paper/dawn quality. Text uses warm near-black (`--foreground: 25 25% 20%`) instead of pure black, softening the reading experience. The spiritual gradient (`--gradient-spiritual`) layers three warm tones (`40 40% 97% → 45 50% 95% → 35 60% 93%`) for ambient section backgrounds.

Saffron-gold is the singular saturated primary — it appears on primary buttons, focus rings, active states, and the gold gradient (`--gradient-gold`). Spiritual blue is the secondary, used sparingly for contrast and information accents. Depth comes from both borders AND soft glows — unlike flat-only systems, AskMukthiGuru intentionally uses glow tokens (`--glow-gold`, `--glow-blue`, `--glow-white`) to evoke a luminous, devotional feel. The 16px base border radius (`--radius: 1rem`) gives components a generous, friendly rounding — softer than typical 10px systems.

Dark mode (`Dark Sanctuary Theme`) inverts to deep night (`--background: 25 18% 8%`) with the same warm gold accents, evoking meditation at dusk.

**Key Characteristics:**
- Inter for UI sans, Outfit for display, Playfair Display for serif/spiritual headings
- Warm saffron-gold (`--ojas-gold`) as the singular primary accent
- Spiritual blue (`--prana-blue`) as secondary for contrast
- Warm off-white canvas (`40 30% 96%`) with golden-hour undertones
- Both borders AND soft glow shadows for depth (devotional luminosity)
- 16px base border radius (`1rem`) — generous, friendly
- Glassmorphism support via `--glass-bg`, `--glass-border`, `--glass-blur`
- Custom keyframe animations: `lotus-bloom`, `petal-sway`, `voice-pulse`, `fade-in-up`
- shadcn/ui component library on Radix UI primitives
- Full dark mode (`Dark Sanctuary`) preserving warm gold accents

## 2. Color Palette & Roles

### Light Mode (Default — Light Sanctuary)

| Role | Token | HSL Value | Use |
|------|-------|-----------|-----|
| Background | `--background` | `40 30% 96%` | Page canvas, warm off-white |
| Foreground | `--foreground` | `25 25% 20%` | Primary text, headings |
| Card | `--card` | `40 40% 98%` | Card surfaces (slightly lighter than bg) |
| Card Foreground | `--card-foreground` | `25 25% 20%` | Text on cards |
| Popover | `--popover` | `40 45% 99%` | Dropdowns, popovers |
| Popover Foreground | `--popover-foreground` | `25 25% 20%` | Text in popovers |
| Primary | `--primary` | `43 96% 56%` | CTAs, active nav, focus rings, links (saffron-gold) |
| Primary Foreground | `--primary-foreground` | `40 30% 10%` | Text on primary buttons (dark warm) |
| Secondary | `--secondary` | `200 60% 55%` | Secondary actions, info accents (spiritual blue) |
| Secondary Foreground | `--secondary-foreground` | `200 80% 15%` | Text on secondary surfaces |
| Muted | `--muted` | `35 20% 90%` | Disabled backgrounds, subtle fills |
| Muted Foreground | `--muted-foreground` | `25 15% 45%` | Secondary text, captions, placeholders |
| Accent | `--accent` | `45 100% 70%` | Hover states, highlights (light gold) |
| Accent Foreground | `--accent-foreground` | `40 30% 10%` | Text on accent surfaces |
| Destructive | `--destructive` | `0 84% 60%` | Error states, delete actions |
| Destructive Foreground | `--destructive-foreground` | `0 0% 98%` | Text on destructive buttons |
| Border | `--border` | `40 20% 85%` | Card outlines, dividers, input borders |
| Input | `--input` | `40 25% 92%` | Input field backgrounds/borders |
| Ring | `--ring` | `43 96% 56%` | Focus ring color (matches primary) |

### Sacred Energy Colors (Named Tokens)

| Token | HSL | Tailwind | Use |
|-------|-----|----------|-----|
| `--ojas-gold` | `43 96% 56%` | `ojas` | Primary brand — saffron/gold |
| `--ojas-gold-light` | `45 100% 70%` | `ojas-light` | Hover, light accent |
| `--ojas-gold-dark` | `40 90% 45%` | `ojas-dark` | Pressed, dark accents |
| `--tejas-white` | `35 30% 25%` | `tejas` | Warm dark neutral for text |
| `--tejas-glow` | `40 40% 35%` | `tejas-glow` | Mid-tone warm glow |
| `--prana-blue` | `200 60% 55%` | `prana` | Secondary — spiritual blue |
| `--prana-blue-light` | `195 65% 70%` | `prana-light` | Info, light blue accents |
| `--prana-blue-dark` | `205 55% 45%` | `prana-dark` | Deep blue for contrast |

### Dark Mode (Dark Sanctuary)

| Role | Token | HSL Value | Notes |
|------|-------|-----------|-------|
| Background | `--background` | `25 18% 8%` | Deep warm night |
| Foreground | `--foreground` | `40 30% 92%` | Warm light text |
| Card | `--card` | `25 20% 11%` | Elevated charcoal |
| Primary | `--primary` | `43 96% 60%` | Slightly brighter gold for dark contrast |
| Secondary | `--secondary` | `200 50% 45%` | Muted spiritual blue |
| Muted | `--muted` | `25 15% 16%` | Dark surface variant |
| Muted Foreground | `--muted-foreground` | `40 15% 65%` | Lighter for dark-bg readability |
| Accent | `--accent` | `45 90% 55%` | Warm gold hover |
| Destructive | `--destructive` | `0 70% 55%` | Brighter red for dark bg |
| Border | `--border` | *(dark warm)* | Warm dark border |

### Spiritual Gradients (Both Modes)

| Token | Value | Use |
|-------|-------|-----|
| `--gradient-spiritual` | `linear-gradient(135deg, hsl(40 40% 97%), hsl(45 50% 95%), hsl(35 60% 93%))` | Ambient section backgrounds, hero panels |
| `--gradient-gold` | `linear-gradient(135deg, hsl(43 96% 56%), hsl(45 100% 70%))` | Primary CTAs, brand accents |
| `--gradient-celestial` | `linear-gradient(180deg, hsl(40 100% 98%), hsl(45 60% 94%), hsl(43 96% 56% / 0.1))` | Hero overlays, celestial section dividers |

### Glow & Glass Effects

| Token | Value | Use |
|-------|-------|-----|
| `--glow-gold` | `0 4px 30px hsl(43 96% 56% / 0.25)` | Primary button glow, active card accent |
| `--glow-blue` | `0 4px 30px hsl(200 60% 55% / 0.2)` | Secondary/info glow |
| `--glow-white` | `0 4px 20px hsl(40 30% 50% / 0.15)` | Subtle white elevation |
| `--glass-bg` | `40 40% 100% / 0.7` | Glassmorphic panel backgrounds |
| `--glass-border` | `40 30% 70% / 0.4` | Glass panel borders |
| `--glass-blur` | `16px` | Backdrop blur for glass surfaces |

### Color Principles
- Saffron-gold (`--ojas-gold`) is the only primary saturated color in core UI
- Spiritual blue (`--prana-blue`) is the secondary — used for contrast, info, and secondary actions
- Warm neutrals throughout — never cold blue-gray
- Dark mode (`Dark Sanctuary`) inverts luminance but preserves the warm gold accent
- Glow tokens intentionally introduce soft luminosity (devotional feel), unlike flat-only systems
- Destructive red is the only non-brand saturated color, reserved for errors

## 3. Typography Rules

### Font Stack
- **Sans:** Inter (`font-sans`) — all UI text, body, navigation, labels
- **Display:** Outfit (`font-display`) — large headings, hero text, marketing
- **Serif:** Playfair Display (`font-serif`) — spiritual/editorial headings, quotes

### Hierarchy

| Role | Size | Weight | Tailwind | Use |
|------|------|--------|----------|-----|
| Hero/Display | 30-48px | 700 | `font-display font-bold` | Hero titles, landing headlines |
| Page Title | 24px | 700 | `text-2xl font-bold` | Page headings |
| Section Heading | 18px | 600 | `text-lg font-semibold` | Section titles within pages |
| Card Title | 16px | 600 | `text-base font-semibold` | Card headings, list item titles |
| Body | 14px | 400 | `text-sm` | Standard reading text, descriptions |
| Body Medium | 14px | 500 | `text-sm font-medium` | Nav links, form labels |
| Caption | 12px | 500 | `text-xs font-medium` | Metadata labels, helper text |
| Badge Text | 12px | 400 | `text-xs` | Status badges, tags, timestamps |

### Color Hierarchy
- `text-foreground` / `--foreground` — primary text, headings, active nav
- `text-muted-foreground` / `--muted-foreground` — secondary text, captions, placeholders
- `text-primary` — interactive text, links, active states (saffron-gold)
- `text-prana` — spiritual blue accents, info links

### Principles
- Three weights in practice: 400 (read), 500 (interact), 600-700 (announce)
- `text-sm` (14px) is the workhorse for body and labels
- Playfair Display reserved for spiritual/editorial content — never for UI chrome
- Inter handles UI text across all sizes; no custom letter-spacing needed
- Line heights use Tailwind defaults (tighter for headings, relaxed for body)

## 4. Component Patterns

### Buttons (shadcn/ui + Radix UI)

| Variant | Background | Text | Use |
|---------|-----------|------|-----|
| Default | `--primary` (saffron-gold) | `--primary-foreground` (dark warm) | Primary CTAs — "Send", "Ask", "Continue" |
| Secondary | `--secondary` (spiritual blue) | `--secondary-foreground` | Secondary actions, info buttons |
| Outline | transparent | foreground | Tertiary actions — "Cancel", "Back" |
| Ghost | transparent | foreground | Inline actions, icon buttons, nav |
| Destructive | `--destructive` (red) | `--destructive-foreground` (white) | Delete, remove |
| Link | transparent | `--primary` | Inline text links |

- Sizes follow shadcn defaults (`sm`, `default`, `lg`, `icon`)
- All use `rounded-lg` (16px base radius)
- Focus: border + ring at primary color
- Primary buttons may carry `--glow-gold` for devotional emphasis on hero CTAs

### Cards & Containers
- Background: `--card` (`40 40% 98%`, slightly lighter than page bg)
- Border: `1px solid --border`
- Radius: `rounded-lg` (16px)
- Padding: `p-4` to `p-6` depending on density
- Optional glow (`--glow-gold`) on active/featured cards
- Glassmorphic variant uses `--glass-bg` + `--glass-border` + `backdrop-blur-[16px]`

### Inputs
- Border: `--input`, `rounded-lg`
- Focus: border shifts + ring at `--ring` (saffron-gold)
- Placeholder: `--muted-foreground`
- Built on Radix UI / shadcn input primitives

### Badges
- Shape: pill (`rounded-full`) or `rounded-lg`
- Variants mirror button variants (default, secondary, outline, destructive)
- Used for: status, categories, tags, meditation step indicators
- Font: `text-xs`

### Chat Interface (Signature Component)
- `ChatInterface` is the orchestrating component (`src/components/chat/`)
- Streaming responses checkpoint to `sessionStorage` every 500ms
- BrandedSpinner as Suspense fallback — never bare "Loading..." text
- Voice input uses `voice-pulse` animation for mic feedback

### Dialogs (shadcn/ui)
- Overlay: semi-transparent backdrop
- Content: `--card` background, `rounded-lg`, `--border`
- Header: title + optional description
- Footer: action buttons right-aligned

### Animations (Custom Keyframes)
| Animation | Duration | Use |
|-----------|----------|-----|
| `lotus-bloom` | 1.5s | Hero entrance, spiritual reveals |
| `petal-sway` | 4s infinite | Idle decorative motion (lotus petals) |
| `voice-pulse` | 1.5s infinite | Mic/voice input feedback |
| `fade-in-up` | 0.7s | Section entrances, content load |
| `scale-in` | 0.3s | Modal/tooltip entrances |
| `slide-in-right` | 0.4s | Toast notifications, side panels |

## 5. Layout Principles

### Spacing System
- Tailwind default scale: 1 (4px), 2 (8px), 3 (12px), 4 (16px), 5 (20px), 6 (24px), 8 (32px)
- Component internal padding: `p-4` (16px) to `p-6` (24px)
- Section gaps: `mb-8` (32px) to `mb-12` (48px) — generous for spiritual breathing room
- Page padding: `px-4 py-6` to `px-8 py-8`

### Page Structure
- Chat-first layout — `ChatPage` is the primary destination
- Fixed sidebar for conversation history (dispatches `conversation:updated` window event on mutation)
- Content area fills remaining width
- Profile page hosts memory manager with graph toggle

### Container
- Centered, `2rem` padding, max `1400px` at `2xl` (per `tailwind.config.ts`)

### Whitespace Philosophy
- Generous vertical rhythm between sections (32-48px) — evokes spaciousness
- Compact within components (16-24px internal padding)
- Page titles get breathing room (`mb-8`)
- Lists use `space-y-2` to `space-y-3` for item gaps

## 6. Depth & Elevation

| Level | Treatment | Use |
|-------|-----------|-----|
| Flat | No border, no shadow | Page background, section fills |
| Surface | `1px solid --border` | Cards, containers, inputs |
| Elevated | `--card` bg + border + optional `--glow-gold` | Featured cards, active states |
| Glass | `--glass-bg` + `--glass-border` + 16px backdrop blur | Overlay panels, modals |
| Overlay | Semi-transparent backdrop | Modal backgrounds |
| Focus | Ring at `--ring` (saffron-gold) | Keyboard focus on interactive elements |

**Depth Philosophy:** AskMukthiGuru uses a hybrid depth model — borders for structure AND soft glows for luminosity. Unlike flat-only systems, the glow tokens (`--glow-gold`, `--glow-blue`) intentionally introduce a devotional, candlelit quality to primary CTAs and featured cards. Elevation is communicated through:
1. Background color shifts (card on off-white page)
2. Borders (`1px solid --border`, warm and whisper-weight)
3. Soft glows (`--glow-gold` on primary/featured elements)
4. Glassmorphism (`--glass-bg` + backdrop blur for overlays)

## 7. Responsive Behavior

### Breakpoints
Standard Tailwind breakpoints apply.

| Name | Width | Key Changes |
|------|-------|-------------|
| Mobile | <640px (`sm`) | Single column, collapsed sidebar, reduced padding |
| Tablet | 640-1024px (`md`) | Toggleable sidebar, content fills width |
| Desktop | 1024px+ (`lg`) | Fixed sidebar + content area, full layout |

### Collapsing Strategy
- **Sidebar:** Fixed at desktop, drawer at mobile/tablet
- **Page content:** `px-8` desktop, `px-4` mobile
- **Chat:** Full height at all breakpoints, single column
- **Dialogs:** Centered overlay at desktop, bottom-sheet pattern at mobile
- **Horizontal overflow:** Clipped (`overflow-x: hidden` on html/body) — decorative absolute elements must not create scrollbars

### Touch Targets
- All buttons minimum `h-9` (36px) for comfortable touch
- Navigation items have generous padding
- Chat input accessible at all sizes

## 8. Accessibility & States

### Interactive States

| State | Treatment |
|-------|-----------|
| Default | Standard appearance with border token |
| Hover | Background shifts to `--accent`, text darkens |
| Active/Pressed | Slightly darker background, `--ojas-gold-dark` |
| Focus | Border + ring at `--ring` (saffron-gold) |
| Disabled | `opacity-50`, `pointer-events-none` |
| Loading | BrandedSpinner replaces content, element disabled |

### Focus System
- All interactive elements receive visible focus indicators
- Focus ring: `--ring` (saffron-gold), 2-3px
- Tab navigation supported throughout
- Focus ring uses primary gold for consistent visual language

### Color Contrast
- Primary text (`--foreground` on `--background`): warm near-black on off-white — exceeds WCAG AAA
- Muted foreground on background: meets WCAG AA
- Saffron-gold on white: meets WCAG AA for large text and UI components
- Dark mode: all contrast ratios maintained through token inversion

### Screen Reader Support
- Semantic HTML elements throughout (nav, main, section, button)
- ARIA labels on icon-only buttons
- Status badges use appropriate ARIA attributes
- Chat messages marked up semantically for screen reader navigation

### Suspense & Loading
- `BrandedSpinner` is the only Suspense fallback — never bare "Loading..." text
- Lazy routes go through `lib/lazyWithRetry.ts` (retries chunk-load failures)

## 9. Agent Prompt Guide

### Quick Token Reference

**Light mode (default):**
- Background: `40 30% 96%` (warm off-white canvas)
- Foreground: `25 25% 20%` (warm near-black text)
- Primary: `43 96% 56%` (saffron-gold — Ojas)
- Secondary: `200 60% 55%` (spiritual blue — Prana)
- Border: `40 20% 85%` (warm whisper-weight)
- Muted text: `25 15% 45%` (warm medium gray)
- Radius: `1rem` (16px)
- Font: Inter (sans), Outfit (display), Playfair Display (serif)

**Dark mode (Dark Sanctuary):**
- Background: `25 18% 8%` (deep warm night)
- Card: `25 20% 11%` (elevated charcoal)
- Primary: `43 96% 60%` (brighter gold for contrast)

### Component Creation Prompts

- "Create a page section: warm off-white background (`bg-background`). Page title at `text-2xl font-bold text-foreground`. Subtitle at `text-sm text-muted-foreground mt-1`. Content area with `px-8 py-8`. Use `font-display` (Outfit) for hero titles."

- "Create a card: `bg-card`, `1px solid border border-border`, `rounded-lg`. Internal padding `p-5`. Title at `text-base font-semibold text-foreground`. Description at `text-sm text-muted-foreground`. For featured cards, add `shadow-[0_4px_30px_hsl(43_96%_56%/0.25)]` (glow-gold)."

- "Create a primary button: `bg-primary` (saffron-gold), `text-primary-foreground` (dark warm), `rounded-lg`, `h-10 px-4`. Hover darkens. Focus shows ring at `--ring`. Use shadcn Button with default variant. Optional: add `shadow-[var(--glow-gold)]` for hero CTAs."

- "Create a status badge: pill shape (`rounded-full`), `text-xs`. Use shadcn Badge. For connected/active status: `bg-primary/10 text-primary border-primary/20`."

- "Create a glassmorphic panel: `bg-[hsl(var(--glass-bg))] border border-[hsl(var(--glass-border))] backdrop-blur-[16px] rounded-lg p-6`. Use for overlay panels and modals."

- "Create a spiritual hero: `bg-gradient-to-br from-[hsl(40_40%_97%)] via-[hsl(45_50%_95%)] to-[hsl(35_60%_93%)]` (gradient-spiritual). Title in `font-serif font-bold` (Playfair Display). Apply `animate-lotus-bloom` on mount for entrance."

### Design Guardrails
1. Saffron-gold (`--ojas-gold` / `--primary`) is the primary saturated color — spiritual blue (`--prana-blue`) is secondary only
2. Use `--glow-gold` sparingly for hero/featured emphasis — not on every card
3. Warm neutrals only — never cold blue-gray (`slate`, `gray`, `zinc` are wrong; use warm `stone`-like tones via our tokens)
4. `text-sm` (14px) for body text — `text-base` only for card titles
5. `rounded-lg` (16px) for all containers — do not use sharp corners
6. Borders are whisper-weight (`--border` token) — never `border-2` or darker
7. Three font weights: 400, 500, 600-700. Avoid 300 (thin) or 800-900 (heavy)
8. Dark mode preserves warm gold accents — never use cold blue accents in dark
9. Icons from lucide-react only — consistent stroke width and style
10. `BrandedSpinner` is the only Suspense fallback — never bare "Loading..." text
11. Playfair Display (`font-serif`) reserved for spiritual/editorial content — never for UI chrome
12. Spacing uses Tailwind scale — no arbitrary pixel values