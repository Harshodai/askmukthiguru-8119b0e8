# 14d — User journey and frontend walkthrough

> **2026-11-06:** Superseded in part by `specifications/PERSONAL_MENTOR_MEMORY_AND_PERSONALIZATION_SPEC.md` (what the personalisation controls must do for UX-006 and UX-009). Status of findings: `FINAL_PENDING_WORK_REGISTER.md`.

Owner: S4 (product, UX). Target: `origin/main@46b808fb`, read from the snapshot. Access date: 2026-11-04.

This document walks 14 steps through the real frontend and API code for two seekers:

- **A — anonymous first-time seeker** (no account, new browser).
- **R — returning signed-in seeker** (account, at least one earlier session).

Configuration assumption: first-person-only chat (root `CLAUDE.md` invariant 21) [DOC-CLAIM]. The deployed configuration is unknown [LIVE-R].

Out of scope here, because other documents own them:

| Topic | Owner |
|---|---|
| Journeys J1–J8, feature map, FR catalogue | `03` §1, §2, §4 |
| Streaks, churn funnel, win-back email, push timing | `12b` (UX-001…UX-004), `03` (PRD-004) |
| Deletion funnel, scheduled deletion never runs | `26` ADV-01 |
| Client translation of quotes has no label | `26` ADV-05 |
| Memory planes, memory on the teaching lane | `12` (MEM-001…MEM-006) |
| Answer depth, follow-up continuity, `answer_trace` | `10` |
| Crisis detection and helpline verification | `14b` (SAFE-001…SAFE-008) |

Known corrections respected: the `CancelFlow` deletion funnel is mounted and is the only UI path to account deletion (`src/pages/ProfilePage.tsx:583` → `src/components/profile/settings/AccountDataCard.tsx:137-195`). Questions without keywords go to the teaching lane, not to a general LLM. The code-default served collection is `first_person_v8`. Doc `03` FR-CONV-02 says history is "synced for signed-in users". Step 9 corrects that.

---

## 1. Step-by-step walkthrough

### Step 1 — Landing page

| Aspect | Detail |
|---|---|
| Code | `src/pages/Index.tsx:77-92` mounts Navbar, Hero, Meet the Gurus, How It Works, Practices, Wisdom Graph, Sample Wisdom, Serene Mind, Safety Pillars, Footer. Google One Tap shows when the capability is on (`:78`). Hero CTA "Ask your first question" links to `/chat` (`src/components/landing/HeroSection.tsx:256-259`). Hero has a mood check-in that routes to practices (`:154-161`). Microcopy: "No account needed." (`en.json` `landing.hero.microcopy`). [V-STATIC] |
| A experiences | A calm page with three ways in (ask, 3-minute pause, practice). Paraphrased teaching lines carry a "not a direct quote" note (`MeetTheGurusSection.tsx:148-156`, `SampleWisdomSection.tsx:127`). Good practice. [V-STATIC] |
| R experiences | Same page. `ContinuePracticeCard` in the hero (`HeroSection.tsx:387`) offers continuity. [V-STATIC] |
| Where it fails | The copy describes "an AI companion", "reflective guidance" and "Talk through what is on your mind" (`landing.demo.step_conversation_*`). The footer says "an AI companion trained on spiritual teachings" (`landing.footer.disclaimer`). On the teaching lane the product returns a recorded clip or a static abstain, and it is not "trained" on the teachings. The page never says "answers are short recordings of the teachers". → PRD-010. [V-STATIC] |

### Step 2 — Understanding the purpose (AI disclosure; what it is and is not)

| Aspect | Detail |
|---|---|
| Code | Hero disclaimer: "not medical, mental-health, or crisis care" (`landing.hero.disclaimer`). Safety pillars link to privacy, terms and crisis resources (`landing.safety.*`). In chat, `AiTransparencyBanner` (`src/components/compliance/AiTransparencyBanner.tsx:68`, mounted `ChatInterface.tsx:2532`) says "AskMukthiGuru is an AI. It draws on recorded teachings where it can find them, and it can make mistakes." It has a "Details" drawer. Dismissal persists in `localStorage` (`:13`, `:37-47`). `/trust` explains verbatim-first answers (`en.json` `trust.pageDescription`). [V-STATIC] |
| A | Sees the banner on the first chat visit. No tour for anonymous users (`src/pages/ChatPage.tsx:83-84`). |
| R | Banner stays hidden once it is dismissed. The guided tour runs once for signed-in users. |
| Where it fails | (1) The first chat message is a hard-coded English "guru" bubble: "dear seeker. I am here to guide you toward your beautiful state … together we shall explore" (`src/components/chat/ChatHelpers.tsx:65`, built at `:71`; inserted `ChatInterface.tsx:578-597`). It speaks as "I", in a guru-style bubble, before any disclosure of the clip model. (2) The "what it is" message is split across the landing, the banner, `/trust` and the guides. No one place tells the seeker the three possible outcomes: clip, honest no-match, or safety response. → PRD-010. [V-STATIC] |

