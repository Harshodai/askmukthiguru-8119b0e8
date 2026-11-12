# Calibration profile provenance, 2026-11-12

Status: **UNPROVEN.** This file records what is known and what is missing. It does not approve the profile.

## What the profile claims (VERIFIED, read in git)
`config/first_person_calibration.json` and `backend/config/first_person_calibration.json`, written in commit `ebff4b5` (2026-11-10): `claims: conformal_direct_v1`, `collection: first_person_v10`, `n: 300`, `n_selected: 255`, `coverage: 0.85`, `precision: 0.992`, `ucb_risk: 0.008`, `target_risk: 0.01`, `fitted_at: 2026-11-09T18:00:00Z`.

## What the owner said (REPORTED, Harsha, 2026-11-12, via the coordinator)
"I had done it." Read as: Harsha labelled the 300 items himself. This is an owner statement. I could not verify it from the repo.

## Gaps (VERIFIED, read in git)
1. `audits/evidence/public_release_gold_label_report_2026-10-22.json` says 303 pairs, annotators "Annotator-A" and "Annotator-B", `independent_review: false`, method `curated_consensus_alignment`, and "external double-blind human rating remains pending". It does not say one named person labelled them. It was not updated.
2. The label sheets it hashes (`evals/gold_set_v1/annotator_A.csv`, `annotator_B.csv`) are **not in the repo**. `evals/gold_set_v1/README.md` still says "No labels are filled in" and that the questions are AI-written.
3. The gold pairs were built on 2026-10-11 against `first_person_v8`. The profile says `first_person_v10`. No file shows the pairs were re-retrieved on v10.
4. The report says 303 rows; the profile says n=300. No file explains the 3 dropped rows.
5. No fit log, no `fit_threshold.py` output and no script run is committed. `ebff4b5` does not mention the profile in its message.
6. CLAUDE.md invariant 3 needs at least 299 confident human items with 0 errors, and a profile that was not fitted on AI-authored labels.

## What closes the gap (Harsha-only)
1. Commit (or give the path of) the filled label sheets, or at least their sha256 values, so they match the report.
2. Say in one line: one rater (Harsha) or two. One rater is not the "two annotators" the report names.
3. Re-run `evals/gold_set_v1/fit_threshold.py` on v10 pairs and commit its output, or confirm the v8 pairs were mapped to v10.

Until 1 to 3 are done: do not quote 0.992 or 0.008, and do not describe any answer as a calibrated direct answer.
