# Profile + Chat UI: World-Class Redesign

## Goal

Take `/profile` and the chat surface from "clumsy" to a **ChatGPT/Claude-tier** experience — visually calm, information-dense but breathable, native on iOS/Android via Capacitor, and structurally scalable. Keep Golden Hour palette + HSL tokens, keep every feature (voice, i18n, memory manager, meditation stats, sources, tour, favorites, notes), no new heavy deps.

## Guiding principles (locked)

1. **One content column, generous rhythm.** Chat mirrors ChatGPT/Claude: assistant messages have no bubble, user messages a subtle rounded surface, max-width ~48rem, consistent 16/24/32px vertical rhythm.
2. **Chrome disappears.** Header, sidebar, composer shrink to essentials. Icons ≥ 44×44 on mobile, safe-area insets everywhere.
3. **Tokens only.** No hex, no `text-white`/`bg-black`. Extend `index.css` with a small set of new semantic tokens (`--chat-surface`, `--chat-user-bubble`, `--chat-user-foreground`, `--divider`, `--hairline`) instead of inventing per-component colors.
4. **Native feel.** Momentum scroll containers, `env(safe-area-inset-*)` padding, no hover-only affordances, haptics via `@capacitor/haptics` if already installed (skip if not), `-webkit-tap-highlight-color: transparent`.
5. **Scalable structure.** Split the two mega-files (`ChatInterface.tsx` 1991 LoC, `ChatMessage.tsx` 1283 LoC, `ProfilePage.tsx` 1068 LoC) into focused sub-components. No behavior change in this pass unless it improves UX.

## Scope

- `src/pages/ProfilePage.tsx` (+ new `src/components/profile/*` split)
- `src/components/chat/ChatInterface.tsx`, `ChatMessage.tsx`, `MessageList.tsx`, `ChatHeader.tsx`, `DesktopSidebar.tsx`, `MobileConversationSheet.tsx`, composer
- `src/index.css` — new tokens, mobile-safe utilities
- `tailwind.config.ts` — expose new tokens
- Landing/other pages: out of scope this pass.

---

## Plan

### Phase 1 — Design system extension (small, foundational)

- Add tokens to `index.css` (both light + dark):
  - `--chat-surface` (page bg), `--chat-user-bubble`, `--chat-user-foreground`, `--assistant-foreground`, `--hairline` (1px borders), `--divider`, `--overlay-scrim`.
  - `--radius-bubble`, `--radius-card`, `--radius-pill`.
  - Motion: `--ease-standard`, `--dur-fast/base/slow`.
- Add safe-area utilities: `.safe-top`, `.safe-bottom`, `.safe-x` using `env(safe-area-inset-*)`.
- Add `.momentum-scroll` (`-webkit-overflow-scrolling: touch; overscroll-behavior: contain`).
- Extend `tailwind.config.ts` with the new tokens under `colors`/`borderRadius`.

### Phase 2 — Chat: layout & message rendering (the big win)

- **New `ChatShell**` wrapping header + main + composer with `dvh` height, safe-area insets, and a max-width content column (`max-w-3xl mx-auto`).
- `**ChatMessage` split** into `AssistantMessage`, `UserMessage`, `MessageActions`, `SourcesInline`, `MessageMarkdown`.
  - Assistant: transparent, prose-tuned typography (Instrument Serif optional for pull-quotes, current serif for body), inline citations chip row, copy/regenerate/feedback actions revealed on hover *and* on tap (mobile long-press).
  - User: pill surface `bg-[--chat-user-bubble] text-[--chat-user-foreground]`, right-aligned, no avatar clutter.
- **MessageList**: virtualized-free but with `content-visibility: auto` per message, scroll anchoring, ChatGPT-style "scroll to latest" FAB retained but restyled (pill with count).
- **Streaming**: cursor caret, shimmer replaced with a small `Thinking…` label + subtle pulse dot (no big spinner).
- **Composer** rebuilt: single-row auto-grow textarea, mic + attach + send inside the field, character/word gentle hint, `Cmd/Ctrl+Enter` retained, on mobile a floating send that morphs into stop while streaming.

### Phase 3 — Chat: navigation & headers

- **Desktop sidebar** slimmed to 260px, groups: New chat (prominent), Recent (grouped by Today/Yesterday/Last 7d — already exists in `conversationGrouping`), Pinned, Search. Icon-only 56px rail when collapsed; use shadcn `Sidebar` primitives per knowledge, ensure trigger stays visible.
- **Chat header** reduced to: sidebar toggle · title (current conversation) · overflow (sources, export, share). Guru photo moves out of header into an ambient hero only for empty state (per memory rule "Guru photo in chat header" — will re-confirm before moving; fallback: keep it but shrink and align left).
- **Mobile**: header collapses on scroll; sidebar becomes a Sheet (already present) with better spacing, thumb-reachable close.

### Phase 4 — Chat: empty state & onboarding polish

- Empty state redesigned to Claude-style: centered greeting, 4 suggestion chips (dynamic from `greeting.ts`), zero clutter. Guarded so tour + PrePracticeGate still trigger.

### Phase 5 — Profile page redesign

