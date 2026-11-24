# Implementation Plan: WhatsApp Secure Website-Linked Companion

**Document:** `.claude/tasks/2026-11-22-whatsapp-companion.md`  
**Date:** 2026-11-22  
**Target:** WhatsApp Companion Integration (FastAPI + Celery + React/Vite + Meta WhatsApp Cloud API v21+)  
**Governing Standard:** Invariant X24 (Zero synthetic prose), Invariant X40 (Licensed rights clearance), DPDP Consent Separation, Zero Disconnection of Mobile Phone App (Coexistence).

---

## 1. Executive Summary & Problem Analysis

AskMukthiGuru aims to provide a direct companion channel over WhatsApp using the existing official WhatsApp Business phone number.
A critical repository and operational invariant is **Zero Disconnection of the Mobile Phone App**: the existing WhatsApp Business app on the physical phone must remain 100% operational for day-to-day manual conversations, voice calls, and customer contacts.

### Key Findings & Verified Defects in Existing Scaffolding:
1. **Frontend Consent Default Defect:** In `src/pages/LinkWhatsAppPage.tsx`, `initialSyncConsent` and `initialMemoryConsent` default to `true`. DPDP compliance and user trust require optional storage and memory to start **unchecked (`false`)**.
2. **Address Bar Secret Exposure:** Linking token `#code=...` remains in the browser address bar after page load, creating referrer leak and history capture risks. It must be stripped via `window.history.replaceState`.
3. **Unauthenticated Orchestrator Call:** In `backend/tasks/whatsapp_tasks.py`, the Celery worker calls `POST /api/chat?wait=true` as an unauthenticated HTTP request with an unsigned deterministic UUID (`uuid.uuid5(uuid.NAMESPACE_DNS, f"whatsapp:{p_hash}")`), bypassing linked user authentication, tenant isolation, and personalized context.
4. **Phony STOP / RESET Implementation:** In `backend/app/api/whatsapp.py`, receiving `STOP` or `RESET` sends a confirmation message to the user, but **never persists** the opt-out status or clears the conversation context in Redis/database.
5. **Expired Graph API Version & False Delivery Logging:** In `backend/tasks/whatsapp_tasks.py`, outbound messages are hardcoded to `v18.0` (expired) and log "delivered" immediately upon Meta API HTTP 200 acceptance, conflating API receipt with actual delivery callback status.
6. **Coexistence Misconception in Docs:** Existing documentation in `META_COEXISTENCE_ONBOARDING_GUIDE.md` suggests an ordinary developer portal "Add Number" flow, which actually risks deregistering the physical SIM. Coexistence requires **Meta Embedded Signup v4 with Session Logging** via an approved Tech Provider.

---

## 2. Technical Architecture & End-to-End Flow

```
[User on WhatsApp]
       │
       ▼ (Inbound Text: "Hi" / "LINK")
[Meta Cloud API Webhook]
       │ (HMAC-SHA256 signature verification)
       ▼
[FastAPI: POST /api/whatsapp/webhook]
       │
       ├─► [Command Engine: STOP/START, RESET, HELP, LINK]
       │        └─► Persist Opt-out / Clear Redis Turn Context / Emit Challenge Link
       │
       └─► [Durable Celery Task: process_whatsapp_turn_task]
                │
                ├─► 1. Crisis Preemption (Tele-MANAS 14416 / 112)
                ├─► 2. Resolve Phone Hash -> Linked User ID & DPDP Consents
                ├─► 3. Invoke Internal Chat Coordinator (Direct Service Call with User Context)
                ├─► 4. Format Sourced Reply (Exact Quotes, Timestamps, Video Links, Split at 4096 chars)
                ├─► 5. Send Outbound via Meta Graph API v21+ (Preserve Message ID)
                └─► 6. If sync_history_consent=True: Sync to User Web Conversation History
```

---

## 3. Workstreams & Tasks Breakdown

### Workstream 1: Setup Confirmation & Coexistence Safety
- **Task 1.1: Clarify Meta Setup & Credentials Protocol**
  - Verify if a Meta Developer App (`Business` type) with WhatsApp product already exists under the owner's Business Portfolio.
  - Re-verify Meta's official AI-provider policy (India general-purpose restrictions) and ensure AskMukthiGuru is strictly scoped as a scripture-grounded spiritual companion and account tool.
  - Surface coexistence onboarding choices (Meta Embedded Signup v4 via Tech Provider) before any number modification.
