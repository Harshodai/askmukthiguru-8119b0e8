# Guide launch signup and structured-data verification

## Build
1. Add a shared, accessible launch-update email signup to the existing public guides. Keep a visible email label, explicit unchecked contact consent, Privacy link, keyboard access, clear pending/success/error states, and retained input on failure. No account signup or login changes.
2. Reuse `waitlist_entries` for consented launch-update subscribers. The current table has RLS enabled but no API grants or policies, and the existing landing form depends on the unavailable teaching backend. Add a validated Supabase intake path independent of Chat; prevent public reads, updates and deletes, suppress duplicate-email disclosure, and reject missing consent. Add abuse protection and bounded input handling.
3. Make stored subscribers accessible to the owner through the existing protected admin experience, newest first. No subscriber addresses in public responses or logs. Email sending is not configured: store subscriptions now; do not pretend updates or owner notifications are being sent.
4. Strengthen the **existing** Article and FAQPage data in AI Spiritual Companion and Serene Mind guides with stable self-referencing identifiers, publisher and language metadata. Keep FAQ answers sourced from the same visible translated content. Do not invent publication dates, teacher quotations, ratings, images or affiliation.
5. Audit the five referenced marketing documents against completed work. Save a new concise execution-status document without overwriting the originals. Finish remaining in-project discovery/navigation checks; retain Chat and custom domain as owner tasks.

## Verification
- Focused tests: email normalization/validation, consent rejection, duplicate behavior, failure recovery, subscriber access isolation, and matching guide structured-data values.
- Browser: real signup and stored-row confirmation, cleanup of only the test row, keyboard flow, error retry, guide-to-practice/Trust navigation, and phone/tablet/desktop layout.
- Check preview diagnostics and commit the changes. Report any unavailable external verification honestly.

## Eligibility and external boundaries
- Valid Article/FAQ markup does not guarantee enhanced search results. Google generally limits FAQ rich results to authoritative government and health sites; no such eligibility claim for AskMukthiGuru.
- Per-route metadata currently appears after JavaScript rendering; verify that output without claiming all crawlers receive it. No hosted-stack migration in this task.
- Publishing is required before changes reach the live site. Directory submissions, outreach, paid listings, duplicate-host redirects, recrawl, affiliation and content-rights decisions remain dependent on authorized accounts, permissions or owner confirmation.
- Owner emails require a verified owned email domain and a destination address. Subscriber campaigns need a configured sender and unsubscribe handling before sending; this task collects opt-ins, not an automatic campaign.

## Technical approach
Reuse existing guide content, design-system fields/buttons, Supabase client, `usePageMeta`, admin guards and subscriber table. Use migration tooling for grants/policies, server-side schema validation for intake, and existing admin permission contracts rather than a new role system. No changes to Chat, teaching retrieval, corpus, domains or Railway.