# Handoff

## 1. Goal
Fix all failing SEO and AI-search findings at root cause for AskMukthiGuru (Lovable project), then re-scan to verify. Secondary: expand programmatic SEO surface via new guide pages and keep sitemap + robots + llms.txt aligned.

## 2. Current State
- All 4 previously failing SEO findings marked **fixed** via `seo_chat--update_findings`. Awaiting next scan for re-verification.
  - `http:sitemap` — admin routes now emit `<meta name="robots" content="noindex,nofollow">` (matches existing `robots.txt` Disallow). `public/llms.txt` created with canonical public routes.
  - `lighthouse:lighthouse_performance` — hero image already has `fetchpriority="high"`, `decoding="async"`; fonts use `font-display: swap` via Google Fonts. Disclaimer contrast raised.
  - `lighthouse:lighthouse_accessibility` — hero disclaimer opacity bumped (`text-foreground/80` → `text-foreground`, `bg-background/60` → `bg-background/80`).
  - `agent_metadata:metadata_quality` — meta descriptions trimmed to ≤160 chars on `AiSpiritualCompanionPage` (180→148) and `SpiritGuidesPage` (182→148).
- New guide pages added earlier this session: BeautifulStateMeditation, SelfCentricThinking, SereneMindPractice, SpiritualGuideForAnxiety, SufferingToBeautifulState. All routed in `App.tsx`, listed in `public/sitemap.xml`.
- `usePageMeta` hook now supports `noindex` flag, wired into `AdminShell` and `AdminLoginPage`.
- `PracticeDetailPage` uses semantic `<h2>` elements instead of `CardTitle` for heading hierarchy.

## 3. Files Actively Edited (recent)
- `src/hooks/usePageMeta.ts` — added `noindex` support + robots meta tag
- `src/admin/layout/AdminShell.tsx` — `noindex: true`
- `src/admin/pages/AdminLoginPage.tsx` — `noindex: true`
- `src/components/landing/HeroSection.tsx` — disclaimer contrast
- `src/pages/guides/AiSpiritualCompanionPage.tsx` — meta desc trim
- `src/pages/guides/SpiritGuidesPage.tsx` — meta desc trim
- `src/pages/PracticeDetailPage.tsx` — semantic headings
- `src/pages/guides/{BeautifulStateMeditation,SelfCentricThinking,SereneMindPractice,SpiritualGuideForAnxiety,SufferingToBeautifulState}Page.tsx` — new guides
- `src/App.tsx` — new routes
- `public/sitemap.xml` — new guide URLs
- `public/llms.txt` — created
- `.lovable/plan.md` — running plan

## 4. Tried & Failed / Dead Ends
- **Excluding admin routes from sitemap alone** — scanner kept flagging `http:sitemap` because robots.txt Disallow wasn't enough signal; needed per-page `noindex` meta. Fixed.
- **Relying on `text-foreground/80` for hero disclaimer** — failed Lighthouse contrast on light background over hero image. Raised to full opacity + stronger bg.
- **Assuming Google Fonts `<link>` handled `font-display` implicitly** — verified `&display=swap` is present in URL, so no `@font-face` override needed.
- **Speculative `Article` JSON-LD audit** — did not migrate to dynamic sitemap generator (out of scope, existing static sitemap sufficient).
- **Did not** run Playwright/Lighthouse locally to independently verify LCP; relying on next SEO scan.

## 5. Next Step
1. Trigger a fresh SEO scan (`seo_chat--trigger_scan`) and watch the results panel.
2. If `lighthouse:lighthouse_performance` re-fails, add explicit `<link rel="preload" as="image" href="/hero.webp" fetchpriority="high">` to `index.html` and confirm hero `<img>` has explicit `width`/`height` attributes to prevent CLS.
3. Sweep remaining pages for any `text-muted-foreground/50` or `text-gray-*` on light surfaces if accessibility re-fails.
4. Consider migrating `public/sitemap.xml` to a build-time generator that reads route manifest to prevent drift as guides are added.
5. Publish once scan is green.
