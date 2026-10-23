#!/usr/bin/env python3
"""Strict, read-only audit of a live fp-context-v1 collection.

``audit_first_person_readiness.py`` checks field presence. This script checks
*truth*: every payload is validated against the strict pydantic contract in
``domain.first_person_context`` (so deterministic identifiers, clip hashes and
``extra="forbid"`` are enforced), the parent/child topology is verified, and the
audio windows are re-derived from the immutable ASR word-timing artifacts on
disk instead of trusting the payload.

It never creates, updates, deletes or aliases a Qdrant collection and never
writes to the collection it audits. Only the JSON report is written.

Usage:
    python -m scripts.ops.audit_first_person_v10_strict \\
        --collection first_person_v10 \\
        --attr-root /Users/harshodaikolluru/mukthiguru_attribution_data \\
        --output audits/evidence/<name>.json
"""
from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import os
import sys
import urllib.error
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

_BACKEND = Path(__file__).resolve().parents[2]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from domain.first_person_context import ParentUnit, SourceSpan  # noqa: E402
from scripts.ops.build_fp_context_from_v9 import _best_window, _norm_words  # noqa: E402

ASR_ROOTS = (
    "mass_ingest_2026-10",
    "pilot50_2026-09-25",
    "audio_2026-09/pilot20_run",
)
# Run identity is derived from the artifact directory that produced the file.
# It is a naming convention of the archive, not a value read out of the audio.
RUN_IDS = {
    "mass_ingest_2026-10": "mass_ingest_2026-10@2026-10-04T01:52:19+05:30",
    "pilot50_2026-09-25": "pilot50_2026-09-25",
    "audio_2026-09/pilot20_run": "pilot20_2026-09",
}


