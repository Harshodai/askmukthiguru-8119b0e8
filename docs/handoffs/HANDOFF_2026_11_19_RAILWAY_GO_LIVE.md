# Handoff 2026-11-19: Railway + Supabase + Lovable go-live

Goal (owner): Railway deployment, Supabase and Lovable working end to end before faculty and colleagues use it.
Lessons from this work: `lessons.md`, section "Nov 19, 2026" (newest on top).

## Where things stand

| Area | State |
|---|---|
| Railway project | `resilient-embrace` `7cbd5f8c-2bb1-4ba8-8de9-8bc36a14e137`, env `production` `e0e120ff-3eca-4a3c-8c4d-7a6b71df7feb` |
| Backend `askmukthiguru-8119b0e8` | id `18690f24-5e2d-4fdb-95f6-42142111df7e`; healthy (200 OK); live smoke test 4/4 passed |
| Worker `celery-worker` | id `9ac523d7-4eae-4db5-9b2a-37906634203b`; cron daily `0 0 * * *` (owner change), exits when queues are empty; follows `main`. Canonical memory writes happen inline in the request; the browser `pending_extractions` plane is gated off (`VITE_MEMORY_EXTRACTION_ENABLED`, 0 rows) and would be drained by the Supabase Edge Function `memory-extract-drain`, not this cron; the outbox has 0 rows. So the daily schedule does not delay memories |
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
8. **Railway BRAIN_KEK Variable Sealing**: Owner confirmed `BRAIN_KEK` is permanently sealed on both `askmukthiguru-8119b0e8` (backend) and `celery-worker`.
9. **Google OAuth 2.0 Origins**: Confirmed `https://askmukthiguru.lovable.app` is active in both Authorized JavaScript origins and Authorized redirect URIs in Google Cloud Console (`1004985929687-iic001qgjb54vfd2gi3stu2uticc6ats.apps.googleusercontent.com`).

## Hardening pass (2026-11-19 afternoon, uncommitted until the owner pushes)

Evidence: 24 h of deploy/http logs for all 5 services, parsed by signature; two live batteries (48 + 47 turns, ~$0.04 OpenRouter total).

Fixed in code (each with a test that fails without it): "according to the teachings" read as an external teacher (`services/guru_registry.py`); chat-extracted memories never vector-indexed, plus sequential lexical recall timing out (`services/canonical_memory/resolver.py`, `retriever.py`, `app/container.py`); nonexistent `get_distress_history` call (`app/orchestrator_utils.py`); personalize decline F-VERIFY ERROR (`personalize_stage.py`); all anonymous users in one usage-monitor bucket (`app/api/chat.py`); porn-addiction question lost the addiction support line (`guardrails/lightweight_handler.py`); ~17 duplicate `GET /api/profile` per page load (`src/lib/profileStorage.ts`); client system prompt sent and dropped on every chat (`src/lib/chat/transport.ts`); "Memory Paused" shown while consent loads (`ChatHeader.tsx`, plus a one-line owner edit in `ChatInterface.tsx:2574`: `memoryActive={memoryConsent}`).

Applied live: migration `20261119084013_pin_function_search_path` (3 functions); Railway vars (take effect at next deploy): `OPENROUTER_DAILY_BUDGET_USD=50`, `OPENROUTER_MONTHLY_BUDGET_USD=500` (backend + worker), `ANON_QUOTA_MESSAGES=50` (backend; abuse tradeoff: anonymous sessions are free to mint, so the per-session quota is not a spend cap; per-IP `CHAT_RATE_LIMIT=20/minute` and the budget guard remain the backstop), `GEMINI_TRANSLATION_ENABLED=false` (the policy already refused Gemini; Sarvam did all translation). Memgraph `sleepApplication=true` (it does not sleep yet: egress to :443, likely Memgraph telemetry).

Measured: ~$0.0007 per chat turn; uncached p50 ~10-12 s, p95 ~14-16 s; crisis helpline 7/7 (English 0.4 s); persona/injection blocked 5/5; Supabase is ap-northeast-1 while Railway is us-west2.

Not fixed (owner decisions, evidence in lessons.md): grief and "And tomorrow?" routed to the crisis reply (semantic sim 0.748 and LLM escalation; gate not loosened); the speaker gate rejects ~41% of candidate spans (`speaker_unverified_or_not_guru`, data); conversational follow-ups ("shorter", "give an example", "the second one") always abstain; "What are the four sacred secrets?" abstains; relevance scorer sometimes returns a miscounted array and the seeker sees "couldn't finish checking" (kept indeterminate by design); admin list fails on a PostgREST embed of `auth.users` (`app/telemetry_db.py:get_admins`); on-device intent encoder never loaded on Railway (keyword DISTRESS defers to the LLM router; crisis pre-emption unaffected).

