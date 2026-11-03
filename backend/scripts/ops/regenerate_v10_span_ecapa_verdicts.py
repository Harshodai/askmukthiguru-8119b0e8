#!/usr/bin/env python3
"""Regenerate per-span ECAPA speaker evidence for the first-person v10 candidate.

**Read-only.** This script never writes to Qdrant, never edits a payload, never
sets ``speaker_verified``, never touches Redis, Docker or Railway. It emits
three new versioned artifacts: a calibration record, one verdict row per
candidate span, and a machine-readable summary.

Why this exists
---------------
``docs/FIRST_PERSON_PUBLIC_RELEASE_STATUS_2026-10-21.md`` blocker **B1**: the
archived verdict archive (``.work/fp_context/speaker_verdicts.json``) carries
1,173 ECAPA verdicts keyed by legacy v9 point ids, has **no** ``cosine_floor``,
has **no** ``calibration_available``, and its ``threshold`` (0.4668) is the p01
of the *margin* distribution of **correct** clips rather than a
false-accept-measured floor. Its false-accept rate is therefore unknown, and
``build_full_corpus_v10.py::load_calibration`` already refuses to consume it.

What this script does differently
---------------------------------
* It works on the **Phase 3 exact candidate** (1,600 spans), never on the live
  payload's coordinates, and never on a legacy v9 clip window.
* It slices audio **only** from ``audio_archive/wavs/{video_id}.wav``. The
  ASR-root ``audio/`` directories hold 86-byte header-only stubs whose declared
  duration has no PCM behind it; a slice justified by such a header points at
  silence that is not there.
* It builds the guru references from the repository's only human ground truth —
  the two human-confirmed anchor moments recorded in
  ``backend/scripts/ops/speaker_attribution.py`` — recomputed with a **pinned**
  ECAPA revision, not from ``speaker_verified=true`` payload flags and not from
  a display label.
* It calibrates the decision floors on a **held-out** impostor set and
  measures the false-accept / false-reject rates on a second held-out split.
* Every row is keyed by ``source_span_id``; the legacy v9 point id never
  appears as a key.

Audio reading
-------------
The standard library ``wave`` module is used; ``soundfile`` is **not** required
(every file in ``audio_archive/wavs/`` is 16-bit PCM, mono, 16 kHz). ``torch``,
``speechbrain`` and ``scikit-learn`` are imported lazily inside the functions
that need them, so the app import graph and the test suite never depend on the
heavy audio stack.

Served-span mode (``--spans-jsonl``)
------------------------------------
The candidate mode above scores the Phase 3 *reconstruction* window. A span that
is already live is served at a different window: the citation player adds
``CITATION_PLAYBACK_PAD_S`` (0.25 s) on both sides
(``backend/services/first_person_pipeline.py``), so the seeker hears
``[start_ms - 250, end_ms + 250]``. Verifying the reconstruction window says
nothing about the audio behind the served window, and a verdict written against
the wrong window is not evidence for what is played.

``--spans-jsonl`` therefore scores exactly the served window, reusing the
**already pinned** calibration artifact (``--calibration``) rather than fitting
new floors on the spans under test. It emits one row per ``source_span_id`` and
writes no collection: the write path is
``scripts/ops/backfill_v10_voice_method.py``.

Usage
-----
    python -m scripts.ops.regenerate_v10_span_ecapa_verdicts \\
        --candidate audits/evidence/public_release_phase3_candidate_2026-10-21.jsonl \\
        --quarantine audits/evidence/public_release_phase3_quarantine_2026-10-21.jsonl \\
        --audio-dir ~/mukthiguru_attribution_data/audio_archive/wavs \\
        --out-verdicts audits/evidence/public_release_phase2_verdicts_2026-10-22.json \\
        --out-verdicts-jsonl audits/evidence/public_release_phase2_verdicts_2026-10-22.jsonl \\
        --out-calibration audits/evidence/public_release_phase2_calibration_2026-10-22.json \\
        --out-summary audits/evidence/public_release_phase2_summary_2026-10-22.json

    # served-window mode: score live spans against the pinned calibration
    python -m scripts.ops.regenerate_v10_span_ecapa_verdicts \\
        --spans-jsonl spans.jsonl \\
        --audio-dir ~/mukthiguru_attribution_data/audio_archive/wavs \\
        --calibration <pinned calibration JSON> \\
        --references <references.npz from a candidate-mode run> \\
        --out-verdicts-jsonl served_verdicts.jsonl
"""

from __future__ import annotations

import argparse
import ast
import datetime as _dt
import hashlib
import json
import math
import sys
import wave
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np

SCRIPT_VERSION = "regenerate-v10-span-ecapa-verdicts-v1"
VERDICT_SCHEMA = "first-person-v10-ecapa-span-verdict-v1"
VERDICT_INDEX_SCHEMA = "first-person-v10-ecapa-verdict-index-v1"
CALIBRATION_SCHEMA = "first-person-v10-ecapa-calibration-v1"
SUMMARY_SCHEMA = "first-person-v10-ecapa-phase2-summary-v1"
SPAN_VERDICT_SCHEMA = "first-person-v10-ecapa-served-span-verdict-v1"
SPAN_SUMMARY_SCHEMA = "first-person-v10-ecapa-served-span-summary-v1"

# ---------------------------------------------------------------------------
# Model / recipe constants
# ---------------------------------------------------------------------------
ECAPA_MODEL_ID = "speechbrain/spkrec-ecapa-voxceleb"
#: Fallback pin. ``backend/scripts/download_models.py::_MODEL_REVISIONS`` is the
#: authority; the literal is only used when that module cannot be imported.
ECAPA_REVISION_FALLBACK = "0f99f2d0ebe89ac095bcc5903c4dd8f72b367286"

TARGET_SAMPLE_RATE = 16000
TARGET_CHANNELS = 1
TARGET_BITS = 16

#: Window recipe inherited from ``backend/scripts/ops/speaker_attribution.py``
#: (``WIN_S = 2.0``, default ``hop = 1.0``). Not re-tuned on this corpus.
WINDOW_SECONDS = 2.0
HOP_SECONDS = 1.0

#: Minimum usable slice. A slice shorter than this cannot carry a 2 s window.
MIN_CLIP_SECONDS = 0.4

#: The pad the citation player adds on both sides of a span, mirroring
#: ``services/first_person_pipeline.CITATION_PLAYBACK_PAD_S`` (0.25 s). A served
#: window is ``[start_ms - SERVED_PAD_MS, end_ms + SERVED_PAD_MS]``, clamped at 0.
SERVED_PAD_MS = 250

#: Clustering / assignment constants inherited unchanged from
#: ``backend/scripts/ops/speaker_attribution.py``. They are cited, not fitted.
CLUSTER_DISTANCE = 0.6
ENROLL_MIN = 0.75
COHORT_MAX = 0.40
ANCHOR_MARGIN = 0.15
#: ``speaker_attribution.py::THRESHOLD_FLOOR``. A held-out slice is *labelled*
#: with an anchor voiceprint only when it clears that floor against the anchor
#: **and** beats the other anchor by ``ANCHOR_MARGIN``. Below it the slice is
#: not a trial: it is either a non-teacher voice or an undecidable one.
ANCHOR_LABEL_MIN = 0.55

#: Human-confirmed anchor moments. Copied from
#: ``backend/scripts/ops/speaker_attribution.py::ANCHORS`` (user listened and
#: confirmed, 2026-09-22). This is the only human ground truth in the repo.
ANCHORS: dict[str, tuple[str, float]] = {
    "preethaji": ("hUmlujE6SN0", 563.0),
    "krishnaji": ("rGcNJ_Nsuy8", 386.0),
}

#: The registry ids a span's expected guru may take. A display label
#: ("Sri Krishnaji") is never accepted as an expected guru.
GURU_IDS = frozenset(ANCHORS)

#: A live span carries a display ``speaker_id``, not a registry id. This is the
#: same label -> registry map ``scripts/ops/score_v10_unchecked_speakers.py``
#: uses (``_TEACHER_CODES``); an unmapped label is rejected at load time rather
#: than guessed, because the expected guru is the claim under test.
GURU_BY_SPEAKER = {
    "sri preethaji": "preethaji",
    "sri krishnaji": "krishnaji",
    "preethaji": "preethaji",
    "krishnaji": "krishnaji",
}

#: Fields a ``--spans-jsonl`` row must carry.
SPAN_REQUIRED_FIELDS = (
    "point_id",
    "source_span_id",
    "video_id",
    "start_ms",
    "end_ms",
    "speaker_id",
)

#: Below this many held-out impostor trials the false-accept rate is not
#: measurable and the calibration must fail closed.
MIN_IMPOSTOR_TRIALS = 20

#: Deterministic video split.
SPLIT_SALT = "fp-phase2-split-v1"
SPLIT_BOUNDS = (("train", 0.60), ("calibration", 0.20), ("test", 0.20))

#: Verdict categories. ``verdict`` carries the specific category, ``verdict_group``
#: carries verified / refused / not_run.
VERDICT_VERIFIED = "verified"
VERDICT_REFUSED_BELOW_COSINE_FLOOR = "refused_below_cosine_floor"
VERDICT_REFUSED_BELOW_MARGIN = "refused_below_margin"
VERDICT_REFUSED_GURU_MISMATCH = "refused_guru_mismatch"
VERDICT_MISSING_AUDIO = "missing_audio"
VERDICT_INVALID_AUDIO = "invalid_audio"
VERDICT_OUT_OF_BOUNDS = "out_of_bounds"
VERDICT_TOO_SHORT = "too_short"
VERDICT_CALIBRATION_UNAVAILABLE = "calibration_unavailable"
VERDICT_NOT_RUN = "not_run"

VERDICT_CATEGORIES = (
    VERDICT_VERIFIED,
    VERDICT_REFUSED_BELOW_COSINE_FLOOR,
    VERDICT_REFUSED_BELOW_MARGIN,
    VERDICT_REFUSED_GURU_MISMATCH,
    VERDICT_MISSING_AUDIO,
    VERDICT_INVALID_AUDIO,
    VERDICT_OUT_OF_BOUNDS,
    VERDICT_TOO_SHORT,
    VERDICT_CALIBRATION_UNAVAILABLE,
    VERDICT_NOT_RUN,
)

#: Categories that mean "the audio itself was unusable" — the span is not
#: refused on speaker grounds, it simply has no evidence.
AUDIO_FAILURE_CATEGORIES = frozenset(
    {
        VERDICT_MISSING_AUDIO,
        VERDICT_INVALID_AUDIO,
        VERDICT_OUT_OF_BOUNDS,
        VERDICT_TOO_SHORT,
    }
)

EXIT_OK = 0
EXIT_RELEASE_BLOCKED = 1
EXIT_INVALID_INPUT = 2


class InputError(Exception):
    """Raised when an input cannot be trusted. Always fatal (exit 2)."""


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------
def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def _finite(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )


def _round(value: float, digits: int = 6) -> float:
    return round(float(value), digits)


