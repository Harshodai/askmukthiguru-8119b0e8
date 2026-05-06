
# Plan: Chat UI/UX Overhaul + Daily Teaching Admin + Tests

## Scope

Six concrete deliverables, all localStorage-based, no external services needed.

---

### 1. Fix Sidebar UI/UX (Expanded + Collapsed)

**Problem:** Header redundancy -- sidebar shows guru photo + brand AND ChatHeader shows guru photo + guru names + Home button + sidebar toggle. Both have Home links.

**Fix:**
- Remove the guru photo from the sidebar header. Keep only the brand text "AskMukthiGuru" when expanded, and a small "M" brand icon when collapsed.
- Remove the "Back to Home" footer link from the sidebar (ChatHeader already has a Home button).
- Remove the desktop `onToggleSidebar` PanelLeft button from ChatHeader -- the sidebar's own chevron toggle is sufficient and always visible.
- Add an AlertDialog confirmation before deleting a conversation in both expanded (trash icon) and collapsed (dropdown menu) modes.

**Files:** `DesktopSidebar.tsx`, `ChatHeader.tsx`

### 2. Daily Teaching: Admin Upload + User Display with TTL

**Current state:** `DailyTeaching.tsx` reads from localStorage but no admin UI exists to set it.

**Fix:**
- Create a new admin page `DailyTeachingPage.tsx` at `/admin/daily-teaching` with:
  - A file input to upload a photo (converted to base64 data URL and stored in localStorage)
  - A caption text field
  - A "Publish" button that calls `setDailyTeaching()` with today's ISO date
  - A preview of the current teaching
- Add the route to `App.tsx` and nav item to `AdminShell.tsx`
- Update `DailyTeaching.tsx` to add 24-hour TTL: compare the teaching's `date` field against today's date; if older than 1 day, treat it as expired and don't show it
- Update `ChatPage.tsx` flow: the DailyTeaching banner appears inside `ChatInterface` AFTER the PrePracticeGate is dismissed (this already works correctly since PrePracticeGate wraps ChatInterface and the teaching is inside ChatInterface's message area)

**Files:** New `src/admin/pages/DailyTeachingPage.tsx`, edit `App.tsx`, `AdminShell.tsx`, `DailyTeaching.tsx`

### 3. Light Mode Verification and Fixes

- Test in browser by toggling to light mode
- Fix any contrast issues found in sidebar, message bubbles, glass-card backgrounds, and input area
- Both light and dark tokens already exist in `index.css` -- this is about verifying they render correctly

**Files:** Potentially `index.css` if issues found

### 4. Conversation Deletion with Confirmation

- Add `AlertDialog` (already available from shadcn) to `DesktopSidebar.tsx`
- In expanded mode: clicking trash opens confirmation dialog
- In collapsed mode: clicking "Delete" in dropdown opens confirmation dialog
- After confirmed deletion of active conversation: create new conversation and select it (existing `onDeleteConversation` callback already handles this)

**Files:** `DesktopSidebar.tsx`

### 5. Expand Vitest Tests

- `DesktopSidebar.test.tsx`: Add tests for delete confirmation dialog (renders, confirm deletes, cancel keeps)
- `ChatMessage.test.tsx`: Add tests for feedback flow (thumbs up sets state, tag selection, submit calls saveFeedback)
- `DailyTeaching.test.tsx`: Add tests for TTL expiry (teaching older than 1 day not shown)

**Files:** `src/test/DesktopSidebar.test.tsx`, `src/test/ChatMessage.test.tsx`, `src/test/DailyTeaching.test.tsx`

### 6. Security Scan

- Current scan shows zero findings. Will re-run after changes to confirm no new issues.

---

## What is NOT in this plan (and why)

- **Database persistence**: Not enabled. Everything stays in localStorage as specified.
- **Backend Python auth testing**: Runs outside Lovable sandbox, cannot be tested here.
- **Playwright E2E tests**: Not available in Lovable. Using Vitest + React Testing Library.
- **Sidebar redesign from scratch**: Not needed. Fixing specific issues only.

## File Change Summary

| File | Action |
|------|--------|
| `src/components/chat/DesktopSidebar.tsx` | Remove guru photo header, remove Home footer, add AlertDialog delete confirmation |
| `src/components/chat/ChatHeader.tsx` | Remove desktop sidebar toggle button |
| `src/components/chat/DailyTeaching.tsx` | Add 24-hour TTL check |
| `src/admin/pages/DailyTeachingPage.tsx` | **New** -- admin upload UI for daily teaching photo + caption |
| `src/admin/layout/AdminShell.tsx` | Add Daily Teaching nav item |
| `src/App.tsx` | Add `/admin/daily-teaching` route |
| `src/test/DesktopSidebar.test.tsx` | Add delete confirmation tests |
| `src/test/ChatMessage.test.tsx` | Add feedback flow tests |
| `src/test/DailyTeaching.test.tsx` | Add TTL expiry tests |
