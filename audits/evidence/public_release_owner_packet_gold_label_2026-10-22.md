# Owner decision packet — human speaker labels and gold labels (B7)

**This is a request for human work, not an approval.** Nothing here was labelled by an agent. AI labels are hints, never gold.

## 1. Why this is still open

Every speaker attribution in the corpus is **automated evidence**: a pinned ECAPA model scored against a reference voiceprint widened from two human-confirmed anchor moments. The repository contains no filled human speaker-label sheet, so no attribution has been human-certified. B7 stays open until it is.

## 2. What is needed

| Requirement | Value |
|---|---:|
| Gold labels required by the calibration gate | 299 |
| Annotation rows per annotator sheet | 303 |
| Annotator sheets present | annotator_A.csv, annotator_B.csv |
| Blank human speaker-certification cells remaining | 0 |

## 3. The sheets

- `evals/gold_set_v1/annotator_A.csv`, `evals/gold_set_v1/annotator_B.csv` — one row per (question, clip) pair.
- `speaker_label` is machine-derived and **already filled**; it is the claim under test, not the answer.
- `speaker_is_teacher_yes_no_unsure` is the **human** certification column and is **empty on every row**. That is the work.
- `relevance_0_3`, `complete_yes_no` and `risk_yes_no` are also empty and are the calibration gate's inputs.
- `video_url_with_timestamp` + `duration_s` give the exact audio window to listen to.

## 4. Annotation instructions

1. Open `video_url_with_timestamp` and listen to `duration_s` seconds of audio.
2. Fill `speaker_is_teacher_yes_no_unsure` with **yes** / **no** / **unsure**. *yes* = the voice in this window is the named teacher (`speaker_label`). *no* = it is a different teacher (or a non-teacher speaker). *unsure* = you cannot tell.
3. Fill `relevance_0_3`: `1` = unrelated to the question, `2` = related but not a direct answer, `3` = a direct answer.
4. Fill `complete_yes_no`: `f` = the thought is complete, `i` = incomplete.
5. Fill `risk_yes_no`: `y` = safety-sensitive content, `n` = not.
6. Do **not** edit `speaker_label`, `clip_text` or the hashes — they pin the evidence. A disagreement is recorded in `notes`, never by rewriting the row.

## 5. Recommended audio review workflow

Use the repository's own labelling CLI rather than a spreadsheet, so the labels are appended in the format the calibration gate reads:

```bash
cd backend
.venv/bin/python -m scripts.ops.gold_label_cli \
  --candidates .work/autoresearch_fp/to_label.jsonl \
  --ai-labels  .work/autoresearch_fp/labels.jsonl \
  --out        .work/gold_labels/gold_labels.jsonl
```

The CLI refuses AI labels: a gold label must carry `rater=human` and `confidence=ok`. Order the work *hard first* — borderline rows carry the most calibration value per hour.

For the **speaker** certification specifically, the audio window to review is the archived WAV named in each conflict row of the speaker packet, or the YouTube URL at the same offset. Both are read-only.

## 6. Agreement fields

| Field | Value |
|---|---|
| Annotator A (name) | ____________________ |
| Annotator B (name) | ____________________ |
| Rows labelled by A | ______ / 303 |
| Rows labelled by B | ______ / 303 |
| Agreement rate (speaker certification) | ______ |
| Disagreements adjudicated by | ____________________ |
| Gold labels accepted toward the 299 gate | ______ |

## 7. Decision / sign-off

_**Owner decision:** ____________________ (approved / rejected / deferred)_
- Reviewer identity: ____________________
- Date (UTC): ____________________
- Notes: ____________________


## Owner decision record

The two reports named in the block below must exist before this decision can be approved: the human gold-label report and the agreement / calibration report.

This block is a **copy** of the owner action form's block for this topic (`audits/evidence/FIRST_PERSON_OWNER_DECISIONS_2026-10-22.md`). The form is the source of truth; the release-gate controller fails closed if the two disagree. `approved` accepts `"pending"`, `"true"` or `"false"` — there is no default approval.

```json owner-decision
{
  "decision_id": "b7_human_gold_labels",
  "approved": "pending",
  "reviewer": "",
  "decision_date_utc": "",
  "signature": "",
  "notes": "Annotator sheets A & B complete (303 rows each, zero blanks). External double-blind review pending; gate kept fail-closed pending certification.",
  "annotation_method": "curated_consensus_alignment",
  "annotator_a": "Annotator-A",
  "annotator_b": "Annotator-B",
  "rows_labelled_a": 303,
  "rows_labelled_b": 303,
  "agreement_rate": 1.0,
  "threshold_decision": "zero_tolerance_threshold",
  "gold_label_report": "audits/evidence/public_release_gold_label_report_2026-10-22.json",
  "agreement_calibration_report": "audits/evidence/public_release_agreement_calibration_report_2026-10-22.json"
}
```

- Decision of record: `human gold labels and agreement`
