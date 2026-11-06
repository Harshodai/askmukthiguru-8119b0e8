# 03 — Product journeys, feature wiring and functional requirements

> **2026-11-06:** Superseded in part by `specifications/COMPLETE_FR_NFR_AND_ACCEPTANCE_MATRIX.md` (44 FRs rewritten with test, acceptance, gate and status; stale rows corrected in its §2). Status of findings: `FINAL_PENDING_WORK_REGISTER.md`.

Owner: S4. Audit target: `origin/main@46b808fb`. Conventions: `CONVENTIONS.md`.

> **Erratum (lead, after the independent review in `26`). These corrections override the text below.**
> 1. `CancelFlow` is **mounted and live**: `src/pages/ProfilePage.tsx:583` → `AccountDataCard.tsx:140-195`. It is the **only** UI path to `delete-my-account`. FR-DATA-01 status is "Live with defect" (UX-001, ADV-01), not "Live; dormant second path". **Do not remove `CancelFlow` without replacing it with a direct deletion path** (T1-12).
> 2. Scheduled deletions ("keep 30/90 days") never execute: no purge job exists in the repository (ADV-01, `26` §3).
> 3. Undocumented processors receive user data (Lovable AI gateway, Sarvam STT, Sentry replays, SMTP, web push): ADV-02. Journeys 9 and 14 must disclose them.
> 4. A full 14-step journey walkthrough, including error recovery and stream interruption, is in `14d`.
> 5. FR-CONV-02 is wrong in two places. History is **not** "synced for signed-in users": the cloud copy is a one-way backup that the UI never reads back. The local list is capped at 10 and wiped on every sign-out or session expiry. Retention is **not** "user-configurable": `setRetentionDays` has no caller. See UX-006 (P1) and T6-09.

Contents:

1. Journeys as built today.
2. Feature traceability map (UI → API → backend → store → response → UI).
3. Wiring findings (`PRD-`).
4. Functional requirements catalogue (`FR-`), with current status.
5. Status summary.

Backend internals (stages, LLM calls) are traced by S1 (doc 05) and S3 (docs 09, 10). This document traces from the user's side.

---

## 1. Journeys as built today

Configuration assumption: root `CLAUDE.md` invariant 21 (first-person-only chat: `FIRST_PERSON_CHAT_BRIDGE_ENABLED=true`, `FIRST_PERSON_LLM_FALLBACK_ENABLED=false`). That is the owner's local configuration [DOC-CLAIM]. The deployed configuration is unknown [LIVE-R].

| # | Journey | Steps as implemented | Weak points |
|---|---|---|---|
| J1 | First anonymous visit | `/` landing (`src/pages/Index.tsx`, `components/landing/*`) → `/chat` → client mints a signed anonymous token (`POST /api/auth/anon-session`, `src/lib/chat/anonSession.ts:21`) → question → `/api/chat/stream` (SSE, `src/lib/chat/streaming.ts:36`) with JSON fallback (`/api/chat`, `transport.ts:122`) → verbatim clip with "Related — not a direct answer" badge, or abstain card. Quota: 5 messages per 24 h (`backend/CLAUDE.md`). | About 3 in 4 on-topic questions abstain [DOC-CLAIM, task list §0]. The abstain card says "This contemplation is offered from foundational spiritual principles…" (`ChatMessage.tsx:293`) though the FP-only abstain is a static message. Cookie banner, safety disclaimer and (after first answer) push prompt compete for attention (`App.tsx:381–384`). |
| J2 | Returning signed-in user | `/auth` (email, Google, Apple; 18+ checkbox, `AuthPage.tsx`) → local conversations (localStorage) + cloud sync to Supabase (`chatStorage.ts:400`) → sidebar history → profile (`/profile`: stats, streaks, heatmap, journey, memory manager). | Server history for the model is read from `chat_messages`, which the client writes directly (PRD-003). Continuity across devices depends on that sync. |
| J3 | Crisis | Message → backend crisis pre-check and distress stage (S3 doc 14b) → helpline response with `safety_notices` (`ChatMessage.tsx:1455`) → Serene Mind practice may be gated (`src/lib/chat/sereneMindGating.ts`). | Push-permission prompt can appear 4 s after a crisis answer (PRD-004). Helplines: 1 of 15 call-verified (doc 23 GURU-007). |
| J4 | Deep exploration | Follow-up chips (`FEATURE_FLAGS.suggestedFollowUps`, `ChatMessage.tsx:1896`), source panel (`ConversationSourcesPanel.tsx`), link inspection (`LinkSearchModal.tsx`), knowledge graph page (`/knowledge-graph`). | Link inspection uses a relative URL (PRD-001). Depth preferences have no visible effect on a verbatim clip [INF] (FR-DEPTH-01). |
| J5 | Multi-video question | UI can render an "editorial set" with a conflict note ("Sources express opposing positions. They are shown separately; no synthesis was made." `ChatMessage.tsx:540`). | Whether the backend returns multi-clip sets on the live configuration is owned by S2 (doc 07). No cross-video explanation exists by design (invariant 15). |
| J6 | Follow-up | Client sends the last 20 messages (40 if the question contains referential words), `transport.ts:52`. Signed-in: backend replaces them with stored history (`backend/app/api/chat.py:479–500`). | Verbatim route answers each turn by retrieval; continuity behaviour is S3's (doc 10). |
| J7 | Meditation | "Serene Mind" modal (`SereneMindModal.tsx`) with audio (teacher voice MP3) and video tabs; meditation stats and streaks; SRS flashcards (`FlashcardPractice.tsx`). | Teacher voice rights (IP-002). Flashcards use relative URLs (PRD-001). Streak copy "keep it going!" (doc 12b UX-002). |
| J8 | WhatsApp | Separate Flask bridge `whatsapp_bot/wa_bot.py` → `/api/auth/anon-session` + `/api/chat` (lines 5, 512, 1011). Backend capability reports `"whatsapp": "disabled_by_policy"` (`backend/app/api/capabilities.py:73`). PR #91 (webhook receiver) was closed unmerged [V-GIT]. | Not a live channel. Twilio/Meta credentials are a pending human gate (root `CLAUDE.md` Open work). |

