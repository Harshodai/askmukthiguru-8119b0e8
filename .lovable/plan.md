# Mobile Polish, Language Icon, Profile Redesign

## 1. Mobile UX hardening (web + Capacitor iOS/Android)

- Apply the existing `safe-top` / `safe-bottom` / `safe-x` utilities consistently at the app shell level instead of ad hoc per page: chat header, chat composer, mobile sheets, profile hero, and any fixed/floating buttons.
- Ensure every interactive control meets a 44x44 CSS px minimum hit area (icon buttons in chat header, composer actions, language pill, profile action rows, sheet close buttons). Small visual icons keep their size; the tap target grows via padding.
- Bottom-sheet ergonomics: add a grab handle, rounded top corners, max height of ~85dvh with internal scroll, safe-area bottom padding, and swipe-to-dismiss where the primitive supports it. Applies to `MobileConversationSheet`, `CitationPanel`, and the starter-preview sheet.
- Add `touch-manipulation` and momentum scrolling on scroll containers to remove tap delay and rubber-band jank.

## 2. Language selector: drop flag emoji

- Remove `LANGUAGE_FLAGS` and all emoji rendering (currently renders as empty boxes on many Android/Windows fonts).
- Compact pill: `Languages` icon + short native label (e.g. "हिन्", "EN").
- Dropdown rows: a small `Globe` glyph tile for each row (same treatment already used in `LanguageOnboardingStep`), native name primary, English name secondary, check dot for selection, 48px row height.
- Update `LanguageOnboardingStep` to match the same row visual so onboarding and in-chat picker are one language.
- Update the existing `LanguageSelector` tests for the new markup.

## 3. Profile tab redesign — calm, spiritual, mobile-first

- Single-column, generous vertical rhythm on mobile; two-column at `lg` with the identity/hero rail sticky on the left.
- Sections in a clear hierarchy: Presence (avatar, name, one-line intent) → Practice (stat tiles + 7-day sparkline) → Journey (streak / healing path) → Knowledge (second brain, graph) → Preferences → Account.
- Section headers as quiet uppercase micro-labels with hairline dividers rather than heavy cards inside cards.
- Serif for numerals and headings, muted body copy, `border-hairline` and `bg-card` only — no nested borders, no drop shadows stacking.
- Remove excess: duplicate stat displays, redundant descriptive paragraphs, decorative icons that carry no information, and any card that shows the same number as a tile above it.

## 4. Excess removal pass (chat + profile)

- Chat: collapse remaining duplicate affordances on the empty state (one primary invitation, one row of starters, one quiet attribution line), keep only one language entry point, and demote secondary links into the disclosure already added.
- Profile: fold single-value cards into the tile grid; move rarely used actions (export, delete) into a compact "Account" list at the bottom.

## Technical notes

- Presentation-only: no backend, schema, or data-fetch changes. Metric calculations in `meditationMetrics.ts` stay as-is.
- Files: `src/components/chat/LanguageSelector.tsx`, `src/components/onboarding/LanguageOnboardingStep.tsx`, `src/components/chat/ChatInterface.tsx`, `src/components/chat/MobileConversationSheet.tsx`, `src/components/chat/CitationPanel.tsx`, `src/components/ui/sheet.tsx` (mobile variant), `src/pages/ProfilePage.tsx`, `src/components/profile/*`, `src/index.css` (tap-target + sheet utilities), locale files for any new strings.
- All new strings go through `t()` with English defaults; Hindi keys added alongside.
- Verify with typecheck, existing Vitest suite, and Playwright screenshots at 375px, 768px, and 1280px.
