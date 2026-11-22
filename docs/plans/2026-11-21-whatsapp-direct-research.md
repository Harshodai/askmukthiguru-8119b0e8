# WhatsApp account-linked workflow: research and current evidence

Reviewed 2026-11-21. Research and design only; no Meta account access, message send, deployment, credential change or number migration performed.

## 2026-11-22 current-branch follow-up

The older implementation inventory below is historical. Current branch also contains `backend/app/api/whatsapp.py`, `backend/tasks/whatsapp_tasks.py`, `src/pages/LinkWhatsAppPage.tsx` and Profile's `WhatsAppCard`. These provide integration scaffolding, not verified public service.

Source inspection found optional history/memory checked by default in the linking page; STOP/RESET confirmations without persisted changes; an unauthenticated worker call to `/api/chat` with a deterministic unsigned session; hardcoded Graph v18 sending with redirects enabled by default; and acceptance logged as delivery without durable callback tracking. Recipient phone metadata is read but not checked against configured identity. Repair the existing route/worker rather than duplicating bots.

Official coexistence and Tech Provider documents were rechecked through web search. Meta's [official AI-provider page](https://developers.facebook.com/documentation/business-messaging/whatsapp/pricing/ai-providers) was fetched directly with HTTP 200: permitted general-purpose-assistant markets do not include India. This establishes a restriction, not whether AskMukthiGuru qualifies for another use-case category; classification still needs confirmation before activation. A bank-style interface does not change eligibility.

Owner requests familiar menus and reliable profile continuity while keeping the Business phone app. Revised plan covers concise native navigation, ordinary question entry, sourced teaching replies, separate unchecked privacy choices, persistent opt-out, handoff and delivery evidence. No Meta credentials were available in inspected shell variables; deployed-runtime credential presence was not inspected. No live message test or deployment occurred.

## Owner requirements

- No Lovable connector. WhatsApp is another channel for the existing website account and teaching service.
- Keep the existing WhatsApp Business number working in the phone app.
- Send new users to website signup/sign-in, then securely link their WhatsApp identity.
- Personal memory is optional, not a consequence of account linking.
- Owner reports Full control for the business portfolio and WhatsApp account. This is owner-reported, not a successful account inspection.

## Evidence versus gaps

| Area | Observed | What remains |
| --- | --- | --- |
| Railway | Public `/api/healthz` returned HTTP 200 with `status=alive` | This is liveness, not teaching readiness or a WhatsApp receiver test |
| Existing receiver | `whatsapp_bot/wa_bot.py` implements direct Meta GET verification, POST HMAC validation, batch handling, dedupe, send records and delivery callbacks | No live number, deployment or delivery proven in this request |
| Website accounts | Bridge calls `/api/chat` using per-phone signed anonymous sessions | No authenticated website account binding or shared profile/history |
| Consent | Bridge has messaging opt-in; backend has versioned memory consent | Current messaging YES cannot be repurposed as permission for personal memory |
| Durability | Bridge persists local state in SQLite; processes responses in daemon threads | Thread work can be lost after webhook acknowledgement; durable work claiming/recovery needed before launch |
| Privacy | Bridge appends message content before command/consent processing | Review pre-consent storage and retention; distinguish minimal delivery records from optional durable conversation/history/memory |
| Languages/media | Existing script detection and text response formatting | Voice/media are not an authenticated end-to-end flow; initial rollout stays text-only |
| Lovable error | Owner reports Full control in Meta | Need exact error/sanitized screenshot to distinguish Meta asset permissions from Lovable connection sharing |

Existing tests were inspected, not executed or represented as current passing evidence. README “production-ready” and historical test counts do not prove deployment readiness.

## Official research findings

### Direct Cloud API versus coexistence

Meta documents direct developer setup for a business's own assets. Direct developer use does not automatically require Advanced Access/App Review for access to its own assets; this does not waive publishing, verification, messaging or coexistence requirements.

