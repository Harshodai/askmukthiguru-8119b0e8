# WhatsApp: secure website-linked companion

## Goal

Use the existing WhatsApp Business number as another channel for AskMukthiGuru: website signup, linked profile, sourced teaching replies and optional memory. Keep the phone app working. No Lovable connector, no number deletion/migration, no fabricated teachings.

## Findings and activation gates

- Current branch has `/link-whatsapp`, Profile connection controls, FastAPI linking endpoints and a Celery WhatsApp task. Reuse and repair these; the older anonymous bridge is not the only implementation now.
- Verified source defects: linking UI preselects history and memory consent; STOP/RESET send confirmations without persisting their promised effect; the worker calls `/api/chat` without authenticated linked identity and with an unsigned deterministic session ID; delivery acceptance is logged as delivery, without durable callback readback. Existing screens do not prove an operational channel.
- Railway `/api/healthz` responds; teaching readiness and WhatsApp delivery remain unverified.
- Owner reports Full control for both Meta assets. Exact Lovable access error is still needed; account name is not evidence of its cause.
- Keeping the phone app requires Meta's supported coexistence onboarding. Current documentation requires an eligible Tech Provider/Solution Partner; an ordinary direct API token is insufficient to promise coexistence.
- Meta's official AI-provider page, fetched on 2026-11-22, excludes India from its permitted general-purpose-assistant markets. Confirm the actual AskMukthiGuru use-case classification before activation: a spiritual scope or bank-style menu is not proof of exemption. Do not disguise an AI companion as customer support.
- Review current WhatsApp fees before sending; do not assume service messages are free.

## Work, in order

### 1. Confirm setup without risking the existing number

Diagnose the supplied access error, inspect owner-authorized Meta configuration, and establish an eligible coexistence path. Avoid Lovable connectors. If a provider or our own Tech Provider setup is required, surface that choice and its cost/approval requirements before onboarding. Do not change the existing number while this is unresolved.

Ask whether a Meta Developer app with WhatsApp already exists. Owner supplied the Business phone number and reports Full control; neither establishes app approval, asset assignment or a working API token. Correct misleading existing onboarding instructions using Meta's current v4 coexistence requirements. Do not assume the dashboard's ordinary Add Number flow enables coexistence.

### 2. Secure signup and account linking

Reuse website signup/sign-in and age gate. Add a linking confirmation page and Profile connected-number controls. Verify website identity plus confirmation from the originating WhatsApp conversation. Use short-lived, one-time opaque challenges; forwarded links and previews must not approve linking. No website session tokens or passwords in WhatsApp.

Repair existing screens instead of duplicating them: optional history and memory start unchecked; strip link secrets from the address bar and stale auth-return storage; make unavailable status distinguishable from disconnected; retain retry and explicit return-to-WhatsApp controls. Require a fresh originating-phone confirmation after website approval so a forwarded link cannot bind another account.

### 3. Reuse the real teaching workflow

Resolve channel identity to the linked user and tenant on the server, then invoke existing safety and teaching services. Preserve exact teacher wording, attribution, rights/integrity checks and honest abstention. Return readable text with real clip/source links. First release: one-to-one text only; no promise of website animations/embedded players inside WhatsApp.

### 4. Optional history, memory and Profile continuity

Separate account linking, conversation sync and long-term memory consent. Default optional storage off. Persist only explicitly enabled channel history, and save remembered content only through existing consent-gated memory services. Label WhatsApp provenance; verify website history/Profile readback. Add disconnect, memory-off and forget controls; revoke queued writes and cover channel stores during erasure. Do not import old phone chats or feed messages into model training/corpus ingestion.

### 5. Reliable receiving, replies and release checks

Audit/harden existing receiver: signatures, intended recipient, durable queue/restart recovery, ordered processing, duplicate events, send outcomes and delivery callbacks. Do not launch with daemon-thread-only processing after acknowledgement. Respect the 24-hour reply window; defer reminders/campaigns/templates until separately approved. Configure a real human-help destination and coexistence handoff so manual phone replies do not compete with automation.

