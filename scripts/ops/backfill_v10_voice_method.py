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
* It writes ``set_payload`` only, restricted to the flat provenance keys in
  ``domain.speaker_provenance.AUTOMATED_PROVENANCE_KEYS`` plus
  ``speaker_verified``. Every other key is refused by
  :func:`allowed_key_violation` before the first write.
* Every merged payload goes through the shared write rule
  (``domain.speaker_provenance.speaker_write_violations``) **in the plan and again
  immediately before each write**. A span whose evidence is incomplete or
  contradicts itself (a score below the threshold recorded next to it, a failed
  window check) is reported as ``guard_refused`` and never written.
* Before writing, the old value of every touched key is saved to
  ``--rollback-out`` and the full "before" payload of **every** point is exported
  to ``--before-out`` (its SHA-256 goes into the report). Rollback is a
  ``set_payload`` from either file, or a snapshot restore.
* After writing it re-reads the collection and checks (see :func:`post_checks`):
  point ids and count unchanged, only allowlisted keys changed, ``verbatim_text``
  / ``source_transcript_text`` / both hashes unchanged on every point, vectors
  identical on a seeded sample, and **zero violators** of the write rule. Any
  failed check exits 1 and names itself in the report.
* Absence of evidence is never converted into evidence: a span with no verdict
  row, an unreadable slice (``missing_audio`` / ``invalid_audio`` /
  ``out_of_bounds`` / ``too_short``), an unverified calibration, an incomplete
  verdict row or a missing window check is left **untouched** and reported as
  ``no_evidence``. Such spans keep violating the write rule, so the
  ``violators_zero`` post-check will say so. ``--demote-no-evidence`` (off by
  default; it changes what is served, so it needs the owner's decision) sets
  them to ``speaker_verified=false`` / ``pending_voice_check`` instead.

Never touched
-------------
``verbatim_text``, ``source_transcript_text``, ``transcript_hash``,
``source_text_hash``, point ids and vectors. This script only changes the keys
above; it never re-embeds, never re-upserts a point and never synthesises text.
(That ``set_payload`` leaves vectors byte-identical is **not** stated in the Qdrant
docs; the vector post-check is how a run proves it.)

Outcomes
--------
* ``pass``    ECAPA verified the labelled teacher **and** the independent window
              check passed: ``voice_verification_method`` is stamped
              ``ecapa_voxceleb_span_slice_v2`` with the score, margin, model
              revision, threshold, calibration id and window check.
              ``speaker_verified`` is left exactly as it was; this script never
              flips a flag to true. The report records its value before the run so
              a span that was already false is visible instead of silently
              promoted.
* ``fail``    a different teacher, a host window, or below the calibrated floor:
              ``speaker_verified=false`` + ``speaker_verification_status="ecapa_failed"``
              (plus the evidence that was available). The span stays in the
              collection; its video is listed in the report's ``listen_queue`` for
              the admin Video Approval listen queue. A human confirmation (plan item
              I4) is what re-serves it with ``human_listen_v1``; this script never
              writes that value.
* ``guard_refused``  the evidence would have produced a payload the write rule
              refuses; nothing was written.
* ``demoted_no_evidence``  only with ``--demote-no-evidence``.
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
        --rollback-out rollback.json --before-out before.jsonl \\
        --expect-count 732 --report backfill_report.json

Exit codes: 0 plan/dry run completed; 1 a write or invariant failure; 2 invalid
input (including ``--apply`` without ``--snapshot``).
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import random
import sys
from collections import Counter
from pathlib import Path
from typing import Any

_BACKEND = Path(__file__).resolve().parents[2] / "backend"
if str(_BACKEND) not in sys.path:
    # Appended, not prepended: the repo-root ``scripts`` package must keep winning.
    sys.path.append(str(_BACKEND))

from domain.speaker_provenance import (  # noqa: E402
    AUTOMATED_PROVENANCE_KEYS,
    METHOD_ECAPA_SPAN_SLICE_V2,
    METHOD_HUMAN_LISTEN_V1,
    STATUS_ECAPA_FAILED,
    STATUS_PENDING_VOICE_CHECK,
    STATUS_VERIFIED,
    WINDOW_CHECK_FAIL,
    WINDOW_CHECK_NONE,
    WINDOW_CHECK_PASS,
    SpeakerWriteRefused,
    assert_speaker_write_allowed,
    speaker_write_violations,
)

EXIT_OK = 0
EXIT_WRITE_FAILED = 1
EXIT_INVALID_INPUT = 2

SCRIPT_VERSION = "backfill-v10-voice-method-v2"
REPORT_SCHEMA = "first-person-v10-voice-method-backfill-v2"
ROLLBACK_SCHEMA = "first-person-v10-voice-method-rollback-v1"
BEFORE_EXPORT_SCHEMA = "first-person-v10-voice-method-before-export-v1"

#: The method stamped only when the served window itself cleared the pinned floor.
PASS_METHOD = METHOD_ECAPA_SPAN_SLICE_V2
#: Human confirmation (plan item I4). Documented, never written here.
HUMAN_METHOD = METHOD_HUMAN_LISTEN_V1
#: Status written on the fail branch.
FAIL_STATUS = STATUS_ECAPA_FAILED

#: The only keys this script may ever set. Anything else is a hard error. The human-review
#: keys are deliberately absent: only a person's listen may write those.
ALLOWED_KEYS = (*AUTOMATED_PROVENANCE_KEYS, "speaker_verified")

#: Text and identity keys. A backfill that changes any of them has gone wrong.
IMMUTABLE_KEYS = (
    "verbatim_text",
    "source_transcript_text",
    "transcript_hash",
    "source_text_hash",
    "source_span_id",
    "parent_unit_id",
)

#: Points whose vectors are compared before and after the writes.
VECTOR_SAMPLE_SIZE = 20
#: Sample diffs shown in the dry-run report.
SAMPLE_DIFF_COUNT = 10
SAMPLE_SEED = "v10-voice-method-backfill-v2"

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

_WINDOW_TO_CHECK = {
    WINDOW_PASS: WINDOW_CHECK_PASS,
    WINDOW_FAIL: WINDOW_CHECK_FAIL,
    WINDOW_NONE: WINDOW_CHECK_NONE,
}


def _finite(value: Any) -> bool:
    import math

    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )


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


