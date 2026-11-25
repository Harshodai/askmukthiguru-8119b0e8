#!/usr/bin/env python3
"""Windowed ECAPA v1 scorer for first_person_v12_shadow.

Owner decision (Harshodai, 2026-11-16): slide windows of W=3s / H=1.5s over
each span and require the teacher to speak throughout — catching host/other
voice inside a clip.  Windowed ECAPA takes precedence over the coarser
diarization window check.

Two modes
---------
calibrate
    Build windowed_calibration.json from positives (shadow verified spans) and
    negatives (diarization O/? windows).  Never writes to Qdrant.

score
    Score a JSONL of spans using a pinned windowed_calibration.json.  Emits
    per-span verdict rows and a summary.  Never writes to Qdrant.

The apply step is handled separately by apply_shadow_voice_verdicts.py with
``--windowed-verdicts-jsonl``.

Silence floor
-------------
A window is considered silent and skipped if its root-mean-square amplitude
< 0.01 (absolute floor, 16-bit normalised, same floor used in
``_window_vectors`` of regenerate_v10_span_ecapa_verdicts.py and
speaker_attribution.py; reliably drops true silence and head/tail pad without
dropping whispering).

Usage
-----
    # calibrate
    python backend/scripts/ops/windowed_ecapa_v1_scorer.py \\
        --mode calibrate \\
        --positive-spans-jsonl pos.jsonl \\
        --negative-diar-dir ~/mukthiguru_attribution_data/mass_ingest_2026-10/raw \\
        --audio-dir ~/mukthiguru_attribution_data/audio_archive/wavs \\
        --references ~/mukthiguru_attribution_data/phase2_references_2026-10-30/references.npz \\
        --out-calibration audits/work/v12-shadow-windowed-ecapa-2026-11-17/windowed_calibration.json

    # score
    python backend/scripts/ops/windowed_ecapa_v1_scorer.py \\
        --mode score \\
        --spans-jsonl target_spans.jsonl \\
        --audio-dir ~/mukthiguru_attribution_data/audio_archive/wavs \\
        --references ~/mukthiguru_attribution_data/phase2_references_2026-10-30/references.npz \\
        --windowed-calibration windowed_calibration.json \\
        --out-verdicts-jsonl windowed_verdicts.jsonl \\
        --out-summary windowed_summary.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np

# ---------------------------------------------------------------------------
# Backend root on sys.path so we can import from domain and sibling scripts.
# ---------------------------------------------------------------------------
_BACKEND = Path(__file__).resolve().parents[2]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

# Import ONLY helpers — never copy.
from scripts.ops.regenerate_v10_span_ecapa_verdicts import (  # noqa: E402
    GURU_BY_SPEAKER,
    GURU_IDS,
    TARGET_SAMPLE_RATE,
    _round,
    _sha256_file,
    _unit,
    decide_verdict,
    load_embedder,
    load_references,
    read_slice,
    score_against_references,
    verdict_group,
    wav_header,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
SCRIPT_VERSION = "windowed-ecapa-v1-scorer-v1"
CALIBRATION_SCHEMA = "windowed-ecapa-calibration-v1"
VERDICT_SCHEMA = "windowed-ecapa-span-verdict-v1"
SUMMARY_SCHEMA = "windowed-ecapa-span-summary-v1"

#: Default window / hop (wider than the existing 2s/1s to catch brief host
#: utterances inside a span).
DEFAULT_WINDOW_S = 3.0
DEFAULT_HOP_S = 1.5

#: Silence threshold — same absolute floor as regenerate_v10_span_ecapa_verdicts
#: and speaker_attribution.py.
SILENCE_RMS_FLOOR = 0.01

#: Served-window pad (mirrors services/first_person_pipeline.CITATION_PLAYBACK_PAD_S).
SERVED_PAD_MS = 250

#: Minimum audio length to even attempt windowing.
MIN_CLIP_S = 0.5

#: Maximum negative windows to collect across all diarization files.
MAX_NEGATIVE_WINDOWS = 2000

#: An O/? diarization window whose cosine against ANY teacher reference is ≥
#: this threshold is probably mis-labelled teacher speech (unsupervised
#: clustering puts some teacher windows in the "other" cluster). We exclude
#: them from the negative set so calibration is not inflated by teacher speech
#: masquerading as host speech.
NEGATIVE_COSINE_CONTAMINATION_THRESHOLD = 0.50

#: Minimum negative windows required for calibration to proceed.
MIN_NEGATIVE_WINDOWS = 100

#: FAR target for calibration.
TARGET_FAR = 0.01

#: Verdict strings.
VERDICT_VERIFIED = "verified"
VERDICT_REFUSED_HOST = "refused_host_window"
VERDICT_REFUSED_FLOOR = "refused_below_cosine_floor"
VERDICT_REFUSED_MARGIN = "refused_below_margin"
VERDICT_INDETERMINATE = "indeterminate_no_windows"

#: Group strings.
GROUP_VERIFIED = "verified"
GROUP_REFUSED = "refused"
GROUP_NOT_RUN = "not_run"


# ---------------------------------------------------------------------------
# Pure helpers (testable without torch / audio)
# ---------------------------------------------------------------------------

def is_silent(window_audio: np.ndarray, rms_floor: float = SILENCE_RMS_FLOOR) -> bool:
    """Return True when the window's RMS amplitude is below the floor.

    Pure function: same input always gives the same result.  No I/O.
    """
    if window_audio.size == 0:
        return True
    rms = float(np.sqrt(np.mean(window_audio.astype(np.float64) ** 2)))
    return rms < rms_floor


def windowed_verdict(
    window_scores: list[dict[str, Any]],
    expected_guru: str,
    cosine_floor: float,
    margin_threshold: float,
    max_failing_windows: int = 0,
) -> tuple[str, str, dict[str, Any]]:
    """Span-level verdict from per-window scores.

    Parameters
    ----------
    window_scores:
        List of score dicts, one per *non-silent* window.  Each dict must
        carry ``predicted`` (guru id), ``cosine`` (float), ``margin`` (float).
    expected_guru:
        The guru id the span claims (the claim under test, not evidence).
    cosine_floor, margin_threshold:
        Decision floors from windowed calibration.
    max_failing_windows:
        How many windows may fail before the span is refused.  0 = strict
        (all windows must pass).  Calibration sets this.

    Returns
    -------
    (verdict, reason, stats)
        verdict  ∈ {verified, refused_host_window, refused_below_cosine_floor,
                    refused_below_margin, indeterminate_no_windows}
        group    carried in stats["group"]
    """
    stats: dict[str, Any] = {
        "windows_scored": len(window_scores),
        "windows_failing": 0,
        "max_failing_allowed": max_failing_windows,
    }
    if not window_scores:
        stats["group"] = GROUP_NOT_RUN
        return VERDICT_INDETERMINATE, VERDICT_INDETERMINATE, stats

    cosines = [float(w["cosine"]) for w in window_scores if w.get("cosine") is not None]
    margins = [float(w["margin"]) for w in window_scores if w.get("margin") is not None]
    stats["span_cosine_mean"] = _round(float(np.mean(cosines))) if cosines else None
    stats["span_cosine_min"] = _round(float(np.min(cosines))) if cosines else None
    stats["span_margin_min"] = _round(float(np.min(margins))) if margins else None

    failing: list[tuple[str, str]] = []  # (verdict, reason) per failing window
    for w in window_scores:
        predicted = str(w.get("predicted") or "")
        cosine = w.get("cosine")
        margin = w.get("margin")
        if cosine is None or margin is None or not math.isfinite(cosine):
            failing.append((VERDICT_REFUSED_FLOOR, "embedding_failed"))
            continue
        v, _reason = decide_verdict(
            expected_guru=expected_guru,
            predicted_guru=predicted,
            cosine=float(cosine),
            margin=float(margin),
            cosine_floor=cosine_floor,
            margin_threshold=margin_threshold,
            calibration_available=True,
        )
        if v != VERDICT_VERIFIED:
            failing.append((v, v))

    stats["windows_failing"] = len(failing)

    if len(failing) > max_failing_windows:
        # Classify by the worst failure type.
        failure_types = [v for v, _ in failing]
        if any(v == VERDICT_REFUSED_HOST for v in failure_types) or any(
            "mismatch" in v for v in failure_types
        ):
            verdict = VERDICT_REFUSED_HOST
        elif any(v == VERDICT_REFUSED_FLOOR for v in failure_types):
            verdict = VERDICT_REFUSED_FLOOR
        else:
            verdict = VERDICT_REFUSED_MARGIN
        stats["group"] = GROUP_REFUSED
        return verdict, verdict, stats

    stats["group"] = GROUP_VERIFIED
    return VERDICT_VERIFIED, VERDICT_VERIFIED, stats


def is_verified_windowed_verdict(verdict: object) -> bool:
    """Accept only the scorer's exact positive terminal verdict."""
    return isinstance(verdict, str) and verdict.strip().lower() == VERDICT_VERIFIED


