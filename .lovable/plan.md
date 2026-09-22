# Cross-Platform UI Clarity and Polish

## Goal
Make every primary journey feel coherent on web, Android, and iOS: one navigation model, one loading state, one language control, and a calmer profile.

## 1. Unblock and verify the real journeys
- Keep the mandatory safety disclosure, but ensure it behaves as a true first-visit gate rather than obscuring every audited route.
- Test acceptance, dismissal, persistence, keyboard focus, and mobile safe-area behavior before evaluating pages behind it.
- Re-capture landing, chat, profile, practices, knowledge graph, and authentication at phone and desktop sizes.

## 2. Chat: one clear interaction model
- Replace the language menu's manual viewport positioning with the existing anchored menu primitive so it opens reliably above or below the composer.
- Keep one discoverable language entry point in the composer; preserve language selection, translation, voice, native labels, and 44px targets.
- Collapse optimistic loading, pipeline progress, slow-response copy, and ThinkingPills into one AI Elements-based status surface. Remove dead duplicate loading components.
- Derive one `isThinking` state so fast, cached, streamed, and delayed responses cannot create missing or overlapping indicators.
- Keep the three-tier empty state: greeting, composer, starter actions. Remove orphaned welcome/empty-state implementations that could be reintroduced accidentally.

## 3. Navigation and sidebars
- Show exactly one return-to-chat action on chat-owned pages, preserving conversation return context.
- Remove duplicate search and Serene Mind actions where header and sidebar currently expose the same command.
- Share one Explore/navigation definition between desktop chat sidebar and mobile conversation sheet while retaining device-appropriate layouts.
- Preserve desktop collapse state, mobile sheet behavior, incognito controls, conversation grouping, and accessibility links.

## 4. Profile: simplify hierarchy
- Remove the duplicate identity hero, duplicate journey metrics, repeated insights, and repeated chat/practice actions.
- Establish clear responsibilities: Overview for identity and next step; Practice for stats, streak, heatmap, and milestones; Memory for notes and Second Brain; Settings for preferences, security, exports, and account actions.
- Reduce mobile tab overload with a compact, discoverable navigation treatment and no unexplained horizontal clipping.
- Standardize surfaces to calm Golden Dawn tokens, system typography, restrained borders, consistent radii, and no stacked glow/gradient cards.
- Preserve avatar operations, URL-linked tabs, MFA redirects, unsaved-change handling, current-conversation protection, and all existing metrics.
- Keep “Clear Local Data,” cloud-memory erasure, and account deletion as separate flows with existing confirmations.

## 5. Landing and shared surfaces
- Restore legibility of the landing visual by reducing the verified near-black hero overlay while retaining the existing image and bounded particle performance safeguards.
- Align public and signed-in surfaces through shared Golden Dawn colors, typography, control sizing, and safe areas without making them visually identical.
- Verify header safe-area handling in installed/mobile display modes.

## Validation
- Focused unit tests for language selection, ThinkingPills/loading, navigation, profile tab URLs, and deletion safety boundaries.
- Full frontend typecheck, lint, test suite, and production build through project scripts.
- Playwright journeys at 390px and 1280px: accept disclosure, open language menu, send a message, inspect one loading indicator, navigate away/back, open every profile tab, and check overflow/focus.
- Authenticated profile evidence remains conditional on an available test session; public and signed-out states will still be fully verified.

## Technical notes
- Frontend-only scope: no backend, schema, security-policy, persistence, metric-formula, or spiritual-answer changes.
- Reuse installed AI Elements and existing design tokens; no new UI dependency.
- Implementation task record and durable UI lessons will be updated during the approved build.