def _evidence_keys(verdict_row: dict[str, Any], window: str | None, now: str) -> dict[str, Any]:
    """Provenance keys the verdict row can back. Only keys with a real value are returned."""
    out: dict[str, Any] = {"voice_verified_at": now}
    revision = str(verdict_row.get("speaker_model_revision") or "")
    if revision:
        out["voice_model_revision"] = revision
    calibration = str(verdict_row.get("calibration_revision") or "")
    if calibration:
        out["voice_calibration_id"] = calibration
    if _finite(verdict_row.get("cosine")):
        out["voice_score"] = float(verdict_row["cosine"])
    if _finite(verdict_row.get("margin")):
        out["voice_margin"] = float(verdict_row["margin"])
    if _finite(verdict_row.get("cosine_floor")) and _finite(verdict_row.get("margin_threshold")):
        out["voice_threshold_applied"] = {
            "cosine_floor": float(verdict_row["cosine_floor"]),
            "margin_threshold": float(verdict_row["margin_threshold"]),
        }
    if window in _WINDOW_TO_CHECK:
        out["voice_window_check"] = _WINDOW_TO_CHECK[window]
    return out


def _fail_updates(
    verdict_row: dict[str, Any] | None = None, window: str | None = None, now: str = ""
) -> dict[str, Any]:
    updates: dict[str, Any] = {
        "speaker_verified": False,
        "speaker_verification_status": FAIL_STATUS,
    }
    if verdict_row is not None:
        # Keep what the listener will need: the score and the threshold it missed.
        updates.update(_evidence_keys(verdict_row, window, now))
    return updates


