"""
Mukthi Guru — Local Whisper STT Service (Apple Silicon / MLX)

Replaces the Sarvam Cloud STT service with local Whisper large-v3-turbo
running on Apple Silicon via mlx-whisper. Zero cost, zero rate limits,
~150x realtime speed on M5.

Usage:
  from services.whisper_local_service import transcribe_with_whisper, download_audio

  audio = download_audio(video_id, "/tmp/audio")
  text = transcribe_with_whisper(video_id, audio)
"""

import logging
import os
import subprocess
from typing import Optional

from app.config import settings

logger = logging.getLogger(__name__)


def download_audio(video_id: str, output_dir: str) -> Optional[str]:
    """
    Download YouTube audio as mono 16kHz MP3 using yt-dlp.
    Returns the path to the downloaded file, or None on failure.
    """
    from services.cookie_helper import ensure_cookies_file

    url = f"https://www.youtube.com/watch?v={video_id}"
    output_template = os.path.join(output_dir, f"{video_id}.%(ext)s")

    # Ensure we have a valid cookies.txt file (will unlock keychain and extract if missing)
    cookie_path = ensure_cookies_file()

    def run_ytdlp(c_path):
        cmd = [
            "yt-dlp",
        ]
        if c_path:
            cmd.extend(["--cookies", c_path])
            logger.info(f"[{video_id}] Using cookies from: {c_path}")
        else:
            cmd.extend(["--cookies-from-browser", "chrome"])
            logger.info(f"[{video_id}] Using Chrome cookies-from-browser fallback")

        # Resolve Node path for executing JS signature challenges (nsig/n-parameter)
        import shutil

        node_path = "/opt/homebrew/bin/node"
        if not os.path.exists(node_path):
            node_path = shutil.which("node")

        if node_path:
            logger.info(f"[{video_id}] JS runtime: node={node_path}")
            cmd.extend(["--js-runtimes", f"node:{node_path}"])
        else:
            logger.warning(f"[{video_id}] JS runtime: node NOT found — nsig challenge may fail")

        cmd.extend(
            [
                "--remote-components",
                "ejs:github",
                "-x",  # Extract audio only
                "--audio-format",
                "mp3",
                "--audio-quality",
                "128K",
                "--postprocessor-args",
                "ffmpeg:-ar 16000 -ac 1",  # 16kHz mono for STT
                "--no-playlist",
                "--quiet",
                "--no-warnings",
                "-o",
                output_template,
                url,
            ]
        )
        return subprocess.run(cmd, capture_output=True, text=True, timeout=600)

    def _classify_error(stderr: str) -> str:
        """Classify yt-dlp stderr into an error category for smart retry logic."""
        if any(
            k in stderr
            for k in (
                "Failed to resolve",
                "nodename nor servname",
                "Network is unreachable",
                "[Errno 8]",
            )
        ):
            return "dns"
        if any(
            k in stderr
            for k in ("Sign in", "bot", "HTTP Error 403", "403 Forbidden", "This video is private")
        ):
            return "auth"
        if "Requested format is not available" in stderr:
            return "format"
        return "unknown"

    try:
        result = run_ytdlp(cookie_path)

        mp3_path = os.path.join(output_dir, f"{video_id}.mp3")
        success = os.path.exists(mp3_path) and os.path.getsize(mp3_path) > 1000

        # Smart retry: only refresh cookies on auth errors, not DNS/format errors
        if not success:
            err_category = _classify_error(result.stderr)
            if err_category == "dns":
                logger.warning(
                    f"[{video_id}] [NETWORK DOWN] DNS resolution failed — "
                    f"skipping cookie refresh (cookies are not the problem)"
                )
                # Still attempt retry in case network recovered
                result = run_ytdlp(cookie_path)
            elif err_category == "format":
                logger.warning(
                    f"[{video_id}] Format not available — "
                    f"skipping cookie refresh (auth is not the problem)"
                )
                # Don't retry — format error won't resolve with same config
            elif err_category in ("auth", "unknown"):
                logger.warning(
                    f"[{video_id}] Auth/unknown error ({err_category}) — "
                    f"refreshing cookies and retrying..."
                )
                cookie_path = ensure_cookies_file(force_refresh=True)
                result = run_ytdlp(cookie_path)
            success = os.path.exists(mp3_path) and os.path.getsize(mp3_path) > 1000

        if result.returncode != 0:
            logger.warning(f"[{video_id}] yt-dlp warning: {result.stderr[:300]}")

        if success:
            size_mb = os.path.getsize(mp3_path) / (1024 * 1024)
            logger.info(f"[{video_id}] Audio downloaded: {size_mb:.1f} MB")
            return mp3_path

        logger.error(f"[{video_id}] Audio download failed — file not found or too small")
        return None

    except subprocess.TimeoutExpired:
        logger.error(f"[{video_id}] Audio download timed out after 10 minutes")
        return None
    except Exception as e:
        logger.error(f"[{video_id}] Audio download error: {e}")
        return None


