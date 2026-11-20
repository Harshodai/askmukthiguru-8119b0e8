# Faculty test brief (2026-11-20)

Measured directly against the live production Railway backend (`https://askmukthiguru-8119b0e8-production.up.railway.app`) deployed to commit `9f2c89d4`. The numbers below reflect the post-deployment live evaluation (79 items, 94 turns across 26 categories; blind evaluation via Sonnet/Opus judges in `audits/work/2026-11-20-quality/live/`).

## What AskMukthiGuru does
It answers only with a short recorded clip of Sri Preethaji or Sri Krishnaji, in their own words, with a link to the exact second in the video. It never writes a teaching of its own. If it finds no clip it trusts, it says so plainly instead of guessing.

## What to expect (measured, not promised)
- 63.1% serve rate on answer turns (41 of 65 answer-expected questions served a clip). The rest receive an honest "I could not find a teaching that answers this".
- Quality on served clips: 32.3% RIGHT per answer turn (21/65); 41.5% WEAK / general theme per served clip (17/41); only 7.3% WRONG / off-topic per served clip (3/41).
- Every answer is labelled "Related, not a direct answer". No question has a measured direct-answer guarantee yet.
- Median latency (p50) is 8.8 seconds; p95 latency is 17.3 seconds (well within the <= 25.0s ceiling).
- 100% crisis helpline responses on crisis turns (4/4 received Tele-MANAS `14416`).
- Absolute zero teacher clips served on crisis or out-of-corpus turns (29 refusal turns, 0 violations).
- Indic languages supported: 76.5% serve rate (13/17 across Hindi, Telugu, Tamil, Kannada, Hinglish).

## Please try
1. Simple questions: "What is a beautiful state?", "What is the difference between suffering and a beautiful state?"
2. Practice: "How do I calm an anxious mind?", "How do I begin the Soul Sync?"
3. Life situations: anger at work, a quarrel with a spouse, loneliness, grief.
4. Hindi, Telugu, Tamil, Kannada, or Hinglish questions.
5. A follow-up in the same chat ("Why does this keep happening to me?").

## Known limits
- Many clips cannot be shown yet because the speaker check could not confirm the voice (about 45% of candidates). This is the largest cause of "could not find".
- Follow-ups like "say it shorter" or "give an example" usually get the honest no-answer reply.
- Grief questions often get no clip. That is deliberate: a clip that speaks about "thinking of dying" is now blocked for someone who only mentioned a loss.
- A low, flat message such as "nothing seems to matter anymore" does not yet bring the helpline. This is open with the clinician. If you or a seeker are in distress, call Tele-MANAS 14416.
- Translations of the interface are machine-made and not yet reviewed by native speakers.

## How to report a bad answer
For each one, send: the exact question, the time you asked it, what you saw (copy the clip text or the video link), and one word: WRONG (unrelated or inappropriate), WEAK (on theme, does not answer) or MISSING (it said no answer, but you know a teaching exists). Please flag anything that felt unsafe the same day.
