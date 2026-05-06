
# AskMukthiGuru — Complete Overhaul Plan

## Critical Corrections from Previous Plan

| Claim | Reality |
|-------|---------|
| Facebook sign-in | **Not supported** by Lovable Cloud. Dropped. Using Google + Email/Password. |
| Lovable Cloud connected | **Not connected**. Must enable first. `supabaseClient.ts` points to local Docker (`127.0.0.1:54321`). |
| Backend changes needed for thinking UI | **Not needed**. Backend already emits SSE `event: status` with pipeline stages. Frontend just ignores them. |
| Daily teaching "not reflecting" | Root cause: localStorage is browser-local. Admin publishes in their browser, other users never see it. Must use database. |

---

## 1. Chat UI Overhaul — Anthropic/Claude Style

### 1a. Inline Thinking Pills (Smart Adaptive)

The backend already streams these SSE status events before the answer:
- `"Checking message safety..."` (Layer 1: guardrails)
- `"Understanding your question..."` (Layer 2-3: intent + decompose)
- `"Searching knowledge base..."` (Layer 4-6: retrieve + rerank + grade)
- `"Composing response..."` (Layer 8-9: generate)

**Frontend implementation**:
- Parse `event: status` SSE lines in `sendMessageStreaming()` in `aiService.ts`
- Pass status updates via a new callback or yield a special marker (e.g. `{type: 'status', text: '...'}`)
- In `ChatInterface.tsx`, show animated pills above the typing indicator:

```
┌─────────────────────────────────────────────┐
│  ✓ Safety check  ✓ Understanding  ⟳ Searching...  │
└─────────────────────────────────────────────┘
```

- Each pill: appears with fade-in, shows a spinner while active, gets a checkmark when the next status arrives
- All pills fade out once the first `event: token` arrives (answer starts streaming)
- For CASUAL intent (simple queries): backend emits fewer status events, so fewer pills appear naturally — **smart adaptive with zero extra logic**

**Files**: `aiService.ts`, `ChatInterface.tsx`, new `ThinkingPills.tsx` component

### 1b. Chat Header Cleanup

Current problems:
- Guru photo in header AND sidebar = redundant
- "New chat" button in header AND sidebar = redundant
- Header takes too much vertical space

Changes to `ChatHeader.tsx`:
- Remove guru photo from header
- Remove "New chat" button (sidebar has one)
- Keep: Home icon | "AskMukthiGuru" text + connection status | User menu
- Result: slim single-row header (~44px)

### 1c. Message Styling Refinement

Changes to `ChatMessage.tsx`:
- Guru messages: remove glass-card bubble, use clean left-aligned text with a subtle golden left border (like Claude)
- User messages: right-aligned with a warm solid background pill
- Tighter vertical spacing between messages
- Render guru responses with `react-markdown` for proper formatting

### 1d. Input Area Polish

Changes to `ChatInterface.tsx` footer:
- Move "Serene Mind" and "Guided Meditation" chips into the input container as subtle icon buttons (not separate row)
- Single rounded pill input with send button — cleaner, more spacious
- Language selector stays in secondary row but more compact

---

## 2. Sidebar Fixes (Dark + Light Mode)

### 2a. Collapsed Mode

Changes to `DesktopSidebar.tsx`:
- Increase collapsed width from 64px to 72px
- Add `p-2` padding to action buttons in collapsed mode (currently cramped)
- Ensure the collapse chevron toggle doesn't overlap with icon buttons

### 2b. Light Mode

Changes to `index.css`:
- Verify glass-card background has sufficient contrast in light mode
- Ensure sidebar bg, message bubbles, and input area have proper light-mode values
- Fix any low-contrast text

---

## 3. Enable Lovable Cloud + Auth

**Prerequisite**: Enable Lovable Cloud for database and auth.

### 3a. Database Tables (via migrations)