### Step 3 — First question (composer, anonymous session, quota messaging)

| Aspect | Detail |
|---|---|
| Code | Starter cards (`ChatInterface.tsx:108-113`): "What is the Beautiful State…", "Guide me through a short breathing meditation", "I'm feeling overwhelmed…", "Share a teaching from Sri Preethaji on suffering". The anonymous token is minted with `POST /api/auth/anon-session` and cached in `localStorage` (`src/lib/chat/anonSession.ts:14`, `:18-31`, `:63-79`). If minting fails, `resolveSessionId` falls back to the client id (`:92-96`). The backend reserves one turn at admission and refunds failed turns (`backend/app/api/chat.py:136-146`). Defaults: 5 messages per 24 h, or 3 when degraded (`backend/app/config.py:1211-1214`). [V-STATIC] |
| A | Can send 5 messages. The quota is shown only after it is exhausted: `QuotaAuthPrompt` says "Free message limit reached … (5 of 5 used)" (`src/components/chat/QuotaAuthPrompt.tsx:16-19`). The 429 body carries `retry_after_seconds` (`chat.py:117-127`). The UI never shows it. The error copy says "try again when your message allowance is available" (`src/lib/chat/errors.ts:56-64`). |
| R | No quota prompt. |
| Where it fails | (1) A does not know the limit in advance. A also does not know that a static abstain uses one of the 5 turns [INF: abstain is a completed interaction]. (2) The prompt and the error copy are hard-coded English. (3) "Share a teaching from Sri Preethaji …" implies a teacher filter. Whether retrieval honours it is unverified [LIVE-Q]; doc `03` FR-SRC-01. → UX-011, UX-008. |

### Step 4 — Answer generation (loading, streaming, SSE, interruption, timeout, 429, 5xx, offline)

| Aspect | Detail |
|---|---|
| Code | `sendMessageStreaming` (`src/lib/chat/streaming.ts:36`). A 202 response queues the job and shows "Queued at position N…" (`:135-165`). SSE events: `status`, `stage`, `teaching_preview`, `final` (`:308`), `done` (`:320`), `error` (`:375`). The backend publishes `final` **before** `done` (`backend/app/orchestrator.py:447-468`). Citations, `verification`, `grounding_state` and `safety_notices` arrive only in `done` (`streaming.ts:320-368`). A missing `done` throws "The response stream ended before completion metadata was received." (`:251-254`, `:403-404`). [V-STATIC] |
| Error mapping | `httpStatusToErrorCode` (`errors.ts:5-16`): 401/403 → unauthorized; 408/504 → timeout; 429 → quota or rate_limited; ≥500 → server_error. A final 503 shows helpline text (`streaming.ts:201-204`; `fetchWithRetry.ts:35-39`). An SSE `error` event is mapped through status 409, so it becomes `unknown` unless it is `context_exhausted` (`streaming.ts:383`). |
| Interruption | `ChatInterface.tsx:1699-1765`. User stop: the partial text is kept with "_Stopped by you._". Disconnect after text arrived: the `final` text or the partial tokens are kept, with a toast "Connection interrupted / Response may be incomplete" (`:1720-1732`). Failure before any text with `network`/`unknown` while online: the client silently retries once through JSON `POST /api/chat` (`:1734-1745`). Otherwise a terminal error card appears. JSON path: 120 s abort and 120 s job polling (`transport.ts:168`, `:222`). A partial-stream checkpoint is restored on reload within 60 s with "(Response was interrupted — tap Regenerate…)" (`ChatInterface.tsx:602-622`). |
| Offline | Detection uses `navigator.onLine` or a fetch error string (`:1732`, `:2000`). There is no offline banner. The service worker never simulates answers (`public/sw.js:6`). |
| Where it fails | (1) A disconnect between `final` and `done` leaves the teacher's verbatim words on screen with no citation card, no speaker label and no "Related — not a direct answer" badge. `ChatMessage.tsx:254-256` renders nothing when citations are empty. The client also loses `safety_notices`, which on the teaching lane hold the support line for self-harm cues (`backend/app/pipeline/stages/first_person_bridge.py:1014-1036`, `:1069-1078`). The stripped message is then saved to history. → UX-005. (2) No client-side stream timeout exists. A stalled SSE runs until the seeker presses Stop [V-STATIC; behaviour INF]. (3) Error states other than 503 show no support line. → UX-007. |

