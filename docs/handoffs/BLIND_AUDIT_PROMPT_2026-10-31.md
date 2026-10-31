# Prompt: blind speaker audit (V7) for first_person_v11

Paste everything below the line into a fresh Claude session in this repo. It covers only the V7 listening audit. Another thread owns the ingestion, backfill and v11 build; do not touch those.

---

You are preparing the blind speaker-attribution listening audit (check V7) for `first_person_v11`. Read `lessons.md` (top entries), `CLAUDE.md`, `scripts/ops/speaker_audit.py`, `backend/domain/speaker_audit.py`, `backend/tests/test_speaker_audit.py`, and sections 4b (V7) and 5 of `path-to-graded-run-2026-10-31-20261031T115257-7cd5.md` first.

**Goal.** Harsha listens blind to a random sample of the NEW auto-verified spans in v11: 30 or 5%, whichever is larger. Pass bar: 0 answers of "not the teacher". 0 errors in 30 only bounds the wrong-speaker rate below about 10% (95%); say so in the evidence, do not oversell it.

**Build (read-only, no Qdrant writes, no Docker, no ECAPA, no OpenRouter):**
1. A sheet generator that takes a collection name and a seed, selects only spans that are new in v11 (not among the 4,224 v10 point ids) and have `speaker_verified=true` with method `ecapa_voxceleb_span_slice_v2`. Exclude clips under 2 s. Use the existing `draw_audit_sample` with a fixed seed string, and print the seed.
2. Per sampled span, cut the exact served window (`start_ms - 250` to `end_ms + 250`, capped at duration) from `~/mukthiguru_attribution_data/audio_archive/wavs/<video_id>.wav` into a numbered, shuffled file (`001.wav` ...). The filename and the sheet must not reveal the teacher, the video id, the score or the model verdict.
3. A listener sheet (CSV or a simple local HTML page) with one row per clip: number, audio, and blind choices Sri Krishnaji / Sri Preethaji / host or interviewer / other / unclear, nothing pre-filled. Put one reference clip of each teacher on the same page.
4. The answer key as a separate file in a different folder (span id, labelled teacher, video id, score, margin). Never in the sheet folder.
5. A scorer that reads Harsha's filled sheet plus the key, writes `reviews.jsonl` in the format `speaker_audit.py gate` expects, and runs the gate. Count a wrong or `unclear`/`host` answer as a failure to report, never as a pass.
6. Tests for the selection (seeded, reproducible, v10 ids excluded, under-2 s excluded) and for the key staying out of the sheet folder.

Build and test it against the staged collection `first_person_v10_stage2_20261031` or v10 as a stand-in until v11 exists (the 74-video build is another thread's job; v11 will appear later). Do not write to Qdrant, do not commit secrets, do not push. Leave changes in the working tree and tell Harsha what changed and what is UNPROVEN.