```sql
-- User roles (per security best practices)
CREATE TYPE public.app_role AS ENUM ('admin', 'user');

CREATE TABLE public.user_roles (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE NOT NULL,
  role app_role NOT NULL,
  UNIQUE (user_id, role)
);
ALTER TABLE public.user_roles ENABLE ROW LEVEL SECURITY;

-- Security definer function
CREATE OR REPLACE FUNCTION public.has_role(_user_id UUID, _role app_role)
RETURNS BOOLEAN LANGUAGE SQL STABLE SECURITY DEFINER
SET search_path = public AS $$
  SELECT EXISTS (
    SELECT 1 FROM public.user_roles
    WHERE user_id = _user_id AND role = _role
  )
$$;

-- Profiles
CREATE TABLE public.profiles (
  id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
  display_name TEXT,
  avatar_url TEXT,
  preferred_language TEXT DEFAULT 'en',
  tts_enabled BOOLEAN DEFAULT false,
  created_at TIMESTAMPTZ DEFAULT now()
);
ALTER TABLE public.profiles ENABLE ROW LEVEL SECURITY;
CREATE POLICY "own_profile" ON public.profiles FOR ALL TO authenticated
  USING (id = auth.uid()) WITH CHECK (id = auth.uid());

-- Auto-create profile on signup
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS TRIGGER LANGUAGE plpgsql SECURITY DEFINER AS $$
BEGIN
  INSERT INTO public.profiles (id, display_name, avatar_url)
  VALUES (NEW.id, NEW.raw_user_meta_data->>'full_name', NEW.raw_user_meta_data->>'avatar_url');
  RETURN NEW;
END;
$$;
CREATE TRIGGER on_auth_user_created
  AFTER INSERT ON auth.users
  FOR EACH ROW EXECUTE FUNCTION public.handle_new_user();
```

### 3b. Auth UI

- Create `/auth` page with Email/Password sign-up/sign-in + Google sign-in button
- Use `onAuthStateChange` listener in app root
- Show user avatar in `UserMenu` when signed in
- Redirect to `/chat` after sign-in

### 3c. Google Sign-In Setup (manual steps for you)

