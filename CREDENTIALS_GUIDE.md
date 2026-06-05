# 🔑 CREDENTIALS & SETUP GUIDE
## Step-by-Step Instructions to Get Your App Running

**Time Required:** 1-2 hours  
**Difficulty:** Medium  
**Cost:** Free (with free tiers)

---

## 🎯 OVERVIEW

You need to obtain the following credentials:
1. ✅ Sarvam API Key (AI/LLM - **CRITICAL**)
2. ✅ Supabase Project (Database & Auth - **CRITICAL**)
3. ✅ JWT Secret (Security - **CRITICAL**)
4. ⚠️ Google OAuth Client ID (Authentication - Recommended)
5. ⚠️ Facebook App ID/Secret (Authentication - Optional)

---

## 1️⃣ SARVAM API KEY (CRITICAL)

### What It Does:
Powers the AI responses in your spiritual guidance app

### How to Get It:

#### Step 1: Sign Up
1. Go to: https://dashboard.sarvam.ai/
2. Click "Sign Up" or "Get Started"
3. Create account with email/password or Google

#### Step 2: Get API Key
1. After login, navigate to "API Keys" or "Settings"
2. Click "Create New API Key" or "Generate Key"
3. Copy the key (starts with `sk_` or similar)
4. **IMPORTANT:** Save it immediately - you may not see it again!

#### Step 3: Configure
```bash
# Edit /app/backend/.env
nano /app/backend/.env

# Add this line:
SARVAM_API_KEY=sk_your_actual_key_here
```

### Free Tier:
- Usually 100-1000 requests/month free
- Check current limits at https://sarvam.ai/pricing

### Test It:
```bash
curl -X POST https://api.sarvam.ai/v1/chat/completions \
  -H "Authorization: Bearer YOUR_KEY_HERE" \
  -H "Content-Type: application/json" \
  -d '{"model":"sarvam-30b","messages":[{"role":"user","content":"Hello"}]}'
```

---

## 2️⃣ SUPABASE PROJECT (CRITICAL)

### What It Does:
- User authentication (email/password, OAuth)
- Database for user profiles, chat history
- Real-time subscriptions

### How to Get It:

#### Step 1: Create Project
1. Go to: https://supabase.com
2. Click "Start your project" or "Sign In"
3. Sign in with GitHub (recommended) or email
4. Click "New Project"
5. Fill in:
   - **Organization:** Create new or select existing
   - **Project Name:** `askmukthiguru` (or your choice)
   - **Database Password:** Generate strong password (save it!)
   - **Region:** Choose closest to your users
   - **Plan:** Free (sufficient for development)

#### Step 2: Get Credentials
1. After project creation (takes 2-3 minutes)
2. Go to **Settings** (gear icon in sidebar)
3. Go to **API** section
4. Copy these values:

```
Project URL: https://your-project-ref.supabase.co
anon/public key: eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
service_role key: eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9... (secret!)
JWT Secret: your-super-secret-jwt
```

#### Step 3: Run Migrations
1. In Supabase Dashboard, go to **SQL Editor**
2. Click "New Query"
3. Copy contents of `/app/supabase/migrations/*.sql` files
4. Run each migration in order (oldest first)

**OR** use Supabase CLI:
```bash
cd /app
npx supabase login
npx supabase link --project-ref your-project-ref
npx supabase db push
```

#### Step 4: Configure OAuth Providers

##### Enable Google OAuth:
1. In Supabase Dashboard → **Authentication** → **Providers**
2. Find **Google** and click to configure
3. Toggle "Enable Sign in with Google"
4. You'll need Google Client ID (see section 4 below)
5. Add Redirect URLs:
   ```
   http://localhost:8080/auth
   https://your-production-domain.com/auth
   ```

##### Enable Facebook OAuth:
1. Same section, find **Facebook**
2. Toggle enable
3. You'll need Facebook App ID/Secret (see section 5 below)
4. Add same redirect URLs

#### Step 5: Configure Environment
```bash
# Edit /app/.env.local (frontend)
nano /app/.env.local

VITE_SUPABASE_URL=https://your-project-ref.supabase.co
VITE_SUPABASE_PUBLISHABLE_KEY=your-anon-key
VITE_SUPABASE_PROJECT_ID=your-project-ref

# Edit /app/backend/.env (backend)
nano /app/backend/.env

SUPABASE_URL=https://your-project-ref.supabase.co
SUPABASE_KEY=your-service-role-key
JWT_SECRET=your-jwt-secret
```

### Verify Setup:
```bash
# Test connection
curl https://your-project-ref.supabase.co/rest/v1/profiles \
  -H "apikey: your-anon-key" \
  -H "Authorization: Bearer your-anon-key"
```

