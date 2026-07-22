# AskMukthiGuru — Handoff

## 1. Goal
Ship a world-class, multilingual, mobile-first spiritual AI product (web + Android + iOS) grounded in Sri Preethaji & Sri Krishnaji doctrine. Zero-hallucination RAG, secure Supabase-backed auth/data, refined "Digital Ashram" UI, and safe production deployment on Railway/Lovable Cloud.

## 2. Current State
- **Build**: `bun run build` green, 17 routes prerendered.
- **Security**: Latest scan findings fixed or ignored with documented rationale in `@security-memory` (RLS on `kb_sources`, `kb_chunks`, `daily_teachings` storage, `ingest_jobs` cleanup, definer-fn EXECUTE revokes, SSRF redirect check, 12-char password policy).
- **UI**: World-class redesign phase 1–3 shipped — chat tokens, user bubble contrast, glass auth, Obsidian-style force-directed KG, profile hero + stat sparklines, Cormorant sacred typography, safe-area utilities.
- **Meditation**: Unified Serene Mind player with Preethaji audio + TTS fallback on 404; YouTube link; step/audio sync via `useMeditationAudio`.
- **i18n**: 6 real locales (en/hi/te/kn/ta/mr) + 8 fallbacks; parity regression test guards regressions. This turn wired `t()` in `ProfilePage` tabs, `PracticesPage` sections, `KGConceptMap` settings, and `DemoModal` tour; added missing keys to `en.json` and extended baselines.
- **Backend**: Railway prod healthy, embedding contract enforced (bge-m3 pinned, dimension guard), OKF doctrine bundle live.

## 3. Files Actively Edited (this turn)
- `src/locales/en.json` — added `landing.demo.*`, `profile.tabs.*`, `practices.dailyWisdom.badge`, `practices.sections.*`, `common.gurusName`.
- `src/test/__snapshots__/i18n_baseline_hi.txt`, `..._te.txt` — extended for new user-facing keys.
- `src/components/kg/KGConceptMap.tsx` — `t()` on help + settings drawer.
- `src/pages/ProfilePage.tsx` — `t()` on all 7 tab triggers.
- `src/pages/PracticesPage.tsx` — `t()` on Wisdom of the Day badge, gurus attribution, section headings.
- `src/components/landing/DemoModal.tsx` — `useTranslation` + `t()` on close/aria/newHere labels.
- `handoff_railway.md` — appended LightRAG persistent-volume runbook.
- `handoff.md` — this file.

## 4. Tried & Failed / Known Gaps
- **8 fallback locales (bn/gu/ml/ur/or/pa/as/sa)**: registered, users see English — deferred (needs Gemini batch translation, ~2 credits/locale).
- **Admin console i18n**: English-only by design; not attempted.
- **Google OAuth Playwright E2E**: cannot automate real Google IdP without dedicated test identities; single-redirect guard (sessionStorage cooldown) is in place and manually verified.
- **Forgot-password E2E via real inbox**: not automated; happy-path Playwright covers route mount + form render. Full inbox click-through would require an edge function generating a recovery link for a test user.
- **LightRAG persistent volume**: cannot mount Railway volumes from Lovable — documented in `handoff_railway.md` as a user action.
- **`pytest` `test_ingest_playlist_chord`**: fails locally without Redis; passes in Docker stack.

## 5. Next Step
1. Trigger a fresh SEO scan (`seo_chat--trigger_scan`); if `lighthouse:lighthouse_performance` still fails, add explicit `<link rel="preload">` for hero image and hero font in `index.html`.
2. Sweep remaining low-visibility strings in `MemoryManager` and `PracticeDetailPage` for `t()` coverage (~15 sites left per `I18N_GAPS.md`).
3. Migrate `public/sitemap.xml` to a build-time generator so route changes stay in sync.
4. Publish once the next scan is green.
