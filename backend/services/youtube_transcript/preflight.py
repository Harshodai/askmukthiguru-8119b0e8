"""Preflight checks and installation guidance for YouTube transcript tooling."""

from __future__ import annotations

import platform
import shutil
import subprocess
from typing import Optional


def check_ytdlp_installed(custom_path: Optional[str] = None) -> bool:
    """Return True if yt-dlp binary is available on PATH or custom_path."""
    if custom_path:
        return shutil.which(custom_path) is not None
    return shutil.which("yt-dlp") is not None


def get_ytdlp_version(custom_path: Optional[str] = None) -> Optional[str]:
    """Return yt-dlp --version string if available, else None."""
    bin_path = custom_path or shutil.which("yt-dlp")
    if not bin_path:
        return None
    try:
        proc = subprocess.run([bin_path, "--version"], capture_output=True, text=True, timeout=5)
        if proc.returncode == 0:
            return proc.stdout.strip()
    except Exception:
        pass
    return None


def get_ytdlp_install_instructions(system_name: Optional[str] = None) -> dict[str, str]:
    """Return system-specific install instructions for yt-dlp."""
    sys_name = (system_name or platform.system()).lower()
    instructions = {
        "macos": "brew install yt-dlp",
        "linux": "sudo apt update && sudo apt install -y yt-dlp",
        "pip": "python3 -m pip install -U yt-dlp",
        "official_repo": "https://github.com/yt-dlp/yt-dlp#installation",
    }
    if "darwin" in sys_name or "mac" in sys_name:
        instructions["primary"] = instructions["macos"]
    elif "linux" in sys_name:
        instructions["primary"] = instructions["linux"]
    else:
        instructions["primary"] = instructions["pip"]
    return instructions


def check_ffmpeg_installed(custom_path: Optional[str] = None) -> bool:
    """Return True if ffmpeg binary is available on PATH or custom_path."""
    if custom_path:
        return shutil.which(custom_path) is not None
    return shutil.which("ffmpeg") is not None


def check_whisper_installed() -> bool:
    """Return True if whisper CLI or Python module is available."""
    if shutil.which("whisper") is not None:
        return True
    try:
        import whisper  # noqa: F401

        return True
    except ImportError:
        pass
    try:
        import mlx_whisper  # noqa: F401

        return True
    except ImportError:
        pass
    return False


def get_whisper_install_instructions() -> dict[str, str]:
    """Return Whisper installation guidance."""
    return {
        "pip": "pip install -U openai-whisper",
        "apple_silicon": "pip install mlx-whisper",
        "ffmpeg_notice": "FFmpeg is required for Whisper audio processing.",
    }
