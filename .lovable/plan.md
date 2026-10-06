# Seeker Journey and Responsive UI Cleanup

## Goal
Make sign-up, language choice, Chat, note saving, Profile, and returning later feel like one clear journey across phone, tablet, and desktop.

## 1. Simplify onboarding and Google sign-in
- Keep the existing profile-backed Supabase auth; no new account tables.
- Route every first successful sign-in directly to language choice, then Chat. Make deeper Profile personalization optional instead of blocking the first question.
- Persist onboarding completion and preferred language in authenticated user metadata plus the existing local profile, so returning users do not repeat onboarding on another device.
- Preserve the 18+ gate, MFA step-up, email confirmation, native deep links, and duplicate Google-callback protection.
- Diagnose the public Google OAuth redirect flow and show clear recovery when provider or redirect configuration is wrong. Provider settings remain managed in the external Supabase dashboard.

## 2. Remove duplicated and confusing UI
- Make Supabase Notes the single “Save as note” destination from Chat and Profile; remove the dual-write/fallback behavior from chat messages.
- Stop showing fabricated notebook examples when the backend is unavailable; show an honest unavailable/empty state.
- Preserve one Profile entry per navigation context and tag Profile/Settings links opened from Chat with a reliable return-to-chat path.
- Reuse one data-export action and remove conflicting duplicate theme controls where they create inconsistent save behavior.

## 3. Responsive Chat and Profile polish
- Keep Chat focused: one sidebar/menu per viewport, compact header actions, full-size touch targets, and response preferences reachable on mobile.
- Replace the Profile phone dropdown with a compact visible four-tab strip so destinations remain discoverable.
- Preserve safe areas, sticky composer/save controls, URL tab state, security deep links, and current Golden Hour design tokens.
- Check phone, tablet, and desktop for overflow, overlap, focus order, tap targets, and back-navigation consistency.

## 4. Complete and verify the journey
- Add focused tests for onboarding persistence, language handoff, Chat-to-Profile return links, canonical note saving, and truthful notebook failure states.
- Exercise sign-in redirect initiation, language choice, first question UI, save note, reload, and return navigation with Playwright.
- Run focused frontend tests and use the preview build signal; capture phone, tablet, and desktop evidence.

## Technical details
- Frontend-first change using existing Supabase auth, `profiles`/`notes`, storage helpers, and design-system components.
- No new dependency, backend service, database schema, or fabricated user data.
- Authenticated Google completion cannot be fully verified in this sandbox because the external Supabase session/provider configuration is not inspectable; redirect initiation and callback handling will still be tested.