- **Task 1.2: Correct Coexistence Documentation**
  - Update `docs/whatsapp/META_COEXISTENCE_ONBOARDING_GUIDE.md` to remove misleading references to manual dashboard number addition and pin the exact v4 Embedded Signup requirements.

### Workstream 2: Secure Signup & Two-Channel Account Linking
- **Task 2.1: Frontend Linking Page Hardening (`src/pages/LinkWhatsAppPage.tsx`)**
  - Change initial state: `initialSyncConsent` = `false`, `initialMemoryConsent` = `false`.
  - Strip code from URL bar immediately upon parsing: `window.history.replaceState({}, document.title, window.location.pathname)`.
  - Clear `sessionStorage.getItem("pending_whatsapp_token")` upon verification or expiration.
  - Ensure clear visual distinction between "Connected", "Disconnected", and "Service Unavailable".
- **Task 2.2: Profile Connection Card (`src/components/profile/settings/WhatsAppCard.tsx`)**
  - Display masked phone number (`+91 98*** **210`), linked date, and independent toggles for Chat History Sync and Personal Memory.
  - Implement Disconnect (Unlink) action with confirmation modal and cleanup.
- **Task 2.3: Backend Two-Channel Verification (`backend/services/whatsapp_service.py` & `backend/app/api/whatsapp.py`)**
  - Verify linking tokens: 32-byte cryptographic random, hashed at rest with SHA-256, 15-minute expiry, atomic single-use.
  - Enforce originating phone confirmation: challenge requires WhatsApp conversation origin before web binding can complete.

### Workstream 3: Real Teaching Workflow & Orchestrator Integration
- **Task 3.1: Server-Side Linked Identity Resolution (`backend/tasks/whatsapp_tasks.py`)**
  - Eliminate the unauthenticated HTTP call to `POST /api/chat`.
  - Resolve phone number hash to authenticated `user_id` in `whatsapp_account_links`.
  - Invoke internal container orchestrator (`container.chat_engine` or `orchestrator_utils.prepare_request_state`) with authenticated user context.
- **Task 3.2: Teaching Formatting & Grounding Preservation**
  - Preserve exact teacher words (Sri Preethaji & Sri Krishnaji) without synthetic glue prose (Invariant X24).
  - Format citations into readable WhatsApp text with YouTube timestamps (`format_whatsapp_message`).
  - Implement safe split boundaries: if formatted message exceeds 4,096 characters, split at paragraph boundaries rather than truncating citations or quotes.

### Workstream 4: Optional History, Memory, and Profile Continuity
- **Task 4.1: Decoupled Consent Enforcement**
  - Separate `sync_history_consent` (web chat history reflection) from `memory_write_consent` (long-term persona store).
  - If `sync_history_consent == False`: do NOT write turn to `conversations` or `chat_messages`.
  - If `memory_write_consent == False`: run request with `incognito=True` behavior, suppressing canonical memory extraction and persona store writes.
- **Task 4.2: Revocation & Unlink Flow**
  - When user unlinks via Profile or sends `UNLINK` on WhatsApp, update status to `unlinked`, set `sync_history_consent=False`, `memory_write_consent=False`.
  - Purge active turn session in Redis.

### Workstream 5: Reliable Inbound Receiving, Replies, and Delivery Tracking
- **Task 5.1: Webhook Inbound Hardening (`backend/app/api/whatsapp.py`)**
  - Validate `X-Hub-Signature-256` using constant-time HMAC check against `META_APP_SECRET`.
  - Verify recipient phone number ID matches configured `META_PHONE_NUMBER_ID` (prevent cross-tenant injection).
  - Enforce deduplication via message ID (`wamid`).
  - Immediate preemption for acute self-harm/suicide (Tele-MANAS `14416` and emergency `112`).
- **Task 5.2: Real STOP / RESET Persistence**
  - On `STOP` / `OPTOUT`: persist opt-out status in `whatsapp_account_links.status = 'opted_out'`, block future automated outbound messages until `START`.
  - On `RESET`: clear user session conversation state in Redis (`whatsapp:session:{p_hash}`).
- **Task 5.3: Graph API v21+ Modernization & Delivery Status Correlator**
  - Replace expired `v18.0` with configurable Graph version (default `v21.0`).
  - Capture Meta outbound message ID (`messages[0].id`).
  - Handle inbound `statuses` callbacks (`sent`, `delivered`, `read`, `failed`), logging accurately without marking accepted as delivered.
  - Implement 24-hour service window check (error code `131047`).