## Owner decisions recorded 2026-11-19 (evening loop, see docs/handoffs/LOOP_NOTES_2026_11_19.md)

- Memory-backfill archive tables dropped in production (migration `20261119135236_drop_memory_backfill_archives.sql`). A read-only check found 149 migrations applied, matching 149 repo files, with no archive tables left and the 18/1/5 live rows intact. The migration's orphan guard is inverted: it aborts when an archived row's live row was erased, so do not copy it for future backfills. `backend/scripts/ops/check_schema_drift.py --applied-versions` now checks repo files against the applied list.
- On-device MiniLM intent encoder stays OFF in production; OpenRouter JEV does intent. `ON_DEVICE_INTENT_ENCODER_ENABLED=false` is set on the Railway backend and worker and applies at the next deploy. Do not bake MiniLM into the image. `scripts/ops/validate_production_env.py` warns when a QUANTIZED_ONLY image runs with the encoder on.

## Remaining Owner Verifications

0. Raise the OpenRouter key limit: it is $5 lifetime (`limit_reset: None`), ~$3.39 left on 2026-11-19, not $5/day.
0. Commit/push the files above, re-attach the backend with `connect-service-source` + `commitSha`, and redeploy the worker so its new variables apply.
0. Backfill vectors for the 5 existing memories of user `f148995a` (tenant `oneness`). `CanonicalMemoryVectorIndex.repair()` also DELETES orphan vectors (no Postgres row), so it needs an explicit OK; the alternative is to re-save those memories from the Memory screen.
0. Post-deploy re-run: a Hindi turn (no Gemini ERROR), "What is suffering according to the teachings?" (serves), owner recall after backfill, one `GET /api/profile` per page load, the porn-addiction reply (support line), no "User anonymous exceeded" warning.

1. Ensure the key from `~/brain_kek_PRODUCTION_2026-11-19.txt` is backed up in your password manager, then remove the plaintext file (Keychain backup `mukthiguru-BRAIN_KEK-production-2026-11-19` remains).
2. Sign in on [https://askmukthiguru.lovable.app](https://askmukthiguru.lovable.app), send a test chat message, and open **My Reflections** (`/second-brain`) to verify the encrypted vault initializes cleanly.

## Gotchas learned (details in lessons.md)

- Never overwrite a production secret that protects stored data; set `BRAIN_KEK_NEXT` and rotate with `scripts/ops/rotate_brain_kek.py`.
- Historical data migrations across tenants must run under `SET LOCAL session_replication_role = 'replica';` so application write-triggers enforcing modern consent receipts do not fail closed on pre-consent rows.
- Never call `t('some.key')` without `{ defaultValue: '...' }` when critical UI/auth components rely on it.
- An automatic `setTimeout` modal on landing blocks the chat composer; keep check-ins inline as gentle banners with user-driven triggers.
- The backend is pinned to a commit: after every push, re-attach with `connect-service-source` + `commitSha`, otherwise nothing deploys.

## Status update, 2026-11-19 evening (written before /compact)

- Git: `main` has local commit `8d549a35` (agent fixes) NOT pushed. Owner commits and pushes (Claude's push is blocked). Backend on Railway still runs `fb404456`; after the push: re-attach backend with `connect-service-source` + `commitSha`, redeploy the worker, publish Lovable, then run the live smoke battery.
- Owner decisions still open: raise OpenRouter key limit (dashboard), crisis false positives / "nothing matters" gap (needs clinician), Memgraph (stop or fix sleep), Railway region (Asia), repair-vs-resave for the owner's 5 memory vectors (`vector_index.repair()` also deletes orphan vectors), Supabase advisors (9 SECURITY DEFINER fns, leaked-password protection off, `vector` in public), en.json label "General Spiritual Context" for unverified attribution (must read "Unverified attribution").
- Running now: ONE lead Opus agent (id a3a039c154cc240f5, resumable with SendMessage) doing everything left as a TDD autonomous loop; its notes file is `docs/handoffs/LOOP_NOTES_2026_11_19.md`. Scope: fix 16 golden-test regressions it introduced, retrieval quality (follow-ups, multi-part, exact-N scorer scores, latency), frontend leftovers (honest labels, 13-locale re-translation), recheck of the owner's commits, never-again guards (env preflight, drift checks, CORS header scan, post-deploy smoke battery), confidence report (target >= 98%). It may edit the four frontend files (ChatInterface, ChatMessage, MoodBanner, useTextToSpeech). It does not commit or push.
- Verified independently at 18:50 IST: frontend `vitest` chat/components/TeacherWords 163 pass; backend first-person subset had 17 failures (16 from the agent's unfinished edits, 1 old jev test double).
- Opus rate limit: 5-hour windows; if an agent dies with HTTP 429, resume it with SendMessage after the reset.
