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
    clip_text_hash,
    make_parent_unit_id,
    make_source_span_id,
)
from ingest.verbatim.boundaries import boundary_defects  # noqa: E402

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
    cosine_floor = data.get("cosine_floor")
    margin_threshold = data.get("threshold", data.get("margin_threshold"))
    for name, value in (("cosine_floor", cosine_floor), ("margin_threshold", margin_threshold)):
        if not isinstance(value, (int, float)) or not math.isfinite(float(value)):
            raise RuntimeError(f"Speaker calibration {path} has no usable {name}: {value!r}")
    return float(cosine_floor), float(margin_threshold)


def compute_centroids(points_file: Path, cache_dir: Path) -> dict[str, np.ndarray]:
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
) -> tuple[str | None, bool, float, float]:
    """Embed ONE span's own audio slice and score it against the centroids.

    Returns ``(predicted_guru, cleared_floors, cosine, margin)``. The caller is
    responsible for the guru-match check before marking anything verified.
    """
    audio = speaker_verify._slice(wav_path, start_ms, end_ms)
    if audio is None:
        return None, False, 0.0, 0.0

    with torch.no_grad():
        emb = embedder.encode_batch(torch.from_numpy(audio).unsqueeze(0))
    vector = emb.squeeze().detach().cpu().numpy().astype(np.float32)
    norm = float(np.linalg.norm(vector))
    if norm <= 0:
        return None, False, 0.0, 0.0
    vector /= norm

    scores = {guru: float(np.dot(vector, c)) for guru, c in centroids.items()}
    if not scores:
        return None, False, 0.0, 0.0
    ordered = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    predicted, best = ordered[0]
    runner_up = ordered[1][1] if len(ordered) > 1 else 0.0
    margin = best - runner_up
    cleared = best >= cosine_floor and margin >= margin_threshold
    return predicted, cleared, best, margin


def parse_transcript(md_path: Path) -> tuple[str, str, str, list[str]]:
    raw = md_path.read_text(encoding="utf-8", errors="replace")
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

    if not transcript_hash:
        transcript_hash = hashlib.sha256(body.encode("utf-8")).hexdigest()

    words = re.findall(r"\S+", re.sub(r"\s+", " ", body).strip())
    return channel, speaker, transcript_hash, words


