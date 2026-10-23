#!/usr/bin/env python3
"""Compare ASR models on the archived teacher audio (phase C2 / E1 input).

The plan names Saaras v3 vs v4. No Sarvam endpoint budget was approved for this
workspace, so this compares the two locally cached faster-whisper models instead
and reports the same three axes the plan asks for: word quality proxies, boundary
quality via clip locatability, and timing agreement with the audio the index
already stores. Swap ``--models`` when a Saaras pair is available; the metrics are
model-agnostic.

For each (video, model) it writes words with start/end/probability to
``--out-dir/<model>/<video_id>.json`` — the word-timing artifacts the context
rebuild needs.

Usage:
    python -m scripts.ops.compare_asr_models --videos Hdr5IXNmRUE 4Fjf6IQsjQs
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import statistics
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf

from scripts.ops.build_fp_context_from_v9 import _best_window

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_WAV_DIR = os.environ.get("WAV_DIR", "")


def _norm_words(text: str) -> list[str]:
    import re

    return re.sub(r"[^a-z0-9 ]", "", text.lower()).split()


def transcribe(model_name: str, wav: Path, *, language: str | None = "en") -> dict[str, Any]:
    from faster_whisper import WhisperModel

    started = time.time()
    model = WhisperModel(model_name, device="cpu", compute_type="int8", local_files_only=True)
    load_s = time.time() - started

    started = time.time()
    segments, info = model.transcribe(
        str(wav), word_timestamps=True, vad_filter=True, beam_size=1, language=language
    )
    words = []
    segment_rows = []
    for segment in segments:
        segment_rows.append(
            {
                "start": round(segment.start, 3),
                "end": round(segment.end, 3),
                "text": segment.text.strip(),
                "avg_logprob": round(segment.avg_logprob, 4),
                "no_speech_prob": round(segment.no_speech_prob, 4),
            }
        )
        for word in segment.words or []:
            words.append(
                {
                    "word": word.word,
                    "start": round(word.start, 3),
                    "end": round(word.end, 3),
                    "probability": round(float(word.probability), 4),
                }
            )
    elapsed = time.time() - started
    duration = float(sf.info(str(wav)).duration)
    return {
        "model": model_name,
        "video_id": wav.stem,
        "language": info.language,
        "language_probability": round(info.language_probability, 4),
        "duration_s": round(float(duration), 2),
        "load_s": round(load_s, 2),
        "transcribe_s": round(elapsed, 2),
        "realtime_factor": round(float(duration) / elapsed, 2) if elapsed else None,
        "words": words,
        "segments": segment_rows,
    }


def score_against_clips(result: dict[str, Any], clips: list[dict[str, Any]]) -> dict[str, Any]:
    """How well do the stored clip texts and timings agree with this ASR pass?"""
    normalized_words = [
        (idx, _norm_words(word["word"])[0])
        for idx, word in enumerate(result["words"])
        if _norm_words(word["word"])
    ]
    transcript = [w for _, w in normalized_words]
    located, offsets, ratios = 0, [], []
    for clip in clips:
        clip_words = _norm_words(clip["payload"].get("verbatim_text") or "")
        if not clip_words:
            continue
        start, ratio = _best_window(clip_words, transcript)
        if start < 0 or ratio < 0.90:
            continue
        located += 1
        ratios.append(ratio)
        orig_idx = normalized_words[start][0]
        asr_start_ms = result["words"][orig_idx]["start"] * 1000
        offsets.append(abs(asr_start_ms - float(clip["payload"].get("start_ms") or 0)))
    probabilities = [word["probability"] for word in result["words"]]
    return {
        "clips": len(clips),
        "clips_located": located,
        "clip_locatability": round(located / len(clips), 4) if clips else 0.0,
        "alignment_ratio_median": round(statistics.median(ratios), 4) if ratios else None,
        "timing_offset_ms_median": round(statistics.median(offsets), 1) if offsets else None,
        "timing_offset_ms_p95": (round(float(np.percentile(offsets, 95)), 1) if offsets else None),
        "word_count": len(result["words"]),
        "word_probability_median": round(statistics.median(probabilities), 4)
        if probabilities
        else None,
        "words_below_0_5": sum(1 for p in probabilities if p < 0.5),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--videos", nargs="*", default=None, help="Video ids (default: 5 shortest)")
    parser.add_argument("--models", nargs="*", default=["small", "large-v3"])
    parser.add_argument("--wav-dir", default=DEFAULT_WAV_DIR)
    parser.add_argument("--points", default=str(_REPO_ROOT / ".work/fp_context/v9_points.json"))
    parser.add_argument("--out-dir", default=str(_REPO_ROOT / ".work/asr"))
    parser.add_argument("--report", default=str(_REPO_ROOT / ".work/asr/comparison.json"))
    parser.add_argument("--language", default="en")
    args = parser.parse_args(argv)
    if not args.wav_dir:
        parser.error("--wav-dir is required (or set WAV_DIR environment variable)")

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    wav_dir = Path(args.wav_dir)
    points = json.loads(Path(args.points).read_text(encoding="utf-8"))["result"]["points"]
    by_video: dict[str, list[dict[str, Any]]] = {}
    for point in points:
        by_video.setdefault(str(point["payload"].get("video_id")), []).append(point)

    videos = args.videos or [
        video
        for video, _ in sorted(
            (
                (video, sf.info(str(wav_dir / f"{video}.wav")).duration)
                for video in by_video
                if (wav_dir / f"{video}.wav").is_file()
            ),
            key=lambda item: item[1],
        )[:5]
    ]

    report: dict[str, Any] = {"models": args.models, "videos": {}, "totals": Counter()}
    for video in videos:
        wav = wav_dir / f"{video}.wav"
        if not wav.is_file():
            logger.warning("no audio for %s", video)
            continue
        clips = by_video.get(video, [])
        report["videos"][video] = {}
        for model_name in args.models:
            result = transcribe(model_name, wav, language=args.language)
            scores = score_against_clips(result, clips)
            report["videos"][video][model_name] = scores
            out_dir = Path(args.out_dir) / model_name
            out_dir.mkdir(parents=True, exist_ok=True)
            (out_dir / f"{video}.json").write_text(
                json.dumps(result, indent=2) + "\n", encoding="utf-8"
            )
            logger.info(
                "%s %s located %s/%s ratio=%s offset_med=%sms rtf=%s",
                video,
                model_name,
                scores["clips_located"],
                scores["clips"],
                scores["alignment_ratio_median"],
                scores["timing_offset_ms_median"],
                result["realtime_factor"],
            )

    for model_name in args.models:
        rows = [
            report["videos"][video][model_name]
            for video in report["videos"]
            if model_name in report["videos"][video]
        ]
        if not rows:
            continue

        prob_vals = [
            row["word_probability_median"]
            for row in rows
            if row.get("word_probability_median") is not None
        ]
        time_vals = [
            row["timing_offset_ms_median"]
            for row in rows
            if row.get("timing_offset_ms_median") is not None
        ]
        report["totals"][model_name] = {
            "clips": sum(row["clips"] for row in rows),
            "clips_located": sum(row["clips_located"] for row in rows),
            "clip_locatability": round(
                sum(row["clips_located"] for row in rows)
                / max(1, sum(row["clips"] for row in rows)),
                4,
            ),
            "word_probability_median": (
                round(statistics.median(prob_vals), 4) if prob_vals else None
            ),
            "timing_offset_ms_median": (
                round(statistics.median(time_vals), 1) if time_vals else None
            ),
        }
    report["totals"] = dict(report["totals"])

    Path(args.report).parent.mkdir(parents=True, exist_ok=True)
    Path(args.report).write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(report["totals"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
