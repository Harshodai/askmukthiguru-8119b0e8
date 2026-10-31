#!/usr/bin/env python3
"""Write the served-window ECAPA verdict back onto first-person v10 spans (B3).

Why this exists
---------------
``backend/scripts/ops/score_v10_unchecked_speakers.py`` and
``backend/scripts/ops/regenerate_v10_span_ecapa_verdicts.py --spans-jsonl``
produce evidence only. Neither writes a collection. This script is the single
place where that evidence becomes a payload change, and it is deliberately
narrow:

* **Dry run by default.** Nothing is written unless ``--apply`` is passed.
* ``--apply`` refuses to run without ``--snapshot`` (a snapshot of the same
  collection taken in the same session). The owner's explicit OK is a human
  gate outside this script; the script only makes skipping the snapshot
  impossible.
* It writes ``set_payload`` only, restricted to
  ``voice_verification_method`` / ``voice_verdict`` / ``speaker_verified`` /
  ``speaker_verification_status``. Every other key is refused by
  :func:`allowed_key_violation` before the first write.
* Before writing, the old value of every touched key is saved to
  ``--rollback-out``. Rollback is a ``set_payload`` from that file, or a
  snapshot restore.
* Absence of evidence is never converted into evidence: a span with no verdict
  row, an unreadable slice (``missing_audio`` / ``invalid_audio`` /
  ``out_of_bounds`` / ``too_short``), an unverified calibration, or a missing
  window check is left **untouched** and reported as ``no_evidence``.

Never touched
-------------
``verbatim_text``, ``source_transcript_text``, ``transcript_hash``,
``source_text_hash``, point ids and vectors. This script only changes the four
speaker-evidence keys above; it never re-embeds, never re-upserts a point and
never synthesises text.

Outcomes
--------
* ``pass``    ECAPA verified the labelled teacher **and** the independent window
              check passed: ``voice_verification_method`` is stamped
              ``ecapa_voxceleb_span_slice_v2`` with the recorded
              ``voice_verdict`` (cosine, margin, calibration revision, window
              check). ``speaker_verified`` is left exactly as it was — the plan
              says it "stays true", and this script never flips a flag on this
              branch. The report records its value before the run so a span that
              was already false is visible instead of silently promoted.
* ``fail``    a different teacher, a host window, or below the calibrated floor:
              ``speaker_verified=false`` + ``speaker_verification_status="ecapa_failed"``.
              The span stays in the collection; its video is listed in the
              report's ``listen_queue`` for the admin Video Approval listen
              queue. A human confirmation (plan item I4) is what re-serves it
              with ``human_listen_v1``; this script never writes that value.
* ``no_evidence``  nothing was written; the span is reported.

Usage
-----
    # dry run (default): prints the plan, writes no payload
    python scripts/ops/backfill_v10_voice_method.py \\
        --verdicts-jsonl served_verdicts.jsonl \\
        --windows-jsonl unchecked_speakers.jsonl \\
        --report backfill_report.json

    # apply, after a snapshot taken in the same session and the owner's OK
    python scripts/ops/backfill_v10_voice_method.py ... \\
        --apply --snapshot first_person_v10-...-2026-10-31-10-00-00.snapshot \\
        --rollback-out rollback.json --report backfill_report.json

Exit codes: 0 plan/dry run completed; 1 a write or invariant failure; 2 invalid
input (including ``--apply`` without ``--snapshot``).
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
from collections import Counter
from pathlib import Path
from typing import Any

EXIT_OK = 0
EXIT_WRITE_FAILED = 1
EXIT_INVALID_INPUT = 2

SCRIPT_VERSION = "backfill-v10-voice-method-v1"
REPORT_SCHEMA = "first-person-v10-voice-method-backfill-v1"
ROLLBACK_SCHEMA = "first-person-v10-voice-method-rollback-v1"

#: The method stamped only when the served window itself cleared the pinned floor.
PASS_METHOD = "ecapa_voxceleb_span_slice_v2"
#: Human confirmation (plan item I4). Documented, never written here.
HUMAN_METHOD = "human_listen_v1"
#: Status written on the fail branch.
FAIL_STATUS = "ecapa_failed"

#: The only keys this script may ever set. Anything else is a hard error.
ALLOWED_KEYS = (
    "voice_verification_method",
    "voice_verdict",
    "speaker_verified",
    "speaker_verification_status",
)

#: Ecapa verdicts that mean "no usable audio / no calibration" — not a refusal.
NO_EVIDENCE_VERDICTS = frozenset(
    {
        "missing_audio",
        "invalid_audio",
        "out_of_bounds",
        "too_short",
        "not_run",
        "calibration_unavailable",
    }
)

#: Window-check outcomes (see ``score_v10_unchecked_speakers.py``).
WINDOW_PASS = "window_pass"
WINDOW_FAIL = "window_fail"
WINDOW_NONE = "no_diarization"


def allowed_key_violation(updates: dict[str, Any]) -> str | None:
    """Return the first key outside :data:`ALLOWED_KEYS`, or ``None`` if clean."""
    extra = sorted(set(updates) - set(ALLOWED_KEYS))
    return extra[0] if extra else None


def _window_verdict(payload: dict[str, Any], window_row: dict[str, Any] | None) -> str | None:
    """Window-check verdict for *this* span, or ``None`` when there is no usable row."""
    if not isinstance(window_row, dict):
        return None
    if str(window_row.get("source_span_id") or "") != str(payload.get("source_span_id") or ""):
        return None
    verdict = str(window_row.get("verdict") or "")
    return verdict or None


def _fail_updates() -> dict[str, Any]:
    return {"speaker_verified": False, "speaker_verification_status": FAIL_STATUS}


def decide(
    payload: dict[str, Any],
    verdict_row: dict[str, Any] | None,
    window_row: dict[str, Any] | None,
) -> tuple[str, dict[str, Any]]:
    """Map one span's evidence to ``("pass" | "fail" | "no_evidence", updates)``.

    Pure: same evidence always gives the same outcome. ``no_evidence`` always
    returns an empty update dict, so a caller cannot accidentally write on it.
    """
    if not isinstance(verdict_row, dict):
        return "no_evidence", {}
    if str(verdict_row.get("source_span_id") or "") != str(payload.get("source_span_id") or ""):
        return "no_evidence", {}

    verdict = str(verdict_row.get("verdict") or "")
    if not verdict or verdict in NO_EVIDENCE_VERDICTS:
        return "no_evidence", {}

    window = _window_verdict(payload, window_row)

    if verdict != "verified":
        # refused_below_cosine_floor / refused_below_margin / refused_guru_mismatch:
        # positive evidence that the labelled teacher is not the one speaking.
        return "fail", _fail_updates()

    revision = str(verdict_row.get("calibration_revision") or "")
    if not revision:
        # A verdict that cannot be traced to a calibration is not evidence.
        return "no_evidence", {}
    if window == WINDOW_PASS:
        return "pass", {
            "voice_verification_method": PASS_METHOD,
            "voice_verdict": {
                "cosine": verdict_row.get("cosine"),
                "margin": verdict_row.get("margin"),
                "calibration_revision": revision,
                "window_check": WINDOW_PASS,
            },
        }
    if window == WINDOW_FAIL:
        return "fail", _fail_updates()
    # ``no_diarization`` or a missing window row: the acoustic half passed but the
    # independent check said nothing. Absence is not a pass and not a refusal.
    return "no_evidence", {}


def _load_rows(path: Path) -> dict[str, dict[str, Any]]:
    """JSONL evidence file keyed by ``source_span_id``.

    A malformed line is fatal: silently skipping it would turn a refusal into
    "no verdict", which is a different (and wrong) claim.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"cannot read {path}: {exc}") from exc
    rows: dict[str, dict[str, Any]] = {}
    for number, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path}: line {number} is not valid JSON: {exc}") from exc
        if not isinstance(row, dict):
            raise ValueError(f"{path}: line {number} is not a JSON object")
        span_id = str(row.get("source_span_id") or "")
        if not span_id:
            raise ValueError(f"{path}: line {number} has no source_span_id")
        if span_id in rows:
            raise ValueError(f"{path}: duplicate source_span_id {span_id!r} at line {number}")
        rows[span_id] = row
    return rows


