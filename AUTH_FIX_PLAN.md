# Authentication Fix & Enhancement Plan

## Issues Identified

### 1. Google OAuth Issues
- **Problem**: OAuth not completing final authentication and returning to app
- **Problem**: No Google One Tap implementation (show continue with signed-in profiles)
- **Root Causes**:
  - Redirect URI mismatch or misconfiguration
  - Session not properly persisting after OAuth return
  - Missing One Tap UI component

### 2. Facebook OAuth Missing
- Need to implement both:
  - Native Supabase OAuth (Facebook provider)
  - Lovable Cloud wrapper for Facebook

### 3. Testing Required
- Full end-to-end auth flow testing
- Chat integration testing with authenticated sessions

## Implementation Steps

### Phase 1: Fix Google OAuth & Add One Tap
1. ✅ Review current OAuth flow in AuthPage.tsx
2. ⬜ Fix redirect handling and session persistence
3. ⬜ Implement Google One Tap UI
4. ⬜ Test Google OAuth flow (both native and Lovable)

### Phase 2: Implement Facebook OAuth
1. ⬜ Configure Facebook OAuth in Supabase
2. ⬜ Extend Lovable auth wrapper for Facebook
3. ⬜ Add Facebook sign-in buttons to AuthPage
4. ⬜ Test Facebook OAuth flows

### Phase 3: Testing & Validation
1. ⬜ Test all auth providers (Google, Facebook, Email/Password)
2. ⬜ Test session persistence across page refreshes
3. ⬜ Test chat integration with authenticated sessions
4. ⬜ Test auth redirect flows

### Phase 4: WhatsApp Bot Integration
1. ⬜ Create WhatsApp bot integration documentation
2. ⬜ Document /api/chat endpoint usage
3. ⬜ Provide webhook setup examples

## Files to Modify

### Frontend
- `/app/src/pages/AuthPage.tsx` - Add One Tap, Facebook OAuth
- `/app/src/integrations/lovable/index.ts` - Extend for Facebook
- `/app/src/integrations/supabase/client.ts` - Verify configuration
- `/app/src/hooks/useRequireAuth.ts` - Ensure proper session handling

### Backend
- `/app/backend/services/auth_service.py` - Verify auth strategies
- `/app/backend/app/main.py` - Verify /api/chat endpoint

### Documentation
- `/app/WHATSAPP_BOT_INTEGRATION.md` - New file for WhatsApp integration

## Configuration Required

### Environment Variables
```env
# Frontend (.env.local)
VITE_SUPABASE_URL=<your-supabase-url>
VITE_SUPABASE_PUBLISHABLE_KEY=<your-anon-key>
VITE_USE_NATIVE_OAUTH=true  # or false for Lovable wrapper
VITE_GOOGLE_CLIENT_ID=<your-google-client-id>  # For One Tap

# Backend (backend/.env)
SUPABASE_URL=<your-supabase-url>
SUPABASE_KEY=<your-service-role-key>
JWT_SECRET=<your-jwt-secret>
```

### Supabase Configuration
1. Enable Google OAuth provider
2. Enable Facebook OAuth provider
3. Configure redirect URLs:
   - http://localhost:8080/auth (local)
   - https://your-domain.com/auth (production)

## Testing Checklist

### Google OAuth
- [ ] Native Supabase Google OAuth works
- [ ] Lovable wrapper Google OAuth works
- [ ] Google One Tap shows signed-in profiles
- [ ] One Tap successfully authenticates
- [ ] Session persists after authentication
- [ ] Redirect to original page works

### Facebook OAuth
- [ ] Native Supabase Facebook OAuth works
- [ ] Lovable wrapper Facebook OAuth works
- [ ] Session persists after authentication
- [ ] Redirect to original page works

### Email/Password Auth
- [ ] Sign up works
- [ ] Sign in works
- [ ] Password reset works
- [ ] Email verification works

### Chat Integration
- [ ] Authenticated user can access /chat
- [ ] Chat messages send successfully
- [ ] Chat history persists
- [ ] Session timeout handled gracefully

### WhatsApp Bot
- [ ] Documentation is clear and complete
- [ ] Example webhook code provided
- [ ] Authentication flow documented