def calibrate_windowed_floor(
    positive_windows: list[dict[str, Any]],
    negative_windows: list[dict[str, Any]],
    target_far: float = TARGET_FAR,
) -> dict[str, Any]:
    """Derive per-window decision floors from positive and negative windows.

    Pure function — takes lists of score dicts, no I/O.

    Parameters
    ----------
    positive_windows:
        Windows from known-verified spans.  Each dict: ``cosine``, ``margin``.
    negative_windows:
        Windows from diarization O/? segments (non-teacher).  Same fields.
    target_far:
        Maximum acceptable false-accept rate on negatives.

    Returns
    -------
    dict with cosine_floor, margin_threshold, far_on_negatives,
    positive_window_pass_rate, roc_auc, max_failing_windows, chosen_rationale.
    """
    if len(negative_windows) < MIN_NEGATIVE_WINDOWS:
        return {
            "calibration_available": False,
            "reason": (
                f"only {len(negative_windows)} negative windows "
                f"(< {MIN_NEGATIVE_WINDOWS}); FAR not measurable"
            ),
        }
    if not positive_windows:
        return {"calibration_available": False, "reason": "no positive windows"}

    neg_cosines = np.asarray([float(w["cosine"]) for w in negative_windows], dtype=np.float64)
    neg_margins = np.asarray([float(w["margin"]) for w in negative_windows], dtype=np.float64)
    pos_cosines = np.asarray([float(w["cosine"]) for w in positive_windows], dtype=np.float64)
    pos_margins = np.asarray([float(w["margin"]) for w in positive_windows], dtype=np.float64)

    # Candidate margin thresholds (teacher-vs-other margin).
    # Margin separates the claimed teacher from the alternative teacher.
    # Standard repository thresholds are 1e-6 (pinned in v10 calibration),
    # 0.05, 0.10, or 0.15 (ANCHOR_MARGIN from speaker_attribution.py).
    candidate_margins = [1e-6, 0.05, 0.10, 0.15]

    # For cosine floor: scan percentiles of negative cosines from p95 up to p100 + eps.
    candidate_cosine_pcts = [95.0, 97.0, 98.0, 99.0, 99.5, 99.9, 100.0]

    best: dict[str, Any] | None = None
    best_frr = 1.0

    for m_floor in candidate_margins:
        for cosine_pct in candidate_cosine_pcts:
            c_floor = float(np.percentile(neg_cosines, cosine_pct)) + 1e-6
            # False accepts on negatives: negative windows that clear BOTH floors.
            fa = int(np.sum((neg_cosines >= c_floor) & (neg_margins >= m_floor)))
            far = fa / len(negative_windows)
            if far > target_far:
                continue
            # False rejects on positives: positive windows that fail EITHER floor.
            fr = int(np.sum((pos_cosines < c_floor) | (pos_margins < m_floor)))
            frr = fr / len(positive_windows)
            if frr < best_frr:
                best_frr = frr
                best = {
                    "cosine_floor": c_floor,
                    "margin_threshold": m_floor,
                    "far_false_accepts": fa,
                    "far_total_negatives": len(negative_windows),
                    "far_rate": far,
                    "frr_false_rejects": fr,
                    "frr_total_positives": len(positive_windows),
                    "frr_rate": frr,
                    "cosine_pct": cosine_pct,
                    "margin_threshold_value": m_floor,
                }

    if best is None:
        # Fallback: strictly above max negative cosine, margin = 1e-6.
        c_floor = float(neg_cosines.max()) + 1e-6
        m_floor = 1e-6
        fa = int(np.sum((neg_cosines >= c_floor) & (neg_margins >= m_floor)))
        fr = int(np.sum((pos_cosines < c_floor) | (pos_margins < m_floor)))
        best = {
            "cosine_floor": c_floor,
            "margin_threshold": m_floor,
            "far_false_accepts": fa,
            "far_total_negatives": len(negative_windows),
            "far_rate": fa / len(negative_windows),
            "frr_false_rejects": fr,
            "frr_total_positives": len(positive_windows),
            "frr_rate": fr / len(positive_windows),
            "cosine_pct": 100.0,
            "margin_threshold_value": m_floor,
        }

    cosine_floor = best["cosine_floor"]
    margin_threshold = best["margin_threshold"]
    positive_pass_rate = 1.0 - best["frr_rate"]

    # ROC AUC approximation (cosine only, trapezoidal).
    roc_auc = _roc_auc(pos_cosines.tolist(), neg_cosines.tolist())

    # Decide max_failing_windows: allow 1 only if span-level FAR stays ≤ target.
    # We approximate by checking how many positive-span groups contain exactly
    # 1 failing window (those would be allowed through with tolerance=1 but
    # blocked with tolerance=0).  Since we don't have span groupings here, we
    # use the conservative default of 0 and note it in the rationale.
    max_failing = 0
    rationale = (
        f"cosine_floor={cosine_floor:.6f} (p{best.get('cosine_pct', 100.0)} of negatives + eps); "
        f"margin_threshold={margin_threshold:.6f}; "
        f"FAR={best['far_rate']:.4f} ({best['far_false_accepts']}/{best['far_total_negatives']}); "
        f"positive_pass_rate={positive_pass_rate:.4f}; "
        f"max_failing_windows=0 (conservative: span-level FAR impact not measurable without "
        f"span groupings in calibrate mode — set to 1 only after dry-run confirms safety)."
    )

    return {
        "calibration_available": True,
        "cosine_floor": float(cosine_floor),
        "margin_threshold": float(margin_threshold),
        "far_on_negatives": {
            "false_accepts": best["far_false_accepts"],
            "total": best["far_total_negatives"],
            "rate": _round(best["far_rate"]),
        },
        "frr_on_positives": {
            "false_rejects": best["frr_false_rejects"],
            "total": best["frr_total_positives"],
            "rate": _round(best["frr_rate"]),
        },
        "positive_window_pass_rate": _round(positive_pass_rate),
        "roc_auc": _round(roc_auc),
        "max_failing_windows": max_failing,
        "chosen_rationale": rationale,
    }


