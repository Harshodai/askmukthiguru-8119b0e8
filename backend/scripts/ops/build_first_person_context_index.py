#!/usr/bin/env python3
"""Build and audit the fp-context-v1 parent/child index (dry run only).

Two modes:

``--from-qdrant``
    Scroll an existing first-person collection and report, per payload field
    required by ``domain.first_person_context.SourceSpan``, how many points
    would fail validation. This is the phase-C inventory gap report; it never
    writes to Qdrant.

``--from-jsonl PATH``
    Convert raw span records into strict ``SourceSpan``/``ParentUnit`` objects
    and emit them as JSONL (``--output``) for review. Deterministic IDs are
    recomputed, so two runs over the same input produce byte-identical output.
    This also never writes to Qdrant.

Writes to a live collection are intentionally NOT implemented here. Promoting a
context collection is a release action with the plan's phase-E evidence and a
rollback record; a builder script must not be able to become one by accident.

Usage:
    python -m scripts.ops.build_first_person_context_index --from-qdrant \
        --collection first_person_v9 --report /tmp/fp_context_gap.json
    python -m scripts.ops.build_first_person_context_index \
        --from-jsonl spans.jsonl --output context.jsonl
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from collections.abc import Iterable
from pathlib import Path
from typing import Any

if __package__ in (None, ""):  # allow `python scripts/ops/...py`
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from domain.first_person_context import (  # noqa: E402
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

REQUIRED_FIELDS = tuple(
    name for name, field in SourceSpan.model_fields.items() if field.is_required()
)
# Fields that exist in the legacy payload under a different name (or not at all).
LEGACY_ONLY_FIELDS = ("start_ms", "end_ms", "video_url", "teacher_ids")
UNMAPPABLE_FIELDS = (
    "word_start",
    "word_end",
    "turn_index",
    "source_span_index",
    "source_asset_id",
    "source_transcript_text",
    "source_text_hash",
    "speaker_role",
    "boundary_status",
    "completeness_status",
    "voice_verification_method",
)


def gap_report(points: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Count how many payloads would fail each fp-context-v1 requirement."""
    total = 0
    missing: Counter[str] = Counter()
    extra_keys: Counter[str] = Counter()
    by_guru: Counter[str] = Counter()
    for payload in points:
        total += 1
        by_guru[str(payload.get("guru_id") or payload.get("teacher_id") or "?")] += 1
        for field_name in REQUIRED_FIELDS:
            if payload.get(field_name) in (None, ""):
                missing[field_name] += 1
        for key in payload:
            if key not in SourceSpan.model_fields and key not in LEGACY_ONLY_FIELDS:
                extra_keys[key] += 1

    missing_ratio = {
        field_name: round(count / total, 4) if total else 0.0
        for field_name, count in missing.most_common()
    }
    return {
        "total_points": total,
        "by_guru": dict(by_guru),
        "missing_required_field": missing_ratio,
        "extra_keys": dict(extra_keys),
        "unmappable_from_legacy": {k: missing_ratio.get(k, 0.0) for k in UNMAPPABLE_FIELDS},
        "migration_ready": (not missing_ratio) and (not extra_keys),
    }


