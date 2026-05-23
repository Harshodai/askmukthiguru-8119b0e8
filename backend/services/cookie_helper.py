"""
Mukthi Guru — YouTube Cookie Automation Helper

Automates unlocking the macOS keychain and extracting cookies from Chrome or Safari
using yt-dlp, resolving any keychain password prompts automatically.
"""

import logging
import os
import platform
import subprocess

logger = logging.getLogger(__name__)

# Primary location for cookies file
COOKIES_PATH = "/Users/harshodaikolluru/Public/askmukthiguru-8119b0e8/cookies.txt"
# Keychain password — loaded from env to keep secrets out of source code.
# Set KEYCHAIN_PASS in backend/.env (gitignored).
KEYCHAIN_PASS = os.environ.get("KEYCHAIN_PASS", "")
if not KEYCHAIN_PASS:
    logger.warning(
        "KEYCHAIN_PASS env var not set — keychain unlock may fail. "
        "Add 'KEYCHAIN_PASS=<your_login_password>' to backend/.env"
    )


def unlock_keychain() -> bool:
    """
    Attempt to unlock the macOS login keychain using the user's password.
    This prevents interactive GUI prompts when yt-dlp accesses Chrome cookies.
    """
    try:
        if platform.system() != "Darwin":
            logger.info("Non-macOS environment detected. Skipping keychain unlock.")
            return False

        logger.info("Attempting to unlock macOS login keychain...")

        # Paths to search for the login keychain on macOS
        possible_keychains = [
            os.path.expanduser("~/Library/Keychains/login.keychain-db"),
            os.path.expanduser("~/Library/Keychains/login.keychain"),
            "login.keychain-db",
            "login.keychain",
        ]

        success = False
        for kc in possible_keychains:
            # If it's a relative default name or the absolute path exists
            if kc in ["login.keychain-db", "login.keychain"] or os.path.exists(kc):
                logger.info(f"Unlocking keychain: {kc}")
                cmd = ["security", "unlock-keychain", "-p", KEYCHAIN_PASS, kc]
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
                if result.returncode == 0:
                    logger.info(f"Successfully unlocked keychain: {kc}")
                    success = True
                else:
                    logger.warning(f"Failed to unlock {kc}: {result.stderr.strip()}")

        # Fallback to default keychain if none of the specific paths succeeded
        if not success:
            logger.info("Falling back to unlocking default keychain...")
            cmd = ["security", "unlock-keychain", "-p", KEYCHAIN_PASS]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                logger.info("Successfully unlocked default keychain.")
                success = True

        return success
    except Exception as e:
        logger.warning(f"Error unlocking keychain: {e}")
        return False


def ensure_cookies_file(force_refresh: bool = False) -> str | None:
    """
    Ensure a valid cookies.txt file exists. If missing or force_refresh=True,
    it unlocks the macOS keychain and extracts cookies from Chrome using yt-dlp.
    """
    # If file exists and we are not forcing a refresh, return it
    if not force_refresh and os.path.exists(COOKIES_PATH) and os.path.getsize(COOKIES_PATH) > 1000:
        return COOKIES_PATH

    logger.info(f"Generating/Refreshing cookies.txt (force_refresh={force_refresh})...")

    # First unlock the keychain so yt-dlp can access Chrome safe storage
    unlock_keychain()

    # Locate host yt-dlp in the host virtual environment
    yt_dlp_path = "/Users/harshodaikolluru/Public/askmukthiguru-8119b0e8/.venv_host/bin/yt-dlp"
    if not os.path.exists(yt_dlp_path):
        logger.info("venv host yt-dlp not found, falling back to system yt-dlp")
        yt_dlp_path = "yt-dlp"

    test_url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"

    cmd = [
        yt_dlp_path,
        "--cookies-from-browser",
        "chrome",
        "--cookies",
        COOKIES_PATH,
        "--skip-download",
        "--ignore-errors",
        "--no-warnings",
        test_url,
    ]

    try:
        logger.info("Running yt-dlp to extract cookies from Chrome...")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

        # Check if cookie file was successfully written/updated (even if yt-dlp exited with non-zero due to format errors)
        if os.path.exists(COOKIES_PATH) and os.path.getsize(COOKIES_PATH) > 1000:
            logger.info(f"Successfully generated/verified cookies.txt at {COOKIES_PATH}")
            return COOKIES_PATH
        else:
            logger.warning(
                f"Chrome cookie extraction failed (code {result.returncode}): {result.stderr.strip()}"
            )

            # Fallback to Safari cookies
            logger.info("Attempting fallback to Safari cookies...")
            fallback_cmd = [
                yt_dlp_path,
                "--cookies-from-browser",
                "safari",
                "--cookies",
                COOKIES_PATH,
                "--skip-download",
                "--ignore-errors",
                "--no-warnings",
                test_url,
            ]
            fallback_res = subprocess.run(fallback_cmd, capture_output=True, text=True, timeout=30)
            if os.path.exists(COOKIES_PATH) and os.path.getsize(COOKIES_PATH) > 1000:
                logger.info("Successfully generated cookies.txt from Safari")
                return COOKIES_PATH
            else:
                logger.error(f"Safari cookie extraction also failed: {fallback_res.stderr.strip()}")
    except Exception as e:
        logger.error(f"Exception during cookie extraction: {e}")

    # If extraction failed but file exists, return the existing file as fallback
    if os.path.exists(COOKIES_PATH) and os.path.getsize(COOKIES_PATH) > 1000:
        logger.warning("Using existing cookies.txt file despite generation failure")
        return COOKIES_PATH

    return None
