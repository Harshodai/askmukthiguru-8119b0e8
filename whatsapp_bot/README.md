# WhatsApp Bot — Reference Implementation

Production-ready single-file Flask bridge: WhatsApp (Twilio + Meta Cloud API)
↔ `/api/chat` (async 202 + job poll, per-phone signed anonymous sessions).

## What you get

- `wa_bot.py` — the service (~200 lines, single file, no framework magic)
- `requirements.txt` — flask, requests, twilio, pyjwt
- `.env.example` — every config knob, all required values explained
- `Dockerfile` — optional, ~10 lines

## 5-minute deploy (Twilio Sandbox + local ngrok)

```bash
# 1. Install
cd whatsapp_bot
pip install -r requirements.txt

# 2. Configure
cp .env.example .env
# Edit .env — set ASKMUKTHIGURU_API_URL, TWILIO_AUTH_TOKEN (or Meta secrets)

# 3. Run
python wa_bot.py    # listens on :8080

# 4. Expose to Twilio (in another terminal)
ngrok http 8080
# Copy the https URL ngrok prints, e.g. https://abc123.ngrok.io

# 5. Configure Twilio sandbox
#    Console → Messaging → Try WhatsApp → Sandbox Settings
#    "When a message comes in" = https://abc123.ngrok.io/twilio/whatsapp
#    Method = POST
#    Save

# 6. Test
#    Send "What is the Beautiful State?" from your phone to the sandbox number
```

## Production deploy (Cloud Run / Railway / Fly.io)

The same `wa_bot.py` runs fine in any container platform. Set the same env vars.
Use the included `Dockerfile`. Webhook URL becomes your service's public URL +
`/twilio/whatsapp`.

## Architecture

```
WhatsApp user
    │ POST (Twilio webhook / Meta Cloud API event)
[ wa_bot.py /whatsapp/twilio | /whatsapp/meta ]
    │ 1. validate signatures (Twilio/Meta)          --- reject if forged
    │ 2. classify inbound: text -> turn; voice /     --- honest decline,
    │    image / file -> decline; receipts -> ignore   never silent
    │ 3. RESET / HELP served locally; per-phone      --- no backend burn
    │    rate limit enforced at the edge
    │ 4. ensure per-phone anon token (POST /api/     --- same quotas +
    │    auth/anon-session, persisted in SQLite)       job ownership as
    │ 5. detect Indic script -> language               anonymous web chat
    │ 6. ack immediately (<15s): empty TwiML / 200   --- L-WA-ASYNC-1
    │ 7. background thread: POST /api/chat -> 202    --- crisis copy,
    │    job_id -> poll /api/jobs -> format            first-person voice
    │ 8. deliver via outbound REST, retry once         preserved verbatim
    ▼
WhatsApp user
```

## Identity and quotas

No JWT_SECRET coupling: on first contact the bot mints a server-signed
anonymous token (POST /api/auth/anon-session), stores it per phone in
`wa_auth`, and echoes it as `session_id` (chat POST) / `X-Session-Id`
(job poll). Backend quotas, job ownership, and crisis preemption therefore
behave exactly as for anonymous web seekers. A `400 Invalid anonymous
session` (rotated server secret) re-issues once and retries.

## Critical config

| Env var | Required | Notes |
|---|---|---|
| `ASKMUKTHIGURU_API_URL` | yes | e.g. `https://api.askmukthiguru.com` (no trailing slash) |
| `JWT_SECRET` | no | Legacy only (`mint_jwt` kept for tooling). Live turns use per-phone anon tokens; no backend JWT is sent. |
| `TWILIO_AUTH_TOKEN` | yes | Twilio console → Account → Auth Token. Used to validate webhook signatures. |
| `TWILIO_FROM` | yes | `whatsapp:+14155238886` for sandbox; your WA number for prod |
| `WA_DB_PATH` | no | Default `./wa_state.db`. Use a persistent volume in production. |
| `WA_CHAT_TIMEOUT_S` | no | Default `60`. Twilio retries webhooks after 15s with no response — see "Long requests" below. |

## Long-request handling (>10s)

Twilio considers a webhook delivered when you return 200. If your backend takes
20s to respond, Twilio will re-send the webhook at 15s thinking it failed.

**Implemented (L-WA-ASYNC-1):** every webhook acks immediately (empty TwiML /
HTTP 200) and inference runs in a background thread with outbound REST
delivery. The patterns below are retained as background reading:

### Pattern A — Background worker
```python
@app.post("/twilio/whatsapp")
def incoming():
    # ... validate, persist user message ...
    rq.enqueue(_handle_async, phone, body)  # Redis-Queue, Celery, or BackgroundTasks
    return _twiml("")  # empty TwiML — Twilio is happy
```

Then in the worker, after calling `/api/chat`, use the Twilio REST API to
push the answer as a separate outbound message:

