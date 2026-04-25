"""
Mukthi Guru — Sarvam Cloud Batch STT Service

Uses Sarvam Saaras v3 Batch API to transcribe YouTube audio when
YouTube auto-captions are unavailable or low-quality.

Workflow per video:
  1. Download audio via yt-dlp (MP3, 16kHz mono)
  2. Chunk into ≤55-minute pieces (Batch API limit: 1hr per file)
  3. Submit batch job to Sarvam (saaras:v3)
  4. Poll until complete (job.wait_until_complete)
  5. Merge chunk transcripts → single text
  6. Clean up temp files

Used by the Transcript Council in youtube_loader.py to get a second
opinion alongside YouTube auto-captions.
"""

import logging
import math
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

from app.config import settings

logger = logging.getLogger(__name__)


def download_audio(video_id: str, output_dir: str) -> Optional[str]:
    """
    Download YouTube audio as mono 16kHz MP3 using yt-dlp.

    Returns the path to the downloaded file, or None on failure.
    We use subprocess so we don't depend on yt-dlp's Python API stability.
    """
    url = f"https://www.youtube.com/watch?v={video_id}"
    output_template = os.path.join(output_dir, f"{video_id}.%(ext)s")

    cmd = [
        "yt-dlp",
        "-x",                          # Extract audio only
        "--audio-format", "mp3",
        "--audio-quality", "128K",
        "--postprocessor-args", "ffmpeg:-ar 16000 -ac 1",  # 16kHz mono for STT
        "--no-playlist",
        "--quiet",
        "--no-warnings",
        "-o", output_template,
        url,
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        if result.returncode != 0:
            logger.warning(f"[{video_id}] yt-dlp warning: {result.stderr[:300]}")

        # Find the output file
        mp3_path = os.path.join(output_dir, f"{video_id}.mp3")
        if os.path.exists(mp3_path) and os.path.getsize(mp3_path) > 1000:
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


def get_audio_duration_seconds(audio_path: str) -> float:
    """Get audio duration via ffprobe."""
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
             "-of", "csv=p=0", audio_path],
            capture_output=True, text=True, timeout=30
        )
        return float(result.stdout.strip())
    except Exception:
        return 0.0


def chunk_audio(audio_path: str, output_dir: str, chunk_minutes: int) -> list[str]:
    """
    Split audio into ≤chunk_minutes chunks for Sarvam Batch API.
    Returns list of chunk file paths.
    """
    duration = get_audio_duration_seconds(audio_path)
    chunk_secs = chunk_minutes * 60

    if duration <= chunk_secs:
        return [audio_path]  # No splitting needed

    num_chunks = math.ceil(duration / chunk_secs)
    logger.info(f"Splitting {duration/60:.1f}min audio into {num_chunks} chunks")

    chunks = []
    basename = Path(audio_path).stem

    for i in range(num_chunks):
        start = i * chunk_secs
        chunk_path = os.path.join(output_dir, f"{basename}_chunk{i:02d}.mp3")
        cmd = [
            "ffmpeg", "-y",
            "-i", audio_path,
            "-ss", str(start),
            "-t", str(chunk_secs),
            "-acodec", "copy",
            chunk_path,
        ]
        result = subprocess.run(cmd, capture_output=True, timeout=120)
        if result.returncode == 0 and os.path.exists(chunk_path):
            chunks.append(chunk_path)
        else:
            logger.warning(f"Failed to create chunk {i}: {result.stderr[:200]}")

    return chunks