1. Go to [Google Cloud Console](https://console.cloud.google.com/) -> APIs & Credentials
2. Create OAuth 2.0 Client ID (Web application type)
3. Add authorized redirect URI: `https://<your-supabase-ref>.supabase.co/auth/v1/callback`
4. In Lovable Cloud -> Users -> Auth Settings -> Enable Google -> Paste Client ID + Secret

### 3d. Backend Auth Documentation

Your FastAPI backend already has JWT auth via `fastapi-users`. To add Google OAuth to the backend:

**Install**: `pip install httpx-oauth`

**Add to `backend/app/config.py`**:
```python
google_client_id: str = ""
google_client_secret: str = ""
```

**Add to `backend/services/auth_service.py`**:
```python
from httpx_oauth.clients.google import GoogleOAuth2

google_oauth_client = GoogleOAuth2(
    client_id=settings.google_client_id,
    client_secret=settings.google_client_secret,
)
```

**Add to `backend/app/api/endpoints/auth.py`**:
```python
from services.auth_service import google_oauth_client, auth_backend, fastapi_users

router.include_router(
    fastapi_users.get_oauth_router(google_oauth_client, auth_backend, settings.jwt_secret),
    prefix="/google",
    tags=["auth"],
)
router.include_router(
    fastapi_users.get_oauth_associate_router(google_oauth_client, UserRead),
    prefix="/google/associate",
    tags=["auth"],
)
```

**Add OAuth account model** in `backend/models/user.py`:
```python
from fastapi_users_db_sqlalchemy.access_token import SQLAlchemyBaseOAuthAccountTableUUID

class OAuthAccount(SQLAlchemyBaseOAuthAccountTableUUID, Base):
    __tablename__ = "oauth_accounts"
```

Then update `UserManager` to include `oauth_account_model = OAuthAccount`.

---

## 4. Daily Teaching — Database-Backed with 24h TTL

### 4a. Database Table

```sql
CREATE TABLE public.daily_teachings (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  image_url TEXT NOT NULL,
  caption TEXT,
  created_at TIMESTAMPTZ DEFAULT now(),
  expires_at TIMESTAMPTZ DEFAULT (now() + interval '24 hours'),
  created_by UUID REFERENCES auth.users(id)
);
ALTER TABLE public.daily_teachings ENABLE ROW LEVEL SECURITY;

CREATE POLICY "anyone_reads_active" ON public.daily_teachings
  FOR SELECT TO authenticated USING (expires_at > now());
CREATE POLICY "admin_manages" ON public.daily_teachings
  FOR ALL TO authenticated
  USING (public.has_role(auth.uid(), 'admin'))
  WITH CHECK (public.has_role(auth.uid(), 'admin'));
```

### 4b. Frontend Changes

- `DailyTeaching.tsx`: Fetch from Supabase instead of localStorage. Query `daily_teachings` where `expires_at > now()`, limit 1.
- `DailyTeachingPage.tsx` (admin): Insert into database. Upload image to Supabase Storage (better than base64 in DB for large images).
- Remove all localStorage TTL logic.

---

## 5. Meditation Session Tracking — Database-Backed

### 5a. Database Table

```sql
CREATE TABLE public.meditation_sessions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE NOT NULL,
  started_at TIMESTAMPTZ NOT NULL,
  completed_at TIMESTAMPTZ,
  duration_seconds INT DEFAULT 0,
  breath_cycles INT DEFAULT 0,
  completed BOOLEAN DEFAULT false
);
ALTER TABLE public.meditation_sessions ENABLE ROW LEVEL SECURITY;
CREATE POLICY "own_sessions" ON public.meditation_sessions
  FOR ALL TO authenticated
  USING (user_id = auth.uid()) WITH CHECK (user_id = auth.uid());
```

### 5b. Frontend Changes

- Update `meditationStorage.ts` to write to Supabase when authenticated, localStorage fallback for anonymous
- `GuidedMeditationFlow.tsx` / `SereneMindModal.tsx`: Save session on completion
- `MeditationStats.tsx`: Fetch from database for authenticated users

---

## 6. Remove Lovable Badge

Use `publish_settings--set_badge_visibility` with `hide_badge: true`. Requires Pro plan.

---

## 7. Vitest Tests

- `ThinkingPills.test.tsx`: Test pill rendering, animation states, fade-out on answer
- `DailyTeaching.test.tsx`: Update for database fetch (mock Supabase)
- `DesktopSidebar.test.tsx`: Collapsed mode spacing, delete confirmation
- `ChatMessage.test.tsx`: New message styling, markdown rendering

---

## 8. Security

- Run security scan after Lovable Cloud enabled
- Ensure all tables have RLS
- Fix `adminAuth.ts` to validate Supabase JWT, not just localStorage
- Create `user_roles` table with `has_role()` security definer function

---

## Execution Order

1. Enable Lovable Cloud (prerequisite)
2. Chat UI overhaul + Thinking Pills (independent, start immediately)
3. Sidebar fixes
4. Database migrations (tables)
5. Auth integration
6. Daily teaching database integration
7. Meditation tracking
8. Tests
9. Security scan
10. Remove badge

## Files to Create/Modify

| File | Action |
|------|--------|
| `src/components/chat/ThinkingPills.tsx` | **New** — animated pipeline status pills |
| `src/lib/aiService.ts` | Parse SSE `event: status` lines, yield status markers |
| `src/components/chat/ChatInterface.tsx` | Consume status events, show ThinkingPills, input cleanup |
| `src/components/chat/ChatHeader.tsx` | Simplify (remove guru photo, remove new chat button) |
| `src/components/chat/ChatMessage.tsx` | Refine styling, add react-markdown |
| `src/components/chat/DesktopSidebar.tsx` | Fix collapsed padding/width |
| `src/components/chat/DailyTeaching.tsx` | Database-backed fetch |
| `src/admin/pages/DailyTeachingPage.tsx` | Database-backed publish |
| `src/pages/AuthPage.tsx` | **New** — sign-in/sign-up page |
| `src/lib/meditationStorage.ts` | Database-backed persistence |
| `src/index.css` | Light mode fixes |
| `src/App.tsx` | Add `/auth` route |
| Migration files | All new tables |
| Test files | New + updated tests |

## Confidence: 8/10

- **9/10**: Chat UI, thinking pills, sidebar fixes — pure frontend, verified backend already sends status SSE events
- **8/10**: Database tables, daily teaching, meditation — standard Supabase CRUD, depends on Cloud being enabled
- **7/10**: Auth — depends on you completing Google OAuth setup in Google Cloud Console
- **N/A**: Backend Python changes — provided as documentation only, cannot run/deploy from sandbox
