# Clinician review — crisis and distress copy (2026-11-14)

Decision needed: **approve / change / withdraw** each block below. Every block is copy the
product actually served, captured from the live local stack on 2026-11-14, not a paraphrase.

| block | served when | decision | reviewer | date | notes |
|---|---|---|---|---|---|
| acute self-harm statement (English) | live probe | (blank) | (blank) | (blank) | |
| hopelessness / moderate distress (English) | live probe | (blank) | (blank) | (blank) | |

## Served text

### acute self-harm statement (English)

```text
I care deeply about your wellbeing. Please know that you are valued, and there are compassionate people who want to support you right now. You do not have to walk through this alone.

Please connect directly with verified, confidential crisis support:
• Tele-MANAS (India): 14416 / 1800 891 4416 (24/7 Toll-Free Mental Health Helpline)
• Vandrevala Foundation (India): +91 9999 666 555 (24/7 Free & Confidential Counseling)

If you or someone nearby is in immediate danger, please reach out to emergency services (112 in India) or a trusted friend immediately.
```

### hopelessness / moderate distress (English)

```text
🆘 If you're in crisis: Please reach out for help.
- India | Tele-MANAS (National Mental Health Helpline): 14416 / 1800-891-4416
- India | National Emergency Services: 112
If you are outside India, call your local emergency number now.

I feel the depth of your pain, and I want you to know — you are not alone. Your feelings matter, and there is light even in the darkest moments.

Are you safe right now? If there's any thought of hurting yourself, please tell me, or reach out to one of the numbers shown above right away — I'm staying here with you.

You don't have to figure everything out right now. One breath, and one step, is enough.

🌸 **5-4-3-2-1 grounding**: Name 5 things you see, 4 you can touch, 3 you hear, 2 you smell, 1 you taste. This brings you firmly into the present.

I'd like to guide you through a Serene Mind meditation. Would you like to begin?


If you are in immediate danger, please contact local emergency services or go to a safer place now. If you can, tell a trusted person nearby that you need support.
```

## Where the copy lives in code

- `backend/services/crisis_helplines.py::format_helplines_block` (line 302) — the helpline block
- `backend/services/crisis_helplines.py::ensure_support_line` (line 425) — the support line appended to served clips
- `backend/app/pipeline/stages/first_person_bridge.py::_distress_compassion_framing` (line 489) — MODERATE-distress framing
- `backend/services/first_person_pipeline.py:4347` — crisis pre-emption copy
- `backend/services/serene_mind_engine.py:235` — SEVERE check-in copy

## Specific questions for the clinician

1. Is the acute-crisis block safe to show verbatim, including the numbered helplines?
2. The moderate-distress block offers a grounding exercise and a meditation. Is that offer
   safe at this severity, or should the turn stay on safety alone?
3. The moderate-distress block asks "Are you safe right now?" — is that question
   appropriate as the closing line, given no human is monitoring the answer?
4. Is the 0.66/0.72/0.74 router-boundary trade-off (`AGENTS.md` X27) acceptable to a
   clinician, or does it need a clinical review before any change?

No answer here is a pass. An unsigned row means the copy is unreviewed.