def _align_words_to_timings(
    words: list[str], timed_words: list[dict[str, Any]]
) -> list[tuple[float, float]] | None:
    """Map every transcript word onto a timed ASR word, or return None.

    Uses SequenceMatcher opcodes: equal blocks map one-to-one, and a replace
    block is only spread across that block's own entries (never across the whole
    file). A word with no aligned entry makes the whole alignment unusable --
    a guessed offset would put the citation on the wrong audio.
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
            block = timed_words[j1:j2]
            span = i2 - i1
            if not block or span <= 0:
                continue
            for offset in range(span):
                # Block-local proportional mapping only: drift stays inside the
                # mismatched run instead of scaling with the file length.
                entry = block[min(len(block) - 1, offset * len(block) // span)]
                out[i1 + offset] = (float(entry.get("start", 0)), float(entry.get("end", 0)))
        # "delete"/"insert" leave a transcript word with no aligned ASR entry.
    if any(item is None for item in out):
        return None
    return out


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


def slice_into_sentence_spans(
    words: list[str], timings: list[tuple[float, float]], min_words: int = 20, max_words: int = 70
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

    # Filter out sentences with boundary defects
    clean_sentences = []
    for s_start, s_end, s_text, sms, ems in sentences:
        defects = boundary_defects(s_text.split())
        if not defects:
            clean_sentences.append((s_start, s_end, s_text, sms, ems))

    if not clean_sentences:
        return []

    # Group CONTIGUOUS clean sentences into child spans. A sentence removed by
    # the boundary filter leaves a word-index gap; joining across it would
    # serve a span whose text is not the audio between start_ms and end_ms.
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
        if group_sentences and item[0] != group_sentences[-1][1]:
            _flush_group()
        group_sentences.append(item)
        group_words += item[1] - item[0]
        if group_words >= min_words:
            _flush_group()

    # Residual tail: merge into the previous span only when it is genuinely
    # contiguous with it, otherwise it becomes its own span.
    if group_sentences:
        contiguous = bool(spans) and group_sentences[0][0] == spans[-1]["word_end"]
        if contiguous and group_words < 15:
            spans[-1]["word_end"] = group_sentences[-1][1]
            spans[-1]["end_ms"] = group_sentences[-1][4]
            spans[-1]["text"] = f"{spans[-1]['text']} {' '.join(s[2] for s in group_sentences)}"
            group_sentences = []
            group_words = 0
        else:
            _flush_group()

    return spans


def _expected_guru(speaker_meta: str, channel_name: str) -> str | None:
    """Guru named by the transcript/channel metadata, when unambiguous."""
    blob = f"{speaker_meta} {channel_name}".lower()
    named = [guru for guru in GURU_IDS if guru in blob]
    return named[0] if len(named) == 1 else None


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
        "--centroid-points",
        default=str(_REPO_ROOT / ".work/fp_context/v9_points.json"),
        help="Qdrant export used to build the guru voice centroids",
    )
    parser.add_argument(
        "--calibration",
        default=str(_REPO_ROOT / ".work/fp_context/speaker_report.json"),
        help="verify_speakers_ecapa output carrying cosine_floor/margin_threshold",
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

    if args.limit > 0:
        missing_candidates = missing_candidates[: args.limit]
        logger.info("Applying limit: processing %d videos.", len(missing_candidates))

    if not missing_candidates:
        logger.info("No missing candidate videos to process.")
        return 0

    # Load ECAPA centroids and embedder
    logger.info("Computing ECAPA teacher voice centroids...")
    centroids = compute_centroids(Path(args.centroid_points), cache_dir)
    logger.info("Centroids ready for: %s", list(centroids.keys()))

    logger.info("Loading ECAPA speaker recognition model...")
    embedder = speaker_verify._load_embedder(cache_dir)

    logger.info("Initializing BGE-M3 embedding service...")
    embed_svc = EmbeddingService()

    processed_videos = 0
    total_spans_created = 0
    total_parents_created = 0
    quarantined: Counter[str] = Counter()

    for p in missing_candidates:
        video_id = p.stem
        wav_path = wav_dir / f"{video_id}.wav"

        # 1. Transcript + rights clearance (cheap, before any acoustic work)
        inv_row = inv_rows.get(video_id, {})
        channel, speaker_meta, transcript_hash, words = parse_transcript(p)
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
        if timings is None:
            quarantined["no_word_timings"] += 1
            logger.info("Video %s: no reliable word timings -> skipped", video_id)
            continue
        span_specs = slice_into_sentence_spans(words, timings)
        if not span_specs:
            quarantined["no_valid_spans"] += 1
            logger.info("Video %s: no valid sentence spans after boundary check", video_id)
            continue

        # 3. Per-span acoustic verification from the span's own audio window
        verdicts: list[dict[str, Any]] = []
        for spec in span_specs:
            predicted, cleared, cosine, margin = verify_span_speaker(
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

        spans: list[SourceSpan] = []
        vectors: dict[str, Any] = {}
        source_url = f"https://www.youtube.com/watch?v={video_id}"

        for idx, spec in enumerate(span_specs):
            verdict = verdicts[idx]
            # Verified only when the span's own voice prediction matches the
            # video's guru AND both calibrated floors cleared.
            verified = bool(verdict["cleared"] and verdict["predicted"] == predicted_guru)
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
                source_transcript_text=spec["text"],
                verbatim_text=spec["text"],
                transcript_hash=transcript_hash,
                source_text_hash=clip_text_hash(spec["text"]),
                boundary_status=BoundaryStatus.VERIFIED,
                completeness_status=CompletenessStatus.COMPLETE,
                rights_cleared=True,
                caption_status="auto",
                provenance_kind=ProvenanceKind.SPEECH_TURN_SPAN,
                previous_span_id=span_ids[idx - 1] if idx > 0 else None,
                next_span_id=span_ids[idx + 1] if idx < len(span_specs) - 1 else None,
                answer_role=AnswerRole.DIRECT,
                source_url=source_url,
                quality_status="verified_verbatim",
            )
            spans.append(span)

            # 4. Dense + sparse embedding
            res = embed_svc.encode_single_full(spec["text"])
            vectors[span.source_span_id] = {
                "passage_dense": res["dense"],
                "passage_sparse": QdrantUtils.sparse_dict_to_vector(res["sparse"]),
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
            boundary_status=BoundaryStatus.VERIFIED,
            completeness_status=CompletenessStatus.COMPLETE,
        )

        # 5. Upsert points into Qdrant
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