def _roc_auc(pos_scores: list[float], neg_scores: list[float]) -> float:
    """Trapezoidal ROC AUC for a binary classifier on cosine scores."""
    if not pos_scores or not neg_scores:
        return 0.5
    all_scores = sorted(set(pos_scores + neg_scores + [-1.0, 1.0]), reverse=True)
    tprs, fprs = [0.0], [0.0]
    total_pos, total_neg = len(pos_scores), len(neg_scores)
    for thresh in all_scores:
        tp = sum(1 for s in pos_scores if s >= thresh)
        fp = sum(1 for s in neg_scores if s >= thresh)
        tprs.append(tp / total_pos)
        fprs.append(fp / total_neg)
    tprs.append(1.0)
    fprs.append(1.0)
    auc = 0.0
    for i in range(1, len(fprs)):
        auc += (fprs[i] - fprs[i - 1]) * (tprs[i] + tprs[i - 1]) / 2.0
    return float(auc)


# ---------------------------------------------------------------------------
# Audio + embedding helpers
# ---------------------------------------------------------------------------

def _slide_windows(
    audio: np.ndarray,
    window_s: float = DEFAULT_WINDOW_S,
    hop_s: float = DEFAULT_HOP_S,
    sr: int = TARGET_SAMPLE_RATE,
) -> list[np.ndarray]:
    """Slide windows of ``window_s`` seconds with ``hop_s`` stride.

    Returns list of windows.  Windows at the tail that are shorter than
    ``window_s`` are zero-padded to full length so the embedder always receives
    a consistent shape.
    """
    window_frames = int(window_s * sr)
    hop_frames = int(hop_s * sr)
    if audio.size == 0:
        return []
    if audio.size < window_frames:
        padded = np.zeros(window_frames, dtype=np.float32)
        padded[: audio.size] = audio
        return [padded]
    starts = list(range(0, audio.size - window_frames + 1, hop_frames))
    # Include a final tail window if audio extends past the last full hop.
    if starts and starts[-1] + window_frames < audio.size:
        starts.append(audio.size - window_frames)
    return [audio[s : s + window_frames] for s in starts]