### Workstream 6: Bank-Style Native Experience & Menus
- **Task 6.1: Native WhatsApp Interactive Buttons & Lists**
  - Support interactive reply buttons for core navigation:
    - 📖 *Ask a Question*
    - 🧘 *Today's Practice*
    - 👤 *My Account*
    - 🛡️ *Privacy & Consents*
    - 💬 *Human Help*
  - Accept natural language questions seamlessly at any time without trapping users in button trees.
- **Task 6.2: Human Handoff & Coexistence Pause**
  - If user selects "Human Help" or staff replies manually on the physical WhatsApp Business phone app, temporarily pause automated bot replies for 60 minutes to prevent automation from colliding with human agent conversation.

---

## 4. Test Plan & Acceptance Matrix

| Test Seam | Test File | Target Invariant / Verification |
|---|---|---|
| **Consent Defaults** | `src/test/whatsappIntegration.test.tsx` | Asserts history and memory switches start `false` (unchecked). |
| **Address Bar Secret Stripping** | `src/test/whatsappIntegration.test.tsx` | Asserts token is scrubbed from browser URL bar after mounting. |
| **HMAC Signature Security** | `backend/tests/test_whatsapp_api.py` | Asserts requests with invalid or missing `X-Hub-Signature-256` return HTTP 403. |
| **Durable Opt-Out (STOP/START)** | `backend/tests/test_whatsapp_api.py` | Asserts `STOP` persists `opted_out` status and blocks subsequent turn processing until `START`. |
| **Conversation Reset (RESET)** | `backend/tests/test_whatsapp_api.py` | Asserts `RESET` clears turn context from session cache. |
| **Internal Orchestrator Resolution** | `backend/tests/test_whatsapp_api.py` | Asserts worker resolves phone hash to authenticated `user_id` without external HTTP calls. |
| **Delivery vs Acceptance** | `backend/tests/test_whatsapp_api.py` | Asserts status callback `delivered` is distinctly processed from outbound send acceptance. |
| **24-Hour Window Expiry** | `backend/tests/test_whatsapp_api.py` | Asserts error 131047 is caught and handled gracefully without retry loops. |

---

## 5. Security & Safety Invariants

- **No Secrets in Client Storage or Chat:** Meta App Secrets, System User Tokens, and encryption keys must never be committed, exposed in client bundles, or printed in logs.
- **Zero Ingestion of User Chats:** Inbound WhatsApp messages must never be fed into LLM fine-tuning or teacher corpus indexing.
- **Fail-Closed on Unauthenticated Links:** Forwarded linking URLs or link previews (GET requests) must never bind an account.
- **No Physical Phone Disconnection:** No registration or API call may be made that triggers deregistration of the physical SIM.

---

## 6. Implementation Log & Completed Changes (2026-11-22)

### 1. Frontend Account Linking & Profile UI
- **`src/pages/LinkWhatsAppPage.tsx`**:
  - Fixed consent default defect: `initialSyncConsent` and `initialMemoryConsent` are now defaulted to `false` (unchecked) ensuring full DPDP compliance.
  - Implemented URL token sanitization: immediately strips `#code=...` or `?code=...` from the browser address bar upon extraction using `window.history.replaceState`.
  - Added dedicated service unavailability state (`isUnavailable`) with a clear error card and a "Retry Connection" button.
- **`src/components/profile/settings/WhatsAppCard.tsx`**:
  - Added service unavailability handling with inline alert and retry button.
  - Preserved decoupled switches for Chat History Sync and Spiritual Journey Memory.
- **`src/test/whatsappIntegration.test.tsx`**:
  - Updated tests to verify that DPDP consent switches default to `false` (unchecked).
  - Added test verifying service failure displays the temporary unavailability banner with retry action.
  - 5/5 Vitest tests passing.