def _request(base_url: str, path: str, method: str = "GET", body: Any = None) -> dict[str, Any]:
    data = None if body is None else json.dumps(body).encode("utf-8")
    request = urllib.request.Request(
        base_url.rstrip("/") + path,
        data=data,
        headers={"Content-Type": "application/json"},
        method=method,
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        payload = json.load(response)
    if not isinstance(payload, dict):
        raise ValueError(f"Qdrant returned a non-object response for {path}")
    return payload


def _scroll_all(base_url: str, collection: str) -> list[dict[str, Any]]:
    points: list[dict[str, Any]] = []
    offset: Any = None
    while True:
        body: dict[str, Any] = {"limit": 256, "with_payload": True, "with_vector": False}
        if offset is not None:
            body["offset"] = offset
        result = _request(base_url, f"/collections/{collection}/points/scroll", "POST", body)["result"]
        points.extend(p for p in result.get("points", []) if isinstance(p, dict))
        offset = result.get("next_page_offset")
        if offset is None:
            return points


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _discover_asr(attr_root: Path) -> dict[str, dict[str, Any]]:
    """Index every archived word-timed transcript by video id."""
    found: dict[str, dict[str, Any]] = {}
    for root_name in ASR_ROOTS:
        root = attr_root / root_name
        transcripts = root / "transcripts_B"
        if not transcripts.is_dir():
            continue
        for transcript in sorted(transcripts.glob("*.json")):
            video_id = transcript.stem
            if video_id in found:
                continue
            raw = root / "raw" / f"{video_id}_parakeet.json"
            align = root / "raw" / f"{video_id}_align.json"
            if not raw.is_file():
                continue
            try:
                raw_data = json.loads(raw.read_text(encoding="utf-8"))
                timed = json.loads(transcript.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if raw_data.get("ok") is False or not isinstance(timed, list) or not timed:
                continue
            align_ok = None
            if align.is_file():
                try:
                    align_ok = json.loads(align.read_text(encoding="utf-8")).get("ok") is True
                except (OSError, ValueError):
                    align_ok = False
            found[video_id] = {
                "video_id": video_id,
                "asr_engine": "parakeet_mlx",
                "asr_model_version": raw_data.get("model"),
                "transcription_run_id": RUN_IDS[root_name],
                "root": root_name,
                "transcript_path": str(transcript),
                "transcript_sha256": _sha256(transcript),
                "raw_asr_path": str(raw),
                "raw_asr_sha256": _sha256(raw),
                "alignment_path": str(align) if align.is_file() else None,
                "alignment_sha256": _sha256(align) if align.is_file() else None,
                "alignment_ok": align_ok,
                "timed_words": timed,
            }
    return found


def _timed_word_window(timed: list[dict[str, Any]], word_start: int, word_end: int) -> dict[str, Any]:
    """Return the measured audio window of the timed words in ``[word_start, word_end)``."""
    if word_start < 0 or word_end > len(timed) or word_end <= word_start:
        return {"ok": False, "reason": "word_index_out_of_range"}
    window = timed[word_start:word_end]
    starts = [float(w.get("start", 0.0)) for w in window]
    ends = [float(w.get("end", 0.0)) for w in window]
    return {
        "ok": True,
        "start_ms": int(round(min(starts) * 1000)),
        "end_ms": int(round(max(ends) * 1000)),
        "words": [str(w.get("w", "")) for w in window],
    }


def _flat_timed_tokens(timed: list[dict[str, Any]]) -> tuple[list[str], list[int]]:
    """Flatten timed words into the builder's normalized token index space.

    Returns ``(tokens, timed_index)`` where ``tokens[i]`` is the i-th
    normalized token and ``timed_index[i]`` is the timed word it came from.
    The builder (``build_fp_context_from_v9._word_source``) uses the same
    flattening, so this reproduces its coordinate system exactly.
    """
    tokens: list[str] = []
    timed_index: list[int] = []
    for position, word in enumerate(timed):
        text = str(word.get("w", ""))
        for token in _norm_words(text):
            if token:
                tokens.append(token)
                timed_index.append(position)
    return tokens, timed_index


def _measured_window(
    tokens: list[str], timed_index: list[int], timed: list[dict[str, Any]], clip_text: str
) -> dict[str, Any]:
    """Locate ``clip_text`` inside the timed tokens and measure its audio window."""
    clip_tokens = _norm_words(clip_text)
    if not clip_tokens:
        return {"ok": False, "reason": "empty_clip"}
    start, ratio = _best_window(clip_tokens, tokens)
    if start < 0 or ratio < 0.90:
        return {"ok": False, "reason": "clip_not_locatable", "ratio": round(ratio, 4)}
    matched = timed_index[start : start + len(clip_tokens)]
    if not matched:
        return {"ok": False, "reason": "empty_match"}
    window = [timed[i] for i in matched]
    starts = [float(w.get("start", 0.0)) for w in window]
    ends = [float(w.get("end", 0.0)) for w in window]
    return {
        "ok": True,
        "ratio": round(ratio, 4),
        "start_ms": int(round(min(starts) * 1000)),
        "end_ms": int(round(max(ends) * 1000)),
    }


def _contains_subsequence(haystack: list[str], needle: list[str]) -> bool:
    """True when ``needle`` appears as a contiguous run inside ``haystack``."""
    if not needle or len(needle) > len(haystack):
        return False
    first = needle[0]
    for index in range(len(haystack) - len(needle) + 1):
        if haystack[index] == first and haystack[index : index + len(needle)] == needle:
            return True
    return False


def _window_tokens_covering(
    timed: list[dict[str, Any]], start_ms: int, end_ms: int, tolerance_ms: int
) -> list[str]:
    """Normalized tokens of every timed word whose audio falls in the cited window."""
    tokens: list[str] = []
    for word in timed:
        start = int(round(float(word.get("start", 0.0)) * 1000))
        end = int(round(float(word.get("end", 0.0)) * 1000))
        if end < start_ms - tolerance_ms or start > end_ms + tolerance_ms:
            continue
        tokens.extend(_norm_words(str(word.get("w", ""))))
    return tokens


def _token_coverage(clip_tokens: list[str], cited_tokens: list[str]) -> float:
    """Fraction of clip tokens that are actually spoken inside the cited window.

    A single ASR wording difference ("yourself but also" vs "yourself also")
    must not fail the check, but a cited window that points at a different
    passage must. Matching blocks give an order-preserving count of the clip
    tokens that were spoken inside the window.
    """
    if not clip_tokens or not cited_tokens:
        return 0.0
    matcher = difflib.SequenceMatcher(None, cited_tokens, clip_tokens, autojunk=False)
    matched = sum(block.size for block in matcher.get_matching_blocks())
    return matched / float(len(clip_tokens))


def audit(
    *,
    base_url: str,
    collection: str,
    alias: str,
    attr_root: Path,
    speaker_verdicts: Path | None,
    tolerance_ms: int,
    coverage_floor: float = 0.90,
) -> dict[str, Any]:
    aliases = _request(base_url, "/aliases").get("result", {}).get("aliases", [])
    alias_target = next(
        (a.get("collection_name") for a in aliases if a.get("alias_name") == alias),
        None,
    )
    _request(base_url, f"/collections/{collection}")["result"]  # collection must exist
    points = _scroll_all(base_url, collection)

    asr_artifacts_available = attr_root.is_dir()
    asr = _discover_asr(attr_root) if asr_artifacts_available else {}
    tokens_by_video: dict[str, tuple[list[str], list[int]]] = {}
    for video_id, evidence in asr.items():
        tokens_by_video[video_id] = _flat_timed_tokens(evidence["timed_words"])
    verdicts: dict[str, Any] = {}
    if speaker_verdicts and speaker_verdicts.is_file():
        verdicts = json.loads(speaker_verdicts.read_text(encoding="utf-8"))
    verdict_items = verdicts.get("items", {}) if isinstance(verdicts, dict) else {}

    children: list[dict[str, Any]] = []
    parents: list[dict[str, Any]] = []
    contract_errors: Counter[str] = Counter()
    contract_samples: dict[str, list[str]] = defaultdict(list)
    for point in points:
        payload = dict(point.get("payload") or {})
        record_type = str(payload.get("record_type") or "")
        if record_type == "parent_unit":
            parents.append(payload)
        else:
            children.append(payload)

    def _fail(code: str, detail: str) -> None:
        contract_errors[code] += 1
        if len(contract_samples[code]) < 3:
            contract_samples[code].append(detail)

    validated_children: dict[str, SourceSpan] = {}
    for payload in children:
        record = {k: v for k, v in payload.items() if k != "record_type"}
        try:
            span = SourceSpan.model_validate(record)
        except Exception as exc:  # pydantic ValidationError
            _fail("child_contract_invalid", f"{payload.get('source_span_id')}: {exc}"[:400])
            continue
        validated_children[span.source_span_id] = span

    validated_parents: dict[str, ParentUnit] = {}
    for payload in parents:
        record = {k: v for k, v in payload.items() if k != "record_type"}
        try:
            parent = ParentUnit.model_validate(record)
        except Exception as exc:
            _fail("parent_contract_invalid", f"{payload.get('parent_unit_id')}: {exc}"[:400])
            continue
        validated_parents[parent.parent_unit_id] = parent

    # --- topology -----------------------------------------------------------
    orphan_children = 0
    wrong_guru = 0
    wrong_video = 0
    wrong_corpus = 0
    parents_without_children = 0
    children_not_in_parent_order = 0
    for span in validated_children.values():
        parent = validated_parents.get(span.parent_unit_id)
        if parent is None:
            orphan_children += 1
            continue
        if span.source_span_id not in set(parent.ordered_source_span_ids):
            children_not_in_parent_order += 1
        if span.guru_id != parent.guru_id:
            wrong_guru += 1
        if span.video_id != parent.video_id:
            wrong_video += 1
        if span.corpus_version != parent.corpus_version:
            wrong_corpus += 1
    for parent in validated_parents.values():
        if not any(s.parent_unit_id == parent.parent_unit_id for s in validated_children.values()):
            parents_without_children += 1

    # --- ASR / audio-window truth ------------------------------------------
    asr_missing = 0
    asr_engine_mismatch = 0
    asr_model_mismatch = 0
    alignment_hash_mismatch = 0
    alignment_not_ok = 0
    verdict_covered = 0
    verdict_uncovered = 0
    verified_without_verdict = 0
    citation_window_checked = 0
    citation_window_exact = 0
    citation_window_mismatch = 0
    citation_window_unverifiable = 0
    coverage_samples: list[float] = []
    word_index_consistent = 0
    word_index_inconsistent = 0
    word_index_out_of_range = 0
    drift_samples: list[int] = []
    word_index_drift_samples: list[int] = []
    examples: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for span in validated_children.values():
        evidence = asr.get(span.video_id)
        if evidence is None:
            asr_missing += 1
            if len(examples["asr_missing"]) < 5:
                examples["asr_missing"].append(
                    {"source_span_id": span.source_span_id, "video_id": span.video_id}
                )
            continue
        if span.asr_engine != evidence["asr_engine"]:
            asr_engine_mismatch += 1
        if span.asr_model_version != evidence["asr_model_version"]:
            asr_model_mismatch += 1
        if evidence["alignment_sha256"] and _sha256(Path(evidence["alignment_path"])) != evidence[
            "alignment_sha256"
        ]:
            alignment_hash_mismatch += 1
        if evidence["alignment_ok"] is not True:
            alignment_not_ok += 1

        # Primary check: does the cited audio window actually contain the clip
        # text? The word indices are a separate coordinate system and are
        # audited independently, so they cannot mask a bad playback offset.
        cited_tokens = _window_tokens_covering(
            asr[span.video_id]["timed_words"], span.start_ms, span.end_ms, tolerance_ms
        )
        clip_tokens = _norm_words(span.verbatim_text)
        citation_window_checked += 1
        if not clip_tokens:
            citation_window_unverifiable += 1
        else:
            coverage = _token_coverage(clip_tokens, cited_tokens)
            coverage_samples.append(coverage)
            if coverage >= coverage_floor:
                citation_window_exact += 1
            else:
                citation_window_mismatch += 1
                if len(examples["citation_window_mismatch"]) < 8:
                    examples["citation_window_mismatch"].append(
                        {
                            "source_span_id": span.source_span_id,
                            "video_id": span.video_id,
                            "payload_start_ms": span.start_ms,
                            "payload_end_ms": span.end_ms,
                            "coverage": round(coverage, 4),
                            "clip_tokens": len(clip_tokens),
                            "cited_tokens": len(cited_tokens),
                            "clip": span.verbatim_text[:160],
                            "cited_text": " ".join(cited_tokens[:60]),
                        }
                    )

        # Secondary check: the payload's word index space vs the ASR token
        # space. A mismatch does not invalidate the citation (the ms offsets
        # are authoritative) but it means the deterministic span id encodes a
        # word coordinate that does not match the ASR artifact.
        index_window = _timed_word_window(
            asr[span.video_id]["timed_words"], span.word_start, span.word_end
        )
        if not index_window["ok"]:
            word_index_out_of_range += 1
        else:
            index_drift = max(
                abs(index_window["start_ms"] - span.start_ms),
                abs(index_window["end_ms"] - span.end_ms),
            )
            word_index_drift_samples.append(index_drift)
            if index_drift <= tolerance_ms:
                word_index_consistent += 1
            else:
                word_index_inconsistent += 1

        window = _measured_window(
            tokens_by_video[span.video_id][0],
            tokens_by_video[span.video_id][1],
            asr[span.video_id]["timed_words"],
            span.verbatim_text,
        )
        if window["ok"]:
            drift = max(
                abs(window["start_ms"] - span.start_ms), abs(window["end_ms"] - span.end_ms)
            )
            drift_samples.append(drift)

        verdict = verdict_items.get(span.source_span_id)
        if verdict and verdict.get("verified") is True:
            verdict_covered += 1
        else:
            verdict_uncovered += 1
            if span.speaker_verified:
                verified_without_verdict += 1

    gates = {
        "contract_children": {
            "status": "VERIFIED" if contract_errors["child_contract_invalid"] == 0 else "BLOCKED",
            "detail": f"{contract_errors['child_contract_invalid']} child payloads violate fp-context-v1",
        },
        "contract_parents": {
            "status": "VERIFIED" if contract_errors["parent_contract_invalid"] == 0 else "BLOCKED",
            "detail": f"{contract_errors['parent_contract_invalid']} parent payloads violate fp-context-v1",
        },
        "topology": {
            "status": (
                "VERIFIED"
                if not (orphan_children or wrong_guru or wrong_video or wrong_corpus
                        or parents_without_children or children_not_in_parent_order)
                else "BLOCKED"
            ),
            "detail": (
                f"orphan_children={orphan_children} wrong_guru={wrong_guru} "
                f"wrong_video={wrong_video} wrong_corpus={wrong_corpus} "
                f"parents_without_children={parents_without_children} "
                f"children_not_in_parent_order={children_not_in_parent_order}"
            ),
        },
        "asr_provenance": {
            "status": (
                "VERIFIED"
                if asr_artifacts_available
                and not (asr_missing or asr_engine_mismatch or asr_model_mismatch)
                else "BLOCKED"
            ),
            "detail": (
                (
                    f"missing={asr_missing} engine_mismatch={asr_engine_mismatch} "
                    f"model_mismatch={asr_model_mismatch}"
                )
                if asr_artifacts_available
                else (
                    f"ASR artifact root {attr_root} is not available on this host; "
                    "the asr_provenance gate could not be evaluated"
                )
            ),
        },
        "alignment_integrity": {
            "status": (
                "VERIFIED" if not (alignment_hash_mismatch or alignment_not_ok) else "BLOCKED"
            ),
            "detail": (
                f"alignment_sha256_mismatch={alignment_hash_mismatch} "
                f"alignment_not_ok={alignment_not_ok}"
            ),
        },
        "citation_window_covers_clip": {
            "status": (
                "VERIFIED"
                if not (citation_window_mismatch or citation_window_unverifiable)
                else "BLOCKED"
            ),
            "detail": (
                f"checked={citation_window_checked} exact={citation_window_exact} "
                f"mismatch={citation_window_mismatch} "
                f"unverifiable={citation_window_unverifiable} "
                f"tolerance_ms={tolerance_ms} coverage_floor={coverage_floor}"
            ),
        },
        "word_index_consistency": {
            "status": "VERIFIED" if word_index_out_of_range == 0 else "BLOCKED",
            "detail": (
                f"consistent={word_index_consistent} inconsistent={word_index_inconsistent} "
                f"out_of_range={word_index_out_of_range}"
            ),
        },
        "speaker_evidence_per_span": {
            "status": "VERIFIED" if verified_without_verdict == 0 else "BLOCKED",
            "detail": (
                f"verified_without_per_span_verdict={verified_without_verdict} "
                f"verdict_covered={verdict_covered} verdict_uncovered={verdict_uncovered}"
            ),
        },
    }
    overall = "VERIFIED" if all(g["status"] == "VERIFIED" for g in gates.values()) else "BLOCKED"

    drift_samples.sort()

    def _pct_of(samples: list[int], value: float) -> int | None:
        if not samples:
            return None
        index = min(len(samples) - 1, int(len(samples) * value))
        return samples[index]

    def _pct(value: float) -> int | None:
        return _pct_of(drift_samples, value)

    return {
        "schema": "first-person-v10-strict-audit-v1",
        "generated_at_utc": _now(),
        "qdrant_url": base_url,
        "collection": collection,
        "alias": alias,
        "alias_target": alias_target,
        "collection_points": len(points),
        "child_points": len(children),
        "parent_points": len(parents),
        "validated_children": len(validated_children),
        "validated_parents": len(validated_parents),
        "attr_root": str(attr_root),
        "asr_artifacts_available": asr_artifacts_available,
        "asr_videos_indexed": len(asr),
        "speaker_verdicts_file": str(speaker_verdicts) if speaker_verdicts else None,
        "speaker_verdicts_count": len(verdict_items),
        "gates": gates,
        "contract_errors": dict(contract_errors),
        "contract_error_samples": {k: v for k, v in contract_samples.items()},
        "citation_window_coverage": {
            "count": len(coverage_samples),
            "min": round(min(coverage_samples), 4) if coverage_samples else None,
            "p05": round(sorted(coverage_samples)[int(len(coverage_samples) * 0.05)], 4)
            if coverage_samples
            else None,
            "p50": round(sorted(coverage_samples)[len(coverage_samples) // 2], 4)
            if coverage_samples
            else None,
            "below_floor": sum(1 for value in coverage_samples if value < coverage_floor),
        },
        "audio_window_drift_ms": {
            "count": len(drift_samples),
            "p50": _pct(0.50),
            "p95": _pct(0.95),
            "max": drift_samples[-1] if drift_samples else None,
        },
        "word_index_drift_ms": {
            "count": len(word_index_drift_samples),
            "p50": _pct_of(word_index_drift_samples, 0.50),
            "p95": _pct_of(word_index_drift_samples, 0.95),
            "max": word_index_drift_samples[-1] if word_index_drift_samples else None,
        },
        "examples": {k: v for k, v in examples.items()},
        "overall": overall,
    }


def _now() -> str:
    import datetime

    return datetime.datetime.now(datetime.UTC).isoformat()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qdrant-url", default=os.getenv("QDRANT_URL", "http://localhost:6333"))
    parser.add_argument("--collection", default=os.getenv("FIRST_PERSON_COLLECTION", "first_person_v10"))
    parser.add_argument("--alias", default=os.getenv("FIRST_PERSON_ALIAS", "first_person"))
    parser.add_argument(
        "--attr-root",
        default=os.getenv(
            "ATTR_ROOT",
            "/Users/harshodaikolluru/mukthiguru_attribution_data",
        ),
    )
    parser.add_argument("--speaker-verdicts", default=None)
    parser.add_argument("--tolerance-ms", type=int, default=50)
    parser.add_argument("--coverage-floor", type=float, default=0.90)
    parser.add_argument("--output")
    args = parser.parse_args(argv)
    try:
        report = audit(
            base_url=args.qdrant_url,
            collection=args.collection,
            alias=args.alias,
            attr_root=Path(args.attr_root),
            speaker_verdicts=Path(args.speaker_verdicts) if args.speaker_verdicts else None,
            tolerance_ms=args.tolerance_ms,
            coverage_floor=args.coverage_floor,
        )
    except (OSError, ValueError, urllib.error.URLError) as exc:
        print(
            json.dumps({"schema": "first-person-v10-strict-audit-v1", "overall": "BLOCKED", "error": str(exc)}),
            file=sys.stderr,
        )
        return 2
    rendered = json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(rendered, encoding="utf-8")
        print(f"wrote {args.output} overall={report['overall']}")
    else:
        print(rendered, end="")
    return 0 if report["overall"] == "VERIFIED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