```python
from twilio.rest import Client

client = Client(account_sid, auth_token)
client.messages.create(from_=TWILIO_FROM, to=phone, body=answer)
```

### Pattern B — Quick acknowledgement
Reply with "Reflecting on your question…" immediately, then send the real
answer as a Twilio REST follow-up when the backend returns.

Trade-off: Pattern A is cleaner; Pattern B is simpler if you don't have a
queue infrastructure yet.

## Persistence

SQLite tables created automatically on first run:
- `wa_messages(phone, role, content, created_at)` — conversation history
- `wa_state(phone, meditation_step, last_serene_at, language)` — per-user state

In containerized deploys, **mount a volume** for `WA_DB_PATH`. Otherwise every
restart wipes meditation state mid-session.

## Security checklist (pre-launch)

```
[ ] No JWT_SECRET needed for live turns (per-phone anon tokens). `mint_jwt` is legacy tooling only
[ ] TWILIO_AUTH_TOKEN set (not the Account SID) so signature validation works
[ ] WA_DB_PATH points to a persistent volume (not /tmp)
[ ] Bot host has correct NTP — JWT clock skew >5min causes 401s
[ ] Production WhatsApp Business number (not the sandbox — sandbox only
    works for users who've opted in via "join <code>")
[ ] Crisis numbers in DISTRESS responses survive the markdown filter
    (run a unit test on md_to_wa with a sample distress response containing
    "Call 1-800-273-TALK")
[ ] PII redaction: do NOT log message bodies with phone in production
[ ] Rate-limit middleware in front of /twilio/whatsapp if you fear abuse
    (Twilio's signature validation already filters non-Twilio traffic)
```

## Testing

Quick smoke without going through Twilio:

```bash
# Generate a JWT
JWT=$(python -c "
import jwt, time, os
print(jwt.encode({'sub':'wa-test','role':'authenticated',
                  'iat':int(time.time()),'exp':int(time.time())+3600,
                  'iss':'askmukthiguru-wa-bot'},
                 os.environ['JWT_SECRET'], algorithm='HS256'))
")

# Hit the backend directly with that JWT
curl -sw "\n%{http_code}\n" -X POST "$ASKMUKTHIGURU_API_URL/api/chat" \
  -H "Authorization: Bearer $JWT" \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [],
    "user_message": "What is the Beautiful State?",
    "session_id": "wa-test",
    "meditation_step": 0,
    "language": "en"
  }' | python -m json.tool
```

If that returns 200 with a real spiritual response, your bot will work.
If it returns 401, the JWT_SECRET mismatch is your problem.

## Failure modes & user-visible fallbacks

The bot returns these specific WhatsApp messages on failure:
- **Timeout / 5xx / 429**: "🙏 I am catching my breath. Please send your message again in a few moments."
- **Other errors**: "🙏 Something went unexpectedly quiet on my end. Could you rephrase or try again?"
- **401 (first attempt)**: silently re-mint JWT and retry once. If second attempt also 401s, treat as generic error.
- **Missing body**: "🙏 I didn't receive any text. Please try again."

These are deliberately warm/non-technical so a confused user doesn't get a
stack trace. Adjust to taste in `wa_bot.py:FALLBACK_DOWN` / `FALLBACK_GENERIC`.

## Local commands and media

- `RESET` (aliases: RESTART, CLEAR, START) wipes local history/state for that
  phone — the WhatsApp equivalent of starting a new chat.
- `HELP` (aliases: MENU, COMMANDS, INFO) describes capabilities and helplines.
- Voice notes, photos, videos, files, and locations get an honest decline
  asking for typed text; receipts/reactions are ignored silently (correct).
- Backend Citation objects (`{url, title}`) render as `Title (url)`, max 3.

## Failure modes & user-visible fallbacks (extended)

- **Anonymous quota 429** → daily-limit copy (no sign-in exists on WhatsApp).
- **Context-exhausted 409** → long-chat copy pointing at RESET.
- **Backend unreachable + crisis phrasing** → failure copy plus the static
  Tele-MANAS 14416 / Emergency 112 footer (numbers match `config/helplines.yaml`,
  enforced by test; KIRAN 1800-599-0019 withdrawn, see RP-C2). Backend
  answers always carry the backend's own reviewed crisis copy verbatim.
- **Per-phone rate limit** (`WA_RATE_LIMIT_COUNT` per `WA_RATE_LIMIT_WINDOW_S`,
  default 10/min) → wait-a-moment copy, no backend call.

## What this code does NOT do

- Multi-tenant isolation
- Voice notes / media messages (text only)
- Webhook idempotency (Twilio's signature includes a request id, but
  this code re-processes duplicates — fine for the spiritual-Q&A use
  case, but if you build a transactional bot, dedupe on `MessageSid`)
- Group chat handling (assumes 1-on-1 conversations)

Each of these is a half-day to add — but YAGNI for a first launch.
