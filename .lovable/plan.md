## Goal
Make chat errors actionable and visible globally, surface auth status in the header, enable one-tap retry of the last prompt, and fix alignment of starter-question chips so they line up cleanly with the message column.

## 1. Global error banner + toast (new: `src/components/chat/ChatErrorBanner.tsx`, `src/lib/chatErrorBus.ts`)

- Add a tiny pub/sub store (`chatErrorBus`) so any layer (streaming loop, auth listener, memory API) can publish a `ChatError { kind, title, summary, detail, messageId?, retryable }`.
- `ChatErrorBanner` mounts inside `ChatInterface` just under `ChatHeader`. Sticky, dismissible, single active banner at a time, dedupes within 5s (reuse existing toast dedupe rule).
- Banner shows: icon + 1-line summary + "Details" (scrolls to/opens the message's error card) + "Retry" + "Dismiss".
- Also fires a sonner `toast.error` for transient confirmation; toast has the same "Details" action that calls `chatErrorBus.focus(messageId)`.
- `ChatMessage` subscribes via a `data-error-id` attribute; "Details" sets focus + expands the existing `<details>` "Technical detail" disclosure already wired in the last pass.

## 2. Auth status indicator in `ChatHeader`

- Add `useAuthStatus()` hook (wraps `supabase.auth.getSession` + `onAuthStateChange`) returning `signed_in | session_expired | anonymous`.
- Header pill (next to the Memory pill):
  - Green dot · "Signed in" (shows email on hover)
  - Amber dot · "Session expired" → button "Sign in again" → `navigate('/auth?redirect=/chat')`
  - Grey dot · "Guest" → "Sign in" link
- On `TOKEN_REFRESHED` failure or 401 from `/api/chat`, flip to `session_expired` and publish a banner via `chatErrorBus`.

## 3. One-tap "Retry last message"

- `ChatInterface` already tracks messages; add `retryLastUserMessage()`:
  1. Find last `role==='user'` message.
  2. Truncate any failed guru message after it.
  3. Re-run the existing send pipeline with the same text + thread context.
- Surface the action in three places, all calling the same handler:
  - Banner "Retry" button.
  - Per-message error card "Retry" (already present — rewire to this).
  - Floating "↻ Retry last message" pill above composer when the latest guru bubble has `message.error` and user is idle.
- Disable while `streaming`.

## 4. Friendly error-code panel (new: `src/components/chat/ErrorCodePanel.tsx`)

- Maps `MessageErrorKind` → `{ code, title, cause, nextStep, docsHref? }`:
  - `unauthorized` → AUTH_401 · "Your session expired" · "Sign in again to continue. Your draft is saved."
  - `rate_limited` → RATE_429 · "Too many requests" · "Wait ~30s, then retry. Upgrade plan for higher limits."
  - `server_error` → MODEL_5XX · "Model unavailable" · "Backend is recovering. Retry in a moment; we'll fall back to offline guidance."
  - `network` → NET_OFFLINE · "Can't reach the guru service" · "Check your connection, then Retry."
  - `timeout` → TIME_OUT · "Response took too long" · "Retry — long answers may need a second attempt."
  - `unknown` → UNK · "Something went off-path" · "Retry; if it persists, share the technical detail with support."
- Rendered inside the per-message error card AND as the expanded content when the banner's "Details" is clicked.
- Includes copy-trace button (`request_id` + last error message) for support.

## 5. Starter questions alignment

In `ChatInterface` / empty-state block currently rendering the suggested prompts:

- Wrap chips in the same max-width column as `MessageList` (use a shared `chat-column` class: `max-w-3xl mx-auto px-4 sm:px-6`).
- Switch from left-ragged flex-wrap to `grid grid-cols-1 sm:grid-cols-2 gap-2` with `items-stretch`, so chips have equal height and align to the message column edges.
- Center the empty-state heading + chips block vertically only when there are no messages; once messages exist, never render chips below them (current bug: misaligned because chips sit outside the column).
- Constrain chip text to 2 lines with `line-clamp-2`, consistent `text-sm font-serif`, `rounded-2xl border border-ojas/20 bg-ojas/5 hover:bg-ojas/10`.

## 6. Files touched

- New: `src/components/chat/ChatErrorBanner.tsx`, `src/components/chat/ErrorCodePanel.tsx`, `src/lib/chatErrorBus.ts`, `src/hooks/useAuthStatus.ts`, `src/hooks/useRetryLastMessage.ts`.
- Edited: `src/components/chat/ChatInterface.tsx`, `src/components/chat/ChatHeader.tsx`, `src/components/chat/ChatMessage.tsx`, `src/components/chat/MessageList.tsx` (chat-column class), `src/lib/chatStorage.ts` (no schema change; reuse `MessageError`).

## 7. Validation

- Manual: kill backend → banner + toast + retry pill all appear; click Retry → re-sends. Expire token (delete from storage) → header flips to "Session expired", banner offers "Sign in again". Send a prompt while offline → error card shows NET_OFFLINE panel with next step.
- Tests: extend `aiServiceStreaming.test.ts` for 401 → `unauthorized` mapping; new `useRetryLastMessage.test.ts`; snapshot `ErrorCodePanel` for each kind.
- Visual: empty-state chips align flush with first message bubble's left/right edges at 384px, 768px, 1280px viewports.

## Out of scope

- No backend changes (error codes are mapped client-side from HTTP status + existing error payload).
- No new auth providers; reuses existing Google + email flow.
- No design tokens added — uses existing Golden Hour palette.