def transcribe_with_whisper(
    video_id: str,
    audio_path: str,
    model: Optional[str] = None,
    language: str = "en",
) -> Optional[str]:
    """
    Transcribe audio using local Whisper via mlx-whisper.

    Runs entirely on Apple Silicon Metal — no cloud API, no rate limits.
    Returns full transcript text or None on failure.
    """
    try:
        import mlx_whisper
    except ImportError:
        logger.error("mlx_whisper not installed — run: pip install mlx-whisper")
        return None

    if not os.path.exists(audio_path):
        logger.error(f"[{video_id}] Audio file not found: {audio_path}")
        return None

    if not model:
        model = settings.whisper_local_model or "mlx-community/whisper-large-v3-turbo"

    size_mb = os.path.getsize(audio_path) / (1024 * 1024)
    logger.info(f"[{video_id}] Transcribing {size_mb:.1f}MB audio with local MLX model: {model}...")

    # Domain-specific terminology corrections
    REPLACEMENTS = {
        "Ecom": "Ekam",
        "Ecoms": "Ekams",
        "Ekum": "Ekam",
        "ECAM": "Ekam",
        "Eikam": "Ekam",
        "Acom": "Ekam",
        "Acoms": "Ekams",
        "Akam": "Ekam",
        "Akham": "Ekam",
        "acom": "ekam",
        "acoms": "ekams",
        "acome": "ekam",
        "Pretaji": "Preethaji",
        "Pritaji": "Preethaji",
        "Preetha ji": "Preethaji",
        "Krishna ji": "Krishnaji",
        "Mukti": "Mukthi",
        "Soulsync": "Soul Sync",
        "soul sink": "Soul Sync",
        "Deeksha": "Deeksha",
        "Diksha": "Deeksha",
    }

    # Root-cause fix: bias Whisper toward the canonical spelling of doctrine proper nouns via
    # initial_prompt — otherwise it renders them phonetically ("Ekam"→"Akam"/"Acam",
    # "Preethaji"→"Pretty Ji"). This prevents the error at the source; REPLACEMENTS above and
    # the ingest corrector's FAST_REPLACEMENTS are the deterministic safety nets downstream.
    DOCTRINE_GLOSSARY = (
        "Correct spellings used in this recording: Ekam, Ekam World Centre, Sri Preethaji, "
        "Sri Krishnaji, Deeksha, Soul Sync, Sadhana, the Beautiful State, Oneness, the Four "
        "Sacred Secrets, Manifest 2026, Limitless Field."
    )

    try:
        result = mlx_whisper.transcribe(
            audio_path, path_or_hf_repo=model, verbose=False, initial_prompt=DOCTRINE_GLOSSARY
        )
        text = result.get("text", "").strip()

        if not text:
            logger.warning(f"[{video_id}] Whisper returned empty transcript")
            return None

        # Filter out common Whisper hallucinations (e.g., repeated "Thank you" loops)
        import re

        # Remove repeated intro phrases like "Thank you. Thank you. Thank you."
        thank_you_pattern = r"^(Thank you[\.\!\?\s,]*){3,}"
        text = re.sub(thank_you_pattern, "Thank you. ", text, flags=re.IGNORECASE)

        # Remove trailing repeated phrases
        trailing_thank_you = r"(Thank you[\.\!\?\s,]*){3,}$"
        text = re.sub(trailing_thank_you, " Thank you.", text, flags=re.IGNORECASE)

        # Apply domain-specific replacements
        for old, new in REPLACEMENTS.items():
            # Case-insensitive replacement while trying to preserve case if possible
            text = re.sub(rf"\b{old}\b", new, text, flags=re.IGNORECASE)

        word_count = len(text.split())
        logger.info(
            f"[{video_id}] ✅ Whisper STT: {len(text)} chars, {word_count} words (domain-corrected)"
        )
        return text

    except Exception as e:
        logger.error(f"[{video_id}] Whisper transcription failed: {e}")
        return None


