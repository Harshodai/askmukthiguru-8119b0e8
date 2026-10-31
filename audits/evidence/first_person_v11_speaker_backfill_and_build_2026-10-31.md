# v10 speaker backfill and v11 build, 2026-10-31

Local stack (Docker), no OpenRouter. Work files: `.work/speaker_2026-10-31/` (gitignored). Code: `ff3e29f9` + `dff0b39f`.

## Calibration (one id for every step)
- Impostor slices: 3,216 candidates from 485 videos (host/interviewer "O" windows). 3,196 used, 20 missing audio.
- `calibration_v2`: id `9cf4b4156124e05866b7327cef24009e8906aae6c0c7479a80c8b86234da7044`, cosine floor 0.4854, margin 0.3862. Test: 0 false accepts in 1,400 impostor trials, 0 false rejects in 262. Clopper-Pearson 95% upper bound **0.21%** (meets 1% and 0.5%). Trials share videos and speakers, so the true bound is wider (UNPROVEN how much). sha256 calibration `8f71e4be…`, references `5ccba5b6…`.
- Supersedes the pinned 1.14% (0/262, revision 8daa5065…).

## Live v10 backfill (Harsha's typed OK after the dry run, then "do 1")
- Snapshots: `…12-02-50` (before backfill 1), `…12-23-09` (before backfill 2), `…12-24-02` (after both).
- Backfill 1, 732 spans claiming verified with no method: 729 pass, 1 fail (margin 0.333 < 0.386, video kzRqQOvjRhA, now `ecapa_failed`, flag false), 2 no_evidence (window past end of audio). 730 writes.
- Backfill 2, 15 more violators found by the post-check (13 old `span_slice_v2` spans without evidence + the 2 no_evidence): 2 stamped, 11 window-failing demoted to `ecapa_failed`, 2 demoted to `pending_voice_check`. 15 writes.
- Post-checks, both runs: 4,224 ids unchanged, text and both hashes unchanged, only allowlisted keys changed, vectors identical on the script's sample (20 and 15 points, not 50), 0 violators (legacy `centroid_v1` exempt, R3).
- Net effect on live v10: 13 spans no longer served as verified.

## v11 (restored from post-backfill v10, then built)
- 74 buildable videos, floors unchanged: 9 built (140 spans, 9 parents), 59 skipped (no span clears the speaker floors; checked on three: meditation or processed audio scores cosine near 0 against both teachers), 6 no valid spans.
- Removed after the build: 15 points (13 spans + 2 parents) from the two V9 mismatch videos `88NOQTz5_yI`, `OWXe9v7PHDs`.
- Incident: another client (host `backend/.venv`, qdrant-client 1.19.1) wrote tags/topics and re-set `speaker_verified=true` on 17 demoted spans in the first v11 at 13:03-13:41Z. That v11 was dropped (snapshot `first_person_v11-…16-38-41` and `v11_dirty_payloads.jsonl` kept) and rebuilt from the clean snapshot. Writer unidentified (UNPROVEN who).

## V1-V10 (final v11: 4,358 points; 2,777 verified, 108 unverified)
| # | Result |
|---|---|
| V1 P4 gate | PASS, exit 0, 0 violators |
| V2 provenance | PASS, 0 violators; 772 `span_slice_v2` + 2,005 legacy centroid (exempt) |
| V3 one calibration | PASS, every v2 span carries `9cf4b415…` (783 counted before the V9 removal; 772 after) |
| V4 integrity | PASS, `source_text_hash == sha256(verbatim_text)` on 2,885 children, 0 mismatches |
| V5 defects | PASS on the 134 new points (scorecard exit 0, no BLOCKER/HIGH). MEDIUM: 17 spans not a fixed point of the ASR cleaner (not edited; quote text is never changed). Serve-time dry pass over 41 verified new spans: 4 fail the standalone gate (filtered at serve), 1 under 15 words |
| V6 duplicates | PASS, 0 exact, 0 near (8-gram >= 60%) vs v10 |
| V7 blind listen | NOT DONE. Seeded sample drawn: 30 of 41 new auto-verified spans (24 of the pool are one video, 1 Preethaji span). Key kept at `~/mukthiguru_attribution_data/speaker_audit/v11_2026-10-31_key/`, sample sha256 `d8b68a23…`. Waits for Harsha. |
| V8 originals | PASS, all 4,224 ids present, 0 payload diffs vs post-backfill v10, 0 vector diffs on a seeded 50 |
| V9 audio sanity | PASS after removing the two mismatch videos |
| V10 serving contract | PARTIAL. v11 declared in `backend/config/first_person_serving_contract.json`; the backend's startup check reported ok=True for it; `make verify-stack-fresh` FRESH. v10-only mode and empty caches UNPROVEN (running backend still has `FIRST_PERSON_COLLECTION=first_person_v8`; graded override not applied) |

**Verdict: v11 is not cleared.** V7 is open and V10 is unproven. Graded run stays NO-GO until the clean-Docker run on final main is graded.
