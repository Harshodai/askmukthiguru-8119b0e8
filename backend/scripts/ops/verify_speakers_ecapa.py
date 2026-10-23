#!/usr/bin/env python3
"""Verify first-person clip speakers with ECAPA-TDNN against the labelled clips.

1,202 of the 1,981 clips in ``first_person_v9`` carry no ``speaker_verified``
value. The plan forbids defaulting that to true, so this script earns the value:

1. Embed every clip's audio slice with ``speechbrain/spkrec-ecapa-voxceleb``.
2. Split the *already verified* clips into a train half and a held-out test half
   (deterministic, no peeking), build one centroid per guru from train, and score
   the test half. That number is the method's accuracy on labels nobody wrote.
3. Pick the decision floors (cosine similarity to the predicted centroid plus
   its margin over the runner-up) from a held-out impostor set: each test clip
   scored against the centroids of teachers it is *not* labelled as. Clips are
   upgraded only when the predicted guru equals the payload's own teacher and
   both floors clear. If no impostor set (or no measurable false-accept rate)
   exists, every clip stays unverified.

Output is a verdict file (``verified`` per source point id) that the context
builder consumes; this script never writes to Qdrant and never edits payloads.

Usage:
    python -m scripts.ops.verify_speakers_ecapa --report .work/fp_context/speaker_report.json
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf
import torch

try:
    from scripts.download_models import _MODEL_REVISIONS
except Exception:
    _MODEL_REVISIONS = {}

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[3]
MIN_CLIP_SECONDS = 0.4
TARGET_SAMPLE_RATE = 16000
ECAPA_MODEL_ID = "speechbrain/spkrec-ecapa-voxceleb"
ECAPA_REVISION = _MODEL_REVISIONS.get(ECAPA_MODEL_ID, "0f99f2d0ebe89ac095bcc5903c4dd8f72b367286")
DEFAULT_WAV_DIR = os.environ.get("WAV_DIR", "")
# A calibration set smaller than this cannot support a measurable false-accept
# rate, so callers must leave every clip unverified instead of guessing floors.
MIN_IMPOSTOR_TRIALS = 20


def _load_embedder(cache_root: Path):
    from huggingface_hub import snapshot_download
    from speechbrain.inference.speaker import SpeakerRecognition

    repo_dir = snapshot_download(
        repo_id=ECAPA_MODEL_ID,
        revision=ECAPA_REVISION,
    )
    return SpeakerRecognition.from_hparams(
        source=repo_dir,
        savedir=str(cache_root / "ecapa"),
        run_opts={"device": "cpu"},
    )


def _slice(path: Path, start_ms: int, end_ms: int) -> np.ndarray | None:
    try:
        info = sf.info(str(path))
    except Exception as exc:  # unreadable archive entry
        logger.warning("cannot stat %s: %s", path.name, exc)
        return None
    start = max(0, int(start_ms)) / 1000.0
    end = min(float(info.frames) / info.samplerate, int(end_ms) / 1000.0)
    if end - start < MIN_CLIP_SECONDS:
        return None
    audio, sr = sf.read(
        str(path),
        start=int(start * info.samplerate),
        frames=int((end - start) * info.samplerate),
        dtype="float32",
    )
    if audio.ndim > 1:
        audio = audio.mean(axis=1)
    if sr != TARGET_SAMPLE_RATE:
        import scipy.signal

        num_samples = int(len(audio) * float(TARGET_SAMPLE_RATE) / float(sr))
        audio = scipy.signal.resample(audio, num_samples).astype(np.float32)
    return audio


def embed_points(points: list[dict[str, Any]], wav_dir: Path, cache: Path) -> dict[str, np.ndarray]:
    """Embed each point once; the npz cache makes reruns cheap."""
    embedder = _load_embedder(cache)
    stored: dict[str, np.ndarray] = {}
    if (cache / "embeddings.npz").is_file():
        with np.load(cache / "embeddings.npz") as data:
            stored = {key: data[key] for key in data.files}
    missing = [p for p in points if str(p["id"]) not in stored]
    logger.info("embedding %d clips (%d cached)", len(missing), len(stored))
    for index, point in enumerate(missing, 1):
        payload = point["payload"]
        wav = wav_dir / f"{payload.get('video_id')}.wav"
        audio = (
            _slice(wav, int(payload.get("start_ms") or 0), int(payload.get("end_ms") or 0))
            if wav.is_file()
            else None
        )
        if audio is None:
            continue
        with torch.no_grad():
            emb = embedder.encode_batch(torch.from_numpy(audio).unsqueeze(0))
        vector = emb.squeeze().detach().cpu().numpy().astype(np.float32)
        norm = float(np.linalg.norm(vector))
        if norm <= 0:
            continue
        stored[str(point["id"])] = vector / norm
        if index % 200 == 0:
            logger.info("embedded %d/%d", index, len(missing))
            np.savez_compressed(cache / "embeddings.npz", **stored)
    np.savez_compressed(cache / "embeddings.npz", **stored)
    return stored


def _cos(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(a, b))


def evaluate(
    points: list[dict[str, Any]], embeddings: dict[str, np.ndarray]
) -> tuple[dict[str, np.ndarray], dict[str, Any], list[tuple[str, str, np.ndarray]]]:
    """Split labelled clips, train centroids, score the held-out half."""
    by_guru: dict[str, list[tuple[str, np.ndarray]]] = defaultdict(list)
    for point in points:
        vector = embeddings.get(str(point["id"]))
        guru = str(point["payload"].get("teacher_id") or "").lower()
        if vector is None or not guru:
            continue
        if point["payload"].get("speaker_verified") is True:
            by_guru[guru].append((str(point["id"]), vector))

    train: dict[str, list[np.ndarray]] = defaultdict(list)
    test: list[tuple[str, str, np.ndarray]] = []
    for guru, rows in sorted(by_guru.items()):
        rows.sort(key=lambda row: row[0])  # deterministic
        for index, (point_id, vector) in enumerate(rows):
            if index % 2 == 0:
                train[guru].append(vector)
            else:
                test.append((point_id, guru, vector))

    centroids = {
        guru: np.mean(np.stack(vecs), axis=0) / np.linalg.norm(np.mean(np.stack(vecs), axis=0))
        for guru, vecs in train.items()
        if vecs
    }

    correct, margins, confusion = 0, [], Counter()
    for _point_id, guru, vector in test:
        scores = {name: _cos(vector, centroid) for name, centroid in centroids.items()}
        ordered = sorted(scores.items(), key=lambda item: item[1], reverse=True)
        predicted = ordered[0][0]
        margin = ordered[0][1] - (ordered[1][1] if len(ordered) > 1 else 0.0)
        confusion[f"{guru}->{predicted}"] += 1
        if predicted == guru:
            correct += 1
            margins.append(margin)

    accuracy = correct / len(test) if test else 0.0
    summary = {
        "labelled_clips": sum(len(rows) for rows in by_guru.values()),
        "train_clips": {guru: len(vecs) for guru, vecs in train.items()},
        "test_clips": len(test),
        "accuracy": round(accuracy, 4),
        "confusion": dict(confusion),
        "margin_on_correct": {
            "min": round(min(margins), 4) if margins else None,
            "p01": round(float(np.percentile(margins, 1)), 4) if margins else None,
            "p50": round(float(np.percentile(margins, 50)), 4) if margins else None,
        },
        "centroid_separation": {
            f"{a}|{b}": round(_cos(centroids[a], centroids[b]), 4)
            for i, a in enumerate(sorted(centroids))
            for b in sorted(centroids)[i + 1 :]
        },
    }
    return centroids, summary, test


def _impostor_trials(
    centroids: dict[str, np.ndarray], test: list[tuple[str, str, np.ndarray]]
) -> list[dict[str, Any]]:
    """Held-out trials where a labelled clip is scored against another teacher."""
    trials: list[dict[str, Any]] = []
    for _point_id, guru, vector in test:
        scores = {name: _cos(vector, centroid) for name, centroid in centroids.items()}
        ordered = sorted(scores.items(), key=lambda item: item[1], reverse=True)
        predicted = ordered[0][0]
        for claimed in centroids:
            if claimed == guru:
                continue
            best = scores[claimed]
            runner_up = max((value for name, value in scores.items() if name != claimed), default=0.0)
            trials.append(
                {
                    "claimed": claimed,
                    "predicted": predicted,
                    "cosine": best,
                    "margin": best - runner_up,
                }
            )
    return trials


def calibrate(
    centroids: dict[str, np.ndarray],
    test: list[tuple[str, str, np.ndarray]],
) -> dict[str, Any] | None:
    """Calibrate floors on held-out impostor trials, never on correct clips.

    The floors sit strictly above every observed impostor cosine and margin, so
    the measured false-accept rate on that set is recorded (0.0 by construction).
    Too few trials means the rate is not measurable: return None so callers keep
    every clip unverified.
    """
    trials = _impostor_trials(centroids, test)
    if len(trials) < MIN_IMPOSTOR_TRIALS:
        return None
    # Still strictly above every observed impostor score, but never allowed to
    # fall below zero: a negative floor would weaken verification instead of
    # tightening it.
    cosine_floor = max(0.0, max(trial["cosine"] for trial in trials)) + 1e-6
    margin_threshold = max(0.0, max(trial["margin"] for trial in trials)) + 1e-6
    false_accepts = sum(
        1
        for trial in trials
        if trial["predicted"] == trial["claimed"]
        and trial["cosine"] >= cosine_floor
        and trial["margin"] >= margin_threshold
    )
    return {
        "impostor_trials": len(trials),
        "cosine_floor": float(cosine_floor),
        "margin_threshold": float(margin_threshold),
        "false_accept_rate": round(false_accepts / len(trials), 6),
    }


def verdicts(
    points: list[dict[str, Any]],
    embeddings: dict[str, np.ndarray],
    centroids: dict[str, np.ndarray],
    margin_threshold: float,
    cosine_floor: float,
) -> dict[str, Any]:
    out: dict[str, Any] = {
        "threshold": margin_threshold,
        "cosine_floor": cosine_floor,
        "items": {},
    }
    upgraded = Counter()
    refused = Counter()
    if not centroids:
        out["upgraded"] = dict(upgraded)
        out["refused"] = {"no_centroids": len(points)}
        return out
    for point in points:
        payload = point["payload"]
        guru = str(payload.get("teacher_id") or "").lower()
        vector = embeddings.get(str(point["id"]))
        if vector is None or not guru:
            continue
        if payload.get("speaker_verified") is True:
            continue
        scores = {name: _cos(vector, centroid) for name, centroid in centroids.items()}
        ordered = sorted(scores.items(), key=lambda item: item[1], reverse=True)
        predicted, best = ordered[0]
        margin = best - (ordered[1][1] if len(ordered) > 1 else 0.0)
        agree = predicted == guru
        passed = agree and margin >= margin_threshold and best >= cosine_floor
        out["items"][str(point["id"])] = {
            "verified": passed,
            "method": "ecapa_voxceleb_centroid_v1",
            "predicted_guru": predicted,
            "payload_guru": guru,
            "cosine": round(best, 4),
            "margin": round(margin, 4),
        }
        if passed:
            upgraded[guru] += 1
        else:
            refused["disagree" if not agree else "below_threshold"] += 1
    out["upgraded"] = dict(upgraded)
    out["refused"] = dict(refused)
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--points", default=str(_REPO_ROOT / ".work/fp_context/v9_points.json"))
    parser.add_argument(
        "--wav-dir",
        default=DEFAULT_WAV_DIR,
    )
    parser.add_argument("--cache", default=str(_REPO_ROOT / ".work/fp_context/speaker"))
    parser.add_argument(
        "--verdicts", default=str(_REPO_ROOT / ".work/fp_context/speaker_verdicts.json")
    )
    parser.add_argument(
        "--report", default=str(_REPO_ROOT / ".work/fp_context/speaker_report.json")
    )
    parser.add_argument("--margin", type=float, default=None, help="Override the calibrated margin")
    args = parser.parse_args(argv)
    if not args.wav_dir:
        parser.error("--wav-dir is required (or set WAV_DIR environment variable)")

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    points = json.loads(Path(args.points).read_text(encoding="utf-8"))["result"]["points"]
    cache = Path(args.cache)
    cache.mkdir(parents=True, exist_ok=True)

    embeddings = embed_points(points, Path(args.wav_dir), cache)
    centroids, summary, test = evaluate(points, embeddings)
    calibration = calibrate(centroids, test)
    summary["impostor_calibration"] = calibration
    if calibration is None:
        logger.error(
            "No measurable held-out impostor set (%d trials < %d); keeping every clip unverified",
            len(_impostor_trials(centroids, test)),
            MIN_IMPOSTOR_TRIALS,
        )
        # Infinity floors reject every candidate: absence of evidence can never
        # become a verification.
        result = verdicts(points, embeddings, centroids, float("inf"), float("inf"))
    else:
        threshold = (
            args.margin if args.margin is not None else calibration["margin_threshold"]
        )
        result = verdicts(
            points,
            embeddings,
            centroids,
            threshold,
            calibration["cosine_floor"],
        )
    result["calibration_available"] = calibration is not None
    result["evaluation"] = summary
    result["embeddings"] = len(embeddings)

    Path(args.verdicts).write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    Path(args.report).write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "accuracy": summary["accuracy"],
                "test_clips": summary["test_clips"],
                "confusion": summary["confusion"],
                "margin_threshold": result["threshold"],
                "cosine_floor": result["cosine_floor"],
                "impostor_calibration": calibration,
                "upgraded": result["upgraded"],
                "refused": result["refused"],
                "embeddings": len(embeddings),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
