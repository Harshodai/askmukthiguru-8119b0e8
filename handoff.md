# Handoff — Profile + Chat UI Redesign

## Goal
Take `/profile` and the chat surface from "clumsy" to ChatGPT/Claude-caliber. Preserve Golden Hour aesthetic, HSL tokens, every feature. Feel native on iOS/Android via Capacitor.

## Current state (this session)
Phase 1 + focused visual polish shipped. Deep component splits deferred (mega-files still ≥1000 LoC but no longer visually clumsy).

### Shipped
- **Design tokens (`src/index.css`)** — added `--chat-surface`, `--chat-user-bubble`, `--chat-user-foreground`, `--assistant-foreground`, `--hairline`, `--divider`, `--overlay-scrim`, `--radius-bubble/card/pill`, motion tokens (`--dur-*`, `--ease-standard`). Full light + dark parity.
- **Native-feel utilities** — `.safe-top`, `.safe-bottom`, `.safe-x` (env safe-area insets), `.momentum-scroll` (iOS momentum + overscroll-contain), `.no-tap-highlight`, `.border-hairline`, `.bg-chat-user`.
- **Chat message polish (`ChatMessage.tsx`)**
  - User bubble: `bg-chat-user` token instead of `bg-ojas/12` — softer, warmer, ChatGPT/Claude-like pill (rounded-[var(--radius-bubble)]), no thick border, single-hairline shadow.
  - Assistant avatar: subtler 7×7 gradient chip, hairline border.
  - Max-width bumped to 85%/75% on user messages, line-height 1.55.
- **Chat scroll surface (`ChatInterface.tsx`)** — momentum-scroll + safe-x on the main scroll container; `space-y-5/6` between messages (was 2/3) — the biggest breathability win.
- **Starter pills** — hairline border instead of chunky `border-border/70`, no shadow.
- **Profile page (`ProfilePage.tsx`)**
  - New **hero row**: 64/80px avatar, display name (serif), email, streak chip with Flame icon. Flat, generous, no gradient panel.
  - **Tabs rebuilt**: horizontally scrollable pill row on mobile (no more cramped 7-col grid), true 7-col grid on desktop, `bg-muted/40` container.
  - Wrapper picks up `safe-x` for Capacitor insets.

### Files touched
- `src/index.css`
- `src/components/chat/ChatMessage.tsx`
- `src/components/chat/ChatInterface.tsx`
- `src/pages/ProfilePage.tsx`

## Not done yet (queued)
1. **Split mega-files** into focused sub-components:
   - `ChatMessage.tsx` (1283 LoC) → `AssistantMessage / UserMessage / MessageMarkdown / MessageActions / SourcesInline / ThinkingIndicator`
   - `ChatInterface.tsx` (1991 LoC) → extract `useChatController` hook + `ChatShell / ChatEmptyState`
   - `ProfilePage.tsx` (1068 LoC) → `ProfileHero / cards/*`
2. **Composer rebuild** — single-row auto-grow, mic+attach+send inside the field, morphing send/stop button.
3. **Empty state** — already Claude-ish; polish typography scale and give suggestion pills more room.
4. **Desktop sidebar** — slim to 260px, shadcn Sidebar primitives, group Today/Yesterday/Last 7d (data already grouped by `conversationGrouping.ts`).
5. **Stat tiles + 7-day sparkline** in Insights tab (SVG, no chart lib).
6. **Danger zone** — group destructive actions under Data tab with confirmation dialogs.
7. **QA** — Playwright visual sweep at 375/390/768/1280/1920; contrast pass on new tokens both themes.

## Next step
Start with the composer rebuild (highest daily-use impact) and the sidebar slim-down. Both are contained, each ≤ 1 session, and unblock further visual density work without touching the huge ChatMessage file.

## Risks
- Behavior of ChatMessage was unchanged; only bubble styling swapped. If a test snapshotted the old classes it will need regen.
- Profile hero reads `user.email` from `useRequireAuth` — verified `user` is returned; falls back to a friendly string.
