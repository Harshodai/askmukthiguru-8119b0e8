## Goal

Resolve every failing SEO/AI-search finding at root cause, then rescan.

## Findings & Fixes

**1. Sitemap needs attention** (`http:sitemap`)
The scanner keeps re-flagging `/admin`, `/admin/login`, `/queries`, `/quality`, `/retrieval` even though they're admin-only and correctly Disallowed in `robots.txt`. Root cause: the scanner walks routes in `src/App.tsx` and can't tell admin nested routes apart from top-level ones. Fix by adding explicit `<meta name="robots" content="noindex, nofollow">` per admin page via `usePageMeta`, which makes the "not in sitemap" intentional and matches the robots.txt block. Also add an `/llms.txt` file so AI crawlers get a clean map of public routes only.

**2. Slow LCP** (`lighthouse:lighthouse_performance`)
Root cause: the homepage hero image likely lacks `fetchpriority="high"`, explicit dimensions, and preload; fonts may not use `font-display: swap`.

- Audit `HeroSection.tsx` — set explicit `width`/`height`, remove any `loading="lazy"` on the LCP image, add `fetchpriority="high"`.
- Add `<link rel="preload" as="image" href="/src/assets/hero-spiritual.webp" fetchpriority="high">` to `index.html`.
- Ensure every `@font-face` in the app has `font-display: swap`.
- Verify hero uses AVIF/WebP via `vite-imagetools` if not already.

**3. Low contrast** (`lighthouse:lighthouse_accessibility`)
Root cause: arbitrary `text-gray-*`, `text-muted-foreground/50`, or `placeholder:text-gray-*` classes on light surfaces. Sweep the codebase for these patterns and replace with design-system tokens (`text-foreground`, `text-muted-foreground`, no opacity <70%). Focus on landing sections, chat input placeholder, and footer.

**4. Long meta description on SpiritGuidesPage** (`agent_metadata:metadata_quality`)
Root cause: description is 176 chars. Rewrite to ≤160 in `src/pages/guides/SpiritGuidesPage.tsx`. Sweep all other guide pages to confirm each description is unique and ≤160 chars.

## Bonus AI-search hardening

- Create `public/llms.txt` with public routes only (home, chat, practices, spirit-guides, 6 guide pages, privacy, terms). No admin, auth, or dashboard routes.
- Verify `index.html` Organization JSON-LD and confirm each guide page carries valid `Article` schema with self-referencing `canonical` and `og:url`.

## Sequence

1. Fix meta description length (fast).
2. Sweep and fix low-contrast Tailwind classes.
3. Optimize LCP (hero image + font-display).
4. Add `noindex` to admin pages via `usePageMeta`; create `llms.txt`.
5. Mark all 4 findings fixed with explanations.
6. Publish so Lighthouse-based findings can re-evaluate against the live site.
7. Make sure these issues will never occur again and add suitable test cases or regressions

## Not doing

- Not migrating `public/sitemap.xml` to a generator script (existing static file is fine; guide pages are static, no dynamic rows).
- Not adding new content pages — the SEO content brief was already satisfied on the last pass.

Approve to proceed to build.