def decide(
    payload: dict[str, Any],
    verdict_row: dict[str, Any] | None,
    window_row: dict[str, Any] | None,
    *,
    now: str = "",
) -> tuple[str, dict[str, Any]]:
    """Map one span's evidence to ``("pass" | "fail" | "no_evidence", updates)``.

    Pure: same evidence (and ``now``) always gives the same outcome. ``no_evidence`` always
    returns an empty update dict, so a caller cannot accidentally write on it. A ``pass``
    needs a complete record: model revision, score, margin, both thresholds and the
    calibration id. A verdict row that cannot back all of them is ``no_evidence``.
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
        return "fail", _fail_updates(verdict_row, window, now)

    revision = str(verdict_row.get("calibration_revision") or "")
    if not revision:
        # A verdict that cannot be traced to a calibration is not evidence.
        return "no_evidence", {}
    if window == WINDOW_PASS:
        updates = _evidence_keys(verdict_row, window, now)
        needed = (
            "voice_model_revision",
            "voice_calibration_id",
            "voice_score",
            "voice_margin",
            "voice_threshold_applied",
        )
        if any(key not in updates for key in needed):
            # Verified, but the row cannot say with what model or against what threshold.
            return "no_evidence", {}
        updates["voice_verification_method"] = PASS_METHOD
        if payload.get("speaker_verified") is True:
            updates["speaker_verification_status"] = STATUS_VERIFIED
        return "pass", updates
    if window == WINDOW_FAIL:
        return "fail", _fail_updates(verdict_row, window, now)
    # ``no_diarization`` or a missing window row: the acoustic half passed but the
    # independent check said nothing. Absence is not a pass and not a refusal.
    return "no_evidence", {}


def _guard_reasons(payload: dict[str, Any], updates: dict[str, Any]) -> list[str]:
    """Write-rule violations of the payload as it would look after ``updates``."""
    return speaker_write_violations({**payload, **updates})


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


def _fetch_vectors(qdrant_url: str, collection: str, point_ids: list[str]) -> dict[str, Any]:
    """Vectors of the given points (read-only), keyed by point id."""
    import requests

    if not point_ids:
        return {}
    resp = requests.post(
        f"{qdrant_url}/collections/{collection}/points",
        json={"ids": point_ids, "with_payload": False, "with_vector": True},
        timeout=60,
    )
    resp.raise_for_status()
    return {str(item["id"]): item.get("vector") for item in resp.json()["result"]}


def vector_sample_ids(rows: list[dict[str, Any]], size: int = VECTOR_SAMPLE_SIZE) -> list[str]:
    """Seeded sample of touched point ids whose vectors are compared before and after."""
    touched = sorted({row["point_id"] for row in rows if writable(row)})
    return sorted(random.Random(f"{SAMPLE_SEED}:vectors").sample(touched, min(size, len(touched))))


def post_checks(
    before: list[tuple[str, dict[str, Any]]],
    after: list[tuple[str, dict[str, Any]]],
    vectors_before: dict[str, Any],
    vectors_after: dict[str, Any],
) -> dict[str, Any]:
    """Prove the backfill changed what it said it would and nothing else. Pure.

    Every check reports ``ok`` and enough detail to act on. ``all_ok`` is the AND.
    """
    before_by_id = {point_id: payload for point_id, payload in before}
    after_by_id = {point_id: payload for point_id, payload in after}
    checks: dict[str, dict[str, Any]] = {}

    missing = sorted(set(before_by_id) - set(after_by_id))
    added = sorted(set(after_by_id) - set(before_by_id))
    checks["points_unchanged"] = {
        "ok": not missing and not added and len(before) == len(after),
        "before": len(before),
        "after": len(after),
        "missing_after": missing[:10],
        "added_after": added[:10],
    }

    immutable_bad: list[dict[str, Any]] = []
    stray_bad: list[dict[str, Any]] = []
    for point_id, old in before_by_id.items():
        new = after_by_id.get(point_id)
        if new is None:
            continue
        for key in IMMUTABLE_KEYS:
            if old.get(key) != new.get(key):
                immutable_bad.append({"point_id": point_id, "key": key})
        changed = {key for key in set(old) | set(new) if old.get(key) != new.get(key)}
        stray = sorted(changed - set(ALLOWED_KEYS))
        if stray:
            stray_bad.append({"point_id": point_id, "keys": stray})
    checks["immutable_keys_unchanged"] = {
        "ok": not immutable_bad,
        "keys": list(IMMUTABLE_KEYS),
        "violations": len(immutable_bad),
        "examples": immutable_bad[:10],
    }
    checks["only_allowlisted_keys_changed"] = {
        "ok": not stray_bad,
        "violations": len(stray_bad),
        "examples": stray_bad[:10],
    }

    by_code: Counter[str] = Counter()
    violator_ids: list[str] = []
    for point_id, payload in after:
        if payload.get("record_type") not in (None, "retrieval_child"):
            continue
        reasons = speaker_write_violations(payload)
        if reasons:
            violator_ids.append(str(payload.get("source_span_id") or point_id))
            by_code[reasons[0].split(":")[0]] += 1
    checks["violators_zero"] = {
        "ok": not violator_ids,
        "violators": len(violator_ids),
        "by_first_reason": dict(by_code),
        "examples": violator_ids[:10],
        "note": (
            "spans still claiming a verified speaker the write rule would refuse; each needs "
            "evidence (re-run ECAPA), a human listen, or --demote-no-evidence"
        )
        if violator_ids
        else "",
    }

    different = sorted(
        point_id
        for point_id in vectors_before
        if vectors_before.get(point_id) != vectors_after.get(point_id)
    )
    checks["vectors_identical_on_sample"] = {
        "ok": not different and set(vectors_before) == set(vectors_after),
        "sampled": len(vectors_before),
        "different": different[:10],
    }

    return {"all_ok": all(check["ok"] for check in checks.values()), "checks": checks}


def export_before(path: str, points: list[tuple[str, dict[str, Any]]]) -> dict[str, Any]:
    """Write every point's id and full payload, sorted by id, and return its SHA-256."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        json.dumps(
            {"schema": BEFORE_EXPORT_SCHEMA, "id": point_id, "payload": payload},
            sort_keys=True,
            ensure_ascii=False,
        )
        for point_id, payload in sorted(points, key=lambda item: item[0])
    ]
    data = ("\n".join(lines) + "\n").encode("utf-8") if lines else b""
    target.write_bytes(data)
    return {
        "path": str(target.resolve()),
        "sha256": hashlib.sha256(data).hexdigest(),
        "points": len(lines),
    }


