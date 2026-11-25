# Launch emails, linked WhatsApp and guide discovery

## Outcome

Visitors enter through a clear launch page, read a useful guide, and explicitly join the launch list. Each signup receives a private unsubscribe link. WhatsApp reuses the website account and teaching workflow, with separately consented storage, while the Business phone app stays working.

## Current evidence

- Both main guides already contain the shared signup form and Article/FAQ data. Reuse these rather than adding duplicate forms or schemas.
- Signup currently writes to `waitlist_entries`; a private unsubscribe token exists, but no sender or email credentials are configured. Do not claim emails are sent yet.
- This project uses externally managed Supabase. Lovable's managed app-email infrastructure is unavailable; launch campaigns also require a dedicated marketing service.
- WhatsApp has linking/Profile screens, receiver and worker code, but durable delivery tracking and trusted linked-user teaching execution remain incomplete. Earlier public-screen tests do not establish live account sync.
- Keeping the existing phone app requires supported Meta coexistence onboarding. A phone number and reported Full control do not establish API access or eligibility.
- Existing preview diagnostics contain errors. Resolve relevant preview failures and distinguish static checks from dependency-complete and live checks.

## 1. Subscriber email delivery

Use Brevo provisionally, or the owner's existing service when supplied. Hold provider-specific connection and sending until the service is chosen. Sender identity and domain must be verified before claiming production delivery.

- Integrate the chosen provider server-side; never expose subscriber tokens, provider keys or subscriber browsing in the browser.
- Retain the existing consent, source validation, anti-enumeration response and protected owner access.
- On accepted signup, schedule one confirmation using an existing durable job path or the smallest persistent delivery record that supports retry. Couple intake and the job atomically; do not rely on a browser fire-and-forget call.
- Include the private unsubscribe/erase link, clear sender identity and purpose. Remove link secrets from browser-visible analytics/referrers; GET link previews must not erase a subscription.
- Handle provider suppression, retries and duplicate signups without turning public signup into an unlimited resend endpoint. Recheck consent before queued sends. Future campaigns must honor the same unsubscribe suppression and retention policy.
- Verify the existing subscribers' confirmation/backfill path without sending an unapproved mass campaign.
- Send one signup confirmation to each owner-provided test address, `kharshaengineer@gmail.com` and `harshakolluru1@gmail.com`, through the real intake/delivery path once configured. These are test sends, not authorization for recurring campaigns. Verify provider acceptance and delivery events where available; inbox receipt requires owner confirmation.
- Test correct-token erasure, wrong-token denial, duplicate-send prevention, provider failure/retry and revoked-consent suppression.

## 2. Complete the existing WhatsApp bot

Continue the approved secure WhatsApp plan; no second bot, Lovable WhatsApp connector, number disconnect or API-only migration.

- Validate raw-body signatures and configured recipient/account identifiers. Persist inbound acceptance before acknowledging and recover work after restarts; avoid slow inline fallback masked as durable queue success.
- Complete single-use, expiring account linking with both website authentication and fresh confirmation from the originating WhatsApp conversation. Forwarded links, GET previews, expired/replayed challenges and wrong-account confirmations must not bind accounts.
- Execute the real teaching coordinator with server-resolved live account identity and tenant, not an unsigned anonymous ID or invented user JWT. Preserve crisis/safety order, rights, speaker and integrity gates, exact quotes and honest abstention; never enable teaching-generation fallback.
- Keep optional history and memory off by default. Reuse existing consent-gated services and account erasure, rechecking binding and consent before queued writes. Verify website Profile/history readback; linking alone must not hydrate/store private memory.
- Offer concise native menus and plain-text questions, saved language, account/privacy controls, persisted STOP/START and scoped RESET. Human handoff is available only after a real destination is configured; pause automation during handoff.
- Use a currently supported configured Graph API version, validated recipients and no credentialed redirects. Persist outbound message IDs and signed delivery callbacks. Accepted is not delivered. Enforce the 24-hour reply window; campaigns/templates/old-chat imports are outside this release.
- Update Meta setup guidance from current official documentation: eligible existing-number coexistence, app/asset permissions, callback setup, secure runtime settings, use-case classification and costs. Do not disguise an AI companion as customer support or promise Indian-market eligibility without confirmation.

**Activation gates:** approved coexistence and use case, actual Meta app/number credentials in the deployed runtime, authorized deployment, real human-help destination, and incoming message → signup → two-channel link → sourced reply → delivered callback → optional save → website readback → unlink verification. Number/account changes and paid onboarding need separate explicit approval.

## 3. Launch funnel

- Add `/launch` as a focused branded entry page, using the existing Golden Hour design, approved existing imagery and reduced-motion-safe transitions.
- Primary CTA opens the spiritual-companion guide; secondary CTA opens the Serene Mind guide. Reuse the existing accessible email signup as the launch-list conversion, with unchecked consent, visible labels, preserved drafts and announced success/error states.
- Add a validated launch-page signup source consistently on client/server, preserving all existing source and rate-limit rules. Link the page from existing public navigation and add it to the sitemap.
- Do not advertise unavailable WhatsApp, claim affiliation, invent teacher quotes or imply clinical treatment. No unrelated homepage or Chat-layout rebuild.

## 4. Search improvements

- Research search intent and current ranking results before selecting target phrases; use available search data and disclose low-volume/unknown evidence.
- Prioritize the spiritual-companion and Serene Mind guides, then relevant existing spiritual/self-help guides and Chat metadata. Use literal, accurate titles and descriptions plus readable headings/internal links; keep translations coherent.
- Target spiritual reflection, spiritual guidance and short meditation/self-help intents without medical promises or teacher impersonation. Keywords belong naturally in content and applicable Article fields; obsolete meta-keywords tags are not a ranking strategy.
- Keep one self-referencing canonical per page, matching social metadata and valid existing Article/FAQ data. Do not add FAQ merely to claim rich-result eligibility or duplicate existing schemas.
- Reuse the existing per-page metadata path unless it demonstrably fails. Update static sitewide fallback metadata only where needed. The Vite site remains client-rendered: per-page social previews for non-JavaScript crawlers are not guaranteed; no unrequested framework migration.
- Explain that live metadata and funnel changes appear after publishing; no automatic publish or search-ranking guarantee.

## Validation and scope

- Focused frontend, unsubscribe, source-validation, backend link/consent/queue/delivery and access-isolation tests. Backend dependency-complete tests run in CI or the locked test image when unavailable locally; no package installation solely for release checks.
- Phone/tablet/desktop funnel → guide → signup and recovery checks, including keyboard access and reduced motion. Authenticated linking/Profile checks must use real signed-in state; mocks are labeled as mocks.
- Real emails and WhatsApp flows are complete only with service evidence, not screenshots of empty screens or health liveness.
- Update existing roadmap/task records and applicable architecture/docs; commit reviewed source changes. No unrelated security finding changes, corpus writes, number migration, spending, mass campaign, or production deployment without authorization.

## Owner inputs still needed

1. Email service choice and verified sender/domain setup; connect securely after selection, never paste credentials in chat.
2. Eligible Meta coexistence/app onboarding and use-case confirmation, then deployed-runtime credentials through secure settings.
3. Real human-help destination/availability and authorization for live WhatsApp deployment/testing.

Ponytail and Token Optimization shape this plan: repair existing flows, smallest durable solution, focused tests, batched independent work.