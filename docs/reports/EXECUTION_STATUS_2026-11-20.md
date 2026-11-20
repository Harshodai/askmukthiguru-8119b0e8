# Execution Status and Marketing Audit Report

**Date:** 2026-11-20  
**Status:** In-Project Work Complete; External & Infrastructure Tasks Retained by Owner  
**Authority:** `.claude/tasks/2026-11-20-guide-launch-signup-and-structured-data.md`  
**Referenced Documents:** `~/Downloads/Visitor growth and launch/` (`plan.md`, `plan_v2.md`, `research.md`, `launch_distribution_kit.md`, `consolidation_and_permissions.md`)

---

## 1. Executive Summary

This audit assesses the state of AskMukthiGuru following the implementation of guide launch signups, admin subscriber management, strengthened structured data, and in-project navigation/discovery enhancements against the recommendations across the five marketing and launch documents.

### High-Level Status
- **In-Project Code & Architecture:** **COMPLETED**
  - Accessible, consent-first launch update email signup on public guides.
  - Supabase intake independent of Chat via `subscribe_launch_updates` RPC and RLS policies on `waitlist_entries`.
  - Protected owner subscriber table under existing admin MFA (AAL2) guards, with honest notice of unconfigured email sending.
  - Strengthened Article and FAQPage JSON-LD using self-referencing `@id` identifiers, publisher organization, and in-language tags; no invented dates, ratings, images, or affiliations.
  - Prerendering of 29 routes updated; sitemap verified at 19 public URLs (including `/trust` and `/guides/spirit-guides`).
- **External Dependencies & Owner Responsibilities:** **BLOCKED / RETAINED BY OWNER**
  - Custom domain purchase and configuration.
  - Live Chat teaching service restoration (Railway/backend infrastructure).
  - Production database migration and frontend hosting deployment.
  - Vercel host redirect deployment and Google Search Console recrawl requests.
  - Directory submissions (Product Hunt, TAAFT) and community outreach (pending permissions).
  - Outbound email sending setup (sender domain verification, DKIM/SPF, unsubscribe handling).

---

## 2. Audit of the Five Marketing Documents

### 2.1 `plan.md` & `plan_v2.md` (Visitor-Growth Plan)

| Action / Proposal | Status | Implementation & Evidence | Remaining Blockers |
|---|---|---|---|
| **Rank 1: Restore and verify teaching on `/chat`** | **Blocked (Owner Task)** | Intentionally untouched per plan boundary. Code keeps honest fallback messaging on `/chat` when backend is unreachable. | Owner infrastructure decision; Railway stack remains inactive. |
| **Rank 2: Connect a custom domain** | **Blocked (Owner Task)** | `src/lib/domain.ts` supports `VITE_PUBLIC_APP_URL` and falls back to `askmukthiguru.lovable.app`. No premature domain string edits. | Owner selection and DNS configuration of brand domain. |
| **Rank 3: Consolidate duplicate hosts & close sitemap gaps** | **Partly Done** | **Done:** `scripts/prerender-seo.mjs` and `public/sitemap.xml` include 19 routes (added `/guides/spirit-guides` and `/trust`). Test `src/test/sitemapCoverage.test.ts` passes.<br>**Blocked:** Vercel host redirects. | Vercel account access confirmation and post-domain redirect deployment. GSC sitemap re-submission. |
| **Rank 4: Improve AI Spiritual Companion guide** | **Done** | English title/intro focused on AI spiritual guidance; citation attribution, abstention policies, and service limits clearly articulated. Added `<LaunchUpdatesSignup source="guide_ai_spiritual_companion" />` and bidirectional links to `/practices/serene-mind` and `/trust`. | External ranking and impressions depend on search engine indexing post-publish. |
| **Rank 5: Publish one useful teacher-specific guide** | **Done** | Reused and strengthened `/guides/serene-mind-practice` with practice guidance, breath instructions, official Oneness products link as source reference, and `<LaunchUpdatesSignup source="guide_serene_mind" />`. | No mass production of thin pages; translations preserved without unverified AI synthesis. |
| **Rank 6: Low-cost directory listing & outreach** | **Blocked (External)** | Drafts and evaluation completed in `launch_distribution_kit.md`. No submission made, no funds expended. | Requires verified accounts, directory fee approval (TAAFT $437 check), and community organizer consent. |

### 2.2 `research.md` (Marketing Research)

