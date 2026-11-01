# Integrations: WhatsApp Cloud API & Webhooks

AskMukthiGuru provides a production-hardened WhatsApp gateway connecting seekers directly to the spiritual wisdom of Sri Preethaji & Sri Krishnaji. Implemented via `whatsapp_bot/wa_bot.py` and backend API endpoints, the bridge supports both Twilio Messaging and native Meta WhatsApp Cloud API protocols with enterprise-grade signature validation, asynchronous turn delivery, and crisis routing.

---

## 1. System Architecture & Request Lifecycle

Because WhatsApp webhook providers (Twilio and Meta) mandate immediate HTTP 200 acknowledgments within 15 seconds, long RAG inference passes cannot run synchronously within the webhook handler. AskMukthiGuru implements the **L-WA-ASYNC-1** decoupled queue architecture:

```text
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                             WHATSAPP INTEGRATION ARCHITECTURE                                     │
├──────────────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                                  │
│   WhatsApp Seeker ────► [Meta Cloud API / Twilio Webhook]                                        │
│                                    │                                                             │
│                                    ▼ POST /whatsapp/meta or /twilio/whatsapp                     │
│                        ┌───────────────────────┐                                                 │
│                        │       wa_bot.py       │ ── 1. Validate X-Hub-Signature-256 (Meta)       │
│                        │     (Edge Gateway)    │ ── 2. Deduplicate message ID in SQLite          │
│                        └───────────────────────┘ ── 3. Return HTTP 200 / Empty TwiML (<500ms)    │
│                                    │                                                             │
│                                    ▼ Background Thread (Worker Pool)                             │
│                        ┌───────────────────────┐                                                 │
│                        │   POST /api/chat      │ ── 4. Mint anonymous session token              │
│                        │   (Returns HTTP 202)  │    (Per-phone signed token, isolated)           │
│                        └───────────────────────┘                                                 │
│                                    │                                                             │
│                                    ▼ Poll /api/jobs/{job_id}                                     │
│                        ┌───────────────────────┐                                                 │
│                        │   LangGraph Engine    │ ── 5. Intent routing & retrieval                │
│                        │   (12-Stage RAG)      │ ── 6. Formulate chunked WhatsApp text           │
│                        └───────────────────────┘                                                 │
│                                    │                                                             │
│                                    ▼ Outbound REST Delivery                                      │
│   WhatsApp Seeker ◄──── [Meta Cloud API / Twilio REST]                                           │
│                                                                                                  │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Webhook Verification & HMAC SHA-256 Security

The gateway enforces multi-layer cryptographic authentication to prevent forged webhooks and replay attacks.

### 2.1 Meta GET Handshake (Webhook Verification)
When registering a new webhook endpoint in the Meta Developer Portal, Meta sends a GET request with verification tokens:
```python
@app.route("/whatsapp/meta", methods=["GET"])
@app.route("/meta/whatsapp", methods=["GET"])
def meta_webhook_verify():
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")

    if mode == "subscribe" and token == os.getenv("META_VERIFY_TOKEN"):
        return challenge, 200
    return "Verification token mismatch", 403