### Step 5 — Teaching attribution (citation card, speaker, "Related, not a direct answer", playback window)

| Aspect | Detail |
|---|---|
| Code | Badge order (`ChatMessage.tsx:296-307`): Verified → Closest passages (not verified) → "Related teaching — not a direct answer" (`verification.direct === false`, `:237`) → Supporting → General. Speaker label (`src/lib/chat/types.ts:293-300`): the name shows only when `speakerVerified === true`; otherwise "shared in <channel>" or "unverified clip". No speaker → "Ekam teachings" (`CitationCard.tsx:13`). Playback: start is ceil and end is floor of the backend-padded window. The HTML5 player uses exact fractional `#t=` (`CitationCard.tsx:194-207`). This matches invariant 6. [V-STATIC] |
| A / R | Both see the same card. On the v8 collection most clips are not voice-verified (685 of 1,801 verified [DOC-CLAIM root `CLAUDE.md` inv. 23]), so "unverified clip" or "shared in <channel>" is the usual label [INF]. |
| Where it fails | (1) "unverified clip" has no explanation. A seeker can read it as "this may not be the teacher". The product means "voice not machine-verified". (2) The trust badges and the attribution strings are English in every locale. → UX-008. (3) The "Translate" popover on a clip is owned by `26` ADV-05. |

### Step 6 — Follow-up

| Aspect | Detail |
|---|---|
| Code | The client sends the last 20 messages, or 40 if the text has referential words (`src/lib/chat/transport.ts:52`). Follow-up chips use `follow_up_suggestions`. The teaching lane rewrites "tell me more" style questions with a regex heuristic (`first_person_bridge.py:761`; `backend/rag/resolve_followup.py:42-60`). [V-STATIC] |
| Where it fails | Each turn is a fresh retrieval. "Tell me more" can return the same clip or an unrelated one. Owned by `10` (answer_trace, T5-05). No new finding. |

### Step 7 — Longer conversation (context limit)

| Aspect | Detail |
|---|---|
| Code | The server owns the budget (`backend/services/chat_context_budget.py:42-110`). On `context_exhausted` the UI blocks sending, keeps the draft and offers "Start a new conversation" (`ChatInterface.tsx:1012-1016`; `errors.ts:29-37`; `ErrorCodePanel.tsx:23-26`). Every 6th user message, `maybeSummarize` runs (`ChatInterface.tsx:1172-1183`). [V-STATIC] |
| Where it fails | `generateSummary` sends `user_message: "Summarize our conversation so far."` to the seeker endpoint `POST {BACKEND_URL}/api/chat` with a client "system" prompt (`transport.ts:433-463`; endpoint `src/lib/chat/config.ts:9-10`). The backend drops client system messages (`03` PRD-002), so the teaching lane treats it as a seeker question. The reply (a clip or an abstain) is stored as `conversations.summary` and sent back as `conversation_summary` (up to 4,000 chars) on later turns (`transport.ts:59`). → PRD-009. |

### Step 8 — Returning user

| Aspect | Detail |
|---|---|
| Code | The welcome bubble is personalised from the local pre-practice log and the last meditation mood (`ChatInterface.tsx:578-597`; `ChatHelpers.tsx:71-99`). The last conversation id is kept in local storage. |
| R experiences | On the **same device and same session**, R sees past conversations (at most 10) and a "welcome back" greeting. After a sign-out, a session expiry or on a new device, R sees an empty sidebar. → UX-006. |
| Where it fails | Continuity depends on one browser's `localStorage`, not on the account. |

### Step 9 — Previous conversations (storage, sync, deletion)

| Aspect | Detail |
|---|---|
| Storage | Local-first in `localStorage` or Capacitor Preferences (`src/lib/chatStorage.ts:11-21`). Local list is trimmed to `getMaxConversations()`, default **10** (`:302-309`, `:590-603`). No UI writes `askmukthiguru_max_conversations`. |
| Sync | One-way and fire-and-forget: `syncConversationToDb` upserts `conversations` and inserts only new `chat_messages` ids (`:396-445`). The comment calls it an "analytics/backup table" (`:433-436`). **No code reads `conversations` or `chat_messages` back into the UI.** The only `.from('conversations')` calls are upsert, delete, rename and summary update (`:407`, `:625`, `:667`, `:699`). [V-STATIC] |
| Wipe on identity change | `clearLocalChatData` removes local conversations, feedback and the retention setting (`:22-39`). It runs on explicit sign-out (`src/components/common/UserMenu.tsx:131-137`) and on **every** `SIGNED_OUT` event, including expiry (`src/components/common/SessionExpiredHandler.tsx:41-50`, `:88-92`). |
| Deletion | `deleteConversation` deletes locally, then in Supabase. Cloud errors are only logged (`chatStorage.ts:616-633`). Supabase-js returns `{error}` and does not throw, so an RLS failure would be silent [INF]. Policies allow owner delete (`supabase/migrations/…backend_improvements.sql` `own_conversations_delete`, `own_messages_delete`). |
| Retention | Local retention is 90 days (`:312-319`), purged at app load (`src/App.tsx:208`). `setRetentionDays` has **no caller** [V-STATIC], so doc `03` FR-CONV-02 "user-configurable" is not true in the UI. The server column `conversations.retention_days` defaults to 90 (`supabase/migrations/20260712000000_add_retention_and_summary.sql:24`). |
| Where it fails | Conversations that drop off the local list or are wiped at sign-out stay on the server. The seeker cannot see, reopen or delete them one by one. They can only reach them through "Export cloud data" or account deletion. → UX-006. |

