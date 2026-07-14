# Meditation narration audio

Drop MP3 files here matching the step IDs in `src/components/meditation/meditationSteps.ts`:

- `arrive.mp3`          (~20s)
- `observe-body.mp3`    (~45s)
- `observe-breath.mp3`  (~60s) — synced to 4-in / 6-out cycle
- `observe-sound.mp3`   (~45s)
- `compassion.mp3`      (~45s)
- `complete.mp3`        (~10s)

The player uses `useMeditationAudio` to load, cross-fade, and preload the next track.
If a file is absent, the timeline still advances silently — the flame + text carry the practice.

Voice direction: warm, unhurried, present-tense. See handoff.md for the recording spec.
