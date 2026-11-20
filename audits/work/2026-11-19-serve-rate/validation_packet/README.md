# Speaker-gate validation packet (2026-11-20) — for a human reviewer

## Why this exists
Another tool reviewed the 200-span speaker sample and wrote y/n into the label column: 192 y, 8 n. That was a machine review (ECAPA voice similarity, Whisper excerpts, written rationales), not human listening. CLAUDE.md invariant 3 forbids fitting any threshold on AI-authored labels, so those verdicts now sit in `../speaker_label_sample_MACHINE_REVIEWED.csv` under a column named MACHINE_REVIEW, and the human label column is empty again.

Treat "96% y" as a hypothesis: the speaker gate may be rejecting many clips where the right teacher is in fact speaking (false rejects). This packet tests that hypothesis with your ears.

**Circularity:** the machine review leans on ECAPA similarity, which is the gate's own signal. Agreement between the machine review and the gate's score therefore proves little. Only human listening breaks that loop.

## What to do (about 50 x 30 s of listening)
1. Open `speaker_validation_packet_50.csv`. Each row has a YouTube link that starts at the clip.
2. Listen from `start_s` to `end_s`. In `HUMAN teacher_correct (y/n/unsure)`, write `y` if the voice is the `claimed_teacher` throughout, `n` if it is someone else (host, translator, audience, the other teacher), `unsure` otherwise. Put your name in `HUMAN reviewer_name`.
3. Do not open `MACHINE_verdicts_for_scoring_only.csv` until you are done. It maps each row to the machine verdict and the gate score, and is used only to score agreement afterwards.

Rows: all 8 machine-`n` rows and 42 machine-`y` rows (random seed 20261120), shuffled together (seed 7).

## Decision rule (agreed before anyone looks at the answers)
- If at least 95% of your answered `y`/`n` rows agree with the machine verdict, the false-reject hypothesis is supported. The next step is a dry-run floor plan (below). The floor itself is never chosen by an AI.
- If agreement is below 95%, the machine review is not trustworthy. Label the full 200 rows by hand before any floor change.

## Dry-run plan for a floor change (only after your OK)
1. Fit a candidate floor on human labels only (`audits/scripts/quality_2026_11_20/speaker/fit_floor.py`).
2. Dry run: count how many v12_shadow children would newly pass the gate, per video. No Qdrant write.
3. Snapshot the collection, then show the owner the dry-run diff.
4. Apply only to a NEW collection version (invariant 4), with the old collection kept for rollback.

## Calibration choice (separate decision)
The answer-calibration profile stays withdrawn (commit b68453e8). A 1% risk target needs 299 consecutive human-labelled correct answers; a 5% target needs about 59 (ln 0.05 / ln 0.95). The owner chooses the target before labelling starts.