def _row(
    *,
    point_id: str,
    payload: dict[str, Any],
    span_id: str,
    outcome: str,
    reason: str,
    updates: dict[str, Any],
    window_check: str | None = None,
) -> dict[str, Any]:
    return {
        "span_id": span_id,
        "point_id": point_id,
        "video_id": payload.get("video_id"),
        "speaker_verified_before": payload.get("speaker_verified"),
        "outcome": outcome,
        "reason": reason,
        "window_check": window_check,
        "updates": updates,
    }


def plan(
    points: list[tuple[str, dict[str, Any]]],
    verdicts: dict[str, dict[str, Any]],
    windows: dict[str, dict[str, Any]],
    *,
    now: str = "",
    demote_no_evidence: bool = False,
) -> dict[str, Any]:
    """Pure planning step: what would change, and on what evidence.

    Only points that carry a ``source_span_id`` present in ``verdicts`` are
    considered, unless ``demote_no_evidence`` is set (then a point that violates the
    write rule and has no usable evidence is planned as a demotion). A point without a
    verdict row is otherwise never touched.
    """
    rows: list[dict[str, Any]] = []
    without_verdict = 0
    point_id_mismatch = 0

    def _demotion(point_id: str, payload: dict[str, Any], span_id: str, reason: str):
        if not demote_no_evidence or payload.get("speaker_verified") is not True:
            return None
        if not speaker_write_violations(payload):
            return None
        return _row(
            point_id=point_id,
            payload=payload,
            span_id=span_id,
            outcome="demoted_no_evidence",
            reason=reason,
            updates={
                "speaker_verified": False,
                "speaker_verification_status": STATUS_PENDING_VOICE_CHECK,
            },
        )

    for point_id, payload in points:
        span_id = str(payload.get("source_span_id") or "")
        if not span_id:
            continue
        verdict_row = verdicts.get(span_id)
        if verdict_row is None:
            without_verdict += 1
            demoted = _demotion(point_id, payload, span_id, "no_verdict_row")
            if demoted:
                rows.append(demoted)
            continue
        declared = str(verdict_row.get("point_id") or "")
        if declared and declared != point_id:
            point_id_mismatch += 1
            rows.append(
                _row(
                    point_id=point_id,
                    payload=payload,
                    span_id=span_id,
                    outcome="no_evidence",
                    reason="declared_point_id_differs_from_collection_point_id",
                    updates={},
                )
            )
            continue
        window_row = windows.get(span_id)
        outcome, updates = decide(payload, verdict_row, window_row, now=now)
        violation = allowed_key_violation(updates)
        if violation is not None:
            raise ValueError(f"refusing to write non-allowlisted key {violation!r}")
        reason = str(verdict_row.get("verdict") or "")
        if outcome == "pass":
            # The write rule decides, not this script's reading of the evidence: a record
            # that contradicts itself is refused here and again at write time.
            reasons = _guard_reasons(payload, updates)
            if reasons:
                outcome, updates, reason = "guard_refused", {}, ",".join(reasons)
        if outcome == "no_evidence":
            demoted = _demotion(point_id, payload, span_id, reason or "no_evidence")
            if demoted:
                rows.append(demoted)
                continue
        rows.append(
            _row(
                point_id=point_id,
                payload=payload,
                span_id=span_id,
                outcome=outcome,
                reason=reason,
                updates=updates,
                window_check=_window_verdict(payload, window_row),
            )
        )
    return {
        "rows": rows,
        "points_without_verdict": without_verdict,
        "point_id_mismatch": point_id_mismatch,
        "counts": dict(Counter(row["outcome"] for row in rows)),
    }


