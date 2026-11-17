"""In-ingest windowed-ECAPA speaker gate.

Why this exists
---------------
The windowed verifier (``ingest/verbatim/windowed_speaker_verify.py``) was built for
offline corpus rebuilds. Every served clip must carry ``speaker_verified=true`` **only**
with complete stored evidence (``AGENTS.md`` invariant 23 / ``domain.speaker_provenance``),
so the moment a new video enters the corpus through the live API — a YouTube URL or a
file upload — that path needs the same gate. Without this module the upload path stamped
``speaker: "Unknown"`` and no voice evidence at all, and the YouTube path left every new
span ``pending_voice_check`` forever.

Contract
--------
* **Fail-closed.** Any missing dependency (no WAV, no calibration, no references, no
  ECAPA model, an import error) returns :func:`pending_voice_fields` — never a
  ``speaker_verified=True`` claim.
* **Only attributed speech is gated.** A compound label (``"Sri Preethaji & Sri
  Krishnaji"``) has no single expected voice, so it is *not applicable* and returns ``{}``
  (the keys stay absent, which reads as "never checked"). Only the two registry teachers
  (``preethaji`` / ``krishnaji``) are gated.
* **One model load per process.** The SpeechBrain ECAPA model is loaded on first use and
  reused; ingestion is a long-running job and a per-span load would dominate the runtime.
* **Never raises into ingestion.** A gate failure must not abort an ingest; it must
  refuse the claim. Every public function catches and records.
* **It reports its own state at boot** (``AGENTS.md`` X41): :func:`log_status` says whether
  the gate is armed, in its own units, and whose limit stopped it.

Not the same thing as ``services/first_person_video_decisions.py``: that records a human
decision per video. This gate produces *machine* evidence per span.
"""

from __future__ import annotations

import logging
import os
import threading
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_verifier: Any = None
_verifier_error: Optional[str] = None
_init_attempts = 0

#: Speaker labels we can attribute to exactly one registry teacher. ``teacher_code``
#: normalises "Sri Krishnaji" / "krishnaji" / "sri_krishnaji"; a compound label
#: intentionally resolves to None and is never voice-gated.
_GATEABLE_GURUS = frozenset({"preethaji", "krishnaji"})


# ---------------------------------------------------------------------------
# Configuration (read through getattr so this module imports on a fresh checkout)
# ---------------------------------------------------------------------------

def _settings():
    from app.config import settings

    return settings


def enabled() -> bool:
    cfg = _settings()
    return bool(getattr(cfg, "speaker_gate_enabled", False))


def _references_path() -> Optional[Path]:
    cfg = _settings()
    raw = str(getattr(cfg, "speaker_gate_references_path", "") or "")
    if raw:
        return Path(os.path.expanduser(raw))
    bundled = Path(__file__).resolve().parents[1] / "config" / "ecapa_guru_references.npz"
    if bundled.is_file():
        return bundled
    default = (
        Path(os.path.expanduser("~/mukthiguru_attribution_data"))
        / "phase2_references_2026-10-30"
        / "references.npz"
    )
    return default if default.is_file() else None


def _calibration_path() -> Optional[Path]:
    cfg = _settings()
    raw = str(getattr(cfg, "speaker_gate_calibration_path", "") or "")
    if raw:
        return Path(os.path.expanduser(raw))
    bundled = Path(__file__).resolve().parents[1] / "config" / "windowed_ecapa_calibration.json"
    return bundled if bundled.is_file() else None


def _model_cache() -> Optional[Path]:
    cfg = _settings()
    raw = str(getattr(cfg, "speaker_gate_model_cache", "") or "")
    return Path(os.path.expanduser(raw)) if raw else None


def audio_dir() -> Optional[Path]:
    """Archived ``<video_id>.wav`` directory, when one is configured and exists."""
    cfg = _settings()
    raw = str(getattr(cfg, "speaker_gate_audio_dir", "") or "")
    if raw:
        path = Path(os.path.expanduser(raw))
        return path if path.is_dir() else None
    default = Path(os.path.expanduser("~/mukthiguru_attribution_data/audio_archive/wavs"))
    return default if default.is_dir() else None


def max_spans_per_source() -> int:
    cfg = _settings()
    try:
        return max(0, int(getattr(cfg, "speaker_gate_max_spans_per_source", 60)))
    except Exception:
        return 60


# ---------------------------------------------------------------------------
# Verifier lifecycle
# ---------------------------------------------------------------------------

