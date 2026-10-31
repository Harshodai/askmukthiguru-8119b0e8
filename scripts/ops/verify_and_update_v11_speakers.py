#!/usr/bin/env python3
"""Offline Speaker Verification & Safe Qdrant Update for first_person_v11.

Evaluates unverified child spans in Qdrant collection `first_person_v11` using
the ECAPA-TDNN speaker recognition model against reference centroids built from
human-confirmed anchor moments.

Invariants respected:
- Invariant X1: Byte-identical mirroring between scripts/ops/ and backend/scripts/ops/.
- Invariant X18: Pinned ECAPA model and reference centroids derived from human anchors;
  claimed guru is the hypothesis under test, never the evidence.
- Invariant X21: Slice ECAPA audio strictly from `audio_archive/wavs/{video_id}.wav`.
- Invariant X40: Honest provenance stamps:
  - Passed spans: `voice_verification_method: "ecapa_voxceleb_span_slice_v2"`,
    `speaker_verified: True`.
  - Failed spans: `speaker_verified: False`, `quarantine_reason: "voice_threshold_failed"`.

Usage:
    # Dry-run evaluation (no writes to Qdrant):
    python -m scripts.ops.verify_and_update_v11_speakers --dry-run

    # Apply payloads to Qdrant:
    python -m scripts.ops.verify_and_update_v11_speakers --apply
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import logging
import math
import os
from pathlib import Path
import sys
from typing import Any

import numpy as np
import scipy.signal
import soundfile as sf
import torch

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# Repository / Backend path setup
_HERE = Path(__file__).resolve()
if _HERE.parents[1].name == "ops" and _HERE.parents[2].name == "scripts" and _HERE.parents[3].name == "backend":
    _REPO_ROOT = _HERE.parents[3].parent
    _BACKEND = _HERE.parents[3]
elif _HERE.parents[1].name == "ops" and _HERE.parents[2].name == "scripts":
    _REPO_ROOT = _HERE.parents[2].parent
    _BACKEND = _REPO_ROOT / "backend"
else:
    _REPO_ROOT = Path.cwd()
    _BACKEND = _REPO_ROOT / "backend"

if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

ECAPA_MODEL_ID = "speechbrain/spkrec-ecapa-voxceleb"
ECAPA_REVISION = "0f99f2d0ebe89ac095bcc5903c4dd8f72b367286"
TARGET_SAMPLE_RATE = 16000
MIN_CLIP_SECONDS = 0.4

DEFAULT_QDRANT_URL = os.environ.get("QDRANT_URL", "http://localhost:6333")
DEFAULT_COLLECTION = "first_person_v11"
DEFAULT_WAV_DIR = "/Users/harshodaikolluru/mukthiguru_attribution_data/audio_archive/wavs"
DEFAULT_REF_NPZ = "/Users/harshodaikolluru/mukthiguru_attribution_data/phase2_references_2026-10-30/references.npz"
DEFAULT_CACHE_DIR = "/tmp/ecapa_cache"
DEFAULT_REPORT_PATH = str(_REPO_ROOT / "audits/evidence/speaker_verification_v11_2026-10-31.json")

DEFAULT_COSINE_FLOOR = 0.35
DEFAULT_MARGIN_THRESHOLD = 0.15

TEACHER_CODES = {
    "sri preethaji": "preethaji",
    "sri krishnaji": "krishnaji",
    "preethaji": "preethaji",
    "krishnaji": "krishnaji",
}

TARGET_VIDEOS = {
    "9yaEGbPIxPk",
    "HCs6I_BNtxo",
    "MJYpyUlwxg0",
    "RvgN5Mfbd5A",
    "ZD1nQPtpojM",
    "kzRqQOvjRhA",
    "oqacXWT14ic",
    "tegTDWT3SDc",
    "wKYEvQZ03Po",
}


def load_references(npz_path: Path) -> dict[str, np.ndarray]:
    """Load pre-calibrated guru reference centroids."""
    if not npz_path.is_file():
        raise FileNotFoundError(f"Reference centroids not found at {npz_path}")
    with np.load(npz_path) as data:
        refs = {k: data[k].astype(np.float32) for k in data.files}
    for required in ("krishnaji", "preethaji"):
        if required not in refs:
            raise ValueError(f"Centroid '{required}' missing in {npz_path}")
    return refs


def load_embedder(cache_dir: Path, device: str = "cpu"):
    """Load pinned ECAPA-TDNN speaker encoder."""
    from huggingface_hub import snapshot_download
    from speechbrain.inference.speaker import SpeakerRecognition

    repo_dir = snapshot_download(
        repo_id=ECAPA_MODEL_ID,
        revision=ECAPA_REVISION,
    )
    return SpeakerRecognition.from_hparams(
        source=repo_dir,
        savedir=str(cache_dir / "ecapa"),
        run_opts={"device": device},
    )


def slice_audio(wav_path: Path, start_ms: int, end_ms: int) -> np.ndarray | None:
    """Read [start_ms, end_ms] PCM audio from wav_path and convert to 16 kHz mono."""
    if not wav_path.is_file():
        logger.warning(f"Audio file missing: {wav_path}")
        return None
    try:
        info = sf.info(str(wav_path))
    except Exception as exc:
        logger.warning(f"Cannot read WAV header for {wav_path}: {exc}")
        return None

    start_sec = max(0.0, float(start_ms) / 1000.0)
    end_sec = min(float(info.duration), float(end_ms) / 1000.0)
    if end_sec - start_sec < MIN_CLIP_SECONDS:
        logger.warning(f"Clip too short ({end_sec - start_sec:.3f}s) in {wav_path}")
        return None

    start_frame = int(round(start_sec * info.samplerate))
    frames = int(round((end_sec - start_sec) * info.samplerate))

    try:
        audio, sr = sf.read(str(wav_path), start=start_frame, frames=frames, dtype="float32")
    except Exception as exc:
        logger.warning(f"Error reading slice from {wav_path}: {exc}")
        return None

    if audio.ndim > 1:
        audio = audio.mean(axis=1)

    if sr != TARGET_SAMPLE_RATE:
        num_samples = int(round(len(audio) * float(TARGET_SAMPLE_RATE) / float(sr)))
        audio = scipy.signal.resample(audio, num_samples).astype(np.float32)

    return audio


def embed_audio(audio: np.ndarray, embedder) -> np.ndarray:
    """Compute normalized 192-dim ECAPA embedding for audio tensor."""
    with torch.no_grad():
        emb = embedder.encode_batch(torch.from_numpy(audio).unsqueeze(0))
    vec = emb.squeeze().detach().cpu().numpy().astype(np.float32)
    norm = float(np.linalg.norm(vec))
    if norm > 0 and math.isfinite(norm):
        vec = (vec / norm).astype(np.float32)
    return vec


def resolve_claimed_guru(payload: dict[str, Any]) -> str | None:
    """Resolve claimed teacher from speaker_id or guru_id."""
    raw_spk = str(payload.get("speaker_id") or "").strip().casefold()
    if raw_spk in TEACHER_CODES:
        return TEACHER_CODES[raw_spk]
    raw_guru = str(payload.get("guru_id") or "").strip().casefold()
    if raw_guru in TEACHER_CODES:
        return TEACHER_CODES[raw_guru]
    return None


def fetch_unverified_points(client, collection: str, point_ids: list[str] | None = None) -> list[Any]:
    """Fetch unverified child spans from Qdrant."""
    from qdrant_client.http import models

    if point_ids:
        return client.retrieve(collection_name=collection, ids=point_ids, with_payload=True, with_vectors=False)

    points = []
    offset = None
    while True:
        res, next_offset = client.scroll(
            collection_name=collection,
            scroll_filter=models.Filter(
                must=[
                    models.FieldCondition(key="record_type", match=models.MatchValue(value="retrieval_child")),
                    models.FieldCondition(key="speaker_verified", match=models.MatchValue(value=False)),
                ]
            ),
            limit=500,
            offset=offset,
            with_payload=True,
            with_vectors=False,
        )
        points.extend(res)
        offset = next_offset
        if not offset:
            break
    return points


def evaluate_span(
    point: Any,
    wav_dir: Path,
    embedder: Any,
    references: dict[str, np.ndarray],
    cosine_floor: float,
    margin_threshold: float,
) -> dict[str, Any]:
    """Score a single Qdrant child span against reference centroids."""
    payload = point.payload or {}
    point_id = str(point.id)
    vid = payload.get("video_id")
    span_id = payload.get("source_span_id")
    start_ms = payload.get("start_ms")
    end_ms = payload.get("end_ms")
    claimed_guru = resolve_claimed_guru(payload)

    if not vid or start_ms is None or end_ms is None:
        return {
            "point_id": point_id,
            "video_id": vid,
            "source_span_id": span_id,
            "start_ms": start_ms,
            "end_ms": end_ms,
            "claimed_guru": claimed_guru,
            "passed": False,
            "error": "Missing video_id or start/end coordinates",
        }

    if not claimed_guru:
        return {
            "point_id": point_id,
            "video_id": vid,
            "source_span_id": span_id,
            "start_ms": start_ms,
            "end_ms": end_ms,
            "claimed_guru": None,
            "passed": False,
            "error": f"Unrecognized speaker_id: {payload.get('speaker_id')!r}",
        }

    wav_path = wav_dir / f"{vid}.wav"
    audio = slice_audio(wav_path, int(start_ms), int(end_ms))
    if audio is None:
        return {
            "point_id": point_id,
            "video_id": vid,
            "source_span_id": span_id,
            "start_ms": start_ms,
            "end_ms": end_ms,
            "claimed_guru": claimed_guru,
            "passed": False,
            "error": "Could not read audio slice",
        }

    vector = embed_audio(audio, embedder)
    ref_k = references["krishnaji"]
    ref_p = references["preethaji"]

    score_k = float(np.dot(vector, ref_k))
    score_p = float(np.dot(vector, ref_p))

    if claimed_guru == "krishnaji":
        claimed_score = score_k
        other_score = score_p
    else:
        claimed_score = score_p
        other_score = score_k

    margin = claimed_score - other_score
    best_guru = "krishnaji" if score_k > score_p else "preethaji"
    best_score = max(score_k, score_p)

    passed = (best_guru == claimed_guru) and (best_score >= cosine_floor) and (margin >= margin_threshold)

    return {
        "point_id": point_id,
        "video_id": vid,
        "source_span_id": span_id,
        "start_ms": int(start_ms),
        "end_ms": int(end_ms),
        "claimed_guru": claimed_guru,
        "predicted_guru": best_guru,
        "speaker_score": round(best_score, 4),
        "speaker_margin": round(margin, 4),
        "score_krishnaji": round(score_k, 4),
        "score_preethaji": round(score_p, 4),
        "passed": passed,
        "verdict": "pass" if passed else "quarantine",
        "quarantine_reason": None if passed else "voice_threshold_failed",
    }


def format_table(results: list[dict[str, Any]]) -> str:
    """Format evaluation results into a human-readable table."""
    header = (
        f"{'Status':<6} {'Video ID':<12} {'Coordinates (ms)':<22} {'Claimed':<11} "
        f"{'Predicted':<11} {'Score':<8} {'Margin':<8} {'Verdict':<10}"
    )
    separator = "-" * len(header)
    lines = [separator, header, separator]

    for r in sorted(results, key=lambda x: (x.get("video_id", ""), x.get("start_ms", 0))):
        status = "PASS" if r.get("passed") else "FAIL"
        vid = str(r.get("video_id", ""))
        coords = f"{r.get('start_ms', 0)} - {r.get('end_ms', 0)}"
        claimed = str(r.get("claimed_guru", ""))
        predicted = str(r.get("predicted_guru", ""))
        score = f"{r.get('speaker_score', 0.0):.4f}"
        margin_val = r.get("speaker_margin", 0.0)
        margin = f"{margin_val:+.4f}"
        verdict = str(r.get("verdict", ""))
        lines.append(
            f"{status:<6} {vid:<12} {coords:<22} {claimed:<11} {predicted:<11} "
            f"{score:<8} {margin:<8} {verdict:<10}"
        )

    lines.append(separator)
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--qdrant-url", default=DEFAULT_QDRANT_URL, help="Qdrant HTTP URL")
    parser.add_argument("--collection", default=DEFAULT_COLLECTION, help="Target collection")
    parser.add_argument("--wav-dir", type=Path, default=Path(DEFAULT_WAV_DIR), help="Directory of WAV files")
    parser.add_argument("--ref-npz", type=Path, default=Path(DEFAULT_REF_NPZ), help="Reference centroids .npz")
    parser.add_argument("--cache-dir", type=Path, default=Path(DEFAULT_CACHE_DIR), help="Model cache directory")
    parser.add_argument("--report", type=Path, default=Path(DEFAULT_REPORT_PATH), help="Audit report JSON path")
    parser.add_argument("--cosine-floor", type=float, default=DEFAULT_COSINE_FLOOR, help="Cosine threshold")
    parser.add_argument("--margin-threshold", type=float, default=DEFAULT_MARGIN_THRESHOLD, help="Margin threshold")
    parser.add_argument("--device", default="cpu", help="Device for torch (cpu / mps)")
    parser.add_argument("--point-ids", nargs="*", default=None, help="Explicit point IDs to process")
    parser.add_argument("--dry-run", action="store_true", help="Perform evaluation without mutating Qdrant")
    parser.add_argument("--apply", action="store_true", help="Apply updates to Qdrant collection payloads")

    args = parser.parse_args(argv)

    if not args.apply and not args.dry_run:
        logger.info("Neither --apply nor --dry-run specified; defaulting to --dry-run (safe mode).")
        args.dry_run = True

    from qdrant_client import QdrantClient

    logger.info(f"Connecting to Qdrant at {args.qdrant_url}, collection '{args.collection}'")
    client = QdrantClient(url=args.qdrant_url)

    logger.info(f"Loading reference centroids from {args.ref_npz}")
    references = load_references(args.ref_npz)

    logger.info(f"Loading ECAPA model (device={args.device})")
    embedder = load_embedder(args.cache_dir, device=args.device)

    logger.info(f"Fetching unverified child points from collection '{args.collection}'...")
    points = fetch_unverified_points(client, args.collection, point_ids=args.point_ids)
    logger.info(f"Found {len(points)} candidate points to evaluate.")

    if not points:
        logger.warning("No candidate points found for verification.")
        return 0

    results = []
    for index, pt in enumerate(points, 1):
        res = evaluate_span(
            point=pt,
            wav_dir=args.wav_dir,
            embedder=embedder,
            references=references,
            cosine_floor=args.cosine_floor,
            margin_threshold=args.margin_threshold,
        )
        results.append(res)

    print("\n" + format_table(results) + "\n")

    passed_count = sum(1 for r in results if r.get("passed"))
    failed_count = sum(1 for r in results if not r.get("passed"))
    logger.info(f"Evaluation complete: Total={len(results)}, PASS={passed_count}, FAIL={failed_count}")

    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    if args.apply:
        logger.info(f"Applying payload mutations for {len(results)} points in '{args.collection}'...")
        for r in results:
            pid = r["point_id"]
            # Clean up any legacy/extra keys that violate SourceSpan(extra='forbid')
            try:
                client.delete_payload(
                    collection_name=args.collection,
                    keys=["speaker_score", "speaker_margin", "speaker_attribution_timestamp"],
                    points=[pid],
                )
            except Exception as e:
                logger.debug(f"delete_payload cleanup on {pid}: {e}")

            if r["passed"]:
                delta = {
                    "speaker_verified": True,
                    "voice_verification_method": "ecapa_voxceleb_span_slice_v2",
                    "voice_score": r["speaker_score"],
                    "voice_margin": r["speaker_margin"],
                    "voice_verified_at": now_iso,
                    "voice_model_revision": ECAPA_REVISION,
                    "speaker_verification_status": "verified",
                    "quality_status": "verified_verbatim",
                    "quarantine_reason": None,
                }
            else:
                delta = {
                    "speaker_verified": False,
                    "quarantine_reason": "voice_threshold_failed",
                    "voice_score": r["speaker_score"],
                    "voice_margin": r["speaker_margin"],
                    "voice_verified_at": now_iso,
                    "voice_model_revision": ECAPA_REVISION,
                    "speaker_verification_status": "ecapa_failed",
                }
            client.set_payload(
                collection_name=args.collection,
                payload=delta,
                points=[pid],
            )
        logger.info(f"Successfully applied {len(results)} payload updates to Qdrant.")

    report_data = {
        "schema": "first-person-v11-speaker-verification-report-v1",
        "execution_timestamp": now_iso,
        "collection": args.collection,
        "qdrant_url": args.qdrant_url,
        "mode": "apply" if args.apply else "dry_run",
        "applied": bool(args.apply),
        "model_id": ECAPA_MODEL_ID,
        "model_revision": ECAPA_REVISION,
        "reference_centroids_path": str(args.ref_npz.resolve()),
        "cosine_floor": args.cosine_floor,
        "margin_threshold": args.margin_threshold,
        "device": args.device,
        "summary": {
            "total_evaluated": len(results),
            "passed": passed_count,
            "failed": failed_count,
        },
        "results": results,
    }

    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report_data, indent=2, sort_keys=True), encoding="utf-8")
    logger.info(f"Audit report saved to {args.report}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
