# AskMukthiGuru - 37 Pre-Launch Checks Implementation Plan

## Project Overview
- **App**: AskMukthiGuru - AI Spiritual Guru Chat Application
- **Stack**: React/TypeScript frontend (Vite), FastAPI backend, Supabase (Postgres + Auth), Qdrant, Neo4j, Redis
- **Deployment**: Railway (backend), Docker + Nginx (frontend), Capacitor for mobile
- **Domain**: askmukthiguru.com (to be configured)

---

## Category 1: Security (6 items - 🔴 Launch Blockers)

### 1.1 Turn on RLS so your database isn't publicly readable
**Status**: ✅ Done (Jul 28, 2026)
**Notes**: Migration `supabase/migrations/20260728103548_*.sql` enables RLS with UPDATE WITH CHECK clause. Idempotent follow-up migration `20260730000000_verify_rls_with_check.sql` applied. Cross-user verifier script `backend/scripts/verify_rls_policies.py` confirms 12 probes pass.
**Location**: Supabase Dashboard / SQL migrations
**Action**: Enable Row Level Security on all tables in Supabase
```sql
-- Run in Supabase SQL Editor
ALTER TABLE public.profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.user_brain_nodes ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.guru_memories ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.chat_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.chat_messages ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.push_devices ENABLE ROW LEVEL SECURITY;
-- Add policies for each table
```

### 1.2 Enforce your login and paywall on the server
**Status**: ⏳ Pending
**Location**: `backend/app/api/endpoints/auth.py`, `backend/app/middleware/`
**Action**: 
- Verify all API routes use `Depends(get_current_user)` or similar
- Check `backend/app/api/chat.py`, `backend/app/api/memory.py`, `backend/app/api/profile.py`
- Ensure no public endpoints expose user data

### 1.3 Check that http://askmukthiguru.com/.env shows nothing
**Status**: ✅ Done
**Notes**: `nginx.conf` has `location ~ /\.env { deny all; return 404; }` — confirmed in code.
**Location**: `frontend/nginx.conf`, `backend/Dockerfile`, Railway config
**Action**: 
- Verify `.env` files are not served by nginx
- Check `nginx.conf` has `location ~ /\.env { deny all; }`
- Ensure Docker builds don't copy `.env` to image

### 1.4 Remove secret keys from your frontend
**Status**: ⏳ Pending
**Location**: `src/lib/`, `src/integrations/`, `vite.config.ts`
**Action**:
- Search for hardcoded API keys, Supabase keys, OpenRouter keys
- Move all secrets to environment variables
- Use `import.meta.env.VITE_*` for frontend-only vars
- Verify no secrets in `src/integrations/supabase/client.ts`

### 1.5 Force HTTPS everywhere and test your SSL certificate
**Status**: ✅ Done (with caveat)
**Notes**: HSTS header `max-age=31536000; includeSubDomains` present in nginx.conf. TLS terminates at Railway's edge (not in nginx container). Confirmed by nginx config structure — `listen 80;` only, upstream Railway handles TLS. Comment added to nginx.conf 2026-08-01 for clarity.
**Location**: Railway dashboard, `frontend/nginx.conf`, `backend/app/main.py`
**Action**:
- Enable "Force HTTPS" in Railway project settings
- Add HSTS header in nginx: `add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;`
- Verify SSL cert with `curl -I https://askmukthiguru.com`

### 1.6 Rate-limit your expensive (AI) endpoints
**Status**: ✅ Done
**Notes**: TokenBucketMiddleware (Redis) on /api/chat; SlowAPI 200/min global; admin rate limiter 30 req/60s; auth TTL-based 5 req/60s. Per `docs/SECURITY_CHECKLIST.md` item #2.
**Location**: `backend/app/middleware/rate_limit.py`, `backend/app/core/limiter.py`
**Action**:
- Verify rate limiter is applied to `/chat/completions`, `/api/chat`, `/api/speech`
- Configure per-user limits (e.g., 10 req/min for chat, 5 req/min for STT/TTS)
- Test with load testing script

---

## Category 2: Emails (4 items - 🔴 Launch Blockers)

### 2.1 Configure SPF, DKIM and DMARC
**Status**: ⏳ Pending (DNS configuration)
**Action**:
- Add SPF record: `v=spf1 include:_spf.resend.com ~all` (or your provider)
- Add DKIM record from email provider (Resend/SendGrid)
- Add DMARC: `v=DMARC1; p=quarantine; rua=mailto:dmarc@askmukthiguru.com`

### 2.2 Set up your transactional emails
**Status**: ⏳ Pending
**Location**: `backend/app/services/email_service.py`, Supabase Auth config
**Action**:
- Configure Supabase SMTP settings (Resend/SendGrid)
- Customize email templates in Supabase Dashboard > Authentication > Email Templates
- Test signup, password reset, magic link emails

### 2.3 Send yourself a signup email in Gmail AND Outlook
**Status**: ⏳ Pending
**Action**: 
- Create test account
- Verify delivery to Gmail (inbox, not spam)
- Verify delivery to Outlook (inbox, not spam)
- Check rendering on mobile/desktop