def writable(row: dict[str, Any]) -> bool:
    """True when the row carries a payload change."""
    return bool(row["updates"]) and row["outcome"] in ("pass", "fail", "demoted_no_evidence")


def bare_flag_count(points: list[tuple[str, dict[str, Any]]]) -> int:
    """Points claiming a verified speaker with no recorded method (the 732)."""
    return sum(
        1
        for _id, payload in points
        if payload.get("record_type") in (None, "retrieval_child")
        and payload.get("speaker_verified") is True
        and not str(payload.get("voice_verification_method") or "").strip()
    )


def sample_diffs(
    points: list[tuple[str, dict[str, Any]]],
    rows: list[dict[str, Any]],
    count: int = SAMPLE_DIFF_COUNT,
) -> list[dict[str, Any]]:
    """A seeded, reproducible sample of before/after diffs for the dry-run report."""
    by_id = {point_id: payload for point_id, payload in points}
    candidates = sorted((row for row in rows if writable(row)), key=lambda r: r["point_id"])
    chosen = random.Random(f"{SAMPLE_SEED}:diffs").sample(candidates, min(count, len(candidates)))
    return [
        {
            "point_id": row["point_id"],
            "span_id": row["span_id"],
            "outcome": row["outcome"],
            "before": {key: by_id[row["point_id"]].get(key) for key in row["updates"]},
            "after": row["updates"],
        }
        for row in chosen
    ]


def apply_row(
    write,
    qdrant_url: str,
    collection: str,
    row: dict[str, Any],
    payload: dict[str, Any],
) -> None:
    """Write one planned row, after the allowlist and the shared write rule agree.

    This is the write-time check (P2) for the backfill's ``set_payload`` path. It repeats
    the planning check on purpose: whatever produced ``row``, nothing reaches Qdrant that
    the rule refuses.
    """
    violation = allowed_key_violation(row["updates"])
    if violation is not None:
        raise ValueError(f"refusing to write non-allowlisted key {violation!r}")
    assert_speaker_write_allowed({**payload, **row["updates"]})
    write(qdrant_url, collection, row["point_id"], row["updates"])


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
        if not writable(row):
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