| Research Finding / Recommendation | Status | Assessment & Status in Codebase |
|---|---|---|
| **Own Presence & Crawlability** | **Done** | Public guides render full text; static HTML prerendered for 29 routes. Canonical tags in place across all routes. Sitemap gaps (`/trust`, `/guides/spirit-guides`) resolved in codebase. |
| **Duplicate Deployment (`askmukthiguru-8119b0e8.vercel.app`)** | **Blocked (Owner)** | Documented in `consolidation_and_permissions.md`. No redirect deployed without owner confirmation of Vercel project access. |
| **Affiliation Disclosure & Teacher Integrity** | **Done** | Code strictly enforces honest attribution. No fabricated claims of endorsement, affiliation, or official certification added. Citation boundaries documented. |
| **Trust & No Made-Up Quotes** | **Done** | System adheres strictly to repository invariants (verbatim quotes, abstention gates). Structured data omits fabricated dates, ratings, and quotes. |
| **India & Crisis Boundaries** | **Done** | Tele-MANAS, 112, and Vandrevala helplines maintained in safety disclaimer and emergency crisis banners. |
| **Listing Candidates (TAAFT, Futurepedia, Product Hunt)** | **Documented** | Identified paths; no unverified submissions or payments attempted. |

### 2.3 `launch_distribution_kit.md`

| Item | Status | Verification & Evidence |
|---|---|---|
| **Posting Conditions** | **Enforced** | Launch materials kept practice-first; Chat-led launch messaging withheld pending teaching backend availability. No unverified user counts or claims. |
| **Product Hunt Draft** | **Ready (Draft)** | Draft text kept to guidelines (name ≤40 chars, tagline ≤60 chars, description ≤500 chars). Submission requires personal owner account. |
| **Directory Assessment (TAAFT)** | **Analyzed** | Official $437 submission verified on checked page; unverified $49 claims noted as unreliable. Paid listing deferred. |
| **Social Posts (LinkedIn, X)** | **Ready (Draft)** | Practice-first drafts prepared with UTM tracking parameters. No automated posting attempted. |
| **Organizer Permission Template** | **Ready (Draft)** | Draft letter prepared for individual outreach to verified cluster leaders without spam or mass collection. |

### 2.4 `consolidation_and_permissions.md`

| Requirement | Status | Current Reality & Action |
|---|---|---|
| **Consolidation Sequence** | **Documented** | Redirect strategy defined: wait for custom domain, configure 301 from Vercel host, test query-string preservation, update `VITE_PUBLIC_APP_URL`. |
| **Affiliation Status** | **Enforced** | Neither "officially affiliated" nor "independent/unaffiliated" declared until owner confirms relationship. Official Oneness link used strictly as source context. |
| **Content Boundaries** | **Enforced** | No audio republication, unauthorized transcriptions, or summaries of copyright-restricted works (e.g. *The Four Sacred Secrets*) introduced. |

---

## 3. In-Project Implementation Summary

### 3.1 Guide Launch Signup & Intake
- **Client Sanitization & Pre-check (`src/lib/launchUpdates.ts`):**
  - Trims, lowercases, and caps input at 254 characters (`sanitizeLaunchEmail`).
  - Validates basic email pattern (`isPlausibleLaunchEmail`).
  - Restricts sources to DB allowlist: `guide_ai_spiritual_companion`, `guide_serene_mind`, `guide_spirit_guides`, `guide_beautiful_state`, `guide_self_centric`, `guide_anxiety`, `guide_suffering`.
  - Submits via `supabase.rpc('subscribe_launch_updates', { p_email, p_consent: true, p_source })`.
  - Suppresses duplicate status; never logs or leaks email addresses in errors or returns.
- **Accessible UI Component (`src/components/guides/LaunchUpdatesSignup.tsx`):**
  - Visible `<Label>` (not `sr-only`).
  - Checkbox unchecked by default; explicit inline validation before submission.
  - Active states: `idle`, `submitting` (disables inputs and button, sets `aria-busy`), `success` (`role="status"`), `error` (`role="alert"`).
  - Retains typed email on failure for seamless single-click retry.
  - Explicit copy: "We will contact you only about launch updates. No account needed."
  - Direct router link to `/privacy`.

### 3.2 Database & Security Model (`supabase/migrations/`)
- Reuses `waitlist_entries` table.
- **Ingest Trigger & RPC (`20261120023738_...` & `20261120023830_...`):**
  - Trigger `validate_launch_subscription` enforces `consent_to_contact = true`, email regex, source allowlist.
  - Concurrency protected by transaction advisory lock `pg_advisory_xact_lock(811901119)`.
  - Rate limiting enforced: max 100 signups per 10 minutes.
  - Duplicate email inserts silently return `NULL` to prevent duplicate-email disclosure.
- **Row Level Security (RLS):**
  - `anon` and `authenticated`: `INSERT` allowed with check (`consent_to_contact = true` and valid source).
  - `SELECT`: Restricted exclusively to authenticated admins with MFA (`auth.jwt()->>'aal' = 'aal2' AND has_role(..., 'admin')`).
  - `UPDATE` & `DELETE`: Denied to all public/authenticated users (fails closed).
  - Verification suite updated in `scripts/verify_rls_policies.py` and `backend/scripts/verify_rls_policies.py` (kept byte-identical per Invariant X1).

