# WhatsApp Bot — Reference Implementation

Production-ready single-file Flask bridge: Twilio WhatsApp ↔ `/api/chat`.

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
# Edit .env — set ASKMUKTHIGURU_API_URL, JWT_SECRET (must match backend), TWILIO_AUTH_TOKEN

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
    │
    ▼ POST (Twilio webhook)
[ wa_bot.py /twilio/whatsapp ]
    │ 1. validate X-Twilio-Signature              ─── reject if forged
    │ 2. read SQLite: last 10 turns + state        ─── per-phone history
    │ 3. mint HS256 JWT (sub=wa-<phone>)           ─── matches backend JWT_SECRET
    │ 4. POST /api/chat                            ─── 60s timeout
    │ 5. md_to_wa() + append citations             ─── WhatsApp formatting
    │ 6. INSERT messages, UPDATE wa_state          ─── persist for next turn
    │ 7. return TwiML <Message>…</Message>         ─── synchronous reply
    ▼
WhatsApp user
```

## Critical config

| Env var | Required | Notes |
|---|---|---|
| `ASKMUKTHIGURU_API_URL` | yes | e.g. `https://api.askmukthiguru.com` (no trailing slash) |
| `JWT_SECRET` | yes | **Must exactly match** `backend/.env:JWT_SECRET`. Otherwise every request 401s. |
| `TWILIO_AUTH_TOKEN` | yes | Twilio console → Account → Auth Token. Used to validate webhook signatures. |
| `TWILIO_FROM` | yes | `whatsapp:+14155238886` for sandbox; your WA number for prod |
| `WA_DB_PATH` | no | Default `./wa_state.db`. Use a persistent volume in production. |
| `WA_CHAT_TIMEOUT_S` | no | Default `60`. Twilio retries webhooks after 15s with no response — see "Long requests" below. |

## Long-request handling (>10s)

Twilio considers a webhook delivered when you return 200. If your backend takes
20s to respond, Twilio will re-send the webhook at 15s thinking it failed.

**Two production-grade patterns** (not implemented in this reference — pick one):

### Pattern A — Background worker
```python
@app.post("/twilio/whatsapp")
def incoming():
    # ... validate, persist user message ...
    rq.enqueue(_handle_async, phone, body)   # Redis-Queue, Celery, or BackgroundTasks
    return _twiml("")                         # empty TwiML — Twilio is happy
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
[ ] JWT_SECRET in this bot's env exactly matches backend/.env JWT_SECRET
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

## What this code does NOT do

- Async queue (see "Long-request handling" above)
- Multi-tenant isolation
- Voice notes / media messages (text only)
- Webhook idempotency (Twilio's signature includes a request id, but
  this code re-processes duplicates — fine for the spiritual-Q&A use
  case, but if you build a transactional bot, dedupe on `MessageSid`)
- Group chat handling (assumes 1-on-1 conversations)

Each of these is a half-day to add — but YAGNI for a first launch.
