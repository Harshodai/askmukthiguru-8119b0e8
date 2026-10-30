# WhatsApp, daily journey and explicit personalization

## Outcomes

1. Predictable Chat interactions on phone, tablet and desktop: submit once, see the question immediately, follow truthful response progress, stop/retry, and keep the original conversation when returning.
2. One optional daily journey: check-in → one real teaching clip → one existing practice → saved reflection → resume.
3. A visible **Personalize** action that uses consented user memory and approved teacher evidence through the general teaching pipeline. Default answers remain recorded verbatim teachings.
4. Clearer Profile and personal Knowledge Graph with source-linked context, honest empty/outage states, and accessible graph/list views.
5. WhatsApp Business incoming messages, replies and delivery callbacks through the existing webhook receiver.

## 1. WhatsApp webhook receiver (current stack kept)

- No framework migration. The web app stays on Vite + React Router; `@tanstack/react-query` remains as the data-fetching library only. The TanStack-stack migration plan was removed on 2026-10-30.
- The receiver already exists: `whatsapp_bot/wa_bot.py` (Flask; Twilio and Meta Cloud API). Signatures are verified fail-closed (`X-Hub-Signature-256`, `X-Twilio-Signature`).
- Incoming messages are deduplicated by provider message id (`wa_inbound`). Every message in a batched Meta payload is handled.
- Outbound attempts (`wa_outbound`) and delivery callbacks (`wa_status_events`) are stored in the bot's SQLite file (mode 0600, no read endpoint). `accepted` is gateway acceptance only. Delivery needs a `delivered` or `read` callback.
- Free-form replies are sent only inside the 24-hour window after the user's last message. Outside it, only the approved template in `META_TEMPLATE_NAME` is sent. With none configured the send is blocked and recorded as `blocked_window`.
- A phone number is never linked to a signed-in user's memory. The bot uses an anonymous per-phone token. Linking needs a separate verified account-linking and consent flow, which does not exist yet.
- Acceptance (UNPROVEN until run): real phone message → stored inbound row → reply → recipient receipt → `delivered`/`read` callback row. Needs a connected Business number, a reachable HTTPS receiver and a real recipient. Railway stays off.
- Teaching engine hosting is a separate dependency. Qdrant/OKF/LightRAG data are not moved by any web change.

Research: Meta documents incoming messages and delivery statuses as webhook events: https://developers.facebook.com/documentation/business-messaging/whatsapp/webhooks/overview.

## 2. Chat query interaction

- Reuse the existing composer, submission handler, conversation and response controls; avoid a parallel chat implementation.
- Fix confirmed submission/queue issues: rapid repeated sends, IME input, queued language/attachments, and quota/context checks before interrupting an active answer.
- Keep textarea expansion and toolbar stable on narrow screens; prevent controls from competing with the question or answer.
- Show actual waiting/streaming/error states, preserve draft and retry context, and avoid jumping away from content the user is reading.
- Use restrained reduced-motion-safe transitions for question entry, response appearance and next-step changes, not decorative animation that delays interaction.

## 3. Complete the daily check-in journey

- Reuse MoodCheckIn and existing Chat/Notes/practice surfaces. Add save-in-progress protection, error/retry handling and reset-on-reopen; retain the draft after failed saves.
- Keep check-ins separate from completed meditation counts/minutes/streaks. Inspect existing storage/grants/policies before any necessary schema migration.
- After a confirmed check-in, submit its self-reported context through the normal safe teaching lane. Show exactly one eligible returned clip, never an invented quote or sample clip.
- Associate one existing practice with the journey. Optional reflection stays editable; save through the existing Notes path with conversation/teaching provenance and confirmed write status.
- Let users skip or cancel, and resume the pending step from Chat or Profile after returning. Only mark teaching/practice/reflection steps complete when their respective actions are confirmed.
- Service failure must preserve the saved check-in and offer retry, not claim the teaching step succeeded. End-to-end teaching verification remains blocked until the approved teaching service is reachable.

## 4. Personalize answers using existing evidence pipeline

- Reuse the existing personalize request builder, handler and backend PersonalizeStage instead of creating another generator.
- Expose **Personalize** on eligible served teachings for signed-in, non-temporary chats; show understandable sign-in/consent/no-context/unavailable states where appropriate.
- Resolve teaching identity server-side and preserve rights, speaker, hash and clip-eligibility checks. Never trust client-sent quote text.
- Run the existing general retrieval/synthesis lane with relevant consent-approved user memory, Qdrant teacher evidence, reviewed OKF and available LightRAG support. Verify actual wiring; configuration/documentation alone is not runtime proof.
- Label the result as a personalized reflection, not teacher speech. Keep the original clip and citations visible and preserve the way back.
- Enforce user/tenant isolation, consent revocation, temporary-chat exclusion and personalized cache separation on the server. Missing evidence or consent must decline honestly; ordinary questions must not silently switch away from verbatim mode.

## 5. Profile and personal Knowledge Graph

- Prioritize recent conversation, pending daily step and useful saved context; remove repeated competing actions instead of adding another destination.
- Distinguish self-reported facts, saved reflections, inferred suggestions and teacher concepts. A graph's existence is not memory consent.
- Use source IDs supplied by the actual APIs to open original note/conversation/teaching with preserved return context. Missing provenance shows unavailable—not a fabricated link.
- Keep graph/list alternatives, consent controls and inspect/edit/delete/forget flows discoverable. Verify account switching and deletion propagation rather than claiming frontend deletion erases every store.

## Technical approach and tests

- Existing surfaces: ChatInterface/ChatComposer, MoodCheckIn, meditationStorage, Notes, ProfilePage/MemoryManager, memoryApi, chat/personalize and backend PersonalizeStage.
- First test pins: duplicate submission and queued context; mood duplicate prevention/reopen/failure; check-in exclusion from practice stats; one clip/one practice/reflection readback/resume; personalization opt-in/default-route preservation, invalid clip, revoked consent, incognito, cross-user isolation and cache scope; source navigation and draft/return preservation.
- Run existing focused frontend suites and dependency-available backend tests. Static checks or isolated mocks are not live-service proof.
- Browser checks across phone/tablet/desktop, reduced motion and keyboard interaction. External Supabase authenticated flows require authorized account testing; this environment cannot mint that project's sessions.
- WhatsApp checks require a connected Business number, a reachable HTTPS receiver and a real recipient. Live teacher personalization/daily clip playback requires a reachable teaching engine.

## Delivery and release limits

Implement Chat/daily journey/personalization/Profile changes after plan approval. Record measured passes and named blockers rather than marking all work complete.

Faculty release needs actual teaching/playback, reflection readback, consent/isolation and relevant auth/admin checks. Keep calibration, clinician/native-speaker review, rights and backup/load evidence explicit under the existing release checklist; do not invent sign-offs or activate production infrastructure.