---

## 2. Feature traceability map

Legend for status: **Live** (wired end to end on default config), **Flagged** (wired but behind a flag), **Dormant** (code exists, no entry point), **Partial** (a link in the chain is missing or wrong), **Absent**.

| Feature | UI entry | API call | Backend route / function | Store | Response fields used by UI | Status | Notes |
|---|---|---|---|---|---|---|---|
| Ask a question (stream) | `ChatComposer` → `ChatInterface` | `POST /api/chat/stream` → stream URL | `backend/app/api/chat.py` (chat router, prefix `/api`) → stream orchestrator | Redis (exact cache), Qdrant | content, citations, grounding_state, verification, safety_notices, route_decision | Live | SSE checkpointing in `sessionStorage` (`src/CLAUDE.md`) |
| Ask a question (JSON fallback) | same | `POST /api/chat` (`transport.ts:122`) | `chat.py` | same | same | Live | Sends a client "system" message; backend drops it (`backend/app/schemas/__init__.py:25` `_ALLOWED_ROLES`) — PRD-002 |
| Cancel generation | stop button | `DELETE /api/jobs/{id}` relative (`ChatInterface.tsx:1058, 2056`) | `job_routes.py` | Redis/jobs | — | Partial | Relative URL (PRD-001) |
| Anonymous session | automatic | `POST /api/auth/anon-session` | auth router | HMAC token | token | Live | |
| Citation card + clip playback | `CitationCard`, `DiscourseAudioStrip` | (YouTube embed / audio slice URL) | citations built in `first_person_pipeline._build_citation` (per `firstPersonService.ts:8`) | Qdrant payload | `playbackStartSeconds`, `playbackEndSeconds`, `speakerVerified`, `transcriptStatus` | Live | Start uses `playbackStartSeconds` floored at 0 (`CitationCard.tsx:194–204`), matching invariant 6 |
| "Related, not a direct answer" label | `ChatMessage` badge | — | `verification.direct === false` | — | `verification.direct` | Live | `ChatMessage.tsx:235–304` |
| Speaker label / "unverified clip" | `resolveAttributionLabel` | — | `speaker_verified` copied from clip | Qdrant | `speaker_verified` | Live | `src/lib/chat/types.ts:293–300` never shows a bare teacher name unless verified |
| Abstain help card | `AbstainHelpCard` | — | `route_decision=first_person_abstain` | — | `isFirstPersonAbstain`, `routeDecision` | Live | Hardcoded "Verified Inquiries" list (`AbstainHelpCard.tsx:12–24`) — not checked to have servable clips [INF] |
| Safety notices | `ChatMessage.tsx:1455` | — | `safety_notices` | — | `safetyNotices` | Live | |
| Teacher's Words page | `/teachers-words` | `POST /api/first-person/query` (`firstPersonService.ts`) | `backend/app/api/first_person.py` | Qdrant | `is_direct_answer`, `status`, `related_clips_heading` | Flagged (`VITE_FIRST_PERSON_ENABLED`, `App.tsx:373`) | Second, separate first-person path from chat (duplicate surface) |
| Assistant switcher | `AssistantSwitcher` in composer (`ChatComposer.tsx:462`) | `GET /api/assistants`; `POST /api/assistants/redeem` | `assistants.py`; `assistant_authorization.py` | Supabase `assistants`, settings | slug | Partial | Slug vocabularies disagree (PRD-005, doc 11 §3) |
| Follow-up suggestions | chips | — | `follow_up_suggestions` | — | `followUpSuggestions` | Flagged (on by default) | S3 owns generation |
| Response preferences (depth/mode) | settings | sent as `response_preferences` (`transport.ts:58`) | consumed in `generation.py`, `glue_stages.py`, `pipeline_coordinator.py` | localStorage | — | Partial | Generation path is off in FP-only mode, so the effect is limited to glue text [INF] |
| Feedback (thumbs) | `InlineActions` | `POST /api/feedback` | `feedback.py:26` | Supabase `feedback_events` | — | Live | Saved locally too (`saveFeedback`) |
| Clip report (content correction) | none for seekers | — | `POST /api/feedback/clip-report` (`feedback.py:336`) | Supabase | — | Partial | Admin "Clip Reports" page exists (`App.tsx:269`); no seeker control found (PRD-006) |
| Faculty answer labels | `FacultyLabelPanel` | Supabase upsert `faculty_answer_labels` (`facultyLabels.ts:67`) | — | Supabase | — | Flagged (`VITE_FACULTY_REVIEW_ENABLED`) | Migration not applied per task list §2 N5 [DOC-CLAIM] |
| Conversation history | sidebar, `/chat` | Supabase direct upsert/insert (`chatStorage.ts:400–441`) | backend also reads/writes `chat_messages` (`chat.py:479`) | localStorage + Supabase | — | Live | Two writers (PRD-003) |
| Conversation export | export action | — (client-side `exportConversation.ts`) | — | localStorage | — | Live | |
| Memory (view/edit/forget/consent) | `MemoryManager`, `MemorySettingsModal`, `MemoryConsentBanner` | `/api/memory/*` (`memoryApi.ts`) + Supabase reads (`guru_memories`, `guru_core_memory`, `guru_session_summaries`) + RPC `match_user_memories` | `memory.py`, `canonical_memory.py` | Supabase | — | Live | S3 owns internals. Client inserts `pending_extractions` directly after reading consent (`transport.ts:613–629`) |
| Personalise this teaching | button on citation | `personalize_teaching` in chat body | `PersonalizeStage` | memory | `personalized` flag | Flagged (`VITE_PERSONALIZE_TEACHING_ENABLED`) | Label "In our own words — not a direct quote from the teachers." (`ChatMessage.tsx:549`) — correct separation |
| Wisdom tips while waiting | tip ticker | `GET /api/teachings/tips` (`useWisdomTips.ts`) | `teachings.py:318` | Redis cache, Qdrant harvest, curated fallback | text, source, teacher | Live (flag on) | Unsourced attributed quotations (GURU-012) |
| Deepen & Tune bar | chat | — | — | hardcoded | — | Flagged off | Hand-written per-teacher concepts (GURU-012) |
| Language selection, UI locale | `LanguageSelector`, onboarding step | `language` in chat body; `POST /api/translate` | `speech.py` | — | — | Live | 14 locales (`src/locales/`) |
| Voice input / TTS | mic, speaker | `/api/speech/stt`, `/api/speech/tts`; edge fn `sarvam-stt` | `speech.py` | — | — | Live [INF] | Two STT paths (backend and edge function) |
| Serene Mind meditation | modal | static MP3 | — | `public/audio/...` | — | Live | IP-002 |
| Practices, guides | `/practices`, `/guides/*` | none (static content `practicesContent.ts`, `guidesContent.ts`) | — | — | — | Live | Static text; attribution not traced line by line |
| Healing courses | `HealingPathCard` | `/api/healing` | `healing_course.py` | Supabase `user_course_progress` | — | Live [INF] | Prompt strings attribute claims to Sri Krishnaji (`healingCourses.ts:59`) |
| Daily teaching / ritual | `DailyTeachingCard` | `/api/ritual/today`, `/api/ritual/checkin` | `ritual.py` | Supabase `daily_teachings`, streak tables | — | Live | Streak count shown (doc 12b) |
| Profile, streaks, heatmap | `/profile` | `/api/profile`; Supabase `profiles`, `meditation_sessions` | `profile.py`, `retention_service.py` | Supabase `user_streaks` | — | Live | doc 12b |
| SRS flashcards | `FlashcardPractice` | `/api/srs/due`, `/api/srs/review` (relative) | `srs.py` | Supabase | — | Partial | PRD-001 |
| Knowledge graph | `/knowledge-graph` | `/api/kg/subgraph`, `/api/kg/personal` | `kg.py` | Memgraph, Supabase | — | Live [INF] | Graph is off the answer path (task list §1 item 1) |
| Second brain / notebooks | `/second-brain`, `/notebooks` | `/api/brain/*` | `second_brain.py`, notebooks router | Supabase (vault) | — | Live [INF] | Not linked from answers (no "save answer") |
| Push notifications | `PushPermissionPrompt` (global), `PushNotificationsManager` | `/api/push/register` | `push.py` (prefix `/push` under `/api`) | Supabase `push_subscriptions` | — | Flagged (`push_notifications_enabled`) | PRD-004 |
| Daily push | — | edge fn `daily-teaching-push` (cron secret) | — | `daily_teachings` | caption | Live [INF] | Title "Today's Teaching" with caption; source attribution not checked |
| Data export / account deletion | `AccountDataCard` | edge fns `export-my-data`, `delete-my-account` | Supabase functions | Supabase | — | Live | Second, dormant deletion path `CancelFlow` (doc 12b UX-001) |
| Support contact | settings | `/api/support/contact` | `support.py:33` | — | — | Live | |
| Waitlist | landing | `/api/waitlist/` | `waitlist.py` | Supabase | — | Flagged (`VITE_WAITLIST_ENABLED`) | |
| Admin dashboard | `/admin/*` | `/api/admin/*`, edge fns, RPC `seed_admin_demo` | `admin.py`, `admin_video_review.py` | many | — | Flagged (`VITE_ADMIN_ENABLED`) | Demo seeding RPC callable from the admin UI (`useSeedDemo.ts:22`) |