def _embed_window(window: np.ndarray, embedder) -> np.ndarray | None:
    """Embed a single window to a L2-normalised ECAPA vector."""
    import torch

    with torch.no_grad():
        batch = torch.from_numpy(window[np.newaxis, :])
        vec = embedder.encode_batch(batch).squeeze(1).detach().cpu().numpy().astype(np.float32)
    return _unit(vec[0]) if vec.shape[0] > 0 else None


def score_span_windows(
    audio: np.ndarray,
    expected_guru: str,
    references: dict[str, np.ndarray],
    embedder,
    window_s: float = DEFAULT_WINDOW_S,
    hop_s: float = DEFAULT_HOP_S,
    rms_floor: float = SILENCE_RMS_FLOOR,
) -> tuple[list[dict[str, Any]], int]:
    """Score each non-silent window in ``audio`` against ``references``.

    Returns (window_scores, silent_skipped_count).
    """
    windows = _slide_windows(audio, window_s=window_s, hop_s=hop_s)
    scores: list[dict[str, Any]] = []
    silent = 0
    for w in windows:
        if is_silent(w, rms_floor):
            silent += 1
            continue
        vec = _embed_window(w, embedder)
        if vec is None:
            # Treat as a failing window (embedding degenerate).
            scores.append({"predicted": "", "cosine": -1.0, "margin": -2.0, "scores": {}})
            continue
        scored = score_against_references(vec, references)
        scores.append(scored)
    return scores, silent


