# First-person v10 provenance coverage — 2026-10-21

Read-only join; no Qdrant points, aliases, files, or runtime data were changed.

## Inputs

- Audio archive manifest: `/Users/harshodaikolluru/mukthiguru_attribution_data/audio_archive/manifest.json` (version `1.0`, 680 archived assets).
- ASR bakeoff: `/Users/harshodaikolluru/mukthiguru_attribution_data/bakeoff_2026-09-25/asr_bakeoff.json` (8 pilot videos; model keys: clips, parakeet, punct, speaker, whisper).
- Pilot word-timed transcripts: `/Users/harshodaikolluru/mukthiguru_attribution_data/pilot50_2026-09-25/transcripts_B` (50 files).
- Current v10 source-span manifest: `/Users/harshodaikolluru/Public/askmukthiguru-8119b0e8/.work/fp_context/manifest_with_speakers.jsonl`.

## Coverage

| Measure | Count |
|---|---:|
| Qdrant v10 retrieval-child points | 2737 |
| Qdrant child videos | 485 |
| Source-manifest child spans | 1838 |
| Qdrant/source-manifest span intersection | 1838 |
| Qdrant child points with archived-audio metadata | 2737 |
| Qdrant child points in pilot-50 videos | 218 |
| Qdrant child points missing ASR engine/model provenance | 2737 |
| Qdrant child IDs absent from source manifest | 899 |

## Conclusion

**BLOCKED.** The supplied archive manifest and pilot ASR artifacts are useful evidence, but no unified per-span `asr_engine`, `asr_model_version`, and `transcription_run_id` mapping exists for all 2737 citable children. The current source-span manifest covers 1838 child spans, leaving 899 Qdrant child IDs outside that manifest. No provenance values were inferred or backfilled.
