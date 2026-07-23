"""
Audio Transcriber Engine — Downsampling, 10-min keyframe chunking, STT, and SSRF safety.

Ported from AgentReach's transcribe.py & transcribe_xiaoyuzhou.sh audio pipeline,
incorporating:
  - Generous timeouts (1800s for download, 1200s for ffmpeg) for long spiritual discourses.
  - SSRF safety checking for public http(s) URLs.
  - ffmpeg downsampling to mono 16kHz 32kbps m4a (reducing size by >85%).
  - 10-minute keyframe-aligned segment chunking when audio exceeds 24MB.
  - Integration with AskMukthiGuru's STT / Whisper pipeline and transcript polisher.
"""

from __future__ import annotations

import asyncio
import ipaddress
import logging
import os
import shutil
import socket
import subprocess
import tempfile
from pathlib import Path
from typing import List, Optional
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# Whisper / STT 25MB limit with headroom
SIZE_LIMIT_BYTES = 24 * 1024 * 1024
CHUNK_SECONDS = 600  # 10 minutes

_BLOCKED_HOSTS = {
    "localhost",
    "metadata.google.internal",
}


def _check_ip(ip: ipaddress.IPAddress) -> bool:
    return any((
        ip.is_private,
        ip.is_loopback,
        ip.is_link_local,
        ip.is_reserved,
        ip.is_multicast,
        ip.is_unspecified,
    ))

def is_safe_public_url(url: str) -> bool:
    """Validate that a URL is a public http(s) endpoint and does not resolve to private IPs.

    TOCTOU note: this resolves the hostname once, here. download_audio_stream()
    then hands the raw URL (not a pinned IP) to a `yt-dlp` subprocess, which
    re-resolves DNS independently at connect time — a DNS-rebinding attacker
    who controls the target hostname could pass this check with a public IP
    and connect with a private one. Not exploitable today: the only caller
    (youtube_service.py) builds the URL from a hardcoded "www.youtube.com"
    host, never from an attacker-influenced value. Do not call this helper
    with an attacker-controlled hostname without closing that gap first
    (e.g. pinning the resolved IP for the actual connection).
    """
    try:
        if "://" not in url:
            parsed = urlparse(f"https://{url}")
        else:
            parsed = urlparse(url)
            if parsed.scheme not in {"http", "https"}:
                return False

        host = (parsed.hostname or "").strip().lower().rstrip(".")
        if not host:
            return False
        if host in _BLOCKED_HOSTS or host.endswith(".localhost"):
            return False

        try:
            ip = ipaddress.ip_address(host)
            if _check_ip(ip):
                return False
            return True
        except ValueError:
            pass  # Hostname, not literal IP — must resolve

        try:
            addrs = socket.getaddrinfo(host, 80)
            for family, _, _, _, sockaddr in addrs:
                raw = sockaddr[0]
                try:
                    ip = ipaddress.ip_address(raw)
                    if _check_ip(ip):
                        return False
                except ValueError:
                    continue
            return True
        except socket.gaierror:
            return False
    except Exception:
        return False


def _run_subprocess(cmd: List[str], timeout: int = 1200) -> subprocess.CompletedProcess:
    """Run a subprocess command with generous timeout headroom."""
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        if proc.returncode != 0:
            logger.error("%s failed (exit %d): %s", cmd[0], proc.returncode, proc.stderr[:300])
        return proc
    except subprocess.TimeoutExpired:
        logger.error("%s timed out after %ds", cmd[0], timeout)
        raise RuntimeError(f"{cmd[0]} timed out after {timeout} seconds")


def download_audio_stream(url: str, out_dir: Path, timeout: int = 1800) -> Path:
    """Download audio from YouTube or media URL using yt-dlp into out_dir."""
    if not is_safe_public_url(url):
        raise ValueError("URL fails SSRF public security check")

    if not shutil.which("yt-dlp"):
        raise RuntimeError("yt-dlp binary not found in PATH")

    template = out_dir / "audio_source.%(ext)s"
    cmd = [
        "yt-dlp",
        "-x",
        "--audio-format",
        "m4a",
        "--audio-quality",
        "0",
        "-o",
        str(template),
        "--",
        url,
    ]
    _run_subprocess(cmd, timeout=timeout)

    files = sorted(out_dir.glob("audio_source.*"))
    if not files:
        raise RuntimeError("yt-dlp produced no audio output file")
    return files[0]


