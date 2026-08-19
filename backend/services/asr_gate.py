"""ASR gate — reject degenerate transcripts BEFORE the LLM corrector (§6.1).

The corrector cannot be trusted to clean a decoder loop; it writes prose about
it instead. This module rejects at the transcript stage using controls that
cost nothing:

  * Decode-level (faster-whisper / whisperx kwargs): ``vad_filter``,
    ``repetition_penalty``, ``compression_ratio_threshold``.
  * Segment-level: ``avg_logprob`` / ``no_speech_prob`` floors (per-segment
    confidence — low-confidence segments are where invention happens).
  * Transcript-level backstop: the 5-gram × ≥4 repetition-loop detector from
    ``services.text_quality_filter`` (reused — one detector, one contract).

The module is deliberately thin: every value comes from ``settings`` so the
gate can be tuned without code changes, and every helper has a runnable
self-check.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Faster-whisper transcribe kwargs that suppress degenerate output at decode time.
# Only passed through when the backend accepts them (whisperx/faster-whisper);
# the MLX fallback path ignores unknown kwargs via explicit allow-list.
_DECODE_KWARG_NAMES = (
    "vad_filter",
    "repetition_penalty",
    "compression_ratio_threshold",
)


def asr_decode_kwargs(backend: str = "faster-whisper") -> dict[str, Any]:
    """Build decode-level kwargs from settings. Empty when gate disabled.

    ``backend`` filters kwargs the target does not accept: ``vad_filter`` is
    faster-whisper/whisperx-only; mlx-whisper would raise on it.
    """
    from app.config import settings

    if not getattr(settings, "asr_gate_enabled", True):
        return {}
    kwargs: dict[str, Any] = {}
    if backend in ("faster-whisper", "whisperx") and getattr(settings, "asr_vad_filter", False):
        kwargs["vad_filter"] = True
    repetition_penalty = getattr(settings, "asr_repetition_penalty", 1.0)
    if repetition_penalty and repetition_penalty != 1.0:
        kwargs["repetition_penalty"] = repetition_penalty
    compression_ratio = getattr(settings, "asr_compression_ratio_threshold", None)
    if compression_ratio:
        kwargs["compression_ratio_threshold"] = compression_ratio
    return kwargs


def is_low_confidence_segment(segment: dict[str, Any]) -> bool:
    """True when a segment fails the confidence floors (missing values pass).

    Uses per-segment ``avg_logprob`` / ``no_speech_prob`` from whisperx/faster-
    whisper output when present. Segments without these fields (MLX text-only
    path) are never rejected here — the transcript-level backstop covers them.
    """
    from app.config import settings

    if not getattr(settings, "asr_gate_enabled", True):
        return False
    avg_logprob = segment.get("avg_logprob")
    if avg_logprob is not None:
        floor = getattr(settings, "asr_avg_logprob_floor", None)
        if floor is not None and avg_logprob < floor:
            return True
    no_speech_prob = segment.get("no_speech_prob")
    if no_speech_prob is not None:
        ceiling = getattr(settings, "asr_no_speech_prob_ceiling", None)
        if ceiling is not None and no_speech_prob > ceiling:
            return True
    return False


def filter_low_confidence_segments(
    segments: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], int]:
    """Drop low-confidence segments. Returns (kept, dropped_count)."""
    kept: list[dict[str, Any]] = []
    dropped = 0
    for seg in segments:
        if is_low_confidence_segment(seg):
            dropped += 1
            continue
        kept.append(seg)
    return kept, dropped


def reject_transcript(text: str) -> Optional[str]:
    """Return a rejection reason for a degenerate transcript, else None.

    Backstop for whatever the decode-level controls miss. Uses the same
    5-gram loop detector as the chunk-level gate (one detector, one contract).
    """
    if not text or len(text.strip()) < 50:
        return None
    from services.text_quality_filter import has_repetition_loop

    loop = has_repetition_loop(text)
    if loop:
        return f"asr_repetition_loop:{loop}"
    return None


if __name__ == "__main__":  # runnable self-check
    from services.text_quality_filter import _LOOP_MIN_REPEATS, _LOOP_NGRAM

    assert _LOOP_NGRAM == 5 and _LOOP_MIN_REPEATS == 4, "loop detector contract changed"

    # Backstop catches the "Each"×N class outright
    loop_text = " ".join(["Each"] * 20) + " gentle breath settles the mind."
    reason = reject_transcript(loop_text)
    assert reason and reason.startswith("asr_repetition_loop"), reason

    clean_text = (
        "In a beautiful state, you are powerful enough to help yourself "
        "and help others around you. That is the gift of presence."
    )
    assert reject_transcript(clean_text) is None

    # Segment confidence floors — enable explicitly (defaults are None/disabled)
    from app.config import settings

    settings.asr_avg_logprob_floor = -1.0
    settings.asr_no_speech_prob_ceiling = 0.6
    assert is_low_confidence_segment({"avg_logprob": -3.5, "no_speech_prob": 0.05})
    assert is_low_confidence_segment({"avg_logprob": -0.2, "no_speech_prob": 0.95})
    assert not is_low_confidence_segment({"avg_logprob": -0.2, "no_speech_prob": 0.05})
    kept, dropped = filter_low_confidence_segments(
        [
            {"text": "good", "avg_logprob": -0.1, "no_speech_prob": 0.01},
            {"text": "bad", "avg_logprob": -4.0, "no_speech_prob": 0.5},
        ]
    )
    assert dropped == 1 and len(kept) == 1, (kept, dropped)

    print("asr_gate self-check OK")
