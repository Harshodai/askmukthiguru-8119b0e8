# Lovable Setup for askmukthiguru

## 1. Set API URL
1. Open https://askmukthiguru.lovable.app
2. Settings → Environment Variables
3. Add: `VITE_BACKEND_URL = https://askmukthiguru-8119b0e8-production.up.railway.app`
   (NOT `VITE_API_URL` — the frontend code (`src/lib/chat/config.ts`, `profileStorage.ts`,
   `memoryApi.ts`, etc.) only reads `VITE_BACKEND_URL`. `VITE_API_URL` is never referenced
   anywhere in the codebase; setting it does nothing and the app silently falls back to
   `placeholder` mode with canned offline responses.)
4. Click "Deploy"

## 2. Verify Connection
- Open browser devtools → Network
- Send a chat message
- Verify request goes to https://askmukthiguru-8119b0e8-production.up.railway.app/api/chat

## 3. Custom Domain (if purchased via Lovable)
- Settings → Domains → Add custom domain
- Follow DNS instructions (CNAME to lovable.app)

## 4. Credits
- Pro plan: 20 credits/month + 5 daily
- Each deploy uses ~1-5 credits
- Monitor: Settings → Credit Usage
