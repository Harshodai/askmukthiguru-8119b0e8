#!/usr/bin/env python3
"""Build the deterministic quarantine/review package for contradictory speaker labels.

**Read-only.** No Qdrant client, no alias, no Redis, no env change, no
deployment. Files in, files out.

Why this exists
---------------
Phase 2 (per-span ECAPA) refused **45** candidate spans with
``reason_code="refused_guru_mismatch"``: the acoustic evidence says one teacher
and the corpus's per-video label says the other. Those 45 spans must never be
served, and the video/speaker/guru label must **not** be silently rewritten to
make the conflict disappear (that is how a mis-attribution becomes permanent
and invisible).

This script turns each conflict into a reviewable record:

* the exact source span id, video, expected teacher and ECAPA-predicted teacher;
* the cosine, the runner-up cosine and the margin, plus the floors those were
  measured against;
* the audio window and the sha256 of the audio file the slice came from;
* the model revision, the calibration revision and the run id, so the score
  can be reproduced;
* the transcript/source hashes, so the text cannot drift;
* a reason code and a **recommended** review action.

Duration fields (v2)
--------------------
Schema ``v1`` wrote the **slice** width (``end_ms - start_ms``) into a field
named ``audio_duration_ms``. The Phase-2 verdict uses that name for the
**complete WAV file** duration. The two numbers differ by orders of magnitude
(for example: slice ``10480`` ms vs file ``214692`` ms), and a human reviewer
reading the v1 packet would reasonably believe the window was near the end of
the file. That was misleading, so ``v1`` is superseded and ``v2`` names the two
durations explicitly:

``audio_file_duration_ms``
    Duration of the **complete** archived WAV the slice was cut from.
``audio_slice_duration_ms``
    Width of the **slice** actually quoted (``audio_end_ms - audio_start_ms``).
``audio_start_ms`` / ``audio_end_ms``
    The slice's own bounds inside the file.

The field ``audio_duration_ms`` is **removed** in v2 — it is never repurposed,
because a repurposed field would silently carry the other meaning for readers
of an old artifact. A v1 row and a v2 row are not interchangeable.

The recommended action is a *recommendation*, never an automatic decision. The
human approves or rejects each row; only an explicit, recorded human decision
may move a span out of quarantine.

Exit codes
----------
=====  ===================================================================
0      Package produced and no conflict exists (the corpus was already clean).
1      Package produced; conflicts exist and are quarantined. This is the
       ordinary, documented release-blocking status.
2      No trustworthy package could be produced: an input is unreadable or
       unparseable, or a verdict references a span that is not in the
       candidate. Fail closed.
=====  ===================================================================

Usage
-----
    python -m scripts.ops.build_fp_speaker_conflict_review \\
        --verdicts audits/evidence/public_release_phase2_verdicts_2026-10-22.json \\
        --candidate audits/evidence/public_release_phase3_candidate_2026-10-21.jsonl \\
        --out-jsonl audits/evidence/public_release_phase4_speaker_conflicts_2026-10-22.jsonl \\
        --out-review audits/evidence/public_release_phase4_speaker_conflict_review_2026-10-22.md \\
        --out-summary audits/evidence/public_release_phase4_speaker_conflict_summary_2026-10-22.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from collections import Counter
from pathlib import Path
from typing import Any

SCHEMA = "first-person-speaker-conflict-v2"
SUMMARY_SCHEMA = "first-person-speaker-conflict-summary-v2"
SCRIPT_VERSION = "build-fp-speaker-conflict-review-v2"

# The superseded schema and the field whose name was misleading in it.
SUPERSEDED_SCHEMA = "first-person-speaker-conflict-v1"
MISLEADING_FIELD = "audio_duration_ms"

MISMATCH_REASON = "refused_guru_mismatch"
CONFLICT_REASON_CODE = "speaker_label_conflict_acoustic_contradiction"

# Why the recommendation is what it is. The acoustic evidence alone cannot
# decide whether the CORPUS LABEL is wrong or the AUDIO WINDOW is wrong (a
# mis-sliced window can contain the other teacher). The human listens and
# decides; the package only makes the window audible and the evidence legible.
RECOMMENDED_ACTION = (
    "listen_to_window_and_decide: if the voice in the window is the ECAPA-predicted "
    "teacher, the CORPUS LABEL for this video is wrong -> reject the span and open a "
    "video-level relabel task; if the voice matches the expected teacher, the SLICE or "
    "the REFERENCE is wrong -> reject the span and open an audio/recalibration task. "
    "Do not relabel the video, the speaker or the guru from this table alone."
)


class SpeakerConflictError(RuntimeError):
    """Raised when no trustworthy conflict package can be produced."""


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for lineno, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise SpeakerConflictError(f"{path}:{lineno} is not valid JSON: {exc}") from exc
            if not isinstance(row, dict):
                raise SpeakerConflictError(f"{path}:{lineno} is not a JSON object")
            rows.append(row)
    return rows


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SpeakerConflictError(f"cannot read JSON from {path}: {exc}") from exc


def build_conflicts(
    verdicts: dict[str, Any],
    candidates: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """One deterministic row per refused_guru_mismatch span."""
    by_span = {str(row.get("source_span_id") or ""): row for row in candidates}
    conflicts: list[dict[str, Any]] = []
    for span_id in sorted(verdicts):
        verdict = verdicts[span_id]
        if not isinstance(verdict, dict):
            raise SpeakerConflictError(f"verdict for {span_id} is not an object")
        if verdict.get("reason_code") != MISMATCH_REASON:
            continue
        candidate = by_span.get(span_id)
        if candidate is None:
            raise SpeakerConflictError(
                f"verdict references a span that is not in the candidate: {span_id}"
            )
        expected = str(verdict.get("expected_guru") or "")
        predicted = str(verdict.get("predicted_guru") or "")
        start_ms = int(candidate.get("audio_start_ms") or 0)
        end_ms = int(candidate.get("audio_end_ms") or 0)
        video_id = str(candidate.get("video_id") or "")

        # Two distinct durations. The verdict's ``audio_duration_ms`` is the
        # COMPLETE WAV file; ``audio_slice_duration_ms`` is the quoted slice.
        # Never collapse them into one field.
        raw_file_duration = verdict.get("audio_duration_ms")
        file_duration = int(raw_file_duration) if raw_file_duration is not None else None
        raw_slice_duration = verdict.get("audio_slice_duration_ms")
        slice_duration = (
            int(raw_slice_duration) if raw_slice_duration is not None else end_ms - start_ms
        )
        if slice_duration != end_ms - start_ms:
            raise SpeakerConflictError(
                f"slice duration disagrees with the window for {span_id}: "
                f"{slice_duration} != {end_ms - start_ms}"
            )
        conflicts.append(
            {
                "schema": SCHEMA,
                "script_version": SCRIPT_VERSION,
                "source_span_id": span_id,
                "video_id": video_id,
                "source_asset_id": str(candidate.get("source_asset_id") or video_id),
                "expected_guru": expected,
                "predicted_guru": predicted,
                "corpus_teacher_label": str(candidate.get("guru_id") or ""),
                "conflict_direction": f"{expected}->{predicted}",
                "cosine": verdict.get("cosine"),
                "runner_up_cosine": verdict.get("runner_up_cosine"),
                "margin": verdict.get("margin"),
                "cosine_floor": verdict.get("cosine_floor"),
                "margin_threshold": verdict.get("margin_threshold"),
                "audio_start_ms": start_ms,
                "audio_end_ms": end_ms,
                # v2: the slice width.
                "audio_slice_duration_ms": slice_duration,
                # v2: the complete archived WAV the slice was cut from.
                "audio_file_duration_ms": file_duration,
                "audio_file_duration_available": file_duration is not None,
                "audio_file_duration_source": (
                    "phase2_verdict.audio_duration_ms (complete WAV file duration)"
                    if file_duration is not None
                    else "unavailable_in_phase2_verdict"
                ),
                "audio_path": str(verdict.get("audio_path") or ""),
                "audio_sha256": str(verdict.get("audio_sha256") or ""),
                "audio_sample_rate": verdict.get("audio_sample_rate"),
                "speaker_model": str(verdict.get("speaker_model") or ""),
                "speaker_model_revision": str(verdict.get("speaker_model_revision") or ""),
                "calibration_revision": str(verdict.get("calibration_revision") or ""),
                "run_id": str(verdict.get("run_id") or ""),
                "split": str(verdict.get("split") or ""),
                "transcript_hash": str(verdict.get("transcript_hash") or ""),
                "source_text_hash": str(verdict.get("source_text_hash") or ""),
                "corpus_version": str(candidate.get("corpus_version") or ""),
                "normalization_version": str(candidate.get("normalization_version") or ""),
                "word_start": candidate.get("word_start"),
                "word_end": candidate.get("word_end"),
                "text": str(candidate.get("reconstructed_text") or ""),
                "reason_code": CONFLICT_REASON_CODE,
                "phase2_reason_code": MISMATCH_REASON,
                "quarantined": True,
                "recommended_review_action": RECOMMENDED_ACTION,
                "review_decision": "",  # filled in by the human reviewer
                "reviewer": "",
                "reviewed_at_utc": "",
                "playback": {
                    "archived_wav": str(verdict.get("audio_path") or ""),
                    "archived_wav_sha256": str(verdict.get("audio_sha256") or ""),
                    "start_ms": start_ms,
                    "end_ms": end_ms,
                    "start_seconds": round(start_ms / 1000.0, 3),
                    "end_seconds": round(end_ms / 1000.0, 3),
                    "slice_duration_ms": slice_duration,
                    "file_duration_ms": file_duration,
                    "youtube_url": (
                        f"https://www.youtube.com/watch?v={video_id}"
                        f"&t={int(start_ms / 1000)}s"
                    ),
                },
            }
        )
    return conflicts


def bounds_report(conflicts: list[dict[str, Any]]) -> dict[str, Any]:
    """Prove the slice windows sit inside the complete archived WAV.

    ``out_of_bounds`` counts a row whose ``audio_end_ms`` is past the end of
    the file, or whose slice width does not equal ``end_ms - start_ms``.
    Rows with no measured file duration cannot be bounds-checked and are
    reported separately — they are never silently counted as "in bounds".
    """
    checked = 0
    unchecked = 0
    out_of_bounds: list[str] = []
    for conflict in conflicts:
        file_duration = conflict.get("audio_file_duration_ms")
        if file_duration is None:
            unchecked += 1
            continue
        checked += 1
        end_ms = int(conflict.get("audio_end_ms") or 0)
        start_ms = int(conflict.get("audio_start_ms") or 0)
        slice_ms = int(conflict.get("audio_slice_duration_ms") or 0)
        if end_ms > int(file_duration) or slice_ms != end_ms - start_ms or start_ms < 0:
            out_of_bounds.append(str(conflict.get("source_span_id") or ""))
    return {
        "rows": len(conflicts),
        "bounds_checked_rows": checked,
        "bounds_unchecked_rows": unchecked,
        "out_of_bounds_count": len(out_of_bounds),
        "out_of_bounds_source_span_ids": out_of_bounds,
        "all_checked_windows_within_file": not out_of_bounds,
    }


def render_review(
    conflicts: list[dict[str, Any]],
    meta: dict[str, Any],
    bounds: dict[str, Any],
) -> str:
    lines: list[str] = []
    lines.append("# Speaker-label conflict review package — 45 quarantined spans")
    lines.append("")
    lines.append(
        "**This is a review queue, not a report of resolved facts.** Every row below is "
        "quarantined: it is excluded from the owner-only test tier and from any serving "
        "candidate until a human records a decision."
    )
    lines.append("")
    lines.append("## How to review one row")
    lines.append("")
    lines.append("1. Open the archived WAV listed in the row "
                 "(`archived_wav`) and jump to `start_seconds`–`end_seconds`.")
    lines.append("   The sha256 in the row must match the file you open.")
    lines.append("2. Optionally cross-check with the YouTube URL in the same row "
                 "(`youtube_url`), which starts at the same offset.")
    lines.append("3. Listen. Decide which of the two claims is wrong:")
    lines.append("   - the **corpus label** for that video (the video is filed under the "
                 "wrong teacher), or")
    lines.append("   - the **slice/reference** (the window does not contain the teacher it "
                 "claims, or the reference voiceprint does not cover this speaker).")
    lines.append("4. Record the decision **in this file** by filling the `review_decision`, "
                 "`reviewer` and `reviewed_at_utc` fields of the matching JSONL row "
                 "(or the markdown table below).")
    lines.append("5. A rejected span stays quarantined. An approved *relabel* opens a "
                 "video-level relabel task; it does **not** by itself admit the span to a "
                 "serving tier.")
    lines.append("")
    lines.append("**Do not** rewrite the video label, the speaker or the guru from this "
                 "table. A silent relabel is how a mis-attribution becomes permanent.")
    lines.append("")
    lines.append("## Evidence legend")
    lines.append("")
    lines.append("| Field | Meaning |")
    lines.append("|---|---|")
    lines.append("| `expected_guru` | The corpus's per-video teacher label. A **claim**, "
                 "never evidence. |")
    lines.append("| `predicted_guru` | Which teacher the ECAPA reference centroid matched. "
                 "Derived from the pinned model. |")
    lines.append("| `cosine` / `runner_up_cosine` / `margin` | Score against the predicted "
                 "and the runner-up reference. |")
    lines.append("| `cosine_floor` / `margin_threshold` | The impostor-calibrated floors "
                 "the score was measured against. |")
    lines.append("| `audio_sha256` | Identity of the archived WAV the slice came from. |")
    lines.append("| `speaker_model_revision` | Pinned SpeechBrain ECAPA revision. |")
    lines.append("| `calibration_revision` | Pinned calibration record. |")
    lines.append("| `source_text_hash` | sha256 of the span text; pins the quoted text. |")
    lines.append("| `audio_file_duration_ms` | Duration of the **complete** archived WAV. |")
    lines.append("| `audio_slice_duration_ms` | Width of the **quoted slice** "
                 "(`audio_end_ms - audio_start_ms`). |")
    lines.append("")
    lines.append("## Correction to the previous packet (schema v1 → v2)")
    lines.append("")
    lines.append(
        "**The previous packet was misleading and has been corrected.** Schema "
        f"`{SUPERSEDED_SCHEMA}` wrote the *slice* width (`audio_end_ms - audio_start_ms`) "
        f"into a field named `{MISLEADING_FIELD}`. In the Phase-2 verdict that field name "
        "means the duration of the **complete WAV file**. The two numbers are different "
        "quantities and differ by orders of magnitude (example: slice `10480` ms vs file "
        "`214692` ms), so a reviewer reading the v1 packet could reasonably believe the "
        "window sat near the end of the recording. It did not."
    )
    lines.append("")
    lines.append(
        f"Schema `{SCHEMA}` removes `{MISLEADING_FIELD}` entirely and states both "
        "durations explicitly: `audio_file_duration_ms` (the whole file) and "
        "`audio_slice_duration_ms` (the quoted slice), alongside `audio_start_ms` and "
        "`audio_end_ms`. The field is **removed, not repurposed**: a repurposed field "
        "would silently carry the other meaning for anyone reading an old artifact. A v1 "
        "row and a v2 row are not interchangeable."
    )
    lines.append("")
    lines.append("**Bounds check.** Every window is checked against the complete file:")
    lines.append("")
    lines.append(
        f"- rows bounds-checked against a measured file duration: "
        f"**{bounds['bounds_checked_rows']}**"
    )
    lines.append(
        f"- rows with no measured file duration (not counted as in-bounds): "
        f"**{bounds['bounds_unchecked_rows']}**"
    )
    lines.append(
        f"- windows outside the file, or whose slice width disagrees with the window: "
        f"**{bounds['out_of_bounds_count']}**"
    )
    lines.append("")
    lines.append("## Aggregate")
    lines.append("")
    lines.append(f"- Conflicts: **{len(conflicts)}**")
    directions = Counter(c["conflict_direction"] for c in conflicts)
    for direction, count in sorted(directions.items()):
        lines.append(f"- `{direction}`: **{count}**")
    lines.append(f"- Distinct videos: **{len({c['video_id'] for c in conflicts})}**")
    lines.append(f"- Model: `{meta['speaker_model']}` @ `{meta['speaker_model_revision']}`")
    lines.append(f"- Calibration revision: `{meta['calibration_revision']}`")
    lines.append(f"- Run id: `{meta['run_id']}`")
    lines.append(
        f"- Audio windows outside the complete file: **{bounds['out_of_bounds_count']} / "
        f"{len(conflicts)}**"
    )
    lines.append("")
    lines.append("## Rows")
    lines.append("")
    lines.append(
        "| # | span id (short) | video | expected | predicted | cosine | margin | "
        "audio window (s) | slice (ms) | file (ms) | decision | reviewer |"
    )
    lines.append("|---:|---|---|---|---|---:|---:|---|---:|---:|---|---|")
    for index, conflict in enumerate(conflicts, start=1):
        playback = conflict["playback"]
        lines.append(
            "| {n} | `{sid}` | `{vid}` | {exp} | {pred} | {cos} | {mar} | "
            "{start}–{end} | {slice} | {file} | {decision} | {reviewer} |".format(
                n=index,
                sid=conflict["source_span_id"][:16],
                vid=conflict["video_id"],
                exp=conflict["expected_guru"],
                pred=conflict["predicted_guru"],
                cos=conflict["cosine"],
                mar=conflict["margin"],
                start=playback["start_seconds"],
                end=playback["end_seconds"],
                slice=conflict["audio_slice_duration_ms"],
                file=conflict["audio_file_duration_ms"],
                decision=conflict["review_decision"] or "_(pending)_",
                reviewer=conflict["reviewer"] or "_",
            )
        )
    lines.append("")
    lines.append("## Per-row detail")
    lines.append("")
    for index, conflict in enumerate(conflicts, start=1):
        playback = conflict["playback"]
        lines.append(f"### {index}. `{conflict['source_span_id']}`")
        lines.append("")
        lines.append(f"- Video: `{conflict['video_id']}`")
        lines.append(
            f"- Corpus label (expected): **{conflict['expected_guru']}** · "
            f"ECAPA predicted: **{conflict['predicted_guru']}** "
            f"(direction `{conflict['conflict_direction']}`)"
        )
        lines.append(
            f"- Score: cosine `{conflict['cosine']}`, runner-up "
            f"`{conflict['runner_up_cosine']}`, margin `{conflict['margin']}` "
            f"(floor `{conflict['cosine_floor']}`, margin threshold "
            f"`{conflict['margin_threshold']}`)"
        )
        lines.append(
            f"- Audio window: `{conflict['audio_start_ms']}`–`{conflict['audio_end_ms']}` ms "
            f"({playback['start_seconds']}–{playback['end_seconds']} s)"
        )
        lines.append(
            f"- **Slice duration (quoted window): "
            f"`{conflict['audio_slice_duration_ms']}` ms**"
        )
        lines.append(
            f"- **Complete file duration: `{conflict['audio_file_duration_ms']}` ms** "
            f"(source: {conflict['audio_file_duration_source']})"
        )
        lines.append(f"- Archived WAV: `{playback['archived_wav']}`")
        lines.append(f"- WAV sha256: `{conflict['audio_sha256']}`")
        lines.append(f"- YouTube: {playback['youtube_url']}")
        lines.append(
            f"- Model: `{conflict['speaker_model']}` @ `{conflict['speaker_model_revision']}`"
        )
        lines.append(f"- Calibration revision: `{conflict['calibration_revision']}`")
        lines.append(f"- Run id: `{conflict['run_id']}`")
        lines.append(f"- Transcript hash: `{conflict['transcript_hash']}`")
        lines.append(f"- Source text hash: `{conflict['source_text_hash']}`")
        lines.append(f"- Corpus version: `{conflict['corpus_version']}`")
        lines.append(
            f"- Words: `{conflict['word_start']}`–`{conflict['word_end']}` "
            f"(normalization `{conflict['normalization_version']}`)"
        )
        lines.append(f"- Reason code: `{conflict['reason_code']}`")
        lines.append(f"- Text: > {conflict['text']}")
        lines.append(f"- Recommended action: {conflict['recommended_review_action']}")
        lines.append(
            f"- Decision: {conflict['review_decision'] or '_(pending)_'} "
            f"— reviewer: {conflict['reviewer'] or '_'} — "
            f"at: {conflict['reviewed_at_utc'] or '_'}"
        )
        lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--verdicts", required=True)
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--out-jsonl", required=True)
    parser.add_argument("--out-review", required=True)
    parser.add_argument("--out-summary", required=True)
    parser.add_argument(
        "--supersedes-jsonl",
        default=None,
        help="path of the superseded v1 JSONL artifact (retained, hashed, never overwritten)",
    )
    parser.add_argument(
        "--supersedes-review",
        default=None,
        help="path of the superseded v1 markdown review artifact (retained, hashed)",
    )
    parser.add_argument(
        "--generated-at-utc",
        default=os.environ.get("FP_CONFLICT_GENERATED_AT_UTC", ""),
        help="pinned timestamp for byte-identical repeats",
    )
    args = parser.parse_args(argv)

    try:
        verdict_doc = _read_json(Path(args.verdicts))
        if not isinstance(verdict_doc, dict) or not isinstance(
            verdict_doc.get("verdicts"), dict
        ):
            raise SpeakerConflictError("verdict manifest has no 'verdicts' object")
        candidates = _read_jsonl(Path(args.candidate))
        conflicts = build_conflicts(verdict_doc["verdicts"], candidates)
    except SpeakerConflictError as exc:
        print(f"[fp-conflicts] ERROR: {exc}", file=sys.stderr)
        return 2

    bounds = bounds_report(conflicts)

    meta = {
        "speaker_model": verdict_doc.get("verdicts", {}).get("", {}) and "",
        "calibration_revision": str(verdict_doc.get("calibration_revision") or ""),
        "run_id": str(verdict_doc.get("run_id") or ""),
    }
    for conflict in conflicts:
        meta["speaker_model"] = conflict["speaker_model"]
        meta["speaker_model_revision"] = conflict["speaker_model_revision"]
        break

    superseded: dict[str, Any] = {}
    for label, raw in (
        ("jsonl", args.supersedes_jsonl),
        ("review", args.supersedes_review),
    ):
        if not raw:
            continue
        path = Path(raw)
        if not path.is_file():
            print(f"[fp-conflicts] ERROR: superseded artifact is missing: {path}", file=sys.stderr)
            return 2
        superseded[label] = {"path": str(path), "sha256": _sha256_file(path)}

    summary = {
        "schema": SUMMARY_SCHEMA,
        "script_version": SCRIPT_VERSION,
        "generated_at_utc": args.generated_at_utc,
        "conflict_count": len(conflicts),
        "conflict_direction_counts": dict(
            sorted(Counter(c["conflict_direction"] for c in conflicts).items())
        ),
        "video_count": len({c["video_id"] for c in conflicts}),
        "video_span_counts": dict(
            sorted(Counter(c["video_id"] for c in conflicts).items())
        ),
        "speaker_model": meta.get("speaker_model", ""),
        "speaker_model_revision": meta.get("speaker_model_revision", ""),
        "calibration_revision": meta["calibration_revision"],
        "run_id": meta["run_id"],
        "all_quarantined": all(c["quarantined"] for c in conflicts),
        "release_blocking": bool(conflicts),
        "duration_fields": {
            "audio_file_duration_ms": "duration of the complete archived WAV",
            "audio_slice_duration_ms": "width of the quoted slice (end_ms - start_ms)",
            "audio_start_ms": "slice start inside the file",
            "audio_end_ms": "slice end inside the file",
            "removed_field": MISLEADING_FIELD,
        },
        "bounds": bounds,
        "schema_migration": {
            "from_schema": SUPERSEDED_SCHEMA,
            "to_schema": SCHEMA,
            "reason": (
                "v1 wrote the slice width into a field named 'audio_duration_ms', the "
                "same name the Phase-2 verdict uses for the complete WAV file duration. "
                "The two quantities are different and differ by orders of magnitude."
            ),
            "removed_field": MISLEADING_FIELD,
            "removed_field_never_repurposed": True,
            "compatibility": (
                "v1 and v2 rows are NOT interchangeable. A v1 row's 'audio_duration_ms' "
                "equals the v2 row's 'audio_slice_duration_ms'."
            ),
            "superseded_artifacts": superseded,
            "superseded_artifacts_retained": bool(superseded),
        },
        "inputs": {
            "verdicts": {"path": args.verdicts, "sha256": _sha256_file(Path(args.verdicts))},
            "candidate": {
                "path": args.candidate,
                "sha256": _sha256_file(Path(args.candidate)),
            },
        },
    }

    out_jsonl = Path(args.out_jsonl)
    out_jsonl.parent.mkdir(parents=True, exist_ok=True)
    with out_jsonl.open("w", encoding="utf-8") as handle:
        for conflict in conflicts:
            handle.write(json.dumps(conflict, sort_keys=True, ensure_ascii=False) + "\n")

    out_review = Path(args.out_review)
    out_review.parent.mkdir(parents=True, exist_ok=True)
    out_review.write_text(render_review(conflicts, summary, bounds), encoding="utf-8")

    out_summary = Path(args.out_summary)
    out_summary.parent.mkdir(parents=True, exist_ok=True)
    out_summary.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    print(
        f"[fp-conflicts] conflicts={len(conflicts)} videos={summary['video_count']} "
        f"directions={summary['conflict_direction_counts']}"
    )
    print(
        f"[fp-conflicts] bounds out_of_bounds={bounds['out_of_bounds_count']}"
        f"/{len(conflicts)} checked={bounds['bounds_checked_rows']}"
        f" unchecked={bounds['bounds_unchecked_rows']}"
    )
    return 1 if conflicts else 0


if __name__ == "__main__":
    raise SystemExit(main())
