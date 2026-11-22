# Meta WhatsApp Business Coexistence Onboarding & Production Setup Guide

**Author:** AskMukthiGuru Engineering  
**Date:** 2026-11-21  
**Scope:** Running AskMukthiGuru Direct Companion alongside the existing physical WhatsApp Business mobile app on the owner's phone without number migration, deletion, or downtime.

---

## 1. Executive Summary & Coexistence Invariant

AskMukthiGuru provides a direct companion channel over WhatsApp using the official Meta WhatsApp Cloud API.
A critical repository and operational invariant is **Zero Disconnection of the Mobile Phone App**:
> The existing WhatsApp Business app on the physical phone must remain 100% operational for day-to-day manual conversations, voice calls, and customer contacts.

Standard Cloud API registration commands typically deregister a phone number from the physical device. To preserve the phone app, **Meta's official Coexistence Onboarding protocol** must be followed.

---

## 2. Coexistence Eligibility & Technical Prerequisites

Meta officially supports WhatsApp Business App and Cloud API coexistence under specific conditions:
1. **WhatsApp Business App Version**: The physical phone must run WhatsApp Business version **2.24.17 or newer** (iOS or Android).
2. **Meta Business Portfolio Access**: The owner must have **Full Control** over the Meta Business Portfolio that owns the WhatsApp Business Account (WABA).
3. **Onboarding Method**: Coexistence requires onboarding via **Meta Embedded Signup v4** (Session Logging enabled) through an eligible Tech Provider. Direct manual registration via Graph API endpoint `/v21.0/{phone_number_id}/register` or standard console "Add phone number" will deregister the physical SIM and disconnect the phone app.
4. **24-Hour Service Window**: Free-form replies can only be sent within the customer's 24-hour service window (initiated when the seeker messages the business). Template messages are required outside this window.

### 2.1 Reality Check: Owner Setup & The Two Safe Operational Paths

> **Owner Context:** The owner currently operates an active physical WhatsApp Business mobile app on their phone. They do not yet have a Meta Developer App.

To protect the phone app from being disconnected, choose one of these two safe paths:

#### Path A: Official Meta Coexistence (Embedded Signup v4 via Tech Provider)
- Requires onboarding through an authorized Meta Business Solution Partner / Tech Provider implementing Embedded Signup v4 with Session Logging.
- The phone app displays the coexistence banner: *"This number is connected to an automated cloud service."*
- Incoming messages are delivered to both the physical phone app and the AskMukthiGuru webhook simultaneously.

#### Path B: Dedicated AI Companion Number (Recommended for Independent Setup)
- Keep the existing WhatsApp Business phone number exclusively on the physical phone for personal/business interactions.
- Provision a separate dedicated business number (virtual number or secondary SIM) specifically for the AskMukthiGuru AI Companion.
- Zero risk to the primary number, zero dependency on third-party Tech Provider approvals, and 100% clean channel separation.

---

## 3. Human Coexistence Handoff & Bank-Style Interactive Menu

To ensure manual phone replies and AI automation never compete or collide:

### Human Handoff (The 60-Minute AI Pause)
- When a user texts `HUMAN`, `SUPPORT`, `AGENT`, or clicks the native **Human Help** button:
  1. AskMukthiGuru immediately pauses automated AI responses for **60 minutes** via Redis key `wa:pause:{phone_hash}`.
  2. The seeker receives: *"🤝 Connecting you to a Guide / Team Member. Automated AI responses are paused for the next 60 minutes..."*
  3. The owner can reply directly from their WhatsApp Business mobile app without AI bot interruption.
  4. The seeker can text `RESUME` at any time to resume AI guidance immediately.

### Native Interactive Buttons (Meta Cloud API)
- Upon connecting or texting `MENU`, AskMukthiGuru serves interactive quick-reply buttons:
  - **Ask a Question**: Prompts user for spiritual inquiries.
  - **Today's Practice**: Delivers the authentic 3-minute Soul Sync meditation practice.
  - **Human Help**: Activates the 60-minute human coexistence handoff.

---

## 4. Step-by-Step Meta Business Portal Setup