def transcribe_with_sarvam(video_id: str, audio_path: str) -> Optional[str]:
    """
    Transcribe audio using Sarvam Saaras v3 Batch API.

    Handles chunking for long files. Returns merged transcript text or None.
    """
    try:
        from sarvamai import SarvamAI
    except ImportError:
        logger.error("sarvamai not installed — cannot use Sarvam STT")
        return None

    api_key = settings.sarvam_api_key
    if not api_key:
        logger.error("SARVAM_API_KEY not set — cannot use Sarvam STT")
        return None

    # Safety check: skip very large files
    size_mb = os.path.getsize(audio_path) / (1024 * 1024)
    if size_mb > settings.stt_max_audio_mb:
        logger.warning(f"[{video_id}] Audio too large ({size_mb:.0f}MB > {settings.stt_max_audio_mb}MB limit), skipping STT")
        return None

    client = SarvamAI(api_subscription_key=api_key)

    with tempfile.TemporaryDirectory() as chunk_dir:
        # Split into chunks if needed
        chunks = chunk_audio(audio_path, chunk_dir, settings.stt_chunk_minutes)
        logger.info(f"[{video_id}] Submitting {len(chunks)} chunk(s) to Sarvam Batch STT")

        all_transcripts = []

        # Process in batches of 20 (Sarvam Batch API limit per job)
        for batch_start in range(0, len(chunks), 20):
            batch = chunks[batch_start:batch_start + 20]

            try:
                job = client.speech_to_text_job.create_job(
                    model=settings.sarvam_stt_model,
                    mode=settings.sarvam_stt_mode,
                    language_code=settings.sarvam_stt_language,
                    with_diarization=False,  # Keep simple for RAG use case
                )

                job.upload_files(file_paths=batch)
                job.start()

                logger.info(f"[{video_id}] Sarvam job started: {job.job_id}")
                job.wait_until_complete()

                file_results = job.get_file_results()
                successful = file_results.get("successful", [])
                failed = file_results.get("failed", [])

                if failed:
                    logger.warning(f"[{video_id}] {len(failed)} chunk(s) failed in Sarvam STT")

                # Download outputs
                output_dir = tempfile.mkdtemp()
                if successful:
                    try:
                        job.download_outputs(output_dir=output_dir)
                    except Exception as e:
                        logger.warning(f"[{video_id}] download_outputs failed: {e}, trying get_output_mappings")

                # Extract transcripts from successful results
                for f in successful:
                    transcript_text = f.get("transcript", "") or f.get("text", "")
                    if transcript_text:
                        all_transcripts.append(transcript_text.strip())
                    else:
                        # Try reading from downloaded output files
                        fname = f.get("file_name", "")
                        if fname:
                            out_path = os.path.join(output_dir, Path(fname).stem + ".txt")
                            if os.path.exists(out_path):
                                with open(out_path) as fp:
                                    all_transcripts.append(fp.read().strip())

            except Exception as e:
                logger.error(f"[{video_id}] Sarvam STT batch error: {e}")
                continue

    if not all_transcripts:
        return None

    merged = " ".join(all_transcripts)
    logger.info(f"[{video_id}] ✅ Sarvam STT: {len(merged)} chars, {len(merged.split())} words")
    return merged


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
    if not text or len(text.strip()) < 50:
        return 0.0

    words = text.split()
    word_count = len(words)

    if word_count == 0:
        return 0.0

    # 1. Length score (up to 0.4): more complete transcripts score higher
    # Typical video: 1500-5000 words. Cap at 5000.
    length_score = min(word_count / 5000, 1.0) * 0.4

    # 2. Punctuation score (up to 0.3): proper punctuation means better STT
    char_count = len(text)
    punct_count = sum(1 for c in text if c in ".!?,;:")
    punct_ratio = punct_count / max(char_count / 100, 1)  # per 100 chars
    punct_score = min(punct_ratio / 3.0, 1.0) * 0.3  # ~3 punct per 100 chars is good

    # 3. Domain term score (up to 0.2): known spiritual terms
    domain_terms = [
        "enlighten", "consciousness", "meditation", "awareness",
        "liberation", "freedom", "mind", "suffering", "joy", "presence",
        "spiritual", "mukthi", "preethaji", "krishnaji", "ekam",
        "dharma", "karma", "awakening", "wisdom", "inner",
    ]
    import re
    found = sum(1 for t in domain_terms if re.search(t, text, re.IGNORECASE))
    domain_score = min(found / 8, 1.0) * 0.2  # Finding 8+ terms is great

    # 4. Repetition penalty (up to -0.1): penalise repeated phrases
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
    sarvam_text: Optional[str],
    video_id: str = "",
) -> dict:
    """
    The Transcript Council: compare YouTube captions vs Sarvam STT,
    return the best one (or merge if both are good).

    Strategy:
    - Score both on quality heuristics
    - If one score is significantly higher (>0.15 gap), pick that one
    - If scores are close (<0.15 gap) and both are long, merge them:
      Sarvam gives punctuation/structure, YouTube gives completeness
    - Always log which won and why

    Returns dict with:
      text: str          — the chosen/merged transcript
      method: str        — 'youtube', 'sarvam', 'merged', or 'failed'
      youtube_score: float
      sarvam_score: float
      winner: str
    """
    yt_score = score_transcript(youtube_text, video_id) if youtube_text else 0.0
    sv_score = score_transcript(sarvam_text, video_id) if sarvam_text else 0.0

    logger.info(
        f"[{video_id}] Council scores — YouTube: {yt_score:.3f}, Sarvam: {sv_score:.3f}"
    )

    # Both failed
    if not youtube_text and not sarvam_text:
        return {"text": "", "method": "failed", "youtube_score": 0.0, "sarvam_score": 0.0, "winner": "none"}

    # Only one available
    if not youtube_text:
        logger.info(f"[{video_id}] Council: Sarvam only (no YouTube captions)")
        return {"text": sarvam_text, "method": "sarvam", "youtube_score": 0.0, "sarvam_score": sv_score, "winner": "sarvam"}
    if not sarvam_text:
        logger.info(f"[{video_id}] Council: YouTube only (no Sarvam STT)")
        return {"text": youtube_text, "method": "youtube", "youtube_score": yt_score, "sarvam_score": 0.0, "winner": "youtube"}

    gap = abs(yt_score - sv_score)
    both_long = len(youtube_text.split()) > 500 and len(sarvam_text.split()) > 500

    if gap > 0.15:
        # Clear winner
        if yt_score > sv_score:
            logger.info(f"[{video_id}] Council: YouTube wins (gap={gap:.2f})")
            return {"text": youtube_text, "method": "youtube", "youtube_score": yt_score, "sarvam_score": sv_score, "winner": "youtube"}
        else:
            logger.info(f"[{video_id}] Council: Sarvam wins (gap={gap:.2f})")
            return {"text": sarvam_text, "method": "sarvam", "youtube_score": yt_score, "sarvam_score": sv_score, "winner": "sarvam"}

    if both_long:
        # Scores close and both long: merge Sarvam (structure) + YouTube (completeness)
        # Use Sarvam as primary (better punctuation), append YouTube unique content
        merged = (
            f"[Sarvam Transcription]\n{sarvam_text}\n\n"
            f"[YouTube Captions — additional coverage]\n{youtube_text}"
        )
        logger.info(f"[{video_id}] Council: Merged both sources (gap={gap:.2f}, both long)")
        return {"text": merged, "method": "merged", "youtube_score": yt_score, "sarvam_score": sv_score, "winner": "merged"}

    # Close scores, one is short: pick higher scorer
    winner_text = youtube_text if yt_score >= sv_score else sarvam_text
    winner_name = "youtube" if yt_score >= sv_score else "sarvam"
    logger.info(f"[{video_id}] Council: {winner_name} wins by score (gap={gap:.2f})")
    return {"text": winner_text, "method": winner_name, "youtube_score": yt_score, "sarvam_score": sv_score, "winner": winner_name}
