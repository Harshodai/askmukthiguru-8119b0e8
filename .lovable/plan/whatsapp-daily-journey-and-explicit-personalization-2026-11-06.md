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

Research: Meta documents incoming messages and delivery statuses as webhook events: [https://developers.facebook.com/documentation/business-messaging/whatsapp/webhooks/overview](https://developers.facebook.com/documentation/business-messaging/whatsapp/webhooks/overview).

## 2. Chat query interaction

- Reuse the existing composer, submission handler, conversation and response controls; avoid a parallel chat implementation.
- Fix confirmed submission/queue issues: rapid repeated sends, IME input, queued language/attachments, and quota/context checks before interrupting an active answer.
- Keep textarea expansion and toolbar stable on narrow screens; prevent controls from competing with the question or answer.
- Show actual waiting/streaming/error states, preserve draft and retry context, and avoid jumping away from content the user is reading.
- Use restrained reduced-motion-safe transitions for question entry, response appearance and next-step changes, not decorative animation that delays interaction.

## 3. Complete the daily check-in journey

**Current implementation scope — November 6: finish this section only.** Chat redesign, WhatsApp, Personalize and broader Profile/KG work remain separate.

### Journey experience

1. **Check-in:** reuse the existing optional mood dialog and confirmed-save handling. Its next action opens the teaching step rather than bypassing it for practice. Keep mood check-ins outside completed-practice statistics.
2. **Teaching:** send the saved self-reported mood through the existing safe Chat request flow. Select one eligible returned recorded clip with real attribution and timestamps; retain its source and conversation reference. No fabricated quotes, substitute sample teachings, or weaker rights/speaker/integrity gates. Unavailable service or no eligible clip leaves this step pending with retry.
3. **Practice:** offer the single existing practice selected at check-in. Continue into its existing player/guide, preserving journey context and existing meditation pause/resume. Guided practice completion or an explicit completed-practice confirmation advances this step; simply visiting or pressing Play does not.
4. **Reflection:** open a dedicated daily-reflection draft using the existing Notes save path. Keep its teaching/conversation provenance, preserve unsaved words when navigating or reloading, guard repeated saves, and complete only after a returned saved note. Ordinary notes and edits must not complete this journey accidentally. Signed-out users see a clear sign-in action for cloud Notes; keep their draft through that return.
5. **Resume:** expose one compact next-step action in Chat and Profile, and retain the way back from practice and Notes. Resume the same saved clip/practice/draft, not a fresh unrelated query. Preserve unfinished journeys across midnight until completed, skipped or explicitly replaced; show completed reflection readback without pressure to start again.

### Technical details and reasoning

- Extend `src/lib/dailyJourney.ts`, not a second journey store. Validate persisted state, version it, and retain only minimal source references plus an explicit local reflection draft. Scope state to the active account or anonymous device so account switching cannot expose another user's journey; integrate existing sign-out cleanup. Same-device resume is this scope; do not claim cross-device progress sync without a server persistence implementation.
- Reuse `MoodCheckIn`, ChatInterface/ChatMessage and their real clip player. Associate completion with the journey's selected message/clip rather than any teaching card clicked in any conversation. A Play request is not proof of successful playback; use observed player state where available and honest failure states otherwise.
- Reuse existing practice completion hooks; match completion to the selected practice and make confirmation possible for guide-only practices. Do not let an unrelated meditation event complete this step.
- Reuse NotesPanel/useNotes for authenticated storage and returned-note readback. Only the explicitly opened journey reflection receives journey completion/provenance. Existing Notes RLS remains unchanged unless inspection establishes a necessary schema change.
- Reuse semantic theme tokens and Button controls, with small reduced-motion-safe step transitions. Keep active conversation uncluttered and actions comfortable on mobile.

### Acceptance and handoff

- Add focused tests for one clip/one practice association, unrelated actions not advancing progress, failed playback/save remaining pending, repeated-save prevention, persisted draft, next-day resume, explicit replacement/skip, account isolation, and saved reflection references.
- Run existing mood/journey/Notes/practice suites plus the added tests. Check phone, tablet and desktop navigation, refresh/resume and reduced motion.
- Exercise check-in → actual returned clip/playback → practice completion → authenticated reflection save/readback → return/resume when services and account access permit. Report any unavailable teaching or external-auth step as blocked, not passed. A controlled mocked flow may validate orchestration but is not live-teaching proof.
- Update the existing task record, lessons and applicable architecture guidance with measured results. Railway remains off; no deployment, corpus changes or human sign-off substitutions.

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
  
please do these in the pr and merge to the feature/audit-strengthen-rag-qdrant branch