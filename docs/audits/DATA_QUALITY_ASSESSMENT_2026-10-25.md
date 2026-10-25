# First-person data-quality assessment (2026-10-25)

Verdict on the data: **FAIL** (7 gating checks fail on the live export, 4 on the rebuilt candidate). Overall release verdict stays NO-GO.

## What was measured, and what was not

| Item | Value |
|---|---|
| Tool | `backend/scripts/ops/fp_data_quality_scorecard.py` (read-only, stdlib plus `ingest.verbatim` helpers), 24 checks over 9 data-quality dimensions |
| Tests | `backend/tests/test_fp_data_quality_scorecard.py`, 22 pass (`pytest --noconftest`, Linux container, 2026-10-25) |
| Input A | `audits/evidence/public_release_v10_points_export_2026-10-21.json`: 2,737 `first_person_v10` children, exported 2026-10-21 |
| Input B | `audits/evidence/public_release_phase4_tier_local_review_candidate_2026-10-22.jsonl`: 1,529 rebuilt candidate spans |
| Reports | `audits/evidence/fp_data_quality_scorecard_v10_live_2026-10-25.{json,md}` and `..._v10_local_review_candidate_2026-10-25.{json,md}` (teacher text redacted) |
| Rerun | `cd backend && python -m scripts.ops.fp_data_quality_scorecard --points <export> --redact-text --out r.json --md-out r.md` |

**Not measured (UNPROVEN):** the live Qdrant collection today (both inputs are committed exports; the 2026-10-22 promotion may have changed what is live), audio-to-text alignment, whether the speaker is correct, ASR word error rate, vector freshness against payload text, and coverage against the full list of source videos. These need the Mac audio archive or Qdrant; this container has neither. The tool cannot see them.

Thresholds are my targets, set by judgement (for example the 8 to 60 s duration band and the 60% clean-span bar). They are not owner-approved numbers. Override with `--thresholds file.json`.

## What is clean (measured)

On the 2,737-span export: required fields 0 missing, types and enums 0 invalid, `sha256(verbatim_text) == source_text_hash` for all 2,737, no duplicate span ids or windows, no negative or zero-width windows, prev/next links closed and symmetric where present (1,460 spans carry none), one lineage (schema, corpus, ASR engine and model all uniform), two teachers balanced (49.7% / 50.3%), 485 videos. The structural contract is sound. That matches the strict audit already on file.

## What is not clean (measured)

| # | Finding | Live v10 export (2,737) | Rebuilt candidate (1,529) |
|---|---|---|---|
| 1 | `speaker_verified=true` with no recorded verification method | **732 (26.7%)** | 0 |
| 2 | Words differ from the raw ASR text | **1,339 (48.9%)** | not measurable: only exact reconstructions were admitted |
| 3 | Span outside 8 to 60 s | **723 (26.4%)**, 675 over 60 s, longest 590 s | 265 (17.3%), 221 over 60 s |
| 4 | Boundary detector finds a head/tail defect | **670 (24.5%)** | **587 (38.4%)** |
| 5 | Speech rate outside 1 to 5 words/s (text and audio window disagree) | 99 (3.6%) | 9 (0.6%) |
| 6 | Span fully inside another span of the same video | 469 (17.1%) | 106 (6.9%) |
| 7 | `asr_cleaner` would still change the text | 37 (1.4%) | 15 (1.0%) |
| 8 | Identical text on two spans | 32 (1.2%) | 30 (2.0%) |
| 9 | Starts in the first 5 s of a video | 243 (8.9%) | 163 (10.7%) |
| 10 | One video holds 85 spans | 3.1% | 20 spans, 1.3% |
| 11 | **Spans passing every span-level check** | **1,087 (39.7%)** | **708 (46.3%)** |

### How to read these

