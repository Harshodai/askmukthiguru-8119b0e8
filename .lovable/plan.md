# WhatsApp, daily journey and explicit personalization

## Outcomes

1. Predictable Chat interactions on phone, tablet and desktop: submit once, see the question immediately, follow truthful response progress, stop/retry, and keep the original conversation when returning.
2. One optional daily journey: check-in → one real teaching clip → one existing practice → saved reflection → resume.
3. A visible **Personalize** action that uses consented user memory and approved teacher evidence through the general teaching pipeline. Default answers remain recorded verbatim teachings.
4. Clearer Profile and personal Knowledge Graph with source-linked context, honest empty/outage states, and accessible graph/list views.
5. WhatsApp Business incoming messages and replies, after the hosted-stack upgrade is approved.

## 1. Hosted stack and WhatsApp — currently blocked

- Migration approval was declined on October 30; no framework files were changed. Keep the current stack until approval is given through the upgrade card.
- When approved, follow the migrate-to-tanstack skill: preserve authentication wrappers, external Supabase, brand tokens, translations, metadata, custom scripts and test backups. Audit service-worker/push and Capacitor behavior separately rather than assuming native compatibility.
- The web-stack upgrade does **not** host the Python teaching engine or transfer Qdrant/OKF/LightRAG data. A reachable approved HTTPS teaching service remains a separate dependency. Railway stays off.
- Connect WhatsApp Business through its connection card, inspect access and account configuration, and deploy the supported signed webhook receiver before any history sync.
- Persist deduplicated incoming messages, reply attempts and delivery callbacks with restricted access. Reply through the connection gateway, respecting the 24-hour service window and approved-template requirements.
- Do not equate a WhatsApp phone number with a signed-in user's memory. Memory personalization requires an explicit verified account-linking and consent boundary; unlinked numbers receive no private user context.
- Acceptance: send a real message from a phone → read the stored incoming message → reply from the app → confirm recipient receipt and callback status. Gateway acceptance alone is not delivery proof.

Research: Meta documents incoming messages and outgoing delivery statuses as webhook events: https://developers.facebook.com/documentation/business-messaging/whatsapp/webhooks/overview.

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
- WhatsApp checks require an approved migration, connected Business number, reachable receiver and a real recipient. Live teacher personalization/daily clip playback requires a reachable teaching engine.

## Delivery and release limits

Implement Chat/daily journey/personalization/Profile changes after plan approval; keep blocked WhatsApp migration open without repeatedly requesting approval. Record measured passes and named blockers rather than marking all work complete.

Faculty release needs actual teaching/playback, reflection readback, consent/isolation and relevant auth/admin checks. Keep calibration, clinician/native-speaker review, rights and backup/load evidence explicit under the existing release checklist; do not invent sign-offs or activate production infrastructure.