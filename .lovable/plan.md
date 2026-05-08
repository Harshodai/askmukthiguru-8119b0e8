
# Combined Plan: Final Production-Ready Overhaul

## Phase A: Fix Runtime Crash
**File:** `src/App.tsx`
Move `Toaster`/`Sonner` inside `BrowserRouter` to fix `useLocation() outside Router` error.

## Phase B: Streaming Fixes (Critical)
**File:** `src/lib/aiService.ts`
1. Unescape `\\n` → `\n` in token chunks (backend escapes for SSE transport)
2. Add `done` StreamChunk type, handle `event: done` SSE (carries intent, citations, meditationStep)
3. Handle `event: error` SSE

**File:** `src/components/chat/ChatInterface.tsx`
4. Process `done` chunk: set citations on guru message, trigger Serene Mind if `intent === 'DISTRESS'`, update meditationStep
5. Remove `citations.slice(0, 3)` limit — show all sources
6. Pass sidebar toggle props to ChatHeader

## Phase C: Response Beautification
**File:** `src/components/chat/ChatMessage.tsx`
1. Remove `citations.slice(0, 3)` limit
2. Extract inline YouTube URLs from response text as fallback citations when citations array is empty
3. Verify prose/markdown styling for lists, headers, bold

## Phase D: Sidebar Toggle Visibility
**File:** `src/components/chat/ChatHeader.tsx`
Add `PanelLeft` toggle button in header — always visible, primary control for sidebar.

## Phase E: Thinking UI Polish
**File:** `src/components/chat/ThinkingPills.tsx`
Wrap in glassmorphism container with "Guru is contemplating..." header, `pointer-events-none`.

## Phase F: Auth-Gated Chat + Google OAuth
1. **New file:** `src/hooks/useRequireAuth.ts` — session guard, redirects to `/auth`
2. **File:** `src/pages/ChatPage.tsx` — wrap with auth guard
3. **File:** `src/pages/AuthPage.tsx` — detailed error messages, Google OAuth already wired via `lovable.auth.signInWithOAuth('google')`, add `onAuthStateChange` listener for post-OAuth redirect to `/chat`
4. **File:** `src/App.tsx` — add global auth state listener for session tracking

## Phase G: Admin Cleanup
1. **File:** `src/admin/pages/AdminLoginPage.tsx` — remove `admin/admin` defaults and DEV MODE badge
2. **File:** `src/admin/layout/AdminTopbar.tsx` — add "Role Verified" badge

## Phase H: Tests
Update existing tests for new StreamChunk types and ThinkingPills container.
