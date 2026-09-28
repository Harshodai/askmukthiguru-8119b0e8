#!/usr/bin/env python3
"""Read-only: compare clip-boundary repair strategies (plan rev 2, cards B2/B3).

For every v2 clip (passages_C) it maps the clip onto its video's word list
(transcripts_B: w/start/end/spk) and scores three strategies:

  none    the clip as built
  shrink  snap_to_sentences          -- drop the partial head/tail sentence
  grow    grow_to_sentence_start, then trim the tail -- recover the head
          sentence while every word stays the clip teacher's own label

Sentence boundaries come from raw/<vid>_punct.json display_words when it is
word-for-word aligned (zero_change_assert_passed and equal length); otherwise
from the verbatim words' own punctuation. Nothing is written except the report.

  .venv/bin/python -m scripts.ops.measure_first_person_boundary_repair \
      --root ~/mukthiguru_attribution_data/pilot50_2026-09-25 --root ~/mukthiguru_attribution_data/bakeoff_2026-09-25
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import statistics
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, os.path.abspath(os.path.join(__file__, "..", "..", "..")))

from ingest.verbatim.boundaries import (  # noqa: E402
    boundary_defects,
    grow_to_sentence_start,
    snap_to_sentences,
)

_REPO = Path(__file__).resolve().parents[3]
_SPK = {"preethaji": "P", "krishnaji": "K"}
_PAD_S = 0.3  # clips carry 0.2 s turn padding
MIN_WORDS = 12
TARGET_MIN_S = 18.0  # FP invariant 11 lower bound


def sentence_tokens(words: list[dict[str, Any]], punct: dict[str, Any] | None) -> tuple[list[str], bool]:
    display = (punct or {}).get("display_words") or []
    if (punct or {}).get("zero_change_assert_passed") and len(display) == len(words):
        return display, True
    return [w["w"] for w in words], False


def clip_span(words: list[dict[str, Any]], start: float, end: float) -> tuple[int, int] | None:
    idx = [i for i, w in enumerate(words) if w["start"] >= start - _PAD_S and w["end"] <= end + _PAD_S]
    return (idx[0], idx[-1] + 1) if idx else None


def repair(sent: list[str], labels: list[str], s: int, e: int, spk: str) -> dict[str, tuple[int, int] | None]:
    grown = grow_to_sentence_start(sent, labels, s, spk)
    return {
        "none": (s, e),
        "shrink": snap_to_sentences(sent, s, e, MIN_WORDS),
        "grow": snap_to_sentences(sent, grown if grown is not None else s, e, MIN_WORDS),
    }


def measure(roots: list[Path], min_duration_s: float) -> dict[str, Any]:
    acc = {m: {"survive": 0, "clean": 0, "clean_18s": 0, "words": 0, "durations": []} for m in ("none", "shrink", "grow")}
    n_clips = n_display = n_unmapped = 0
    for root in roots:
        for f in sorted((root / "passages_C").glob("*.json")):
            tpath, ppath = root / "transcripts_B" / f"{f.stem}.json", root / "raw" / f"{f.stem}_punct.json"
            if not tpath.exists():
                continue
            words = json.loads(tpath.read_text())
            sent, used_display = sentence_tokens(words, json.loads(ppath.read_text()) if ppath.exists() else None)
            labels = [w.get("spk", "?") for w in words]
            for clip in json.loads(f.read_text()):
                spk = _SPK.get(clip.get("speaker", ""))
                if spk is None or clip["end"] - clip["start"] < min_duration_s:
                    continue
                span = clip_span(words, clip["start"], clip["end"])
                if span is None:
                    n_unmapped += 1
                    continue
                n_clips += 1
                n_display += used_display
                for method, r in repair(sent, labels, *span, spk).items():
                    if r is None:
                        continue
                    s, e = r
                    dur = words[e - 1]["end"] - words[s]["start"]
                    clean = not boundary_defects(sent[s:e])
                    a = acc[method]
                    a["survive"] += 1
                    a["clean"] += clean
                    a["clean_18s"] += clean and dur >= TARGET_MIN_S
                    a["words"] += e - s
                    a["durations"].append(dur)
    return {
        "clips": n_clips,
        "clips_with_display_layer": n_display,
        "unmapped": n_unmapped,
        "methods": {
            m: {
                "survive": a["survive"],
                "clean": a["clean"],
                "clean_pct_of_input": round(100 * a["clean"] / n_clips, 1) if n_clips else 0.0,
                "clean_and_18s_plus": a["clean_18s"],
                "words_kept": a["words"],
                "median_duration_s": round(statistics.median(a["durations"]), 1) if a["durations"] else None,
            }
            for m, a in acc.items()
        },
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", type=Path, action="append", required=True)
    ap.add_argument("--min-duration-s", type=float, default=8.0)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args(argv)
    report = {
        "generated_at": dt.datetime.now(dt.UTC).isoformat(),
        "roots": [str(r) for r in args.root],
        "min_words": MIN_WORDS,
        **measure(args.root, args.min_duration_s),
    }
    out = args.out or _REPO / "docs" / "evidence" / f"first_person_boundary_repair_{dt.date.today().isoformat()}.json"
    out.write_text(json.dumps(report, indent=2))
    print(json.dumps({k: v for k, v in report.items() if k != "roots"}, indent=1), f"\n-> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
