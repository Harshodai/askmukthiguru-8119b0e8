
# Complete Overhaul Plan

## 1. Sidebar — Fully Hidden with Toggle Button

**Files**: `DesktopSidebar.tsx`, `ChatInterface.tsx`

- Collapsed state becomes **fully hidden** (width 0, off-screen)
- A floating toggle button (small pill with chevron icon) stays visible at the left edge of the chat area
- Expanded state remains 280px with current design
- Smooth Framer Motion animation for open/close
- Mobile bottom sheet behavior unchanged

## 2. Guru Photos in Chat Header

**File**: `ChatHeader.tsx`

- Add a 28px circular image using `src/assets/gurus-photo.jpg` next to the title
- Add subtle subtitle "Guided by Sri Preethaji & Sri Krishnaji" (10px, muted, hidden on mobile)
- Layout: `[Home] [☰mobile] [guru-photo] AskMukthiGuru [subtitle] ... [wifi] [UserMenu]`

## 3. Admin Panel Security Fix

### 3a. Delete `src/admin/lib/supabaseClient.ts`
Broken — points to `127.0.0.1:54321` with demo key.

### 3b. Update `src/admin/lib/mockData.ts`
Import from `@/integrations/supabase/client` instead of `./supabaseClient`.

### 3c. Rewrite `src/admin/lib/adminAuth.ts`
- Import from `@/integrations/supabase/client`
- New `verifyAdminSession()` — async, checks real Supabase JWT + `has_role` RPC
- localStorage only caches display info, never used for auth decisions

### 3d. Rewrite `src/admin/hooks/useAdminGuard.ts`
- Async `verifyAdminSession()` replaces sync `isAdminAuthenticated()`

### 3e. Add `created_by` to daily teaching insert
In `DailyTeachingPage.tsx`, get user ID from `supabase.auth.getSession()` and include in insert.

## 4. Chat Message Database Persistence

### 4a. Database migration
```sql
CREATE TABLE conversations (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid NOT NULL,
  title text,
  preview text,
  created_at timestamptz DEFAULT now(),
  updated_at timestamptz DEFAULT now()
);

CREATE TABLE chat_messages (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  conversation_id uuid REFERENCES conversations(id) ON DELETE CASCADE NOT NULL,
  role text NOT NULL CHECK (role IN ('user', 'guru')),
  content text NOT NULL,
  citations text[],
  confidence_score float,
  created_at timestamptz DEFAULT now()
);

ALTER TABLE conversations ENABLE ROW LEVEL SECURITY;
ALTER TABLE chat_messages ENABLE ROW LEVEL SECURITY;

CREATE POLICY "own_conversations" ON conversations
  FOR ALL TO authenticated
  USING (user_id = auth.uid()) WITH CHECK (user_id = auth.uid());

CREATE POLICY "own_messages" ON chat_messages
  FOR ALL TO authenticated
  USING (conversation_id IN (SELECT id FROM conversations WHERE user_id = auth.uid()));
```

### 4b. Create `src/lib/chatPersistence.ts`
DB-backed CRUD:
- `loadConversationsFromDb()` — user's conversations
- `saveMessageToDb(conversationId, message)` — insert message
- `createConversationInDb(firstMessage)` — create + first message
- `deleteConversationFromDb(id)` — delete

### 4c. Update `ChatInterface.tsx` and `DesktopSidebar.tsx`
- Authenticated users: load/save from DB, sync across devices
- Anonymous users: localStorage fallback (existing behavior)

## 5. Meditation DB Persistence

**File**: `src/lib/meditationStorage.ts`

Add DB-backed variants:
- `completeMeditationSession()` updated to write to `meditation_sessions` table when authenticated
- `loadMeditationSessionsFromDb()` / `getMeditationStatsFromDb()`
- `GuidedMeditationFlow.tsx` and `SereneMindModal.tsx` — no changes needed (they call `completeMeditationSession` which will auto-persist)

## 6. Backend URL Auto-Detection via Env Var

**File**: `src/lib/aiService.ts`

- Read `VITE_BACKEND_URL` env var
- Default: relative `/api/chat` (works behind a proxy in production)
- Local dev: set `VITE_BACKEND_URL=http://localhost:8000` in `.env.local`
- Update `currentConfig.endpoint` to use this

