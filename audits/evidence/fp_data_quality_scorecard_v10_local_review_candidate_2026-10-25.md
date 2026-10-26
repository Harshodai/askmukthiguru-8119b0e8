# First-person data-quality scorecard (public_release_phase4_tier_local_review_candidate_2026-10-22.jsonl)

Verdict: **FAIL** — 17/26 checks pass; gating failures: duration_out_of_band_rate, boundary_defect_rate, strict_clean_rate.
Spans: 1529. Generated 2026-10-26T05:10:18.263658+00:00.

| Check | Severity | Measured | Target | Status |
|---|---|---|---|---|
| missing_required_fields | BLOCKER | 0 (0/1529) | ≤ 0 | PASS |
| invalid_values | BLOCKER | 0 (0/1529) | ≤ 0 | PASS |
| text_hash_mismatch | BLOCKER | 0 (0/1529) | ≤ 0 | PASS |
| asr_clean_not_idempotent | MEDIUM | 9 (9/1529) | ≤ 0 | FAIL |
| script_mixed_or_loop | BLOCKER | 0 (0/1529) | ≤ 0 | PASS |
| asr_cleaner_two_pass_unstable | HIGH | 0 (0/1529) | ≤ 0 | PASS |
| duplicate_identity | BLOCKER | 0 (0/1529) | ≤ 0 | PASS |
| duplicate_text_rate | MEDIUM | 1.96% (30/1529) | ≤ 0.50% | FAIL |
| contained_in_other_span_rate | MEDIUM | 6.93% (106/1529) | ≤ 5.00% | FAIL |
| broken_chain | HIGH | 0 (0/1529) | ≤ 0 | PASS |
| invalid_time_window | BLOCKER | 0 (0/1529) | ≤ 0 | PASS |
| duration_out_of_band_rate | HIGH | 17.33% (265/1529) | ≤ 5.00% | FAIL |
| speech_rate_out_of_band_rate | HIGH | 0.59% (9/1529) | ≤ 2.00% | PASS |
| short_text_rate | MEDIUM | 0.33% (5/1529) | ≤ 2.00% | PASS |
| boundary_defect_rate | HIGH | 38.39% (587/1529) | ≤ 10.00% | FAIL |
| boundary_label_disagreement_rate | HIGH | 0.00% (0/1529) | ≤ 2.00% | PASS |
| unverified_boundary_label_rate | MEDIUM | 100.00% (1529/1529) | ≤ 10.00% | FAIL |
| text_edited_vs_source_rate | HIGH | 0.00% (0/1529) | ≤ 10.00% | PASS |
| heavily_edited_vs_source_rate | HIGH | 0.00% (0/1529) | ≤ 1.00% | PASS |
| speaker_verified_without_method | BLOCKER | 0 (0/1529) | ≤ 0 | PASS |
| lineage_variants | MEDIUM | 1 | ≤ 1 | PASS |
| export_age_days | MEDIUM | n/a | ≤ 7.0 d | FAIL |
| max_video_share | MEDIUM | 1.31% (20/1529) | ≤ 2.00% | PASS |
| min_guru_share | MEDIUM | 45.19% | ≥ 30.00% | PASS |
| opening_clip_rate | MEDIUM | 10.66% (163/1529) | ≤ 5.00% | FAIL |
| strict_clean_rate | HIGH | 46.63% (713/1529) | ≥ 60.00% | FAIL |
