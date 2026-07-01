# Ruthless Finish Sprint — P2 → P4

Continuing from P1 (already shipped: hero padding, avatar contrast, scroll-margin, cookie banner compact). Confidence today: **7.5/10**. Target after this sprint: **9.5/10**.

## Scope (what you asked for)

1. Footer + dvh audit — no layout jump, nothing hidden below fold on mobile Safari.
2. Tablet (768–1024) polish — hero, cookie banner, chat header.
3. Consistent typography scale — landing / chat / footer, verified contrast + line-height.
4. Axe a11y sweep — fix every P0/P1 on landing + chat.
5. Reaudit remaining items from `.lovable/plan.md`.
6. **AI Elements migration** of the chat surface (Conversation, Message, MessageResponse, PromptInput, Tool, Shimmer).
7. Empty / loading / streaming states consistent on 384 / 820 / 1440.

## Plan

### Sprint A — Layout & dvh (fast, safe)
- Replace remaining `h-screen` / `min-h-screen` with `h-dvh` / `min-h-dvh` project-wide (rg sweep).
- Footer: verify it renders on all pages; if Index page's `min-h-dvh` + sticky hero pushes footer off, wrap in a flex column so footer sits at document end without jumping when mobile URL bar collapses.
- Add `pb-[env(safe-area-inset-bottom)]` where fixed bottom elements exist (composer, cookie banner).

### Sprint B — Tablet (768–1024)
- Hero: bump `max-w-*` scale (`md:max-w-3xl lg:max-w-5xl` already partially there — verify Meet the Gurus, Practices, How It Works).
- Cookie banner: at `md+`, keep bottom-left toast width capped at `max-w-md` so it doesn't span full width.
- Chat header: verify avatar + title + language selector + user menu don't wrap or truncate at 820. Add responsive gap/hide-label rules.

### Sprint C — Typography system
- Define scale in `tailwind.config.ts` + `index.css`:
  - Display (H1 hero): typewriter, 3xl→7xl
  - Heading (H2 section): typewriter, 2xl→5xl
  - Subheading (H3): sans, xl→2xl semibold
  - Body: sans, base, `leading-relaxed`
  - Caption/eyebrow: sans, xs uppercase tracking-widest
- Sweep landing components + Footer + Chat: replace ad-hoc `text-*` chains with the scale.
- Body copy currently monospace → switch `.prose` and long `<p>` to paired sans (already loaded).

### Sprint D — Accessibility (axe P0/P1)
- Alt text sweep (hero lotus, guru images, decorative → `alt=""`).
- Icon-only buttons → `aria-label` (hamburger, close, fav star, scroll-to-bottom fab, mic).
- Fav star → `aria-pressed`.
- Focus-visible rings on all interactive elements (already global? verify).
- Single `<main>` per route.
- Verify contrast tokens (muted-foreground/50 → muted-foreground) in disclaimer, timestamps, chat meta.
- Color-not-alone: error states get icon + text.
- `lang="en"` on `<html>`.
- React Router v7 future flags to silence console noise.

### Sprint E — AI Elements chat migration
- `bun x ai-elements@latest add conversation message prompt-input shimmer tool`
- Rewrite `ChatInterface` to compose `Conversation` / `ConversationContent` / `ConversationScrollButton`.
- `ChatMessage` → `Message` + `MessageContent` + `MessageResponse` (markdown streaming).
- Composer → `PromptInput` + `PromptInputTextarea` + `PromptInputFooter` (submit right-aligned, mic + language chips in footer).
- Thinking indicator → `Shimmer` ("Reflecting…").
- Assistant messages: NO background bubble (per contract). User bubble: `bg-primary text-primary-foreground`.
- Empty state: guru portrait + suggested prompts (no Sparkles icon).
- Verify streaming, error, and loading render identically at 384 / 820 / 1440 via Playwright.

### Sprint F — Reaudit
- Rerun Playwright at 3 viewports on `/`, `/chat` (with injected session), `/practices`, `/profile`.
- Cross-check `.lovable/plan.md` items 1–12; close resolved, log remainder.
- Run axe via Playwright, list residual violations (accept only AAA-tier or design-decision).

## Deliverables
- Updated `.lovable/plan.md` with post-sprint scores per surface.
- Before/after screenshots checked into `/tmp/browser/` for the audit trail.
- Final confidence score with justification.

## Risks / Notes
- AI Elements migration touches many chat files. I will preserve message persistence, streaming transport (`sendMessageStreaming`), and existing hooks — only the presentational layer changes.
- Existing custom ChatMessage has domain-specific features (regenerate, edit-in-place, quick actions, TTS, wisdom card). These stay as message actions on top of `MessageResponse`.
- Tests: run vitest + typecheck after each sprint.

**Approve to execute all six sprints in order.** ETA ~45–60 min of tool time.