```typescript
const BACKEND_URL = import.meta.env.VITE_BACKEND_URL || '';
let currentConfig: AIConfig = {
  provider: 'custom',
  endpoint: `${BACKEND_URL}/api/chat`,
  ...
};
```

## 7. ThinkingPills + SSE Tests

### 7a. `src/test/ThinkingPills.test.tsx`
- Renders pills with correct labels for active/done/pending
- `visible=false` renders nothing
- `mapStatusToLabel()` maps all known backend statuses correctly
- Unknown statuses: trailing `...` stripped as fallback

### 7b. `src/test/aiServiceStreaming.test.ts`
- SSE parsing of `event: status` lines
- All 6 status mappings verified
- `[DONE]` signal stops the generator

## 8. Streaming Fallback Toast

**File**: `ChatInterface.tsx`

Add toast in the streaming catch block when partial content was received:
```typescript
catch (err) {
  if (fullContent) {
    toast({ title: 'Connection interrupted', description: 'Response may be incomplete.' });
  }
}
```

## 9. Add Admin User

**Email**: kharshaengineer@gmail.com

You haven't signed up yet — the account doesn't exist in the database. After I implement the changes:
1. Sign up at `/auth` with kharshaengineer@gmail.com
2. I'll then insert your user ID into `user_roles` with `role = 'admin'`

## 10. Setup Documentation

**File**: Create `SETUP.md` in project root

Complete setup guide covering:

### Local Development
- Prerequisites (Node 18+, Python 3.11+, Docker)
- Frontend: `bun install && bun run dev` (port 8080)
- Backend: `cd backend && docker compose up -d` (Qdrant + FastAPI on port 8000)
- Ollama: `ollama serve` on host + `setup_sarvam.sh`
- `.env.local`: `VITE_BACKEND_URL=http://localhost:8000`
- Lovable Cloud (Supabase) local: env vars are auto-injected by Lovable; for standalone local dev, copy `VITE_SUPABASE_URL` and `VITE_SUPABASE_PUBLISHABLE_KEY` from Lovable Cloud settings

### Production Deployment
- Frontend: Lovable auto-deploys on publish
- Backend: Deploy FastAPI to your server/cloud (Docker compose)
- Set `VITE_BACKEND_URL` to your production FastAPI URL
- Lovable Cloud (database, auth, storage) is automatically provisioned
- Edge functions auto-deploy

### Database Tables Reference
- `profiles` — auto-created on signup via trigger
- `user_roles` — admin role management (manual insert)
- `daily_teachings` — 24h TTL teachings with image storage
- `meditation_sessions` — per-user meditation tracking
- `conversations` — chat conversation metadata (new)
- `chat_messages` — individual chat messages (new)

### Manual Steps Checklist
- Sign up and get admin role assigned
- (Optional) Configure Google OAuth credentials in Cloud settings
- (Optional) Set `VITE_BACKEND_URL` for local dev

---

## Files Summary

| File | Action |
|------|--------|
| `src/components/chat/DesktopSidebar.tsx` | Fully hidden collapse + toggle |
| `src/components/chat/ChatHeader.tsx` | Guru photo + subtitle |
| `src/components/chat/ChatInterface.tsx` | DB persistence + fallback toast |
| `src/admin/lib/supabaseClient.ts` | **Delete** |
| `src/admin/lib/mockData.ts` | Fix import |
| `src/admin/lib/adminAuth.ts` | Rewrite — JWT auth |
| `src/admin/hooks/useAdminGuard.ts` | Async verification |
| `src/admin/pages/DailyTeachingPage.tsx` | Add `created_by` |
| `src/lib/aiService.ts` | `VITE_BACKEND_URL` env var |
| `src/lib/chatPersistence.ts` | **New** — DB chat CRUD |
| `src/lib/meditationStorage.ts` | Add DB persistence |
| `src/test/ThinkingPills.test.tsx` | **New** |
| `src/test/aiServiceStreaming.test.ts` | **New** |
| `SETUP.md` | **New** — full setup docs |
| Migration SQL | `conversations` + `chat_messages` tables |
