"""Speaker-verification provenance and the write-time rule that enforces it.

Why this module exists
----------------------
732 live ``first_person_v10`` spans were written ``speaker_verified=true`` with no
record of what produced the claim. A boolean is not evidence. This module names
the evidence keys (P1) and the refusal rule (P2) in one dependency-free place so
the store, the builders and the backfill writer all enforce the same thing.

Stdlib only, on purpose: ``scripts/ops/backfill_v10_voice_method.py`` runs on the
host with ``requests`` and no pydantic, and must be able to import this.

What the rule does and does not do
----------------------------------
* It works on raw payload dicts (the shape Qdrant stores), not on ``SourceSpan``.
* It is a **write-time** rule. It is not a model validator, because the harness
  reads live payloads into ``SourceSpan`` and the 732 spans in the live
  collection must stay readable until the backfill has run.
* It checks that the record is *complete and self-consistent*. It cannot check
  that the audio really scored that cosine; the backfill's post-checks and the
  P6 random audit cover that.
* It never lists a voice score as a "pass" on its own: a score below the
  threshold recorded next to it is refused.
"""

from __future__ import annotations

import hashlib
import math
import re
from collections.abc import Mapping
from typing import Any

#: ECAPA scored the exact served window (``start_ms-250`` to ``end_ms+250``)
#: against the pinned calibration. Needs the full provenance set below.
METHOD_ECAPA_SPAN_SLICE_V2 = "ecapa_voxceleb_span_slice_v2"
#: Legacy centroid verdict. Kept so spans written before the provenance fields
#: existed stay writable; it is **not** accepted as a new full-provenance method.
METHOD_ECAPA_CENTROID_V1 = "ecapa_voxceleb_centroid_v1"
#: A person listened to the served window. Never merged into an automated method.
METHOD_HUMAN_LISTEN_V1 = "human_listen_v1"

KNOWN_METHODS = frozenset(
    {METHOD_ECAPA_SPAN_SLICE_V2, METHOD_ECAPA_CENTROID_V1, METHOD_HUMAN_LISTEN_V1}
)

STATUS_VERIFIED = "verified"
STATUS_ECAPA_FAILED = "ecapa_failed"
STATUS_PENDING_VOICE_CHECK = "pending_voice_check"
STATUS_PENDING_LISTEN = "pending_listen"
SPEAKER_VERIFICATION_STATUSES = (
    STATUS_VERIFIED,
    STATUS_ECAPA_FAILED,
    STATUS_PENDING_VOICE_CHECK,
    STATUS_PENDING_LISTEN,
)

WINDOW_CHECK_PASS = "pass"
WINDOW_CHECK_FAIL = "fail"
WINDOW_CHECK_NONE = "no_diarization"
WINDOW_CHECKS = (WINDOW_CHECK_PASS, WINDOW_CHECK_FAIL, WINDOW_CHECK_NONE)

#: Blind-choice options for a human listen (nothing pre-filled in the UI).
REVIEW_CHOICES = ("sri_krishnaji", "sri_preethaji", "host_or_interviewer", "other", "unclear")

#: Flat keys written by an automated verdict (so Qdrant can filter on each).
AUTOMATED_PROVENANCE_KEYS = (
    "voice_verification_method",
    "voice_model_revision",
    "voice_score",
    "voice_margin",
    "voice_threshold_applied",
    "voice_calibration_id",
    "voice_window_check",
    "voice_verified_at",
    "speaker_verification_status",
)

#: Extra keys a human listen records. The automated backfill never writes these.
HUMAN_REVIEW_KEYS = (
    "reviewer_id",
    "reviewed_at",
    "review_guidelines_version",
    "reviewed_audio_sha256",
    "review_choice",
)

_SHA256 = re.compile(r"^[0-9a-f]{64}$")

#: Code returned when a verified span has no method. Kept as the pre-existing code so the
#: store's earlier error text and tests still match.
CODE_NO_METHOD = "speaker_verified_without_method"


def _blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _finite(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )


def _threshold(payload: Mapping[str, Any], key: str) -> float | None:
    applied = payload.get("voice_threshold_applied")
    if isinstance(applied, Mapping) and _finite(applied.get(key)):
        return float(applied[key])
    return None