### Step 10 — Personalisation (what actually changes the answer)

| Signal sent | Where set | Read on the teaching lane? |
|---|---|---|
| `response_preferences` (mode, practice, reflection, action step) | `ResponsePreferencesMenu.tsx:47-76`; desktop only (`ChatHeader.tsx:134`, `hidden sm:block`) | No: 0 references in `first_person_bridge.py`, `rag/nodes/first_person.py`, `services/first_person_pipeline.py` [V-STATIC] |
| `guru_tone`, familiarity | Profile; preview copy "Clear, concise guidance…", "explains spiritual terms plainly…" (`src/components/profile/GuidancePreview.tsx:11-21`) | No (same grep) |
| `seeker_context` (memories) | `transport.ts` | No (same grep); see `12` MEM-002 |
| `personalize_teaching` | Flagged button | Separate `PersonalizeStage`, labelled "In our own words" (`03`) |
| `language` | Selector | Glue text only; quotes never translated (`first_person_bridge.py:328`) |

What does change the answer on the teaching lane: the question text, the language of glue text, and the safety lanes [V-STATIC]. The controls and the memory banner ("to tailor future guidance", `en.json` `chat.memoryBanner.toastEnabledDesc`) promise more. → UX-009.

### Step 11 — Language

| Aspect | Detail |
|---|---|
| Code | `handleLanguageChange` sets the AI language, clears the response cache, saves the profile and switches the UI language (`ChatInterface.tsx:886-903`). There are 14 locale files with identical key sets (1,937 keys each) [V-STATIC]. |
| What is translated | Glue and notices on the backend, within a 5 s fail-open budget. Quotes stay in the original language. The UI chrome is translated. |
| Where it fails | 33 of 234 `t()` keys in 8 chat components are missing from **every** locale file, including `en.json`. They fall back to inline English. They include every trust badge (`chat.teachingContext.relatedBadge`, `partialBadge`, `chat.guruTeaching.*`), the whole abstain help card (`chat.abstainHelp.*`), the conflict disclosure and "Play clip". Hard-coded English also appears in `errors.ts` titles, `QuotaAuthPrompt`, "unverified clip" and "shared in …" (`src/lib/chat/types.ts:297-299`), "Watch on YouTube" (`CitationCard.tsx:235`), the welcome text and the `GuidancePreview` copy. A Hindi seeker therefore gets Hindi chrome with English trust and error labels. → UX-008. Native-speaker review of crisis detection is owned by `14b`. |

### Step 12 — Profile

| Aspect | Detail |
|---|---|
| Code | Tabs: journey, profile, memory, settings (`ProfilePage.tsx:346-367`). Settings holds Security, Preferences, Account & Data and Support (`:580-584`). Streaks and the heatmap are owned by `12b`. |
| Where it fails | The profile shows tone and familiarity with a preview that the teaching lane ignores (UX-009). Most of the profile copy is in locale files. |

### Step 13 — Error recovery (rendered states and silent failures)

| State | Rendered as | Recovery |
|---|---|---|
| network | "Connection problem" + cause + code + "Copy trace" (`errors.ts`, `ErrorCodePanel.tsx:50-56`) | Retry |
| timeout | "The response took too long" | Retry |
| rate_limited | "Please try again shortly" | Retry |
| quota_exceeded | Error card + `QuotaAuthPrompt` | Sign in |
| unauthorized | "Sign-in required" | Sign in |
| server_error (non-503) | "Something went wrong … Please retry." | Retry |
| server_error 503 | "The service is very busy" + helplines | Retry |
| context_exhausted | "Conversation context limit reached" | New chat, draft kept |
| stream interrupted after text | Toast; partial or `final` text kept | Regenerate (UX-005) |
| backend HTML instead of SSE | "Backend not reachable … Set VITE_BACKEND_URL" (`streaming.ts:217-227`) | Developer-facing text shown to seekers [V-STATIC] |

