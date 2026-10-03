#!/usr/bin/env python3
"""CLI: build sentence-bounded v2 clips from labelled transcripts.

Reads `<dir>/transcripts_B/<video_id>.json` (word list with per-word speaker
labels; see `services.speaker_diarization.build_clips_from_labelled_words`)
and writes `<dir>/passages_C/<video_id>.json` -- never `passages_B`, which is
the older, fragment-prone offline builder's output and must not be touched.

Usage
-----
    .venv/bin/python scripts/ops/build_clips_v2.py \\
        --dir ~/mukthiguru_attribution_data/bakeoff_2026-09-25 \\
        --dir ~/mukthiguru_attribution_data/pilot50_2026-09-25
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Optional

_BACKEND = Path(__file__).resolve().parents[2]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from services.speaker_diarization import build_clips_from_labelled_words  # noqa: E402

_STATS_KEYS = (
    "runs",
    "clips",
    "dropped_short",
    "merged_unknown_gaps",
    "cut_at_sentence",
    "cut_at_pause",
    "dropped_mid_sentence_at_flip",
)


def _percentile(sorted_values: list[int], p: float) -> Optional[int]:
    if not sorted_values:
        return None
    idx = min(len(sorted_values) - 1, int(len(sorted_values) * p))
    return sorted_values[idx]


def build_dir(data_dir: Path, out_subdir: str = "passages_C") -> dict[str, Any]:
    """Build passages under <data_dir>/<out_subdir>/ for every transcripts_B/<video_id>.json
    under `data_dir`. Only ever writes to out_subdir -- passages_B is read-only
    input territory for this script."""
    transcripts_dir = data_dir / "transcripts_B"
    passages_c_dir = data_dir / out_subdir
    passages_c_dir.mkdir(parents=True, exist_ok=True)

    word_counts: list[int] = []
    totals = dict.fromkeys(_STATS_KEYS, 0)
    videos = 0

    for f in sorted(transcripts_dir.glob("*.json")):
        video_id = f.stem
        words = json.loads(f.read_text())
        clips, stats = build_clips_from_labelled_words(words, video_id)
        (passages_c_dir / f"{video_id}.json").write_text(json.dumps(clips, indent=1))
        for key in _STATS_KEYS:
            totals[key] += stats[key]
        word_counts.extend(len(c["verbatim_text"].split()) for c in clips)
        videos += 1

    word_counts.sort()
    return {
        "dir": str(data_dir),
        "videos": videos,
        **totals,
        "p10": _percentile(word_counts, 0.10),
        "p50": _percentile(word_counts, 0.50),
        "p90": _percentile(word_counts, 0.90),
    }


def print_report(reports: list[dict[str, Any]]) -> None:
    print("=" * 78)
    print("build_clips_v2 report (passages_C)")
    print("=" * 78)
    print(f"{'dir':<40}{'videos':>8}{'clips':>8}{'p10':>6}{'p50':>6}{'p90':>6}")
    for r in reports:
        print(
            f"{Path(r['dir']).name:<40}{r['videos']:>8}{r['clips']:>8}"
            f"{r['p10'] or 0:>6}{r['p50'] or 0:>6}{r['p90'] or 0:>6}"
        )
    print("-" * 78)
    for r in reports:
        print(
            f"{Path(r['dir']).name}: runs={r['runs']} dropped_short={r['dropped_short']} "
            f"merged_unknown_gaps={r['merged_unknown_gaps']} "
            f"cut_at_sentence={r['cut_at_sentence']} cut_at_pause={r['cut_at_pause']} "
            f"dropped_mid_sentence_at_flip={r['dropped_mid_sentence_at_flip']}"
        )


def _self_check() -> None:
    words = [
        {"w": "Love", "start": 0.0, "end": 0.3, "spk": "P"},
        {"w": "is", "start": 0.3, "end": 0.5, "spk": "P"},
        {"w": "not", "start": 0.5, "end": 0.7, "spk": "P"},
        {"w": "a", "start": 0.7, "end": 0.8, "spk": "P"},
        {"w": "feeling.", "start": 0.8, "end": 1.2, "spk": "P"},
        {"w": "It", "start": 1.3, "end": 1.4, "spk": "P"},
        {"w": "is", "start": 1.4, "end": 1.5, "spk": "P"},
        {"w": "an", "start": 1.5, "end": 1.6, "spk": "P"},
        {"w": "existence.", "start": 1.6, "end": 2.1, "spk": "P"},
    ]
    clips, stats = build_clips_from_labelled_words(words, "self_check", min_words=3)
    assert len(clips) == 1 and stats["clips"] == 1
    print("self-check OK")


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--dir",
        action="append",
        dest="dirs",
        default=[],
        help="Repeatable: a data dir containing transcripts_B/. Writes only to <dir>/<out-subdir>/.",
    )
    parser.add_argument(
        "--out-subdir",
        default="passages_C",
        help="Subdirectory name to write passages to (default: passages_C).",
    )
    parser.add_argument("--self-check", action="store_true")
    args = parser.parse_args(argv)

    if args.self_check:
        _self_check()
        return 0

    if not args.dirs:
        parser.error("--dir (repeatable) is required")

    reports = [build_dir(Path(d).expanduser(), out_subdir=args.out_subdir) for d in args.dirs]
    print_report(reports)
    return 0


if __name__ == "__main__":
    sys.exit(main())
