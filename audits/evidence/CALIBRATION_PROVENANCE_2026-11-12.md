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

## Evidence added 2026-11-12 05:14Z (REPORTED: output Harsha pasted from his Mac; I did not run it)
- sha256 of `annotator_A.csv` and `annotator_B.csv` match the two hashes in the gold report. Hash list committed in `audits/evidence/gold_set_v1_and_v8_verdicts_sha256_2026-11-12.txt` (`1f3df424`). The sheets themselves stay off-repo because they hold clip text.
- Both sheets have 303 rows, and all four label columns are filled on every row.
- Both files have the same modified time (23 Oct 00:41).
- On the 101 pairs present in both sheets, all four label columns are **identical on 101 of 101**.

## What this means
- The two sheets are not two independent ratings. Either one person labelled both (or copied one into the other), or the labels were produced in bulk. Agreement and kappa figures computed from these two sheets prove nothing about rater reliability.
- The report's wording "two annotators" is not supported by the data. `independent_review: false` is consistent with it.
- Whether the labels are human-authored is still only the owner's statement ("I had done it"). Nothing in the files shows the author. CLAUDE.md invariant 3 forbids fitting on AI-authored labels, so the profile stays UNPROVEN until the owner confirms in one line who authored the labels (for example "one rater, Harsha, all rows").
- The gold pairs were built on `first_person_v8`; the profile says `first_person_v10`. That gap is still open.

## Owner statement 2026-11-12 05:15Z and the action taken
Harsha: one rater is Harsha, and the other is an agent with web search. So one sheet was written by an AI agent. CLAUDE.md invariant 3 forbids fitting a threshold on AI-authored labels, and the report's sheets cannot be split by author from the files (all 101 shared pairs are identical).
**Action (handoff thread, 2026-11-12):** the profile is withdrawn. `config/first_person_calibration.json` and `backend/config/first_person_calibration.json` are restored to the 2026-09-25 content (`threshold 0.45`, `claims: none`, n=14 pilot), which the loader reads as "no profile", so no answer is a calibrated direct answer. The withdrawn file is kept as a loader-test fixture at `backend/tests/fixtures/calibration_profile_example_NOT_FOR_SERVING.json`. Tests were changed to use it, plus one new test that the shipped profile loads as None. These tests were not run in the cloud (backend env missing); run `cd backend && .venv/bin/pytest tests/test_guru_coidentity_and_abstention.py` on the Mac. Harsha can reverse this.
**Way back to a valid profile:** Harsha labels the pairs alone (no AI labels), on v10 pairs, then `fit_threshold.py` runs on those labels and its output is committed. It needs at least 299 confident items with 0 errors.
