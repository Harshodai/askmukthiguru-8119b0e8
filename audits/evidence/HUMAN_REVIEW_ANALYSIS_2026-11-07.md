# Human Audit & Review Analysis Report

**Audit Date:** 2026-11-07  
**Auditor:** Harsha  
**Source Data:** `audits/evidence/human_review_results.json`  
**Updated Markdown Sheets:**
- [`audits/evidence/11_demoted_clips_listen_sheet.md`](file:///Users/harshodaikolluru/Public/askmukthiguru-8119b0e8/audits/evidence/11_demoted_clips_listen_sheet.md)
- [`audits/evidence/50_served_clips_human_label_sheet.md`](file:///Users/harshodaikolluru/Public/askmukthiguru-8119b0e8/audits/evidence/50_served_clips_human_label_sheet.md)

---

## 1. Summary of Results

### Sheet 1: 11 Demoted Clips Audit (DATA-15 / Obligation E)
- **Total Reviewed:** 11 clips
- **Confirmed Teacher:** 9 clips (81.8%)
- **Rejected Impostors / Devotee Voices:** 2 clips (18.2%)
  - `0d36a4b1-f036-5e8f-a273-0d61d2f50bbf` (Video: `tegTDWT3SDc`, Window: 161s–185s): *Devotee/guest sharing experience*
  - `60b39aa2-d11d-5a1c-8fbb-76ec5944db91` (Video: `tegTDWT3SDc`, Window: 73s–84s): *Devotee/guest sharing experience*
- **Outcome:** Validates that ECAPA acoustic demotion was correct to flag these points. Both rejected points must be permanently quarantined.

### Sheet 2: 50 Sampled Served Clips (Seed 42 / Obligation F)
- **Total Reviewed:** 50 clips
- **Teacher Voice Match:** 48 / 50 (**96.0% Teacher Voice Accuracy**)
- **Non-Teacher Devotee Voice Identified:** 2 / 50 (4.0%)
  - `0ad56deb-43e1-594b-88ac-37cadea0aa00` (Video: `Lm-5gKTKD7Y`, Window: 104s–130s): *Devotee sharing personal experience*
  - `295a5e1e-9f7e-587c-88d6-cdd8d0a948ac` (Video: `Lm-5gKTKD7Y`, Window: 384s–406s): *Devotee sharing personal experience*
- **Boundary Cleanliness & Content Quality Findings:**
  1. **Story Continuity Needs Full Multi-Span Window:**
     - For story narrations (e.g. `00b5a51f...`, `00d2acb5...`, `00c475c4...`), individual 30–60s spans cut mid-story. Serving requires full parent window expansion (`first_person_enrichment_window_enabled = true` / `enrich_to_parent_window`) so the full story is presented cohesively.
  2. **Event / Program Call-to-Action Spans:**
     - Clips promoting courses (e.g. Manifest, Field of Awakening: `0045104c...`, `03922e5d...`, `03f24c38...`, `1c202e65...`) contain event calls-to-action rather than enduring spiritual doctrine.
     - Recommendation: Quarantine promotional call-to-actions or tag them specifically as course announcements.
  3. **Meditation & Technique Spans:**
     - Clips leading structured meditations (e.g. `20252ce5...`) should be indexed with meditation practice tags.

---

## 2. Immediate Quarantine Action

The 4 identified non-teacher points must be quarantined so they are completely excluded from serving:
```bash
# Quarantine the 4 non-teacher spans
python3 scripts/ops/quarantine_fp_points.py \
  --collection first_person_v10 \
  --reason "devotee_or_guest_experience_human_audit" \
  --apply \
  0d36a4b1-f036-5e8f-a273-0d61d2f50bbf \
  60b39aa2-d11d-5a1c-8fbb-76ec5944db91 \
  0ad56deb-43e1-594b-88ac-37cadea0aa00 \
  295a5e1e-9f7e-587c-88d6-cdd8d0a948ac
```
