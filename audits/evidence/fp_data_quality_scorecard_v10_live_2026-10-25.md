# First-person data-quality scorecard (public_release_v10_points_export_2026-10-21.json)

Verdict: **FAIL** — 12/24 checks pass; gating failures: asr_clean_not_idempotent, duration_out_of_band_rate, speech_rate_out_of_band_rate, boundary_defect_rate, text_edited_vs_source_rate, speaker_verified_without_method, strict_clean_rate.
Spans: 2737. Generated 2026-10-25T06:40:24.559007+00:00.

| Check | Severity | Measured | Target | Status |
|---|---|---|---|---|
| missing_required_fields | BLOCKER | 0 (0/2737) | ≤ 0 | PASS |
| invalid_values | BLOCKER | 0 (0/2737) | ≤ 0 | PASS |
| text_hash_mismatch | BLOCKER | 0 (0/2737) | ≤ 0 | PASS |
| asr_clean_not_idempotent | HIGH | 37 (37/2737) | ≤ 0 | FAIL |
| duplicate_identity | BLOCKER | 0 (0/2737) | ≤ 0 | PASS |
| duplicate_text_rate | MEDIUM | 1.17% (32/2737) | ≤ 0.50% | FAIL |
| contained_in_other_span_rate | MEDIUM | 17.14% (469/2737) | ≤ 5.00% | FAIL |
| broken_chain | HIGH | 0 (0/2737) | ≤ 0 | PASS |
| invalid_time_window | BLOCKER | 0 (0/2737) | ≤ 0 | PASS |
| duration_out_of_band_rate | HIGH | 26.42% (723/2737) | ≤ 5.00% | FAIL |
| speech_rate_out_of_band_rate | HIGH | 3.62% (99/2737) | ≤ 2.00% | FAIL |
| short_text_rate | MEDIUM | 0.22% (6/2737) | ≤ 2.00% | PASS |
| boundary_defect_rate | HIGH | 24.48% (670/2737) | ≤ 10.00% | FAIL |
| boundary_label_disagreement_rate | HIGH | 0.44% (12/2737) | ≤ 2.00% | PASS |
| unverified_boundary_label_rate | MEDIUM | 24.04% (658/2737) | ≤ 10.00% | FAIL |
| text_edited_vs_source_rate | HIGH | 48.92% (1339/2737) | ≤ 10.00% | FAIL |
| heavily_edited_vs_source_rate | HIGH | 0.55% (15/2737) | ≤ 1.00% | PASS |
| speaker_verified_without_method | BLOCKER | 732 (732/2737) | ≤ 0 | FAIL |
| lineage_variants | MEDIUM | 1 | ≤ 1 | PASS |
| export_age_days | MEDIUM | 3.7 d | ≤ 7.0 d | PASS |
| max_video_share | MEDIUM | 3.11% (85/2737) | ≤ 2.00% | FAIL |
| min_guru_share | MEDIUM | 49.65% | ≥ 30.00% | PASS |
| opening_clip_rate | MEDIUM | 8.88% (243/2737) | ≤ 5.00% | FAIL |
| strict_clean_rate | HIGH | 39.72% (1087/2737) | ≥ 60.00% | FAIL |