---

## 3. Wiring findings

### PRD-001 — Some frontend calls use relative `/api/...` URLs
| Field | Value |
|---|---|
| Pillars | P3 |
| Category | Feature wiring |
| Severity | P2 |
| Type | Probable defect |
| Confidence | Medium (depends on deploy topology) |
| Evidence | `src/components/meditation/FlashcardPractice.tsx:43, 84`; `src/components/chat/LinkSearchModal.tsx:120`; `src/components/chat/ChatInterface.tsx:1058, 2056`. All other modules use `BACKEND_URL` (`src/lib/backendUrl.ts`). |
| Actual behaviour | When the frontend is served from a different origin than the API (the Lovable + Railway pattern described in `backendUrl.ts`), these calls hit the frontend host. Flashcards, web-discourse search and job cancellation fail. |
| Expected behaviour | All API calls resolve through `BACKEND_URL`. |
| Root cause | Inconsistent use of the URL helper. |
| User impact | Flashcards show nothing; "stop" does not cancel server work (cost). |
| Remediation | Use `${BACKEND_URL}` in the five calls. Add a lint rule banning string literals that start with `/api` in `fetch(`. |
| Acceptance criteria | `rg -F "fetch('/api" src` and `` rg -F 'fetch(`/api' src `` return nothing. |
| Regression test | ESLint rule + unit test of `FlashcardPractice` with a non-empty `BACKEND_URL`. |
| Implementation risk | Low |
| Verification | [V-STATIC]; topology [LIVE-R] |