def score_transcript(text: str, video_id: str = "") -> float:
    """
    Score transcript quality using heuristics.
    Higher is better. Range: 0.0 – 1.0

    Factors:
    - Word count (more words = more complete)
    - Punctuation density (periods/commas = better structure)
    - Ratio of known spiritual/domain terms
    - No excessive repetition
    """
    import re

    if not text or len(text.strip()) < 50:
        return 0.0

    words = text.split()
    word_count = len(words)

    if word_count == 0:
        return 0.0

    # 1. Length score (up to 0.4)
    length_score = min(word_count / 5000, 1.0) * 0.4

    # 2. Punctuation score (up to 0.3)
    char_count = len(text)
    punct_count = sum(1 for c in text if c in ".!?,;:")
    punct_ratio = punct_count / max(char_count / 100, 1)
    punct_score = min(punct_ratio / 3.0, 1.0) * 0.3

    # 3. Domain term score (up to 0.2)
    domain_terms = [
        "enlighten",
        "consciousness",
        "meditation",
        "awareness",
        "liberation",
        "freedom",
        "mind",
        "suffering",
        "joy",
        "presence",
        "spiritual",
        "mukthi",
        "preethaji",
        "krishnaji",
        "ekam",
        "dharma",
        "karma",
        "awakening",
        "wisdom",
        "inner",
        "beautiful state",
        "suffering state",
        "soul sync",
    ]
    found = sum(1 for t in domain_terms if re.search(t, text, re.IGNORECASE))
    domain_score = min(found / 8, 1.0) * 0.2

    # 4. Repetition penalty (up to -0.1)
    unique_words = len(set(w.lower() for w in words))
    uniqueness_ratio = unique_words / word_count
    repetition_penalty = (1.0 - uniqueness_ratio) * 0.1 if uniqueness_ratio < 0.5 else 0.0

    total = length_score + punct_score + domain_score - repetition_penalty
    total = max(0.0, min(1.0, total))

    logger.debug(
        f"[{video_id}] Score={total:.3f} "
        f"(len={length_score:.2f}, punct={punct_score:.2f}, "
        f"domain={domain_score:.2f}, rep_penalty={repetition_penalty:.2f})"
    )
    return total


def council_pick_best(
    youtube_text: Optional[str],
    whisper_text: Optional[str],
    video_id: str = "",
) -> dict:
    """
    The Transcript Council: compare YouTube captions vs local Whisper STT,
    return the best one (or merge if both are good).
    """
    yt_score = score_transcript(youtube_text, video_id) if youtube_text else 0.0
    wh_score = score_transcript(whisper_text, video_id) if whisper_text else 0.0

    logger.info(f"[{video_id}] Council scores — YouTube: {yt_score:.3f}, Whisper: {wh_score:.3f}")

    # Both failed
    if not youtube_text and not whisper_text:
        return {
            "text": "",
            "method": "failed",
            "youtube_score": 0.0,
            "whisper_score": 0.0,
            "winner": "none",
        }

    # Only one available
    if not youtube_text:
        logger.info(f"[{video_id}] Council: Whisper only (no YouTube captions)")
        return {
            "text": whisper_text,
            "method": "whisper",
            "youtube_score": 0.0,
            "whisper_score": wh_score,
            "winner": "whisper",
        }
    if not whisper_text:
        logger.info(f"[{video_id}] Council: YouTube only (no Whisper STT)")
        return {
            "text": youtube_text,
            "method": "youtube",
            "youtube_score": yt_score,
            "whisper_score": 0.0,
            "winner": "youtube",
        }

    gap = abs(yt_score - wh_score)
    both_long = len(youtube_text.split()) > 500 and len(whisper_text.split()) > 500

    if gap > 0.15:
        if yt_score > wh_score:
            logger.info(f"[{video_id}] Council: YouTube wins (gap={gap:.2f})")
            return {
                "text": youtube_text,
                "method": "youtube",
                "youtube_score": yt_score,
                "whisper_score": wh_score,
                "winner": "youtube",
            }
        else:
            logger.info(f"[{video_id}] Council: Whisper wins (gap={gap:.2f})")
            return {
                "text": whisper_text,
                "method": "whisper",
                "youtube_score": yt_score,
                "whisper_score": wh_score,
                "winner": "whisper",
            }

    if both_long:
        # Scores close and both long — Whisper has better punctuation, merge
        merged = (
            f"[Whisper Transcription]\n{whisper_text}\n\n"
            f"[YouTube Captions — additional coverage]\n{youtube_text}"
        )
        logger.info(f"[{video_id}] Council: Merged both sources (gap={gap:.2f}, both long)")
        return {
            "text": merged,
            "method": "merged",
            "youtube_score": yt_score,
            "whisper_score": wh_score,
            "winner": "merged",
        }

    # Close scores, one is short: pick higher scorer
    winner_text = youtube_text if yt_score >= wh_score else whisper_text
    winner_name = "youtube" if yt_score >= wh_score else "whisper"
    logger.info(f"[{video_id}] Council: {winner_name} wins by score (gap={gap:.2f})")
    return {
        "text": winner_text,
        "method": winner_name,
        "youtube_score": yt_score,
        "whisper_score": wh_score,
        "winner": winner_name,
    }
