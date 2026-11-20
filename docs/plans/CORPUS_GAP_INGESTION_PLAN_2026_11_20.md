# Corpus-gap ingestion plan (2026-11-20) — PLAN ONLY, nothing run

Status: proposal. No download, transcription or Qdrant write has been done. Every write step needs dry-run, then snapshot, then owner OK (backend/CLAUDE.md).

## Gaps found (read-only, `audits/scripts/serve_rate_2026_11_19/corpus_gaps.py` on local v12_shadow, 2026-11-19)
| Gap | Evidence | Kind |
|---|---|---|
| "Four sacred secrets" | the phrase is in 5 transcripts; 3 of those videos were never indexed (`rRs__D_3mKY`, `0z-IZ2ar4eA`, `gMrOMT4mfno`); 2 are indexed with 0 children carrying the phrase (`UlOt31lBhLY`, `xTVHvMHakow`) | ingestion + segmentation |
| Serene Mind, Soul Sync | present, but speaker-blocked (7 of 11 and 14 of 20 children) | speaker labels (validation packet), not ingestion |
| Grief | the only grief clip served in the 2026-11-20 runs opens with "thinking of dying" and is now blocked for non-explicit turns; grief turns mostly abstain | corpus gap: search transcripts for standalone grief teachings |
| Conversation follow-ups, specific life situations | follow-ups abstain `no_evidence`; first turns get generic "two states" clips | partly corpus (few situation-specific clips), partly follow-up handling |

## Steps
1. **Audio:** add the 3 unindexed videos to the audio archive through `scripts/ops/audio_archive.py` (the archive is the only source; ingestion never downloads directly, invariant 17). Check the manifest first; they may already be archived.
2. **Transcribe:** run the hardened Whisper config (`services/speech_config.py`) and the ASR cleaner (`ingest/verbatim/asr_cleaner.py`, invariant 13); hash each span (`source_text_hash`).
3. **Segment:** a rolling 18-25 s window with no splits on trailing conjunctions (invariants 10, 11). For `UlOt31lBhLY` and `xTVHvMHakow`, re-segment so that the four-secrets passages form whole clips. Dry run first: `backend/scripts/ops/dry_run_resegmentation.py`.
4. **Speaker check:** windowed ECAPA, same floor as today. Do not change the floor here; that is the validation-packet decision.
5. **Embed host-side** with `backend/.venv/bin/python3` (invariant 18), never in the container.
6. **Dry run** of the index build into a NEW collection (for example `first_person_v13_shadow`), never into the serving one (invariant 4). The report must show per-video span counts, gate pass rates and a diff against v12_shadow.
7. **Snapshot** v12_shadow, then wait for the owner's OK.
8. **Apply** to the new collection; run the frozen eval (`eval_set_v1.json`, tune split) PROD vs PROD-on-v13 with blind judges; switch serving only on a measured paired improvement, with v12_shadow kept for rollback.

## Grief search (read-only, can run now)
Grep the transcripts in `transcripts/*.md` for standalone teachings on loss and grief that do not frame the listener as suicidal. List candidates with timestamps for the owner to review before any segmentation change.
