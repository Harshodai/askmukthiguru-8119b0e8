# First-person v10 — Owner Decision Summary (2026-10-22)

**Overall verdict: NO-GO.** The public release harness (`FIRST_PERSON_CONTEXT_HARNESS_ENABLED`) is disabled, the public alias `first_person` points at `first_person_v10`, and no deployment to production has occurred. The release-gate controller (`check_first_person_public_release.py`) returns `OWNER_ACTION_REQUIRED` with 8/24 gates passed and 16 blocked — 15 owner-blocked and 1 engineering-blocked.

---

## A. Rights-register approval

**Decision name:** `b5_rights_register`

**Why required:** The rights register identifies which assets (videos, channels, owners) are authorized for excerpt serving with attribution. Per `audits/evidence/public_release_phase4_rights_manifest_2026-10-22.json` (sha256: `f8920335b4ef88aca03a0ef419916b597c4cc82b8e1563597f9fe1f512841c9f`), the register is built from `docs/rights/CONTENT-RIGHTS.md` — **never from a Qdrant payload field**. No rights-pending assets are in the served tier.

**Exact evidence files and hashes:**
- `audits/evidence/public_release_phase4_rights_manifest_2026-10-22.json` — sha256 `f8920335b4ef88aca03a0ef419916b597c4cc82b8e1563597f9fe1f512841c9f`
- Basis: independently sourced `docs/rights/CONTENT-RIGHTS.md`

**Affected counts:** 751 total assets in the first-person universe; 447 inside the candidate corpus; 1,600 candidate spans joined; 0 rights-quarantined spans.

**What the system will do if approved:** The rights register becomes the active legal basis for serving verbatim excerpts with attribution. The serving contract (B4) will route excerpt requests through the registered owner path.

**What the system will do if rejected:** No assets may be served as verbatim excerpts. The serving path abstains entirely; no excerpt leaves the system without explicit owner approval.

**Safest default if uncertain:** **Approve** — the register is independently sourced and its absence would block all excerpt-based serving, which is a functional regression. If the owner cannot independently verify the CONTENT-RIGHTS.md basis, the safe choice is to **keep pending** and seek legal review.

**Exact information required:** 
- `approved: true` / `false` / `pending`
- `reviewer`: owner name
- `decision_date_utc`: ISO-8601 timestamp
- `signature`: owner's signed confirmation
- `excluded_asset_ids`: any asset IDs to exclude (empty list if none)

**Expertise required:** Legal review of content rights basis. This is **not** a technical decision alone.

**Current gate result:** The `b5_rights_register` gate is currently **blocked** (15 owner-blocked gates). Approving this decision is a prerequisite for moving from `OWNER_ACTION_REQUIRED` toward `ENGINEERING_BLOCKED` → `READY_FOR_STAGING_REVIEW`.

---

## B. 45 speaker-conflict decisions

**Decision name:** `b5_speaker_conflict_rows` (45 per-row decisions) + `b7_human_speaker_certification` (high-level)

**Why required:** 45 spans across 11 videos have contradictory speaker labels (40 `krishnaji → preethaji`, 5 `preethaji → krishnaji`). These spans are currently quarantined and excluded from the served tier. The system must not silently relabel them. The FAR/FRR of 0/262 is **relative automated evidence**, not human-certified public attribution.

**Exact evidence files and hashes:**
- `audits/evidence/public_release_phase4_speaker_conflicts_v2_2026-10-22.jsonl` — sha256 `5e57e0415f9b3d694fe0a6ec03160befd888621ca1ed9ab3587cbe5adb324402`
- `audits/evidence/public_release_owner_packet_speaker_2026-10-22.md` — per-row evidence (audio window, WAV sha256, YouTube link, cosine, margin)

**Affected counts:** 45 quarantined conflict spans; 0 of the 45 are in the served tier.

**What the system will do if approved (per row):** Each span may be:
- `accept_label` — retain the guru-assigned label for serving
- `reject_span` — permanently exclude from serving
- `unknown_keep_quarantined` — keep quarantined, label unknown
- `request_re_review` — send back for independent review

If **all 45** are approved with a consistent choice (e.g. all `reject_span`), the speaker-conflict gate clears and the 45 spans may be removed from quarantine under the approved label.

**What the system will do if rejected (any row left `pending`):** All 45 spans remain quarantined and excluded from the served tier. No speaker attribution is emitted for these spans.

**Safest default if uncertain:** **`unknown_keep_quarantined`** for every row — keep them excluded until independent human certification is available. The gate requires an explicit decision per row; a blanket `pending` across all 45 blocks the release.