Silent failures [V-STATIC]: cloud sync (`chatStorage.ts:443-445`), cloud delete (`:626-628`), summary (`transport.ts:459-462`), title (falls back to the first 48 chars), anonymous token minting (`anonSession.ts:28-30`). All of them log to the console only.

Gaps: (1) Only the 503 state carries a support line. A seeker who writes a crisis message while the backend is down, slow or erroring sees an error code, not a helpline. The client has no local crisis fallback (`src/lib/crisisHelplines.ts` is used only for the 503 copy). → UX-007. (2) The error card leads with a monospace error code and "Copy trace". That is engineering language for a seeker [INF]. (3) Titles are English (UX-008).

### Step 14 — Privacy and account control

| Control | Code | Status |
|---|---|---|
| Incognito | Header note "Not saved to history, personal memory, or your personal wisdom map" (`ChatHeader.tsx:135`). `saveConversation` returns early (`chatStorage.ts:591`). | Live [V-STATIC]. The requests still reach the backend. |
| Export | "Export local data"; "Export cloud data" through the `export-my-data` edge function (`AccountDataCard.tsx:104-131`) | Live. The cloud export is the only way to see conversations the UI no longer lists (UX-006). |
| Delete conversation | Sidebar confirm → `deleteConversation` | Live; cloud failure is silent |
| Delete account | Only through `CancelFlow` (`AccountDataCard.tsx:137-195`) | See `12b` UX-001 and `26` ADV-01 |
| Memory consent and controls | `MemoryConsentBanner` (signed-in, not incognito, `:31`, `:39`); `MemoryManager` in Profile → memory | See `12` |
| Retention setting | No UI (step 9) | Gap |
| WhatsApp | Header button always shown (`ChatHeader.tsx:61-63`, `:138-148`). The backend reports `whatsapp: disabled_by_policy` (`backend/app/api/capabilities.py:73`). `VITE_WHATSAPP_NUMBER` is not set in any repo env file, so the link is `https://wa.me/?text=…` (a share sheet with no recipient). | → UX-010 |

---

## 2. Findings

### UX-005 — An interrupted stream shows teacher words without attribution, label or safety notices
| Field | Value |
|---|---|
| Pillars | P4, P3 |
| Category | Frontend wiring / attribution |
| Severity | P2 |
| Type | Confirmed defect (static); frequency [LIVE-R] |
| Confidence | High |
| Evidence | `backend/app/orchestrator.py:447-468` (`final` before `done`); `src/lib/chat/streaming.ts:308`, `:320-368`, `:403-404`; `src/components/chat/ChatInterface.tsx:1720-1732` keeps `streamedFinalText` and only shows a toast; `ChatMessage.tsx:254-256` renders no grounding panel without citations; `first_person_bridge.py:1014-1036`, `:1069-1078` (support line only in `safety_notices`) |
| Actual behaviour | A disconnect after `final` and before `done` leaves verbatim clip text with no speaker, no video, no "Related" badge and no support line. It is saved to history in that state. |
| Expected behaviour | Teacher text never renders without its citation and label. Safety notices never get lost. |
| Root cause | The client treats `final` text as complete. The metadata contract lives in a separate, later event. |
| User impact | An unattributed quote. A seeker with a self-harm cue can lose the support line. |
| Downstream impact | Unattributed text in local and cloud history; misleading feedback rows. |
| Dependencies | T5-03 (API contract) |
| Remediation | Hold `final` until `done` arrives. On a done-less disconnect, re-fetch the job result (`/api/jobs/{id}`) or show "Answer could not be completed" with no teacher text. Send citations and `safety_notices` in or before `final`. |
| Acceptance criteria | Simulated cut between `final` and `done` → no teacher text without its citation; support line present when the server sent one. |
| Regression test | Vitest: mocked SSE stream truncated after `final` (`src/test/chat/`), plus a `ChatInterface` render test. |
| Implementation risk | Low; perceived latency rises slightly. |
| Verification | [V-STATIC] |

