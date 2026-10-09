# AskMukthiGuru WhatsApp Bot Setup & Operations Guide
========================================================

**Document:** `docs/WHATSAPP_SETUP_GUIDE.md`  
**Audience:** Harsha & AskMukthiGuru Engineering Team  
**Service:** `whatsapp_bot/wa_bot.py`  
**Status:** Production Ready  

---

## 1. Executive Summary & Architecture

The AskMukthiGuru WhatsApp Bot enables seekers to converse directly with Mukthi Guru over WhatsApp without needing to access the website. It provides the same grounded spiritual wisdom, guided meditation sequences, and crisis safety preemption as the web platform.

```
WhatsApp Seeker (Phone)
       │
       ▼ Inbound Webhook (<15s deadline)
[ whatsapp_bot/wa_bot.py ]
   ├── 1. Fail-closed signature verification (Twilio HMAC-SHA1 or Meta HMAC-SHA256)
   ├── 2. Normalized session isolation: `wa-<phone_number>`
   ├── 3. SQLite persistence: `wa_messages` and `wa_state`
   ├── 4. Immediate HTTP 200 / empty TwiML acknowledgment (<15s)
   │
   ▼ Background Worker Thread
[ Backend /api/chat & Job Queue ]
   ├── Mints short-lived HS256 JWT (sub: `wa-<phone_number>`)
   ├── Dispatches chat turn (or polls /api/jobs/{id} when queued)
   ├── Renders grounded wisdom & retains meditation state
   │
   ▼ Outbound Dispatch via REST API
[ Provider Delivery ]
   ├── Twilio: REST Client (POST /2010-04-01/Accounts/{SID}/Messages.json)
   └── Meta: Graph API (POST https://graph.facebook.com/v18.0/{id}/messages)
       │
       ▼
WhatsApp Seeker (Receives formatted answer + clickable links + crisis helplines)
```

### Key Architectural Invariants
1. **Immediate Webhook Acknowledgment (<15s):** WhatsApp providers (both Twilio and Meta) retry or drop webhooks if not answered within 15 seconds. The bot immediately returns an acknowledgment (empty TwiML or HTTP 200) and executes conversational inference in a background thread, pushing the final answer via the provider's outbound REST API.
2. **Fail-Closed Cryptography:** Requests lacking valid `X-Twilio-Signature` or `X-Hub-Signature-256` headers (or when provider secrets are missing) are immediately rejected with HTTP 403 Forbidden.
3. **Session & Auth Isolation:** Every phone number maps to session `wa-<phone_number>` and mints an HS256 JWT accepted by the backend's `LocalAuthStrategy`.
4. **Clinical Crisis Preservation:** Helplines including Tele-MANAS (`14416`) and Emergency (`112`) are preserved without truncation, markdown distortion, or removal.
5. **Clean Clickable URLs:** Markdown links `[Title](https://...)` convert cleanly to `Title (https://...)`, allowing WhatsApp to render them as interactive links.

---

## 2. Option A: Twilio Sandbox Setup (2-Minute Instant Test)

Twilio's WhatsApp Sandbox allows immediate end-to-end testing from your personal phone without waiting for WhatsApp Business verification.

