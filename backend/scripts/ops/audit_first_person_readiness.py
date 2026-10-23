"""Read-only first-person readiness audit.

This script never creates, updates, deletes, or aliases Qdrant collections. It
checks the active alias, collection metadata, and every payload point needed by
the fp-context-v1 release gates. It is intentionally usable from the host or a
runtime image with only Python's standard library.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import urllib.error
import urllib.request
from collections import Counter
from typing import Any

REQUIRED_CONTEXT_FIELDS = (
    "guru_id",
    "corpus_version",
    "source_asset_id",
    "parent_unit_id",
    "source_span_id",
    "speaker_id",
    "speaker_role",
    "speaker_verified",
    "turn_id",
    "turn_index",
    "boundary_status",
    "completeness_status",
    "source_text_hash",
    "caption_status",
    "asr_engine",
    "asr_model_version",
    "audio_start_ms",
    "audio_end_ms",
)

REQUIRED_PARENT_FIELDS = (
    "schema_version",
    "record_type",
    "corpus_version",
    "guru_id",
    "video_id",
    "parent_unit_id",
    "ordered_source_span_ids",
    "start_ms",
    "end_ms",
    "parent_text_hash",
    "speaker_ids",
    "speaker_continuity",
    "boundary_status",
    "completeness_status",
    "parent_version",
)


def _request(base_url: str, path: str, method: str = "GET", body: Any = None) -> dict[str, Any]:
    data = None if body is None else json.dumps(body).encode("utf-8")
    request = urllib.request.Request(
        base_url.rstrip("/") + path,
        data=data,
        headers={"Content-Type": "application/json"},
        method=method,
    )
    with urllib.request.urlopen(request, timeout=30) as response:  # nosec B310 -- operator-supplied http(s) base URL, read-only audit call
        payload = json.load(response)
    if not isinstance(payload, dict):
        raise ValueError(f"Qdrant returned a non-object response for {path}")
    return payload


def _result(base_url: str, path: str, method: str = "GET", body: Any = None) -> dict[str, Any]:
    payload = _request(base_url, path, method, body).get("result")
    if not isinstance(payload, dict):
        raise ValueError(f"Qdrant response has no object result for {path}")
    return payload


def _collection_info(base_url: str, collection: str) -> dict[str, Any]:
    return _result(base_url, f"/collections/{collection}")


def _scroll_all(base_url: str, collection: str) -> list[dict[str, Any]]:
    points: list[dict[str, Any]] = []
    offset: Any = None
    while True:
        body: dict[str, Any] = {"limit": 256, "with_payload": True, "with_vector": False}
        if offset is not None:
            body["offset"] = offset
        result = _result(base_url, f"/collections/{collection}/points/scroll", "POST", body)
        batch = result.get("points", [])
        if not isinstance(batch, list):
            raise ValueError("Qdrant scroll returned a non-list points value")
        points.extend(point for point in batch if isinstance(point, dict))
        offset = result.get("next_page_offset")
        if offset is None:
            return points


def _gate(status: str, detail: str, **extra: Any) -> dict[str, Any]:
    return {"status": status, "detail": detail, **extra}


def audit(
    base_url: str,
    collection: str,
    alias: str,
    context_collection: str | None = None,
) -> dict[str, Any]:
    aliases = _result(base_url, "/aliases").get("aliases", [])
    alias_target = next(
        (
            item.get("collection_name")
            for item in aliases
            if isinstance(item, dict) and item.get("alias_name") == alias
        ),
        None,
    )
    info = _collection_info(base_url, collection)
    points = _scroll_all(base_url, collection)
    missing = Counter()
    speaker_unverified = 0
    rights_bad = 0
    eligible_bad = 0
    verbatim_bad = 0
    hash_mismatch = 0
    duplicate_ids = 0
    seen_ids: set[str] = set()
    record_types = Counter()
    child_points = 0
    parent_points = 0
    for point in points:
        point_id = str(point.get("id"))
        if point_id in seen_ids:
            duplicate_ids += 1
        seen_ids.add(point_id)
        payload = point.get("payload") or {}
        if not isinstance(payload, dict):
            payload = {}
        record_type = str(payload.get("record_type") or "unknown")
        record_types[record_type] += 1
        required_fields = (
            REQUIRED_PARENT_FIELDS if record_type == "parent_unit" else REQUIRED_CONTEXT_FIELDS
        )
        if record_type == "parent_unit":
            parent_points += 1
        else:
            child_points += 1
        for field in required_fields:
            # fp-context-v1 stores the exact playback interval as start_ms/end_ms;
            # accept those canonical names for the audit's audio aliases.
            present = field in payload and payload[field] not in (None, "")
            if field == "audio_start_ms":
                present = present or payload.get("start_ms") not in (None, "")
            elif field == "audio_end_ms":
                present = present or payload.get("end_ms") not in (None, "")
            if not present:
                missing[field] += 1
        # Parent records describe grouping/context and do not themselves carry
        # a servable quote. Strict speaker/rights/verbatim/hash gates apply to
        # retrieval children only; requiring child fields on parents would
        # manufacture false failures while masking the actual child contract.
        if record_type == "parent_unit":
            continue
        if payload.get("speaker_verified") is not True:
            speaker_unverified += 1
        if payload.get("rights_cleared") is not True:
            rights_bad += 1
        # fp-context-v1 child records use rights_cleared and quality/status
        # gates; first_person_eligible is a legacy clip-store field and is not
        # part of the typed context contract.
        if record_type != "retrieval_child" and payload.get("first_person_eligible") is not True:
            eligible_bad += 1
        if payload.get("is_verbatim") is not True:
            verbatim_bad += 1
        text = payload.get("verbatim_text")
        # transcript_hash identifies the source transcript/video in this
        # schema. source_text_hash is the span-level hash that must match the
        # immutable verbatim text.
        stored_hash = payload.get("source_text_hash")
        # A missing/empty hash cannot be recomputed, so it fails closed like a
        # mismatch rather than silently passing the gate.
        if not isinstance(text, str) or not text.strip():
            hash_mismatch += 1
        elif not isinstance(stored_hash, str) or not stored_hash:
            hash_mismatch += 1
        elif hashlib.sha256(text.encode("utf-8")).hexdigest() != stored_hash:
            hash_mismatch += 1

    expected_context = context_collection or ""
    context_info = None
    if expected_context:
        context_info = _collection_info(base_url, expected_context)

    gates = {
        "alias_target": (
            _gate("VERIFIED", f"alias {alias!r} targets {alias_target!r}")
            if alias_target == collection
            else _gate(
                "BLOCKED", f"alias {alias!r} targets {alias_target!r}, expected {collection!r}"
            )
        ),
        "collection_green": _gate(
            "VERIFIED" if info.get("status") == "green" else "BLOCKED",
            f"collection status={info.get('status')!r} optimizer={info.get('optimizer_status')!r}",
        ),
        # Completeness is only meaningful when a context collection was
        # supplied to audit. Without one the gate never ran, so it must report
        # NOT_RUN rather than a VERIFIED derived from the clip store, whose
        # schema is not the fp-context-v1 payload being audited.
        "context_payload_completeness": _gate(
            "VERIFIED" if not missing else "BLOCKED",
            "all required fields present" if not missing else "required fields are missing",
            missing=dict(missing),
        )
        if expected_context
        else _gate(
            "NOT_RUN",
            "no context collection was supplied",
            missing=dict(missing),
        ),
        "speaker_verification": _gate(
            "VERIFIED" if speaker_unverified == 0 else "BLOCKED",
            f"{speaker_unverified} points are unverified or missing speaker_verified",
        ),
        "rights_and_eligibility": _gate(
            "VERIFIED" if rights_bad == 0 and eligible_bad == 0 else "BLOCKED",
            f"rights_bad={rights_bad}, eligible_bad={eligible_bad}",
        ),
        "verbatim_and_hash": _gate(
            "VERIFIED" if verbatim_bad == 0 and hash_mismatch == 0 else "BLOCKED",
            f"is_verbatim_bad={verbatim_bad}, hash_mismatch={hash_mismatch}",
        ),
        "duplicate_point_ids": _gate(
            "VERIFIED" if duplicate_ids == 0 else "BLOCKED",
            f"duplicate_ids={duplicate_ids}",
        ),
        "context_collection": _gate(
            "VERIFIED" if context_info and context_info.get("status") == "green" else "BLOCKED",
            f"context_collection={expected_context!r}",
        )
        if expected_context
        else _gate("NOT_RUN", "no context collection was supplied"),
    }
    overall = (
        "VERIFIED" if all(gate["status"] == "VERIFIED" for gate in gates.values()) else "BLOCKED"
    )
    return {
        "schema": "first-person-readiness-audit-v1",
        "qdrant_url": base_url,
        "collection": collection,
        "alias": alias,
        "alias_target": alias_target,
        "collection_points": len(points),
        "record_types": dict(record_types),
        "child_points": child_points,
        "parent_points": parent_points,
        "collection_info": info,
        "context_collection": expected_context or None,
        "context_collection_info": context_info,
        "gates": gates,
        "overall": overall,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qdrant-url", default=os.getenv("QDRANT_URL", "http://localhost:6333"))
    parser.add_argument(
        "--collection", default=os.getenv("FIRST_PERSON_COLLECTION", "first_person_v9")
    )
    parser.add_argument("--alias", default=os.getenv("FIRST_PERSON_ALIAS", "first_person"))
    parser.add_argument(
        "--context-collection", default=os.getenv("FIRST_PERSON_CONTEXT_COLLECTION", "")
    )
    parser.add_argument("--output", help="write JSON to this path instead of stdout")
    args = parser.parse_args(argv)
    try:
        report = audit(
            args.qdrant_url, args.collection, args.alias, args.context_collection or None
        )
    except (OSError, ValueError, urllib.error.URLError) as exc:
        print(
            json.dumps(
                {
                    "schema": "first-person-readiness-audit-v1",
                    "overall": "BLOCKED",
                    "error": str(exc),
                }
            ),
            file=sys.stderr,
        )
        return 2
    rendered = json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    if args.output:
        with open(args.output, "w", encoding="utf-8") as handle:
            handle.write(rendered)
    else:
        print(rendered, end="")
    return 0 if report["overall"] == "VERIFIED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
