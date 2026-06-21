# Plan: Chat Ruthless Audit + Consistency + Two New Features

Scope: complete the pending Lovable-side work, do a thorough audit of the chat section, fix every UX issue found, enforce visual consistency across the app, and add two new capabilities (Sub-Modules / Custom Assistants, Notes). Backend (Python/FastAPI) is out of scope — work stays in the Lovable frontend + Supabase (Lovable Cloud) edge functions/tables.

---

## Part A — Chat Audit (findings to fix)

Audit targets: `ChatInterface`, `ChatHeader`, `ChatMessage`, `MessageList`, `ChatEmptyState`, `ThinkingPills`, `DesktopSidebar`, `MobileConversationSheet`, `ScrollToBottomFab`, `SereneMindModal`, `SlashCommandMenu`, composer, and the empty/resume hero.

Issues to fix:

1. Spacing inconsistency between user vs assistant turns; assistant max-width changes between viewports.
2. Sample question pills still misaligned on mobile (overflow, uneven row heights, weak tap targets).
3. "Continue where you left off" card under-uses horizontal space and visually disconnects from the transcript.
4. Composer: textarea height jitter, submit button stretches, attach/voice icons not aligned, focus ring inconsistent with tokens.
5. Mobile (384px) header crowding — guru avatar + title + actions wrap awkwardly.
6. Sidebar collapse animation flickers; floating reopen toggle z-index conflicts with FAB.
7. Scroll behavior: jumps on streamed token append; resume anchor sometimes off by one due to image/avatar layout shift.
8. Color/contrast drift — a handful of `text-white`, `bg-black/40` literals still present; must move to semantic tokens.
9. Markdown rendering: lists tight, code blocks no horizontal scroll on mobile, links no hover state.
10. Error banner stacks with toast — dedupe into a single inline retry affordance.
11. Keyboard a11y: pill grid not arrow-navigable; composer Enter/Shift+Enter inconsistent across browsers.
12. Tablet (768–1024): wasted whitespace on right rail; messages should expand to `max-w-[78ch]`.

Fix strategy: rebuild chat surface on AI Elements primitives (`Conversation`, `Message`, `MessageContent`, `MessageResponse`, `PromptInput`, `Shimmer`) per the chat-ui-composition rules, keep our streaming + resume + telemetry logic intact, and replace bespoke bubbles with tokenized variants.

---

## Part B — Visual Consistency Pass

- Single source of truth: extend `src/index.css` Golden Hour tokens (`--surface`, `--surface-elev`, `--chat-user`, `--chat-user-foreground`, `--accent-gold`, `--ring-gold`).
- Remove every hardcoded color in chat + landing + profile + admin shell; replace with tokens.
- Standardize spacing scale (4 / 8 / 12 / 16 / 24 / 32) and radii (`--radius-sm/md/lg`).
- Typography: lock display + body pair; one H1 per route; consistent prose styles.
- Responsive rules: mobile `< 640`, tablet `640–1024`, desktop `> 1024` — verified on header, sidebar, chat, profile, practices, landing.
- Motion: unify framer-motion easings/durations in a `motion.ts` preset.

---

## Part C — Feature 1: Sub-Modules / Custom Assistants

Decision: **Yes, ship it** — adds clear value (focused, gated experiences distinct from general guidance) and is the natural home for SKY / unreleased private teachings + relationship guidance.

Shape:

- **Assistants** = curated personas with their own system prompt, allowed knowledge sources, intro, and starter prompts.
- Built-in: `General Guru` (default), `Relationship Guidance`, `SKY Teachings (Private)`.
- **Access tiers**:
  - Public: General + Relationship.
  - Link-gated: private assistants joined via invite link/code (e.g. `/join/sky-...`). Stored in `assistant_access` table per user.
  - Custom: users with `creator` role can author their own assistant (name, avatar, system prompt, starter questions, optional knowledge filter).
- UI: assistant switcher in `ChatHeader` (pill dropdown showing avatar + name); selected assistant is persisted per conversation. Empty state + sample questions adapt to the active assistant.
- Knowledge scoping: assistant carries an optional `knowledge_tag` array; passed to chat API so backend can filter retrieval (frontend contract only — backend filter is additive, out of scope here).

Tables (Lovable Cloud):

- `assistants(id, slug, name, description, avatar_url, system_prompt, starter_questions jsonb, knowledge_tags text[], visibility enum public|link|private, created_by, created_at)`
- `assistant_access(user_id, assistant_id, granted_via text, created_at)` — RLS: user reads own rows; service_role writes via edge function on invite redemption.
- `conversations.assistant_id` (new nullable FK).
- Edge function `redeem-assistant-invite` validates code and grants access.

---

## Part D — Feature 2: Notes

Value: lets users keep teachings/insights they resonated with; exportable from any chat response or written freely. Lives under Profile.

Shape:

- "Save as note" action on every assistant message (bookmark icon next to copy).
- "New note" composer in Profile → Notes tab (title, body markdown, tags, source link to original message if any).
- List view with search, tag filter, sort by recent/favorite.
- Export: copy-to-clipboard, download `.md`, share image (reuse `WisdomCardGenerator`).
- Bulk export all notes as `.zip` of markdown.

Table: `notes(id, user_id, title, body, tags text[], source_message_id, source_conversation_id, is_favorite, created_at, updated_at)` with RLS scoped to `auth.uid()`, full GRANT block, `updated_at` trigger.

Routes:

- `/profile/notes` (list)
- `/profile/notes/:id` (detail/edit)

---

## Part E — Execution Order

1. Audit fixes 1–12 + AI Elements migration of chat surface.
2. Token + consistency sweep across app.
3. Notes feature (tables → API hook → Profile UI → message action).
4. Assistants feature (tables → switcher → empty state per assistant → invite redemption edge function).
5. Tests: extend Vitest for `MessageList`, `ChatHeader` switcher, `useNotes`, resume anchor; Playwright smoke at 390 / 820 / 1440.
6. Final pass: a11y, contrast, mobile.

---

## Out of Scope

- Backend retrieval changes (knowledge_tag filtering is wired in payload only). I need what needs to be done in backend via an docs .md so that I can refer that and get that implemented and also make sure nothing breaks
- Voice/TTS changes.
- Real-time collaboration on notes.

Approve to start with Part A + B immediately; Parts C & D follow in the same session.