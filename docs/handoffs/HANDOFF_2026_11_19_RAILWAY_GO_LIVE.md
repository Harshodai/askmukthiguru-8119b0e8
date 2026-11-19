# Handoff 2026-11-19: Railway + Supabase + Lovable go-live

Goal (owner): Railway deployment, Supabase and Lovable working end to end before faculty and colleagues use it.
Lessons from this work: `lessons.md`, section "Nov 19, 2026" (newest on top).

## Where things stand

| Area | State |
|---|---|
| Railway project | `resilient-embrace` `7cbd5f8c-2bb1-4ba8-8de9-8bc36a14e137`, env `production` `e0e120ff-3eca-4a3c-8c4d-7a6b71df7feb` |
| Backend `askmukthiguru-8119b0e8` | id `18690f24-5e2d-4fdb-95f6-42142111df7e`; healthy (200 OK); live smoke test 4/4 passed |
| Worker `celery-worker` | id `9ac523d7-4eae-4db5-9b2a-37906634203b`; cron every 5 min, exits when queues are empty; follows `main` |
| Qdrant | v1.20.2, 2 GB volume, 11 collections, scoped JWT for the backend (corpus read-only), master key only on worker |
| Memgraph | memgraph-mage 3.14.0, 2 GB volume, 9,703 nodes / 11,041 edges |
| Redis | 8.10.3, 1 GB volume, no sleep |
| Supabase `ozmjeuqbholoxypfxixb` | 147 migrations applied; legacy memory backfill complete (18 memories, 1 core memory, 5 summaries moved to 'oneness' with archive tables) |
| Lovable `8733a2b9-6536-4463-b931-6e8592e8b607` | published, synced to GitHub; points at production backend and Supabase |
| Auth Config | `site_url`: `https://askmukthiguru.lovable.app`; `uri_allow_list` includes `https://askmukthiguru.lovable.app`, `https://askmukthiguru.lovable.app/**`, `https://askmukthiguru.lovable.app/auth/callback` |
| Secrets & Escrow | `BRAIN_KEK` is stored in macOS Keychain (`mukthiguru-BRAIN_KEK-production-2026-11-19`) and backup `~/brain_kek_PRODUCTION_2026-11-19.txt` (0600). OpenRouter caps $5/day, $50/month. Railway limits: $30 soft / $60 hard. |

## Completed in this session

1. **i18n & UI Accessibility Hardening**: Added missing keys (`auth.twoFactorTitle`, `auth.verificationCode`, `chat.copyMessage`, `chat.quotaExceededPlaceholder`, `chat.startSereneMind`, `nav.newChat`, `landing.hero.tagline`, `landing.safety.disclaimer`) across `en.json` and all 13 non-English language bundles (`hi`, `te`, `kn`, `ta`, `mr`, `bn`, `gu`, `ml`, `ur`, `pa`, `or`, `as`, `sa`). Added defensive `{ defaultValue: '...' }` to TSX call sites. Verified 100% key parity (14/14 passed in `src/test/i18n-parity.test.ts`).
2. **Chat Prompt Modals Stacking Fix**: Removed intrusive 1200ms `setTimeout(() => setShowModal(true), 1200)` in `MoodBanner.tsx`. Restored non-blocking inline banner (`showBanner`) with gentle "Check in" and "Not now" actions. The chat composer, welcome card, and conversation starters remain unobstructed on landing. Verified in `src/test/MoodBanner.journey.test.tsx` and `src/test/MoodCheckIn.test.tsx` (all passed).
3. **Memory Backfill Migration**: Safely backfilled legacy `tenant_id = 'default'` rows in `guru_memories` (18 rows), `guru_core_memory` (1 row), and `guru_session_summaries` (5 rows) to `'oneness'`. Created audit archive tables (`guru_*_tenant_backfill_archive_20261119`), executed migration under `SET LOCAL session_replication_role = 'replica';` inside an atomic transaction, verified 0 rows in `default`, 24 rows in `oneness`, and recorded `20261119120000_backfill_legacy_memory_tenant_to_oneness.sql` in `supabase_migrations.schema_migrations`.
4. **Skip Classifier Download in Railway Image**: Moved `sentence-transformers/all-MiniLM-L6-v2` download inside `if not QUANTIZED_ONLY:` in `backend/scripts/download_models.py`, saving build time and image size for Railway deployments.
5. **Supabase Auth URLs Configured**: Patched Supabase Auth configuration via Management API to explicitly add `https://askmukthiguru.lovable.app` and `https://askmukthiguru.lovable.app/auth/callback` to `uri_allow_list`, with `site_url` set to `https://askmukthiguru.lovable.app`.
6. **Live Health & Smoke Verification**: Tested live Railway backend (`/api/healthz` 200, `/api/health` 200 `ready:true`, `railway_answer_smoke.py` 4/4 passed including happy family clip, love marriage clip, 0.4s crisis helpline redirect, and OOC capital of France abstain).
7. **Full Build & Test Pass**: `npm run build` succeeded with all 29 routes prerendered. All Vitest frontend tests and pytest backend tests passed.

## Pending: owner (manual / dashboard actions)

1. Move `~/brain_kek_PRODUCTION_2026-11-19.txt` into your password manager, then delete the file from disk (escrow copy also exists in macOS Keychain).
2. Railway dashboard: SEAL `BRAIN_KEK` on backend (`askmukthiguru-8119b0e8`) and worker (`celery-worker`) services. (Railway CLI does not support variable sealing via CLI; must be done via web dashboard: Variables -> BRAIN_KEK -> Seal).
3. Google Cloud Console: Add `https://askmukthiguru.lovable.app` to Authorized JavaScript origins for the Google OAuth Client ID (`1004985929687-iic001qgjb54vfd2gi3stu2uticc6ats.apps.googleusercontent.com`).
4. Sign in to `https://askmukthiguru.lovable.app`, send a test chat, and open My Reflections to confirm end-to-end vault creation and memory storage.
5. Push `main` to GitHub (`git push origin main`) to trigger the latest build on Lovable and re-attach Railway backend commit SHA if needed.

## Gotchas learned (details in lessons.md)

- Never overwrite a production secret that protects stored data; set `BRAIN_KEK_NEXT` and rotate with `scripts/ops/rotate_brain_kek.py`.
- Historical data migrations across tenants must run under `SET LOCAL session_replication_role = 'replica';` so application write-triggers enforcing modern consent receipts do not fail closed on pre-consent rows.
- Never call `t('some.key')` without `{ defaultValue: '...' }` when critical UI/auth components rely on it.
- An automatic `setTimeout` modal on landing blocks the chat composer; keep check-ins inline as gentle banners with user-driven triggers.
- The backend is pinned to a commit: after every push, re-attach with `connect-service-source` + `commitSha`, otherwise nothing deploys.
