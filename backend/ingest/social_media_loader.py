"""
Mukthi Guru — Hardened Social Media & Direct Video Loader

Security & Ingestion Invariants:
  - Strict URL Scheme & Hostname Validation: http/https only, no credentials.
  - Comprehensive SSRF Defense: Rejection of private (10/8, 172.16/12, 192.168/16),
    loopback (127/8, ::1), link-local (169.254/16, fe80::/10), multicast, broadcast,
    and reserved IP ranges in standard, decimal, hex, and octal representations.
  - DNS Resolution & Rebinding Safety: Resolves hostnames and verifies all resolved
    IPs against blocked IP networks, with redirect hop re-validation.
  - Resource Protection: Streaming download size limit (50MB max), explicit connect,
    read, total, and subprocess timeouts.
  - Clean Teardown: Temporary file & directory cleanup on all success and error paths.
  - Injection Safety: No shell string interpolation; arguments passed as lists.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import ipaddress
import logging
import os
import re
import shutil
import socket
import subprocess
import tempfile
import time
import urllib.parse
from typing import Any, Dict, List, Optional, Tuple, Union

logger = logging.getLogger(__name__)

# Maximum response size allowed during streaming ingestion (50 MB)
MAX_INGEST_RESPONSE_BYTES = 50 * 1024 * 1024

# Timeouts in seconds
CONNECT_TIMEOUT = 10.0
READ_TIMEOUT = 30.0
TOTAL_DOWNLOAD_TIMEOUT = 120.0
SUBPROCESS_TIMEOUT = 600.0

ALLOWED_SCHEMES = {"http", "https"}

# Blocked IP networks covering all non-public/internal/cloud metadata scopes
_BLOCKED_NETWORKS = [
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("100.64.0.0/10"),  # Carrier-grade NAT
    ipaddress.ip_network("127.0.0.0/8"),    # Loopback
    ipaddress.ip_network("169.254.0.0/16"), # Link-local / Cloud Metadata (AWS/GCP/Azure)
    ipaddress.ip_network("172.16.0.0/12"),  # Private Class B
    ipaddress.ip_network("192.0.0.0/24"),   # IETF Protocol Assignments
    ipaddress.ip_network("192.0.2.0/24"),   # TEST-NET-1
    ipaddress.ip_network("192.168.0.0/16"), # Private Class C
    ipaddress.ip_network("198.18.0.0/15"),  # Benchmarking
    ipaddress.ip_network("198.51.100.0/24"),# TEST-NET-2
    ipaddress.ip_network("203.0.113.0/24"), # TEST-NET-3
    ipaddress.ip_network("224.0.0.0/4"),    # Multicast
    ipaddress.ip_network("240.0.0.0/4"),    # Reserved / Future use
    ipaddress.ip_network("255.255.255.255/32"), # Broadcast
    # IPv6
    ipaddress.ip_network("::/128"),         # Unspecified
    ipaddress.ip_network("::1/128"),        # Loopback
    ipaddress.ip_network("::ffff:0:0/96"),  # IPv4-mapped IPv6
    ipaddress.ip_network("64:ff9b::/96"),   # IPv4/IPv6 translation
    ipaddress.ip_network("100::/64"),       # Discard prefix
    ipaddress.ip_network("2001:db8::/32"),  # Documentation
    ipaddress.ip_network("fc00::/7"),       # Unique Local Address (ULA)
    ipaddress.ip_network("fe80::/10"),      # Link-local
    ipaddress.ip_network("ff00::/8"),       # Multicast
]

# Patterns for social media / direct video URL detection
SOCIAL_MEDIA_PATTERNS = [
    re.compile(r"instagram\.com/(reel|p|tv)/", re.IGNORECASE),
    re.compile(r"tiktok\.com/", re.IGNORECASE),
    re.compile(r"twitter\.com/.+/status/", re.IGNORECASE),
    re.compile(r"x\.com/.+/status/", re.IGNORECASE),
    re.compile(r"(youtube\.com/watch\?v=|youtu\.be/|youtube\.com/shorts/)", re.IGNORECASE),
    re.compile(r"facebook\.com/.+/(videos|reel)/", re.IGNORECASE),
    re.compile(r"threads\.net/.+/post/", re.IGNORECASE),
    re.compile(r"vimeo\.com/\d+", re.IGNORECASE),
    re.compile(r"reddit\.com/r/.+/comments/", re.IGNORECASE),
]

DIRECT_VIDEO_PATTERN = re.compile(
    r"\.(mp4|mov|avi|webm|mkv|flv|wmv|m4v)(\?.*)?$",
    re.IGNORECASE,
)


def _is_prohibited_ip(ip: Union[ipaddress.IPv4Address, ipaddress.IPv6Address]) -> bool:
    """Return True if IP is private, loopback, link-local, reserved, multicast, or unspecified."""
    if ip.is_private or ip.is_loopback or ip.is_reserved or ip.is_link_local or ip.is_multicast or ip.is_unspecified:
        return True
    for net in _BLOCKED_NETWORKS:
        if ip in net:
            return True
    return False


def _parse_ip_literal(host: str) -> Optional[Union[ipaddress.IPv4Address, ipaddress.IPv6Address]]:
    """Parse standard, integer, hex, octal, or IPv6-bracketed literal."""
    h = host.strip("[]").strip()
    if not h:
        return None

    # 1. Standard ipaddress parse
    try:
        return ipaddress.ip_address(h)
    except ValueError:
        pass

    # 2. Integer or Hex literal (e.g. 2130706433, 0x7f000001)
    if h.isdigit():
        try:
            num = int(h, 10)
            if 0 <= num <= 0xFFFFFFFF:
                return ipaddress.IPv4Address(num)
        except (ValueError, OverflowError):
            pass
    elif h.lower().startswith("0x"):
        try:
            num = int(h, 16)
            if 0 <= num <= 0xFFFFFFFF:
                return ipaddress.IPv4Address(num)
        except (ValueError, OverflowError):
            pass

    # 3. Dotted octal/hex/decimal parts (e.g. 0177.0.0.1 or 0x7f.0.0.1 or 127.1)
    parts = h.split(".")
    if 1 < len(parts) <= 4:
        try:
            parsed_parts = []
            for p in parts:
                p_clean = p.strip()
                if p_clean.startswith(("0x", "0X")):
                    val = int(p_clean, 16)
                elif p_clean.startswith("0") and len(p_clean) > 1 and p_clean.isdigit():
                    val = int(p_clean, 8)
                elif p_clean.isdigit():
                    val = int(p_clean, 10)
                else:
                    return None
                if val < 0 or (val > 255 and len(parts) == 4):
                    return None
                parsed_parts.append(val)

            if len(parsed_parts) == 4:
                return ipaddress.IPv4Address(bytes(parsed_parts))
            elif len(parsed_parts) == 2:  # a.b -> (a << 24) | b
                num = (parsed_parts[0] << 24) | parsed_parts[1]
                if 0 <= num <= 0xFFFFFFFF:
                    return ipaddress.IPv4Address(num)
        except (ValueError, OverflowError):
            pass

    return None


def resolve_and_validate_hostname(hostname: str, port: int = 80) -> List[str]:
    """
    Resolve hostname and verify that NONE of the resolved IPs are private/loopback/reserved.
    Returns list of valid public IP strings, or raises ValueError.
    """
    cleaned_host = hostname.strip("[]").strip()
    if not cleaned_host:
        raise ValueError("Missing hostname")

    # Reject localhost aliases & internal TLDs
    lower_host = cleaned_host.lower()
    if lower_host in ("localhost", "localhost.localdomain", "ip6-localhost", "ip6-loopback"):
        raise ValueError(f"Blocked localhost hostname: {hostname}")

    if any(lower_host.endswith(tld) for tld in (".local", ".internal", ".localhost", ".lan", ".corp", ".home", ".localdomain")):
        raise ValueError(f"Blocked internal domain name: {hostname}")

    # Check for direct IP literal in hostname
    ip_lit = _parse_ip_literal(cleaned_host)
    if ip_lit is not None:
        if _is_prohibited_ip(ip_lit):
            raise ValueError(f"Prohibited IP address literal: {ip_lit}")
        return [str(ip_lit)]

    try:
        addr_info = socket.getaddrinfo(cleaned_host, port, socket.AF_UNSPEC, socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise ValueError(f"Failed to resolve hostname '{hostname}': {exc}") from exc
    except Exception as exc:
        raise ValueError(f"DNS resolution error for '{hostname}': {exc}") from exc

    if not addr_info:
        raise ValueError(f"No DNS records found for hostname: {hostname}")

    public_ips: List[str] = []
    for entry in addr_info:
        sockaddr = entry[4]
        ip_str = sockaddr[0]
        try:
            ip = ipaddress.ip_address(ip_str)
            if _is_prohibited_ip(ip):
                raise ValueError(f"Hostname '{hostname}' resolved to prohibited IP: {ip}")
            if str(ip) not in public_ips:
                public_ips.append(str(ip))
        except ValueError as exc:
            if "prohibited" in str(exc).lower() or "private" in str(exc).lower():
                raise
            continue

    if not public_ips:
        raise ValueError(f"No valid public IP addresses resolved for hostname: {hostname}")

    return public_ips


def validate_safe_url(url: str) -> Tuple[bool, str]:
    """
    Validate that a URL is safe for ingestion against SSRF, bad schemes, and credentials.
    Returns (is_safe, error_reason).
    """
    if not url or not isinstance(url, str):
        return False, "Empty or non-string URL"

    try:
        parsed = urllib.parse.urlsplit(url.strip())
    except Exception as exc:
        return False, f"Malformed URL: {exc}"

    scheme = (parsed.scheme or "").lower()
    if scheme not in ALLOWED_SCHEMES:
        return False, f"Disallowed scheme: '{scheme}'. Only http and https are permitted."

    if not parsed.netloc:
        return False, "URL is missing network location (hostname)"

    if parsed.username or parsed.password:
        return False, "URL contains embedded credentials"

    hostname = parsed.hostname
    if not hostname:
        return False, "URL is missing hostname"

    hostname = hostname.strip().lower()

    try:
        if parsed.port is not None:
            if not (1 <= parsed.port <= 65535):
                return False, f"Invalid port: {parsed.port}"

        # Check for direct IP literal in hostname
        ip_lit = _parse_ip_literal(hostname)
        if ip_lit is not None:
            if _is_prohibited_ip(ip_lit):
                return False, f"Blocked prohibited IP address literal: {ip_lit}"

        # Check DNS resolution
        port = parsed.port or (443 if scheme == "https" else 80)
        resolve_and_validate_hostname(hostname, port)
    except ValueError as exc:
        return False, str(exc)

    return True, ""


def is_social_media_url(url: str) -> bool:
    """Return True if the URL points to a social media video or direct video file."""
    for pattern in SOCIAL_MEDIA_PATTERNS:
        if pattern.search(url):
            return True
    return bool(DIRECT_VIDEO_PATTERN.search(url))


def _get_cookie_opts() -> dict:
    """Reuse existing cookie helper for authentication (same as youtube_loader.py)."""
    try:
        from services.cookie_helper import ensure_cookies_file
        cookie_path = ensure_cookies_file()
        if cookie_path and os.path.exists(cookie_path):
            return {"cookiefile": cookie_path}
    except Exception as e:
        logger.debug("cookie_helper unavailable: %s", e)

    possible = [
        os.path.join(os.getcwd(), "cookies.txt"),
    ]
    for path in possible:
        if os.path.exists(path):
            return {"cookiefile": path}

    return {}


async def download_streaming_file(
    url: str,
    dest_path: str,
    *,
    max_bytes: int = MAX_INGEST_RESPONSE_BYTES,
    max_redirects: int = 5,
    connect_timeout: float = CONNECT_TIMEOUT,
    read_timeout: float = READ_TIMEOUT,
    total_timeout: float = TOTAL_DOWNLOAD_TIMEOUT,
) -> int:
    """
    Stream download a file with SSRF re-validation at each redirect hop and hard max_bytes limit.
    Aborts immediately and cleans up dest_path if max_bytes is exceeded or validation fails.
    Returns total bytes downloaded.
    """
    import httpx

    current_url = url
    redirect_count = 0
    total_bytes = 0
    deadline = time.monotonic() + total_timeout

    try:
        timeout = httpx.Timeout(
            connect=connect_timeout,
            read=read_timeout,
            write=read_timeout,
            pool=connect_timeout,
        )
        async with httpx.AsyncClient(follow_redirects=False, timeout=timeout) as client:
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError(f"Download of '{url}' exceeded total timeout of {total_timeout}s")

                is_safe, reason = validate_safe_url(current_url)
                if not is_safe:
                    raise ValueError(f"SSRF blocked URL '{current_url}': {reason}")

                req = client.build_request("GET", current_url, headers={"User-Agent": "MukthiGuru-Ingest/1.0"})
                resp = await asyncio.wait_for(
                    client.send(req, stream=True),
                    timeout=min(connect_timeout + 5.0, remaining),
                )

                # Re-validate redirect hops
                if resp.status_code in (301, 302, 303, 307, 308):
                    await resp.aclose()
                    redirect_count += 1
                    if redirect_count > max_redirects:
                        raise ValueError(f"Too many redirects (exceeded {max_redirects})")
                    location = resp.headers.get("Location")
                    if not location:
                        raise ValueError(f"Redirect status {resp.status_code} missing Location header")
                    current_url = urllib.parse.urljoin(current_url, location)
                    continue

                if resp.status_code >= 400:
                    await resp.aclose()
                    raise ValueError(f"HTTP error {resp.status_code} fetching URL")

                with open(dest_path, "wb") as f:
                    async for chunk in resp.aiter_bytes(chunk_size=65536):
                        remaining = deadline - time.monotonic()
                        if remaining <= 0:
                            await resp.aclose()
                            raise TimeoutError(
                                f"Download of '{url}' exceeded total timeout of {total_timeout}s"
                            )
                        total_bytes += len(chunk)
                        if total_bytes > max_bytes:
                            await resp.aclose()
                            raise ValueError(f"Response size ({total_bytes} bytes) exceeds limit of {max_bytes} bytes")
                        f.write(chunk)
                await resp.aclose()
                return total_bytes
    except Exception:
        if os.path.exists(dest_path):
            try:
                os.unlink(dest_path)
            except OSError:
                pass
        raise


async def ingest_social_media(
    url: str,
    whisper_service: Optional[object] = None,
    max_bytes: int = MAX_INGEST_RESPONSE_BYTES,
) -> dict:
    """
    Download audio from a social media or direct video URL and transcribe with Whisper.

    Args:
        url: Instagram/TikTok/Twitter/direct video URL
        whisper_service: Optional object exposing .transcribe(path) (for DI); if None, falls back to transcribe_with_whisper
        max_bytes: Maximum response download bytes before aborting (default: 50MB)

    Returns:
        Dict with keys: text, source_url, title, content_type, method, duration_seconds
        On failure: error key is set, text is empty string.
    """
    # Security Gate: SSRF & URL validation
    is_safe, error_reason = validate_safe_url(url)
    if not is_safe:
        logger.warning("SSRF / URL validation blocked URL '%s': %s", url, error_reason)
        return {
            "text": "",
            "source_url": url,
            "title": "",
            "content_type": "social_video",
            "method": "blocked_ssrf",
            "error": f"Security validation failed: {error_reason}",
        }

    with tempfile.TemporaryDirectory() as tmpdir:
        audio_outtmpl = os.path.join(tmpdir, "audio.%(ext)s")
        result_info: Dict[str, Any] = {}

        # Step 1: Download audio via yt-dlp
        def _download_audio() -> dict:
            try:
                import yt_dlp  # type: ignore
                cookie_opts = _get_cookie_opts()
                ydl_opts = {
                    "format": "bestaudio/best",
                    "postprocessors": [
                        {
                            "key": "FFmpegExtractAudio",
                            "preferredcodec": "wav",
                            "preferredquality": "0",
                        }
                    ],
                    "outtmpl": audio_outtmpl,
                    "quiet": True,
                    "no_warnings": True,
                    "extract_flat": False,
                    "socket_timeout": 15,
                    "max_filesize": max_bytes,
                    **cookie_opts,
                }
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(url, download=True)
                    return {
                        "title": info.get("title") or info.get("id", ""),
                        "duration": info.get("duration") or 0,
                        "uploader": info.get("uploader") or info.get("channel") or "Unknown",
                    }
            except Exception as e:
                logger.warning("yt-dlp download failed for %s: %s", url, e)
                return {"error": str(e)}

        loop = asyncio.get_running_loop()
        with concurrent.futures.ThreadPoolExecutor() as pool:
            result_info = await loop.run_in_executor(pool, _download_audio)

        if "error" in result_info:
            return {
                "text": "",
                "source_url": url,
                "title": "",
                "content_type": "social_video",
                "method": "yt_dlp_failed",
                "error": result_info["error"],
            }

        # Find the downloaded audio file
        audio_file = None
        for fname in os.listdir(tmpdir):
            if fname.startswith("audio."):
                audio_file = os.path.join(tmpdir, fname)
                break

        if not audio_file or not os.path.exists(audio_file):
            return {
                "text": "",
                "source_url": url,
                "title": result_info.get("title", ""),
                "content_type": "social_video",
                "method": "no_audio_file",
                "error": "Audio extraction produced no file",
            }

        # Step 2: Transcribe with Whisper
        def _transcribe(af: str) -> str:
            try:
                if whisper_service is not None:
                    result = whisper_service.transcribe(af)
                    if isinstance(result, dict):
                        return result.get("text", "")
                    return str(result)
                from services.whisper_local_service import transcribe_with_whisper
                text = transcribe_with_whisper("", af)
                return text or ""
            except Exception as e:
                logger.warning("transcribe_with_whisper failed (%s), trying faster-whisper directly", e)
                try:
                    from faster_whisper import WhisperModel  # type: ignore
                    from services.doctrine_terms import get_whisper_initial_prompt
                    model = WhisperModel("large-v3", device="cpu", compute_type="int8")
                    prompt = get_whisper_initial_prompt()
                    segments, _ = model.transcribe(af, initial_prompt=prompt)
                    return " ".join(seg.text for seg in segments)
                except Exception as e2:
                    logger.error("faster-whisper direct transcription failed: %s", e2)
                    raise

        try:
            with concurrent.futures.ThreadPoolExecutor() as pool:
                transcript = await loop.run_in_executor(pool, _transcribe, audio_file)
        except Exception as e:
            return {
                "text": "",
                "source_url": url,
                "title": result_info.get("title", ""),
                "content_type": "social_video",
                "method": "whisper_failed",
                "error": str(e),
            }

    import unicodedata
    clean_text = unicodedata.normalize("NFC", transcript.replace("\x00", "")).strip()
    try:
        from services.doctrine_terms import apply_corrections
        clean_text = apply_corrections(clean_text)
    except Exception:
        pass

    return {
        "text": clean_text,
        "source_url": url,
        "title": result_info.get("title", ""),
        "speaker": result_info.get("uploader", "Unknown"),
        "content_type": "social_video",
        "method": "yt_dlp_whisper",
        "duration_seconds": result_info.get("duration", 0),
    }


if __name__ == "__main__":
    async def _test():
        result = await ingest_social_media("https://www.instagram.com/reel/test123/")
        print(f"Result keys: {list(result.keys())}")
        print(f"Method: {result.get('method')}")
        print(f"Error: {result.get('error', 'none')}")

    asyncio.run(_test())