def speaker_write_violations(payload: Mapping[str, Any]) -> list[str]:
    """Reasons a payload may not be written with ``speaker_verified=true``.

    Empty list means the write is allowed. A payload that does not claim a verified
    speaker is always allowed: writing ``speaker_verified=false`` is the safe direction.
    """
    if payload.get("speaker_verified") is not True:
        return []

    method = str(payload.get("voice_verification_method") or "").strip()
    if not method:
        return [CODE_NO_METHOD]
    if method not in KNOWN_METHODS:
        return [f"voice_method_unknown:{method}"]

    out: list[str] = []

    status = payload.get("speaker_verification_status")
    if not _blank(status) and status != STATUS_VERIFIED:
        out.append(f"status_contradicts_flag:{status}")

    if method == METHOD_ECAPA_SPAN_SLICE_V2:
        for key in ("voice_calibration_id", "voice_model_revision"):
            if _blank(payload.get(key)):
                out.append(f"ecapa_missing:{key}")
        score = payload.get("voice_score")
        if not _finite(score):
            out.append("ecapa_missing:voice_score")
        floor = _threshold(payload, "cosine_floor")
        if floor is None:
            # Without the threshold in force at write time the score cannot be judged.
            out.append("ecapa_missing:voice_threshold_applied")
        elif _finite(score) and float(score) < floor:
            out.append("ecapa_score_below_floor")
        margin = payload.get("voice_margin")
        margin_floor = _threshold(payload, "margin_threshold")
        if _finite(margin) and margin_floor is not None and float(margin) < margin_floor:
            out.append("ecapa_margin_below_threshold")
        if payload.get("voice_window_check") == WINDOW_CHECK_FAIL:
            out.append("window_check_failed")

    elif method == METHOD_HUMAN_LISTEN_V1:
        for key in ("reviewer_id", "reviewed_at"):
            if _blank(payload.get(key)):
                out.append(f"human_missing:{key}")
        sha = payload.get("reviewed_audio_sha256")
        if _blank(sha) or not _SHA256.match(str(sha)):
            out.append("human_missing:reviewed_audio_sha256")

    return out


class SpeakerWriteRefused(ValueError):
    """Raised when a write would claim a verified speaker without complete evidence."""

    def __init__(self, span_id: str, violations: list[str]):
        self.span_id = span_id
        self.violations = list(violations)
        super().__init__(f"{violations[0]}: {span_id} (all: {', '.join(violations)})")


def assert_speaker_write_allowed(payload: Mapping[str, Any]) -> None:
    """Raise :class:`SpeakerWriteRefused` unless :func:`speaker_write_violations` is empty."""
    violations = speaker_write_violations(payload)
    if violations:
        span_id = str(payload.get("source_span_id") or payload.get("id") or "?")
        raise SpeakerWriteRefused(span_id, violations)


# --------------------------------------------------------------------------
# Builder helpers (P3)
#
# Both corpus builders turn an ECAPA verdict into the span fields below. They share this
# code so a builder cannot write a verified span the write rule would refuse. Every helper
# returns ``SourceSpan`` keyword arguments and never raises on missing evidence: missing
# evidence yields ``speaker_verified=False`` with ``pending_voice_check``. The span is
# stored, never dropped, and it is never promoted.
# --------------------------------------------------------------------------


def pending_voice_fields() -> dict[str, Any]:
    """Span fields for a span with no usable voice verdict. Safe direction: not verified."""
    return {
        "speaker_verified": False,
        "voice_verification_method": None,
        "speaker_verification_status": STATUS_PENDING_VOICE_CHECK,
    }