### 3.3 Admin Experience (`/admin/subscribers`)
- **Loader (`src/admin/lib/waitlistSubscribers.ts`):**
  - Selects `id, email, source, consented_at` ordered by `consented_at DESC`.
  - Errors sanitized to prevent address leakage.
- **Page (`src/admin/pages/WaitlistSubscribersPage.tsx`):**
  - Accessible under `AdminRoute` and `AdminShell` navigation.
  - Displays subscriber count, email, source, formatted date, skeleton loading, error retry, and empty state.
  - Visible non-misleading notice: *"Email sending is not configured. These addresses are collected only; no update or owner notification is being sent."*
  - No send action controls present.

### 3.4 Structured Data (Schema.org JSON-LD)
- **Builder (`src/lib/guideStructuredData.ts`):**
  - Emits `@graph` with `Article` (`#article`) and `FAQPage` (`#faq`).
  - Self-referencing IDs linked to canonical URLs and origin organizations (`#organization`, `#website`).
  - Publisher metadata included with name `'AskMukthiGuru'`.
  - `inLanguage` matched to active translation locale.
  - FAQ questions and answers strictly mapped from the identical translated `content.faqs.items` rendered in `<dl>`.
  - **Zero Fabrication:** No publication dates, modification dates, rating aggregates, review counts, awards, or false teacher affiliations.
- **Prerendering Integration (`scripts/prerender-seo.mjs`):**
  - Static HTML includes Article metadata with `@id` and publisher URL.
  - Full Article + FAQPage graph rendered post-JS without prose drift.

---

## 4. Verification Evidence

### 4.1 Automated Test Battery
All focused and regression test suites executed and passed:
1. `src/test/launchUpdates.test.ts` (7 tests passed):
   - Whitespace trimming, lowercase normalization, 254-char truncation.
   - Rejection of malformed email formats.
   - Verification of `p_consent: true` and source parameter passing.
   - Verification that email is never leaked in success or error payloads.
   - Verification of source allowlist parity.
2. `src/test/components/LaunchUpdatesSignup.test.tsx` (5 tests passed):
   - Visible label and unchecked consent box on initial render.
   - Form submission refusal and alert without consent.
   - Pending state transitions and `aria-busy` toggling.
   - Retained email input on failure and successful subsequent retry.
   - Malformed address rejection before network request.
3. `src/test/guideStructuredData.test.tsx` (3 tests passed):
   - Structure verification: self-referencing `@id`, publisher, language, schema context.
   - `AiSpiritualCompanionPage`: Injected JSON-LD matches rendered `<dt>` and `<dd>` text; forbidden fields absent.
   - `SereneMindPracticePage`: Injected JSON-LD matches rendered `<dt>` and `<dd>` text; forbidden fields absent.
4. `src/test/admin/WaitlistSubscribersPage.test.tsx` (6 tests passed):
   - `listWaitlistSubscribers`: Columns and newest-first sort verified; generic error sanitization confirmed.
   - UI states: Skeleton on loading, generic error alert on failure, empty state card, full table rendering with disclaimer and no send controls.
5. Python Invariant Regressions:
   - `backend/tests/test_repo_layout.py` (5 tests passed): Confirmed shared scripts between `scripts/` and `backend/scripts/` remain byte-identical.
6. TypeScript & Linting:
   - `npx tsc -b`: 0 errors.
   - `npx eslint` across touched files: 0 errors, 0 warnings.
7. Build & Prerender:
   - `npm run build`: 29 routes prerendered cleanly. Inspected `dist/guides/ai-spiritual-companion/index.html` and `dist/guides/serene-mind-practice/index.html`.

---

## 5. Technical Boundaries and Honest Disclosure

1. **Structured Data Rich Results:**
   - Valid Article and FAQPage markup has been implemented and tested.
   - **Google Rich Results Limitation:** Google restricts FAQ rich results primarily to authoritative government and health sites. AskMukthiGuru is a spiritual inquiry platform; search results will not automatically gain rich FAQ snippets. No claim of guaranteed rich snippet display can be made.
2. **Client-Side Rendering vs Static Crawlers:**
   - Static HTML contains base Article structured data and prerendered content.
   - Dynamic FAQPage schema is injected by `usePageMeta` during JavaScript hydration.
   - Modern search crawlers (Googlebot) execute JavaScript, but simpler or strict no-JS crawlers will receive only the static Article block.
3. **Email Subscriptions:**
   - Signups are securely collected and stored in `waitlist_entries`.
   - **No Outbound Delivery:** There is currently no active email provider (e.g., Resend, Postmark, SendGrid), DNS configuration (SPF/DKIM/DMARC), or automated campaign handler connected. Stored addresses cannot receive emails until infrastructure is provisioned.
4. **Publishing Requirement:**
   - Changes reside locally in the repository. The Supabase database migrations and built frontend assets must be applied to live staging/production before taking effect.
5. **External Tasks:**
   - Domain management, custom host configuration, Vercel redirects, Google Search Console indexing requests, and official Oneness outreach remain owner responsibilities.