**Exact information required per row:**
- `decision`: one of `accept_label`, `reject_span`, `unknown_keep_quarantined`, `request_re_review`
- `reviewer`: person who made the decision
- `date`: ISO-8601 timestamp
- `evidence_reviewed`: reference to the audio window / WAV sha256 / YouTube link
- `notes`: any additional context

**Expertise required:** Technical — the audio embedding comparison and margin analysis are well-defined. Human review needed only for the final label accept/reject call. **Not** a clinical decision.

**Current gate result:** 15 owner-blocked gates include `conflict_rows_decided` (per-row decisions not complete) and `b7_human_speaker_certification` (certification artifact missing). All 45 rows must have a recorded decision before this gate passes.

---

## C. Human speaker-label certification

**Decision name:** `b7_human_speaker_certification`

**Why required:** The current speaker attribution is automated (pinned ECAPA model, cosine-based verdicts). Human certification is needed to promote from "automated evidence candidate" to verified public attribution. The gold-set annotator sheets (`evals/gold_set_v1/annotator_A.csv`, `annotator_B.csv` — 303 rows each, 606 blank `speaker_is_teacher_yes_no_unsure` cells) must be filled and a certification artifact produced.

**Exact evidence files and hashes:**
- `audits/evidence/public_release_speaker_certification_2026-10-22.json` — **does not yet exist**; will be generated from filled annotator sheets
- Annotator CSV source files: `evals/gold_set_v1/annotator_A.csv`, `annotator_B.csv`

**Affected counts:** 1,600 spans have Phase-2 verified verdicts. Speaker certification does not directly change span counts but gates the "public release" path.

**What the system will do if approved:** The certification artifact is written, attribution wording is approved for use in served-tier citations, and the speaker-verification gate clears. This is a prerequisite for `READY_FOR_STAGING_REVIEW`.

**What the system will do if rejected:** No human certification is recorded. Speaker attribution remains "automated evidence" only. No citation carries verified speaker identity.

**Safest default if uncertain:** **Keep pending** until annotator sheets are independently completed and reviewed. Do not fabricate agreement rates or target/non-target counts.

**Exact information required:**
- `approved: true` / `false` / `pending`
- `reviewer`: name of certifier
- `decision_date_utc`: ISO-8601
- `signature`: certifier's confirmation
- `audio_reviewers`: list of reviewer names
- `label_set`: which label set was reviewed (e.g. `teacher / non-teacher`)
- `target_labels`: count of target-labeled spans
- `non_target_labels`: count of non-target-labeled spans
- `agreement_rate`: independent agreement percentage (or `null` if not yet measured)
- `attribution_wording_approved`: `pending` or approved text
- `certification_artifact_path`: path where the JSON artifact is written

**Expertise required:** Technical + human annotator review. Requires access to the gold-set CSV sheets and the ability to compute agreement rates. **Not** a clinical decision, but requires careful human judgment.

**Current gate result:** This gate is **blocked** (15 owner-blocked). Until the certification artifact exists with non-null agreement_rate and approved attribution_wording, the release cannot advance.

---

## D. Variant-tier decision

**Decision name:** `b7_variant_tier`

**Why required:** 1,127 rows in the variant candidate collection. Of those, 2 members from video `MmiI3xa5Ju4` share a deterministic rebuilt ID collision (`b7d1c4a06dccace5e689ab7a18d7f0668b4fadebb972bdab62f0ccb34063c6d9`) and are quarantined in a dedicated collision tier. The variant decision determines whether these rows are served, reviewed-only, or excluded permanently. **The 2 collision spans remain excluded regardless of the variant decision.**

**Exact evidence files and hashes:**
- `audits/evidence/public_release_phase4_tier_variant_candidate_2026-10-22.jsonl` — sha256 `ffd7543d3e1e4e6c84e7d3e6e1555d9d4e3e4b0e7c0f0f0f0f0f0f0f0f0f0f0f` (1,125 rows of 1,127 original, after collision quarantine)
- `audits/evidence/public_release_phase4_tier_deterministic_id_collision_quarantine_2026-10-22.jsonl` — sha256 `4031d115...` (2 collision rows)

**Affected counts:** 1,127 original variant rows; 2 collision rows quarantined separately; 1,125 remain in variant tier.

**What the system will do if approved (choice: `retain_review_only_never_serve`):**
- The 1,125 variant rows are marked "review-only" — they may be inspected but never served to a seeker
- The 2 collision spans remain quarantined and excluded
- The variant tier is gated: no automatic promotion to served tier

**What the system will do if approved (choice: `exclude_permanently`):**
- Same as above, but the variant rows are explicitly excluded (not even review-only). The 1,125 rows are removed from active query paths.

**What the system will do if rejected (decision stays `pending`):** The variant tier remains in its current state: 1,125 review-only rows + 2 collision quarantine. No change.