- **Finding 1 is a claim without evidence.** All 2,737 children carry the flag; 732 have no `voice_verification_method`. This matches blocker B1 in `docs/FIRST_PERSON_PUBLIC_RELEASE_STATUS_2026-10-21.md` (no per-span verdict). The tool treats the flag as a claim until a method is recorded.
- **Finding 2 is a lineage gap, not proof of error.** Samples I read look like ASR corrections ("cash land" became "crash land"), but one rewrites "IC 2020 has" to "I see 2020 as". No per-span record says which stage changed the words or why, and the audio is the only ground truth. The Phase 3 rebuild independently quarantined 1,127 spans as `reconstruction_variant_not_exact`; the two counts use different baselines, so they agree in size, not in identity. UNPROVEN whether the edits are right.
- **Finding 3: the span is not a clip.** A 590-second "span" cannot be quoted or played as a passage. The Phase 3 rebuild fixed coordinates but 17% of the rebuilt candidate is still outside the band.
- **Finding 4 got worse after the rebuild (24.5% to 38.4%).** Same detector, same text rules. The dominant defects are `head_lowercase` (443) and `tail_no_terminal` (358). My hypothesis is that exact ASR reconstruction cuts mid-sentence because the word stream carries little punctuation; I have not verified it. The rebuild fixed provenance and cost sentence quality.
- **Finding 11 is mechanical, not semantic.** A span that passes all 14 span-level checks is structurally sound. It is not necessarily a complete, standalone, relevant teaching. The earlier blind judge put the showable share at about 1 in 7 on v8 (`docs/audits/RELEASE_EVIDENCE_2026-10-11_CLAUDE_CODE.md`); a different measure on a different collection. Expect the showable share to sit below 39.7%, not above it.

## Governance finding

`lessons.md` L-PUBLIC-REPO-1 records the repo as public (checked 2026-10-11; **re-verify**). `audits/evidence/` tracks 99 files, including the 2,737-span export and several candidate and quarantine JSONL files with full teacher text. The publication guard (`scripts/guards/lesson_guards.py`) only inspects CSV headers and specific paths, so JSON and JSONL with a `verbatim_text` or `text` field pass it. This is a guard gap and a rights question for the owner (T-A1). I did not change the guard: it is shared tooling and the call on the already-tracked files is the owner's. The two reports I added are redacted and carry no teacher text.

## Fix order, with a measurable exit for each

1. **Edit ledger.** Record `{stage, before, after, reason}` per changed span, or stop editing. Exit: `text_edited_vs_source_rate` explained 100% by ledger entries, plus a human audio check of a stratified sample of edited spans (Mac).
2. **Speaker evidence per span.** Exit: `speaker_verified_without_method` = 0 and the B1 reconciliation gates.
3. **Re-segment over-long spans** into sentence-complete passages inside 8 to 60 s (target 18 to 25 s). Exit: `duration_out_of_band_rate` at most 5%.
4. **Sentence-boundary pass on the rebuilt candidate.** Exit: `boundary_defect_rate` at most 10%, without reintroducing coordinate drift. Re-check with the strict audit.
5. **Redundancy and hub clips:** collapse contained spans and exact duplicates; cap per-video share. Exit: contained at most 5%, duplicate text at most 0.5%, opening clips at most 5%.
6. **Resolve the one deterministic-id collision** (`public_release_phase4_tiers_summary_2026-10-22.json`).
7. **Gate it.** After fixes 1 to 4, run the scorecard with `--baseline` against the previous export before every graded run and attach the report to the evidence pack. Drift (id churn, same-id text changes) is reported by the same command.

## What this does not fix

The tool measures; it does not repair data. The pending items go green only when the data changes and the scorecard says so. Today the data fails gating checks on both inputs, and the earlier B1 to B7 blockers still stand.

## Code-level cause found and fixed (commit 670b33f)

Finding 1 traces to `backend/scripts/ops/build_fp_context_from_v9.py`: the builder wrote `speaker_verified=True` for every span and inverted the `voice_verification_method` condition, so a label-only point became "verified" with no method. The builder now copies the stored per-point verdict (invariant 23), quarantines refused verdicts (`speaker_verdict_refused`), runs `clean_verbatim_text` before hashing (invariant 13) and reports `quality_counters`. Tests: 4 new in `backend/tests/test_fp_context_builder_from_v9.py` (72 pass across the four related test files, `--noconftest`).

**Consequence:** a rebuild now carries label-only spans as `speaker_verified=false`, which `points_servable` refuses, so roughly 732 spans leave the servable set until span-level evidence exists. That is the honest number. The existing v10 collection is unchanged; nothing was rebuilt or written to Qdrant (UNPROVEN on live data).

Still report-only, not fixed in code: over-long spans, the missing edit ledger, `asr_cleaner` non-idempotence (37 spans), the boundary regression in `rebuild_v10_asr_coordinates.py` (not inspected), the one id collision.
