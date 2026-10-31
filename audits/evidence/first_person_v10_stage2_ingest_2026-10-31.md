# Staging ingest of remaining videos, 2026-10-31

Target: `first_person_v10_stage2_20261031` (new; live `first_person_v10` untouched, 4,224 points before and after; no serving config changed). Earlier `first_person_v10_stage_20261031` is a superseded first build (no ASR provenance) and can be deleted.
Safety snapshot of live v10 first: `first_person_v10-1111874297854021-2026-10-30-20-11-44.snapshot` (53,106,688 bytes, sha256 67d78c94...a0255).

## Candidates (transcript + WAV, not in v10): 81
- 4 aligned word-for-word, 70 only via `--text-from-words`, 7 no timed words (left out). Ids: `audits/evidence/first_person_v10_stage2_candidate_buckets_2026-10-31.json`.
- Built: 18 of the 74 buildable videos, 232 spans + 18 parents = 250 points.
- Quarantine: speaker_unverified 50 videos, no_valid_spans 6 videos, zero_duration_span 19 spans.

## Strict audit (`first_person_v10_stage2_strict_audit_2026-10-31.json`): overall BLOCKED
VERIFIED: alignment_integrity, asr_provenance, citation_window_covers_clip (232/232 exact), contract_children, contract_parents, topology, word_index_consistency.
BLOCKED: speaker_evidence_per_span (no per-span verdict file exists for new spans; same gate is BLOCKED on live v10) - independent speaker evidence UNPROVEN.

## Own scan
- 0 exact duplicates inside stage; 0 vs live v10; 1 near-duplicate span (kNMpaK6SIbc, >=60% 8-gram overlap with v10).
- speaker_verified: 104 true, 128 false. 4 spans are boundary `fragment` (labelled uncertain); 3 spans under 15 words; 4 over 90 s; 6 with >50% foreign windows.
- 100 of 232 pass: speaker verified, clean boundary, >=15 words, <=90 s, foreign windows <=50%.
- Host/interviewer speech present among unverified spans (e.g. "Preetaji delivered a powerful message ..."): do not promote unverified spans.
- 7 candidates have WAV length vs timing end off by >10%/30 s (`207izZBbqVg`, `88NOQTz5_yI`, `OWXe9v7PHDs`, `XcE2G9J8U_4`, `dQw77H27GMY`, `tOi1Ho5Kwhk`, `vLCsNfcbWqs`); `dQw77H27GMY` (20 words) is not corpus content. Whether these are the "3 held audio-mismatch" videos is UNPROVEN.
- Retrieval quality of stage vs v10: NOT measured.