def build_from_jsonl(records: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert raw records to parent/child payloads, ordered by start_ms per video."""
    grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for record in records:
        key = (
            str(record["guru_id"]),
            str(record["video_id"]),
            str(record.get("corpus_version", "fp-context-v1")),
        )
        grouped.setdefault(key, []).append(record)

    out: list[dict[str, Any]] = []
    for (guru_id, video_id, corpus_version), rows in grouped.items():
        rows.sort(key=lambda r: (int(r["start_ms"]), int(r["end_ms"])))
        spans: list[SourceSpan] = []
        for index, row in enumerate(rows):
            if "word_start" not in row or "word_end" not in row:
                continue
            word_start = int(row["word_start"])
            word_end = int(row["word_end"])
            verbatim = str(row["verbatim_text"])
            transcript_hash = str(row["transcript_hash"])
            span = SourceSpan(
                corpus_version=corpus_version,
                guru_id=guru_id,
                video_id=video_id,
                source_asset_id=str(row.get("source_asset_id", video_id)),
                source_span_id=make_source_span_id(
                    guru_id=guru_id,
                    video_id=video_id,
                    corpus_version=corpus_version,
                    word_start=word_start,
                    word_end=word_end,
                    transcript_hash=transcript_hash,
                ),
                parent_unit_id=make_parent_unit_id(
                    guru_id=guru_id,
                    video_id=video_id,
                    corpus_version=corpus_version,
                    first_word_index=int(rows[0]["word_start"]),
                    last_word_index=int(rows[-1]["word_end"]),
                ),
                turn_id=str(row.get("turn_id", f"{video_id}:turn:{index}")),
                turn_index=index,
                source_span_index=index,
                start_ms=int(row["start_ms"]),
                end_ms=int(row["end_ms"]),
                word_start=word_start,
                word_end=word_end,
                speaker_id=str(row.get("speaker_id", "unknown")),
                speaker_role=SpeakerRole(row.get("speaker_role", "unknown")),
                speaker_verified=bool(row.get("speaker_verified", False)),
                source_transcript_text=str(row.get("source_transcript_text", verbatim)),
                verbatim_text=verbatim,
                transcript_hash=transcript_hash,
                source_text_hash=clip_text_hash(verbatim),
                boundary_status=BoundaryStatus(row.get("boundary_status", "uncertain")),
                completeness_status=CompletenessStatus(row.get("completeness_status", "uncertain")),
                rights_cleared=bool(row.get("rights_cleared", False)),
                caption_status=str(row.get("caption_status", "auto")),
                provenance_kind=ProvenanceKind(row.get("provenance_kind", "speech_turn_span")),
                source_url=str(row.get("source_url", "")),
            )
            spans.append(span)

        if not spans:
            continue
        ordered = tuple(s.source_span_id for s in spans)
        parent = ParentUnit(
            corpus_version=corpus_version,
            guru_id=guru_id,
            video_id=video_id,
            parent_unit_id=spans[0].parent_unit_id,
            ordered_source_span_ids=ordered,
            start_ms=spans[0].start_ms,
            end_ms=spans[-1].end_ms,
            parent_text_hash=clip_text_hash(" ".join(s.verbatim_text for s in spans)),
            speaker_ids=tuple(sorted({s.speaker_id for s in spans})),
            speaker_continuity=len({s.speaker_id for s in spans}) == 1,
            boundary_status=(
                BoundaryStatus.VERIFIED
                if all(s.boundary_status == BoundaryStatus.VERIFIED for s in spans)
                else BoundaryStatus.UNCERTAIN
            ),
            completeness_status=(
                CompletenessStatus.COMPLETE
                if all(s.completeness_status == CompletenessStatus.COMPLETE for s in spans)
                else CompletenessStatus.UNCERTAIN
            ),
        )
        out.extend(span.to_payload() for span in spans)
        out.append(parent.to_payload())
    return out


def _load_points(qdrant_url: str, collection: str) -> list[dict[str, Any]]:
    from qdrant_client import QdrantClient

    client = QdrantClient(url=qdrant_url)
    points: list[dict[str, Any]] = []
    offset = None
    while True:
        records, offset = client.scroll(
            collection_name=collection,
            limit=512,
            with_payload=True,
            with_vectors=False,
            offset=offset,
        )
        points.extend(record.payload or {} for record in records)
        if offset is None:
            break
    return points


def _self_check() -> None:
    record = {
        "guru_id": "krishnaji",
        "video_id": "vid-self-check",
        "word_start": 0,
        "word_end": 6,
        "start_ms": 0,
        "end_ms": 2000,
        "verbatim_text": "Suffering is a call to awaken.",
        "transcript_hash": "a" * 64,
        "rights_cleared": True,
        "speaker_verified": True,
        "source_url": "https://example.invalid/watch?v=vid-self-check",
    }
    payloads = build_from_jsonl([record])
    assert len(payloads) == 2, payloads
    assert payloads[0]["record_type"] == "retrieval_child"
    assert payloads[1]["record_type"] == "parent_unit"
    assert payloads[0]["source_text_hash"] == clip_text_hash(record["verbatim_text"])
    report = gap_report([{k: v for k, v in record.items() if k != "video_id"}])
    assert report["total_points"] == 1
    assert report["missing_required_field"], report
    print("self-check ok")


def main(argv: list[str] | None = None) -> int:
    from app.config import settings

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--from-qdrant", action="store_true")
    parser.add_argument("--collection", default="first_person_v9")
    parser.add_argument(
        "--qdrant-url",
        default=settings.qdrant_url,
    )
    parser.add_argument("--report", type=Path)
    parser.add_argument("--from-jsonl", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)

    if args.from_qdrant:
        report = gap_report(_load_points(args.qdrant_url, args.collection))
        text = json.dumps(report, indent=2, sort_keys=True)
        if args.report:
            args.report.write_text(text + "\n", encoding="utf-8")
        print(text)
        return 0

    if args.from_jsonl:
        if not args.output:
            parser.error("--from-jsonl requires --output")
        records = [
            json.loads(line)
            for line in args.from_jsonl.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        payloads = build_from_jsonl(records)
        args.output.write_text(
            "\n".join(json.dumps(p, sort_keys=True) for p in payloads) + "\n",
            encoding="utf-8",
        )
        print(f"wrote {len(payloads)} records to {args.output}")
        return 0

    parser.error("choose --from-qdrant or --from-jsonl")


if __name__ == "__main__":
    if "--self-check" in sys.argv:
        _self_check()
    else:
        raise SystemExit(main())
