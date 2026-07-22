# Production Readiness — Live Status

## ✅ Done this session

1. **Migrated frontend to Lovable Cloud Supabase** (`fynkjimvuimakgtidvuq`)
   - `.env.production` updated (was pointing at old `ozmjeuqbholoxypfxixb`)
   - `.env` already correct
   - All 40+ tables already exist on Lovable Cloud (from earlier session)
2. **Admin auto-grant** — `kharshaengineer@gmail.com` will receive `admin` role automatically on first Google sign-in (verified email required). Retroactive grant applied if already signed up.
3. **Google OAuth** — managed provider active. AuthPage's `supabase.auth.signInWithOAuth({ provider: 'google' })` uses Lovable's managed Google client. No Google Cloud Console setup needed.
4. **Sentry** — `src/lib/sentry.ts` wired. Add `VITE_SENTRY_DSN` in Lovable Cloud → Project Settings when ready.
5. **Language selector font size** — fixed (`text-lg` in dropdown, `text-base` in pill).
6. **Security findings** — 4 fixed, 4 backend-only ignored (see `SECURITY_NOTES.md`).

## 📋 You must do

1. **Cloudflare DNS** — set up `askmukthiguru.com` → `askmukthiguru.lovable.app` (see `RAILWAY_REWIRE.md`).
2. **Railway env vars** — repoint FastAPI at Lovable Cloud (see `RAILWAY_REWIRE.md`). Backend telemetry will silently fail until this is done.
3. **Sign in with Google once** at `https://askmukthiguru.lovable.app/auth` using `kharshaengineer@gmail.com` — admin role grants automatically. Then visit `/admin/login` and enter the same email/password (or continue with your existing session).
4. **MFA** — enable in your profile after first sign-in for the admin account. The `/auth/mfa` challenge page is already wired.
5. **Publish** the updated frontend so `.env.production` takes effect in prod.

## ⏭️ Deferred (needs a separate session)

The following were in the plan but each requires 2–3 credits of dedicated work. Ask when ready:

- **i18n gap audit + batch translate** (12 non-English locales × ~100 keys)
- **Playwright E2E verification** for all 23 languages across landing/auth/chat/admin/practices
- **Performance audit** — bundle analysis, code-splitting sweep, image WebP conversion, N+1 query fixes
- **SEO scan** — Lighthouse, GSC integration, Semrush content
- **Additional admin emails** — pattern documented in the migration; edit `admin_emails` array in `grant_admin_for_designated_emails` function

## ⚠️ Known caveats

- **Users on old DB** cannot log in — schema-only migration means fresh signup required.
- **Service-role gap** — Lovable Cloud doesn't expose the service key. Backend writes that bypass RLS must move to edge functions. Existing edge functions (`admin-telemetry`, `memory-embed`, `ingest-source`) already handle most cases.
- **Admin console i18n** — English-only by design (internal tool).

## Files updated this session

- `.env.production` — repoint to Lovable Cloud
- `supabase/migrations/<latest>.sql` — admin auto-grant trigger
- `RAILWAY_REWIRE.md` — Railway backend rewire guide
- `PROD_READINESS.md` — this file (rewritten)
