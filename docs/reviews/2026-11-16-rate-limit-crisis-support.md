# Crisis-support lines on rate-limit and quota refusals (2026-11-16)

Written by an AI agent. Not yet clinician-reviewed. It decides nothing.

## What happened

In the registered run of 2026-11-15 the Tamil probe meaning "I want to die" was refused
with HTTP 429 and an empty body: the request limiter runs before any crisis check, so a
person who is rate-limited or over the anonymous message allowance was shown no helpline.

## What changed for the seeker

Every 429 refusal on the chat surface (`/api/chat*`, `/api/auth/anon-session`,
`/api/first-person*`) now carries one extra field, `crisis_support`, holding the
phone-verified helpline block from `config/helplines.yaml` (the same accessor the static
crisis replies use, `format_helplines_block(verified_only=True)`).

Text shown as of this change (public information):

```
🆘 If you're in immediate crisis, please reach out:
- India | Tele-MANAS (National Mental Health Helpline): 14416 / 1800-891-4416
- India | National Emergency Services: 112
If you are outside India, call your local emergency number now.
```

The "Get help now" button is already shown in the chat header on every screen, including
after a refusal.

Verified live on 2026-11-16: the anonymous-quota refusal at message 6 kept its status,
`Retry-After` and every existing field, and added the block above.

## Deliberately not changed

- No crisis classification before or around the limiter.
- No request is exempted from any limit; the refusal stays a refusal (no model call).
- No crisis routing, distress levels or safety-kernel text.
- The refusal message itself ("Free-message limit reached" / "Please try again shortly")
  does not yet render the lines inline in the chat bubble; the header button does.

## Reviewer decision

| reviewer | date | decision (approve / change / reject) | notes |
|---|---|---|---|
| | | | |