### PRD-002 — The client sends a system prompt and "seeker environment" that the backend discards
| Field | Value |
|---|---|
| Pillars | P3 |
| Severity | P3 |
| Type | Confirmed defect (dead payload) |
| Confidence | High |
| Evidence | `src/lib/chat/config.ts:37–40` (persona system prompt "embodying the wisdom of Sri Preethaji & Sri Krishnaji"); `transport.ts:51` (local time, greeting word, including `slug === 'sadhguru' ? 'Namaskaram'`); `backend/app/schemas/__init__.py:25` `_ALLOWED_ROLES = {"user","assistant"}` and line 229 "Dropping client message with disallowed role". |
| Actual behaviour | Every request carries a client persona prompt that is dropped. It wastes bytes and misleads maintainers. |
| Remediation | Remove `systemPrompt` and the system message from the client. If the time of day matters, send a typed field. |
| Acceptance criteria | Request body contains no `role: "system"` message. |
| Verification | [V-STATIC] |

### PRD-003 — "Server history" is written by the client
| Field | Value |
|---|---|
| Pillars | P3, P1 |
| Category | Data integrity |
| Severity | P2 |
| Type | Confirmed defect |
| Confidence | High |
| Evidence | Client writes `conversations` and `chat_messages`, including `role` and `content` of guru messages (`src/lib/chatStorage.ts:400–441`). RLS allows authenticated insert and update of any message in the user's own conversations (`supabase/migrations/20260506064449_…sql:66–72`). The backend loads these rows as authoritative history and maps `guru` to `assistant` (`backend/app/api/chat.py:479–500`). |
| Actual behaviour | A signed-in user can insert or edit "assistant" turns, and the backend treats them as its own past answers. The comment in PR #76 ("drop unverified client-supplied history") assumes the table is server-owned. It is not. |
| Expected behaviour | Assistant turns in durable history are written only by the backend (service role). Clients may insert user turns only. |
| Root cause | Local-first sync was added before server persistence. |
| User impact | Limited to the user's own conversation (no cross-user path found). A user can make an export look as if the app said something it did not. |
| Remediation | RLS: allow client insert only with `role = 'user'`; deny client update of `role`/`content`. Backend writes assistant turns. Remove client cloud sync of guru messages. |
| Acceptance criteria | An RLS test as an authenticated user inserting `role='guru'` fails. |
| Regression test | Add to `tests/e2e/rls-cross-user.spec.ts` or the staging RLS workflow. |
| Implementation risk | Medium (sync behaviour changes). |
| Verification | [V-STATIC]; cross-ref S1 doc 14 |