### UX-006 — Conversation history is tied to one browser, capped at 10 and wiped at sign-out; the cloud copy is never shown
| Field | Value |
|---|---|
| Pillars | P5, P6, P4 |
| Category | Returning-user continuity / data control |
| Severity | P1 |
| Type | Confirmed defect |
| Confidence | High |
| Evidence | `src/lib/chatStorage.ts:302-309` (default 10), `:590-603` (trim), `:396-445` (one-way sync, insert-only), `:22-39` (`clearLocalChatData`); `UserMenu.tsx:131-137`; `SessionExpiredHandler.tsx:41-50`, `:88-92`; no `select` on `conversations` in `src/` (grep) |
| Actual behaviour | On sign-out, session expiry or a new device, the sidebar is empty. The 11th conversation drops the oldest. The server keeps all of them. The seeker cannot list, reopen or delete those one by one. |
| Expected behaviour | A signed-in seeker sees their account's conversations on any device and can delete each one (FR-CONV-02). |
| Root cause | The cloud table was built as a backup, not as the source of truth. Identity-change hygiene clears the only readable copy. |
| User impact | Returning seekers lose access to past reflections. Server-held conversations are not visible to their owner. |
| Downstream impact | Doc `03` FR-CONV-02 status is wrong. PRD-003 (client-written history) makes a read-back riskier until T6-05 is done. |
| Dependencies | T6-05, T6-06 |
| Remediation | After T6-05, load the conversation list from Supabase for signed-in users (paged). Remove the 10-item cap for the cloud list. Keep the local purge on sign-out. Add a retention control that updates `conversations.retention_days`. |
| Acceptance criteria | Sign out → sign in → the same conversations are listed. A second device shows them. Deleting from the list removes the server rows. |
| Regression test | e2e (Playwright) with a seeded user: sign-out/sign-in round trip; 12 conversations all listed. |
| Implementation risk | Medium: a merge of local and cloud lists; RLS reads. |
| Verification | [V-STATIC]; [LIVE-R] for row counts |

### UX-007 — Error states other than 503 give no support line
| Field | Value |
|---|---|
| Pillars | P4, P6 |
| Category | Safety UX |
| Severity | P2 (S3 may raise; doc `14b` owns crisis policy) |
| Type | Confirmed defect |
| Confidence | High |
| Evidence | `src/lib/chat/errors.ts:79-89` (only `status === 503` adds `SERVER_BUSY_HELPLINE_MESSAGE`; generic copy at `:90-97`); `fetchWithRetry.ts:35-39`; no crisis check on the client error paths (`ChatInterface.tsx:1746-1765`, `:1990-2025`) |
| Actual behaviour | Network, timeout, 5xx other than 503, 401 and 429 show a code and "retry". The server-side crisis pre-check never ran. |
| Expected behaviour | Every failed turn shows one neutral line: "If you are in distress, help is available now: …" with call-verified lines only (T4-07). |
| Root cause | RP-A2 covered only the overload state. |
| User impact | A seeker in crisis, with the backend down (Railway is stopped per root `CLAUDE.md`), gets no resource. |
| Dependencies | T4-07 (call-verified helplines) |
| Remediation | Append the support line to every terminal error card. It is static text and needs no detection. |
| Acceptance criteria | Each `MessageErrorKind` card renders the support line; snapshot test. |
| Regression test | `src/test/chat/errors.test.ts` over all kinds. |
| Implementation risk | Low |
| Verification | [V-STATIC] |

### UX-008 — Trust labels, the abstain card, errors and quota copy are English in all 13 non-English locales
| Field | Value |
|---|---|
| Pillars | P4, P6 |
| Category | Localisation |
| Severity | P2 |
| Type | Confirmed defect |
| Confidence | High |
| Evidence | Script over 8 chat components: 33 of 234 `t()` keys are absent from every `src/locales/*.json`, for example `chat.teachingContext.relatedBadge`, `chat.guruTeaching.relatedBadge`, `chat.guruTeaching.unverifiedBadge`, `chat.abstainHelp.title`. Hard-coded: `errors.ts` titles, `QuotaAuthPrompt.tsx:16-19`, `src/lib/chat/types.ts:297-299`, `CitationCard.tsx:235`, `ChatHelpers.tsx:65`, `GuidancePreview.tsx:11-21`. |
| Actual behaviour | The honesty labels that matter most ("Related — not a direct answer", "unverified clip") and the no-match help card show in English. |
| Expected behaviour | Every trust, safety and error string exists in every pilot locale and is native-reviewed (FR-LANG-01). |
| Root cause | Inline `t(key, fallback)` defaults hide missing keys. No CI check for missing keys. |
| User impact | Non-English seekers can miss the "not a direct answer" meaning. |
| Dependencies | Native reviewers [HUMAN] (root `CLAUDE.md` Open work) |
| Remediation | Add the keys. Add a CI guard: every `t('…')` key must exist in `en.json` and in each locale. Move hard-coded strings into the locale files. |
| Acceptance criteria | Guard passes with 0 missing keys. Hindi render shows Hindi badges. |
| Regression test | New `scripts/guards` check plus a Vitest i18n coverage test. |
| Implementation risk | Low; translation quality needs review. |
| Verification | [V-STATIC] |