Run focused security and journey tests, then the real flow: incoming message → signup → both-channel link → sourced reply → delivered callback → optional save → website readback → revoke/unlink. No completion claim from mocks or liveness checks.

### 6. Familiar, bank-style WhatsApp experience

Use concise native WhatsApp lists/reply buttons where appropriate: Ask a question, Today's practice, My account, Privacy, and Human help. Accept ordinary text without trapping users in menus. Reuse saved website language; offer an explicit language choice for new users. First rollout remains text-only and makes no voice-note claim.

Show one readable sourced reply rather than repeated promotional messages. Keep teacher wording intact; split long replies at safe boundaries instead of silently truncating quotes or source links. Offer retry when service fails. Persist STOP/START, reset only the stated conversation context, and pause automation during human handoff so phone replies do not compete. Human help is offered only once a real destination and operating availability are configured.

This borrows banking chat usability, not banking accreditation or end-to-end secrecy from Meta. Never request passwords, website tokens, bank details or payment PINs. Templates, reminders, campaigns and old-chat imports remain outside this release.

## Technical approach

- Reuse existing `whatsapp_bot/wa_bot.py`, website auth/return handling, backend composition root, teaching coordinator and memory-consent services. Keep React/Vite; no whole-app hosted-stack migration required merely for a direct external HTTPS receiver.
- Channel-auth endpoints must be server-only and validate both trusted caller and live binding; never fabricate Supabase user JWTs, store refresh tokens in the bot or accept arbitrary user IDs.
- Link challenges: random opaque values, hashes at rest, short expiry, atomic single use, two-channel proof, no sensitive logging/referrers/analytics. GET previews do not mutate state.
- Reuse persistent storage/encryption and existing queue patterns; design RLS/grants and denial tests before any migration. No production schema/data mutation or deploy without its approval.
- Target current FastAPI receiver and Celery worker, not a second parallel bot. Validate configured recipient/account identifiers, require signatures, persist inbound acceptance before acknowledgement, recover queued work and enforce per-chat ordering. Missing queues must not cause slow inline processing after falsely claiming durable acceptance.
- Replace expired hardcoded Graph versions with a currently supported configured version; disable credentialed redirects; preserve outbound message IDs and durable signed status transitions. API acceptance means accepted, never delivered.
- Resolve live user/tenant/consent through existing trusted coordinator services; never call the public chat endpoint with a fabricated anonymous session or expose a public user-ID override. Recheck consent and binding before pending history/memory writes.

## Acceptance and handoff

- Automated tests: consent off by default; forwarded/expired/replayed linking denied; wrong phone/account rejected; persistent STOP/START and RESET; duplicate events/restart recovery; memory-off/revoke races; closed-window sends; accepted versus delivered callbacks.
- Browser checks: link/signup/return and Profile privacy/disconnect on phone and desktop with authenticated account state.
- Live activation packet: approved coexistence and use case, secure runtime credentials, current callback subscription, real incoming message and reply, matching delivered callback, website readback and revoke. Dependency-complete Python tests run in CI or the locked test image; sandbox static checks do not replace them.
- Blocked until owner supplies Meta onboarding/account access and confirms real human-help destination. Secure secrets use runtime settings, never chat. Provider cost, number changes and deployment require explicit approval; no connector is introduced.
- Preserve existing safety, tenant, memory, rights and cache boundaries; memory-off turns must not hydrate/store private context through a side path.
- Secrets go to the actual deployed sender/receiver runtime through secure settings. Explain setup first; never ask for secrets in chat.

## Scope and approval

Approval starts implementation and isolated tests. It does not authorize deleting/migrating the number, spending, historical imports, public activation, mass messaging, unrelated UI changes, or production deploy/data mutation. Meta eligibility, secure credentials and real message testing remain external dependencies.

Research, sources and acceptance detail: `docs/plans/2026-11-21-whatsapp-direct-research.md`.