def compress_audio_to_mono(src: Path, out_dir: Path, timeout: int = 1200) -> Path:
    """Re-encode audio to mono / 16kHz / 32kbps m4a (downsamples size by >85%)."""
    if not shutil.which("ffmpeg"):
        raise RuntimeError("ffmpeg binary not found in PATH")

    dst = out_dir / "compressed_mono.m4a"
    cmd = [
        "ffmpeg",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(src),
        "-vn",
        "-ac",
        "1",
        "-ar",
        "16000",
        "-b:a",
        "32k",
        str(dst),
    ]
    _run_subprocess(cmd, timeout=timeout)
    if not dst.exists():
        raise RuntimeError("ffmpeg compression failed to produce output file")
    return dst


def chunk_audio_keyframe_segments(
    src: Path, out_dir: Path, segment_seconds: int = CHUNK_SECONDS, timeout: int = 1200
) -> List[Path]:
    """Split audio file into 10-minute segments aligned to keyframes."""
    if not shutil.which("ffmpeg"):
        raise RuntimeError("ffmpeg binary not found in PATH")

    pattern = out_dir / "chunk_%03d.m4a"
    cmd = [
        "ffmpeg",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(src),
        "-f",
        "segment",
        "-segment_time",
        str(segment_seconds),
        "-ac",
        "1",
        "-ar",
        "16000",
        "-b:a",
        "32k",
        str(pattern),
    ]
    _run_subprocess(cmd, timeout=timeout)
    chunks = sorted(out_dir.glob("chunk_*.m4a"))
    if not chunks:
        raise RuntimeError("ffmpeg chunking produced no segment files")
    return chunks


async def _transcribe_chunks(chunks: List[Path]) -> str:
    """Transcribe each audio chunk via the local Whisper service, in order.

    Mirrors the fallback call in ingest/video_pipeline.py's _transcribe():
    same helper, run off the event loop since mlx-whisper is blocking.
    """
    from services.whisper_local_service import transcribe_with_whisper

    texts: List[str] = []
    for i, chunk in enumerate(chunks):
        text = await asyncio.to_thread(transcribe_with_whisper, f"audio_chunk_{i}", str(chunk))
        if text:
            texts.append(text)
        else:
            logger.warning("Whisper returned no transcript for chunk %d/%d (%s)", i + 1, len(chunks), chunk)

    if not texts:
        raise RuntimeError("Whisper transcription produced no output for any chunk")
    return "\n\n".join(texts)


async def transcribe_and_preprocess_audio(
    source_url_or_path: str,
    output_dir: Optional[Path] = None,
    should_polish: bool = True,
) -> str:
    """Full audio pipeline: download -> 16kHz mono compress -> chunk -> transcribe -> polish."""
    from services.transcript_polisher import polish_transcript

    is_file = Path(source_url_or_path).is_file()
    if not is_file and not is_safe_public_url(source_url_or_path):
        raise ValueError(f"Prohibited or non-public URL: {source_url_or_path}")

    with tempfile.TemporaryDirectory(prefix="mukthi-audio-") as tmp_str:
        work_dir = output_dir or Path(tmp_str)
        work_dir.mkdir(parents=True, exist_ok=True)

        if is_file:
            audio_source = Path(source_url_or_path)
        else:
            audio_source = download_audio_stream(source_url_or_path, work_dir, timeout=1800)

        compressed = compress_audio_to_mono(audio_source, work_dir, timeout=1200)
        
        if compressed.stat().st_size <= SIZE_LIMIT_BYTES:
            chunks = [compressed]
        else:
            chunks = chunk_audio_keyframe_segments(compressed, work_dir, timeout=1200)

        logger.info("Audio processed into %d chunk(s) for STT transcription", len(chunks))

        transcribed_text = await _transcribe_chunks(chunks)

        if should_polish:
            return await polish_transcript(transcribed_text)

        return transcribed_text
