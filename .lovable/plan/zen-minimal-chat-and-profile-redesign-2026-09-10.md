# Zen Minimal Chat and Profile Redesign

## Chat

- Remove decorative particles, the extra guidance panel, and the duplicate resume/teaching block from the empty state.
- Keep exactly three tiers: greeting with one subline, primary composer, and one compact row of starter actions.
- Keep language selection inside the composer toolbar; simplify its pill and menu while preserving voice and translation behavior.
- Make the empty-state composer sit in the mobile thumb zone with safe-area spacing, without changing the active-conversation composer.
- Tighten the AI disclosure into a quiet supporting line near the composer while retaining required disclosure content.

## Profile

- Restyle the page as a focused single-column flow using Golden Dawn semantic tokens and system typography.
- Replace the oversized profile card and pill-heavy navigation with a compact identity header and clean segmented navigation.
- Flatten section styling, reduce nested cards and decorative icons, and standardize section headings, fields, and action rows.
- Preserve real metrics, privacy controls, memory tools, account actions, and all existing data behavior.
- Keep 44px touch targets, safe-area spacing, and horizontal overflow protection across web, Android, and iOS.
- make sure all things will work by trying to seed some to test and making sure that this is world class and top notch by design, use websearch if needed

## Validation

- Run focused chat/profile tests, lint, and production build through the project harness.
- Capture mobile and desktop chat screenshots plus authenticated profile screenshots when a preview session is available.
- Check light/dark contrast, keyboard focus, reduced motion, and composer overlap at narrow heights.

## Technical notes

- Frontend presentation only; no backend, schema, metric formula, or persistence changes.
- Reuse installed AI Elements composer primitives and existing semantic design tokens.
- Update `lessons.md` only with durable UI lessons introduced by this implementation.