Split into `ProfileHero`, `ProfileTabs`, `AccountCard`, `PreferencesCard`, `MeditationStatsCard`, `MemoryCard`, `LanguageCard`, `NotificationsCard`, `DataCard`, `DangerZoneCard`.

Layout:

- **Hero**: avatar (72px), name, email, member-since, streak badge — flat, no gradient card, generous whitespace.
- **Tabs** (shadcn `Tabs`): *Account · Practice · Preferences · Data*. Mobile becomes a segmented control; desktop a horizontal underline tabs row.
- **Cards**: uniform `rounded-2xl border border-hairline bg-card p-6`, section title + one-line helper + content. Kill nested gradient panels.
- **Meditation stats**: refactor into 4 clean stat tiles (Total, Minutes, Streak, Breath cycles) + a small 7-day sparkline (SVG, no chart lib).
- **Memory manager**: unchanged logic; wrap in the new card + move destructive actions to the Data tab.
- **Danger zone**: destructive actions (sign out everywhere, delete account) grouped, red-outlined, confirmation dialog.
- **Mobile**: single column, sticky sub-nav for tabs, safe-area padding.

### Phase 6 — Native (Capacitor) polish

- Verify `viewport-fit=cover` in `index.html`; add if missing.
- Apply `safe-*` utilities to `ChatShell` top/bottom and Profile sticky bars.
- Momentum-scroll on message list + profile main.
- Disable text selection on chrome (headers/tabs) with `select-none`; keep messages selectable.
- Confirm HashRouter path already handled — no route changes.

### Phase 7 — QA & verification

- `npm run lint` clean, `tsgo` clean, `npm test` green (update snapshots for renamed components).
- Playwright smoke: open `/chat`, send message, open sidebar, open sources, toggle theme; open `/profile`, switch tabs, edit name, open memory manager.
- Visual pass at 375×812 (iPhone), 390×844, 768 (tablet), 1280, 1920. Screenshot each.
- Contrast check on both themes for new tokens.

### Phase 8 — Docs

- Update `handoff.md` with what shipped + follow-ups (icon set, richer markdown code blocks, PWA install banner if desired).

---

## Technical notes

**File splits (target sizes ≤ 300 LoC each)**

```
src/components/chat/
  ChatShell.tsx
  ChatEmptyState.tsx
  message/
    AssistantMessage.tsx
    UserMessage.tsx
    MessageMarkdown.tsx
    MessageActions.tsx
    SourcesInline.tsx
    ThinkingIndicator.tsx
  composer/
    Composer.tsx
    ComposerActions.tsx
    AttachmentButton.tsx
    MicButton.tsx
    SendButton.tsx
src/components/profile/
  ProfileHero.tsx
  ProfileTabs.tsx
  cards/
    AccountCard.tsx
    PreferencesCard.tsx
    MeditationStatsCard.tsx
    MemoryCard.tsx
    LanguageCard.tsx
    NotificationsCard.tsx
    DataCard.tsx
    DangerZoneCard.tsx
```

**Token additions (illustrative — final HSL tuned to Golden Hour)**

```css
:root {
  --chat-surface: var(--background);
  --chat-user-bubble: 36 40% 94%;       /* warm sand */
  --chat-user-foreground: 24 20% 15%;
  --hairline: 30 10% 88%;
  --divider: 30 8% 92%;
  --radius-bubble: 1.25rem;
  --radius-card: 1rem;
  --dur-base: 200ms;
  --ease-standard: cubic-bezier(.2,.8,.2,1);
}
.dark { --chat-user-bubble: 30 12% 18%; --chat-user-foreground: 40 20% 92%; --hairline: 30 6% 22%; --divider: 30 6% 18%; }
```

**Safe-area utility**

```css
@layer utilities {
  .safe-top    { padding-top: max(env(safe-area-inset-top), 0.5rem); }
  .safe-bottom { padding-bottom: max(env(safe-area-inset-bottom), 0.5rem); }
  .momentum-scroll { -webkit-overflow-scrolling: touch; overscroll-behavior: contain; }
}
```

**Behavior invariants preserved**

- ChatInterface state machine, telemetry, tour triggers, PrePracticeGate, multi-device continue prompt, keyboard shortcuts, voice input, i18n.
- Profile persistence via `profileStorage` + Supabase sync.
- Admin/guru memory rules untouched.

---

## Risks & mitigations

- **Mega-file refactors can regress state.** Mitigation: split *behind* current props; move logic into hooks (`useChatController`, `useProfileTabs`) then swap presentational shells last. Ship phases 1→7 as separate commits so a bisect is trivial.
- **Guru photo in header memory rule.** I'll re-verify before removing; default is to keep it, just smaller.
- **Snapshot tests** will need updates for renamed files — expected, low risk.

## Deliverable order (each independently shippable) -> ship all at once using subagents and /token-optimization skill and /ponytail skill

1. Tokens + utilities (Phase 1)
2. Chat message + list redesign (Phase 2)
3. Chat header + sidebar + composer (Phases 3, 2 composer)
4. Empty state (Phase 4)
5. Profile page (Phase 5)
6. Native polish sweep (Phase 6)
7. QA + handoff update (Phases 7-8)