def _ecapa_revision() -> str:
    """The pinned ECAPA revision from the repository's model-pin registry.

    ``backend/scripts/download_models.py`` is **not** imported: it has
    module-level side effects (it downloads and loads several sentence
    transformers and rewrites ``HF_HOME`` to the container path ``/app``), so
    importing it would pull gigabytes and fail on a read-only root. The pin
    table is read with :mod:`ast` instead — no execution, no side effect.
    """
    registry = Path(__file__).resolve().parents[1] / "download_models.py"
    try:
        tree = ast.parse(registry.read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        return ECAPA_REVISION_FALLBACK
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        targets = [target.id for target in node.targets if isinstance(target, ast.Name)]
        if "_MODEL_REVISIONS" not in targets:
            continue
        try:
            table = ast.literal_eval(node.value)
        except (ValueError, TypeError):
            continue
        if isinstance(table, dict):
            revision = table.get(ECAPA_MODEL_ID)
            if isinstance(revision, str) and revision:
                return revision
    return ECAPA_REVISION_FALLBACK


# ---------------------------------------------------------------------------
# RIFF/WAVE inspection (standard library only)
# ---------------------------------------------------------------------------
def wav_header(path: Path) -> dict[str, Any] | None:
    """Parse a RIFF/WAVE header without any third-party dependency.

    Returns the declared format plus ``audio_complete``: a header-only stub
    declares a correct duration with **no PCM behind it**, so it must never
    justify a citation window or an ECAPA slice.
    """
    try:
        file_size = path.stat().st_size
        with path.open("rb") as handle:
            header = handle.read(12)
            if len(header) < 12 or header[0:4] != b"RIFF" or header[8:12] != b"WAVE":
                return None
            channels = sample_rate = bits = None
            data_bytes: int | None = None
            data_offset: int | None = None
            offset = 12
            while True:
                handle.seek(offset)
                chunk_header = handle.read(8)
                if len(chunk_header) < 8:
                    break
                chunk_id = chunk_header[0:4]
                chunk_size = int.from_bytes(chunk_header[4:8], "little")
                body_offset = offset + 8
                if chunk_id == b"fmt ":
                    fmt = handle.read(min(chunk_size, 16))
                    if len(fmt) >= 16:
                        channels = int.from_bytes(fmt[2:4], "little")
                        sample_rate = int.from_bytes(fmt[4:8], "little")
                        bits = int.from_bytes(fmt[14:16], "little")
                elif chunk_id == b"data":
                    data_bytes = chunk_size
                    data_offset = body_offset
                    break
                offset = body_offset + chunk_size + (chunk_size % 2)
    except OSError:
        return None

    if not sample_rate or not channels or not bits or data_bytes is None:
        return None
    bytes_per_second = float(sample_rate) * float(channels) * (float(bits) / 8.0)
    if bytes_per_second <= 0:
        return None
    duration_ms = int(round((float(data_bytes) / bytes_per_second) * 1000.0))
    present = data_offset is not None and (file_size - data_offset) >= data_bytes
    return {
        "path": str(path),
        "sample_rate": int(sample_rate),
        "channels": int(channels),
        "bits_per_sample": int(bits),
        "data_bytes": int(data_bytes),
        "data_offset": data_offset,
        "file_bytes": int(file_size),
        "duration_ms": duration_ms,
        "audio_complete": bool(present),
    }


def read_slice(path: Path, start_ms: int, end_ms: int) -> tuple[np.ndarray | None, str | None]:
    """Read ``[start_ms, end_ms)`` of a PCM WAV.

    Returns ``(audio, None)`` on success or ``(None, reason)`` where reason is
    one of ``missing_audio`` / ``invalid_audio`` / ``out_of_bounds`` /
    ``too_short``.
    """
    if not path.is_file():
        return None, VERDICT_MISSING_AUDIO
    header = wav_header(path)
    if header is None:
        return None, VERDICT_INVALID_AUDIO
    if not header["audio_complete"]:
        # A header-only stub: the declared duration exists but there is no audio.
        return None, VERDICT_INVALID_AUDIO
    if (
        header["sample_rate"] != TARGET_SAMPLE_RATE
        or header["channels"] != TARGET_CHANNELS
        or header["bits_per_sample"] != TARGET_BITS
    ):
        return None, VERDICT_INVALID_AUDIO
    if start_ms < 0 or end_ms < 0:
        return None, VERDICT_OUT_OF_BOUNDS
    if end_ms > int(header["duration_ms"]):
        return None, VERDICT_OUT_OF_BOUNDS
    if end_ms <= start_ms:
        return None, VERDICT_TOO_SHORT

    start_frame = int(round(start_ms * TARGET_SAMPLE_RATE / 1000.0))
    end_frame = int(round(end_ms * TARGET_SAMPLE_RATE / 1000.0))
    frames = end_frame - start_frame
    if frames <= 0:
        return None, VERDICT_TOO_SHORT
    try:
        with wave.open(str(path), "rb") as handle:
            handle.setpos(start_frame)
            raw = handle.readframes(frames)
    except Exception:
        return None, VERDICT_INVALID_AUDIO
    if len(raw) < frames * 2:
        return None, VERDICT_INVALID_AUDIO
    audio = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
    if audio.size < int(MIN_CLIP_SECONDS * TARGET_SAMPLE_RATE):
        return None, VERDICT_TOO_SHORT
    return audio, None


def read_whole_mono(path: Path) -> np.ndarray | None:
    """Read a whole mono 16 kHz 16-bit WAV (used for the anchor videos)."""
    header = wav_header(path)
    if header is None or not header["audio_complete"]:
        return None
    if (
        header["sample_rate"] != TARGET_SAMPLE_RATE
        or header["channels"] != TARGET_CHANNELS
        or header["bits_per_sample"] != TARGET_BITS
    ):
        return None
    try:
        with wave.open(str(path), "rb") as handle:
            raw = handle.readframes(handle.getnframes())
    except Exception:
        return None
    if len(raw) < header["data_bytes"]:
        return None
    return np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0


# ---------------------------------------------------------------------------
# ECAPA embedding
# ---------------------------------------------------------------------------
def resolve_device(device: str) -> str:
    """Resolve ``auto`` to the concrete torch device that will be used."""
    if device != "auto":
        return device
    try:
        import torch

        return "mps" if torch.backends.mps.is_available() else "cpu"
    except Exception:
        return "cpu"


def load_embedder(cache_dir: Path, device: str = "auto"):
    """Load the pinned ECAPA-TDNN speaker encoder.

    ``device="auto"`` routes to Apple Silicon's MPS backend when it is
    available, which is the binding host rule (``lessons.md`` →
    ``L-MPS-ECAPA-1``: CPU forward passes took ~7 minutes per video, MPS takes
    1.5–15 s). The device is part of the embedding cache key and is recorded in
    every artifact, so a CPU run and an MPS run are never silently mixed.
    """
    from huggingface_hub import snapshot_download
    from speechbrain.inference.speaker import SpeakerRecognition

    if device == "auto":
        try:
            import torch

            device = "mps" if torch.backends.mps.is_available() else "cpu"
        except Exception:
            device = "cpu"
    repo_dir = snapshot_download(repo_id=ECAPA_MODEL_ID, revision=_ecapa_revision())
    return SpeakerRecognition.from_hparams(
        source=repo_dir,
        savedir=str(cache_dir / "ecapa"),
        run_opts={"device": device},
    )


def _window_vectors(audio: np.ndarray, embedder) -> tuple[np.ndarray, np.ndarray]:
    """One ECAPA vector per 2 s window (1 s hop), skipping silent windows.

    Returns ``(vectors, start_seconds)``. The silence floor is the
    repository's absolute floor (RMS > 0.01), copied from
    ``speaker_attribution.py::embed_windows``; a *relative* floor there
    silently dropped ~45 % of the speech. The window start times travel with
    the vectors so an anchor moment can be located in the *filtered* window
    list rather than in the unfiltered one.
    """
    import torch

    window = int(WINDOW_SECONDS * TARGET_SAMPLE_RATE)
    hop = int(HOP_SECONDS * TARGET_SAMPLE_RATE)
    if audio.size < window:
        padded = np.zeros(window, dtype=np.float32)
        padded[: audio.size] = audio
        windows = [padded]
        starts = [0]
    else:
        starts = list(range(0, audio.size - window + 1, hop))
        windows = [audio[start : start + window] for start in starts]
    rms = np.array([float(np.sqrt(np.mean(w**2))) for w in windows])
    keep = rms > 0.01
    if not keep.any():
        keep = np.ones(len(windows), dtype=bool)
    kept = [w for w, flag in zip(windows, keep) if flag]
    kept_starts = [s for s, flag in zip(starts, keep) if flag]
    vectors: list[np.ndarray] = []
    with torch.no_grad():
        for index in range(0, len(kept), 64):
            batch = torch.from_numpy(np.stack(kept[index : index + 64]))
            embedded = (
                embedder.encode_batch(batch).squeeze(1).detach().cpu().numpy().astype(np.float32)
            )
            vectors.append(embedded)
    times = np.asarray(kept_starts, dtype=np.float64) / TARGET_SAMPLE_RATE
    return np.concatenate(vectors, axis=0), times


def _unit(vector: np.ndarray) -> np.ndarray | None:
    norm = float(np.linalg.norm(vector))
    if norm <= 0 or not math.isfinite(norm):
        return None
    return (vector / norm).astype(np.float32)


def embed_slice(audio: np.ndarray, embedder) -> np.ndarray | None:
    """Mean-pool a slice's window vectors into one L2-normalized vector."""
    windows, _times = _window_vectors(audio, embedder)
    if windows.size == 0:
        return None
    return _unit(windows.mean(axis=0))


def anchor_voiceprint(
    audio: np.ndarray, anchor_seconds: float, embedder
) -> tuple[np.ndarray | None, dict[str, Any]]:
    """Build one guru's anchor voiceprint from the human-confirmed moment.

    Uses the repository's own recipe: cluster the video's 2 s windows, take the
    cluster the confirmed moment belongs to, and average that cluster.
    """
    from sklearn.cluster import AgglomerativeClustering

    windows, times = _window_vectors(audio, embedder)
    info: dict[str, Any] = {"window_count": int(windows.shape[0])}
    if windows.shape[0] < 2:
        info["reason"] = "too_few_windows"
        return None, info
    labels = AgglomerativeClustering(
        n_clusters=None,
        distance_threshold=CLUSTER_DISTANCE,
        metric="cosine",
        linkage="average",
    ).fit_predict(windows)
    index = int(np.argmin(np.abs(times - anchor_seconds)))
    cluster = int(labels[index])
    members = windows[labels == cluster]
    info["cluster_id"] = cluster
    info["cluster_windows"] = int(members.shape[0])
    info["anchor_window_index"] = index
    info["anchor_window_seconds"] = _round(float(times[index]))
    vector = _unit(members.mean(axis=0))
    if vector is None:
        info["reason"] = "degenerate_cluster"
    return vector, info


# ---------------------------------------------------------------------------
# Deterministic split
# ---------------------------------------------------------------------------
def assign_split(video_id: str) -> str:
    """Deterministic, video-level split.

    The two human-confirmed anchor videos are forced into ``train``: they seed
    the reference centroids, so they can never be part of a held-out trial.
    """
    if video_id in {vid for vid, _moment in ANCHORS.values()}:
        return "train"
    digest = hashlib.sha256(f"{SPLIT_SALT}|{video_id}".encode()).hexdigest()
    value = int(digest[:8], 16) / 0xFFFFFFFF
    cumulative = 0.0
    for name, weight in SPLIT_BOUNDS:
        cumulative += weight
        if value < cumulative:
            return name
    return SPLIT_BOUNDS[-1][0]


# ---------------------------------------------------------------------------
# Input loading
# ---------------------------------------------------------------------------
def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise InputError(f"cannot read {path}: {exc}") from exc
    for number, line in enumerate(text.splitlines(), 1):
        stripped = line.strip()
        if not stripped:
            continue
        try:
            row = json.loads(stripped)
        except json.JSONDecodeError as exc:
            raise InputError(f"{path}: line {number} is not valid JSON: {exc}") from exc
        if not isinstance(row, dict):
            raise InputError(f"{path}: line {number} is not a JSON object")
        rows.append(row)
    return rows


def load_candidate(path: Path, expected_spans: int) -> list[dict[str, Any]]:
    """Load the Phase 3 exact candidate and assert its shape."""
    rows = load_jsonl(path)
    if not rows:
        raise InputError(f"{path}: no candidate spans")
    if len(rows) != expected_spans:
        raise InputError(
            f"{path}: expected {expected_spans} exact candidate spans, found {len(rows)}"
        )
    seen: set[str] = set()
    for index, row in enumerate(rows):
        span_id = str(row.get("source_span_id") or "")
        if not span_id:
            raise InputError(f"{path}: row {index} has no source_span_id")
        if span_id in seen:
            raise InputError(f"{path}: duplicate source_span_id {span_id!r} at row {index}")
        seen.add(span_id)
        if not str(row.get("video_id") or ""):
            raise InputError(f"{path}: row {index} has no video_id")
        if str(row.get("guru_id") or "") not in GURU_IDS:
            raise InputError(
                f"{path}: row {index} has an unusable expected guru {row.get('guru_id')!r}"
            )
        for field in ("audio_start_ms", "audio_end_ms"):
            value = row.get(field)
            if not isinstance(value, int) or isinstance(value, bool):
                raise InputError(f"{path}: row {index} has a non-integer {field}")
        if int(row["audio_end_ms"]) <= int(row["audio_start_ms"]):
            raise InputError(f"{path}: row {index} has audio_end_ms <= audio_start_ms")
    return rows


def load_quarantine(path: Path, expected_rows: int) -> tuple[list[dict[str, Any]], set[str], int]:
    """Load the Phase 3 quarantine file.

    Returns ``(rows, source_span_ids, rows_without_id)``. Ten quarantined spans
    (``span_not_located_in_asr``) never got a rebuilt span id at all, so the
    row count and the unique-id count are different numbers and both are
    reported.
    """
    rows = load_jsonl(path)
    if expected_rows and len(rows) != expected_rows:
        raise InputError(f"{path}: expected {expected_rows} quarantined spans, found {len(rows)}")
    ids = {
        str(row.get("source_span_id") or "") for row in rows if str(row.get("source_span_id") or "")
    }
    without_id = sum(1 for row in rows if not str(row.get("source_span_id") or ""))
    return rows, ids, without_id


# ---------------------------------------------------------------------------
# Served-span inputs
# ---------------------------------------------------------------------------
def served_window(start_ms: int, end_ms: int, pad_ms: int = SERVED_PAD_MS) -> tuple[int, int]:
    """The window a seeker actually hears for a span.

    Pure: same inputs always give the same bounds, no audio needed. The start is
    clamped at zero because a negative offset is not addressable; the end is not
    clamped here (an end past the file is an ``out_of_bounds`` audio failure, not
    a silently shortened window).
    """
    start = max(0, int(start_ms) - int(pad_ms))
    end = int(end_ms) + int(pad_ms)
    return start, end


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def load_spans(path: Path) -> list[dict[str, Any]]:
    """Load a ``--spans-jsonl`` file and assert every row is scorable.

    A row is rejected rather than repaired: an unmapped speaker label would make
    the expected guru a guess, and a duplicate ``source_span_id`` would make the
    verdict rows ambiguous against the one-row-per-span contract.
    """
    rows = load_jsonl(path)
    if not rows:
        raise InputError(f"{path}: no spans")
    seen: set[str] = set()
    for index, row in enumerate(rows):
        for field in SPAN_REQUIRED_FIELDS:
            if row.get(field) in (None, ""):
                raise InputError(f"{path}: row {index} has no {field}")
        span_id = str(row["source_span_id"])
        if span_id in seen:
            raise InputError(f"{path}: duplicate source_span_id {span_id!r} at row {index}")
        seen.add(span_id)
        for field in ("start_ms", "end_ms"):
            if not _is_int(row.get(field)):
                raise InputError(f"{path}: row {index} has a non-integer {field}")
        if int(row["end_ms"]) <= int(row["start_ms"]):
            raise InputError(f"{path}: row {index} has end_ms <= start_ms")
        if str(row["speaker_id"]).strip().casefold() not in GURU_BY_SPEAKER:
            raise InputError(
                f"{path}: row {index} has an unusable speaker_id {row['speaker_id']!r}"
            )
    return rows


def load_pinned_calibration(path: Path, max_far: float | None = None) -> dict[str, Any]:
    """Read the already-pinned calibration artifact. Never recalibrates.

    ``max_far`` (optional, off by default) refuses an artifact whose Clopper-Pearson
    false-accept bound on the held-out test impostors exceeds it. The default is off
    because the calibration pinned on 2026-10-30 has 262 trials and a bound near 1.1%; the
    owner decides when a tighter target applies.

    Fail closed: an unmeasurable or malformed artifact means no span can be
    verified, so the caller stops instead of applying an invented floor. The
    revision travels into every row so a verdict can be traced to the exact
    calibration that produced it.
    """
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise InputError(f"calibration {path} is unreadable: {exc}") from exc
    if not isinstance(data, dict):
        raise InputError(f"calibration {path} is not a JSON object")
    if data.get("calibration_available") is False:
        raise InputError(
            f"calibration {path} reports calibration_available=false; no span can be verified"
        )
    # The phase-2 certification artifact nests its measured floors under "thresholds".
    floors = data.get("thresholds") if isinstance(data.get("thresholds"), dict) else {}
    cosine_floor = data.get("cosine_floor", floors.get("cosine_floor"))
    margin_threshold = data.get(
        "margin_threshold", data.get("threshold", floors.get("margin_threshold"))
    )
    for name, value in (("cosine_floor", cosine_floor), ("margin_threshold", margin_threshold)):
        if not _finite(value):
            raise InputError(f"calibration {path} has no usable {name}: {value!r}")
    revision = str(data.get("calibration_revision") or "")
    if not revision:
        raise InputError(f"calibration {path} carries no calibration_revision")
    # Always recorded, so every served-window run states how well the false-accept rate it
    # relies on is bounded; it only refuses when the owner sets ``max_far``.
    ok, far_record = far_gate(data, max_far if max_far is not None else DEFAULT_TARGET_FAR)
    if max_far is not None:
        if not ok:
            raise InputError(
                f"calibration {path} does not meet the false-accept target {max_far}: "
                f"bound {far_record['upper_bound']} from {far_record['false_accepts']} false "
                f"accepts in {far_record['impostor_trials']} trials; about "
                f"{far_record['clean_trials_needed_for_target']} clean trials are needed"
            )
    return {
        "far_bound": far_record,
        "calibration_available": True,
        "calibration_revision": revision,
        "cosine_floor": float(cosine_floor),
        "margin_threshold": float(margin_threshold),
        "path": str(path.resolve()),
        "sha256": _sha256_file(path),
    }


def load_references(path: Path) -> dict[str, np.ndarray]:
    """Load the guru reference centroids a candidate-mode run wrote."""
    try:
        with np.load(path) as data:
            references = {name: data[name].astype(np.float32) for name in data.files}
    except (OSError, ValueError) as exc:
        raise InputError(f"references {path} are unreadable: {exc}") from exc
    if not references:
        raise InputError(f"references {path} hold no centroids")
    missing = sorted(set(references) - GURU_IDS)
    if missing:
        raise InputError(f"references {path} carry unknown guru ids {missing}")
    return references


def build_span_verdict_row(
    *,
    span: dict[str, Any],
    vector: np.ndarray | None,
    audio_failure: str | None,
    references: dict[str, np.ndarray],
    calibration: dict[str, Any],
    run_id: str,
    model_revision: str,
    device: str,
    audio_dir: Path,
    audio_hashes: dict[str, str],
    audio_info: dict[str, dict[str, Any]],
    slice_durations: dict[str, int],
) -> dict[str, Any]:
    """Build one served-window verdict row. Pure: same inputs always give the row."""
    span_id = str(span["source_span_id"])
    video_id = str(span["video_id"])
    expected_guru = GURU_BY_SPEAKER[str(span["speaker_id"]).strip().casefold()]
    span_start = int(span["start_ms"])
    span_end = int(span["end_ms"])
    window_start, window_end = served_window(span_start, span_end)
    cosine_floor = calibration["cosine_floor"]
    margin_threshold = calibration["margin_threshold"]

    if vector is None:
        verdict = audio_failure or VERDICT_NOT_RUN
        reason = verdict
        scored = {"predicted": "", "cosine": None, "runner_up_cosine": None, "margin": None}
        predicted_guru = ""
    else:
        scored = score_against_references(vector, references)
        predicted_guru = scored["predicted"]
        verdict, reason = decide_verdict(
            expected_guru=expected_guru,
            predicted_guru=predicted_guru,
            cosine=float(scored["cosine"]),
            margin=float(scored["margin"]),
            cosine_floor=cosine_floor,
            margin_threshold=margin_threshold,
            calibration_available=bool(calibration["calibration_available"]),
        )

    header = audio_info.get(video_id) or {}
    return {
        "schema": SPAN_VERDICT_SCHEMA,
        "run_id": run_id,
        "mode": "served_window",
        "source_span_id": span_id,
        "point_id": str(span["point_id"]),
        "video_id": video_id,
        "speaker_id": str(span["speaker_id"]),
        "guru_id": expected_guru,
        "expected_guru": expected_guru,
        "expected_guru_source": (
            "payload.speaker_id mapped through GURU_BY_SPEAKER (a claim under test, never evidence)"
        ),
        "predicted_guru": predicted_guru or None,
        "span_start_ms": span_start,
        "span_end_ms": span_end,
        "window_start_ms": window_start,
        "window_end_ms": window_end,
        "window_pad_ms": SERVED_PAD_MS,
        "audio_path": str((audio_dir / f"{video_id}.wav").resolve()),
        "audio_sha256": audio_hashes.get(video_id, ""),
        "audio_sample_rate": header.get("sample_rate"),
        "audio_file_duration_ms": header.get("duration_ms"),
        "audio_start_ms": window_start,
        "audio_end_ms": window_end,
        "audio_slice_duration_ms": slice_durations.get(span_id),
        "audio_window_ordered": bool(window_end > window_start),
        "speaker_model": ECAPA_MODEL_ID,
        "speaker_model_revision": model_revision,
        "speaker_device": device,
        "calibration_revision": calibration["calibration_revision"],
        "cosine": _round(scored["cosine"]) if scored["cosine"] is not None else None,
        "runner_up_cosine": (
            _round(scored["runner_up_cosine"]) if scored["runner_up_cosine"] is not None else None
        ),
        "margin": _round(scored["margin"]) if scored["margin"] is not None else None,
        "cosine_floor": _round(cosine_floor),
        "margin_threshold": _round(margin_threshold),
        "verdict": verdict,
        "verdict_group": verdict_group(verdict),
        "reason_code": reason,
    }


def span_verdict_rows(
    spans: list[dict[str, Any]],
    *,
    audio_dir: Path,
    calibration: dict[str, Any],
    references: dict[str, np.ndarray],
    embed_slice_fn,
    run_id: str,
    model_revision: str,
    device: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """One served-window verdict row per span, plus run counters.

    ``embed_slice_fn(audio) -> vector | None`` is the only model-dependent step,
    so a test can inject a fake embedder and never import torch/speechbrain.
    """
    audio_hashes: dict[str, str] = {}
    audio_info: dict[str, dict[str, Any]] = {}
    slice_durations: dict[str, int] = {}
    audio_failures: dict[str, str] = {}
    rows: list[dict[str, Any]] = []

    for span in sorted(spans, key=lambda item: str(item["source_span_id"])):
        span_id = str(span["source_span_id"])
        video_id = str(span["video_id"])
        wav_path = audio_dir / f"{video_id}.wav"
        if video_id not in audio_hashes:
            audio_hashes[video_id] = _sha256_file(wav_path) if wav_path.is_file() else ""
            audio_info[video_id] = (wav_header(wav_path) or {}) if wav_path.is_file() else {}

        window_start, window_end = served_window(int(span["start_ms"]), int(span["end_ms"]))
        vector: np.ndarray | None = None
        audio, reason = read_slice(wav_path, window_start, window_end)
        if audio is None:
            audio_failures[span_id] = reason or VERDICT_INVALID_AUDIO
        else:
            slice_durations[span_id] = int(round(audio.size * 1000.0 / TARGET_SAMPLE_RATE))
            vector = embed_slice_fn(audio)
            if vector is None:
                audio_failures[span_id] = VERDICT_INVALID_AUDIO

        rows.append(
            build_span_verdict_row(
                span=span,
                vector=vector,
                audio_failure=audio_failures.get(span_id),
                references=references,
                calibration=calibration,
                run_id=run_id,
                model_revision=model_revision,
                device=device,
                audio_dir=audio_dir,
                audio_hashes=audio_hashes,
                audio_info=audio_info,
                slice_durations=slice_durations,
            )
        )
    return rows, {
        "rows": len(rows),
        "audio_failures": dict(Counter(audio_failures.values())),
        "slices_embedded": len(slice_durations),
    }


# ---------------------------------------------------------------------------
# Scoring helpers
# ---------------------------------------------------------------------------
def _cos(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(a, b))


def _percentiles(values: list[float]) -> dict[str, float | None]:
    if not values:
        return {"min": None, "p01": None, "p05": None, "p50": None, "p95": None, "max": None}
    array = np.asarray(values, dtype=np.float64)
    return {
        "min": _round(float(array.min())),
        "p01": _round(float(np.percentile(array, 1))),
        "p05": _round(float(np.percentile(array, 5))),
        "p50": _round(float(np.percentile(array, 50))),
        "p95": _round(float(np.percentile(array, 95))),
        "max": _round(float(array.max())),
    }


def score_against_references(
    vector: np.ndarray, references: dict[str, np.ndarray]
) -> dict[str, Any]:
    """Score one embedding against every guru reference.

    Returns the ordered scores, the predicted guru, the runner-up and the
    margin. The runner-up is the best score among the *other* references.
    """
    scores = {name: _cos(vector, reference) for name, reference in references.items()}
    ordered = sorted(scores.items(), key=lambda item: (-item[1], item[0]))
    predicted, best = ordered[0]
    runner_up = ordered[1][1] if len(ordered) > 1 else 0.0
    return {
        "scores": scores,
        "predicted": predicted,
        "cosine": best,
        "runner_up_cosine": runner_up,
        "margin": best - runner_up,
    }


def decide_verdict(
    *,
    expected_guru: str,
    predicted_guru: str,
    cosine: float,
    margin: float,
    cosine_floor: float | None,
    margin_threshold: float | None,
    calibration_available: bool,
) -> tuple[str, str]:
    """Deterministic verdict for one span. Pure function of its inputs."""
    if not calibration_available or cosine_floor is None or margin_threshold is None:
        return VERDICT_CALIBRATION_UNAVAILABLE, VERDICT_CALIBRATION_UNAVAILABLE
    if not _finite(cosine) or not _finite(margin):
        return VERDICT_NOT_RUN, VERDICT_NOT_RUN
    if predicted_guru != expected_guru:
        return VERDICT_REFUSED_GURU_MISMATCH, VERDICT_REFUSED_GURU_MISMATCH
    if cosine < cosine_floor:
        return VERDICT_REFUSED_BELOW_COSINE_FLOOR, VERDICT_REFUSED_BELOW_COSINE_FLOOR
    if margin < margin_threshold:
        return VERDICT_REFUSED_BELOW_MARGIN, VERDICT_REFUSED_BELOW_MARGIN
    return VERDICT_VERIFIED, VERDICT_VERIFIED


def verdict_group(verdict: str) -> str:
    if verdict == VERDICT_VERIFIED:
        return "verified"
    if verdict in AUDIO_FAILURE_CATEGORIES or verdict == VERDICT_NOT_RUN:
        return "not_run"
    return "refused"


# ---------------------------------------------------------------------------
# Calibration
# ---------------------------------------------------------------------------
def _anchor_scores(vector: np.ndarray, anchors: dict[str, np.ndarray]) -> dict[str, float]:
    """Cosine similarity of one slice against every anchor voiceprint."""
    return {name: _cos(vector, reference) for name, reference in anchors.items()}


def _assign_guru(scores: dict[str, float], min_score: float, margin: float) -> str | None:
    """Name a slice from anchor scores, or abstain.

    ``None`` means "not a trial": the audio is not confidently one of the two
    teachers. Abstaining is always safe — a slice that cannot be named cannot
    produce a false accept.
    """
    ordered = sorted(scores.items(), key=lambda item: (-item[1], item[0]))
    best_name, best = ordered[0]
    second = ordered[1][1] if len(ordered) > 1 else 0.0
    if best < min_score:
        return None
    if best - second < margin:
        return None
    return best_name


def _label_from_anchors(
    vector: np.ndarray, anchors: dict[str, np.ndarray]
) -> tuple[str | None, dict[str, float]]:
    """Label one slice with the anchor voiceprints alone.

    This is the *label* function of the held-out trials: it uses only the
    human-confirmed anchor vectors, never the widened reference centroids the
    decision function uses.
    """
    scores = _anchor_scores(vector, anchors)
    return _assign_guru(scores, ANCHOR_LABEL_MIN, ANCHOR_MARGIN), scores


def build_references(
    vectors: dict[str, np.ndarray],
    splits: dict[str, str],
    anchors: dict[str, np.ndarray],
) -> tuple[dict[str, np.ndarray], dict[str, Any]]:
    """Guru reference centroids from the anchor voiceprints + train slices."""
    members: dict[str, list[np.ndarray]] = {name: [anchor] for name, anchor in anchors.items()}
    selected: list[str] = []
    unlabeled = 0
    for span_id in sorted(vectors):
        if splits.get(span_id) != "train":
            continue
        scores = _anchor_scores(vectors[span_id], anchors)
        # A reference member must match its anchor strongly (ENROLL_MIN): the
        # reference is the widened anchor, not every anchor-adjacent slice.
        label = _assign_guru(scores, ENROLL_MIN, ANCHOR_MARGIN)
        if label is None:
            unlabeled += 1
            continue
        members[label].append(vectors[span_id])
        selected.append(span_id)
    references: dict[str, np.ndarray] = {}
    stats: dict[str, Any] = {}
    for name, rows in sorted(members.items()):
        reference = _unit(np.mean(np.stack(rows), axis=0))
        if reference is None:
            raise InputError(f"degenerate reference centroid for {name}")
        references[name] = reference
        stats[name] = {
            "member_count": len(rows),
            "anchor_members": 1,
            "train_slice_members": len(rows) - 1,
        }
    return references, {
        "references": stats,
        "train_slices_selected": len(selected),
        "train_slices_unlabeled": unlabeled,
    }


def build_trials(
    vectors: dict[str, np.ndarray],
    splits: dict[str, str],
    anchors: dict[str, np.ndarray],
    references: dict[str, np.ndarray],
    split: str,
) -> dict[str, Any]:
    """Positive and impostor trials on one held-out split.

    A positive trial is a labelled slice scored against its own guru's
    reference. The same slice scored against the *other* guru's reference is an
    impostor trial.
    """
    positives: list[dict[str, Any]] = []
    impostors: list[dict[str, Any]] = []
    unlabeled = 0
    for span_id in sorted(vectors):
        if splits.get(span_id) != split:
            continue
        vector = vectors[span_id]
        label, _anchor_scores = _label_from_anchors(vector, anchors)
        if label is None:
            unlabeled += 1
            continue
        scored = score_against_references(vector, references)
        positives.append(
            {
                "source_span_id": span_id,
                "label": label,
                "cosine": scored["scores"][label],
                "margin": scored["scores"][label]
                - max(value for name, value in scored["scores"].items() if name != label),
                "predicted": scored["predicted"],
            }
        )
        for other in sorted(references):
            if other == label:
                continue
            impostors.append(
                {
                    "source_span_id": span_id,
                    "claimed": other,
                    "true_label": label,
                    "cosine": scored["scores"][other],
                    "margin": scored["scores"][other] - scored["scores"][label],
                }
            )
    return {
        "split": split,
        "positive_trials": positives,
        "impostor_trials": impostors,
        "unlabeled_slices": unlabeled,
    }


def calibrate_from_trials(trials: dict[str, Any]) -> dict[str, Any]:
    """Derive the decision floors from the held-out impostor trials."""
    impostors = trials["impostor_trials"]
    positives = trials["positive_trials"]
    if len(impostors) < MIN_IMPOSTOR_TRIALS:
        return {
            "calibration_available": False,
            "reason": (
                f"only {len(impostors)} held-out impostor trials "
                f"(< {MIN_IMPOSTOR_TRIALS}); the false-accept rate is not measurable"
            ),
            "impostor_trials": len(impostors),
            "positive_trials": len(positives),
            "cosine_floor": None,
            "margin_threshold": None,
        }
    impostor_cosines = [float(trial["cosine"]) for trial in impostors]
    impostor_margins = [float(trial["margin"]) for trial in impostors]
    positive_cosines = [float(trial["cosine"]) for trial in positives]
    positive_margins = [float(trial["margin"]) for trial in positives]
    # The floors sit strictly above every observed impostor score, so the
    # measured false-accept rate on this split is zero by construction. The
    # honest generalization number is measured on the separate test split.
    # Neither floor is allowed to go below zero: a negative floor would weaken
    # verification instead of tightening it (``speaker_attribution.py``).
    cosine_floor = max(0.0, max(impostor_cosines)) + 1e-6
    margin_threshold = max(0.0, max(impostor_margins)) + 1e-6
    false_accepts = sum(
        1
        for trial in impostors
        if trial["cosine"] >= cosine_floor and trial["margin"] >= margin_threshold
    )
    false_rejects = sum(
        1
        for trial in positives
        if trial["cosine"] < cosine_floor or trial["margin"] < margin_threshold
    )
    return {
        "calibration_available": True,
        "impostor_trials": len(impostors),
        "positive_trials": len(positives),
        "cosine_floor": float(cosine_floor),
        "margin_threshold": float(margin_threshold),
        "calibration_false_accepts": false_accepts,
        "calibration_false_accept_rate": _round(false_accepts / len(impostors))
        if impostors
        else None,
        "calibration_false_rejects": false_rejects,
        "calibration_false_reject_rate": _round(false_rejects / len(positives))
        if positives
        else None,
        "impostor_cosine_distribution": _percentiles(impostor_cosines),
        "impostor_margin_distribution": _percentiles(impostor_margins),
        "positive_cosine_distribution": _percentiles(positive_cosines),
        "positive_margin_distribution": _percentiles(positive_margins),
    }


def evaluate_on_split(
    trials: dict[str, Any], cosine_floor: float, margin_threshold: float
) -> dict[str, Any]:
    """False-accept / false-reject measurement on a held-out split."""
    impostors = trials["impostor_trials"]
    positives = trials["positive_trials"]
    false_accepts = [
        trial
        for trial in impostors
        if trial["cosine"] >= cosine_floor and trial["margin"] >= margin_threshold
    ]
    false_rejects = [
        trial
        for trial in positives
        if trial["cosine"] < cosine_floor or trial["margin"] < margin_threshold
    ]
    wrong_prediction = sum(1 for trial in positives if trial["predicted"] != trial["label"])
    return {
        "split": trials["split"],
        "impostor_trials": len(impostors),
        "positive_trials": len(positives),
        "false_accepts": len(false_accepts),
        "false_accept_rate": _round(len(false_accepts) / len(impostors)) if impostors else None,
        "false_rejects": len(false_rejects),
        "false_reject_rate": _round(len(false_rejects) / len(positives)) if positives else None,
        "wrong_prediction": wrong_prediction,
        "wrong_prediction_rate": _round(wrong_prediction / len(positives)) if positives else None,
        "unlabeled_slices": trials["unlabeled_slices"],
        "impostor_cosine_distribution": _percentiles([float(t["cosine"]) for t in impostors]),
        "impostor_margin_distribution": _percentiles([float(t["margin"]) for t in impostors]),
        "positive_cosine_distribution": _percentiles([float(t["cosine"]) for t in positives]),
        "positive_margin_distribution": _percentiles([float(t["margin"]) for t in positives]),
    }


# ---------------------------------------------------------------------------
# Impostor evidence and the false-accept bound (P7)
# ---------------------------------------------------------------------------
#: The error rate the false-accept bound is judged against. 0.5% needs about 600 clean
#: impostor trials; 0.1% needs about 3,000. The value is the merged plan's proposal
#: (2026-10-31), not a measured requirement.
DEFAULT_TARGET_FAR = 0.005
#: One-sided confidence for the Clopper-Pearson bound.
FAR_ALPHA = 0.05
#: Label values a foreign (non-teacher) slice may carry.
FOREIGN_LABELS = frozenset({"host", "interviewer", "other"})
FOREIGN_SLICE_REQUIRED = ("slice_id", "video_id", "start_ms", "end_ms", "label")


def far_upper_bound(false_accepts: int, trials: int, alpha: float = FAR_ALPHA) -> float | None:
    """Exact one-sided Clopper-Pearson upper bound on the false-accept rate, or ``None``."""
    if trials <= 0 or false_accepts < 0 or false_accepts > trials:
        return None
    from evaluation.gold.metrics import clopper_pearson_upper

    return float(clopper_pearson_upper(false_accepts, trials, alpha))


def trials_needed_for_far(target: float, alpha: float = FAR_ALPHA) -> int:
    """Clean (zero false accept) impostor trials needed for the bound to reach ``target``."""
    if not 0.0 < target < 1.0:
        raise ValueError("target must be between 0 and 1")
    return math.ceil(math.log(alpha) / math.log(1.0 - target))


def far_bound_record(
    false_accepts: int | None,
    trials: int | None,
    *,
    target: float = DEFAULT_TARGET_FAR,
    alpha: float = FAR_ALPHA,
) -> dict[str, Any]:
    """The calibration record's false-accept evidence: counts, bound, target, verdict."""
    needed = trials_needed_for_far(target, alpha)
    bound = (
        far_upper_bound(int(false_accepts), int(trials), alpha)
        if isinstance(false_accepts, int) and isinstance(trials, int)
        else None
    )
    return {
        "impostor_trials": trials,
        "false_accepts": false_accepts,
        "alpha": alpha,
        "upper_bound": _round(bound, 8) if bound is not None else None,
        "target": target,
        "meets_target": bool(bound is not None and bound <= target),
        "clean_trials_needed_for_target": needed,
        "method": "clopper_pearson_one_sided_exact",
        # The bound treats every trial as independent. Slices of one speaker in one video are
        # not, so the effective evidence is smaller than the count (a limit of this method).
        "independence_caveat": (
            "assumes independent trials; trials sharing a speaker or a video are correlated, "
            "so the true uncertainty is wider than this bound"
        ),
    }


def far_gate(calibration: dict[str, Any], target: float) -> tuple[bool, dict[str, Any]]:
    """Refuse a calibration whose false-accept bound exceeds ``target``.

    Reads the counts the calibration artifact already records for the held-out **test**
    split (``trial_counts.test_impostor_trials`` and ``false_accept.test.count``); the
    calibration split is excluded because its floors sit above every observed impostor by
    construction. An artifact that does not carry both counts cannot be judged, so it is
    refused rather than waved through.
    """
    counts = calibration.get("trial_counts")
    trials = counts.get("test_impostor_trials") if isinstance(counts, dict) else None
    false_accept = calibration.get("false_accept")
    test = false_accept.get("test") if isinstance(false_accept, dict) else None
    accepts = test.get("count") if isinstance(test, dict) else None
    record = far_bound_record(accepts, trials, target=target)
    record["source"] = "trial_counts.test_impostor_trials, false_accept.test.count"
    return bool(record["meets_target"]), record


def load_foreign_slices(path: Path) -> list[dict[str, Any]]:
    """Host / interviewer / other-speaker slices to use as extra impostor trials.

    One JSON object per line with ``slice_id``, ``video_id``, ``start_ms``, ``end_ms`` and a
    ``label`` in :data:`FOREIGN_LABELS`. These are voices that are NOT Sri Krishnaji or Sri
    Preethaji (for example diarization windows named ``O``); a slice that is really a
    teacher would only add false accepts, which fails safe.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise InputError(f"foreign slices {path} are unreadable: {exc}") from exc
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for number, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise InputError(f"{path}: line {number} is not valid JSON: {exc}") from exc
        if not isinstance(row, dict):
            raise InputError(f"{path}: line {number} is not a JSON object")
        for field in FOREIGN_SLICE_REQUIRED:
            if row.get(field) in (None, ""):
                raise InputError(f"{path}: line {number} is missing {field}")
        if str(row["label"]) not in FOREIGN_LABELS:
            raise InputError(f"{path}: line {number} has label {row['label']!r}")
        if not (_is_int(row["start_ms"]) and _is_int(row["end_ms"])) or int(row["end_ms"]) <= int(
            row["start_ms"]
        ):
            raise InputError(f"{path}: line {number} has an invalid window")
        if str(row["slice_id"]) in seen:
            raise InputError(f"{path}: duplicate slice_id {row['slice_id']!r} at line {number}")
        seen.add(str(row["slice_id"]))
        rows.append(row)
    return rows


def build_foreign_trials(
    vectors: dict[str, np.ndarray],
    splits: dict[str, str],
    references: dict[str, np.ndarray],
    split: str,
    labels: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    """Impostor trials from non-teacher voices: each slice claims each teacher in turn.

    Same trial shape as :func:`build_trials` impostors, so the floors and the false-accept
    count treat both kinds alike. ``margin`` is the claimed teacher's score minus the best
    other reference.
    """
    trials: list[dict[str, Any]] = []
    for slice_id in sorted(vectors):
        if splits.get(slice_id) != split:
            continue
        scored = score_against_references(vectors[slice_id], references)
        for claimed in sorted(references):
            best_other = max(
                (value for name, value in scored["scores"].items() if name != claimed),
                default=0.0,
            )
            trials.append(
                {
                    "source_span_id": slice_id,
                    "claimed": claimed,
                    "true_label": (labels or {}).get(slice_id, "foreign"),
                    "kind": "foreign_voice",
                    "cosine": scored["scores"][claimed],
                    "margin": scored["scores"][claimed] - best_other,
                }
            )
    return trials


# ---------------------------------------------------------------------------
# Verdict rows
# ---------------------------------------------------------------------------
def build_verdict_row(
    *,
    candidate_row: dict[str, Any],
    vector: np.ndarray | None,
    audio_failure: str | None,
    references: dict[str, np.ndarray],
    split: str,
    calibration_available: bool,
    cosine_floor: float | None,
    margin_threshold: float | None,
    run_id: str,
    calibration_revision: str,
    model_revision: str,
    device: str,
    audio_dir: Path,
    audio_hashes: dict[str, str],
    audio_info: dict[str, dict[str, Any]],
    slice_durations: dict[str, int],
) -> dict[str, Any]:
    """Build one verdict row. Pure: same inputs always give the same row."""
    span_id = str(candidate_row["source_span_id"])
    video_id = str(candidate_row["video_id"])
    expected_guru = str(candidate_row["guru_id"])
    start_ms = int(candidate_row["audio_start_ms"])
    end_ms = int(candidate_row["audio_end_ms"])

    if vector is None:
        verdict = audio_failure or VERDICT_NOT_RUN
        reason = verdict
        scored = {"predicted": "", "cosine": None, "runner_up_cosine": None, "margin": None}
        predicted_guru = ""
    else:
        scored = score_against_references(vector, references)
        predicted_guru = scored["predicted"]
        verdict, reason = decide_verdict(
            expected_guru=expected_guru,
            predicted_guru=predicted_guru,
            cosine=float(scored["cosine"]),
            margin=float(scored["margin"]),
            cosine_floor=cosine_floor,
            margin_threshold=margin_threshold,
            calibration_available=calibration_available,
        )

    header = audio_info.get(video_id) or {}
    return {
        "schema": VERDICT_SCHEMA,
        "run_id": run_id,
        "source_span_id": span_id,
        "video_id": video_id,
        "guru_id": expected_guru,
        "expected_guru": expected_guru,
        "expected_guru_source": (
            "phase3_candidate.guru_id (explicit registry id; a claim under test, never evidence)"
        ),
        "predicted_guru": predicted_guru or None,
        "source_text_hash": str(candidate_row.get("source_text_hash") or ""),
        "transcript_hash": str(candidate_row.get("transcript_hash") or ""),
        "timed_transcript_sha256": str(candidate_row.get("timed_transcript_sha256") or ""),
        "audio_path": str((audio_dir / f"{video_id}.wav").resolve()),
        "audio_sha256": audio_hashes.get(video_id, ""),
        "audio_sample_rate": header.get("sample_rate"),
        "audio_duration_ms": header.get("duration_ms"),
        "audio_start_ms": start_ms,
        "audio_end_ms": end_ms,
        "audio_slice_duration_ms": slice_durations.get(span_id),
        "audio_window_ordered": bool(end_ms > start_ms),
        "speaker_model": ECAPA_MODEL_ID,
        "speaker_model_revision": model_revision,
        "speaker_device": device,
        "calibration_revision": calibration_revision,
        "cosine": _round(scored["cosine"]) if scored["cosine"] is not None else None,
        "runner_up_cosine": (
            _round(scored["runner_up_cosine"]) if scored["runner_up_cosine"] is not None else None
        ),
        "margin": _round(scored["margin"]) if scored["margin"] is not None else None,
        "cosine_floor": _round(cosine_floor) if cosine_floor is not None else None,
        "margin_threshold": _round(margin_threshold) if margin_threshold is not None else None,
        "split": split,
        "verdict": verdict,
        "verdict_group": verdict_group(verdict),
        "reason_code": reason,
    }


# ---------------------------------------------------------------------------
# Row validation
# ---------------------------------------------------------------------------
def validate_row(row: dict[str, Any]) -> list[str]:
    """Every required validation for one verdict row."""
    failures: list[str] = []
    verdict = str(row.get("verdict") or "")
    speaker_verdict = verdict not in AUDIO_FAILURE_CATEGORIES and verdict != VERDICT_NOT_RUN

    always_required = (
        "source_span_id",
        "video_id",
        "expected_guru",
        "speaker_model",
        "speaker_model_revision",
        "calibration_revision",
        "verdict",
        "reason_code",
    )
    for field in always_required:
        if not str(row.get(field) or ""):
            failures.append(f"missing_{field}")
    if speaker_verdict and not str(row.get("predicted_guru") or ""):
        failures.append("missing_predicted_guru")
    if str(row.get("expected_guru") or "") not in GURU_IDS:
        failures.append("expected_guru_not_a_registry_id")
    if verdict not in VERDICT_CATEGORIES:
        failures.append("unknown_verdict")
    if str(row.get("reason_code") or "") not in VERDICT_CATEGORIES:
        failures.append("unknown_reason_code")
    for field in ("cosine", "runner_up_cosine", "margin"):
        value = row.get(field)
        if value is None:
            continue
        if not _finite(value):
            failures.append(f"non_finite_{field}")
    if speaker_verdict:
        for field in ("cosine_floor", "margin_threshold"):
            if not _finite(row.get(field)):
                failures.append(f"non_finite_{field}")
    if verdict == VERDICT_VERIFIED:
        if not _finite(row.get("cosine")) or not _finite(row.get("margin")):
            failures.append("verified_without_finite_score")
        else:
            recomputed, _reason = decide_verdict(
                expected_guru=str(row["expected_guru"]),
                predicted_guru=str(row["predicted_guru"]),
                cosine=float(row["cosine"]),
                margin=float(row["margin"]),
                cosine_floor=row.get("cosine_floor"),
                margin_threshold=row.get("margin_threshold"),
                calibration_available=True,
            )
            if recomputed != verdict:
                failures.append("verdict_not_reproducible")
    if verdict in AUDIO_FAILURE_CATEGORIES:
        if _finite(row.get("cosine")):
            failures.append("audio_failure_with_a_score")
    return failures


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Regenerate independently calibrated per-span ECAPA evidence.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--candidate", default=None, help="Phase 3 exact candidate JSONL.")
    parser.add_argument("--quarantine", default=None, help="Phase 3 quarantine JSONL.")
    parser.add_argument("--audio-dir", required=True, help="audio_archive/wavs directory.")
    parser.add_argument(
        "--out-verdicts", default=None, help="Verdict index JSON (keyed by source_span_id)."
    )
    parser.add_argument("--out-verdicts-jsonl", default=None, help="Verdict rows JSONL.")
    parser.add_argument(
        "--out-calibration",
        default=None,
        help="Calibration artifact JSON (candidate mode only; spans mode never recalibrates).",
    )
    parser.add_argument("--out-summary", default=None, help="Summary JSON.")
    parser.add_argument(
        "--spans-jsonl",
        default=None,
        help="Served-window mode: spans JSONL (point_id, source_span_id, video_id, start_ms, "
        "end_ms, speaker_id). Scores [start_ms-250, end_ms+250] against the pinned calibration.",
    )
    parser.add_argument(
        "--calibration",
        default=None,
        help="Served-window mode: the already-pinned calibration artifact (read, never refitted).",
    )
    parser.add_argument(
        "--references",
        default=None,
        help="Served-window mode: guru reference centroids (.npz written by --out-references).",
    )
    parser.add_argument(
        "--cache",
        default=str(Path(__file__).resolve().parents[3] / ".work/public_release/phase2_cache"),
        help="Embedding cache directory.",
    )
    parser.add_argument("--expected-spans", type=int, default=1600)
    parser.add_argument("--expected-quarantine", type=int, default=1137)
    parser.add_argument(
        "--device",
        default="auto",
        help="Torch device for the ECAPA encoder: auto (mps when available), cpu or mps.",
    )
    parser.add_argument("--generated-at-utc", default=None)
    parser.add_argument(
        "--out-references",
        default=None,
        help="Optional .npz path: write the guru reference centroids used for this run, "
        "so a later builder can verify new spans against the SAME references.",
    )
    parser.add_argument(
        "--foreign-slices-jsonl",
        default=None,
        help="Candidate mode: host / interviewer / other-speaker slices (slice_id, video_id, "
        "start_ms, end_ms, label). Added to the held-out impostor trials of their video's "
        "split. Build them with scripts/ops/build_impostor_slices.py.",
    )
    parser.add_argument(
        "--max-far",
        type=float,
        default=None,
        help="Served-window mode: refuse the pinned calibration unless its one-sided 95%% "
        "Clopper-Pearson false-accept bound on the test impostors is at most this (e.g. 0.005). "
        "Off by default.",
    )
    parser.add_argument(
        "--write-to-qdrant",
        action="store_true",
        help="REJECTED. This script has no write mode; it only emits file artifacts.",
    )
    return parser


def _write_json_file(path: str, payload: Any) -> str:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return str(target)


def run_spans_mode(args: argparse.Namespace) -> int:
    """Score the served window for every span in ``--spans-jsonl``.

    Never recalibrates and never writes to a collection: the floors come from the
    pinned artifact, the rows are a file artifact, and
    ``scripts/ops/backfill_v10_voice_method.py`` owns the (gated) write path.
    """
    required = (
        ("--spans-jsonl", args.spans_jsonl),
        ("--calibration", args.calibration),
        ("--references", args.references),
        ("--out-verdicts-jsonl", args.out_verdicts_jsonl),
    )
    missing = [name for name, value in required if not value]
    if missing:
        print(
            json.dumps(
                {
                    "status": "invalid_input",
                    "error": f"served-window mode requires {', '.join(missing)}",
                    "script_version": SCRIPT_VERSION,
                },
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return EXIT_INVALID_INPUT

    spans_path = Path(args.spans_jsonl)
    calibration_path = Path(args.calibration)
    references_path = Path(args.references)
    audio_dir = Path(args.audio_dir).expanduser()
    try:
        spans = load_spans(spans_path)
        calibration = load_pinned_calibration(calibration_path, args.max_far)
        references = load_references(references_path)
    except InputError as exc:
        print(
            json.dumps(
                {"status": "invalid_input", "error": str(exc), "script_version": SCRIPT_VERSION},
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return EXIT_INVALID_INPUT

    cache_dir = Path(args.cache).expanduser()
    cache_dir.mkdir(parents=True, exist_ok=True)
    device = resolve_device(args.device)
    model_revision = _ecapa_revision()

    run_manifest = {
        "script_version": SCRIPT_VERSION,
        "mode": "served_window",
        "model": {"id": ECAPA_MODEL_ID, "revision": model_revision, "device": device},
        "recipe": {
            "window_seconds": WINDOW_SECONDS,
            "hop_seconds": HOP_SECONDS,
            "sample_rate": TARGET_SAMPLE_RATE,
            "silence_rms_floor": 0.01,
            "served_pad_ms": SERVED_PAD_MS,
            "window_rule": "max(0, start_ms - pad) .. end_ms + pad (CITATION_PLAYBACK_PAD_S)",
        },
        "calibration": {
            "path": calibration["path"],
            "sha256": calibration["sha256"],
            "calibration_revision": calibration["calibration_revision"],
        },
        "spans": {"path": str(spans_path.resolve()), "sha256": _sha256_file(spans_path)},
        "references": {
            "path": str(references_path.resolve()),
            "sha256": _sha256_file(references_path),
        },
        "audio_dir": str(audio_dir.resolve()),
    }
    run_id = _sha256_bytes(_canonical_json(run_manifest).encode("utf-8"))

    embedder = load_embedder(cache_dir, device=device)
    rows, counters = span_verdict_rows(
        spans,
        audio_dir=audio_dir,
        calibration=calibration,
        references=references,
        embed_slice_fn=lambda audio: embed_slice(audio, embedder),
        run_id=run_id,
        model_revision=model_revision,
        device=device,
    )

    validation_failures: list[dict[str, Any]] = []
    per_check = Counter()
    for row in rows:
        failures = validate_row(row)
        for failure in failures:
            per_check[failure] += 1
        if failures:
            validation_failures.append(
                {"source_span_id": row["source_span_id"], "failures": failures}
            )
    checks = {
        "one_row_per_source_span_id": len(rows) == len(spans)
        and len({row["source_span_id"] for row in rows}) == len(rows),
        "every_row_echoes_calibration_revision": all(
            row["calibration_revision"] == calibration["calibration_revision"] for row in rows
        ),
        "every_row_uses_the_served_window": all(
            (row["window_start_ms"], row["window_end_ms"])
            == served_window(row["span_start_ms"], row["span_end_ms"])
            for row in rows
        ),
        "row_schema_failures": len(validation_failures),
    }
    verdict_counts = Counter(row["verdict"] for row in rows)
    summary = {
        "schema": SPAN_SUMMARY_SCHEMA,
        "script_version": SCRIPT_VERSION,
        "run_id": run_id,
        "mode": "served_window",
        "generated_at_utc": args.generated_at_utc or _dt.datetime.now(_dt.UTC).isoformat(),
        "inputs": {name: value for name, value in run_manifest.items() if name != "script_version"},
        "calibration": {
            "cosine_floor": calibration["cosine_floor"],
            "margin_threshold": calibration["margin_threshold"],
            "calibration_revision": calibration["calibration_revision"],
            "recalibrated": False,
            "false_accept_bound": calibration["far_bound"],
        },
        "spans_scored": len(spans),
        "rows_emitted": len(rows),
        "by_verdict": {name: verdict_counts.get(name, 0) for name in VERDICT_CATEGORIES},
        "audio_failures": counters["audio_failures"],
        "slices_embedded": counters["slices_embedded"],
        "validation": {
            "checks": checks,
            "row_failure_reasons": dict(per_check),
            "failures": validation_failures[:50],
        },
        "mutations": {
            "qdrant_reads": 0,
            "qdrant_writes": 0,
            "alias_changes": 0,
            "redis_operations": 0,
            "environment_changes": 0,
        },
    }

    written = {"verdicts_jsonl": str(Path(args.out_verdicts_jsonl))}
    target = Path(args.out_verdicts_jsonl)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n")
    if args.out_verdicts:
        written["verdicts"] = _write_json_file(
            args.out_verdicts,
            {
                "schema": VERDICT_INDEX_SCHEMA,
                "script_version": SCRIPT_VERSION,
                "run_id": run_id,
                "mode": "served_window",
                "key_field": "source_span_id",
                "verdict_count": len(rows),
                "calibration_revision": calibration["calibration_revision"],
                "verdicts": {row["source_span_id"]: row for row in rows},
            },
        )
    if args.out_summary:
        written["summary"] = _write_json_file(args.out_summary, summary)

    print(
        json.dumps(
            {
                "script_version": SCRIPT_VERSION,
                "mode": "served_window",
                "run_id": run_id,
                "rows_emitted": len(rows),
                "verdicts": dict(verdict_counts),
                "calibration_revision": calibration["calibration_revision"],
                "audio_failures": counters["audio_failures"],
                "validation": checks,
                "written": written,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return EXIT_INVALID_INPUT if validation_failures else EXIT_OK


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.write_to_qdrant:
        print(
            json.dumps(
                {
                    "status": "refused",
                    "reason": "this script has no write mode; verdicts are a file artifact only",
                    "script_version": SCRIPT_VERSION,
                },
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return EXIT_INVALID_INPUT

    if args.spans_jsonl:
        return run_spans_mode(args)

    missing = [
        name
        for name, value in (
            ("--candidate", args.candidate),
            ("--quarantine", args.quarantine),
            ("--out-verdicts", args.out_verdicts),
            ("--out-calibration", args.out_calibration),
            ("--out-summary", args.out_summary),
        )
        if not value
    ]
    if missing:
        print(
            json.dumps(
                {
                    "status": "invalid_input",
                    "error": f"candidate mode requires {', '.join(missing)}",
                    "script_version": SCRIPT_VERSION,
                },
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return EXIT_INVALID_INPUT

    candidate_path = Path(args.candidate)
    quarantine_path = Path(args.quarantine)
    audio_dir = Path(args.audio_dir).expanduser()

    try:
        candidate = load_candidate(candidate_path, args.expected_spans)
        _quarantine_rows, quarantine_ids, quarantine_without_id = load_quarantine(
            quarantine_path, args.expected_quarantine
        )
    except InputError as exc:
        print(
            json.dumps(
                {"status": "invalid_input", "error": str(exc), "script_version": SCRIPT_VERSION},
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return EXIT_INVALID_INPUT

    candidate_ids = {str(row["source_span_id"]) for row in candidate}
    overlap = candidate_ids & quarantine_ids
    if overlap:
        print(
            json.dumps(
                {
                    "status": "invalid_input",
                    "error": f"{len(overlap)} spans are both candidate and quarantined",
                    "script_version": SCRIPT_VERSION,
                },
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return EXIT_INVALID_INPUT

    foreign_slices: list[dict[str, Any]] = []
    foreign_sha256 = ""
    if args.foreign_slices_jsonl:
        foreign_path = Path(args.foreign_slices_jsonl)
        try:
            foreign_slices = load_foreign_slices(foreign_path)
        except InputError as exc:
            print(
                json.dumps(
                    {
                        "status": "invalid_input",
                        "error": str(exc),
                        "script_version": SCRIPT_VERSION,
                    },
                    sort_keys=True,
                ),
                file=sys.stderr,
            )
            return EXIT_INVALID_INPUT
        foreign_sha256 = _sha256_file(foreign_path)

    cache_dir = Path(args.cache).expanduser()
    cache_dir.mkdir(parents=True, exist_ok=True)
    embedding_cache_path = cache_dir / "embeddings.npz"

    device = resolve_device(args.device)
    embedder = load_embedder(cache_dir, device=device)
    model_revision = _ecapa_revision()

    # ---- audio + embedding -------------------------------------------------
    audio_hashes: dict[str, str] = {}
    audio_info: dict[str, dict[str, Any]] = {}
    vectors: dict[str, np.ndarray] = {}
    audio_failures: dict[str, str] = {}
    cached: dict[str, np.ndarray] = {}
    if embedding_cache_path.is_file():
        with np.load(embedding_cache_path) as data:
            for key in data.files:
                cached[key] = data[key]

    splits: dict[str, str] = {}
    for row in candidate:
        span_id = str(row["source_span_id"])
        video_id = str(row["video_id"])
        splits[span_id] = assign_split(video_id)

    def _cache_key(video_id: str, start_ms: int, end_ms: int) -> str:
        raw = (
            f"{ECAPA_MODEL_ID}|{model_revision}|{device}|{WINDOW_SECONDS}|{HOP_SECONDS}|"
            f"{video_id}|{audio_hashes.get(video_id, '')}|{start_ms}|{end_ms}"
        )
        return _sha256_bytes(raw.encode("utf-8"))

    new_vectors: dict[str, np.ndarray] = {}
    audio_files_opened = 0
    slices_generated = 0
    slices_from_cache = 0
    slice_durations: dict[str, int] = {}
    for row in candidate:
        span_id = str(row["source_span_id"])
        video_id = str(row["video_id"])
        start_ms = int(row["audio_start_ms"])
        end_ms = int(row["audio_end_ms"])
        wav_path = audio_dir / f"{video_id}.wav"
        if video_id not in audio_hashes:
            if wav_path.is_file():
                audio_files_opened += 1
                audio_hashes[video_id] = _sha256_file(wav_path)
                info = wav_header(wav_path)
                audio_info[video_id] = info or {}
            else:
                audio_hashes[video_id] = ""
                audio_info[video_id] = {}
        key = _cache_key(video_id, start_ms, end_ms)
        if key in cached:
            vectors[span_id] = cached[key]
            slice_durations[span_id] = end_ms - start_ms
            slices_from_cache += 1
            continue
        audio, reason = read_slice(wav_path, start_ms, end_ms)
        if audio is None:
            audio_failures[span_id] = reason or VERDICT_INVALID_AUDIO
            continue
        vector = embed_slice(audio, embedder)
        if vector is None:
            audio_failures[span_id] = VERDICT_INVALID_AUDIO
            continue
        new_vectors[key] = vector
        vectors[span_id] = vector
        slice_durations[span_id] = int(round(audio.size * 1000.0 / TARGET_SAMPLE_RATE))
        slices_generated += 1
    if new_vectors:
        merged = dict(cached)
        merged.update(new_vectors)
        np.savez_compressed(embedding_cache_path, **merged)

    # ---- foreign (host / interviewer / other) slices: extra impostor evidence (P7) ------
    foreign_vectors: dict[str, np.ndarray] = {}
    foreign_splits: dict[str, str] = {}
    foreign_labels: dict[str, str] = {}
    foreign_failures: Counter[str] = Counter()
    for row in foreign_slices:
        slice_id = f"foreign:{row['slice_id']}"
        video_id = str(row["video_id"])
        wav_path = audio_dir / f"{video_id}.wav"
        audio, reason = read_slice(wav_path, int(row["start_ms"]), int(row["end_ms"]))
        vector = embed_slice(audio, embedder) if audio is not None else None
        if vector is None:
            foreign_failures[reason or VERDICT_INVALID_AUDIO] += 1
            continue
        foreign_vectors[slice_id] = vector
        foreign_splits[slice_id] = assign_split(video_id)
        foreign_labels[slice_id] = str(row["label"])

    # ---- anchors, references, calibration ----------------------------------
    anchor_vectors: dict[str, np.ndarray] = {}
    anchor_details: dict[str, Any] = {}
    for guru in sorted(ANCHORS):
        video_id, moment = ANCHORS[guru]
        wav_path = audio_dir / f"{video_id}.wav"
        audio = read_whole_mono(wav_path)
        if audio is None:
            raise InputError(f"anchor audio unavailable for {guru}: {wav_path}")
        vector, info = anchor_voiceprint(audio, moment, embedder)
        if vector is None:
            raise InputError(f"anchor voiceprint unavailable for {guru}: {info}")
        anchor_vectors[guru] = vector
        anchor_details[guru] = {
            "anchor_video_id": video_id,
            "anchor_seconds": moment,
            "anchor_source": "backend/scripts/ops/speaker_attribution.py::ANCHORS (human-confirmed)",
            "anchor_video_audio_sha256": audio_hashes.get(video_id, ""),
            **info,
        }

    references, reference_stats = build_references(vectors, splits, anchor_vectors)
    if args.out_references:
        np.savez_compressed(Path(args.out_references), **references)
    calibration_trials = build_trials(vectors, splits, anchor_vectors, references, "calibration")
    test_trials = build_trials(vectors, splits, anchor_vectors, references, "test")
    foreign_calibration_trials = build_foreign_trials(
        foreign_vectors, foreign_splits, references, "calibration", foreign_labels
    )
    foreign_test_trials = build_foreign_trials(
        foreign_vectors, foreign_splits, references, "test", foreign_labels
    )
    # Foreign voices join the same impostor pool, so the floors rise above them too.
    calibration_trials["impostor_trials"].extend(foreign_calibration_trials)
    test_trials["impostor_trials"].extend(foreign_test_trials)
    calibration = calibrate_from_trials(calibration_trials)
    cosine_floor = calibration.get("cosine_floor")
    margin_threshold = calibration.get("margin_threshold")
    calibration_available = bool(calibration.get("calibration_available"))
    if calibration_available:
        test_evaluation = evaluate_on_split(
            test_trials, float(cosine_floor), float(margin_threshold)
        )
    else:
        test_evaluation = {
            "split": "test",
            "impostor_trials": len(test_trials["impostor_trials"]),
            "positive_trials": len(test_trials["positive_trials"]),
            "false_accepts": None,
            "false_accept_rate": None,
            "false_rejects": None,
            "false_reject_rate": None,
            "unlabeled_slices": test_trials["unlabeled_slices"],
            "note": "calibration unavailable; no thresholds were applied",
        }

    # ---- verdicts ----------------------------------------------------------
    run_manifest = {
        "script_version": SCRIPT_VERSION,
        "model": {"id": ECAPA_MODEL_ID, "revision": model_revision, "device": device},
        "recipe": {
            "window_seconds": WINDOW_SECONDS,
            "hop_seconds": HOP_SECONDS,
            "sample_rate": TARGET_SAMPLE_RATE,
            "silence_rms_floor": 0.01,
        },
        "candidate": {
            "path": str(candidate_path.resolve()),
            "sha256": _sha256_file(candidate_path),
        },
        "quarantine": {
            "path": str(quarantine_path.resolve()),
            "sha256": _sha256_file(quarantine_path),
        },
        "audio_dir": str(audio_dir.resolve()),
        "audio_sha256": {video: audio_hashes[video] for video in sorted(audio_hashes)},
        "splits": {span_id: splits[span_id] for span_id in sorted(splits)},
        "anchors": {guru: list(ANCHORS[guru]) for guru in sorted(ANCHORS)},
    }
    run_id = _sha256_bytes(_canonical_json(run_manifest).encode("utf-8"))

    calibration_revision = _sha256_bytes(
        _canonical_json(
            {
                "cosine_floor": cosine_floor,
                "margin_threshold": margin_threshold,
                "calibration_available": calibration_available,
                "model_revision": model_revision,
                "recipe": run_manifest["recipe"],
                "reference_stats": reference_stats,
                # Only when foreign slices were used, so a run without them keeps the
                # revision it always had.
                **({"foreign_slices_sha256": foreign_sha256} if foreign_sha256 else {}),
            }
        ).encode("utf-8")
    )

    generated_at = args.generated_at_utc or _dt.datetime.now(_dt.UTC).isoformat()

    rows: list[dict[str, Any]] = []
    for row in sorted(candidate, key=lambda item: str(item["source_span_id"])):
        span_id = str(row["source_span_id"])
        rows.append(
            build_verdict_row(
                candidate_row=row,
                vector=vectors.get(span_id),
                audio_failure=audio_failures.get(span_id),
                references=references,
                split=splits[span_id],
                calibration_available=calibration_available,
                cosine_floor=cosine_floor,
                margin_threshold=margin_threshold,
                run_id=run_id,
                calibration_revision=calibration_revision,
                model_revision=model_revision,
                device=device,
                audio_dir=audio_dir,
                audio_hashes=audio_hashes,
                audio_info=audio_info,
                slice_durations=slice_durations,
            )
        )

    # ---- validation --------------------------------------------------------
    validation_failures: list[dict[str, Any]] = []
    per_check = Counter()
    for row in rows:
        failures = validate_row(row)
        for failure in failures:
            per_check[failure] += 1
        if failures:
            validation_failures.append(
                {"source_span_id": row["source_span_id"], "failures": failures}
            )

    checks = {
        "rows_emitted": len(rows) == len(candidate),
        "rows_match_candidate_count": len(rows) == args.expected_spans,
        "unique_source_span_ids": len({row["source_span_id"] for row in rows}) == len(rows),
        "every_row_keyed_by_source_span_id": all(bool(row["source_span_id"]) for row in rows),
        "no_quarantined_span_in_verdicts": not (candidate_ids & quarantine_ids),
        "expected_spans_requested": args.expected_spans,
        "quarantined_rows_excluded": args.expected_quarantine,
        "quarantined_unique_source_span_ids": len(quarantine_ids),
        "quarantined_rows_without_span_id": quarantine_without_id,
        "row_schema_failures": len(validation_failures),
    }

    verdict_counts = Counter(row["verdict"] for row in rows)
    reason_counts = Counter(row["reason_code"] for row in rows)
    mismatches = [row for row in rows if row["verdict"] == VERDICT_REFUSED_GURU_MISMATCH]
    mismatch_breakdown = {
        "count": len(mismatches),
        "by_expected_to_predicted": {
            f"{expected}->{predicted}": count
            for (expected, predicted), count in sorted(
                Counter(
                    (row["expected_guru"], str(row["predicted_guru"])) for row in mismatches
                ).items()
            )
        },
        "videos": dict(Counter(row["video_id"] for row in mismatches).most_common(15)),
    }

    calibration_artifact = {
        "schema": CALIBRATION_SCHEMA,
        "script_version": SCRIPT_VERSION,
        "run_id": run_id,
        "generated_at_utc": generated_at,
        "calibration_method": "fp-ecapa-heldout-impostor-v1",
        "calibration_method_description": (
            "Guru reference centroids are built from the two human-confirmed anchor "
            "voiceprints plus the train-split slices that clear the repository's "
            "ENROLL_MIN/MARGIN rule against those anchors. The decision floors are the "
            "strictly-above-maximum held-out impostor cosine and margin on the "
            "calibration split; false-accept and false-reject rates are measured on a "
            "separate held-out test split."
        ),
        "calibration_available": calibration_available,
        "calibration_revision": calibration_revision,
        "model": {"id": ECAPA_MODEL_ID, "revision": model_revision, "device": device},
        "embedding_configuration": {
            "sample_rate": TARGET_SAMPLE_RATE,
            "channels": TARGET_CHANNELS,
            "bits_per_sample": TARGET_BITS,
            "window_seconds": WINDOW_SECONDS,
            "hop_seconds": HOP_SECONDS,
            "silence_rms_floor": 0.01,
            "slice_pooling": "mean of window vectors, then L2 normalization",
            "reference_pooling": "mean of member vectors, then L2 normalization",
            "similarity": "cosine",
        },
        "reference_construction": {
            "method": "anchor voiceprint + train-split slices (ENROLL_MIN / ANCHOR_MARGIN)",
            "constants_source": "backend/scripts/ops/speaker_attribution.py (inherited unchanged)",
            "enroll_min": ENROLL_MIN,
            "cohort_max": COHORT_MAX,
            "anchor_margin": ANCHOR_MARGIN,
            "anchor_label_min": ANCHOR_LABEL_MIN,
            "cluster_distance": CLUSTER_DISTANCE,
            "anchors": anchor_details,
            "per_guru": reference_stats["references"],
            "train_slices_selected": reference_stats["train_slices_selected"],
            "train_slices_unlabeled": reference_stats["train_slices_unlabeled"],
        },
        "split_definition": {
            "salt": SPLIT_SALT,
            "bounds": {name: weight for name, weight in SPLIT_BOUNDS},
            "rule": "sha256(salt|video_id) -> uniform bucket; anchor videos are forced to train",
            "per_split_span_counts": dict(Counter(splits.values())),
            "per_split_video_counts": {
                split: len(
                    {
                        row["video_id"]
                        for row in candidate
                        if splits[str(row["source_span_id"])] == split
                    }
                )
                for split, _weight in SPLIT_BOUNDS
            },
        },
        "trial_counts": {
            "calibration_positive_trials": len(calibration_trials["positive_trials"]),
            "calibration_impostor_trials": len(calibration_trials["impostor_trials"]),
            "calibration_unlabeled_slices": calibration_trials["unlabeled_slices"],
            "test_positive_trials": len(test_trials["positive_trials"]),
            "test_impostor_trials": len(test_trials["impostor_trials"]),
            "test_unlabeled_slices": test_trials["unlabeled_slices"],
            "min_impostor_trials_required": MIN_IMPOSTOR_TRIALS,
            "foreign_voice_slices_used": len(foreign_vectors),
            "foreign_voice_slices_failed": dict(foreign_failures),
            "foreign_voice_calibration_trials": len(foreign_calibration_trials),
            "foreign_voice_test_trials": len(foreign_test_trials),
            "foreign_slices_sha256": foreign_sha256 or None,
        },
        "score_distributions": {
            "calibration_impostor_cosine": calibration.get("impostor_cosine_distribution"),
            "calibration_impostor_margin": calibration.get("impostor_margin_distribution"),
            "calibration_positive_cosine": calibration.get("positive_cosine_distribution"),
            "calibration_positive_margin": calibration.get("positive_margin_distribution"),
            "test_impostor_cosine": test_evaluation.get("impostor_cosine_distribution"),
            "test_impostor_margin": test_evaluation.get("impostor_margin_distribution"),
            "test_positive_cosine": test_evaluation.get("positive_cosine_distribution"),
            "test_positive_margin": test_evaluation.get("positive_margin_distribution"),
        },
        "thresholds": {
            "cosine_floor": calibration.get("cosine_floor"),
            "margin_threshold": calibration.get("margin_threshold"),
        },
        "decision_rule": {
            "order": [
                "calibration_available",
                "predicted_guru == expected_guru",
                "cosine >= cosine_floor",
                "margin >= margin_threshold",
            ],
            "cosine_floor_derivation": (
                "max(0, max held-out impostor cosine) + 1e-6 — strictly above every "
                "observed impostor score, so the calibration split's false-accept "
                "rate is zero by construction and the honest number is the test split"
            ),
            "margin_threshold_derivation": (
                "max(0, max held-out impostor margin) + 1e-6 — same rule, and the "
                "floor at zero is the repository's own guard against a threshold that "
                "would weaken verification"
            ),
            "margin_gate_note": (
                "When every held-out impostor margin is negative the derived margin "
                "threshold collapses to 1e-06 and the margin gate becomes a strict "
                "ordering requirement (the predicted reference must be the best one) "
                "rather than a separation requirement. The separation evidence is in "
                "the cosine floor and in the score distributions."
            ),
            "trial_label_rule": (
                "a held-out slice is a trial only when it clears ANCHOR_LABEL_MIN "
                f"({ANCHOR_LABEL_MIN}) against its anchor voiceprint and beats the "
                f"other anchor by ANCHOR_MARGIN ({ANCHOR_MARGIN}); otherwise it is "
                "unlabeled and excluded from every trial"
            ),
        },
        "false_accept": {
            "calibration": {
                "count": calibration.get("calibration_false_accepts"),
                "rate": calibration.get("calibration_false_accept_rate"),
                "note": "zero by construction on the calibration split (the floor sits above every observed impostor)",
            },
            "test": {
                "count": test_evaluation.get("false_accepts"),
                "rate": test_evaluation.get("false_accept_rate"),
                "note": "held-out measurement; this is the honest number",
            },
        },
        "false_accept_bound": far_bound_record(
            test_evaluation.get("false_accepts"),
            test_evaluation.get("impostor_trials"),
            target=DEFAULT_TARGET_FAR,
        ),
        "false_reject": {
            "calibration": {
                "count": calibration.get("calibration_false_rejects"),
                "rate": calibration.get("calibration_false_reject_rate"),
            },
            "test": {
                "count": test_evaluation.get("false_rejects"),
                "rate": test_evaluation.get("false_reject_rate"),
            },
        },
        "data_hashes": {
            "candidate_sha256": run_manifest["candidate"]["sha256"],
            "quarantine_sha256": run_manifest["quarantine"]["sha256"],
            "audio_sha256": run_manifest["audio_sha256"],
            "input_manifest_sha256": run_id,
        },
        "honest_limits": [
            "The trial labels come from the two human-confirmed anchor moments, not from a "
            "human-labelled clip set. The repository has no filled human speaker-label sheet, "
            "so a human-certified false-accept rate is not available and remains a B7 dependency.",
            "The trial label rule and the reference centroids share the same two human "
            "anchors, so the measured false-accept and false-reject rates are a relative "
            "consistency measurement on held-out videos, not an independent certification.",
            "The expected guru of a span is the corpus assignment carried by the Phase 3 "
            "candidate. It is the claim under test, never the evidence.",
            "A span whose acoustic prediction disagrees with the corpus assignment is "
            "refused_guru_mismatch and is never promoted to verified.",
        ],
    }

    summary = {
        "schema": SUMMARY_SCHEMA,
        "script_version": SCRIPT_VERSION,
        "run_id": run_id,
        "generated_at_utc": generated_at,
        "release_blocking": True,
        "release_blocking_reasons": [
            "Phase 2 only closes or measures B1; B4 (legacy/context schema separation), "
            "B5 (independent rights register), B6 (clinician review) and B7 (human gold "
            "labels and public-scale evidence) remain open.",
            "The rebuilt candidate has NOT been written to any collection; the live v10 "
            "collection still carries its defective coordinates.",
            "FIRST_PERSON_CONTEXT_HARNESS_ENABLED stays false.",
        ],
        "inputs": {
            "candidate": {
                "path": str(candidate_path.resolve()),
                "sha256": run_manifest["candidate"]["sha256"],
            },
            "quarantine": {
                "path": str(quarantine_path.resolve()),
                "sha256": run_manifest["quarantine"]["sha256"],
            },
            "audio_dir": str(audio_dir.resolve()),
        },
        "model": {"id": ECAPA_MODEL_ID, "revision": model_revision, "device": device},
        "recipe": run_manifest["recipe"],
        "requested": {
            "exact_candidate_spans": args.expected_spans,
            "quarantined_rows_excluded": args.expected_quarantine,
            "quarantined_unique_source_span_ids": len(quarantine_ids),
            "quarantined_rows_without_span_id": quarantine_without_id,
        },
        "verdicts": {
            "rows_emitted": len(rows),
            "by_verdict": {name: verdict_counts.get(name, 0) for name in VERDICT_CATEGORIES},
            "by_verdict_group": dict(Counter(row["verdict_group"] for row in rows)),
            "by_reason_code": {name: reason_counts.get(name, 0) for name in VERDICT_CATEGORIES},
            "guru_mismatch_breakdown": mismatch_breakdown,
        },
        "calibration": {
            "calibration_available": calibration_available,
            "calibration_revision": calibration_revision,
            "cosine_floor": calibration.get("cosine_floor"),
            "margin_threshold": calibration.get("margin_threshold"),
            "positive_trials": calibration.get("positive_trials"),
            "impostor_trials": calibration.get("impostor_trials"),
            "test_evaluation": test_evaluation,
            "per_split_span_counts": dict(Counter(splits.values())),
        },
        "audio": {
            "audio_files_opened": audio_files_opened,
            "audio_files_referenced": len(audio_hashes),
            "audio_slices_generated": len(vectors),
            "audio_slice_failures": dict(Counter(audio_failures.values())),
            "audio_source": "audio_archive/wavs/{video_id}.wav only",
            "asr_root_audio_used": False,
            "embedding_cache_note": (
                "the embedding cache is keyed by model id, model revision, device, window "
                "recipe, video id, audio sha256 and the slice bounds, so a cached slice is "
                "only reused when the exact same audio and recipe produced it"
            ),
        },
        "validation": {
            "checks": checks,
            "row_failure_reasons": dict(per_check),
            "failures": validation_failures[:50],
        },
        "mutations": {
            "qdrant_reads": 0,
            "qdrant_writes": 0,
            "alias_changes": 0,
            "redis_operations": 0,
            "environment_changes": 0,
            "docker_changes": 0,
            "deployments": 0,
            "railway_actions": 0,
            "harness_enabled": False,
        },
    }

    verdict_index = {
        "schema": VERDICT_INDEX_SCHEMA,
        "script_version": SCRIPT_VERSION,
        "run_id": run_id,
        "generated_at_utc": generated_at,
        "key_field": "source_span_id",
        "verdict_count": len(rows),
        "calibration_revision": calibration_revision,
        "verdicts": {row["source_span_id"]: row for row in rows},
    }

    written = {
        "verdicts": _write_json_file(args.out_verdicts, verdict_index),
        "calibration": _write_json_file(args.out_calibration, calibration_artifact),
        "summary": _write_json_file(args.out_summary, summary),
    }
    if args.out_verdicts_jsonl:
        target = Path(args.out_verdicts_jsonl)
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("w", encoding="utf-8") as handle:
            for row in rows:
                handle.write(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n")
        written["verdicts_jsonl"] = str(target)

    trustworthy = (
        checks["rows_emitted"]
        and checks["rows_match_candidate_count"]
        and checks["unique_source_span_ids"]
        and checks["no_quarantined_span_in_verdicts"]
        and not validation_failures
    )
    summary["validation"]["trustworthy"] = bool(trustworthy)
    _write_json_file(args.out_summary, summary)

    print(
        json.dumps(
            {
                "script_version": SCRIPT_VERSION,
                "run_id": run_id,
                "rows_emitted": len(rows),
                "verdicts": dict(verdict_counts),
                "calibration_available": calibration_available,
                "cosine_floor": calibration.get("cosine_floor"),
                "margin_threshold": calibration.get("margin_threshold"),
                "positive_trials": calibration.get("positive_trials"),
                "impostor_trials": calibration.get("impostor_trials"),
                "test_evaluation": test_evaluation,
                "validation_trustworthy": bool(trustworthy),
                # Run-scoped counters are printed, never written into the
                # artifacts: the artifacts must stay byte-identical between a
                # cold-cache run and a warm-cache run.
                "audio_slices_embedded_this_run": slices_generated,
                "audio_slices_from_embedding_cache": slices_from_cache,
                "written": written,
            },
            indent=2,
            sort_keys=True,
        )
    )
    if not trustworthy:
        return EXIT_INVALID_INPUT
    return EXIT_RELEASE_BLOCKED


if __name__ == "__main__":
    raise SystemExit(main())