# ---------------------------------------------------------------------------
# Served window (mirrors existing convention)
# ---------------------------------------------------------------------------

def served_window(start_ms: int, end_ms: int, pad_ms: int = SERVED_PAD_MS) -> tuple[int, int]:
    """The window a seeker actually hears (same convention as regenerate script)."""
    return max(0, start_ms - pad_ms), end_ms + pad_ms


# ---------------------------------------------------------------------------
# Canonical JSON + revision helpers
# ---------------------------------------------------------------------------

def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def _calibration_revision(data: dict[str, Any]) -> str:
    # Exclude the revision field itself from the hash to avoid circularity.
    stripped = {k: v for k, v in data.items() if k != "windowed_calibration_revision"}
    return hashlib.sha256(_canonical_json(stripped).encode()).hexdigest()


# ---------------------------------------------------------------------------
# Calibrate mode helpers
# ---------------------------------------------------------------------------

def _load_positive_spans(path: Path) -> list[dict[str, Any]]:
    rows = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        rows.append(json.loads(line))
    return rows


def _load_negative_diar_windows(
    diar_dir: Path,
    audio_dir: Path,
    references: dict[str, np.ndarray],
    embedder,
    window_s: float,
    hop_s: float,
    max_windows: int = MAX_NEGATIVE_WINDOWS,
) -> list[dict[str, Any]]:
    """Extract O/? diarization windows as negative ECAPA embeddings.

    A video qualifies only when it contains at least one K or P window
    (genuinely mixed), so we know the teacher was present.
    """
    neg_windows: list[dict[str, Any]] = []
    files = sorted(diar_dir.glob("*_speaker.json"))
    print(f"  scanning {len(files)} diarization files for negatives …", flush=True)
    for sp_file in files:
        if len(neg_windows) >= max_windows:
            break
        try:
            d = json.loads(sp_file.read_text())
        except Exception:
            continue
        cluster_names: dict[str, str] = d.get("cluster_names") or {}
        win_lab: list[str] = d.get("win_lab") or []
        t_centres: list[float] = d.get("t_centres") or []
        if len(win_lab) != len(t_centres):
            continue
        # Map cluster int→label string; win_lab may already be label strings.
        def _resolve(lab: str) -> str:
            return cluster_names.get(str(lab), str(lab))

        labels = [_resolve(w) for w in win_lab]
        teacher_labels = {"K", "P"}
        if not any(lbl in teacher_labels for lbl in labels):
            continue  # no teacher in this video — skip

        video_id = d.get("video_id") or sp_file.stem.split("_speaker")[0]
        wav_path = audio_dir / f"{video_id}.wav"
        if not wav_path.is_file():
            continue
        hdr = wav_header(wav_path)
        if hdr is None or not hdr.get("audio_complete"):
            continue
        dur_ms = int(hdr["duration_ms"])

        for t_s, lbl in zip(t_centres, labels):
            if len(neg_windows) >= max_windows:
                break
            if lbl not in ("O", "?"):
                continue
            # Extract ±window_s/2 around the diarization centre (clamped).
            half_ms = int(window_s * 1000 / 2)
            w_start = max(0, int(t_s * 1000) - half_ms)
            w_end = min(dur_ms, int(t_s * 1000) + half_ms)
            if w_end - w_start < int(MIN_CLIP_S * 1000):
                continue
            audio, err = read_slice(wav_path, w_start, w_end)
            if audio is None or is_silent(audio):
                continue
            vec = _embed_window(audio, embedder)
            if vec is None:
                continue
            scored = score_against_references(vec, references)
            best_cosine = float(scored["cosine"])
            # Filter: exclude O/? windows that score like teacher speech. The
            # unsupervised diarization clusterer assigns some teacher windows to
            # the "O" (other) cluster when the voice is slightly unusual or at
            # a speaker transition. Including those as negatives would inflate
            # the calibration floor into teacher-speech territory.
            if best_cosine >= NEGATIVE_COSINE_CONTAMINATION_THRESHOLD:
                continue
            neg_windows.append({
                "video_id": video_id,
                "t_s": t_s,
                "diar_label": lbl,
                "cosine": float(scored["cosine"]),
                "margin": float(scored["margin"]),
                "predicted": scored["predicted"],
            })
    print(f"  collected {len(neg_windows)} negative windows", flush=True)
    return neg_windows


