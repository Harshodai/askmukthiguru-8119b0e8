#!/usr/bin/env python3
"""Build and populate first_person_v10 with full corpus videos.

Extracts clean verbatim sentences using ingest.verbatim.boundaries,
applies ECAPA-TDNN acoustic speaker verification PER SPAN against guru voice
centroids with calibrated floors, computes BGE-M3 1024-dim dense + sparse
embeddings, and upserts strict ParentUnit / SourceSpan records into Qdrant.

Honesty invariants (see docs/FIRST_PERSON_COLLECTION_EVOLUTION_V1_TO_V10.md):
  * Word timings come from a real transcript alignment. A video without a
    reliable alignment is quarantined as ``no_word_timings``; no timing is ever
    synthesised from the WAV duration.
  * Each span is verified from its OWN ``start_ms``/``end_ms`` slice, never
    from the first 60 s of the video, and only when the predicted guru matches
    the video's guru AND both calibrated floors clear. Failing spans stay
    ``speaker_verified=False``.
  * Paths and the Qdrant endpoint come from arguments/environment; the shared
    QdrantService honours ``QDRANT_URL`` / ``QDRANT_LOCAL_PATH``.

Run from ``backend/``:

    python -m scripts.ops.build_full_corpus_v10 \\
        --wav-dir "$WAV_DIR" --attr-root "$ATTR_ROOT" --target-collection first_person_v10
"""

from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import logging
import math
import os
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import numpy as np
import torch


def _resolve_backend_root() -> Path:
    """Directory that holds the ``domain``/``services`` packages.

    The canonical copy lives at ``backend/scripts/ops/`` (this file's
    ``parents[2]``). The byte-identical repo-root copy at ``scripts/ops/``
    resolves ``parents[2]`` to the repository root instead, so the backend
    directory is found by looking for the packages it actually imports.
    """
    here = Path(__file__).resolve()
    for candidate in here.parents:
        if (candidate / "domain" / "first_person_context.py").is_file():
            return candidate
        nested = candidate / "backend"
        if (nested / "domain" / "first_person_context.py").is_file():
            return nested
    raise RuntimeError(f"cannot locate the backend package root from {here}")


_BACKEND = _resolve_backend_root()
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from qdrant_client.models import PointStruct  # noqa: E402

from domain.first_person_context import (  # noqa: E402
    AnswerRole,
    BoundaryStatus,
    CompletenessStatus,
    ParentUnit,
    ProvenanceKind,
    SourceSpan,
    SpeakerRole,
    TextOrigin,
    clip_text_hash,
    make_parent_unit_id,
    make_source_span_id,
)
from ingest.verbatim.asr_cleaner import asr_cleaner_flags  # noqa: E402
from ingest.verbatim.boundaries import boundary_defects  # noqa: E402
from ingest.verbatim.gates import script_and_loop_problem  # noqa: E402

# One shared location for the pinned rights register: the serving pipeline
# fingerprints the same file, so a drifted literal would pin two different ones.
from services.first_person_serving_contract import (  # noqa: E402
    RIGHTS_MANIFEST_RELPATH,
    rights_manifest_path,
)

try:  # pragma: no cover - import-shape dependent
    from scripts.ops import verify_speakers_ecapa as speaker_verify  # noqa: E402
