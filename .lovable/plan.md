## Goal

Ruthlessly fix `ChatPage` end-to-end so it feels on par with claude.ai / manus.im: centered empty state with spiritual greetings, tight message rhythm, sticky non-overlapping composer, clean language menu, refined sidebar, and correct mobile/tablet layout.

## Root causes (from audit of `src/components/chat/*`, 1771-line `ChatInterface.tsx`)

1. **Empty state off-center** — `ChatInterface` renders empty state inside the same flex column as the composer with no min-height centering; hero is top-aligned, not vertically centered in the available area.
2. **Greeting is time-of-day only** — no spiritual variants; claude.ai-style personal + spiritual greeting missing.
3. **Prompt-card click broken** — `ChatEmptyState` prompt cards call a handler that sets composer text but never triggers `handleSend`; also races with focus timing.
4. **Huge message gaps** — `MessageList` uses `space-y-8`/large vertical padding per message; user + assistant rendered as heavy cards with `py-6`/`my-6`; no grouping.
5. **Composer overlap with last answer** — messages container lacks bottom padding equal to composer height; composer is `absolute`/`fixed` without a spacer.
6. **Language selector opens upward off-screen** — `LanguageSelector` popover uses `side="top"` with no `collisionPadding`/`avoidCollisions`; on short viewports it clips above the fold.
7. **Sidebar** — `DesktopSidebar` fixed width, no collapse polish, thread rows too tall, hover states weak.
8. **Mobile/tablet** — no responsive breakpoints on grid; sidebar always mounted; composer full-bleed with wrong safe-area padding; header wraps.

## Approach

Migrate the chat surface to **AI Elements** (per `chat-ui-composition` contract) and rebuild layout with a strict 3-zone shell. Preserve backend transport, storage, streaming, memory, citations — only presentation changes.

### Phase 1 — Install AI Elements + shell

- `bunx ai-elements@latest add conversation message prompt-input shimmer tool`
- New `ChatShell.tsx`: CSS grid `[sidebar] [main]` on `lg+`, single column on mobile with `Sheet` sidebar.
- Main column is a flex column: `header` (sticky top) / `scroll region` (Conversation) / `composer` (sticky bottom, safe-area padded).
- Scroll region gets `pb-[calc(var(--composer-h)+1rem)]` via CSS var written from composer `ResizeObserver` — kills composer/answer overlap.

### Phase 2 — Empty state (centered + spiritual)

- `ChatEmptyHero.tsx` grid-placed with `place-items-center` inside a `min-h-full` wrapper so orb + greeting + prompt cards sit dead-center regardless of viewport height.
- Greeting util: rotate through spiritual variants keyed on time-of-day AND day-of-week (e.g., "Namaste, {name}. May this morning meet you in stillness.", "Peace to you, {name} — the evening is a good teacher.", "Welcome home, seeker."). Deterministic per session, not random-flickering.
- Prompt cards call `onPromptSelect(text)` which BOTH pre-fills composer AND immediately calls `send(text)` — no double-click required. Focus returns to composer only if send is deferred.

### Phase 3 — Message rhythm (claude.ai density)

- Replace `MessageList` + `ChatMessage` with AI Elements `Conversation` / `Message` / `MessageContent` / `MessageResponse`.
- Assistant: no background, `text-foreground`, `prose-sm` markdown, 12px between turns, 4px within a turn's parts.
- User: right-aligned bubble, `bg-primary/10 text-foreground`, max-width `min(70%, 42rem)`.
- Group consecutive same-role messages: shared avatar rail on first, subsequent get indent only.
- `Shimmer` "Contemplating…" while `status==='submitted'`.

### Phase 4 — Composer

- AI Elements `PromptInput` + `PromptInputTextarea` + `PromptInputFooter` (submit right-aligned via `justify-end`).
- Sticky bottom, `max-w-3xl mx-auto`, `pb-[env(safe-area-inset-bottom)]`.
- Enter sends, Shift+Enter newline, submit toggles to Stop while streaming.
- Autofocus on: mount, post-send, stream-end, thread switch.
- Disclaimer line rendered as a single muted caption directly under the composer, consistent across empty + active states.

### Phase 5 — Language selector

- Rebuild `LanguageSelector` on shadcn `Popover` with `side="top" align="end" sideOffset={8} collisionPadding={16} avoidCollisions`.
- On `<sm` screens, switch to `Sheet` from bottom instead of popover.

### Phase 6 — Sidebar refresh

- `DesktopSidebar`: 260px wide, condensed rows (h-9), truncate w/ tooltip, active row uses `bg-accent`, hover `bg-accent/50`. Add pinned "New chat" button top, footer user chip bottom. Collapse toggle persists to localStorage.
- Mobile: same content behind `Sheet`, trigger in header.

### Phase 7 — Responsive pass

- Header collapses actions into overflow menu below `md`.
- Empty-state prompt grid: `grid-cols-1 sm:grid-cols-2`, cards `min-h-24`.
- Orb: `w-20 sm:w-24`.
- Verify at 360, 414, 768, 1024, 1280 via Playwright screenshots and attach.

### Phase 8 — Verification

- Playwright script at `/tmp/browser/chat-audit/` captures: empty state (mobile/tablet/desktop), post-first-message, mid-stream, post-stream, language menu open, sidebar open on mobile. View each screenshot to confirm centering, spacing, no overlap, language menu on-screen.
- `tsgo` typecheck.
- Vitest run for `ChatInterface.test.tsx` — update assertions where DOM shape changed.

## Files touched

- **New:** `src/components/chat/ChatShell.tsx`, `ChatEmptyHero.tsx`, `hooks/useChatSession.ts`, `lib/chat/greeting.ts`, `src/components/ai-elements/*` (via CLI).
- **Rewritten:** `ChatInterface.tsx` (down to ~350 lines as orchestrator), `ChatComposer.tsx`, `MessageList.tsx`, `ChatMessage.tsx`, `LanguageSelector.tsx`, `DesktopSidebar.tsx`, `ChatEmptyState.tsx` (→ delegates to `ChatEmptyHero`).
- **Untouched:** `src/lib/chat/transport.ts`, `chatStorage.ts`, memory/citation code, backend.

## Out of scope

- Rate limiting (still pending Redis-vs-in-memory answer).
- Landing page redesign.
- New backend endpoints.

## Technical notes

- CSS var `--composer-h` set by `ResizeObserver` on the composer wrapper — the only reliable way to keep the scroll region padded regardless of textarea auto-grow.
- Greeting util is a pure function `getSpiritualGreeting({ hour, firstName, seed })` — testable in vitest.
- Prompt-card send: single `send(text, { origin: 'prompt-card' })` call, no double-hop through composer state.

Approve to proceed to build. And use websearch so that you can see and feel how Claude and chatgpt and even lovable on how they do ruthlessly, you are a staff product designer and frontend engineer now