---

## 3️⃣ JWT SECRET (CRITICAL)

### What It Does:
Secures your authentication tokens and sessions

### How to Generate:

#### Option 1: OpenSSL (Recommended)
```bash
openssl rand -hex 32
# Output: 64-character hex string
```

#### Option 2: Python
```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

#### Option 3: Node.js
```bash
node -e "console.log(require('crypto').randomBytes(32).toString('hex'))"
```

### Configure:
```bash
# Edit /app/backend/.env
nano /app/backend/.env

JWT_SECRET=your_64_character_hex_string_here
```

### ⚠️ SECURITY WARNING:
- **NEVER** commit this to git
- **NEVER** share publicly
- Use different secrets for dev/staging/production
- Minimum 32 characters (64 recommended)
- Changing this invalidates all existing sessions

---

## 4️⃣ GOOGLE OAUTH CLIENT ID (Recommended)

### What It Does:
Enables "Sign in with Google" and Google One Tap

### How to Get It:

#### Step 1: Create Google Cloud Project
1. Go to: https://console.cloud.google.com
2. Click "Select a project" → "New Project"
3. Name: `AskMukthiGuru` (or your choice)
4. Click "Create"

#### Step 2: Enable Google Identity
1. In your new project, go to **APIs & Services** → **Library**
2. Search for "Google Identity"
3. Click "Google Identity Toolkit API"
4. Click "Enable"

#### Step 3: Create OAuth Credentials
1. Go to **APIs & Services** → **Credentials**
2. Click "Create Credentials" → "OAuth client ID"
3. If prompted, configure OAuth consent screen:
   - User Type: **External** (for testing)
   - App name: `AskMukthiGuru`
   - User support email: your email
   - Developer contact: your email
   - Click "Save and Continue"
   - Scopes: Leave default (just email and profile)
   - Test users: Add your email for testing
   - Click "Save and Continue"

4. Back to Create OAuth Client ID:
   - Application type: **Web application**
   - Name: `AskMukthiGuru Web`
   - Authorized JavaScript origins:
     ```
     http://localhost:8080
     http://localhost:3000
     https://your-production-domain.com
     ```
   - Authorized redirect URIs:
     ```
     http://localhost:8080/auth
     https://your-production-domain.com/auth
     https://your-project-ref.supabase.co/auth/v1/callback
     ```
   - Click "Create"

#### Step 4: Copy Credentials
1. You'll see a popup with:
   - **Client ID** (ends in `.apps.googleusercontent.com`)
   - **Client Secret** (keep secret!)
2. Download JSON for backup
3. Copy Client ID

#### Step 5: Configure in Supabase
1. Supabase Dashboard → **Authentication** → **Providers** → **Google**
2. Paste **Client ID** and **Client Secret**
3. Save changes

#### Step 6: Configure in App
```bash
# Edit /app/.env.local
nano /app/.env.local

VITE_GOOGLE_CLIENT_ID=your-client-id.apps.googleusercontent.com
```

### Test It:
1. Go to http://localhost:8080/auth
2. Click "Continue with Google"
3. Should redirect to Google sign-in
4. After signing in, should return to your app

---

## 5️⃣ FACEBOOK APP ID/SECRET (Optional)

### What It Does:
Enables "Sign in with Facebook"

### How to Get It:

#### Step 1: Create Facebook App
1. Go to: https://developers.facebook.com
2. Click "My Apps" → "Create App"
3. Use case: **Consumer** (for user authentication)
4. App name: `AskMukthiGuru`
5. App contact email: your email
6. Click "Create App"

#### Step 2: Add Facebook Login
1. In your app dashboard, click "Add Product"
2. Find "Facebook Login" → Click "Set Up"
3. Choose platform: **Web**
4. Site URL: `http://localhost:8080` (for now)
5. Save

#### Step 3: Configure OAuth Settings
1. In left sidebar, go to **Facebook Login** → **Settings**
2. Valid OAuth Redirect URIs:
   ```
   http://localhost:8080/auth
   https://your-production-domain.com/auth
   https://your-project-ref.supabase.co/auth/v1/callback
   ```
3. Save Changes

#### Step 4: Get App Credentials
1. Go to **Settings** → **Basic**
2. Copy:
   - **App ID**: (public)
   - **App Secret**: Click "Show" (keep secret!)

#### Step 5: Configure in Supabase
1. Supabase Dashboard → **Authentication** → **Providers** → **Facebook**
2. Paste **App ID** and **App Secret**
3. Save changes