def _refuse(message: str, *, status: str = "refused") -> int:
    print(
        json.dumps(
            {
                "schema": REPORT_SCHEMA,
                "script_version": SCRIPT_VERSION,
                "status": status,
                "error": message,
            },
            sort_keys=True,
        ),
        file=sys.stderr,
    )
    return EXIT_INVALID_INPUT


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
    parser.add_argument(
        "--before-out",
        default=None,
        help="REQUIRED with --apply: JSONL export of every point's payload before any write.",
    )
    parser.add_argument(
        "--expect-count",
        type=int,
        default=None,
        help="Refuse (dry run and apply) unless exactly this many points currently claim a "
        "verified speaker with no recorded method. The plan expects 732.",
    )
    parser.add_argument(
        "--demote-no-evidence",
        action="store_true",
        help="Set speaker_verified=false / pending_voice_check on spans that violate the write "
        "rule and have no usable evidence. Changes what is served; needs the owner's decision.",
    )
    parser.add_argument(
        "--verified-at",
        default=None,
        help="UTC timestamp recorded as voice_verified_at (default: now). For reproducible runs.",
    )
    parser.add_argument("--report", default=None, help="Report JSON (dry run and apply).")
    args = parser.parse_args(argv)

    if args.apply and not str(args.snapshot).strip():
        return _refuse(
            "--apply requires --snapshot <name>: take a snapshot of the collection in "
            "the same session first, and get the owner's explicit OK. Nothing was written."
        )

    try:
        verdicts = _load_rows(Path(args.verdicts_jsonl))
        windows = _load_rows(Path(args.windows_jsonl)) if args.windows_jsonl else {}
    except ValueError as exc:
        return _refuse(str(exc), status="invalid_input")

    now = args.verified_at or dt.datetime.now(dt.UTC).isoformat(timespec="seconds")
    try:
        points = list(_scroll(args.qdrant_url, args.collection))
        planned = plan(
            points, verdicts, windows, now=now, demote_no_evidence=args.demote_no_evidence
        )
    except ValueError as exc:
        return _refuse(str(exc), status="invalid_input")

    bare = bare_flag_count(points)
    if args.expect_count is not None and bare != args.expect_count:
        return _refuse(
            f"--expect-count {args.expect_count} but {bare} point(s) currently claim a verified "
            "speaker with no recorded method. The collection is not the one this plan was made "
            "for. Nothing was written.",
            status="count_mismatch",
        )

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
        "points_claiming_verified_without_method_before": bare,
        "expect_count": args.expect_count,
        "demote_no_evidence": bool(args.demote_no_evidence),
        "points_without_verdict": planned["points_without_verdict"],
        "point_id_mismatch": planned["point_id_mismatch"],
        "outcomes": counts,
        "written": 0,
        "snapshot": str(args.snapshot) if args.apply else None,
        "listen_queue": _listen_queue(rows),
        "sample_diffs": sample_diffs(points, rows),
        "rows": rows,
    }

    def _summary() -> str:
        return json.dumps(
            {k: v for k, v in report.items() if k != "rows"}, indent=2, sort_keys=True
        )

    if not args.apply:
        report["mutations"] = {"qdrant_writes": 0}
        if args.report:
            _write_json(args.report, report)
        print(_summary())
        print("\nDRY RUN — zero writes performed. Re-run with --apply --snapshot <name> to write.")
        return EXIT_OK

    if not args.rollback_out or not args.before_out:
        return _refuse(
            "--apply requires --rollback-out and --before-out: no write happens without a saved "
            "old value for every touched key and a full export of the collection before it. "
            "Nothing was written."
        )

    report["before_export"] = export_before(args.before_out, points)
    rollback = _rollback_payload(points, rows, args.collection, str(args.snapshot))
    _write_json(args.rollback_out, rollback)

    sample_ids = vector_sample_ids(rows)
    vectors_before = _fetch_vectors(args.qdrant_url, args.collection, sample_ids)

    payload_by_id = {point_id: payload for point_id, payload in points}
    written = 0
    failed: list[dict[str, Any]] = []
    for row in rows:
        if not writable(row):
            continue
        try:
            apply_row(
                _set_payload,
                args.qdrant_url,
                args.collection,
                row,
                payload_by_id.get(row["point_id"], {}),
            )
        except SpeakerWriteRefused as exc:
            failed.append({"span_id": row["span_id"], "error": f"write_rule_refused: {exc}"})
            continue
        except Exception as exc:  # noqa: BLE001 - one failed point must not hide the rest
            failed.append({"span_id": row["span_id"], "error": str(exc)})
            continue
        written += 1

    after = list(_scroll(args.qdrant_url, args.collection))
    vectors_after = _fetch_vectors(args.qdrant_url, args.collection, sample_ids)
    report["post_checks"] = post_checks(points, after, vectors_before, vectors_after)
    report["written"] = written
    report["failed"] = failed
    report["rollback_path"] = str(Path(args.rollback_out).resolve())
    report["mutations"] = {"qdrant_writes": written}
    if args.report:
        _write_json(args.report, report)
    print(_summary())
    if failed:
        print(
            f"\nINCOMPLETE: {len(failed)} point(s) failed to write. Rollback: {args.rollback_out}"
        )
        return EXIT_WRITE_FAILED
    if not report["post_checks"]["all_ok"]:
        bad = [name for name, c in report["post_checks"]["checks"].items() if not c["ok"]]
        print(
            f"\nPOST-CHECK FAILED ({', '.join(bad)}) after {written} write(s). Do not promote this "
            f"collection. Rollback: {args.rollback_out} or restore snapshot {args.snapshot}."
        )
        return EXIT_WRITE_FAILED
    print(f"\nAPPLIED {written} point(s); all post-checks passed. Rollback: {args.rollback_out}")
    return EXIT_OK


def _write_json(path: str, payload: Any) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    sys.exit(main())
