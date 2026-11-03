#!/usr/bin/env python3
"""Build host / interviewer impostor slices from saved diarization windows (P7).

The calibration's false-accept evidence is only as strong as its impostor set. Today the
impostors are one teacher scored against the other teacher's reference (262 held-out trials,
0 false accepts, a 95% upper bound near 1.1%). The voices that actually sit next to a
teacher in our videos, the host and the interviewer, are not in it. This script finds
stretches of those voices in the diarization output that already exists
(``<video_id>_speaker.json``, written by ``ingest/verbatim/speaker_verify.py``) and writes
them as slices for ``regenerate_v10_span_ecapa_verdicts.py --foreign-slices-jsonl``.

Read-only: reads JSON, writes one JSONL and one summary. No audio, no Qdrant, no network.

How a slice is chosen
---------------------
* A run of consecutive windows all named ``O`` (neither teacher's voiceprint). Diarization
  cannot tell host from interviewer from audience, so the label is ``other``.
* Window ``i`` covers ``[t_i, t_i + WIN_S]`` and neighbours overlap. The first and last ``O``
  window of a run overlap a non-``O`` neighbour, so the slice runs **centre to centre**:
  ``[centre_first, centre_last]``. That excludes every neighbour's audio.
* A run shorter than ``--min-s`` (default 3.0) is dropped; a longer one is cut into
  ``--max-s`` (default 12.0) pieces; at most ``--max-per-video`` slices per video are kept,
  evenly spaced, so one talkative host cannot dominate the set. Slices of one video are not
  independent trials; the cap limits how much a single voice can count.

What this does not prove
------------------------
An ``O`` cluster is "not matched to a teacher voiceprint", not "confirmed host". If a
teacher is mis-named ``O`` the slice only adds false accepts, which fails safe (a higher
bound, never a lower one). The real trial count after embedding is in the calibration
artifact (``trial_counts.foreign_voice_*``); this file's counts are candidates only.

Usage
-----
    python -m scripts.ops.build_impostor_slices \\
        --speaker-dir <dir with *_speaker.json> --out impostor_slices.jsonl \\
        --summary impostor_slices_summary.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

WIN_S = 2.0  # mirrors scripts.ops.speaker_attribution.WIN_S; not imported to stay torch-free
SCHEMA = "first-person-impostor-slices-v1"
OTHER_LABEL = "O"

EXIT_OK = 0
EXIT_INVALID_INPUT = 2


def other_runs(
    t_centres: list[float], win_lab: list[str], hop_s: float = 1.0
) -> list[tuple[float, float]]:
    """``(first_centre, last_centre)`` seconds for each run of consecutive ``O`` windows."""
    runs: list[tuple[float, float]] = []
    start: float | None = None
    last: float | None = None
    for centre, label in zip(t_centres, win_lab, strict=False):
        contiguous = last is not None and (centre - last) <= hop_s * 1.5
        if label == OTHER_LABEL and (start is None or contiguous):
            if start is None:
                start = centre
            last = centre
            continue
        if start is not None and last is not None:
            runs.append((start, last))
        if label == OTHER_LABEL:
            start = last = centre
        else:
            start = last = None
    if start is not None and last is not None:
        runs.append((start, last))
    return runs


def slices_for_video(
    video_id: str,
    speaker: dict[str, Any],
    *,
    min_s: float = 3.0,
    max_s: float = 12.0,
    max_per_video: int = 20,
    hop_s: float = 1.0,
) -> list[dict[str, Any]]:
    """Impostor slice rows for one video. Fails closed: a bad file yields no slices."""
    if not isinstance(speaker, dict) or speaker.get("ok") is not True:
        return []
    centres = speaker.get("t_centres")
    labels = speaker.get("win_lab")
    if not isinstance(centres, list) or not isinstance(labels, list) or len(centres) != len(labels):
        return []
    pieces: list[tuple[int, int]] = []
    for first, last in other_runs([float(c) for c in centres], [str(x) for x in labels], hop_s):
        cursor = first
        while last - cursor >= min_s:
            end = min(cursor + max_s, last)
            if end - cursor < min_s:
                break
            pieces.append((int(round(cursor * 1000)), int(round(end * 1000))))
            cursor = end
    if len(pieces) > max_per_video > 0:
        step = len(pieces) / max_per_video
        pieces = [pieces[int(i * step)] for i in range(max_per_video)]
    return [
        {
            "slice_id": f"{video_id}:{start}-{end}",
            "video_id": video_id,
            "start_ms": start,
            "end_ms": end,
            "label": "other",
            "source": "diarization_O_windows_centre_to_centre",
        }
        for start, end in pieces
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--speaker-dir", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--summary", default=None)
    parser.add_argument("--min-s", type=float, default=3.0)
    parser.add_argument("--max-s", type=float, default=12.0)
    parser.add_argument("--max-per-video", type=int, default=20)
    parser.add_argument("--hop-s", type=float, default=1.0)
    args = parser.parse_args(argv)

    speaker_dir = Path(args.speaker_dir).expanduser()
    files = sorted(speaker_dir.glob("*_speaker.json"))
    if not files:
        print(
            json.dumps({"status": "invalid_input", "error": f"no *_speaker.json in {speaker_dir}"}),
            file=sys.stderr,
        )
        return EXIT_INVALID_INPUT

    rows: list[dict[str, Any]] = []
    unreadable: list[str] = []
    per_video: dict[str, int] = {}
    for path in files:
        video_id = path.name[: -len("_speaker.json")]
        try:
            speaker = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            unreadable.append(video_id)
            continue
        found = slices_for_video(
            video_id,
            speaker,
            min_s=args.min_s,
            max_s=args.max_s,
            max_per_video=args.max_per_video,
            hop_s=args.hop_s,
        )
        if found:
            per_video[video_id] = len(found)
        rows.extend(found)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8"
    )
    summary = {
        "schema": SCHEMA,
        "speaker_files": len(files),
        "unreadable_files": unreadable,
        "videos_with_slices": len(per_video),
        "candidate_slices": len(rows),
        "slices_per_video": dict(sorted(per_video.items())),
        "parameters": {
            "min_s": args.min_s,
            "max_s": args.max_s,
            "max_per_video": args.max_per_video,
            "hop_s": args.hop_s,
        },
        "note": (
            "candidates only; the usable trial count (after embedding and the video-disjoint "
            "split) is trial_counts.foreign_voice_* in the calibration artifact. Each slice "
            "yields one impostor trial per teacher."
        ),
    }
    if args.summary:
        Path(args.summary).parent.mkdir(parents=True, exist_ok=True)
        Path(args.summary).write_text(
            json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
