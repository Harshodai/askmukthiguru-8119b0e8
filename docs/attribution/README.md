# Speaker attribution — two sheets

Built 2026-09-23 for the Guru Brain attribution pilot. Not committed.

## 1. `label_UlOt31lBhLY_15min.csv` — you (≈15 minutes of audio)

Marie Forleo interview with Sri Preethaji and Sri Krishnaji, 2:00–17:00.
For each row, open the `listen` link (it jumps to that second) and fill `speaker`:

| Code | Meaning |
|---|---|
| `P` | Sri Preethaji |
| `K` | Sri Krishnaji |
| `H` | Host (Marie Forleo) |
| `O` | Anyone else / music / silence |
| `X` | Two people at once, or you can't tell |

Rows are ~6 s. The text is an automatic transcript, so treat it as a hint only;
judge by the voice. This is the answer key the automatic labels get scored against.
Leave my predictions out of your view on purpose — they are not in this file.

## 2. `ekam_speaker_request.csv` — for Ekam / PK Consciousness

638 unique videos, sorted by how much of our corpus each one supplies.
**The first 14 rows are half the corpus; the first 157 are 80%.** If they can
only do some, ask for the top rows first.

`our_current_label` is what our system believes today — they should correct it,
not trust it (at least one is already known wrong: `hUmlujE6SN0` is labelled
`krishnaji` but the speaker is Sri Preethaji). Columns to fill: who teaches in
the video, other voices present, names, languages, notes.

## 3. `label_40clips_UlOt31lBhLY.csv` — shorter sheet (~10 minutes)  ← do this one first

39 clips of 2–10 s from the same interview, deliberately weighted toward the
hard cases: segments the voice model could not decide, and moments where the
speaker changes. Open `listen` (it jumps to the second), listen until the
`end_s` time, fill `speaker` with the same codes as above (`P` / `K` / `H` / `O` / `X`).
If a clip contains two people, write both in order, e.g. `H,P`.
The model's guesses are kept in a separate file you never see, so the sheet
stays an honest test.

## 4. `pilot_audit_60_quotes.csv` — does the pipeline's OUTPUT hold up? (~15 minutes)

60 sentences drawn at random from the 1,292 the pipeline would allow us to quote
as a named teacher, across 12 videos. For each: open `listen`, and fill
- `who_speaks`: `P` / `K` / `H` (host) / `O` (anyone else) / `X` (mixed or unsure)
- `text_matches_audio`: `Y` if the words are what was said (small spelling
  differences in names are fine), `N` if words are wrong or missing.

This is a pilot to catch gross failures fast. It is NOT the certification: after
any fixes it triggers, the pipeline is frozen and a fresh random sample of 299
is drawn — 299 with zero errors certifies at least 99% precision at 95% confidence.