def _scroll(qdrant_url: str, collection: str, page: int = 512):
    """Yield every point payload (vectors are never requested)."""
    import requests

    offset = None
    while True:
        body: dict[str, Any] = {"limit": page, "with_payload": True, "with_vector": False}
        if offset:
            body["offset"] = offset
        resp = requests.post(
            f"{qdrant_url}/collections/{collection}/points/scroll", json=body, timeout=60
        )
        resp.raise_for_status()
        result = resp.json()["result"]
        for point in result.get("points") or []:
            yield str(point["id"]), point.get("payload") or {}
        offset = result.get("next_page_offset")
        if not offset:
            return


def _set_payload(qdrant_url: str, collection: str, point_id: str, updates: dict[str, Any]) -> None:
    """The only write in this file: a payload patch on one point."""
    import requests

    resp = requests.post(
        f"{qdrant_url}/collections/{collection}/points/payload",
        json={"payload": updates, "points": [point_id]},
        timeout=60,
    )
    resp.raise_for_status()


def plan(
    points: list[tuple[str, dict[str, Any]]],
    verdicts: dict[str, dict[str, Any]],
    windows: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Pure planning step: what would change, and on what evidence.

    Only points that carry a ``source_span_id`` present in ``verdicts`` are
    considered. A point without a verdict row is never touched.
    """
    rows: list[dict[str, Any]] = []
    without_verdict = 0
    point_id_mismatch = 0
    for point_id, payload in points:
        span_id = str(payload.get("source_span_id") or "")
        if not span_id:
            continue
        verdict_row = verdicts.get(span_id)
        if verdict_row is None:
            without_verdict += 1
            continue
        declared = str(verdict_row.get("point_id") or "")
        if declared and declared != point_id:
            point_id_mismatch += 1
            rows.append(
                {
                    "span_id": span_id,
                    "point_id": point_id,
                    "video_id": payload.get("video_id"),
                    "speaker_verified_before": payload.get("speaker_verified"),
                    "outcome": "no_evidence",
                    "reason": "declared_point_id_differs_from_collection_point_id",
                    "updates": {},
                }
            )
            continue
        outcome, updates = decide(payload, verdict_row, windows.get(span_id))
        violation = allowed_key_violation(updates)
        if violation is not None:
            raise ValueError(f"refusing to write non-allowlisted key {violation!r}")
        rows.append(
            {
                "span_id": span_id,
                "point_id": point_id,
                "video_id": payload.get("video_id"),
                "speaker_verified_before": payload.get("speaker_verified"),
                "outcome": outcome,
                "reason": str(verdict_row.get("verdict") or ""),
                "window_check": _window_verdict(payload, windows.get(span_id)),
                "updates": updates,
            }
        )
    return {
        "rows": rows,
        "points_without_verdict": without_verdict,
        "point_id_mismatch": point_id_mismatch,
        "counts": dict(Counter(row["outcome"] for row in rows)),
    }


def _rollback_payload(
    points: list[tuple[str, dict[str, Any]]],
    rows: list[dict[str, Any]],
    collection: str,
    snapshot: str,
) -> dict[str, Any]:
    """Old value of every key the apply step would touch.

    A key that was absent is recorded as ``null`` **and** listed in
    ``keys_previously_absent``: ``set_payload`` cannot delete a key, so a rollback
    of a previously-absent key is a null patch (or a snapshot restore), and the
    file says which is which instead of pretending null was the old value.
    """
    by_id = {point_id: payload for point_id, payload in points}
    entries: list[dict[str, Any]] = []
    for row in rows:
        if row["outcome"] == "no_evidence" or not row["updates"]:
            continue
        payload = by_id.get(row["point_id"], {})
        previous = {key: payload.get(key) for key in row["updates"]}
        absent = sorted(key for key in row["updates"] if key not in payload)
        entries.append(
            {"id": row["point_id"], "previous": previous, "keys_previously_absent": absent}
        )
    return {
        "schema": ROLLBACK_SCHEMA,
        "script_version": SCRIPT_VERSION,
        "collection": collection,
        "snapshot": snapshot,
        "created_at_utc": dt.datetime.now(dt.UTC).isoformat(),
        "restore": "set_payload each entry's 'previous' onto its 'id' (or restore the snapshot)",
        "points": entries,
    }


def _listen_queue(rows: list[dict[str, Any]]) -> dict[str, list[str]]:
    """Videos whose failed spans need a human listen (admin Video Approval queue)."""
    queue: dict[str, list[str]] = {}
    for row in rows:
        if row["outcome"] != "fail":
            continue
        video_id = str(row["video_id"] or "")
        if not video_id:
            continue
        queue.setdefault(video_id, []).append(row["span_id"])
    return {video_id: sorted(spans) for video_id, spans in sorted(queue.items())}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--verdicts-jsonl", required=True, help="Served-window ECAPA verdict rows.")
    parser.add_argument(
        "--windows-jsonl", default=None, help="Window-check rows (score_v10_unchecked_speakers.py)."
    )
    parser.add_argument(
        "--qdrant-url", default=os.environ.get("QDRANT_URL", "http://localhost:6333")
    )
    parser.add_argument(
        "--collection", default=os.environ.get("QDRANT_COLLECTION", "first_person_v10")
    )
    parser.add_argument("--apply", action="store_true", help="Write to Qdrant (default: dry run).")
    parser.add_argument(
        "--snapshot",
        default="",
        help="REQUIRED with --apply: name of a snapshot of this collection taken in this session.",
    )
    parser.add_argument("--rollback-out", default=None, help="Rollback JSON (apply only).")
    parser.add_argument("--report", default=None, help="Report JSON (dry run and apply).")
    args = parser.parse_args(argv)

    if args.apply and not str(args.snapshot).strip():
        print(
            json.dumps(
                {
                    "schema": REPORT_SCHEMA,
                    "script_version": SCRIPT_VERSION,
                    "status": "refused",
                    "error": (
                        "--apply requires --snapshot <name>: take a snapshot of the collection in "
                        "the same session first, and get the owner's explicit OK. Nothing was written."
                    ),
                },
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return EXIT_INVALID_INPUT

    try:
        verdicts = _load_rows(Path(args.verdicts_jsonl))
        windows = _load_rows(Path(args.windows_jsonl)) if args.windows_jsonl else {}
    except ValueError as exc:
        print(
            json.dumps(
                {"schema": REPORT_SCHEMA, "status": "invalid_input", "error": str(exc)},
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return EXIT_INVALID_INPUT

    try:
        points = list(_scroll(args.qdrant_url, args.collection))
        planned = plan(points, verdicts, windows)
    except ValueError as exc:
        print(
            json.dumps(
                {"schema": REPORT_SCHEMA, "status": "invalid_input", "error": str(exc)},
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return EXIT_INVALID_INPUT

    rows = planned["rows"]
    counts = planned["counts"]
    report: dict[str, Any] = {
        "schema": REPORT_SCHEMA,
        "script_version": SCRIPT_VERSION,
        "generated_at_utc": dt.datetime.now(dt.UTC).isoformat(),
        "mode": "apply" if args.apply else "dry_run",
        "qdrant_url": args.qdrant_url,
        "collection": args.collection,
        "inputs": {
            "verdicts_jsonl": str(Path(args.verdicts_jsonl).resolve()),
            "windows_jsonl": str(Path(args.windows_jsonl).resolve())
            if args.windows_jsonl
            else None,
        },
        "points_scrolled": len(points),
        "points_without_verdict": planned["points_without_verdict"],
        "point_id_mismatch": planned["point_id_mismatch"],
        "outcomes": counts,
        "written": 0,
        "snapshot": str(args.snapshot) if args.apply else None,
        "listen_queue": _listen_queue(rows),
        "rows": rows,
    }

    if not args.apply:
        report["mutations"] = {"qdrant_writes": 0}
        if args.report:
            _write_json(args.report, report)
        print(
            json.dumps({k: v for k, v in report.items() if k != "rows"}, indent=2, sort_keys=True)
        )
        print("\nDRY RUN — zero writes performed. Re-run with --apply --snapshot <name> to write.")
        return EXIT_OK

    if not args.rollback_out:
        print(
            json.dumps(
                {
                    "schema": REPORT_SCHEMA,
                    "status": "refused",
                    "error": "--apply requires --rollback-out: no write happens without a saved "
                    "old value for every touched key. Nothing was written.",
                },
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return EXIT_INVALID_INPUT

    rollback = _rollback_payload(points, rows, args.collection, str(args.snapshot))
    _write_json(args.rollback_out, rollback)

    written = 0
    failed: list[dict[str, Any]] = []
    for row in rows:
        if row["outcome"] == "no_evidence" or not row["updates"]:
            continue
        try:
            _set_payload(args.qdrant_url, args.collection, row["point_id"], row["updates"])
        except Exception as exc:  # noqa: BLE001 - one failed point must not hide the rest
            failed.append({"span_id": row["span_id"], "error": str(exc)})
            continue
        written += 1

    report["written"] = written
    report["failed"] = failed
    report["rollback_path"] = str(Path(args.rollback_out).resolve())
    report["mutations"] = {"qdrant_writes": written}
    if args.report:
        _write_json(args.report, report)
    print(json.dumps({k: v for k, v in report.items() if k != "rows"}, indent=2, sort_keys=True))
    if failed:
        print(
            f"\nINCOMPLETE: {len(failed)} point(s) failed to write. Rollback: {args.rollback_out}"
        )
        return EXIT_WRITE_FAILED
    print(f"\nAPPLIED {written} point(s). Rollback: {args.rollback_out}")
    return EXIT_OK


def _write_json(path: str, payload: Any) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    sys.exit(main())