### 2.4 Send app emails from a subdomain
**Status**: ⏳ Pending
**Action**:
- Configure `mail.askmukthiguru.com` or `app.askmukthiguru.com` for transactional emails
- Update SPF/DKIM for subdomain
- Update Supabase email sender domain

---

## Category 3: Findability/SEO (6 items - Mix of 🔴 and 🟡)

### 3.1 Add a preview image for your links (og:image)
**Status**: ⏳ Pending
**Location**: `index.html`, `src/pages/` meta tags
**Action**:
- Create 1200x630 OG image at `public/og-image.png`
- Add to `index.html`: `<meta property="og:image" content="/og-image.png" />`
- Add Twitter card meta tags
- Test with Facebook Sharing Debugger and Twitter Card Validator

### 3.2 Submit your sitemap to Google Search Console
**Status**: ⏳ Pending
**Location**: `src/lib/sitemap.ts` (to create), `public/robots.txt`
**Action**:
- Generate `sitemap.xml` with all public routes
- Add to `robots.txt`: `Sitemap: https://askmukthiguru.com/sitemap.xml`
- Submit in GSC after deployment

### 3.3 Check you're not accidentally blocking Google
**Status**: ⏳ Pending
**Location**: `public/robots.txt`, `frontend/nginx.conf`
**Action**:
- Verify `robots.txt` allows `/` and `/chat` paths
- Check no `noindex` meta tags on public pages
- Verify nginx doesn't block Googlebot

### 3.4 Give every public page a real title and description
**Status**: ⏳ Pending
**Location**: `src/pages/*.tsx`, `index.html`
**Action**:
- Add unique `<title>` and `<meta name="description">` to each page
- Pages: `/`, `/chat`, `/profile`, `/knowledge-graph`, `/auth`, `/reset-password`

### 3.5 Remove http://localhost and staging leftovers
**Status**: ⏳ Pending
**Location**: `src/lib/backendUrl.ts`, `src/lib/api.ts`, `.env*`, `vite.config.ts`
**Action**:
- Search for `localhost`, `staging`, `127.0.0.1` in codebase
- Replace with environment variables
- Verify production build uses correct API URL

### 3.6 Add a robots.txt (and llms.txt if you want)
**Status**: ⏳ Pending
**Location**: `public/robots.txt`, `public/llms.txt` (optional)
**Action**:
```
# public/robots.txt
User-agent: *
Allow: /

Sitemap: https://askmukthiguru.com/sitemap.xml

# public/llms.txt (optional)
# Allow AI crawlers to index content
User-agent: GPTBot
Allow: /
User-agent: ClaudeBot
Allow: /
User-agent: PerplexityBot
Allow: /
```

---

## Category 4: Speed (4 items - Mix of 🔴 and 🟡)

### 4.1 Run PageSpeed Insights
**Status**: ⏳ Pending (requires deployed URL)
**Action**:
- Deploy to staging/production
- Run PageSpeed Insights on key pages
- Target: Mobile > 90, Desktop > 95
- Fix identified issues

### 4.2 Compress your images with Squoosh
**Status**: ⏳ Pending
**Location**: `public/`, `src/assets/`
**Action**:
- Convert all images to WebP/AVIF
- Resize to appropriate dimensions
- Use `<picture>` element with fallbacks
- Target: < 100KB for hero images, < 50KB for icons

### 4.3 Fix anything that jumps around while loading (CLS)
**Status**: ⏳ Pending
**Location**: `src/pages/`, `src/components/`, `index.css`
**Action**:
- Add `width`/`height` or `aspect-ratio` to all images
- Reserve space for ads/embeds
- Use `font-display: swap` for web fonts
- Avoid inserting content above existing content

### 4.4 Remove libraries AI installed but didn't end up using
**Status**: ⏳ Pending
**Location**: `package.json`, `backend/requirements.txt`
**Action**:
- Run `npm run build` and check bundle analyzer
- Run `pip-audit` or `pip check` for backend
- Remove unused dependencies

---

## Category 5: Analytics (4 items - Mix of 🔴 and 🟡)

### 5.1 Install analytics and check it's actually firing
**Status**: ⏳ Pending
**Location**: `src/lib/analytics.ts` (to create), `index.html`
**Action**:
- Add Plausible/GA4/Umami tracking
- Verify events fire on: page_view, chat_start, chat_message, signup
- Test in browser dev tools Network tab

### 5.2 Track web vitals from day one
**Status**: ⏳ Pending
**Location**: `src/lib/web-vitals.ts` (to create)
**Action**:
- Add web-vitals library
- Send CLS, FID, LCP, TTFB to analytics
- Set up alerts for regressions

### 5.3 Set up at least one conversion funnel
**Status**: ⏳ Pending
**Location**: Analytics dashboard
**Action**:
- Define funnel: Landing → Signup → First Chat → Return Visit
- Configure in analytics tool
- Set up weekly review