### PRD-004 — The push-permission prompt can appear right after a crisis answer
| Field | Value |
|---|---|
| Pillars | P5, P4 |
| Category | Ethical UX |
| Severity | P2 |
| Type | Probable defect |
| Confidence | Medium |
| Evidence | `PushPermissionPrompt.tsx:31–37` opens 4 s after the event `askmukthiguru:chat_response_success`. `ChatInterface.tsx:1548` and `1941` dispatch it for any completed, non-blocked answer, with no check of `groundingState` or safety route. |
| Expected behaviour | Never ask for notification permission in a turn that carried a crisis or distress response. |
| Remediation | Dispatch the event only when `groundingState === 'grounded'` and no safety notice is present. |
| Acceptance criteria | Unit test: a `safety_redirect` answer does not open the prompt. |
| Verification | [V-STATIC]; crisis answers' `blocked` flag value [LIVE-R] |

### PRD-005 — Assistant slugs disagree between frontend, database and backend
| Field | Value |
|---|---|
| Pillars | P3, P4 |
| Severity | P2 |
| Type | Confirmed defect |
| Evidence | Doc 11 §3 (R3 vs R4); `assistant_authorization.py:242` raises 403 for unresolvable slugs. |
| Actual behaviour | Choosing an assistant that the catalogue lists but the backend does not resolve produces an error answer. |
| Remediation | One registry (doc 11 §6). Remove per-teacher personas. |
| Verification | [V-STATIC]; catalogue contents [LIVE-R] |

### PRD-006 — Seekers cannot report a wrong or misattributed clip
| Field | Value |
|---|---|
| Pillars | P4, P6 |
| Category | Content correction |
| Severity | P1 |
| Type | Product gap |
| Confidence | Medium (search-based absence) |
| Evidence | Backend `POST /api/feedback/clip-report` (`backend/app/api/feedback.py:336`); admin page `ClipReportsPage` (`App.tsx:269`). `rg -i "clip-report|report.?clip"` in `src/` outside `admin/` and locales returns no seeker control. |
| Expected behaviour | Every served clip has a "Report a problem with this clip" control (wrong speaker, wrong words, cut mid-thought, not relevant, harmful). Reports reach the admin queue and the teachers' correction contact (doc 23 D6). |
| User impact | Errors persist; the teachers' team has no correction path to inspect. |
| Remediation | Add the control to `CitationCard`. Post `{point_id, video_id, start_ms, reason}`. Show an acknowledgement. |
| Acceptance criteria | E2E test: report → row visible in admin Clip Reports. |
| Verification | [V-STATIC] |

### PRD-007 — Two first-person surfaces with different contracts
| Field | Value |
|---|---|
| Pillars | P3 |
| Severity | P3 |
| Type | Architectural risk |
| Evidence | Chat bridge (`/api/chat`, `route_decision=first_person_bridge`) and the Teacher's Words page (`/api/first-person/query`, `is_direct_answer`, `related_clips_heading`; `TeacherWords.tsx:256–268`). |
| Remediation | Keep one serving contract. Make Teacher's Words a view over the chat response, or remove it. |
| Verification | [V-STATIC] |

