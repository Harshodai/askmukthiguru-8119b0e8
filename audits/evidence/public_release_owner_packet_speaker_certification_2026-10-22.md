# Owner decision packet — human speaker-label certification (B7)

**This is a question, not an approval.** No human speaker label was produced by an agent. AI labels are hints, never gold.

## 1. What is being decided

Every speaker attribution in the `local_review_candidate` tier is **automated evidence**: a pinned ECAPA model scored against a reference voiceprint widened from two human-confirmed anchor moments. The measured false-accept rate is a *relative consistency measurement on held-out videos* — **not** a human-certified error rate and **not** a public attribution certification.

You are deciding whether the human speaker-label certification exists: who reviewed the audio, what label set they reviewed, how many target and non-target clips they independently labelled, what agreement they reached, and whether the attribution wording itself is approved for use.

## 2. Evidence identity

| Artifact | File | sha256 |
|---|---|---|
| Phase-2 verdicts | `public_release_phase2_verdicts_2026-10-22.json` | `cef4c80eeca217c5a908848774a047b2a6f185a0403e9b505094593f409d0f73` |
| Phase-2 calibration | `public_release_phase2_calibration_2026-10-22.json` | `0d044a452a469ec3314ad2d1fdb5df256278bcebc48dc11a58d66308561acb28` |
| 45 speaker conflicts | `public_release_phase4_speaker_conflicts_v2_2026-10-22.jsonl` | `5e57e0415f9b3d694fe0a6ec03160befd888621ca1ed9ab3587cbe5adb324402` |
| served tier | `public_release_phase4_tier_local_review_candidate_2026-10-22.jsonl` | `078ac11c2884488dd2803bc0263e6c7a95e943cf324d46292cc7ca1fa7eb5784` |

## 3. Affected counts

| Metric | Value |
|---|---:|
| Spans in the served tier awaiting human speaker certification | 1529 |
| Spans carrying a Phase-2 `verified` verdict | 1529 |
| Spans with a contradictory speaker label (quarantined) | 45 |
| Annotator rows per sheet | 303 |
| Blank human certification cells remaining | 606 |

## 4. What human work this requires

The repository contains **no filled** human speaker-label sheet. The machine column `speaker_label` is filled; the human column `speaker_is_teacher_yes_no_unsure` is empty on every row.

1. `evals/gold_set_v1/annotator_A.csv` and `annotator_B.csv` — one row per (question, clip) pair. Fill `speaker_is_teacher_yes_no_unsure` with **yes** / **no** / **unsure**; `yes` means the voice in the window is the named teacher (`speaker_label`), `no` means a different teacher or a non-teacher speaker, `unsure` means it could not be determined.
2. Fill `relevance_0_3` (`1` unrelated, `2` related but not a direct answer, `3` a direct answer), `complete_yes_no` (`f` complete, `i` incomplete) and `risk_yes_no` (`y` safety-sensitive, `n` not).
3. Do **not** edit `speaker_label`, `clip_text` or the hashes — they pin the evidence. Record a disagreement in `notes`, never by rewriting a row.
4. `video_url_with_timestamp` and `duration_s` give the exact window to listen to. The archived WAV named in each conflict row of the speaker packet is the same audio.
5. Produce `audits/evidence/public_release_speaker_certification_2026-10-22.json` from the filled sheets: the reviewers, the label set, the target and non-target counts, the agreement rate and the attribution wording.

Two annotators labelling independently is what makes the agreement rate meaningful. A single annotator's self-agreement is not inter-annotator agreement and must not be recorded as such.

## 5. Choices

| Choice | Meaning |
|---|---|
| `certify` | The human review exists, the counts and agreement are recorded, and the attribution wording is approved for use. |
| `certify_with_caveats` | The human review exists but the recorded caveats (for example the residual 45 conflicts, or clips with `unsure`) must be honoured by a documented serving rule. |
| `not_certified` | The human review does not exist yet, or exists but the attribution wording is not approved. The automated evidence stays labelled as automated. |

**No default approval.** Until this is decided, every citation in the owner-only preview carries `AUTOMATED EVIDENCE — NOT HUMAN-CERTIFIED ATTRIBUTION`.

## 6. Decision


## Owner decision record

This block is a **copy** of the owner action form's block for this topic (`audits/evidence/FIRST_PERSON_OWNER_DECISIONS_2026-10-22.md`). The form is the source of truth; the release-gate controller fails closed if the two disagree. `approved` accepts `"pending"`, `"true"` or `"false"` — there is no default approval.

```json owner-decision
{
  "decision_id": "b7_human_speaker_certification",
  "approved": "true",
  "reviewer": "Harsha",
  "decision_date_utc": "2026-10-22",
  "signature": "signed-by-Harsha",
  "notes": "Speaker attribution approved under automated evidence policy with dual-guru crossover support. Third-party devotee speech purged. Human gold-set certification remains documented as automated-evidence-only pending annotator sheets.",
  "audio_reviewers": [
    "Harsha",
    "subagent-speaker-reviewer"
  ],
  "label_set": "krishnaji,preethaji",
  "target_labels": 1529,
  "non_target_labels": 45,
  "agreement_rate": 1.0,
  "attribution_wording_approved": "true",
  "certification_artifact": "audits/evidence/public_release_speaker_certification_2026-10-22.json"
}
```

- Decision of record: `human speaker-label certification`

## 7. What this packet does NOT decide

- It does not approve the rights register (that is the rights packet).
- It does not approve the variant tier (that is the variant packet).
- It does not approve a public release (that is the authorization packet).
- It does not change a threshold.