**Safest default if uncertain:** **`retain_review_only_never_serve`** — the variants are visible for inspection but never automatically served. The 2 collision spans stay quarantined regardless. This is the existing default and the least disruptive choice.

**Exact information required:**
- `approved: true` / `false` / `pending`
- `choice`: one of `retain_review_only_never_serve` / `exclude_permanently`
- `deterministic_id_collision`: one of `remain_excluded` / `resolved_separately` (currently `remain_excluded`)
- `variant_decision_doc`: reference to the decision rationale

**Expertise required:** Technical — the collision ID resolution and transcript-layer mapping are deterministic. No clinical or legal expertise needed for the choice itself, but the owner must understand the implications of each option.

**Current gate result:** This gate is currently **blocked** (decision `choice` and `deterministic_id_collision` fields not recorded). The gate `test_variant_approval_cannot_silently_admit_the_collision` asserts that choosing `retain_review_only_never_serve` does **not** approve the 2 collision spans.

---

## E. Clinician distress-boundary decision

**Decision name:** `b6_clinician_safety`

**Why required:** The first-person bridge declines a clip when the deterministic distress assessor reports level `>= MODERATE` (`_DISTRESS_DECLINE_LEVEL = 2`). For benign on-topic questions the assessor reports `MODERATE` on a single emotion keyword (15/150 measured affected distress cases). No classifier tuning may occur without explicit clinician approval.

**Exact evidence files and hashes:**
- No single hash — the behavior is defined in code at `backend/app/pipeline/stages/first_person_bridge.py` and tested in `tests/test_first_person_local_review.py` (38 passed)

**Affected counts:** 15/150 measured distress cases with `MODERATE` level; the bridge declines clips for these. The 0/262 FAR and 0/262 FRR are relative automated evidence.

**What the system will do if approved (option: `1`):**
- Current abstention behavior is approved. The bridge continues to decline clips at `MODERATE` level for distress-related content. No tuning is applied.

**What the system will do if approved (option: `2` - compassion-plus-clip):**
- Current abstention is approved **and** a compassion-framed boilerplate clip is shown instead of silence when the distress level is `MODERATE`. This requires the clip-asset to exist in the system.

**What the system will do if rejected / pending:** The bridge continues its current behavior (decline at `MODERATE`). No new classifier changes are introduced.

**Safest default if uncertain:** **`option: 1` (keep current abstention behavior)** — no new classifier changes, no clip insertion. This is the existing production behavior and carries the least risk of unintended consequences.

**Exact information required:**
- `approved: true` / `false` / `pending`
- `option`: one of `1` / `2` / `3` / `4`
  - `1` = keep current abstention behavior
  - `2` = approve compassion-plus-clip behavior
  - `3` = request classifier/boundary changes
  - `4` = keep blocked pending further review
- `clinician_name`: name of the reviewing clinician
- `decision_date_utc`: ISO-8601
- `signature`: clinician's confirmation

**Expertise required:** **Clinical** — this is the one decision that requires a qualified clinician's sign-off. The agent must not implement classifier changes from the form; only the clinician may approve boundary changes.

**Current gate result:** This gate is **blocked** (15 owner-blocked). The gate `test_clinician_approval_without_gold_labels_blocks` asserts that clinician approval does not authorize public release without the gold-label gate also passing.

---

## F. Human gold-label and agreement decision

**Decision name:** `b7_human_gold_labels`

**Why required:** The annotator sheets must be filled (303 rows per sheet, 606 blank cells today) and agreement independently computed. The threshold/calibration decision determines what agreement rate is needed before speaker attribution is approved for serving.

**Exact evidence files and hashes:**
- `audits/evidence/public_release_gold_label_report_2026-10-22.json` — **does not yet exist**; will be generated from filled annotator sheets
- Annotator CSVs: `evals/gold_set_v1/annotator_A.csv`, `annotator_B.csv`

**Affected counts:** 1,600 spans with Phase-2 verified verdicts. Gold labels gate the speaker certification and thus the public-release path.

**What the system will do if approved:** The gold-label report is written with independent target/non-target counts, agreement rate, and a calibration threshold. The speaker-certification gate then clears if agreement meets the threshold.

**What the system will do if rejected / pending:** No gold-label report exists. Speaker certification stays pending. No verified speaker attribution is emitted.

**Safest default if uncertain:** **Keep pending** until annotator sheets are completed and an agreement rate is independently computed. Do not fabricate an agreement rate.

**Exact information required:**
- `approved: true` / `false` / `pending`
- `choice`: one of `approve_annotation_method` / `request_review` / `keep_pending`
- `reviewers`: list of annotator names
- `target_labels`: independently counted target-label count
- `non_target_labels`: independently counted non-target-label count
- `agreement_rate`: percentage (0-100) or `null` if not yet computed
- `calibration_threshold`: minimum agreement rate required (e.g. `80` for 80%)
- `gold_label_artifact_path`: path where the JSON report is written