except ImportError:  # repo-root copy: the sibling lives in the backend tree
    import importlib.util

    def _load_sibling(name: str):
        candidates = [
            _BACKEND / "scripts" / "ops" / f"{name}.py",
            Path("/app/backend_scripts/ops") / f"{name}.py",
        ]
        path = next((c for c in candidates if c.is_file()), candidates[0])
        spec = importlib.util.spec_from_file_location(name, path)
        if spec is None or spec.loader is None:
            raise RuntimeError(f"cannot load sibling module {name} from {path}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
        return module

    speaker_verify = _load_sibling("verify_speakers_ecapa")
from services.embedding_service import EmbeddingService  # noqa: E402
from services.first_person_context_store import (  # noqa: E402
    parent_point_id,
    point_id_for_record,
)
from services.qdrant.utils import QdrantUtils  # noqa: E402
from services.qdrant_service import QdrantService  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("build_full_corpus_v10")

_REPO_ROOT = _BACKEND.parent
DEFAULT_CORPUS_VERSION = "fp-context-transcript-v1"
GURU_IDS = ("krishnaji", "preethaji")

# Window-level speaker check: how far below the whole-span floor the window floor
# sits. Provisional (calibrate on held-out impostors before treating it as
# measured). The rule itself is strict by design: ONE window below the floor
# revokes clearance, because a short host interruption inside a guru span is an
# attribution error, and a run-limit would let a single foreign window through.
# (Rejected 2026-10-26: "revoke only after two consecutive weak windows". It
# weakens an uncalibrated gate; D3 calibration must land first.)
WINDOW_COSINE_FLOOR_MARGIN = 0.10

CLEARED_CHANNELS = {
    "sri preethaji & sri krishnaji",
    "ekam",
    "o&o academy",
    "times now",
}
CLEARED_VIDEO_IDS = {
    "TqxxCYnAxo8",
    "UlOt31lBhLY",
    "iKkySU5r_x8",
    "hUmlujE6SN0",
    "HCs6I_BNtxo",
}


def load_calibration(path: Path) -> tuple[float, float]:
    """Return ``(cosine_floor, margin_threshold)`` from the ECAPA calibration.

    Fail closed: an absent, unmeasurable, or malformed calibration means a
    speaker can never be verified, so the caller must stop instead of writing
    clips with an invented floor.
    """
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise RuntimeError(
            f"Speaker calibration {path} is unreadable ({exc}). Run "
            "scripts.ops.verify_speakers_ecapa first; no clip can be verified without it."
        ) from exc
    if data.get("calibration_available") is False:
        raise RuntimeError(
            f"Speaker calibration {path} reports calibration_available=false "
            "(too few held-out impostor trials). Every span would stay unverified."
        )
    # The phase-2 certification artifact nests its measured floors under "thresholds".
    floors = data.get("thresholds") if isinstance(data.get("thresholds"), dict) else {}
    cosine_floor = data.get("cosine_floor", floors.get("cosine_floor"))
    margin_threshold = data.get(
        "threshold", data.get("margin_threshold", floors.get("margin_threshold"))
    )
    for name, value in (("cosine_floor", cosine_floor), ("margin_threshold", margin_threshold)):
        if not isinstance(value, (int, float)) or not math.isfinite(float(value)):
            raise RuntimeError(f"Speaker calibration {path} has no usable {name}: {value!r}")
    return float(cosine_floor), float(margin_threshold)


#: validate_release_grade() codes that block a video from being written. The duration
#: band is reported only.
RELEASE_GRADE_BLOCKING = frozenset(
    {
        "speaker_verified_without_method",
        "boundary_status_verified_with_defects",
        "unverified_contextual_header_claimed",
    }
)


def compute_centroids(
    points_file: Path, cache_dir: Path, *, allow_label_derived: bool = False
) -> dict[str, np.ndarray]:
    """Teacher voice centroids from the points export's own ``speaker_verified`` labels.

    CIRCULAR: those labels are the claim under audit (2026-10-25 data audit D3), so a
    centroid built from them can only reproduce the earlier decision, not check it.
    Refused unless ``allow_label_derived`` is set deliberately (bootstrap only). The
    non-circular reference is human-confirmed anchors, see
    ``regenerate_v10_span_ecapa_verdicts.py``.
    """
    if not allow_label_derived:
        raise RuntimeError(
            "refusing to build speaker centroids from payload speaker_verified labels: "
            "that check is circular. Pass --allow-label-centroids only to bootstrap, "
            "and prefer human-confirmed anchors."
        )
    embeds_file = cache_dir / "embeddings.npz"
    if not (points_file.is_file() and embeds_file.is_file()):
        raise RuntimeError(f"Missing {points_file} or cached {embeds_file} for centroids")

    embeds = np.load(embeds_file)
    data = json.loads(points_file.read_text(encoding="utf-8"))
    points = data.get("result", {}).get("points", [])

    by_guru = defaultdict(list)
    for p in points:
        pid = str(p.get("id"))
        if pid in embeds and p.get("payload", {}).get("speaker_verified") is True:
            guru = str(p["payload"].get("teacher_id") or "").lower().strip()
            if guru:
                by_guru[guru].append((pid, embeds[pid]))

    train = defaultdict(list)
    for guru, rows in sorted(by_guru.items()):
        rows.sort(key=lambda r: r[0])
        for idx, (_pid, vec) in enumerate(rows):
            if idx % 2 == 0:
                train[guru].append(vec)

    centroids = {}
    for guru, vecs in train.items():
        if vecs:
            mean = np.mean(np.stack(vecs), axis=0)
            centroids[guru] = mean / float(np.linalg.norm(mean))
    return centroids


def verify_span_speaker(
    wav_path: Path,
    start_ms: int,
    end_ms: int,
    embedder: Any,
    centroids: dict[str, np.ndarray],
    *,
    cosine_floor: float,
    margin_threshold: float,
    window_ms: int = 2500,
    hop_ms: int = 1000,
) -> tuple[str | None, bool, float, float, dict[str, Any]]:
    """Embed ONE span's audio slice with sub-window scoring to catch host interruptions (D3).

    Returns (predicted_guru, cleared_floors, cosine, margin, window_metrics).
    """
    audio = speaker_verify._slice(wav_path, start_ms, end_ms)
    empty_metrics = {"window_count": 0, "min_window_cosine": 0.0, "foreign_window_count": 0}
    if audio is None:
        return None, False, 0.0, 0.0, empty_metrics

    with torch.no_grad():
        emb = embedder.encode_batch(torch.from_numpy(audio).unsqueeze(0))
    vector = emb.squeeze().detach().cpu().numpy().astype(np.float32)
    norm = float(np.linalg.norm(vector))
    if norm <= 0:
        return None, False, 0.0, 0.0, empty_metrics
    vector /= norm

    scores = {guru: float(np.dot(vector, c)) for guru, c in centroids.items()}
    if not scores:
        return None, False, 0.0, 0.0, empty_metrics
    ordered = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    predicted, best = ordered[0]
    runner_up = ordered[1][1] if len(ordered) > 1 else 0.0
    margin = best - runner_up
    cleared = best >= cosine_floor and margin >= margin_threshold

    # Window-level check for spans longer than window_ms. A span whose whole-slice
    # score already failed the calibrated floors is not re-scored window by
    # window: that pass costs embeddings and cannot rescue it.
    span_duration_ms = end_ms - start_ms
    min_win_cos = best
    foreign_window_count = 0
    win_count = 1

    if cleared and span_duration_ms > window_ms:
        # A 2.5 s window carries less speaker evidence than the whole span
        # (ECAPA EER rises from ~1.0% on long utterances to ~1.8% at 2 s), so the
        # window pass uses its own floor instead of the whole-span calibration
        # floor. Both numbers stay provisional until a held-out impostor run
        # calibrates them (D3 threshold is UNPROVEN).
        window_floor = cosine_floor - WINDOW_COSINE_FLOOR_MARGIN
        win_scores = []
        cur_w_start = start_ms
        expected_windows = 1 + (span_duration_ms - window_ms) // hop_ms
        while cur_w_start + window_ms <= end_ms:
            w_audio = speaker_verify._slice(wav_path, cur_w_start, cur_w_start + window_ms)
            if w_audio is not None and len(w_audio) > 0:
                with torch.no_grad():
                    w_emb = embedder.encode_batch(torch.from_numpy(w_audio).unsqueeze(0))
                w_vec = w_emb.squeeze().detach().cpu().numpy().astype(np.float32)
                w_norm = float(np.linalg.norm(w_vec))
                if w_norm > 0:
                    w_vec /= w_norm
                    w_score = float(np.dot(w_vec, centroids.get(predicted, vector)))
                    win_scores.append(w_score)
                    if w_score < window_floor:
                        foreign_window_count += 1
            cur_w_start += hop_ms

        if win_scores:
            win_count = len(win_scores)
            min_win_cos = min(win_scores)
            # Strict rule: any expected window that cannot be scored, or any window
            # below the floor, revokes the span's clearance.
            if len(win_scores) < expected_windows or min_win_cos < window_floor:
                cleared = False
        else:
            if expected_windows > 0:
                cleared = False

    metrics = {
        "window_count": win_count,
        "min_window_cosine": round(min_win_cos, 4),
        "foreign_window_count": foreign_window_count,
    }
    return predicted, cleared, best, margin, metrics


def parse_transcript(md_path: Path) -> tuple[str, str, str, list[str], str]:
    """Return (channel, speaker, transcript_hash, words, artifact_sha256).

    ``transcript_hash`` hashes the transcript *body* (it is part of the span id);
    ``artifact_sha256`` hashes the whole markdown file, so a rebuild can prove
    which on-disk artifact a span's coordinates came from (D15)."""
    p_md_bytes = md_path.read_bytes()
    raw = p_md_bytes.decode("utf-8", errors="replace")
    channel = ""
    speaker = ""
    transcript_hash = ""

    for line in raw.splitlines()[:25]:
        if "Channel:" in line:
            channel = line.split("Channel:", 1)[1].strip().strip("`* ")
        elif "Speaker:" in line:
            speaker = line.split("Speaker:", 1)[1].strip().strip("`* ")
        elif "Transcript Hash:" in line:
            transcript_hash = line.split("Transcript Hash:", 1)[1].strip().strip("`* ")

    body = raw.split("## Transcript", 1)[1] if "## Transcript" in raw else raw
    body = re.split(r"\n## ", body)[0].strip()

    computed_hash = hashlib.sha256(body.encode("utf-8")).hexdigest()
    if transcript_hash and transcript_hash != computed_hash:
        logger.warning(
            "Transcript hash header mismatch for %s (header=%s != computed=%s)",
            md_path.name,
            transcript_hash,
            computed_hash,
        )
        transcript_hash = computed_hash
    elif not transcript_hash:
        transcript_hash = computed_hash

    words = re.findall(r"\S+", re.sub(r"\s+", " ", body).strip())
    artifact_sha256 = hashlib.sha256(p_md_bytes).hexdigest()
    return channel, speaker, transcript_hash, words, artifact_sha256


_EDGE_PUNCT_RE = re.compile(r"^[^\w]+|[^\w]+$", re.UNICODE)


def _strip_edge_punct(token: str) -> str:
    """Token without surrounding punctuation, so ``peace.`` matches ``peace``."""
    return _EDGE_PUNCT_RE.sub("", token)


def _edit_distance_le_1(s1: str, s2: str) -> bool:
    """True if Levenshtein edit distance between s1 and s2 is at most 1."""
    if abs(len(s1) - len(s2)) > 1:
        return False
    if s1 == s2:
        return True
    if len(s1) == len(s2):
        return sum(c1 != c2 for c1, c2 in zip(s1, s2)) <= 1
    short, long_ = (s1, s2) if len(s1) < len(s2) else (s2, s1)
    i = j = diff = 0
    while i < len(short) and j < len(long_):
        if short[i] != long_[j]:
            diff += 1
            if diff > 1:
                return False
            j += 1
        else:
            i += 1
            j += 1
    return True


def _align_words_to_timings(
    words: list[str], timed_words: list[dict[str, Any]]
) -> list[tuple[float, float]] | None:
    """Map every transcript word onto a timed ASR word, or return None.

    Strict 1-to-1 or edit-distance <= 1 alignment only. Rejects and refuses
    to proportionally interpolate disparate timing blocks (D17).
    """
    if not words or not timed_words:
        return None
    timed_text = [str(entry.get("w", "")) for entry in timed_words]
    matcher = difflib.SequenceMatcher(
        None, [w.lower() for w in words], [w.lower() for w in timed_text], autojunk=False
    )
    out: list[tuple[float, float] | None] = [None] * len(words)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            for offset in range(i2 - i1):
                entry = timed_words[j1 + offset]
                out[i1 + offset] = (float(entry.get("start", 0)), float(entry.get("end", 0)))
        elif tag == "replace":
            # D17: Reject proportional interpolation across length-mismatched or divergent blocks
            if (i2 - i1) != (j2 - j1):
                return None
            for offset in range(i2 - i1):
                # Punctuation is not a word difference: compare word forms only,
                # then keep the existing edit-distance bound.
                w_trans = _strip_edge_punct(words[i1 + offset].lower())
                w_timed = _strip_edge_punct(str(timed_words[j1 + offset].get("w", "")).lower())
                if w_trans != w_timed and not _edit_distance_le_1(w_trans, w_timed):
                    return None
                entry = timed_words[j1 + offset]
                out[i1 + offset] = (float(entry.get("start", 0)), float(entry.get("end", 0)))
        else:
            return None
    if any(item is None for item in out):
        return None
    return out


def asr_provenance(video_id: str, tb_dirs: list[Path]) -> tuple[str | None, str | None]:
    """(engine, model) of the archived Parakeet run that timed this video, else (None, None).

    Read from ``<root>/raw/<id>_parakeet.json`` (the artifact the audit re-derives
    provenance from); a missing or failed run records nothing rather than a guess.
    """
    for tb in tb_dirs:
        raw = tb.parent / "raw" / f"{video_id}_parakeet.json"
        if not raw.is_file():
            continue
        try:
            data = json.loads(raw.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(data, dict) and data.get("ok") is not False and data.get("model"):
            return "parakeet_mlx", str(data["model"])
    return None, None


def words_from_timed_file(
    video_id: str, tb_dirs: list[Path]
) -> tuple[list[str], list[tuple[float, float]], str] | None:
    """Words, their (start, end) seconds and the file sha256, straight from a timed
    word file; None when absent or any word lacks a time.

    Opt-in route (``--text-from-words``) for a video whose markdown transcript is
    missing, garbled or unalignable. The text is the voted ASR word stream itself, so
    text and times always come from the same file; nothing is synthesised.
    """
    for tb_dir in tb_dirs:
        candidate = tb_dir / f"{video_id}.json"
        if not candidate.is_file():
            continue
        raw = candidate.read_bytes()
        try:
            data = json.loads(raw.decode("utf-8"))
        except Exception:
            continue
        if not isinstance(data, list) or not data:
            continue
        words: list[str] = []
        times: list[tuple[float, float]] = []
        for row in data:
            if not isinstance(row, dict) or "start" not in row or "end" not in row:
                return None
            token = str(row.get("w", "")).strip()
            if not token:
                continue
            words.append(token)
            times.append((float(row["start"]), float(row["end"])))
        if words:
            return words, times, hashlib.sha256(raw).hexdigest()
    return None


def get_word_timings(
    video_id: str, words: list[str], tb_dirs: list[Path]
) -> list[tuple[float, float]] | None:
    """Word-level timings from a Transcripts_B alignment, or None.

    There is deliberately no synthetic fallback: spreading the WAV's runtime
    evenly across the words would emit playback offsets that point at audio the
    words were never spoken in. The caller quarantines the video instead.
    """
    for tb_dir in tb_dirs:
        candidate = tb_dir / f"{video_id}.json"
        if not candidate.is_file():
            continue
        try:
            tb_data = json.loads(candidate.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("Video %s: unreadable timing file %s (%s)", video_id, candidate, exc)
            continue
        if not isinstance(tb_data, list) or not tb_data:
            continue
        if len(tb_data) == len(words):
            return [(float(w.get("start", 0)), float(w.get("end", 0))) for w in tb_data]
        aligned = _align_words_to_timings(words, [w for w in tb_data if isinstance(w, dict)])
        if aligned is not None:
            return aligned
        logger.warning(
            "Video %s: %s could not be aligned word-for-word with the transcript",
            video_id,
            candidate.name,
        )
    return None


def _make_span(spec: dict[str, Any]) -> dict[str, Any]:
    return {
        "word_start": spec["word_start"],
        "word_end": spec["word_end"],
        "start_ms": spec["start_ms"],
        "end_ms": spec["end_ms"],
        "text": spec["text"],
    }


def drop_zero_duration_specs(
    specs: list[dict[str, Any]], quarantined: Counter[str]
) -> list[dict[str, Any]]:
    """Quarantine spans whose timing collapsed to ``end_ms <= start_ms``.

    Disputed ASR words can all share one timestamp; such a span has no audio window
    to verify or play, and ``SourceSpan`` rejects it. Counted, never synthesised.
    """
    kept: list[dict[str, Any]] = []
    for spec in specs:
        if spec["end_ms"] <= spec["start_ms"]:
            quarantined["zero_duration_span"] += 1
            continue
        kept.append(spec)
    return kept


def slice_into_sentence_spans(
    words: list[str], timings: list[tuple[float, float]], min_words: int = 45, max_words: int = 70
) -> list[dict[str, Any]]:
    terminals = (".", "?", "!")
    sentences: list[tuple[int, int, str, int, int]] = []
    cur: list[str] = []
    start_idx = 0

    for i, w in enumerate(words):
        cur.append(w)
        if w.endswith(terminals) or i == len(words) - 1:
            s_text = " ".join(cur)
            s_start_ms = int(timings[start_idx][0] * 1000)
            s_end_ms = int(timings[i][1] * 1000)
            sentences.append((start_idx, i + 1, s_text, s_start_ms, s_end_ms))
            cur = []
            start_idx = i + 1

    # Filter out sentences with boundary defects or script garbage
    clean_sentences = []
    for s_start, s_end, s_text, sms, ems in sentences:
        defects = boundary_defects(s_text.split())
        garbage = script_and_loop_problem(s_text)
        if not defects and not garbage:
            clean_sentences.append((s_start, s_end, s_text, sms, ems))

    if not clean_sentences:
        return []

    # Group CONTIGUOUS clean sentences into child spans. Target 45-70 words.
    spans: list[dict[str, Any]] = []
    group_sentences: list[tuple[int, int, str, int, int]] = []
    group_words = 0

    def _flush_group() -> None:
        nonlocal group_sentences, group_words
        if not group_sentences:
            return
        spans.append(
            _make_span(
                {
                    "word_start": group_sentences[0][0],
                    "word_end": group_sentences[-1][1],
                    "start_ms": group_sentences[0][3],
                    "end_ms": group_sentences[-1][4],
                    "text": " ".join(s[2] for s in group_sentences),
                }
            )
        )
        group_sentences = []
        group_words = 0

    for item in clean_sentences:
        item_words = item[1] - item[0]
        if group_sentences and item[0] != group_sentences[-1][1]:
            _flush_group()
        elif (
            group_sentences and (group_words + item_words > max_words) and group_words >= min_words
        ):
            _flush_group()
        group_sentences.append(item)
        group_words += item_words
        if group_words >= min_words and item[2].endswith(terminals):
            if group_words >= max_words or len(group_sentences) >= 2:
                _flush_group()

    # Residual tail: merge into the previous span only when contiguous and within max_words
    if group_sentences:
        contiguous = bool(spans) and group_sentences[0][0] == spans[-1]["word_end"]
        if (
            contiguous
            and (spans[-1]["word_end"] - spans[-1]["word_start"] + group_words) <= max_words
        ):
            spans[-1]["word_end"] = group_sentences[-1][1]
            spans[-1]["end_ms"] = group_sentences[-1][4]
            spans[-1]["text"] = f"{spans[-1]['text']} {' '.join(s[2] for s in group_sentences)}"
            group_sentences = []
            group_words = 0
        elif group_words >= min_words:
            _flush_group()

    return spans


def _expected_guru(speaker_meta: str, channel_name: str) -> str | None:
    """Guru named by the transcript/channel metadata, when unambiguous."""
    blob = f"{speaker_meta} {channel_name}".lower()
    named = [guru for guru in GURU_IDS if guru in blob]
    return named[0] if len(named) == 1 else None


def _embedding_provenance() -> tuple[str | None, str | None]:
    """Model identity of the vectors this run writes (D4).

    Read from the configured backend instead of assumed: the ONNX encoder and the
    FlagEmbedding path pin different commits, so a payload naming the wrong
    revision is worse than one naming none.
    """
    from app.config import settings

    backend = str(getattr(settings, "embedding_backend", "") or "").lower()
    model = getattr(settings, "embedding_model", None)
    if "onnx" in backend:
        from services.embedding_service import EmbeddingService

        onnx_model = EmbeddingService._ONNX_CANDIDATE
        onnx_rev = (
            getattr(settings, "hf_revision", None)
            or os.environ.get("HF_REVISION")
            or EmbeddingService._ONNX_ENCODER_REVISION
        )
        return onnx_model, onnx_rev
    return model, getattr(settings, "embedding_model_revision", None)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--qdrant-url",
        default="",
        help="Override QDRANT_URL; QDRANT_LOCAL_PATH is honoured when set",
    )
    parser.add_argument("--target-collection", default="first_person_v10")
    parser.add_argument("--corpus-version", default=DEFAULT_CORPUS_VERSION)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument(
        "--limit", type=int, default=0, help="Limit number of videos to process (0 = all)"
    )
    parser.add_argument(
        "--only-videos",
        default="",
        help="Comma-separated video ids: build only these (still skips videos already "
        "in the target collection, so a run is purely additive).",
    )
    parser.add_argument(
        "--wav-dir",
        default=os.environ.get("WAV_DIR", ""),
        help="WAV archive directory (default: $WAV_DIR)",
    )
    parser.add_argument(
        "--attr-root",
        default=os.environ.get("ATTR_ROOT", os.environ.get("MUKTHIGURU_ATTR_ROOT", "")),
        help="Attribution data root holding transcripts_B/ and inventory (default: $ATTR_ROOT)",
    )
    parser.add_argument("--transcripts-dir", default=str(_REPO_ROOT / "transcripts"))
    parser.add_argument(
        "--cache-dir",
        default=os.environ.get("FP_CONTEXT_CACHE", str(_REPO_ROOT / ".work/fp_context/speaker")),
    )
    parser.add_argument(
        "--text-from-words",
        action="store_true",
        help="Only for videos that would be quarantined as no_word_timings: take the span "
        "text from the timed word file itself instead of the markdown transcript. "
        "Off by default; certified behaviour is unchanged.",
    )
    parser.add_argument(
        "--references-npz",
        default="",
        help="Guru reference centroids saved by regenerate_v10_span_ecapa_verdicts "
        "--out-references (human-anchor based, non-circular). Preferred over label centroids.",
    )
    parser.add_argument(
        "--allow-label-centroids",
        action="store_true",
        help="Build voice centroids from payload speaker_verified labels. CIRCULAR; "
        "bootstrap only (D3).",
    )
    parser.add_argument(
        "--centroid-points",
        default=str(_REPO_ROOT / ".work/fp_context/v9_points.json"),
        help="Qdrant export used to build the guru voice centroids",
    )
    parser.add_argument(
        "--calibration",
        default=str(_REPO_ROOT / ".work/fp_context/speaker_report.json"),
        help="verify_speakers_ecapa output carrying cosine_floor/margin_threshold",
    )
    parser.add_argument(
        "--rights-manifest",
        default=str(rights_manifest_path()),
        help=(
            "Rights register manifest used to verify video rights status "
            f"(default: the pinned {RIGHTS_MANIFEST_RELPATH})"
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="Run without upserting into Qdrant (default: True)",
    )
    parser.add_argument(
        "--no-dry-run",
        dest="dry_run",
        action="store_false",
        help="Actually execute writes to Qdrant",
    )
    parser.add_argument(
        "--allow-live-target",
        action="store_true",
        default=False,
        help="Allow writing to a collection currently configured for live serving",
    )
    args = parser.parse_args()

    if not args.wav_dir:
        parser.error("--wav-dir is required (or set WAV_DIR)")
    if not args.attr_root:
        parser.error("--attr-root is required (or set ATTR_ROOT)")
    if args.qdrant_url and not os.environ.get("QDRANT_URL"):
        os.environ["QDRANT_URL"] = args.qdrant_url

    wav_dir = Path(args.wav_dir)
    transcripts_dir = Path(args.transcripts_dir)
    cache_dir = Path(args.cache_dir)
    attr_root = Path(args.attr_root)

    # Transcripts_B paths
    tb_dirs = [
        attr_root / "pilot50_2026-09-25/transcripts_B",
        attr_root / "mass_ingest_2026-10/transcripts_B",
        attr_root / "bakeoff_2026-09-25/transcripts_B",
    ]

    # Inventory
    inv_file = attr_root / "full_corpus_inventory/inventory.json"
    inv_rows = {}
    if inv_file.is_file():
        try:
            inv_rows = {r["video_id"]: r for r in json.loads(inv_file.read_text()).get("rows", [])}
        except Exception:
            pass

    # Calibration first: without measured floors nothing can be verified.
    cosine_floor, margin_threshold = load_calibration(Path(args.calibration))
    logger.info(
        "Speaker floors: cosine_floor=%.4f margin_threshold=%.4f", cosine_floor, margin_threshold
    )

    # Load rights manifest (D18)
    rights_path = Path(args.rights_manifest)
    cleared_videos: set[str] = set()
    if rights_path.is_file():
        try:
            rm_data = json.loads(rights_path.read_text(encoding="utf-8"))
            for asset in rm_data.get("assets", []):
                if str(asset.get("rights_status", "")).startswith("confirmed"):
                    cleared_videos.add(str(asset.get("video_id")))
            logger.info("Loaded rights manifest: %d cleared video IDs", len(cleared_videos))
        except Exception as exc:
            logger.error("Failed to load rights manifest %s: %s", rights_path, exc)
            return 1
    else:
        logger.error("Rights manifest %s not found", rights_path)
        return 1

    # Safety check on target collection (D5). The protected live collection comes
    # from backend settings, not a shell-only variable, so the guard checks the
    # collection the app would actually serve.
    from app.config import settings

    live_coll = str(
        getattr(settings, "first_person_context_collection", "")
        or getattr(settings, "first_person_collection", "")
        or ""
    ).strip()
    protected_targets = {"first_person", "first_person_v10"}
    if live_coll:
        protected_targets.add(live_coll)
    if (
        not args.dry_run
        and not args.allow_live_target
        and args.target_collection in protected_targets
    ):
        logger.error(
            "Target collection '%s' is a live or protected serving collection. "
            "Refusing write. Use a versioned collection (e.g. first_person_v11) or pass --allow-live-target.",
            args.target_collection,
        )
        return 1

    # Shared facade: honours QDRANT_URL / QDRANT_LOCAL_PATH.
    qdrant = QdrantService(collection=args.target_collection)
    try:
        qdrant.collection_info(args.target_collection)
    except Exception as exc:
        logger.error("Target collection %s is not readable: %s", args.target_collection, exc)
        return 1

    # Ensure collection exists and get existing videos
    existing_videos: set[str] = set()
    try:
        offset = None
        while True:
            page, offset = qdrant.scroll_page(
                collection=args.target_collection, offset=offset, limit=1000, with_payload=True
            )
            for p in page:
                vid = p.payload.get("video_id") if p.payload else None
                if vid:
                    existing_videos.add(str(vid))
            if offset is None:
                break
    except Exception as exc:
        logger.error("Failed to read target collection %s: %s", args.target_collection, exc)
        return 1

    logger.info(
        "Collection %s has %d unique videos already indexed.",
        args.target_collection,
        len(existing_videos),
    )

    all_transcripts = sorted(list(transcripts_dir.glob("*.md")))
    all_wavs = {p.stem for p in wav_dir.glob("*.wav")} if wav_dir.is_dir() else set()

    missing_candidates = [
        p for p in all_transcripts if p.stem not in existing_videos and p.stem in all_wavs
    ]
    logger.info("Found %d missing candidate videos with WAV audio.", len(missing_candidates))

    only = {v.strip() for v in str(args.only_videos or "").split(",") if v.strip()}
    if only:
        unknown = only - {p.stem for p in missing_candidates}
        if unknown:
            logger.warning(
                "--only-videos ids that are not buildable additions (already indexed, no "
                "transcript, or no WAV): %s",
                sorted(unknown),
            )
        missing_candidates = [p for p in missing_candidates if p.stem in only]
        logger.info("Restricted to --only-videos: %d video(s).", len(missing_candidates))

    if args.limit > 0:
        missing_candidates = missing_candidates[: args.limit]
        logger.info("Applying limit: processing %d videos.", len(missing_candidates))

    if not missing_candidates:
        logger.info("No missing candidate videos to process.")
        return 0

    # Load ECAPA centroids and embedder
    logger.info("Computing ECAPA teacher voice centroids...")
    if args.references_npz:
        with np.load(Path(args.references_npz)) as refs:
            centroids = {str(k).lower(): np.asarray(refs[k], dtype=np.float32) for k in refs.files}
    else:
        centroids = compute_centroids(
            Path(args.centroid_points), cache_dir, allow_label_derived=args.allow_label_centroids
        )
    logger.info("Centroids ready for: %s", list(centroids.keys()))

    logger.info("Loading ECAPA speaker recognition model...")
    embedder = speaker_verify._load_embedder(cache_dir)

    logger.info("Initializing BGE-M3 embedding service...")
    embed_svc = EmbeddingService()
    emb_model, emb_revision = _embedding_provenance()
    logger.info("Embedding provenance: model=%s revision=%s", emb_model, emb_revision)

    processed_videos = 0
    total_spans_created = 0
    total_parents_created = 0
    quarantined: Counter[str] = Counter()
    # D9: release-grade contract checked on every built span, reported per reason
    # code. Reported, not enforced: dropping spans here would hide a data-quality
    # defect from the scorecard instead of measuring it.
    release_grade_defects: Counter[str] = Counter()

    for p in missing_candidates:
        video_id = p.stem
        wav_path = wav_dir / f"{video_id}.wav"

        # 1. Transcript + rights clearance (cheap, before any acoustic work)
        inv_row = inv_rows.get(video_id, {})
        channel, speaker_meta, transcript_hash, words, artifact_sha256 = parse_transcript(p)
        channel_name = str(inv_row.get("channel") or channel or "").lower().strip()
        rights_cleared = (
            channel_name in CLEARED_CHANNELS
            or video_id in CLEARED_VIDEO_IDS
            or "preethaji" in channel_name
            or "krishnaji" in channel_name
            or "ekam" in channel_name
        )
        if not rights_cleared:
            quarantined["rights_not_cleared"] += 1
            logger.info(
                "Video %s: rights not cleared (channel=%s) -> skipped", video_id, channel_name
            )
            continue

        if not words:
            quarantined["empty_transcript"] += 1
            continue

        # 2. Word timings & sentence slicing
        timings = get_word_timings(video_id, words, tb_dirs)
        if timings is None and args.text_from_words:
            from_words = words_from_timed_file(video_id, tb_dirs)
            if from_words is not None:
                words, timings, artifact_sha256 = from_words
                transcript_hash = hashlib.sha256(" ".join(words).encode("utf-8")).hexdigest()
                logger.warning(
                    "Video %s: markdown transcript unusable for alignment; text and times "
                    "taken from the timed word file (--text-from-words)",
                    video_id,
                )
        if timings is None:
            quarantined["no_word_timings"] += 1
            logger.info("Video %s: no reliable word timings -> skipped", video_id)
            continue

        if video_id not in cleared_videos:
            quarantined["rights_unconfirmed"] += 1
            logger.warning(
                "Video %s is not in the confirmed rights register -> quarantined", video_id
            )
            continue
        span_specs = slice_into_sentence_spans(words, timings)
        # D2: the cleaner's deletion rules (trailing severed clause, retreat-date
        # announcement, embedded audience acknowledgement) are quarantine reasons,
        # never edits: deleting the words would desynchronise text and audio window.
        kept_specs: list[dict[str, Any]] = []
        for spec in span_specs:
            flags = asr_cleaner_flags(spec["text"])
            if flags:
                for flag in flags:
                    quarantined[f"asr_cleaner_{flag}"] += 1
                continue
            kept_specs.append(spec)
        span_specs = drop_zero_duration_specs(kept_specs, quarantined)
        if not span_specs:
            quarantined["no_valid_spans"] += 1
            logger.info("Video %s: no valid sentence spans after boundary check", video_id)
            continue

        # 3. Per-span acoustic verification from the span's own audio window
        verdicts: list[dict[str, Any]] = []
        for spec in span_specs:
            predicted, cleared, cosine, margin, metrics = verify_span_speaker(
                wav_path,
                spec["start_ms"],
                spec["end_ms"],
                embedder,
                centroids,
                cosine_floor=cosine_floor,
                margin_threshold=margin_threshold,
            )
            verdicts.append(
                {
                    "predicted": predicted,
                    "cleared": cleared,
                    "cosine": cosine,
                    "margin": margin,
                    "metrics": metrics,
                }
            )

        expected_guru = _expected_guru(speaker_meta, channel_name)
        cleared_gurus = Counter(
            v["predicted"] for v in verdicts if v["cleared"] and v["predicted"] in GURU_IDS
        )
        if not cleared_gurus:
            quarantined["speaker_unverified"] += 1
            logger.info("Video %s: no span cleared the speaker floors -> skipped", video_id)
            continue
        predicted_guru = cleared_gurus.most_common(1)[0][0]
        if expected_guru is not None and expected_guru != predicted_guru:
            quarantined["speaker_metadata_mismatch"] += 1
            logger.info(
                "Video %s: voice says %s but metadata says %s -> skipped",
                video_id,
                predicted_guru,
                expected_guru,
            )
            continue

        parent_unit_id = make_parent_unit_id(
            guru_id=predicted_guru,
            video_id=video_id,
            corpus_version=args.corpus_version,
            first_word_index=span_specs[0]["word_start"],
            last_word_index=span_specs[-1]["word_end"],
        )

        span_ids = [
            make_source_span_id(
                guru_id=predicted_guru,
                video_id=video_id,
                corpus_version=args.corpus_version,
                word_start=s["word_start"],
                word_end=s["word_end"],
                transcript_hash=transcript_hash,
            )
            for s in span_specs
        ]

        asr_engine, asr_model_version = asr_provenance(video_id, tb_dirs)
        spans: list[SourceSpan] = []
        vectors: dict[str, Any] = {}
        source_url = f"https://www.youtube.com/watch?v={video_id}"

        for idx, spec in enumerate(span_specs):
            verdict = verdicts[idx]
            # Verified only when the span's own voice prediction matches the
            # video's guru AND both calibrated floors cleared.
            verified = bool(verdict["cleared"] and verdict["predicted"] == predicted_guru)
            # The vector is produced from the instruction-prefixed passage text
            # embedded by encode_batch below, so this hash names exactly the
            # string actually embedded, bypassing query expansion.
            embedded_input = f"{getattr(embed_svc, 'instruction', '')}{spec['text']}"
            # D9: labels are derived from the detector, never constants. A span with a
            # boundary defect is UNCERTAIN (related at best, never direct) and a
            # FRAGMENT; only a defect-free span is VERIFIED / COMPLETE.
            has_boundary_defect = bool(boundary_defects(spec["text"].split()))
            span = SourceSpan(
                corpus_version=args.corpus_version,
                guru_id=predicted_guru,
                video_id=video_id,
                source_asset_id=video_id,
                source_span_id=span_ids[idx],
                parent_unit_id=parent_unit_id,
                turn_id=f"{parent_unit_id[:12]}:t{idx}",
                turn_index=idx,
                source_span_index=idx,
                start_ms=spec["start_ms"],
                end_ms=spec["end_ms"],
                word_start=spec["word_start"],
                word_end=spec["word_end"],
                speaker_id=predicted_guru,
                speaker_role=SpeakerRole.GURU,
                speaker_verified=verified,
                voice_verification_method=("ecapa_voxceleb_span_slice_v2" if verified else None),
                asr_engine=asr_engine,
                asr_model_version=asr_model_version,
                source_transcript_text=spec["text"],
                verbatim_text=spec["text"],
                transcript_hash=transcript_hash,
                source_text_hash=clip_text_hash(spec["text"]),
                boundary_status=(
                    BoundaryStatus.UNCERTAIN if has_boundary_defect else BoundaryStatus.VERIFIED
                ),
                completeness_status=(
                    CompletenessStatus.FRAGMENT
                    if has_boundary_defect
                    else CompletenessStatus.COMPLETE
                ),
                rights_cleared=True,
                caption_status="auto",
                provenance_kind=ProvenanceKind.SPEECH_TURN_SPAN,
                previous_span_id=span_ids[idx - 1] if idx > 0 else None,
                next_span_id=span_ids[idx + 1] if idx < len(span_specs) - 1 else None,
                answer_role=AnswerRole.DIRECT,
                source_url=source_url,
                quality_status="verified_verbatim",
                window_count=verdict["metrics"]["window_count"],
                min_window_cosine=verdict["metrics"]["min_window_cosine"],
                foreign_window_count=verdict["metrics"]["foreign_window_count"],
                embedding_model=emb_model,
                embedding_revision=emb_revision,
                embedded_text_sha256=clip_text_hash(embedded_input),
                # This text comes from the voted ASR transcript this run parsed,
                # so the origin is known here (unlike the v9 carry-over builder).
                text_origin=TextOrigin.ASR_VOTED,
                source_artifact_sha256=artifact_sha256,
            )
            spans.append(span)

            # 4. Dense + sparse embedding via encode_batch (bypasses query expansion)
            res = embed_svc.encode_batch([spec["text"]])
            vectors[span.source_span_id] = {
                "passage_dense": res["dense"][0],
                "passage_sparse": QdrantUtils.sparse_dict_to_vector(res["sparse"][0]),
            }

        parent = ParentUnit(
            corpus_version=args.corpus_version,
            guru_id=predicted_guru,
            video_id=video_id,
            parent_unit_id=parent_unit_id,
            ordered_source_span_ids=tuple(s.source_span_id for s in spans),
            start_ms=spans[0].start_ms,
            end_ms=spans[-1].end_ms,
            parent_text_hash=clip_text_hash(" ".join(s.verbatim_text for s in spans)),
            speaker_ids=(predicted_guru,),
            speaker_continuity=True,
            # The parent is only as verified as its children.
            boundary_status=(
                BoundaryStatus.UNCERTAIN
                if any(x.boundary_status is BoundaryStatus.UNCERTAIN for x in spans)
                else BoundaryStatus.VERIFIED
            ),
            completeness_status=(
                CompletenessStatus.FRAGMENT
                if any(x.completeness_status is CompletenessStatus.FRAGMENT for x in spans)
                else CompletenessStatus.COMPLETE
            ),
        )

        # 5. Upsert points into Qdrant. A label that contradicts its own evidence blocks
        # the whole video (D9): the labels above are derived, so this should never fire,
        # and if it does a code change reintroduced a constant. The duration band is
        # counted but not blocking: re-segmentation is a separate step (D7).
        blocking = []
        for span in spans:
            for defect in span.validate_release_grade():
                code = defect.split(":", 1)[0]
                release_grade_defects[code] += 1
                if code in RELEASE_GRADE_BLOCKING:
                    blocking.append(code)
        if blocking:
            quarantined["release_grade_blocked"] += 1
            logger.error(
                "Video %s: release-grade labels contradict evidence: %s", video_id, blocking
            )
            continue
        points_to_upsert = [
            PointStruct(
                id=point_id_for_record(s.source_span_id),
                vector=vectors[s.source_span_id],
                payload=s.to_payload(),
            )
            for s in spans
        ]
        points_to_upsert.append(
            PointStruct(
                id=parent_point_id(parent.parent_unit_id),
                vector={},
                payload=parent.to_payload(),
            )
        )

        if args.dry_run:
            logger.info(
                "[DRY-RUN] Video %s: would upsert %d spans and 1 parent into %s",
                video_id,
                len(spans),
                args.target_collection,
            )
            processed_videos += 1
            total_spans_created += len(spans)
            total_parents_created += 1
            continue

        try:
            qdrant.upsert_points(points_to_upsert, collection=args.target_collection, wait=True)
        except Exception as exc:
            # A raised upsert leaves this video's state unknown: the write may
            # have partially applied before the error or timeout. Quarantine the
            # video and delete the IDs we attempted, because reruns treat any
            # video_id already present in the collection as indexed and would
            # otherwise keep a partial clip set.
            quarantined["upsert_failed"] += 1
            logger.error("Video %s: upsert failed: %s -> quarantined", video_id, exc)
            try:
                qdrant.delete_points_by_ids(
                    [point.id for point in points_to_upsert],
                    collection=args.target_collection,
                )
            except Exception as cleanup_exc:
                logger.error(
                    "Video %s: cleanup after failed upsert also failed: %s "
                    "(a rerun may treat it as already indexed)",
                    video_id,
                    cleanup_exc,
                )
            continue

        verified_spans = sum(1 for s in spans if s.speaker_verified)
        if verified_spans == 0:
            logger.warning("Video %s: no span was speaker-verified after gating", video_id)
        processed_videos += 1
        total_spans_created += len(spans)
        total_parents_created += 1

        if processed_videos % 10 == 0:
            logger.info(
                "Progress: %d videos processed, %d spans, %d parents",
                processed_videos,
                total_spans_created,
                total_parents_created,
            )

    logger.info(
        "Batch ingestion finished: %d videos processed, %d spans, %d parents.",
        processed_videos,
        total_spans_created,
        total_parents_created,
    )
    logger.info("Quarantine summary: %s", dict(quarantined))
    logger.info("Release-grade defects by reason: %s", dict(release_grade_defects))

    if args.dry_run:
        logger.info(
            "[DRY-RUN] Finished run across %d videos. No writes performed to %s",
            processed_videos,
            args.target_collection,
        )
        return 0

    # 6. Snapshot
    try:
        snapshot = qdrant.create_snapshot(collection=args.target_collection)
        logger.info("Created Qdrant snapshot: %s", getattr(snapshot, "name", snapshot))
    except Exception as exc:
        logger.warning("Snapshot creation: %s", exc)

    info = qdrant.collection_info(args.target_collection)
    logger.info(
        "Collection %s census: %d points, status: %s",
        args.target_collection,
        getattr(info, "points_count", 0),
        getattr(info, "status", "unknown"),
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