### Step 1: Meta Developer App Configuration
1. Log in to [Meta for Developers](https://developers.facebook.com/) with the Business Portfolio admin account.
2. Select your existing app (or create a **Business** type app named `AskMukthiGuru`).
3. Under **Add products to your app**, select **WhatsApp** and click **Set up**.
4. Link the app to your verified Meta Business Portfolio.

### Step 2: Webhook Registration
1. In the left navigation, navigate to **WhatsApp** $\rightarrow$ **Configuration**.
2. Under **Webhook**, click **Edit**:
   - **Callback URL**:  
     `https://askmukthiguru-8119b0e8-production.up.railway.app/api/whatsapp/webhook`
   - **Verify Token**:  
     A secure random string (must match `WHATSAPP_VERIFY_TOKEN` in Railway, e.g. generate via `openssl rand -hex 24`).
3. Click **Verify and Save**. Meta will issue a GET request with `hub.mode=subscribe` and `hub.verify_token`.
4. Click **Manage** under Webhook fields, and subscribe to:
   - `messages` (Inbound user messages)
   - `message_deliveries` (Delivery status receipts)
   - `message_reads` (Read receipts)

### Step 3: Coexistence Embedded Signup Flow
1. In **WhatsApp** $\rightarrow$ **Quickstart** or **API Setup**, navigate to **Phone Numbers**.
2. Select **Add Phone Number**.
3. When prompted to connect your existing WhatsApp Business number, choose **Use Existing Number (Coexistence)**.
4. Verify the 6-digit SMS/voice challenge sent to your phone.
5. **CRITICAL**: Confirm that the mobile app displays the coexistence banner: *"This number is connected to an automated cloud service."* Do not click "Migrate to Cloud API only".

### Step 4: System User & Permanent Token Generation
1. In [Meta Business Suite](https://business.facebook.com/) $\rightarrow$ **Business Settings** $\rightarrow$ **Users** $\rightarrow$ **System Users**.
2. Create an Admin System User named `askmukthiguru-cloud-worker`.
3. Under **Assigned Assets**, assign the WhatsApp Account with Full Control.
4. Click **Generate New Token**:
   - Select expiration: **Never** (Permanent token).
   - Select permissions:
     - `whatsapp_business_messaging`
     - `whatsapp_business_management`
5. Copy the generated token securely.

---

## 4. Railway Production Environment Variables Checklist

Set the following variables in the Railway production environment (`e0e120ff-3eca-4a3c-8c4d-7a6b71df7feb`):

| Variable Name | Description | Example / Source |
| :--- | :--- | :--- |
| `META_ACCESS_TOKEN` | Permanent System User token | `EAA...` (From Meta Business Manager) |
| `META_PHONE_NUMBER_ID` | Numeric phone number ID assigned by Meta | `109283746501928` (From WhatsApp API Setup tab) |
| `META_APP_SECRET` | App Secret for incoming HMAC-SHA256 signature verification | Found in **App Settings** $\rightarrow$ **Basic** in Meta Developers |
| `WHATSAPP_VERIFY_TOKEN` | Random string for webhook GET challenge | Shared secret entered in Step 2 |
| `WHATSAPP_LINK_BASE_URL` | Base URL for account linking page | `https://askmukthiguru.com` (or `https://askmukthiguru.lovable.app`) |

---

## 5. End-to-End Operational Lifecycle & Failure Modes

```
                                  [Inbound WhatsApp Message]
                                              │
                                              ▼
                             [Meta Cloud API Webhook (POST)]
                                              │
                      ┌───────────────────────┴───────────────────────┐
                      ▼                                               ▼
         [X-Hub-Signature-256 Valid?]                   [Message wamid in Cache?]
                      │                                               │
               No ───►│ (HTTP 403)                             Yes ──►│ (HTTP 200, Skip)
                      ▼                                               ▼
           [Is STOP/RESET/HELP/LINK?] ──────── Yes ───► [Immediate Action & Direct Reply]
                      │
                      ▼ No
           [Is Acute Distress/Crisis?] ──────── Yes ──► [Immediate Tele-MANAS 14416 Preemption]
                      │
                      ▼ No
       [Enqueue Celery process_whatsapp_turn_task] ───► [HTTP 200 Acknowledged to Meta (<1s)]
                      │
                      ▼
            [Celery Background Worker]
                      │
         ┌────────────┴────────────┐
         ▼                         ▼
 [Check Linked User]     [Orchestrator /api/chat]
         │                         │
         │                         ▼
         │               [Verbatim Quote with Video Link]
         │                         │
         │                         ▼
         │               [Send Outbound via Meta API]
         │                         │
         └────────────┬────────────┘
                      ▼
         [Sync Chat History (if opted-in)]
         [Write Second-Brain Memory (if opted-in)]
```

### Safety & Invariant Protections
1. **SSRF Guard**: Meta Graph API calls are strictly restricted to `graph.facebook.com` over HTTPS.
2. **Crisis Preemption**: Keywords indicating suicide or acute self-harm trigger immediate Tele-MANAS `14416` and `112` helplines, completely bypassing generative and retrieval lanes.
3. **DPDP Separation**: History sync and spiritual second-brain memory writing are separate consent switches. An unlinked user or linked user without consent receives answers without their questions being saved to their website profile.
4. **Rate Limiting & Deduplication**: All webhook events maintain a rolling 1,000-message `wamid` deduplication filter.