```

### 2.2 Inbound Payload Authentication (`X-Hub-Signature-256`)
Every inbound POST request from Meta contains the `X-Hub-Signature-256` header. The payload is validated using HMAC SHA-256 with the application secret:
```python
def validate_meta_signature(req: Request) -> bool:
    app_secret = os.getenv("META_APP_SECRET", "").strip()
    if not app_secret:
        return True  # Bypass in local non-production environments

    header_sig = req.headers.get("X-Hub-Signature-256", "")
    if not header_sig.startswith("sha256="):
        return False

    expected_sig = "sha256=" + hmac.new(
        key=app_secret.encode("utf-8"),
        msg=req.get_data(),
        digestmod=hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(header_sig, expected_sig)
```

---

## 3. Dual-Mode Seeker Interactions

AskMukthiGuru on WhatsApp supports two primary conversational interaction modalities:

```text
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                              DUAL-MODE CONVERSATIONAL MODES                                      │
├────────────────────────────────────────┬─────────────────────────────────────────────────────────┤
│    MODE 1: FREE-FORM SPIRITUAL INQUIRY │    MODE 2: SACRED SADHANA CHECK-INS                     │
├────────────────────────────────────────┼─────────────────────────────────────────────────────────┤
│ • Interactive Q&A on spiritual topics  │ • Scheduled morning contemplative check-in              │
│ • "What is the Beautiful State?"       │ • Evening reflection & gratitude integration            │
│ • "How do I overcome anxiety?"         │ • Guided multi-step Serene Mind meditation pacing       │
│ • Full citation formatting:            │ • State tracking in SQLite (`meditation_step`,          │
│   "Title (https://youtube.com/...)"    │   `last_serene_at`, `language`)                         │
│ • Indic script detection (hi, te, ta)  │ • Local quick commands: `RESET`, `HELP`, `STOP`         │
└────────────────────────────────────────┴─────────────────────────────────────────────────────────┘
```

### 3.1 Mode 1: Free-Form Spiritual Guidance
1. **Indic Language Detection**: Incoming message text is automatically scanned for Indian Unicode scripts (Devanagari, Telugu, Tamil, Kannada, Bengali). The detected language is stored in seeker state and passed to the backend prompt context.
2. **Citation Normalization**: Rich web citation cards are flattened into clean WhatsApp markdown:
   ```text
   A Beautiful State is an expansive inner state free from fear and division.

   Sources:
   • The Art of Beautiful Living (https://youtu.be/ehkqJ54DIC0?t=120)
   • Ending Emotional Agitation (https://youtu.be/ClbKAXVvzzo?t=45)
   ```

### 3.2 Mode 2: Scheduled Morning & Evening Sadhana Check-Ins
Seekers who opt into daily spiritual practice receive timely, non-intrusive contemplative reminders:
* **Morning Awakening (Prabhat Sadhana)**: A short sacred sutra and 3-minute breath observation invitation.
* **Evening Stillness (Sayam Sadhana)**: An invitation to witness the day's reactions, step out of the *I-centric* mind, and dissolve unconscious friction into the Beautiful State.
* **Serene Mind Interactive Steps**: The bot tracks meditation stages across turns (`meditation_step = 1 .. 4`). When a seeker replies *"ready"*, the bot advances to the next contemplative instruction.

---

## 4. Asynchronous Streaming & Chunked Delivery

WhatsApp messages have a strict upper limit of 4,096 characters per message. To prevent delivery rejections and optimize mobile readability:

### 4.1 Message Chunking Algorithm
The gateway splits long answers into coherent paragraphs, honoring sentence boundaries:
```python
def chunk_text_for_whatsapp(text: str, max_chars: int = 1500) -> list[str]:
    paragraphs = text.split("\n\n")
    chunks = []
    current_chunk = []

    for p in paragraphs:
        if sum(len(x) for x in current_chunk) + len(p) < max_chars:
            current_chunk.append(p)
        else:
            if current_chunk:
                chunks.append("\n\n".join(current_chunk))
            current_chunk = [p]

    if current_chunk:
        chunks.append("\n\n".join(current_chunk))
    return chunks
```

### 4.2 Rate Limiting & Quota Protection
* **Per-Phone Throttling**: Limits users to 10 incoming requests per minute to prevent denial-of-service abuse and backend cost exhaustion.
* **Edge Interception**: Inquiries sent during an active rate-limit window receive an immediate, courteous wait message without touching backend LLM APIs.

---

## 5. WhatsApp Safety Notices & Crisis Routing

When a seeker sends a message indicating severe emotional distress, self-harm, or despair, the gateway bypasses spiritual philosophy and immediately transmits verified emergency crisis contacts.

```text
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                             WHATSAPP CRISIS RESPONSE FORMAT                                      │
├──────────────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                                  │
│   You are not alone. Please reach out to someone who can help right now:                        │
│                                                                                                  │
│   🇮🇳 Tele-MANAS (Govt of India): Call 14416 or 1800-891-4416 (24/7, Toll-Free)                  │
│   🇮🇳 Vandrevala Foundation: Call +91 9999 666 555 (24/7 Crisis Support)                         │
│   🚨 National Emergency: Call 112                                                               │
│                                                                                                  │
│   If you are outside India, please contact your local emergency services or find a              │
│   support line at https://findahelpline.com                                                     │
│                                                                                                  │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘
```

#### WhatsApp-Specific Safety Rules:
1. **Zero Emojis on Crisis Cards**: Emojis are stripped to maintain clinical seriousness, with standard flags used solely for regional identification.
2. **Direct Phone Links**: Contact numbers are formatted with clickable WhatsApp tel-links (`tel:14416`).
3. **No Spiritual Gaslighting**: The bot never suggests that severe psychological pain or suicidal ideation is merely an "illusion of the ego" or a "state of suffering to be witnessed."

---

## 6. Operational Configuration & Deployment

### 6.1 Environment Variables

| Variable | Required | Default | Purpose |
|---|---|---|---|
| `ASKMUKTHIGURU_API_URL` | Yes | - | Backend API URL (e.g. `https://api.askmukthiguru.com`) |
| `META_ACCESS_TOKEN` | Yes* | - | System user access token with `whatsapp_business_messaging` |
| `META_PHONE_NUMBER_ID` | Yes* | - | WhatsApp Business Phone Number ID |
| `META_VERIFY_TOKEN` | Yes* | - | Secret string for Meta webhook challenge handshake |
| `META_APP_SECRET` | Yes* | - | Meta App Secret for HMAC SHA-256 payload verification |
| `TWILIO_AUTH_TOKEN` | No | - | Twilio auth token (if deploying Twilio provider) |
| `TWILIO_FROM` | No | - | Twilio WhatsApp sender number |
| `WA_DB_PATH` | No | `./wa_state.db` | SQLite persistence path for sessions and rate limits |
| `WA_ASYNC_ACK` | No | `true` | Enables immediate HTTP 200 acknowledgment |

*\*Required when using Meta Cloud API.*

### 6.2 Health Probes & Monitoring
* **Liveness Probe**: `GET /healthz` returns `{"status": "ok", "db": "connected"}`.
* **Delivery Status Callbacks**: Meta delivery receipts (`sent`, `delivered`, `read`, `failed`) are logged to SQLite to track message delivery success rates.

---

## 7. Cross-Reference Navigation

* [Architecture: Overview](Architecture-Overview)
* [RAG Execution Pipeline](Architecture-RAG-Pipeline)
* [Serene Mind Distress Triage & Helplines](Domain-Serene-Mind-Safety)
* [Quality Benchmarks & Evaluation](Quality-Evaluation-and-Benchmarks)
* [Troubleshooting Runbooks & Diagnostics](Troubleshooting-and-Runbooks)