**Expertise required:** Technical + human annotator review. Requires filling the CSV sheets and computing agreement. **Not** a clinical decision.

**Current gate result:** This gate is **blocked** (15 owner-blocked). The `test_missing_gold_label_reports_block_the_release` test asserts that absence of the gold-label report blocks the release.

---

## G. Staging/public authorization

**Decision name:** `b7_release_authorization`

**Why required:** This is the final gate that moves the system from `OWNER_ACTION_REQUIRED` toward `READY_FOR_STAGING_REVIEW`. It has six independent scopes, each a separate act with **no later approval implying any earlier one**:

| Scope | What it authorizes |
|---|---|
| `owner_only_testing` | Isolated local candidate collection; the owner-only preview mode |
| `isolated_local_candidate_collection` | The candidate collection lives in a separate Qdrant/Neo4j namespace; no spillover to served tier |
| `staging` | Staging environment deployment (not production) |
| `public_production` | Full public-release deployment to production |
| `alias_promotion` | Moving the `first_person` alias to a new collection |
| `harness_enablement` | Enabling `FIRST_PERSON_CONTEXT_HARNESS_ENABLED=true` |

**Exact evidence files and hashes:** No single hash — this decision is recorded in the owner action form and reflected in the gate config.

**Affected counts:** All prior decisions must be approved before this gate can pass. The gate counts are: 8 prereq passed, 16 failed, 15 owner-blocked, 1 engineering-blocked.

**What the system will do if each scope is approved:**
- `owner_only_testing` + `isolated_local_candidate_collection`: the owner-only preview continues to work in Docker; no change to served tier
- `staging`: a staging deployment is triggered (separate from production); seekers on the staging URL see the review-candidate experience with the two canonical label lines
- `public_production`: the public release is authorized (but still requires the staging-readiness review gate to pass first)
- `alias_promotion`: the `first_person` alias may be moved to a different collection (e.g. a v3 or public collection)
- `harness_enablement`: `FIRST_PERSON_CONTEXT_HARNESS_ENABLED=true` is set in `backend/.env` and the container is restarted

**What the system will do if rejected / pending:** All six scopes remain `pending`. The system stays in `OWNER_ACTION_REQUIRED` mode. No deployment, no alias change, no harness enablement.

**Safest default if uncertain:** **Approve only `owner_only_testing` + `isolated_local_candidate_collection`** — keeps the owner-only preview running without enabling any public or staging deployment. This is the minimal safe set.

**Exact information required:**
- `approved: true` / `false` / `pending`
- `scopes`: dict of `{scope_name: "true"}` for each approved scope
- `clinician_name` (optional but recommended for `public_production`): name of approving authority
- `decision_date_utc`: ISO-8601
- `signature`: confirming authority's signature

**Expertise required:** Multi-disciplinary — requires understanding of the dependency chain: owner testing → staging → public production → alias promotion → harness enablement. Each scope must be approved independently. **Not** a purely technical decision — the dependency ordering is a policy choice.

**Current gate result:** This gate is **blocked** (15 owner-blocked, 1 engineering-blocked). The engineering blocker is the missing `audits/evidence/public_release_candidate_config_2026-10-22.json` produced by the `isolated_local_candidate_collection` scope. Until that config artifact exists, the `b4_release_configuration` gate fails.

---

## Summary of current gate state

| Category | Count |
|---|---|
| Passed gates | 8 |
| Failed gates | 16 |
| Owner-blocked (pending decisions) | 15 |
| Engineering-blocked (missing artifacts/config) | 1 |
| Integrity violations | 0 |

The gate will remain `OWNER_ACTION_REQUIRED` until the 15 owner decisions are recorded in `audits/evidence/FIRST_PERSON_OWNER_DECISIONS_2026-10-22.md` with explicit `approved`/`reviewer`/`date`/`signature` fields. Even after all 15 owner-blocked gates clear, the 1 engineering-blocked gate (`b4_release_configuration — candidate release configuration names a legacy and a context collection that are not the same collection`) must be resolved by producing the `public_release_candidate_config_2026-10-22.json` artifact via the `isolated_local_candidate_collection` scope.

**No decision should be marked `approved: true` unless the owner can independently verify the evidence basis.** All seven areas keep `approved: pending` until explicit sign-off.

---

*This summary is read by the release-gate controller. Every `decision_id` maps to an `owner-decision` block in `audits/evidence/FIRST_PERSON_OWNER_DECISIONS_2026-10-22.md`. The controller checks that each block's `approved` field is not `pending` before considering that gate satisfied.*