def _run_calibrate(args: argparse.Namespace) -> int:
    audio_dir = Path(args.audio_dir).expanduser()
    diar_dir = Path(args.negative_diar_dir).expanduser()
    references_path = Path(args.references).expanduser()
    positive_spans_path = Path(args.positive_spans_jsonl)
    out_path = Path(args.out_calibration)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    model_cache = Path(args.model_cache).expanduser() if args.model_cache else Path.home() / ".cache" / "huggingface"
    print("Loading ECAPA embedder …", flush=True)
    embedder = load_embedder(model_cache, device="auto")
    from scripts.ops.regenerate_v10_span_ecapa_verdicts import _ecapa_revision, resolve_device
    model_revision = _ecapa_revision()
    device = resolve_device("auto")
    print(f"  model revision: {model_revision}, device: {device}", flush=True)

    print("Loading references …", flush=True)
    references = load_references(references_path)
    refs_sha = _sha256_file(references_path)

    print("Loading positive spans …", flush=True)
    pos_spans = _load_positive_spans(positive_spans_path)
    # Sample up to 300 deterministically.
    if len(pos_spans) > 300:
        rng = np.random.default_rng(42)
        idx = rng.choice(len(pos_spans), 300, replace=False)
        pos_spans = [pos_spans[i] for i in sorted(idx)]
    print(f"  {len(pos_spans)} positive spans to window", flush=True)

    cache_dir = out_path.parent / "scratch"
    cache_dir.mkdir(parents=True, exist_ok=True)
    pos_cache = cache_dir / "pos_windows_cache.json"
    neg_cache = cache_dir / "neg_windows_cache.json"

    if pos_cache.is_file() and neg_cache.is_file():
        print(f"Loading cached positive/negative windows from {cache_dir} …", flush=True)
        pos_windows = json.loads(pos_cache.read_text())
        neg_windows = json.loads(neg_cache.read_text())
        print(f"  loaded {len(pos_windows)} pos, {len(neg_windows)} neg windows from cache", flush=True)
    else:
        print("Extracting positive windows …", flush=True)
        pos_windows = []
        for span in pos_spans:
            video_id = str(span.get("video_id") or "")
            start_ms = int(span.get("start_ms") or span.get("audio_start_ms") or 0)
            end_ms = int(span.get("end_ms") or span.get("audio_end_ms") or 0)
            guru_id = str(span.get("guru_id") or "")
            if not video_id or end_ms <= start_ms:
                continue
            wav_path = audio_dir / f"{video_id}.wav"
            w_start, w_end = served_window(start_ms, end_ms)
            audio, err = read_slice(wav_path, w_start, w_end)
            if audio is None:
                continue
            wscores, _silent = score_span_windows(
                audio, guru_id, references, embedder,
                window_s=args.window_s, hop_s=args.hop_s,
            )
            for ws in wscores:
                pos_windows.append({"cosine": ws["cosine"], "margin": ws["margin"], "guru_id": guru_id})
        print(f"  {len(pos_windows)} positive windows collected", flush=True)
        pos_cache.write_text(json.dumps(pos_windows))

        print("Extracting negative windows …", flush=True)
        neg_windows = _load_negative_diar_windows(
            diar_dir, audio_dir, references, embedder,
            window_s=args.window_s, hop_s=args.hop_s,
        )
        neg_cache.write_text(json.dumps(neg_windows))

    print("Calibrating …", flush=True)
    result = calibrate_windowed_floor(pos_windows, neg_windows, target_far=args.target_far)
    if not result.get("calibration_available"):
        print(f"ERROR: calibration failed: {result.get('reason')}", file=sys.stderr)
        return 1

    # Load pinned calibration revision for traceability.
    pinned_cal_rev = ""
    if args.pinned_calibration:
        try:
            pc = json.loads(Path(args.pinned_calibration).expanduser().read_text())
            pinned_cal_rev = str(pc.get("calibration_revision") or "")
        except Exception:
            pass

    artifact: dict[str, Any] = {
        "schema": CALIBRATION_SCHEMA,
        "script_version": SCRIPT_VERSION,
        "window_w_s": args.window_s,
        "window_h_s": args.hop_s,
        "silence_rms_floor": SILENCE_RMS_FLOOR,
        "positive_spans": len(pos_spans),
        "positive_windows": len(pos_windows),
        "negative_windows": len(neg_windows),
        "model_revision": model_revision,
        "device": device,
        "references_sha256": refs_sha,
        "pinned_calibration_revision": pinned_cal_rev,
        **result,
    }
    rev = _calibration_revision(artifact)
    artifact["windowed_calibration_revision"] = rev
    out_path.write_text(json.dumps(artifact, indent=2))
    print(f"Calibration written → {out_path}")
    print(f"  cosine_floor={result['cosine_floor']:.6f}  "
          f"margin_threshold={result['margin_threshold']:.6f}")
    print(f"  FAR={result['far_on_negatives']['rate']:.4f}  "
          f"positive_pass_rate={result['positive_window_pass_rate']:.4f}  "
          f"ROC-AUC={result['roc_auc']:.4f}")
    return 0