def automated_voice_fields(
    *,
    verified: bool,
    evidence: Mapping[str, Any] | None,
    model_revision: str | None,
    calibration_id: str | None,
    verified_at: str | None = None,
    window_check: str | None = None,
) -> dict[str, Any]:
    """Span fields for a span scored by the span-slice ECAPA check (method v2).

    ``evidence`` keys: ``cosine``, ``margin``, ``cosine_floor``, ``margin_threshold``.

    * No score at all -> :func:`pending_voice_fields`.
    * ``verified`` and the record is complete and passes the write rule -> method v2 with
      the full provenance and status ``verified``.
    * ``verified`` but the record is incomplete (no model revision, no calibration id, no
      threshold, or a score below its own floor) -> :func:`pending_voice_fields`. The
      builder never claims what it cannot back with evidence.
    * not ``verified`` with a score -> ``speaker_verified=False``, status ``ecapa_failed``,
      the evidence recorded, and no method.
    """
    ev = evidence or {}
    if not _finite(ev.get("cosine")):
        return pending_voice_fields()

    fields: dict[str, Any] = {
        "voice_model_revision": None if _blank(model_revision) else str(model_revision),
        "voice_score": float(ev["cosine"]),
        "voice_margin": float(ev["margin"]) if _finite(ev.get("margin")) else None,
        "voice_calibration_id": None if _blank(calibration_id) else str(calibration_id),
        "voice_verified_at": None if _blank(verified_at) else str(verified_at),
        "voice_window_check": window_check,
    }
    if _finite(ev.get("cosine_floor")) and _finite(ev.get("margin_threshold")):
        fields["voice_threshold_applied"] = {
            "cosine_floor": float(ev["cosine_floor"]),
            "margin_threshold": float(ev["margin_threshold"]),
        }

    if not verified:
        fields.update(
            speaker_verified=False,
            voice_verification_method=None,
            speaker_verification_status=STATUS_ECAPA_FAILED,
        )
        return fields

    fields.update(
        speaker_verified=True,
        voice_verification_method=METHOD_ECAPA_SPAN_SLICE_V2,
        speaker_verification_status=STATUS_VERIFIED,
    )
    if speaker_write_violations(fields):
        return pending_voice_fields()
    return fields


def span_slice_voice_fields(
    *,
    verified: bool,
    scored: bool,
    cosine: float,
    margin: float,
    foreign_window_count: int,
    cosine_floor: float,
    margin_threshold: float,
    model_revision: str | None,
    calibration_id: str | None,
    verified_at: str | None,
) -> dict[str, Any]:
    """Span fields from one span-slice verdict of ``build_full_corpus_v10``.

    ``scored`` is False when no embedding exists (no audio, zero norm): the verdict's
    ``cosine=0.0`` is then a placeholder, not a score, so it must not be recorded as one.
    The window check recorded here is the builder's own sliding-window pass over the span
    (``pass`` when the span cleared, ``fail`` when a window fell below the window floor).
    """
    return automated_voice_fields(
        verified=verified,
        evidence=(
            {
                "cosine": cosine,
                "margin": margin,
                "cosine_floor": cosine_floor,
                "margin_threshold": margin_threshold,
            }
            if scored
            else None
        ),
        model_revision=model_revision,
        calibration_id=calibration_id,
        verified_at=verified_at,
        window_check=(
            WINDOW_CHECK_PASS
            if verified
            else (WINDOW_CHECK_FAIL if foreign_window_count > 0 else None)
        ),
    )


def legacy_centroid_fields(
    row: Mapping[str, Any], *, verified_at: str | None = None
) -> dict[str, Any]:
    """Span fields for a verdict row from the legacy whole-clip centroid check.

    Only the v9 carry-over builder uses this: it has no span audio to re-score, so it cannot
    produce method v2. The legacy exemption in the write rule lets such a span be written;
    the promotion gate counts them (non-blocking). Whatever evidence the row carries is kept.
    """
    fields: dict[str, Any] = {
        "speaker_verified": True,
        "voice_verification_method": METHOD_ECAPA_CENTROID_V1,
        "speaker_verification_status": STATUS_VERIFIED,
    }
    if _finite(row.get("cosine")):
        fields["voice_score"] = float(row["cosine"])
    if _finite(row.get("margin")):
        fields["voice_margin"] = float(row["margin"])
    if not _blank(verified_at):
        fields["voice_verified_at"] = str(verified_at)
    return fields


def calibration_id_from(data: Mapping[str, Any], raw: bytes) -> str:
    """Name the calibration a verdict used.

    Prefer the pinned ``calibration_revision`` the verdict script wrote. An older calibration
    file has none, so fall back to the sha256 of the file bytes: that still names exactly
    which file produced the floors, which is the point of the field.
    """
    revision = data.get("calibration_revision")
    if not _blank(revision):
        return str(revision)
    return f"file-sha256:{hashlib.sha256(raw).hexdigest()}"