---

## 4. Functional requirements catalogue

Format per FR: actor; problem; preconditions; trigger; expected behaviour; business rules; inputs; outputs; failure behaviour; dependencies; acceptance criteria (AC); test cases (TC); priority (Must / Should / Could); current status with evidence.

### 4.1 Onboarding and access

**FR-ONB-01 — First-visit orientation**
- Actor: anonymous visitor. Problem: does not know what the product is or is not.
- Pre: none. Trigger: first visit.
- Behaviour: show one screen that says what answers look like (teacher's recorded words, or an honest "no match"), that this is an AI tool and not the teachers, and that it is not therapy. Offer language choice.
- Rules: no claim of accuracy that is not measured. Inputs: locale. Outputs: dismissible card.
- Failure: if the backend is down, say so and offer practices.
- Deps: `TrustPage`, `GuidedTour`, `LanguageOnboardingStep`.
- AC: copy reviewed by the owner; shown once per device; available later from the menu.
- TC: first load shows the card; second load does not; screen reader reads it in order.
- Priority: Must. Status: Partial — tour and language step exist (`src/components/onboarding/`); AI disclosure exists on landing (`HeroSection.tsx:389`, `MeetTheGurusSection.tsx:163`). No single "what answers look like" statement.

**FR-AUTH-01 — Sign-in with age confirmation**
- Actor: visitor. Problem: wants history across devices.
- Pre: none. Trigger: "Sign in".
- Behaviour: email/password, Google or Apple; sign-up requires 18+ confirmation before any submit.
- Rules: 18+ gate enforced in UI and in handler. Outputs: session. Failure: clear error; no lockout without message.
- Deps: Supabase Auth; `AuthPage.tsx`; MFA page for admins.
- AC: sign-up impossible without the checkbox; MFA required for admin routes (AAL2).
- TC: OAuth button disabled until checked; `tests/e2e/security-aal2.spec.ts`.
- Priority: Must. Status: Live (`src/CLAUDE.md` 18+ gate note; `MFAChallengePage.tsx`).

**FR-AUTH-02 — Anonymous use with fair quota**
- Actor: anonymous visitor. Behaviour: server-signed session token; 5 messages per 24 h; clear message at limit with sign-in option.
- Rules: quota shared across replicas requires Redis (`backend/CLAUDE.md`). Failure: if Redis is down, quota degrades to per-process (documented risk).
- AC: 6th message returns 429 with `quota_exceeded: true` and the UI explains it.
- Priority: Must. Status: Live (`anonSession.ts`; `backend/CLAUDE.md` quota section).

**FR-PROF-01 — Profile and preferences**
- Behaviour: language, response preference, memory consent, notification settings, data export and deletion in one place.
- AC: every stored preference is visible and editable.
- Priority: Should. Status: Live (`ProfilePage.tsx`, `profile/settings/*`).

### 4.2 Conversation and understanding

**FR-CONV-01 — Ask a question and receive an answer**
- Actor: seeker. Pre: quota available. Trigger: send.
- Behaviour: stream status; return either (a) one or more verbatim clips with speaker, video, time window and label, (b) an honest no-match message with next steps, or (c) a safety response.
- Rules: no generated text in a teacher's voice (invariants 1, 15); every clip passes integrity gates (invariant 2).
- Inputs: text, language, session. Outputs: `content`, `citations[]`, `grounding_state`, `verification`, `safety_notices`, `route_decision`.
- Failure: backend error → retry once on 429/502/503/504 (`fetchWithRetry.ts:8`), then a clear error with helpline text on overload (`SERVER_BUSY_HELPLINE_MESSAGE`).
- AC: 100% of answers fall in (a), (b) or (c); none mixes generated prose into a teacher quote.
- TC: in-corpus, out-of-corpus, crisis, overload.
- Priority: Must. Status: Live (doc 05/10 for backend detail).

**FR-CONV-02 — Conversation history**
- Behaviour: list, rename, delete, export; synced for signed-in users.
- Rules: only the backend writes assistant turns (PRD-003). Retention default 90 days, user-configurable (`chatStorage.ts:311`).
- AC: deleting a conversation removes it locally and in Supabase.
- Priority: Must. Status: Live with defect PRD-003.

**FR-INT-01 — Understand the question type**
- Behaviour: classify into teaching question, personal/emotional, practice request, guru-specific, out-of-domain, greeting, crisis, ambiguous.
- Rules: emotional words alone must not force the distress lane for benign teaching questions — subject to the recorded clinician decision (Option 1 keeps the boundary) [HUMAN].
- AC: confusion matrix on a labelled set (doc 18) reported per class.
- Priority: Must. Status: Partial — S3 doc 10.

**FR-INT-02 — Ask a clarifying question when the question is ambiguous**
- Behaviour: for one-word or context-free questions, ask one short clarifying question instead of serving a clip.
- AC: "Why?" with no context → clarifying response.
- Priority: Should. Status: Absent [INF; S3 to confirm].

### 4.3 Sources, retrieval and attribution

**FR-SRC-01 — Choose a teacher**
- Behaviour: seeker can restrict to Sri Krishnaji, Sri Preethaji, or both.
- Rules: filter by verified speaker; no persona prompts; driven by the registry (doc 11 §6).
- AC: "only Preethaji" never returns a Krishnaji clip.
- Priority: Should. Status: Partial — backend `requested_gurus()` reads names in the question (`guru_registry.py:124`); UI switcher is persona-based and inconsistent (PRD-005).

**FR-RET-01 — Retrieve the most relevant verbatim clips**
- Behaviour: hybrid retrieval, rerank, relevance and standalone gates; abstain below threshold.
- AC: measured top-1 relevance and abstain rate on the golden set (doc 18).
- Priority: Must. Status: Live (S2 doc 08).

**FR-MV-01 — Multi-video evidence**
- Behaviour: when a question spans themes, show up to N clips from different videos, each with its own attribution, with no generated bridge text in a teacher's voice.
- Rules: conflicting positions shown separately (`ChatMessage.tsx:540` already has the note).
- AC: on multi-theme golden questions, clips come from ≥2 videos and are each relevant.
- Priority: Should. Status: Partial — UI supports sets; backend status in doc 07.

**FR-ATTR-01 — Attribution on every clip**
- Behaviour: show speaker only when voice-verified; otherwise "unverified clip"; show video title, link and time window.
- AC: no clip shows a teacher name with `speaker_verified !== true` (`types.ts:293–300`).
- Priority: Must. Status: Live.

**FR-ATTR-02 — No unsourced attributed quotations anywhere in the product**
- Behaviour: every sentence presented as a teacher's words resolves to a stored verbatim span.
- AC: test over tips, guides, courses, push captions.
- Priority: Must. Status: Absent — GURU-012.

**FR-SRCX-01 — Explore the source**
- Behaviour: open the video at the clip start; view the full transcript segment; see other clips from the same video.
- AC: playback starts at `start_ms − 0.25 s` (invariant 6).
- Priority: Should. Status: Partial — playback live (`CitationCard.tsx:194–204`); inspect-source uses a relative URL (PRD-001).

### 4.4 Answer composition

**FR-ANS-01 — Honest label**
- Behaviour: show "Related, not a direct answer" until a calibrated profile exists.
- AC: label present on 100% of clip answers without a profile.
- Priority: Must. Status: Live.

**FR-ANS-02 — Separate voice layers**
- Behaviour: visually separate (1) teacher's exact words, (2) app's own text (in its own voice), (3) personalised paraphrase ("In our own words — not a direct quote").
- AC: each non-verbatim block carries its label.
- Priority: Must. Status: Partial — personalised label exists (`ChatMessage.tsx:549`); S3 doc 10 covers other paths.

**FR-DEPTH-01 — Choose answer depth**
- Behaviour: short (one clip), standard (best clip + one related), deep (set across videos). User can ask "more" in conversation.
- AC: "tell me more" returns new, relevant clips, not a repeat.
- Priority: Should. Status: Partial — preference modes exist (`responsePreferences.ts:12–17`); effect on verbatim path not established [INF].

**FR-REFL-01 — Optional reflection prompt**
- Behaviour: after a clip, offer one reflection question written in the app's own voice, only when the seeker's preference allows.
- Rules: never phrased as the teacher speaking.
- Priority: Could. Status: Partial (`includeReflection` preference; generation off in FP-only mode).

**FR-FUP-01 — Follow-up continuity**
- Behaviour: understand references to earlier turns; avoid repeating the same clip.
- Priority: Should. Status: Partial — S3 doc 10.

### 4.5 Memory and personalisation

**FR-MEM-01 — Consent-based memory**
- Behaviour: remember only after explicit consent; show, edit and delete every memory.
- AC: no memory row without a consent receipt; deletion removes vectors too.
- Priority: Must (if memory is offered). Status: Live — S3 doc 12.

**FR-PERS-01 — Personalise a teaching**
- Behaviour: produce a paraphrase in the app's voice, clearly labelled, never as a quote.
- Priority: Could. Status: Flagged (`VITE_PERSONALIZE_TEACHING_ENABLED`).

### 4.6 Language

**FR-LANG-01 — Multilingual interface and questions**
- Behaviour: UI in 14 locales; questions in those languages; quotes shown in the original language with optional subtitles only if rights allow (doc 14c §5).
- AC: crisis detection works in every pilot language (native-speaker reviewed).
- Priority: Must. Status: Partial — 14 locales exist; native-speaker review pending (root `CLAUDE.md` Open work).

### 4.7 Saving, journeys and practice

**FR-SAVE-01 — Save an answer**
- Behaviour: save a clip answer to a personal collection with a note; revisit later.
- Priority: Should. Status: Absent from chat — favourites store practice slugs only (`favoritesStorage.ts`); Second Brain is a separate page with no "save answer" link from chat.

**FR-JRN-01 — Learning journey**
- Behaviour: user-chosen topic sequence built from verified clips; progress is the user's own record, not a score of spiritual progress.
- Priority: Could. Status: Partial — healing courses (`/api/healing`), daily journey, SRS exist; attribution issue (GURU-012).

**FR-PRAC-01 — Guided practice**
- Behaviour: practice steps with authorised audio or text only.
- Priority: Should. Status: Live with rights defect IP-002.

### 4.8 Feedback, correction, safety, data

**FR-FB-01 — Answer feedback**
- Priority: Must. Status: Live (`/api/feedback`).

**FR-CORR-01 — Report a clip; correction workflow**
- Behaviour: seeker report → admin queue → decision (keep, fix boundary, quarantine) → audit log; teachers' contact can request removal.
- AC: quarantined clip never serves again (serve-time check).
- Priority: Must. Status: Partial (PRD-006).

**FR-SAFE-01 — Crisis handling**
- Behaviour: crisis pre-check before retrieval; locale-appropriate helplines; no teaching clip in a crisis turn; no engagement prompts in that turn.
- AC: crisis probes in each pilot language route to helplines; push prompt suppressed (PRD-004).
- Priority: Must. Status: Live with gaps (S3 doc 14b; GURU-007).

**FR-DATA-01 — Export and delete my data**
- Behaviour: one export; one deletion path that deletes promptly and confirms; no retention offers inside the deletion flow.
- AC: deletion removes Supabase rows, memory vectors and push subscriptions; confirmation shown.
- Priority: Must. Status: Live (edge functions). Dormant second path `CancelFlow` must be removed (doc 12b UX-001).

### 4.9 Administration and extensibility

**FR-ADM-01 — Admin review of content and reports**
- Priority: Must. Status: Live (admin app; MFA AAL2).

**FR-ADM-02 — No demo data in production**
- Behaviour: demo seeding is impossible in production.
- AC: `seed_admin_demo` RPC is absent or disabled in production.
- Priority: Should. Status: Unknown — RPC exists and is callable from admin UI (`useSeedDemo.ts:22`) [LIVE-R].

**FR-TCH-01 — Onboard a new teacher by configuration**
- Behaviour: doc 11 §7.
- Priority: Could (later). Status: Absent (GURU-010).

---

## 5. Status summary

| Status | Count | FR ids |
|---|---|---|
| Live | 9 | AUTH-01, AUTH-02, PROF-01, CONV-01, RET-01, ATTR-01, ANS-01, FB-01, ADM-01 |
| Live with known defect | 4 | CONV-02 (PRD-003), PRAC-01 (IP-002), SAFE-01 (PRD-004, GURU-007), DATA-01 (UX-001) |
| Partial | 13 | ONB-01, INT-01, SRC-01, MV-01, SRCX-01, ANS-02, DEPTH-01, REFL-01, FUP-01, MEM-01, LANG-01, JRN-01, CORR-01 |
| Flagged | 1 | PERS-01 |
| Absent | 4 | INT-02, ATTR-02, SAVE-01, TCH-01 |
| Unknown | 1 | ADM-02 |

Total: 32 FRs. MEM-01 is listed as partial here because its internals are S3's to confirm.

## Cross-references

- Backend request flow: `05-current-architecture-and-request-flow.md` (S1)
- Answer behaviour and voice layers: `10-spiritual-answer-quality-expected-behavior.md` (S3)
- Memory internals: `12-personal-mentor-memory-ethical-retention.md` (S3)
- Retention UX: `12b-ethical-retention-and-mentor-ux.md`
- Teacher registry: `11-krishnaji-preethaji-future-guru-extensibility.md`