# ---------------------------------------------------------------------------
# Score mode
# ---------------------------------------------------------------------------

def _load_windowed_calibration(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text())
    if not data.get("calibration_available"):
        raise ValueError(f"windowed calibration at {path} reports calibration_available=false")
    for key in ("cosine_floor", "margin_threshold"):
        if not isinstance(data.get(key), (int, float)):
            raise ValueError(f"windowed calibration missing {key}")
    return data


def _load_spans_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        rows.append(json.loads(line))
    return rows


def _run_score(args: argparse.Namespace) -> int:
    audio_dir = Path(args.audio_dir).expanduser()
    references_path = Path(args.references).expanduser()
    cal_path = Path(args.windowed_calibration)
    spans_path = Path(args.spans_jsonl)
    out_verdicts = Path(args.out_verdicts_jsonl)
    out_summary_path = Path(args.out_summary)

    out_verdicts.parent.mkdir(parents=True, exist_ok=True)
    out_summary_path.parent.mkdir(parents=True, exist_ok=True)

    model_cache = Path(args.model_cache).expanduser() if args.model_cache else Path.home() / ".cache" / "huggingface"

    print("Loading windowed calibration …", flush=True)
    cal = _load_windowed_calibration(cal_path)
    cosine_floor = float(cal["cosine_floor"])
    margin_threshold = float(cal["margin_threshold"])
    max_failing = int(cal.get("max_failing_windows", 0))
    windowed_cal_rev = str(cal.get("windowed_calibration_revision") or "")
    pinned_cal_rev = str(cal.get("pinned_calibration_revision") or "")

    print("Loading references …", flush=True)
    references = load_references(references_path)

    print("Loading ECAPA embedder …", flush=True)
    embedder = load_embedder(model_cache, device="auto")
    from scripts.ops.regenerate_v10_span_ecapa_verdicts import _ecapa_revision, resolve_device
    model_revision = _ecapa_revision()
    device = resolve_device("auto")

    print("Loading spans …", flush=True)
    spans = _load_spans_jsonl(spans_path)
    print(f"  {len(spans)} spans to score", flush=True)

    counts: Counter[str] = Counter()
    audio_failures: Counter[str] = Counter()

    with out_verdicts.open("w") as vfh:
        for i, span in enumerate(spans):
            if (i + 1) % 100 == 0:
                print(f"  scored {i+1}/{len(spans)} …", flush=True)

            span_id = str(span.get("source_span_id") or "")
            video_id = str(span.get("video_id") or "")
            speaker_id = str(span.get("speaker_id") or "").strip().casefold()
            from scripts.ops.regenerate_v10_span_ecapa_verdicts import GURU_BY_SPEAKER
            expected_guru = GURU_BY_SPEAKER.get(speaker_id, "")
            start_ms = int(span.get("start_ms") or span.get("audio_start_ms") or 0)
            end_ms = int(span.get("end_ms") or span.get("audio_end_ms") or 0)

            wav_path = audio_dir / f"{video_id}.wav"
            w_start, w_end = served_window(start_ms, end_ms)
            audio, err = read_slice(wav_path, w_start, w_end)

            row: dict[str, Any] = {
                "schema": VERDICT_SCHEMA,
                "source_span_id": span_id,
                "video_id": video_id,
                "guru_id": expected_guru,
                "audio_start_ms": w_start,
                "audio_end_ms": w_end,
                "window_w_s": args.window_s,
                "window_h_s": args.hop_s,
                "windowed_calibration_revision": windowed_cal_rev,
                "pinned_calibration_revision": pinned_cal_rev,
                "model_revision": model_revision,
                "device": device,
            }

            if audio is None:
                audio_failures[err or "unknown"] += 1
                row.update({
                    "windows_total": 0, "windows_silent_skipped": 0,
                    "windows_scored": 0, "windows_failing": 0,
                    "max_failing_allowed": max_failing,
                    "span_verdict": VERDICT_INDETERMINATE,
                    "span_reason": err or "audio_failure",
                    "span_cosine_mean": None, "span_cosine_min": None,
                    "span_margin_min": None,
                    "verdict_group": GROUP_NOT_RUN,
                    "window_check": "indeterminate",
                })
                counts[GROUP_NOT_RUN] += 1
                vfh.write(json.dumps(row) + "\n")
                continue

            if not expected_guru:
                row.update({
                    "windows_total": 0, "windows_silent_skipped": 0,
                    "windows_scored": 0, "windows_failing": 0,
                    "max_failing_allowed": max_failing,
                    "span_verdict": VERDICT_INDETERMINATE,
                    "span_reason": "unknown_guru",
                    "span_cosine_mean": None, "span_cosine_min": None,
                    "span_margin_min": None,
                    "verdict_group": GROUP_NOT_RUN,
                    "window_check": "indeterminate",
                })
                counts[GROUP_NOT_RUN] += 1
                vfh.write(json.dumps(row) + "\n")
                continue

            wscores, silent_count = score_span_windows(
                audio, expected_guru, references, embedder,
                window_s=args.window_s, hop_s=args.hop_s,
            )
            all_windows = _slide_windows(audio, window_s=args.window_s, hop_s=args.hop_s)
            verdict, reason, stats = windowed_verdict(
                wscores, expected_guru, cosine_floor, margin_threshold, max_failing
            )

            group = stats["group"]
            counts[group] += 1

            row.update({
                "windows_total": len(all_windows),
                "windows_silent_skipped": silent_count,
                "windows_scored": stats["windows_scored"],
                "windows_failing": stats["windows_failing"],
                "max_failing_allowed": max_failing,
                "span_verdict": verdict,
                "span_reason": reason,
                "span_cosine_mean": stats.get("span_cosine_mean"),
                "span_cosine_min": stats.get("span_cosine_min"),
                "span_margin_min": stats.get("span_margin_min"),
                "verdict_group": group,
                "window_check": "pass" if group == GROUP_VERIFIED else (
                    "fail" if group == GROUP_REFUSED else "indeterminate"
                ),
            })
            vfh.write(json.dumps(row) + "\n")

    summary: dict[str, Any] = {
        "schema": SUMMARY_SCHEMA,
        "script_version": SCRIPT_VERSION,
        "spans_scored": len(spans),
        "by_group": dict(counts),
        "audio_failures": dict(audio_failures),
        "windowed_calibration_revision": windowed_cal_rev,
        "pinned_calibration_revision": pinned_cal_rev,
        "cosine_floor": cosine_floor,
        "margin_threshold": margin_threshold,
        "max_failing_windows": max_failing,
        "window_w_s": args.window_s,
        "window_h_s": args.hop_s,
    }
    out_summary_path.write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    ap.add_argument("--mode", choices=["calibrate", "score"], required=True)
    ap.add_argument("--window-s", type=float, default=DEFAULT_WINDOW_S, dest="window_s")
    ap.add_argument("--hop-s", type=float, default=DEFAULT_HOP_S, dest="hop_s")
    ap.add_argument("--target-far", type=float, default=TARGET_FAR, dest="target_far")
    ap.add_argument("--model-cache", default="", dest="model_cache")
    ap.add_argument("--audio-dir", default="")
    ap.add_argument("--references", default="")

    # calibrate-mode args
    ap.add_argument("--positive-spans-jsonl", default="", dest="positive_spans_jsonl")
    ap.add_argument("--negative-diar-dir", default="", dest="negative_diar_dir")
    ap.add_argument("--pinned-calibration", default="", dest="pinned_calibration")
    ap.add_argument("--out-calibration", default="", dest="out_calibration")

    # score-mode args
    ap.add_argument("--spans-jsonl", default="", dest="spans_jsonl")
    ap.add_argument("--windowed-calibration", default="", dest="windowed_calibration")
    ap.add_argument("--out-verdicts-jsonl", default="", dest="out_verdicts_jsonl")
    ap.add_argument("--out-summary", default="", dest="out_summary")
    return ap


def main(argv: list[str] | None = None) -> int:
    ap = _build_parser()
    args = ap.parse_args(argv)
    if args.mode == "calibrate":
        for required in ("positive_spans_jsonl", "negative_diar_dir", "audio_dir",
                         "references", "out_calibration"):
            if not getattr(args, required):
                ap.error(f"--mode calibrate requires --{required.replace('_', '-')}")
        return _run_calibrate(args)
    else:
        for required in ("spans_jsonl", "audio_dir", "references",
                         "windowed_calibration", "out_verdicts_jsonl", "out_summary"):
            if not getattr(args, required):
                ap.error(f"--mode score requires --{required.replace('_', '-')}")
        return _run_score(args)


if __name__ == "__main__":
    raise SystemExit(main())