### UX-009 — Personalisation controls promise effects that the teaching lane ignores
| Field | Value |
|---|---|
| Pillars | P5, P2 |
| Category | Product honesty |
| Severity | P3 |
| Type | Confirmed defect (UI promise vs. teaching-lane code); deployed effect [LIVE-R] |
| Confidence | Medium (glue text may vary) |
| Evidence | `GuidancePreview.tsx:11-21`; `ResponsePreferencesMenu.tsx:47-76`; `en.json` `chat.memoryBanner.toastEnabledDesc`; 0 references to `response_preferences`, `guru_tone`, `seeker_context`, `memory_context` in the three teaching-lane files (grep) |
| Actual behaviour | The seeker picks "gentle / beginner / include practice". The clip and its label are the same. |
| Expected behaviour | Show only the controls that change the output, or label them "applies to practices and general replies". |
| Root cause | The controls predate first-person-only mode. |
| User impact | Lower trust when a promised effect never appears. |
| Dependencies | T6-03, `12` MEM-002, `03` FR-DEPTH-01 |
| Remediation | Hide or relabel them now. Later map depth to clip length or number of clips (verbatim-safe). |
| Acceptance criteria | Every visible preference changes a rendered output, or carries a scope label. |
| Regression test | Component test for the labels. |
| Implementation risk | Low |
| Verification | [V-STATIC] |

### UX-010 — The WhatsApp button points to a disabled channel or to a blank share
| Field | Value |
|---|---|
| Pillars | P6 |
| Category | Dead entry point |
| Severity | P3 |
| Type | Confirmed defect |
| Confidence | High |
| Evidence | `ChatHeader.tsx:61-63`, `:138-148` (unconditional); `capabilities.py:73` `"whatsapp": "disabled_by_policy"`; `VITE_WHATSAPP_NUMBER` is not set in any repo env file |
| Actual behaviour | Default build: WhatsApp opens with no recipient. With a number set, messages go to a bot that is off. |
| Expected behaviour | Show the button only when the `whatsapp` capability is enabled. |
| Remediation | Gate on `useChatCapabilities()`. |
| Acceptance criteria | Disabled capability → no button. |
| Regression test | `ChatHeader` render test with both capability states. |
| Implementation risk | Low |
| Verification | [V-STATIC] |

### UX-011 — The anonymous quota is invisible until it runs out, and the reset time is hidden
| Field | Value |
|---|---|
| Pillars | P5, P6 |
| Category | Onboarding |
| Severity | P3 |
| Type | Product gap |
| Confidence | High |
| Evidence | `QuotaAuthPrompt.tsx:16-19`; `errors.ts:56-64`; `chat.py:117-127` returns `retry_after_seconds` and `remaining`, which the UI does not use before the limit |
| Actual behaviour | "No account needed" on the landing page. After 5 turns (abstains included) the seeker is stopped. |
| Expected behaviour | After the first answer, show "N of 5 free questions left today". At the limit, show "Resets in ~X h". |
| Dependencies | FR-AUTH-02 |
| Remediation | Return `remaining` on success responses too, and render it. Translate it. |
| Acceptance criteria | Counter visible from turn 1; reset time shown at the limit. |
| Regression test | Vitest on the `done` metadata and the 429 parsing. |
| Implementation risk | Low |
| Verification | [V-STATIC] |

### PRD-009 — The conversation summary is made by sending "Summarize our conversation so far." to the seeker chat endpoint
| Field | Value |
|---|---|
| Pillars | P3, P1, P5 |
| Category | Wiring |
| Severity | P2 |
| Type | Confirmed defect (static call); the stored content is [INF] / [LIVE-L] |
| Confidence | High (call); Medium (effect) |
| Evidence | `src/lib/chat/transport.ts:433-463`; `ChatInterface.tsx:1172-1183` (every 6th user message, not incognito); `src/lib/chat/config.ts:9-10` (`/api/chat`); `backend/app/schemas/__init__.py:25` `_ALLOWED_ROLES` drops `system` (`03` PRD-002); `chat.py:710` uses `conversation_summary` |
| Actual behaviour | An extra seeker-style turn runs the full pipeline: gates, scorer LLM, telemetry. The reply is a clip or a static abstain. It is saved as the summary and sent with later turns. |
| Expected behaviour | No summary call, or a dedicated server endpoint that the server owns. |
| Root cause | Legacy client code from the generation era. |
| User impact | Hidden cost and latency. Nonsense "summary" context. Analytics show questions the seeker never asked. |
| Downstream impact | `12` MEM-005 (unfenced summary). |
| Dependencies | T6-05, T7-04 |
| Remediation | Remove `maybeSummarize` and `generateSummary`. If continuity needs a summary, the server makes it after T5-05. |
| Acceptance criteria | No request with `user_message` "Summarize our conversation so far." in a 12-turn e2e. |
| Regression test | Vitest: no fetch to `/api/chat` from summary code; a lint guard on the literal. |
| Implementation risk | Low |
| Verification | [V-STATIC] |