def guru_for_speaker(*names: Any) -> Optional[str]:
    """Registry teacher id for a speaker label, or None when it is not gateable.

    A label that names both teachers at once has no single expected voice: the real
    speaker inside a span may be either, so verifying against one reference would
    fabricate evidence. Returns None there.
    """
    from domain.speaker_provenance import teacher_code

    code = teacher_code(*names)
    return code if code in _GATEABLE_GURUS else None


def _build_verifier():
    """Construct the windowed verifier. Raises on missing dependency."""
    from ingest.verbatim.windowed_speaker_verify import WindowedEcapaVerifier

    refs = _references_path()
    cal = _calibration_path()
    if refs is None:
        raise FileNotFoundError(
            "ECAPA references not found; set SPEAKER_GATE_REFERENCES_PATH or place "
            "references.npz under ~/mukthiguru_attribution_data/phase2_references_2026-10-30/"
        )
    if cal is None:
        raise FileNotFoundError(
            "windowed ECAPA calibration not found; set SPEAKER_GATE_CALIBRATION_PATH or "
            "WINDOWED_ECAPA_CALIBRATION_PATH"
        )
    return WindowedEcapaVerifier(
        references_path=refs,
        calibration_path=cal,
        audio_dir=None,  # ingestion always passes an explicit WAV
        model_cache=_model_cache(),
    )


def get_verifier() -> Any:
    """Return the process-wide verifier, or None when it cannot be built."""
    global _verifier, _verifier_error, _init_attempts
    if _verifier is not None:
        return _verifier
    with _lock:
        if _verifier is not None:
            return _verifier
        _init_attempts += 1
        try:
            _verifier = _build_verifier()
            _verifier_error = None
            logger.info(
                "speaker gate: windowed ECAPA verifier armed (calibration=%s)",
                _calibration_path(),
            )
        except Exception as exc:
            _verifier_error = f"{type(exc).__name__}: {exc}"
            logger.warning(
                "speaker gate: verifier unavailable (%s); new spans will be stamped "
                "pending_voice_check, never verified",
                _verifier_error,
            )
            return None
    return _verifier


def reset_for_tests() -> None:
    """Drop the cached verifier so a test can inject its own."""
    global _verifier, _verifier_error, _init_attempts
    with _lock:
        _verifier = None
        _verifier_error = None
        _init_attempts = 0


def set_verifier_for_tests(verifier: Any) -> None:
    """Install a stub verifier (tests only)."""
    global _verifier, _verifier_error
    with _lock:
        _verifier = verifier
        _verifier_error = None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def status() -> dict[str, Any]:
    """Machine-readable gate state, in the gate's own units.

    ``state`` is one of ``off`` / ``missing_references`` / ``missing_calibration`` /
    ``verifier_error`` / ``ready``. Nothing here is inferred from a serving flag: it
    reports what this process will actually do.
    """
    if not enabled():
        return {
            "state": "off",
            "enabled": False,
            "reason": "speaker_gate_enabled is false",
            "calibration_path": None,
            "references_path": None,
            "max_spans_per_source": max_spans_per_source(),
        }
    refs = _references_path()
    cal = _calibration_path()
    if refs is None:
        state, reason = "missing_references", "ECAPA references.npz not found"
    elif cal is None:
        state, reason = "missing_calibration", "windowed ECAPA calibration not found"
    elif _verifier is not None:
        state, reason = "ready", "verifier armed"
    elif _verifier_error:
        state, reason = "verifier_error", _verifier_error
    else:
        state, reason = "ready", "verifier loads on first scored span"
    return {
        "state": state,
        "enabled": True,
        "reason": reason,
        "calibration_path": str(cal) if cal else None,
        "references_path": str(refs) if refs else None,
        "max_spans_per_source": max_spans_per_source(),
    }


def log_status(log: logging.Logger | None = None, settings: Any = None) -> dict[str, Any]:
    """Log the gate state once at startup and return it.

    ``settings`` is accepted (and ignored) so the boot wiring matches
    ``app.runtime_budget.log_budget_headroom(logger, settings)``.
    """
    state = status()
    log = log or logger
    if state["state"] == "ready":
        log.info(
            "speaker gate: ARMED — windowed ECAPA v1 will verify teacher-attributed spans "
            "at ingest (calibration=%s, max %d spans/source)",
            state["calibration_path"],
            state["max_spans_per_source"],
        )
    else:
        log.warning(
            "speaker gate: DISARMED (%s) — %s. New spans are stamped "
            "pending_voice_check and are never marked verified.",
            state["state"],
            state["reason"],
        )
    return state