- [Cloud API setup](https://developers.facebook.com/documentation/business-messaging/whatsapp/get-started)
- [App Review and direct developer distinction](https://developers.facebook.com/docs/whatsapp/embedded-signup/app-review/)

The current coexistence documentation was fetched successfully. It requires Business app version 2.24.17 or newer, an existing Solution Partner or Tech Provider, a working receiver, and Embedded Signup with session logging. Current documentation directs integrations to v4; do not build on deprecated v2/v3.

**Consequence:** owning the phone number and a Meta token is not enough to promise a self-service direct coexistence connection. Keeping the phone app working requires an eligible onboarding path: an approved provider without a Lovable connector, or our own eligible Tech Provider setup if Meta permits it. Do not assume creating an ordinary Meta app meets this requirement. Do not delete/disconnect the phone account as a workaround. An old March 2025 announcement excluded India; it is not current eligibility evidence for this specific number.

- [Current coexistence requirements](https://developers.facebook.com/documentation/business-messaging/whatsapp/embedded-signup/onboarding-business-app-users)

### AI-use eligibility

Meta's current official AI-provider page restricts general-purpose AI assistants to markets where Meta is legally required to permit them. The underlying terms also require review of the “AI primary versus ancillary functionality” classification. Being narrowly spiritual or using retrieval does not establish approval by itself.

Keep the proposed channel scoped to AskMukthiGuru account support, recorded-teaching discovery, practice and consented reflections, not an unrestricted general-purpose AI assistant. **Eligibility remains unresolved** until the actual use case and recipient markets are checked against current Meta terms. Do not evade restrictions by changing the display name, using another sender/provider, or calling the same assistant “support.”

- [Official AI-provider restrictions/pricing](https://developers.facebook.com/documentation/business-messaging/whatsapp/pricing/ai-providers)
- [Meta terms, redirected from WhatsApp terms](https://www.facebook.com/legal/Meta-Terms-for-WhatsApp-Business-Platform)

### Windows, fees and callbacks

Free-form replies require the customer's open 24-hour service window. Outside it, approved templates and appropriate opt-in are required; no automatic reminder/template campaign in the first release. Phone-app sends do not create or extend the API window. Current official pricing includes October 2026 changes: do not reuse the earlier blanket claim that support replies are free. Verify account/category/recipient-market rates before activation; Railway and model inference also have costs.

“API accepted” is not “delivered.” Correlate Meta message IDs with signed sent/delivered/read/failed callbacks. Deploy and verify the receiver before subscribing or requesting any permitted sync; never ingest historical customer chats by default.

- [Official pricing](https://developers.facebook.com/docs/whatsapp/pricing/)
- [WhatsApp webhooks](https://developers.facebook.com/docs/graph-api/webhooks/getting-started/webhooks-for-whatsapp/)

## Proposed account workflow

1. User messages business number. Receive only a verified, correctly addressed event; show disclosure and secure website sign-in link. Safety support remains available before signup.
2. Link opens website. Preserve intended linking destination through existing signup, age gate and OAuth/email confirmation.
3. Signed-in user sees masked number, what linking permits and separate optional history/memory choices. No hidden grants.
4. Require confirmation from both the signed-in website account and the originating WhatsApp conversation before binding. A forwarded link alone must not bind a number.
5. Resolve future signed inbound sender identity to a revocable channel binding, user and tenant on the server. Do not trust user IDs or consent flags supplied in a WhatsApp message.
6. Reuse the existing teaching/safety services; quotes retain speaker/source/time/integrity/rights metadata. WhatsApp sends readable text and source/playback links rather than promising an embedded web player.
7. With separate explicit conversation-sync consent, persist channel-labelled conversation rows readable in website history. Long-term memory requires its own active versioned consent and explicit save/remember action. History and memory are distinct.
8. Profile exposes connected number, memory controls and Disconnect. Revocation blocks pending memory work; account deletion covers binding, provider/bridge records and channel history under the documented retention policy. It cannot erase copies already held by WhatsApp or recipients.
9. STOP stops automated replies except necessary confirmation/safety support; RESET clears short-term conversation context, not unrelated website memories. Human-help escalation must have a real configured destination before public activation.

## Security design to implement after approval

- Short-lived random opaque link challenges, hashed at rest; single-use, atomic expiry/replay enforcement and both-channel confirmation. Keep website access/refresh tokens out of WhatsApp, URLs, logs and channel storage.
- Link secrets in URL fragments where feasible; remove before navigation, prevent referrer/analytics capture and retain only the minimal pre-auth linking handle needed for signup continuation. Link GETs/previews must never consume/approve the binding.
- Dedicated server-only channel authorization, separate from website authentication. Verify caller identity and binding again before invoking the existing coordinator; never mint fake Supabase user JWTs or accept a public `user_id` override.
- TLS, expected-host validation, no credentialed redirects, raw-body HMAC validation before parsing, recipient phone/account checks, duplicate/replay protection and out-of-order callback handling.
- Reuse managed persistent storage and existing encryption facilities where appropriate; separate lookup indexes from encrypted number/content fields. No new crypto algorithm, no alteration/rotation of existing vault keys. Treat WhatsApp-to-server integration as a trust boundary, not a claim that Meta cannot access processed content.
- Durable inbound work and per-conversation ordering. Acknowledge only after durable acceptance; recover work after restarts, prevent duplicate saved messages/memories, surface ambiguous outbound send outcomes instead of claiming exactly-once delivery.
- No WhatsApp data for model training/fine-tuning or teacher-corpus ingestion. Existing memory/rights/safety gates remain mandatory.

## Required owner/setup evidence

- Exact Lovable error without credentials; no connector action is necessary for the chosen direct architecture.
- Eligible coexistence onboarding and Meta use-case approval/classification where required.
- Meta application credentials and assigned account/phone identifiers, supplied only through secure secret settings. Provider tokens belong in the runtime actually sending messages, not merely Lovable frontend settings.
- Public deployed receiver URL and the same webhook verify token in Meta and receiver settings; app secret validates POST signatures and is distinct from verify token.
- Real test phone and authorization for messages. First test uses Meta's test sender where possible; production-number changes wait for approved coexistence.

## Launch evidence required

Real incoming question → website signup/sign-in → two-channel link → verified sourced answer → delivered callback → opt-in save → website readback → revoke/unlink. Test expired/forwarded/replayed links, wrong account/tenant, duplicate/batched events, restart recovery, memory-off, revoke during processing, number disconnect and closed-window sends. Mock tests alone cannot close this gate.