#### Step 6: Switch to Production (When Ready)
1. Top of Facebook App Dashboard
2. Toggle "App Mode" from Development to Live
3. Complete App Review if required

### Test It:
1. Go to http://localhost:8080/auth
2. Click "Continue with Facebook"
3. Should redirect to Facebook login
4. After login, should return to your app

---

## 6️⃣ INFRASTRUCTURE SETUP

### Qdrant (Vector Database)
```bash
# Start with Docker
docker run -d \
  --name qdrant \
  -p 6333:6333 \
  -p 6334:6334 \
  -v $(pwd)/qdrant_storage:/qdrant/storage:z \
  qdrant/qdrant

# Verify
curl http://localhost:6333/health
```

### Redis (Caching)
```bash
# Start with Docker
docker run -d \
  --name redis \
  -p 6379:6379 \
  redis:latest

# Verify
redis-cli ping
# Should return: PONG
```

---

## 7️⃣ VERIFICATION CHECKLIST

### Backend Configuration:
```bash
cd /app/backend
cat .env | grep -E "(SARVAM_API_KEY|JWT_SECRET|SUPABASE)"
```

Should show:
- ✅ SARVAM_API_KEY=sk_...
- ✅ JWT_SECRET=64-char-hex
- ✅ SUPABASE_URL=https://...
- ✅ SUPABASE_KEY=eyJ...

### Frontend Configuration:
```bash
cd /app
cat .env.local | grep -E "(VITE_SUPABASE|VITE_GOOGLE)"
```

Should show:
- ✅ VITE_SUPABASE_URL=https://...
- ✅ VITE_SUPABASE_PUBLISHABLE_KEY=eyJ...
- ✅ VITE_GOOGLE_CLIENT_ID=...apps.googleusercontent.com

### Services Running:
```bash
sudo supervisorctl status
```

Should show:
- ✅ backend: RUNNING
- ✅ frontend: RUNNING
- ✅ mongodb: RUNNING

### Test Endpoints:
```bash
# Backend health
curl http://localhost:8001/api/health

# Frontend
curl http://localhost:3000

# Qdrant
curl http://localhost:6333/health

# Redis
redis-cli ping
```

---

## 8️⃣ TROUBLESHOOTING

### "Backend not starting"
```bash
# Check logs
tail -100 /var/log/supervisor/backend.err.log

# Common issues:
# 1. Missing dependencies
cd /app/backend && /root/.venv/bin/pip install -r requirements.txt

# 2. Import errors
cd /app/backend && python3 -c "from app.main import app"

# 3. Environment vars not loaded
cat /app/backend/.env
```

### "Frontend not building"
```bash
# Check logs
tail -100 /var/log/supervisor/frontend.err.log

# Rebuild
cd /app && yarn build
```

### "OAuth not working"
1. Check redirect URIs match exactly (no trailing slashes)
2. Verify Supabase provider is enabled
3. Check browser console for errors
4. Ensure cookies enabled
5. Try incognito mode

### "Database connection failed"
```bash
# Test Supabase
curl https://your-project.supabase.co/rest/v1/

# Check migrations ran
# Supabase Dashboard → Database → look for tables
```

---

## 9️⃣ SECURITY BEST PRACTICES

### Secrets Management:
- ✅ Never commit `.env` files to git
- ✅ Use different secrets for dev/prod
- ✅ Rotate keys regularly (quarterly)
- ✅ Use environment variables, not config files
- ✅ Limit access to production keys

### OAuth Security:
- ✅ Use HTTPS in production (required)
- ✅ Validate redirect URIs strictly
- ✅ Keep OAuth secrets encrypted
- ✅ Monitor for suspicious auth attempts

---

## 🎉 READY TO START!

Once you have all credentials configured:

```bash
# Restart all services
sudo supervisorctl restart all

# Check status
sudo supervisorctl status

# Test the app
curl http://localhost:8001/api/health
curl http://localhost:3000

# Open in browser
# http://localhost:3000
```

### First Test:
1. Navigate to http://localhost:3000/auth
2. Try signing in with email/password (create account first)
3. Try "Continue with Google"
4. Go to /chat and send a message
5. Verify AI responds

---

## 📞 NEED HELP?

### Got Credentials But Still Not Working?
- Check `/app/RUTHLESS_AUDIT_REPORT.md` for detailed issues
- Review logs in `/var/log/supervisor/`
- Ensure all services running: `sudo supervisorctl status`

### Can't Get Credentials?
- Sarvam: Check https://sarvam.ai/docs for signup issues
- Supabase: Try https://supabase.com/docs/guides/auth
- Google: Check https://developers.google.com/identity/protocols/oauth2

---

**Good luck! 🚀**
