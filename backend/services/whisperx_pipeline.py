"""
Mukthi Guru — WhisperX Pipeline (word-level alignment + speaker diarization)

Modeled on external_repos/zabt-ai/zabt-gpu-worker/src/pipeline.py but adapted
for this codebase. Uses the `whisperx` library (faster-whisper under the hood)
to produce:
  - word-level timestamps via phoneme alignment
  - speaker labels via pyannote 3.1 (gated HF model — needs hf_token)

Graceful degradation:
  - no whisperx / torch installed  → return None (caller falls back to MLX Whisper)
  - no hf_token                    → skip diarization, still align (SPEAKER_UNKNOWN)
  - no CUDA                       → run on CPU int8 (slow but works)

Usage:
  from services.whisperx_pipeline import transcribe_with_alignment

  result = transcribe_with_alignment(video_id, audio_path, hf_token=os.getenv("HF_TOKEN"))
  if result is None:
      # fall back to MLX whisper
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Device / compute-type resolution
# ---------------------------------------------------------------------------

def _resolve_device(device: str) -> str:
    """Resolve 'auto' → 'cuda' if available else 'cpu'."""
    if device != "auto":
        return device
    try:
        import torch

        if torch.cuda.is_available():
            return "cuda"
        if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
            # WhisperX/pyannote are not reliably MPS-compatible — stay on CPU for safety.
            logger.info("MPS available but WhisperX CUDA-only — using CPU")
            return "cpu"
    except ImportError:
        logger.warning("torch not installed — cannot resolve cuda; using cpu")
    return "cpu"


def _resolve_compute_type(compute_type: str, device: str) -> str:
    """Resolve 'auto' → float16 (cuda) / int8 (cpu)."""
    if compute_type != "auto":
        return compute_type
    return "float16" if device == "cuda" else "int8"


# ---------------------------------------------------------------------------
# Language resolution (mirrors zabt _resolve_language_after_detect)
# ---------------------------------------------------------------------------

def _resolve_language(
    detected: str,
    forced: Optional[str],
    allowed: Optional[set[str]],
) -> tuple[str, bool]:
    """Pick the language to use after a first-pass detection.

    Returns (language_code, was_forced_retranscribe_needed).
    """
    if forced and not allowed:
        return forced, forced != detected
    if not allowed:
        return detected, False
    if detected in allowed:
        return detected, False
    if forced:
        return forced, True
    return detected, False


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def transcribe_with_alignment(
    video_id: str,
    audio_path: str,
    *,
    language: Optional[str] = None,
    allowed_languages: Optional[set[str]] = None,
    whisper_model_name: str = "large-v3",
    device: str = "auto",
    compute_type: str = "auto",
    batch_size: int = 16,
    min_speakers: int = 1,
    max_speakers: int = 10,
    hf_token: Optional[str] = None,
    diarization_model_name: str = "pyannote/speaker-diarization-3.1",
) -> Optional[dict]:
    """
    Full WhisperX pipeline: transcribe → align → diarize.

    Returns dict:
        {
            "text": str,                    # speaker-tagged transcript
            "segments": list[dict],         # [{start, end, text, speaker, words: [...]}]
            "language": str,
            "method": "whisperx_aligned_diarized" | "whisperx_aligned",
        }
    or None on failure (caller should fall back to MLX Whisper).
    """
    try:
        import torch  # noqa: F401
        import whisperx
    except ImportError as e:
        logger.warning(
            f"[{video_id}] whisperx/torch not installed ({e}) — "
            f"cannot run alignment pipeline"
        )
        return None

    if not os.path.exists(audio_path):
        logger.error(f"[{video_id}] Audio file not found: {audio_path}")
        return None

    device = _resolve_device(device)
    compute_type = _resolve_compute_type(compute_type, device)

    size_mb = os.path.getsize(audio_path) / (1024 * 1024)
    logger.info(
        f"[{video_id}] WhisperX pipeline start: {size_mb:.1f}MB audio, "
        f"model={whisper_model_name}, device={device}, compute={compute_type}"
    )
    t0 = time.time()

    # --- Stage 1: Transcribe ------------------------------------------------
    try:
        logger.info(f"[{video_id}] Loading WhisperX model...")
        tl = time.time()
        whisper_model = whisperx.load_model(
            whisper_model_name, device=device, compute_type=compute_type
        )
        logger.info(f"[{video_id}]   model loaded in {time.time() - tl:.1f}s")

        tl = time.time()
        transcribe_kwargs: dict[str, Any] = {"batch_size": batch_size, "print_progress": True}
        if language:
            transcribe_kwargs["language"] = language
        raw_result = whisper_model.transcribe(audio_path, **transcribe_kwargs)

        detected = raw_result.get("language", "en")
        resolved_lang, needs_retranscribe = _resolve_language(
            detected=detected, forced=language, allowed=allowed_languages
        )

        if needs_retranscribe and resolved_lang != detected:
            logger.info(
                f"[{video_id}] Detected '{detected}' outside allowed set "
                f"{allowed_languages} — re-transcribing forced as '{resolved_lang}'"
            )
            raw_result = whisper_model.transcribe(
                audio_path,
                batch_size=batch_size,
                print_progress=True,
                language=resolved_lang,
            )

        logger.info(
            f"[{video_id}] Transcription done in {time.time() - tl:.1f}s "
            f"({len(raw_result.get('segments', []))} segments, lang={resolved_lang})"
        )
    except Exception as e:
        logger.error(f"[{video_id}] WhisperX transcription failed: {e}")
        return None

    # Free transcribe model VRAM before alignment (zabt pipeline.py:124-126)
    del whisper_model
    if device == "cuda":
        try:
            import torch

            torch.cuda.empty_cache()
        except Exception:
            pass

    # --- Stage 2: Align (word-level timestamps) -----------------------------
    try:
        logger.info(f"[{video_id}] Aligning word timestamps...")
        tl = time.time()
        align_model, align_metadata = whisperx.load_align_model(
            language_code=resolved_lang, device=device
        )
        raw_result = whisperx.align(
            raw_result["segments"],
            align_model,
            align_metadata,
            audio_path,
            device,
            return_char_alignments=False,
        )
        logger.info(f"[{video_id}]   alignment done in {time.time() - tl:.1f}s")
    except Exception as e:
        logger.error(f"[{video_id}] WhisperX alignment failed: {e}")
        return None
    finally:
        try:
            del align_model
            if device == "cuda":
                import torch

                torch.cuda.empty_cache()
        except Exception:
            pass

    # --- Stage 3: Diarize (speaker labels) ----------------------------------
    method = "whisperx_aligned"
    if not hf_token:
        logger.warning(
            f"[{video_id}] No hf_token — skipping diarization (SPEAKER_UNKNOWN)"
        )
        for seg in raw_result.get("segments", []):
            seg["speaker"] = "SPEAKER_UNKNOWN"
            for w in seg.get("words", []):
                w["speaker"] = "SPEAKER_UNKNOWN"
    else:
        try:
            logger.info(f"[{video_id}] Diarizing speakers (min={min_speakers}, max={max_speakers})...")
            tl = time.time()
            from whisperx.diarize import DiarizationPipeline, assign_word_speakers

            diarize_model = DiarizationPipeline(
                model_name=diarization_model_name,
                token=hf_token,
                device=device,
            )
            audio = whisperx.load_audio(audio_path)
            diarize_segments = diarize_model(
                audio,
                min_speakers=min_speakers,
                max_speakers=max_speakers,
            )
            raw_result = assign_word_speakers(diarize_segments, raw_result)
            method = "whisperx_aligned_diarized"
            logger.info(f"[{video_id}]   diarization done in {time.time() - tl:.1f}s")

            del diarize_model
            if device == "cuda":
                import torch

                torch.cuda.empty_cache()
        except Exception as e:
            logger.warning(
                f"[{video_id}] Diarization failed ({e}) — "
                f"continuing with SPEAKER_UNKNOWN"
            )
            for seg in raw_result.get("segments", []):
                seg.setdefault("speaker", "SPEAKER_UNKNOWN")
                for w in seg.get("words", []):
                    w.setdefault("speaker", "SPEAKER_UNKNOWN")

    # --- Format output ------------------------------------------------------
    segments_out: list[dict] = []
    text_parts: list[str] = []
    for seg in raw_result.get("segments", []):
        text = (seg.get("text") or "").strip()
        speaker = seg.get("speaker", "SPEAKER_UNKNOWN")
        start = float(seg.get("start", 0.0))
        end = float(seg.get("end", 0.0))
        words = [
            {
                "word": w.get("word", ""),
                "start": float(w.get("start", 0.0)),
                "end": float(w.get("end", 0.0)),
                "speaker": w.get("speaker", speaker),
            }
            for w in seg.get("words", [])
        ]
        segments_out.append(
            {"start": start, "end": end, "text": text, "speaker": speaker, "words": words}
        )
        if text:
            text_parts.append(f"[{speaker}] {text}")

    full_text = "\n".join(text_parts)

    logger.info(
        f"[{video_id}] WhisperX pipeline complete in {time.time() - t0:.1f}s "
        f"(method={method}, {len(segments_out)} segments, {len(full_text)} chars)"
    )

    return {
        "text": full_text,
        "segments": segments_out,
        "language": resolved_lang,
        "method": method,
    }


# ---------------------------------------------------------------------------
# Self-check
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # Verify device resolution logic without needing torch/whisperx installed.
    assert _resolve_device("cpu") == "cpu"
    assert _resolve_device("cuda") == "cuda"
    assert _resolve_compute_type("int8", "cpu") == "int8"
    assert _resolve_compute_type("float16", "cuda") == "float16"
    assert _resolve_compute_type("auto", "cpu") == "int8"
    assert _resolve_compute_type("auto", "cuda") == "float16"

    # Language resolution
    assert _resolve_language("en", None, None) == ("en", False)
    assert _resolve_language("hi", "en", None) == ("en", True)
    assert _resolve_language("en", None, {"en", "hi"}) == ("en", False)
    assert _resolve_language("fr", None, {"en", "hi"}) == ("fr", False)
    assert _resolve_language("fr", "en", {"en", "hi"}) == ("en", True)

    print("whisperx_pipeline self-check OK")