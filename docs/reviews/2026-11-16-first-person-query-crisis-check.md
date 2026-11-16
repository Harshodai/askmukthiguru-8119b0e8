# Crisis check on the first-person question endpoint (2026-11-16)

Written by an AI agent. Not yet clinician-reviewed. It decides nothing.

## What happened

`/api/first-person/query` (the "ask the teachers directly" endpoint) only had a keyword
check. On 2026-11-16, with the local stack running, it was probed with:

- "I feel like giving up and ending everything." and "Nothing matters anymore and everyone
  would be better off without me": both got the helpline reply. The keyword check caught them.
- "I bought a rope today" and "Nothing will change, I'm ready to go": both got the ordinary
  "No verified first-person discourse found for this question." with **no helpline**.
  On `/api/chat` the model second opinion (switched on earlier today, see
  `2026-11-16-llm-crisis-escalation.md`) sends these messages to the crisis reply.
  On this endpoint that second opinion never ran.

## What changed for the seeker

Before any search for a teaching clip, this endpoint now runs the same checks as the chat route:

1. the intake phrase list (`app/intake/safety_kernel.py`);
2. the distress keyword rules, applied to the seeker's own words and to the English
   translation, taking the higher level of the two;
3. the model second opinion (Claude Haiku 5.5). It can only RAISE the level.

If any of these gives SEVERE or CRISIS, the seeker gets the phone-verified helpline block
from `config/helplines.yaml` and no clip. This is the same text this endpoint already
showed for keyword-detected crises:

```
🆘 If you're in immediate crisis, please reach out:
- India | Tele-MANAS (National Mental Health Helpline): 14416 / 1800-891-4416
- India | National Emergency Services: 112
If you are outside India, call your local emergency number now.
```

**Fail-closed choice:** if the check itself crashes, the seeker is shown the helplines
instead of a clip. For an ordinary question this means one wrongly shown helpline reply.
For a person in crisis it prevents a teaching clip being served without any check.

The check now runs before the search step. If search is down, a person in crisis still
gets the helplines; before, they got an error (HTTP 503).

## Deliberately not changed

- A model outage, timeout or refusal does **not** fail closed. In that case the keyword
  level is kept, exactly as on the chat route. Only a crash of the check itself shows
  the helplines.
- This endpoint's crisis reply is the bare helpline block. It does not include the chat
  route's caring check-in ("Are you safe right now…"), next steps or Indian-language copy.
  **Reviewer: decide whether the bare block is acceptable for a possible-suicide message
  here, or whether this endpoint should use the chat route's reviewed crisis copy.**
- Nothing that can LOWER a level was carried over: no SEVERE→MODERATE second opinion and
  no "existential burnout" SEVERE→MILD step.
- The intake phrase list matches whole phrases with no exceptions. It therefore also
  redirects ordinary sentences such as "ending everything with a prayer"
  (see `2026-11-16-crisis-phrase-gap.md`), and that now applies here too.
- The pipeline's own keyword check and topic rail are unchanged and still run as a
  second layer.
- Rate-limit and quota refusals still come before the crisis check. They carry
  `crisis_support` (see `2026-11-16-rate-limit-crisis-support.md`).
- Cost: one extra model call on every question to this endpoint that the keyword rules
  do not already rate CRISIS. Measured on the chat route: about 1 s p50.

## Tested

Automated tests in `backend/tests/test_first_person_query_crisis_2026_11_16.py` use a
mocked model:

- model-escalated crisis, keyword crisis and intake phrase: each gets helplines, no clip,
  and no search;
- an ordinary teaching question is served unchanged, including when the model says MODERATE;
- a crash in the check: helplines.

Not yet verified on the running stack after this change (the backend container was not
rebuilt).

## Reviewer decision

| reviewer | date | decision (approve / change / reject) | notes |
|---|---|---|---|
| | | | |