### Step 1: Open Twilio Sandbox Console
1. Log into your [Twilio Console](https://console.twilio.com/).
2. Navigate to **Messaging** $\to$ **Try it out** $\to$ **Send a WhatsApp message**.
3. You will see a sandbox number (typically `+1 415 523 8886`) and a join code (e.g., `join desert-flower`).

### Step 2: Join the Sandbox on Your Phone
1. Open WhatsApp on your mobile device.
2. Send the message `join <your-code>` to `+1 415 523 8886`.
3. You will receive an instant reply confirming connection to the sandbox.

### Step 3: Expose Local Bot or Deploy
If testing locally with ngrok:
```bash
# Terminal 1: Run the WhatsApp bridge
cd whatsapp_bot
python wa_bot.py  # listens on port 8080

# Terminal 2: Expose via ngrok
ngrok http 8080
# Output URL: https://abc123xyz.ngrok-free.app
```

### Step 4: Configure Webhook in Twilio Console
1. In Twilio Console: **Messaging** $\to$ **Settings** $\to$ **WhatsApp sandbox settings**.
2. Under **"WHEN A MESSAGE COMES IN"**:
   - URL: `https://<your-domain-or-ngrok>/twilio/whatsapp` (or `/whatsapp/twilio`)
   - HTTP Method: `POST`
3. Click **Save**.

### Step 5: Environment Variables for Twilio
In your `.env` file (or container environment):
```env
ASKMUKTHIGURU_API_URL=https://api.askmukthiguru.com  # or http://localhost:8000
JWT_SECRET=your_backend_jwt_secret_here             # must match backend/.env

TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TWILIO_AUTH_TOKEN=your_auth_token_from_twilio_dashboard
TWILIO_FROM=whatsapp:+14155238886

WA_ASYNC_ACK=true
WA_DB_PATH=/data/wa_state.db
```

---

## 3. Option B: Meta WhatsApp Cloud API Setup (Production)

For official AskMukthiGuru production deployment with a branded WhatsApp Business profile and high message throughput.

### Step 1: Create Meta Developer App
1. Go to [developers.facebook.com](https://developers.facebook.com/).
2. Click **My Apps** $\to$ **Create App**.
3. Select **Other** $\to$ App Type: **Business**.
4. Enter App Name: `AskMukthiGuru`.

### Step 2: Add WhatsApp Product
1. Under **Add products to your app**, locate **WhatsApp** and click **Set up**.
2. Select your Meta Business Account (or let Meta create a default test account).
3. Under **API Setup**:
   - You will find your **Phone Number ID** (e.g., `105938472910294`).
   - You will find your **WhatsApp Business Account ID**.

### Step 3: Configure Webhook
1. In the sidebar, navigate to **WhatsApp** $\to$ **Configuration**.
2. Next to **Webhook**, click **Edit**:
   - **Callback URL:** `https://your-domain.com/whatsapp/meta` (must be HTTPS)
   - **Verify Token:** Set any secure random string (e.g. `mukthi_guru_webhook_verify_2026`)
3. Click **Verify and Save**. (The bot handles the GET challenge verification automatically).
4. Under **Webhook fields**, click **Manage** and subscribe to `messages`.

### Step 4: Generate Permanent System User Access Token
1. In [business.facebook.com](https://business.facebook.com/) $\to$ **Business Settings** $\to$ **Users** $\to$ **System Users**.
2. Create a System User: `MukthiGuruBot` (Admin role).
3. Click **Generate New Token**:
   - Select your App (`AskMukthiGuru`).
   - Token Expiration: **Never**.
   - Permissions: check `whatsapp_business_messaging` and `whatsapp_business_management`.
4. Copy the resulting token (`EAA...`).

### Step 5: Environment Variables for Meta
```env
ASKMUKTHIGURU_API_URL=https://api.askmukthiguru.com
JWT_SECRET=your_backend_jwt_secret_here

# Meta Cloud API
META_APP_SECRET=your_meta_app_secret_from_app_dashboard
META_VERIFY_TOKEN=mukthi_guru_webhook_verify_2026
META_ACCESS_TOKEN=EAABxxxxxxxxxxxxxxxxxxxxxxx
META_PHONE_NUMBER_ID=105938472910294

WA_ASYNC_ACK=true
WA_DB_PATH=/data/wa_state.db
```

---

## 4. Environment Variables Reference

| Variable | Provider | Required | Description | Example |
|---|---|---|---|---|
| `ASKMUKTHIGURU_API_URL` | Both | **Yes** | URL of AskMukthiGuru backend | `http://backend:8000` |
| `JWT_SECRET` | Both | **Yes** | Shared secret matching `backend/.env:JWT_SECRET` | `secret_xyz` |
| `TWILIO_ACCOUNT_SID` | Twilio | Yes (if Twilio) | Twilio Account SID | `ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx` |
| `TWILIO_AUTH_TOKEN` | Twilio | Yes (if Twilio) | Twilio Auth Token (used for signature validation & REST) | `1a2b3c4d5e...` |
| `TWILIO_FROM` | Twilio | Yes (if Twilio) | Twilio WhatsApp sender number | `whatsapp:+14155238886` |
| `META_APP_SECRET` | Meta | Yes (if Meta) | Meta App Secret (used for HMAC-SHA256 signature validation) | `abcdef0123456789...` |
| `META_VERIFY_TOKEN` | Meta | Yes (if Meta) | Custom string used during webhook setup challenge | `mukthi_verify_token_2026` |
| `META_ACCESS_TOKEN` | Meta | Yes (if Meta) | Meta System User Graph API access token | `EAAxxxxxxxx...` |
| `META_PHONE_NUMBER_ID` | Meta | Yes (if Meta) | Default Phone Number ID from WhatsApp API Setup | `105938472910294` |
| `WA_ASYNC_ACK` | Both | No (default `true`) | Immediately acknowledge webhook (<15s) and send via outbound API | `true` |
| `WA_DB_PATH` | Both | No | File path for SQLite message & state database | `/data/wa_state.db` |
| `WA_CHAT_TIMEOUT_S` | Both | No (default `60`) | Polling/connection timeout in seconds | `60` |
| `WA_HISTORY_LIMIT` | Both | No (default `10`) | Turns of past conversation included per prompt | `10` |
| `PORT` | Both | No (default `8080`) | HTTP listen port | `8080` |

---

## 5. Deployment with Docker & Docker Compose

### Option 1: Docker Compose (Integrated Production Stack)
The `whatsapp-bot` service is defined directly in `docker-compose.prod.yml`:

```bash
# Deploy with Docker Compose
docker compose -f docker-compose.prod.yml up -d whatsapp-bot
```

### Option 2: Standalone Docker Container
```bash
docker run -d \
  --name mukthiguru-whatsapp-bot \
  -p 8085:8080 \
  -v /var/data/whatsapp:/data \
  -e ASKMUKTHIGURU_API_URL="http://localhost:8000" \
  -e JWT_SECRET="your_matching_jwt_secret" \
  -e TWILIO_ACCOUNT_SID="ACxxx" \
  -e TWILIO_AUTH_TOKEN="your_token" \
  -e TWILIO_FROM="whatsapp:+14155238886" \
  -e WA_DB_PATH="/data/wa_state.db" \
  -e WA_ASYNC_ACK="true" \
  --restart always \
  ghcr.io/your-org/askmukthiguru-whatsapp-bot:latest
```

---

## 6. Frontend "Chat on WhatsApp" Action

The web application exposes seamless entry points so seekers can transition from browser to WhatsApp:

1. **Header Action Button (`ChatHeader.tsx`):**
   - Visible on all viewports (desktop, tablet, and mobile).
   - Features the official WhatsApp icon styled in `#25D366` hover theme.
   - Links directly to: `https://wa.me/${VITE_WHATSAPP_NUMBER || ''}?text=Namaste%20Mukthi%20Guru`.
2. **Empty State Banner (`ChatEmptyState.tsx`):**
   - Beautiful card displayed when starting a conversation: *"Connect with Mukthi Guru on WhatsApp — Ask questions & receive daily wisdom directly on your phone"*.
3. **Configuration:**
   - Set in frontend environment: `VITE_WHATSAPP_NUMBER=14155238886` (country code without `+` or spaces).

---

## 7. Clinical Crisis Safety Preservation

WhatsApp is an essential lifeline for seekers in crisis. The bridge service guarantees:
- **Zero Truncation of Helplines:** Tele-MANAS (`14416`) and Emergency (`112`) are preserved intact.
- **Smart Chunking:** If a response exceeds WhatsApp's 4,096-character limit, `_chunk_text` divides messages along paragraph and sentence boundaries so helpline directives are never cut in half.
- **Fail-Open Safe Fallbacks:** If the backend encounters a timeout, connection interruption, or 500 error, warm supportive spiritual fallback messages are returned rather than cryptic error traces.

---

## 8. Verification & Diagnostics

### Liveness Probe
```bash
curl http://localhost:8080/healthz
# {"status":"ok","db":"/data/wa_state.db"}
```

### Readiness & Diagnostics Probe
```bash
curl http://localhost:8080/health
# {
#   "status": "ok",
#   "ready": true,
#   "backend_ready": true,
#   "db_ready": true,
#   "twilio_configured": true,
#   "meta_configured": false
# }
```

### Verify Signature Rejection (Security Gate)
```bash
# Sending unauthorized webhook without signature must return 403 Forbidden
curl -i -X POST http://localhost:8080/whatsapp/twilio \
  -d "From=whatsapp:+919876543210&Body=Hello"
# HTTP/1.1 403 FORBIDDEN
```

### Run Python Regression Tests
```bash
backend/.venv/bin/pytest backend/tests/test_whatsapp_bot_integration.py -v
```