### PRD-010 — Landing and welcome copy promise a conversational guide; the teaching lane answers with a clip or a static abstain
| Field | Value |
|---|---|
| Pillars | P2, P4, P5 |
| Category | Expectation setting |
| Severity | P2 |
| Type | Product gap |
| Confidence | High |
| Evidence | `en.json` `landing.demo.step_conversation_title` "Talk through what is on your mind"; `landing.footer.disclaimer` "AI companion trained on spiritual teachings"; `ChatHelpers.tsx:65` "I am here to guide you … together we shall explore"; root `CLAUDE.md` invariant 21 |
| Actual behaviour | The seeker expects dialogue and gets a recording or "no direct match". Abstains feel like failure. |
| Expected behaviour | Before the first question, say: "You will hear the teachers' own recorded words when a matching talk exists; otherwise you will be told honestly and offered a practice." |
| Root cause | Marketing copy predates first-person-only mode. |
| User impact | Early disappointment and low trust in abstains [INF; no user research, `02` PRD-008]. |
| Dependencies | T2-07 (usability test), FR-ONB-01 |
| Remediation | Rewrite the welcome as neutral product voice (not "I"). Add a three-outcome explainer. Replace "trained on". |
| Acceptance criteria | A usability test: ≥80% of participants predict the answer format before asking. |
| Regression test | Copy snapshot test; voice-lint for "I am here to guide you". |
| Implementation risk | Low |
| Verification | [V-STATIC]; [HUMAN] for the test |

---

## 3. Step summary

| # | Step | Works | Breaks | Finding | Task suggestion |
|---|---|---|---|---|---|
| 1 | Landing | Clear scope disclaimers; paraphrases labelled; anonymous start | Promises a "companion"; "trained on" | PRD-010 | Rewrite copy (FR-ONB-01) |
| 2 | Purpose / AI disclosure | Chat banner; `/trust` page | Guru-voice English welcome; no three-outcome explainer | PRD-010 | Neutral welcome + explainer |
| 3 | First question | Signed token; refund on failure; starter cards | Quota invisible until exhausted; English prompt | UX-011, UX-008 | Show remaining count and reset time |
| 4 | Answer generation | Queue status; stop; JSON fallback; 503 helpline | Done-less disconnect drops citation and notices; no stream timeout | UX-005, UX-007 | Gate `final` on `done`; job re-fetch |
| 5 | Attribution | Verified-only names; "Related" badge; exact playback window | "unverified clip" unexplained; English badges | UX-008 | Explain the label; localise |
| 6 | Follow-up | History window; chips | Fresh retrieval each turn | — (`10`) | T5-05 |
| 7 | Long conversation | Server budget; draft kept | Summary call runs as a seeker question | PRD-009 | Remove client summary |
| 8 | Returning user | Same-device welcome back | Nothing after sign-out or on a new device | UX-006 | Cloud read-back after T6-05 |
| 9 | Previous conversations | Local list; delete; local export | Cap 10; wipe at sign-out; no cloud read; retention has no UI | UX-006 | Cloud list + retention control |
| 10 | Personalisation | Personalise-teaching is labelled | Tone, depth and memory do not change clips | UX-009 | Hide or relabel; T6-03 |
| 11 | Language | UI chrome in 14 locales; quotes not translated | 33 trust and abstain keys missing; hard-coded English | UX-008 | Key guard in CI |
| 12 | Profile | Tabs; preferences; data card | Preview promises unused effects | UX-009 | Same as 10 |
| 13 | Error recovery | Typed error cards; retry; draft kept | No support line except 503; dev text on HTML fallback; silent sync failures | UX-007 | Static support line on all errors |
| 14 | Privacy and control | Incognito; local and cloud export; memory consent | Deletion via funnel (`12b`/`26`); hidden server conversations; WhatsApp dead link | UX-006, UX-010 (+UX-001, ADV-01) | T1-12; gate WhatsApp |

## Cross-references

`02` (personas, PRD-008), `03` (journeys, PRD-001…PRD-007, FR catalogue), `10` (answer depth, follow-ups), `12` (MEM-002, MEM-005), `12b` (UX-001…UX-004), `14b` (SAFE-*), `20` (T4-07, T5-03, T5-05, T6-03, T6-05, T6-06, T7-04), `26` (ADV-01, ADV-05).