### 5.4 Turn on error tracking
**Status**: ⏳ Partial (Sentry config exists?)
**Location**: `src/lib/sentry.ts` (check), `backend/app/main.py`
**Action**:
- Initialize Sentry in frontend and backend
- Capture errors with user context
- Set up alerts for error rate spikes

---

## Category 6: Legal (3 items - Mix of 🔴 and 🟡)

### 6.1 Publish your Terms of Service and Privacy Policy
**Status**: ⏳ Pending
**Location**: `src/pages/Terms.tsx`, `src/pages/Privacy.tsx` (to create), `public/`
**Action**:
- Create legal pages with proper content
- Link in footer and auth pages
- Add to sitemap

### 6.2 Know who your merchant of record is
**Status**: ⏳ Pending (Stripe is MoR)
**Action**:
- Document: Stripe is Merchant of Record
- Update Privacy Policy with Stripe data processing terms
- Configure Stripe Tax if needed

### 6.3 Add a cookie banner if you track
**Status**: ⏳ Pending
**Location**: `src/components/CookieBanner.tsx` (to create)
**Action**:
- Add consent banner for analytics cookies
- Respect `Do Not Track` header
- Store consent in localStorage/cookie

---

## Category 7: Final Tests (5 items - 🔴 Launch Blockers + 🟡)

### 7.1 Check your 404 page
**Status**: ⏳ Pending
**Location**: `src/pages/NotFound.tsx`
**Action**:
- Create friendly 404 page with search link
- Add "Back to Home" button
- Test by visiting `/nonexistent`

### 7.2 Test in a second browser and on desktop
**Status**: ⏳ Pending
**Action**:
- Test in Firefox, Safari, Chrome
- Test on Windows, macOS, Linux
- Verify all features work

### 7.3 Walk your core flow on your phone
**Status**: ⏳ Partial (mobile app exists)
**Action**:
- Test: Signup → Chat → Voice → Profile → Knowledge Graph
- Test on iOS Safari and Android Chrome
- Test Capacitor mobile app build

### 7.4 Test your Stripe webhooks in live mode
**Status**: ⏳ Pending (if using Stripe)
**Location**: `backend/app/api/webhooks/stripe.py`, Stripe Dashboard
**Action**:
- Configure webhook endpoint in Stripe Dashboard
- Test with `stripe trigger` CLI
- Verify subscription events handled correctly

### 7.5 Click every link and button
**Status**: ⏳ Pending
**Action**:
- Automated: Run Playwright tests
- Manual: Navigate every page, click every interactive element
- Fix broken links, missing handlers

---

## Nice to Have (🟢)

### 8.1 Score 9+ on mail-tester.com
**Status**: ⏳ Pending
**Action**: Send test email to mail-tester.com, fix issues

### 8.2 Set up session recordings (with consent)
**Status**: ⏳ Pending
**Action**: Add PostHog/FullStory with consent gate

### 8.3 Put your app on a subdomain, marketing on the main domain
**Status**: ⏳ Pending
**Action**: Configure `app.askmukthiguru.com` for app, `askmukthiguru.com` for marketing

---

## Execution Order (Priority-Based)

### Phase 1: Security Launch Blockers (Day 1-2)
1. RLS policies
2. Server-side auth enforcement
3. Remove frontend secrets
4. Rate limiting verification
5. HTTPS/SSL
6. .env exposure check

### Phase 2: Email Setup (Day 2-3)
1. SPF/DKIM/DMARC DNS records
2. Transactional email config
3. Test delivery
4. Subdomain setup

### Phase 3: SEO/Findability (Day 3-4)
1. OG image + meta tags
2. robots.txt + sitemap.xml
3. Page titles/descriptions
4. Localhost cleanup
5. GSC submission (after deploy)

### Phase 4: Speed Optimization (Day 4-5)
1. Image optimization
2. CLS fixes
3. Bundle analysis
4. PageSpeed audit

### Phase 5: Analytics & Legal (Day 5-6)
1. Analytics + web vitals
2. Error tracking
3. Legal pages
4. Cookie banner
5. Conversion funnel

### Phase 6: Final Testing (Day 6-7)
1. 404 page
2. Cross-browser
3. Mobile testing
4. Stripe webhooks
5. Click every link/button

---

## Verification Commands

```bash
# Security checks
curl -I https://askmukthiguru.com/.env  # Should 403/404
curl -I https://askmukthiguru.com/ | grep -i strict-transport-security

# SEO checks
curl https://askmukthiguru.com/robots.txt
curl https://askmukthiguru.com/sitemap.xml

# Rate limit test
for i in {1..15}; do curl -s -o /dev/null -w "%{http_code}\n" https://askmukthiguru.com/api/chat; done

# Bundle analysis
npm run build && npx vite-bundle-analyzer dist
```

---

## Tracking

Update the CSV file at `/Users/harshodaikolluru/Downloads/ExportBlock-ea299486-4751-4d6a-8611-446aedde5427-Part-1/The 37 Pre-Launch Checks 53ab5b78c6f6821ab6bc011fdf7479b7_all.csv` with `Done` status as items are completed.