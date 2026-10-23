

## Stage 4 supplied-artifact provenance reconciliation — 2026-10-21

The user-provided audio archive manifest, ASR bakeoff, pilot word-timed transcript directory, and workspace transcripts were reconciled against v10 in a metadata-only read-only join. Serving is confirmed disabled in both `backend/.env` and the running backend (`FIRST_PERSON_CONTEXT_HARNESS_ENABLED=false`). Evidence is retained in `audits/evidence/first_person_provenance_coverage_2026-10-21.json` and `.md`.

| Measure | Result |
|---|---:|
| v10 retrieval-child points | 2,737 |
| v10 child videos | 485 |
| Child points with archived-audio metadata | 2,737 |
| Current source-manifest child spans | 1,838 |
| Qdrant/source-manifest intersection | 1,838 |
| Qdrant child IDs outside current source manifest | 899 |
| Pilot word-timed transcript files | 50 |
| v10 child points in pilot videos | 218 across 37 videos |
| ASR bakeoff videos | 8 |
| Child points missing ASR engine/model provenance | 2,737 |

Conclusion: the supplied artifacts strengthen audio/rights and pilot-method evidence but do not close the full-corpus provenance gate. No unified per-span `asr_engine`, `asr_model_version`, or `transcription_run_id` mapping exists for all citable children. No provenance values were invented or backfilled; no Qdrant point, alias, deployment, or serving state changed.
