# User Actions — Ready-to-Execute Checklist

Everything below requires **you** to do it (Lovable / agent cannot). Ordered by priority.

---

## 🔴 P0 — Do Now (Blocks Production)

### 1. Sign in with `kharshaengineer@gmail.com` to activate admin

The DB trigger `grant_admin_for_designated_emails` auto-grants admin role on first Google sign-in with a verified email.

1. Open <https://askmukthiguru.lovable.app/auth>
2. Click **Continue with Google** → sign in with `kharshaengineer@gmail.com`
3. Navigate to `/admin` — should load Overview page
4. If redirected to `/admin/login`, wait 5s, refresh. Trigger runs on `email_confirmed_at`.

**Verify** (optional): ask agent to run `SELECT * FROM user_roles WHERE role='admin'` — your user_id should appear.

### 2. Cloudflare DNS for `askmukthiguru.com`

Point apex + `www` at your Lovable custom domain:

| Type | Name | Value | Proxy |
|------|------|-------|-------|
| CNAME | `@` (or ALIAS) | `askmukthiguru.lovable.app` | DNS only |
| CNAME | `www` | `askmukthiguru.lovable.app` | DNS only |

Then in Lovable → Project Settings → Domains → add `askmukthiguru.com`.

### 3. Set `VITE_SENTRY_DSN` (frontend errors)

Lovable → Project Settings → Environment Variables → add `VITE_SENTRY_DSN` = your Sentry DSN.
Guard in `src/lib/sentry.ts` already restricts to `*.lovable.app` hosts.

---

## 🟡 P1 — Do This Week

### 4. Update Railway backend to Lovable Cloud (backend migration)

See `RAILWAY_REWIRE.md` for full instructions. TL;DR — set these Railway env vars:

```
SUPABASE_URL=https://fynkjimvuimakgtidvuq.supabase.co
SUPABASE_ANON_KEY=<from Lovable Cloud → Backend → API keys>
SUPABASE_PUBLISHABLE_KEY=<same as above>
CORS_ORIGINS=https://askmukthiguru.lovable.app,https://askmukthiguru.com,https://*.lovable.app
```

⚠️ **Service-role gap**: Lovable Cloud does NOT expose `service_role` keys. Any backend code that bypasses RLS (telemetry, embeddings, admin ops) must route through edge functions (`admin-telemetry`, `memory-embed`, `ingest-source` already scaffolded).

### 5. Enable MFA on your admin account

`/profile` → Security → Two-Factor Authentication → enroll TOTP. Prevents admin takeover if Google account is compromised.

### 6. Verify session/auth flows manually

Not automated this turn — run this checklist:

- [ ] Log out → visit `/chat` → redirects to `/auth` ✓
- [ ] Log in → visit `/chat` → loads ✓
- [ ] In DevTools, delete `sb-fynkjimvuimakgtidvuq-auth-token` from localStorage → refresh → toast "Your session has ended" + redirect to `/auth` ✓
- [ ] Click sign-out → no toast (explicit) + redirect to `/auth` ✓
- [ ] Google OAuth button → redirects to `accounts.google.com` ✓

---

## 🟢 P2 — Do When You Have Time

### 7. Translate remaining locales (bn, gu, ml, ur, or, pa, as, sa)

Currently these 8 languages are **selectable** in the LanguageSelector but fall back to English text (i18next `fallbackLng: 'en'`). Existing translations: en, hi, te, kn, ta, mr.

**To complete a locale** (example: Bengali):

1. Copy `src/locales/en.json` → `src/locales/bn.json`
2. Use ChatGPT/Gemini or human translator to fill values (keys stay identical)
3. In `src/i18n.ts`:
   ```ts
   import bn from './locales/bn.json';
   // then in resources block:
   bn: { translation: bn },  // remove the enFallback line
   ```

### 8. Delete old `ozmjeuqbholoxypfxixb` Supabase project

Only after step 4 (Railway rewire) succeeds AND you've re-signed in all admin users on new Cloud DB. Schema-only migration = old user accounts are gone by design.

### 9. Custom Google OAuth branding

Managed Google OAuth already works. If you want the consent screen to say "AskMukthiGuru" instead of "Lovable":

1. Google Cloud Console → OAuth consent screen → configure with your logo/name
2. Get Client ID + Client Secret
3. Lovable → Cloud → Users → Auth Settings → Google → paste your credentials

---

## Reference Files

| File | Purpose |
|------|---------|
| `RAILWAY_REWIRE.md` | Railway env-var flip instructions |
| `MIGRATION_DECISION.md` | Why Lovable Cloud + hybrid backend |
| `PROD_READINESS.md` | Current production status |
| `PERF_AUDIT.md` | Performance findings + fixes shipped |
| `I18N_STATUS.md` | Translation coverage per locale |

---

## What the Agent Already Did (No Action Needed)

- ✅ Migrated 40-table schema to Lovable Cloud (`fynkjimvuimakgtidvuq`)
- ✅ Admin auto-grant trigger for `kharshaengineer@gmail.com`
- ✅ Managed Google OAuth configured
- ✅ 8 new languages registered (fall back to English)
- ✅ Language selector font-size fix (native scripts now readable)
- ✅ Sentry SDK wired (needs your DSN — step 3)
- ✅ All admin & heavy routes are code-split via `lazyWithRetry`
- ✅ MFA challenge page live at `/auth/mfa`
- ✅ `.env.production` points at Lovable Cloud