### 2. Backend Orchestration & Teaching Delivery
- **`backend/tasks/whatsapp_tasks.py`**:
  - Modernized Meta Graph API to configurable version defaulting to `v21.0` (upgraded from deprecated `v18.0`).
  - Replaced unauthenticated HTTP `POST /api/chat` calls with in-process `PipelineCoordinator` execution passing authenticated `effective_user={"id": user_id, "is_anonymous": False}` and `incognito=not memory_write`.
  - Added `_split_whatsapp_message(text, max_chars=4000)`: splits long teacher discourses along paragraph boundaries so teachings and citations are never cut off.
  - Added `_send_meta_interactive`: supports sending native Meta interactive button messages.
  - Accurately logs carrier acceptance with outbound message ID (`messages[0].id`), distinguishing API acceptance from device delivery status.
- **`backend/services/whatsapp_service.py`**:
  - Added `optout_account_by_phone(supabase, phone)`: persists `status = 'opted_out'` in database on `STOP`.
  - Added `resume_account_by_phone(supabase, phone)`: restores `status = 'active'` on `START`.
  - Added `pause_whatsapp_ai(phone_hash, duration_seconds=3600)`, `is_whatsapp_ai_paused(phone_hash)`, and `resume_whatsapp_ai(phone_hash)` for coexistence human handoff.
  - Added `clear_whatsapp_session(phone_hash)` to purge conversation context in Redis on `RESET`.
  - Added `build_meta_interactive_buttons(to_number, body_text, buttons, header_text, footer_text)` for native Meta Cloud API quick reply buttons.
- **`backend/app/api/whatsapp.py`**:
  - Enforced `phone_number_id` validation against `configured_phone_id` to block cross-account injections.
  - Added native support for interactive button and list replies (`type == "interactive"`).
  - Wired real persistence for `STOP` (database `opted_out` + Redis session clear) and `RESET` (Redis purge).
  - Implemented human coexistence handoff on `HUMAN`, `SUPPORT`, `AGENT`, `btn_human`: pauses AI for 60 minutes and resumes on `RESUME`.
  - Added interactive quick-menu on `MENU`, `OPTIONS`, `START`, and `CONFIRM`.
  - In `POST /api/whatsapp/link/unlink`: purges active session from Redis before unlinking.
- **`backend/tests/test_whatsapp_api.py`**:
  - Added comprehensive test coverage for message splitting, interactive buttons, AI pause/resume, database optout/resume, human handoff, interactive inbound replies, and mismatched phone ID rejection.
  - 25/25 pytest tests verified.

### 3. Documentation & Operational Runbooks
- **`docs/whatsapp/META_COEXISTENCE_ONBOARDING_GUIDE.md`**:
  - Documented the owner's single mobile WhatsApp Business app status and the strict prohibition of manual Cloud API registration commands that could wipe the mobile app.
  - Detailed the two safe paths: Path A (Embedded Signup v4 via Tech Provider) vs Path B (Dedicated Companion Number).
  - Documented the 60-minute Human Coexistence Handoff and native interactive button capabilities.

## Follow-up verification and corrected setup guidance

The implementation log above records earlier work, not live Meta acceptance. This pass reused `useWhatsAppConnection` and `whatsappConnection` for linking/Profile state: optional choices start off; challenge storage expires at 15 minutes; sign-in return URLs contain no challenge; private codes are not rendered; external return URLs must identify a specific `https://wa.me` number; status and mutations are validated; stale-account responses and duplicate changes are denied.

Validation rerun: `bunx vitest run src/test/whatsappIntegration.test.tsx src/test/whatsappConnection.test.ts src/test/useWhatsAppConnection.test.ts` — 23 tests passed. Public browser flow at 384×681 and 1280×1800 checked private-link stripping, no horizontal overflow, clean sign-in return and no page errors. Preview build log is green. Tooling emitted the existing Vite SWC recommendation; this is not zero-warning release evidence.

Corrected coexistence guide removes the unapproved separate-number recommendation and ordinary Add Number instructions, uses the `messages` callback field, and marks menus/handoff as unverified live behavior. Owner has only the Business phone app: Meta Developer setup, eligible coexistence and actual AI-use classification must precede activation. A separate number or narrow domain does not waive India's general-purpose-assistant restrictions.

Still open: fresh two-channel proof against forwarded links; durable inbound/outbound acceptance, callback persistence and restart recovery; full trusted-context and revoke-race verification; authorized hosted persistence checks; configured human operator; live Meta incoming/reply/delivered/readback/unlink. Authenticated browser checks are unavailable on external unmanaged Supabase. No Meta credential change, number migration, message send, production schema change or deployment occurred in this pass. Existing backend log claims must be independently verified in the locked test image and live receiver before public readiness.

