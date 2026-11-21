# WhatsApp: secure website-linked companion

## Goal

Use the existing WhatsApp Business number as another channel for AskMukthiGuru: website signup, linked profile, sourced teaching replies and optional memory. Keep the phone app working. No Lovable connector, no number deletion/migration, no fabricated teachings.

## Findings and activation gates

- Existing bridge supports anonymous Meta chats, not signed-in profiles or website memory/history.
- Railway `/api/healthz` responds; teaching readiness and WhatsApp delivery remain unverified.
- Owner reports Full control for both Meta assets. Exact Lovable access error is still needed; account name is not evidence of its cause.
- Keeping the phone app requires Meta's supported coexistence onboarding. Current documentation requires an eligible Tech Provider/Solution Partner; an ordinary direct API token is insufficient to promise coexistence.
- Check Meta's AI-use terms for the actual companion use case and markets before activation. A narrow domain is not proof of approval.
- Review current WhatsApp fees before sending; do not assume service messages are free.

## Work, in order

### 1. Confirm setup without risking the existing number

Diagnose the supplied access error, inspect owner-authorized Meta configuration, and establish an eligible coexistence path. Avoid Lovable connectors. If a provider or our own Tech Provider setup is required, surface that choice and its cost/approval requirements before onboarding. Do not change the existing number while this is unresolved.

### 2. Secure signup and account linking

Reuse website signup/sign-in and age gate. Add a linking confirmation page and Profile connected-number controls. Verify website identity plus confirmation from the originating WhatsApp conversation. Use short-lived, one-time opaque challenges; forwarded links and previews must not approve linking. No website session tokens or passwords in WhatsApp.

### 3. Reuse the real teaching workflow

Resolve channel identity to the linked user and tenant on the server, then invoke existing safety and teaching services. Preserve exact teacher wording, attribution, rights/integrity checks and honest abstention. Return readable text with real clip/source links. First release: one-to-one text only; no promise of website animations/embedded players inside WhatsApp.

### 4. Optional history, memory and Profile continuity

Separate account linking, conversation sync and long-term memory consent. Default optional storage off. Persist only explicitly enabled channel history, and save remembered content only through existing consent-gated memory services. Label WhatsApp provenance; verify website history/Profile readback. Add disconnect, memory-off and forget controls; revoke queued writes and cover channel stores during erasure. Do not import old phone chats or feed messages into model training/corpus ingestion.

### 5. Reliable receiving, replies and release checks

Audit/harden existing receiver: signatures, intended recipient, durable queue/restart recovery, ordered processing, duplicate events, send outcomes and delivery callbacks. Do not launch with daemon-thread-only processing after acknowledgement. Respect the 24-hour reply window; defer reminders/campaigns/templates until separately approved. Configure a real human-help destination and coexistence handoff so manual phone replies do not compete with automation.

Run focused security and journey tests, then the real flow: incoming message → signup → both-channel link → sourced reply → delivered callback → optional save → website readback → revoke/unlink. No completion claim from mocks or liveness checks.

## Technical approach

- Reuse existing `whatsapp_bot/wa_bot.py`, website auth/return handling, backend composition root, teaching coordinator and memory-consent services. Keep React/Vite; no whole-app hosted-stack migration required merely for a direct external HTTPS receiver.
- Channel-auth endpoints must be server-only and validate both trusted caller and live binding; never fabricate Supabase user JWTs, store refresh tokens in the bot or accept arbitrary user IDs.
- Link challenges: random opaque values, hashes at rest, short expiry, atomic single use, two-channel proof, no sensitive logging/referrers/analytics. GET previews do not mutate state.
- Reuse persistent storage/encryption and existing queue patterns; design RLS/grants and denial tests before any migration. No production schema/data mutation or deploy without its approval.
- Preserve existing safety, tenant, memory, rights and cache boundaries; memory-off turns must not hydrate/store private context through a side path.
- Secrets go to the actual deployed sender/receiver runtime through secure settings. Explain setup first; never ask for secrets in chat.

## Scope and approval

Approval starts implementation and isolated tests. It does not authorize deleting/migrating the number, spending, historical imports, public activation, mass messaging, unrelated UI changes, or production deploy/data mutation. Meta eligibility, secure credentials and real message testing remain external dependencies.

Research, sources and acceptance detail: `docs/plans/2026-11-21-whatsapp-direct-research.md`.