def pending_fields() -> dict[str, Any]:
    from domain.speaker_provenance import pending_voice_fields

    return pending_voice_fields()


def verify(
    *,
    audio_path: str | Path | None,
    start_ms: float | None,
    end_ms: float | None,
    speaker: str | None,
    video_id: str | None = None,
) -> dict[str, Any]:
    """Voice payload fields for one ingest chunk.

    Returns
    -------
    ``{}``
        Not applicable: gate disabled, or the label does not name exactly one
        registry teacher. No voice keys are added, so the payload says "never
        checked" rather than "checked and refused".
    ``pending_voice_fields()``
        Gate armed and applicable, but no verdict could be produced (missing audio,
        unknown bounds, model unavailable, no non-silent window). Never verified.
    ``automated_voice_fields(...)``
        A real verdict: ``speaker_verified=True`` with full provenance on a pass, or
        ``speaker_verified=False`` / ``ecapa_failed`` with the score recorded on a
        refusal.
    """
    if not enabled():
        return {}
    guru = guru_for_speaker(speaker)
    if guru is None:
        return {}
    if audio_path is None or start_ms is None or end_ms is None:
        return pending_fields()
    if float(end_ms) <= float(start_ms):
        return pending_fields()

    verifier = get_verifier()
    if verifier is None:
        return pending_fields()

    try:
        fields = verifier.verify_audio_file(audio_path, start_ms, end_ms, guru)
    except Exception as exc:  # verify_audio_file already swallows; belt and braces
        logger.warning(
            "speaker gate: verification raised for %s [%s-%s] (%s); stamping pending",
            video_id or Path(str(audio_path)).name, start_ms, end_ms, exc,
        )
        return pending_fields()

    from domain.speaker_provenance import speaker_write_violations

    if fields.get("speaker_verified") is True and speaker_write_violations(fields):
        # Defence in depth: a claim the write rule would refuse must never be carried
        # into a payload by this path.
        logger.error(
            "speaker gate: verifier returned an invalid verified record for %s [%s-%s]; "
            "demoting to pending",
            video_id or Path(str(audio_path)).name, start_ms, end_ms,
        )
        return pending_fields()
    return fields


def annotate_chunks(
    *,
    chunks: list[str],
    starts: list[float | None] | None,
    ends: list[float | None] | None,
    speakers: list[str | None] | None,
    audio_path: str | Path | None,
    video_id: str | None = None,
    source_url: str = "",
) -> list[dict[str, Any]]:
    """Voice fields per chunk, parallel to ``chunks``.

    Cost-bounded: only the first ``speaker_gate_max_spans_per_source`` gateable chunks
    are scored; the rest are stamped ``pending_voice_check`` with the reason recorded, so
    a 10-hour upload cannot turn ingestion into an hour of ECAPA work while still never
    claiming an unverified speaker. A chunk with no timing keeps pending fields, never a
    guess (a timestamp on the wrong chunk is a misattribution defect).
    """
    out: list[dict[str, Any]] = []
    if not enabled():
        return out
    limit = max_spans_per_source()
    scored = 0
    for index, _chunk in enumerate(chunks):
        speaker = speakers[index] if speakers and index < len(speakers) else None
        start = starts[index] if starts and index < len(starts) else None
        end = ends[index] if ends and index < len(ends) else None
        if guru_for_speaker(speaker) is None:
            out.append({})  # not applicable: no single expected voice
            continue
        if scored >= limit:
            out.append(pending_fields())
            continue
        scored += 1
        out.append(
            verify(
                audio_path=audio_path,
                start_ms=start,
                end_ms=end,
                speaker=speaker,
                video_id=video_id,
            )
        )
    if scored >= limit and limit > 0:
        logger.warning(
            "speaker gate: capped at %d verified spans for %s — remaining teacher-attributed "
            "chunks are stamped pending_voice_check",
            limit,
            source_url or video_id or audio_path,
        )
    return out


__all__ = [
    "annotate_chunks",
    "audio_dir",
    "enabled",
    "get_verifier",
    "guru_for_speaker",
    "log_status",
    "max_spans_per_source",
    "pending_fields",
    "reset_for_tests",
    "set_verifier_for_tests",
    "status",
    "verify",
]
