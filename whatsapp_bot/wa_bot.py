"""
AskMukthiGuru WhatsApp Bot — Production Bridge Service
======================================================

Flask service that bridges WhatsApp (Twilio and Meta Cloud API) <-> /api/chat.

Capabilities:
  1. Dual-Provider Inbound Webhooks:
     - Twilio WhatsApp: /whatsapp/twilio and /twilio/whatsapp
     - Meta Cloud API:  /whatsapp/meta and /meta/whatsapp (GET verification & POST events)
  2. Fail-Closed Cryptographic Signature Verification:
     - Twilio: X-Twilio-Signature validation via RequestValidator / RFC HMAC-SHA1
     - Meta:   X-Hub-Signature-256 validation via HMAC-SHA256
  3. Immediate Webhook Acknowledgment (<15s Deadline):
     - Webhooks acknowledged with empty TwiML or 200 OK immediately
     - Chat pipeline processing and queue polling runs in background thread
     - Answers sent via outbound provider REST APIs (Twilio Client / Meta Graph API)
  4. Anonymous Session Identity (per-phone quota parity with web chat):
     - One server-signed anon token per phone (`POST /api/auth/anon-session`),
       persisted in SQLite and sent as `session_id` (chat POST) /
       `X-Session-Id` (job poll), so backend quotas and job ownership work
       exactly as they do for anonymous web seekers. The legacy HS256 JWT
       (`mint_jwt`) is retained for compatibility but is no longer sent.
  5. Robust Markdown -> WhatsApp Formatting:
     - **bold** -> *bold*
     - [Title](url) -> Title (url) clickable URLs
     - Header formatting and bullet points
     - Complete preservation of Indian crisis helplines (Tele-MANAS 14416, 112)
  6. Per-Phone State Tracking:
     - Short-lived anon token + SQLite conversation history and meditation steps
     - RESET / HELP commands, per-phone rate limiting, Indic language detection
     - Non-text inbound (voice notes, images, files) gets an honest decline —
       never a silent drop.
"""

from __future__ import annotations

import base64
import collections
import hashlib
import hmac
import html
import json
import logging
import os
import re
import sqlite3
import threading
import time
import urllib.parse
from contextlib import closing
from pathlib import Path
from typing import Any

import jwt
import requests
from flask import Flask, abort, jsonify, request

try:
    from twilio.request_validator import RequestValidator
    from twilio.rest import Client as TwilioClient
except ImportError:
    RequestValidator = None  # type: ignore
    TwilioClient = None  # type: ignore

# ---------------------------------------------------------------------------
# Config (env-driven with safe fallbacks)
# ---------------------------------------------------------------------------
API_URL = os.getenv(
    "ASKMUKTHIGURU_API_URL", os.getenv("BACKEND_URL", "http://localhost:8000")
).rstrip("/")
JWT_SECRET = os.getenv("JWT_SECRET", "default-dev-jwt-secret")

# Twilio Configuration
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "")
TWILIO_FROM = os.getenv("TWILIO_FROM", "")

# Meta Cloud API Configuration
META_APP_SECRET = os.getenv("META_APP_SECRET", "")
META_VERIFY_TOKEN = os.getenv("META_VERIFY_TOKEN", os.getenv("VERIFY_TOKEN", ""))
META_ACCESS_TOKEN = os.getenv("META_ACCESS_TOKEN", os.getenv("WHATSAPP_TOKEN", ""))
META_PHONE_NUMBER_ID = os.getenv("META_PHONE_NUMBER_ID", "")

# App Configuration
WA_DB_PATH = os.getenv("WA_DB_PATH", "./wa_state.db")
WA_CHAT_TIMEOUT_S = int(os.getenv("WA_CHAT_TIMEOUT_S", "60"))
WA_HISTORY_LIMIT = int(os.getenv("WA_HISTORY_LIMIT", "10"))
CACHE_TTL_SECONDS = int(os.getenv("WA_CACHE_TTL_SECONDS", "1800"))
MAX_MSG_LENGTH = 4096
ASYNC_WEBHOOK_ACK = os.getenv("WA_ASYNC_ACK", "true").lower() == "true"

# Per-phone inbound rate limit: max turns forwarded to the backend per window.
# Anonymous web chat shares the backend 20/minute limiter by egress IP, so a
# single WA number must never be able to burn the shared budget alone.
WA_RATE_LIMIT_COUNT = int(os.getenv("WA_RATE_LIMIT_COUNT", "10"))
WA_RATE_LIMIT_WINDOW_S = int(os.getenv("WA_RATE_LIMIT_WINDOW_S", "60"))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s | %(message)s")
log = logging.getLogger("wa_bot")


def sanitize_log_input(val: Any) -> str:
    """Sanitize user input to prevent log injection (CWE-117)."""
    return str(val).replace("\r", "").replace("\n", " ")[:200]


app = Flask(__name__)


# ---------------------------------------------------------------------------
# Persistence (SQLite)
# ---------------------------------------------------------------------------
SCHEMA = """
CREATE TABLE IF NOT EXISTS wa_messages (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  phone           TEXT NOT NULL,
  role            TEXT NOT NULL CHECK (role IN ('user','assistant')),
  content         TEXT NOT NULL,
  created_at      INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_wa_phone_time ON wa_messages(phone, created_at DESC, id DESC);

CREATE TABLE IF NOT EXISTS wa_state (
  phone               TEXT PRIMARY KEY,
  meditation_step     INTEGER NOT NULL DEFAULT 0,
  last_serene_at      INTEGER,
  language            TEXT NOT NULL DEFAULT 'en',
  consented           INTEGER NOT NULL DEFAULT 0,
  opted_out            INTEGER NOT NULL DEFAULT 0,
  updated_at          INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS wa_auth (
  phone               TEXT PRIMARY KEY,
  token               TEXT NOT NULL,
  updated_at          INTEGER NOT NULL
);
"""


def _db() -> sqlite3.Connection:
    Path(WA_DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(WA_DB_PATH, isolation_level=None)
    conn.row_factory = sqlite3.Row
    return conn


def _init_db() -> None:
    with closing(_db()) as conn:
        conn.executescript(SCHEMA)
        # Existing DBs predate the consent columns: add them idempotently.
        for col in ("consented INTEGER NOT NULL DEFAULT 0", "opted_out INTEGER NOT NULL DEFAULT 0"):
            try:
                conn.execute(f"ALTER TABLE wa_state ADD COLUMN {col}")
            except Exception:
                pass  # column already present


def _prune_db() -> None:
    cutoff = int(time.time()) - CACHE_TTL_SECONDS
    with closing(_db()) as conn:
        conn.execute("DELETE FROM wa_messages WHERE created_at < ?", (cutoff,))


def history_for(phone: str, limit: int = WA_HISTORY_LIMIT) -> list[dict]:
    """Return last `limit` messages in chronological order (oldest first)."""
    _prune_db()
    with closing(_db()) as conn:
        rows = conn.execute(
            "SELECT role, content FROM wa_messages WHERE phone=? "
            "ORDER BY created_at DESC, id DESC LIMIT ?",
            (phone, limit),
        ).fetchall()
    return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]


def append_message(phone: str, role: str, content: str) -> None:
    with closing(_db()) as conn:
        conn.execute(
            "INSERT INTO wa_messages (phone, role, content, created_at) VALUES (?, ?, ?, ?)",
            (phone, role, content, int(time.time())),
        )


def state_for(phone: str) -> dict:
    with closing(_db()) as conn:
        row = conn.execute(
            "SELECT meditation_step, last_serene_at, language, "
            "COALESCE(consented, 0) AS consented, COALESCE(opted_out, 0) AS opted_out "
            "FROM wa_state WHERE phone=?",
            (phone,),
        ).fetchone()
    if row is None:
        return {
            "meditation_step": 0,
            "last_serene_at": None,
            "language": "en",
            "consented": 0,
            "opted_out": 0,
        }
    return dict(row)


def update_state(
    phone: str,
    *,
    meditation_step: int,
    last_serene_at: int | None,
    language: str = "en",
    consented: int | None = None,
    opted_out: int | None = None,
) -> None:
    # None means "keep": read the current row so an explicit NULL never hits
    # the NOT NULL columns (and an existing 1 is never reset by a caller that
    # only updates meditation/language state).
    cur = state_for(phone)
    if consented is None:
        consented = int(cur.get("consented", 0) or 0)
    if opted_out is None:
        opted_out = int(cur.get("opted_out", 0) or 0)
    with closing(_db()) as conn:
        conn.execute(
            "INSERT INTO wa_state (phone, meditation_step, last_serene_at, language, "
            "consented, opted_out, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(phone) DO UPDATE SET "
            "  meditation_step=excluded.meditation_step, "
            "  last_serene_at=COALESCE(excluded.last_serene_at, wa_state.last_serene_at), "
            "  language=excluded.language, "
            "  consented=COALESCE(excluded.consented, wa_state.consented), "
            "  opted_out=COALESCE(excluded.opted_out, wa_state.opted_out), "
            "  updated_at=excluded.updated_at",
            (
                phone,
                meditation_step,
                last_serene_at,
                language,
                consented,
                opted_out,
                int(time.time()),
            ),
        )


def clear_conversation(phone: str) -> None:
    """Wipe local history and meditation state for a phone (RESET command).

    The anon session token is kept so backend quota identity stays stable.
    Consent/opt-out survive a RESET (only STOP revokes consent).
    """
    clean = sanitize_phone(phone)
    keep = state_for(clean)
    with closing(_db()) as conn:
        conn.execute("DELETE FROM wa_messages WHERE phone=?", (clean,))
        conn.execute("DELETE FROM wa_state WHERE phone=?", (clean,))
    update_state(
        clean,
        meditation_step=0,
        last_serene_at=None,
        language=str(keep.get("language") or "en"),
        consented=int(keep.get("consented", 0) or 0),
        opted_out=int(keep.get("opted_out", 0) or 0),
    )


# ---------------------------------------------------------------------------
# Anonymous session identity (per-phone quota parity with web chat)
# ---------------------------------------------------------------------------
def get_stored_anon_token(phone: str) -> str | None:
    clean = sanitize_phone(phone)
    with closing(_db()) as conn:
        row = conn.execute("SELECT token FROM wa_auth WHERE phone=?", (clean,)).fetchone()
    return str(row["token"]) if row and row["token"] else None


def store_anon_token(phone: str, token: str) -> None:
    clean = sanitize_phone(phone)
    with closing(_db()) as conn:
        conn.execute(
            "INSERT INTO wa_auth (phone, token, updated_at) VALUES (?, ?, ?) "
            "ON CONFLICT(phone) DO UPDATE SET token=excluded.token, "
            "updated_at=excluded.updated_at",
            (clean, token, int(time.time())),
        )


def invalidate_anon_token(phone: str) -> None:
    with closing(_db()) as conn:
        conn.execute("DELETE FROM wa_auth WHERE phone=?", (sanitize_phone(phone),))


def ensure_anon_token(phone: str) -> str:
    """Return the persisted per-phone anon token, issuing one if absent.

    The backend signs tokens at POST /api/auth/anon-session; the bot echoes
    the token back as `session_id` (chat POST) and `X-Session-Id` (job poll)
    so quotas and job ownership resolve exactly as for anonymous web seekers.
    Raises on transport failure — callers map that to honest failure copy.
    """
    clean = sanitize_phone(phone)
    cached = get_stored_anon_token(clean)
    if cached:
        return cached
    resp = requests.post(f"{API_URL}/api/auth/anon-session", timeout=5)
    resp.raise_for_status()
    token = str((resp.json() or {}).get("token") or "").strip()
    if not token or "." not in token:
        raise ValueError("anon-session endpoint returned a malformed token")
    store_anon_token(clean, token)
    return token


# ---------------------------------------------------------------------------
# Per-phone rate limiting (in-memory sliding window)
# ---------------------------------------------------------------------------
_rate_buckets: dict[str, collections.deque[float]] = {}
_rate_lock = threading.Lock()

# ---------------------------------------------------------------------------
# Per-phone crisis processing capacity (RP-C1 companion)
# ---------------------------------------------------------------------------
# Crisis messages bypass is_rate_limited, but repeated matches must not trigger
# unbounded backend calls. A small per-phone in-flight counter caps concurrent
# crisis turns without blocking the local helpline footer response.
WA_CRISIS_CAPACITY = int(os.getenv("WA_CRISIS_CAPACITY", "3"))
_crisis_in_flight: dict[str, int] = {}
_crisis_lock = threading.Lock()


def _crisis_capacity_acquire(phone: str) -> bool:
    """Claim one crisis in-flight slot; return True if acquired, False if full."""
    with _crisis_lock:
        current = _crisis_in_flight.get(phone, 0)
        if current >= WA_CRISIS_CAPACITY:
            return False
        _crisis_in_flight[phone] = current + 1
        return True


def _crisis_capacity_release(phone: str) -> None:
    """Release one crisis in-flight slot; drop the entry at zero so the
    per-phone map cannot grow without bound."""
    with _crisis_lock:
        remaining = _crisis_in_flight.get(phone, 0) - 1
        if remaining <= 0:
            _crisis_in_flight.pop(phone, None)
        else:
            _crisis_in_flight[phone] = remaining


def reset_rate_limits() -> None:
    """Clear all rate-limit buckets. Tests only."""
    with _rate_lock:
        _rate_buckets.clear()


def _rate_limit_cfg() -> tuple[int, int]:
    try:
        count = int(os.getenv("WA_RATE_LIMIT_COUNT", str(WA_RATE_LIMIT_COUNT)))
    except ValueError:
        count = WA_RATE_LIMIT_COUNT
    try:
        window = int(os.getenv("WA_RATE_LIMIT_WINDOW_S", str(WA_RATE_LIMIT_WINDOW_S)))
    except ValueError:
        window = WA_RATE_LIMIT_WINDOW_S
    return max(1, count), max(1, window)


def is_rate_limited(phone: str) -> bool:
    """True when this phone exhausted its backend-turn budget for the window."""
    clean = sanitize_phone(phone)
    count, window = _rate_limit_cfg()
    now = time.time()
    with _rate_lock:
        bucket = _rate_buckets.setdefault(clean, collections.deque())
        while bucket and bucket[0] <= now - window:
            bucket.popleft()
        if len(bucket) >= count:
            return True
        bucket.append(now)
        return False


# ---------------------------------------------------------------------------
# Indic script detection (per-turn language parity with chat preferences)
# ---------------------------------------------------------------------------
_SCRIPT_LANG_COUNTS: tuple[tuple[str, tuple[tuple[int, int], ...]], ...] = (
    ("hi", ((0x0900, 0x097F),)),  # Devanagari; mr shares the script, hi is the default
    ("bn", ((0x0980, 0x09FF),)),
    ("pa", ((0x0A00, 0x0A7F),)),
    ("gu", ((0x0A80, 0x0AFF),)),
    ("or", ((0x0B00, 0x0B7F),)),
    ("ta", ((0x0B80, 0x0BFF),)),
    ("te", ((0x0C00, 0x0C7F),)),
    ("kn", ((0x0C80, 0x0CFF),)),
    ("ml", ((0x0D00, 0x0D7F),)),
    ("ur", ((0x0600, 0x06FF),)),
)


def detect_language(text: str) -> str | None:
    """Return an Indic language code when the text is dominated by its script.

    Latin-script text returns None (caller keeps the stored preference).
    Static script ranges only — no network, no model, no threshold coupling
    with backend safety stages.
    """
    counts: dict[str, int] = {}
    for ch in text or "":
        code = ord(ch)
        for lang, ranges in _SCRIPT_LANG_COUNTS:
            if any(lo <= code <= hi for lo, hi in ranges):
                counts[lang] = counts.get(lang, 0) + 1
                break
    if not counts:
        return None
    best, best_n = max(counts.items(), key=lambda kv: kv[1])
    return best if best_n >= 3 else None


# ---------------------------------------------------------------------------
# Crisis fail-safe footer (backend-unreachable path ONLY)
# ---------------------------------------------------------------------------
# Minimal severe-phrase screen used solely to pick failure copy when the
# backend cannot be reached. It never replaces or re-thresholds the backend
# DistressStage: when the backend answers, its reviewed crisis copy is
# delivered verbatim. Static list, no LLM, no translation.
_CRISIS_FAILSAFE_RE = re.compile(
    r"suicid|kill\s+(myself|me)|end\s+(my|this)\s+life|self[-\s]?harm|hurt\s+myself|"
    r"want\s+to\s+die|wish\s+i\s+(were\s+dead|could\s+die)|no\s+reason\s+to\s+live|"
    r"going\s+to\s+hurt\s+(myself|me\b)|harm\s+my\s*self|"
    r"आत्महत्या|ಆತ್ಮಹತ್ಯೆ|ఆత్మహత్య|தற்கொலை|ആത്മഹത്യ|আত্মহত্যা|atmahatya|"
    r"जीव\s+देणे",  # Marathi idiom (review P2-2, 2026-10-13; cf. distress_stage.py)
    re.IGNORECASE,
)
_HELPLINE_FOOTER = (
    "If you are in distress, help is available right now: "
    "Tele-MANAS (India, 24x7 toll-free): 14416; "
    "Emergency: 112."
)
# NOTE (RP-C2/QBUG-1, 2026-10-13): KIRAN 1800-599-0019 was removed here on the
# owner's QO-2 ruling — the registry (config/helplines.yaml) records it as
# merged into Tele-MANAS. Only 24/7 lines are listed (RP-C8: iCall is not
# 24/7). Every number above must exist in config/helplines.yaml — enforced by
# test_no_withdrawn_kiran_number_in_bot_copy. Full yaml-driven footer needs a
# yaml parser in whatsapp_bot/requirements.txt (owner decision, new dep).


def likely_crisis(text: str) -> bool:
    """Fail-safe screen for the backend-unreachable path only."""
    return bool(text and _CRISIS_FAILSAFE_RE.search(text))


def with_helplines_if_crisis(copy: str, user_message: str) -> str:
    if likely_crisis(user_message):
        return f"{copy}\n\n{_HELPLINE_FOOTER}"
    return copy


# ---------------------------------------------------------------------------
# Local commands (no backend call, no quota burn)
# ---------------------------------------------------------------------------
RESET_WORDS = frozenset({"RESET", "RESTART", "CLEAR", "START", "RESET CHAT"})
STOP_WORDS = frozenset({"STOP", "STOP ALL", "UNSUBSCRIBE", "CANCEL", "END"})
YES_WORDS = frozenset({"YES", "Y", "YEAH", "OK", "OKAY", "AGREE", "I AGREE", "CONSENT", "SURE"})

# T-C8 consent gate (18+, self-declared like the web checkbox; lawyer view pending).
CONSENT_COPY = (
    "🙏 Welcome to AskMukthiGuru on WhatsApp — verbatim teachings of "
    "Sri Preethaji & Sri Krishnaji.\n\n"
    "Reply YES to receive teachings (18+ only; chats are stored to answer you). "
    "Reply STOP to opt out anytime."
)
CONSENT_WELCOME_COPY = "🙏 Thank you — you are opted in. What would you like to ask about?"
STOP_COPY = (
    "You are opted out — no further teachings will be sent. "
    "Reply START anytime to opt back in. In distress? Tele-MANAS (24x7): 14416."
)
OPTED_OUT_COPY = (
    "You are opted out. Reply START to opt back in, or HELP for options. "
    "In distress? Tele-MANAS (24x7): 14416."
)
HELP_WORDS = frozenset({"HELP", "MENU", "COMMANDS", "INFO"})

HELP_COPY = (
    "🙏 *AskMukthiGuru on WhatsApp*\n\n"
    "• Type any spiritual question as text and I will answer from the teachings.\n"
    "• I can't open photos, voice notes, or files yet — please type your question.\n"
    "• Send RESET to clear this chat and start fresh.\n\n"
    "In distress? Tele-MANAS (24x7): 14416. Emergency: 112."
)
RESET_COPY = (
    "🧹 Fresh page. Your WhatsApp conversation history was cleared. What would you like to ask?"
)


def _is_rate_limit_exempt(word: str, clean_phone: str = "") -> bool:
    """True when `word` must bypass the per-phone rate limiter.

    Local commands and consent words are served without any backend call,
    so limiting them only skews the budget bookkeeping — worse, it can
    swallow consent itself: STOP opts out, START opts back in. RESET_WORDS
    already covers START, but the exemption is spelled out explicitly so
    consent never depends on that overlap. YES is exempt only while consent
    is still pending for this phone (it opts in); once consented it is an
    ordinary message and spends the rate-limit budget like any other.
    Crisis is handled separately via likely_crisis at the call sites.
    """
    upper = (word or "").strip().upper()
    if upper in RESET_WORDS or upper in HELP_WORDS or upper in STOP_WORDS or upper == "START":
        return True
    if upper in YES_WORDS:
        return not bool(state_for(clean_phone).get("consented"))
    return False


# ---------------------------------------------------------------------------
# Phone Normalization & JWT Minting
# ---------------------------------------------------------------------------
def sanitize_phone(phone: str) -> str:
    """Normalize phone number: strip whitespace, whatsapp: prefix, keeping + and digits."""
    clean = str(phone or "").replace("whatsapp:", "").strip()
    clean = re.sub(r"[^\d+]", "", clean)
    return clean or str(phone).strip()


def mint_jwt(phone: str) -> str:
    """Mint an HS256 JWT (legacy).

    Retained for compatibility: existing tooling and tests pin this shape
    (sub=wa-<phone>). The live chat path no longer sends it — the backend
    only trusts Supabase-issued tokens, so WhatsApp turns travel as signed
    anonymous sessions (see ensure_anon_token) with per-phone quota parity.
    """
    clean = sanitize_phone(phone)
    now = int(time.time())
    secret = os.getenv("JWT_SECRET", JWT_SECRET)
    payload = {
        "sub": f"wa-{clean}",
        "email": f"wa-{clean.replace('+', '')}@bot.local",
        "role": "authenticated",
        "iat": now,
        "exp": now + 3600,
        "iss": "askmukthiguru-wa-bot",
    }
    return jwt.encode(payload, secret, algorithm="HS256")


# ---------------------------------------------------------------------------
# Markdown -> WhatsApp Formatting & Crisis Preservation
# ---------------------------------------------------------------------------
def md_to_wa(text: str) -> str:
    """
    Convert markdown to WhatsApp-compatible formatting.
    Preserves all numbers, helpline referrals, and contact details intact.
    """
    if not text:
        return ""

    # 1. Convert markdown headers: ### Header -> *Header*
    text = re.sub(r"^(?:#{1,6})\s*(.+?)$", r"*\1*", text, flags=re.MULTILINE)

    # 2. Convert bold: **text** -> *text*
    text = re.sub(r"\*\*(.+?)\*\*", r"*\1*", text)

    # 3. Convert underline/italic: __text__ -> _text_
    text = re.sub(r"__(.+?)__", r"_\1_", text)

    # 4. Convert markdown links: [Title](url) -> Title (url)
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1 (\2)", text)

    # 5. Clean triple backtick code blocks while preserving inline code
    text = re.sub(r"```[a-zA-Z0-9_-]*\n?", "", text)

    # 6. Normalize bullet points: lines starting with '* ' or '- ' -> '• '
    text = re.sub(r"^\s*[-*]\s+", "• ", text, flags=re.MULTILINE)

    # 7. Strip blockquote markers: '> text' -> text
    text = re.sub(r"^\s*>\s*", "", text, flags=re.MULTILINE)

    return text.strip()


def normalize_citations(citations: Any) -> list[str]:
    """Normalize backend citations to short WhatsApp-safe source lines.

    The backend returns Citation objects ({url, title, ...}); older mocks
    and caches may carry plain strings. Dicts render as "Title (url)".
    """
    if not citations:
        return []
    if isinstance(citations, dict):
        citations = [citations]
    out: list[str] = []
    for c in citations:
        if isinstance(c, dict):
            url = str(c.get("url") or "").strip()
            title = str(c.get("title") or "").strip()
            if not url:
                continue
            out.append(f"{title} ({url})" if title else url)
        elif isinstance(c, str) and c.strip():
            out.append(c.strip())
    return out[:3]


def with_citations(text: str, citations: list[str]) -> str:
    """Format and append up to 3 top citations with clean WhatsApp bullets."""
    top = normalize_citations(citations)
    if not top:
        return text
    return text + "\n\n📜 *Sources:*\n" + "\n".join(f"• {c}" for c in top)


def format_whatsapp_response(raw_text: str, citations: list[str] | None = None) -> str:
    formatted = md_to_wa(raw_text or "")
    return with_citations(formatted, citations or [])


def _chunk_text(text: str, max_length: int = MAX_MSG_LENGTH) -> list[str]:
    """Smart text chunker that splits at paragraph or sentence breaks without truncating."""
    if not text:
        return []
    if len(text) <= max_length:
        return [text]

    chunks = []
    remaining = text
    while len(remaining) > max_length:
        # Try paragraph break
        split_idx = remaining.rfind("\n\n", 0, max_length)
        if split_idx == -1:
            # Try newline break
            split_idx = remaining.rfind("\n", 0, max_length)
        if split_idx == -1:
            # Try sentence or word break
            split_idx = remaining.rfind(" ", 0, max_length)
        if split_idx == -1 or split_idx < max_length // 2:
            split_idx = max_length

        chunk = remaining[:split_idx].strip()
        if chunk:
            chunks.append(chunk)
        remaining = remaining[split_idx:].strip()

    if remaining:
        chunks.append(remaining)
    return chunks


# ---------------------------------------------------------------------------
# Cryptographic Signature Verification (Fail-Closed)
# ---------------------------------------------------------------------------
def compute_twilio_signature(url: str, params: dict[str, str], auth_token: str) -> str:
    """Compute Twilio signature per official RFC specification."""
    s = url + "".join(f"{k}{params[k]}" for k in sorted(params.keys()))
    mac = hmac.new(auth_token.encode("utf-8"), s.encode("utf-8"), hashlib.sha1)
    return base64.b64encode(mac.digest()).decode("utf-8")


def validate_twilio_signature(req) -> bool:
    """Validates X-Twilio-Signature against TWILIO_AUTH_TOKEN."""
    token = os.getenv("TWILIO_AUTH_TOKEN", TWILIO_AUTH_TOKEN)
    if not token:
        log.error("TWILIO_AUTH_TOKEN is not configured; rejecting request.")
        return False

    signature = req.headers.get("X-Twilio-Signature", "")
    if not signature:
        return False

    params = req.form.to_dict()
    url = req.url

    # Check via twilio library if available
    if RequestValidator is not None:
        validator = RequestValidator(token)
        if validator.validate(url, params, signature):
            return True
        proto = req.headers.get("X-Forwarded-Proto")
        host = req.headers.get("X-Forwarded-Host", req.host)
        if proto:
            forwarded_url = f"{proto}://{host}{req.full_path.rstrip('?')}"
            if validator.validate(forwarded_url, params, signature):
                return True
        return False

    # Native Python HMAC-SHA1 fallback
    expected_sig = compute_twilio_signature(url, params, token)
    if hmac.compare_digest(expected_sig, signature):
        return True

    proto = req.headers.get("X-Forwarded-Proto")
    host = req.headers.get("X-Forwarded-Host", req.host)
    if proto:
        forwarded_url = f"{proto}://{host}{req.full_path.rstrip('?')}"
        expected_fwd = compute_twilio_signature(forwarded_url, params, token)
        if hmac.compare_digest(expected_fwd, signature):
            return True

    return False


def validate_meta_signature(req) -> bool:
    """Validates X-Hub-Signature-256 against META_APP_SECRET."""
    secret = os.getenv("META_APP_SECRET", META_APP_SECRET)
    if not secret:
        log.error("META_APP_SECRET is not configured; rejecting request.")
        return False

    header_sig = req.headers.get("X-Hub-Signature-256", "")
    if not header_sig or not header_sig.startswith("sha256="):
        return False

    expected_sig = header_sig[7:].strip()
    raw_body = req.get_data()
    computed_sig = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(computed_sig, expected_sig)


# ---------------------------------------------------------------------------
# Outbound Message Senders (Twilio REST & Meta Graph API)
# ---------------------------------------------------------------------------
_ALLOWED_META_HOST = "graph.facebook.com"
_PHONE_NUMBER_ID_RE = re.compile(r"^\d{1,32}$")


def push_twilio_message(to_number: str, body_text: str, from_number: str | None = None) -> bool:
    """Send WhatsApp message using Twilio REST API."""
    account_sid = os.getenv("TWILIO_ACCOUNT_SID", TWILIO_ACCOUNT_SID)
    auth_token = os.getenv("TWILIO_AUTH_TOKEN", TWILIO_AUTH_TOKEN)
    sender = from_number or os.getenv("TWILIO_FROM", TWILIO_FROM)

    if not account_sid or not auth_token or not sender:
        log.error(
            "Missing Twilio credentials (ACCOUNT_SID, AUTH_TOKEN, or FROM); cannot send outbound message"
        )
        return False

    clean_to = sanitize_phone(to_number)
    target = (
        f"whatsapp:{clean_to}" if not str(to_number).startswith("whatsapp:") else str(to_number)
    )
    source = f"whatsapp:{sender}" if not str(sender).startswith("whatsapp:") else str(sender)

    chunks = _chunk_text(body_text)

    # 1. Twilio Client if installed
    if TwilioClient is not None:
        try:
            client = TwilioClient(account_sid, auth_token)
            for chunk in chunks:
                client.messages.create(body=chunk, from_=source, to=target)
            log.info("Sent Twilio message to %s", sanitize_log_input(target))
            return True
        except Exception as e:
            log.warning(
                "TwilioClient send failed; attempting REST fallback: %s", sanitize_log_input(e)
            )

    # 2. Direct HTTP REST fallback
    try:
        url = f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json"
        for chunk in chunks:
            resp = requests.post(
                url,
                data={"From": source, "To": target, "Body": chunk},
                auth=(account_sid, auth_token),
                timeout=10,
            )
            resp.raise_for_status()
        log.info("Sent Twilio message via REST fallback to %s", sanitize_log_input(target))
        return True
    except Exception as e:
        log.exception("Failed to send message via Twilio REST API: %s", sanitize_log_input(e))
        return False


def push_meta_message(
    phone_number_id: str,
    to_number: str,
    body_text: str,
    access_token: str | None = None,
) -> bool:
    """Send WhatsApp message using Meta Cloud API with strict SSRF guards."""
    token = access_token or os.getenv("META_ACCESS_TOKEN", META_ACCESS_TOKEN)
    if not token:
        log.error("Missing META_ACCESS_TOKEN; cannot send outbound Meta message")
        return False

    clean_id = str(
        phone_number_id or os.getenv("META_PHONE_NUMBER_ID", META_PHONE_NUMBER_ID)
    ).strip()
    if not clean_id.isdigit() or not _PHONE_NUMBER_ID_RE.match(clean_id):
        log.error("Invalid phone_number_id format rejected: %s", sanitize_log_input(clean_id))
        return False

    url = f"https://graph.facebook.com/v18.0/{int(clean_id)}/messages"
    parsed = urllib.parse.urlparse(url)
    if (
        parsed.scheme != "https"
        or parsed.netloc.lower() != "graph.facebook.com"
        or not parsed.path.startswith("/v18.0/")
        or not parsed.path.endswith("/messages")
    ):
        log.error("SSRF guard rejected Meta API request URL: %s", sanitize_log_input(url))
        return False

    clean_to = sanitize_phone(to_number)
    chunks = _chunk_text(body_text)
    all_ok = True
    for chunk in chunks:
        try:
            resp = requests.post(
                url,
                json={
                    "messaging_product": "whatsapp",
                    "to": clean_to,
                    "text": {"body": chunk},
                },
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                timeout=10,
            )
            resp.raise_for_status()
        except Exception as e:
            log.error("Failed to send Meta message chunk: %s", sanitize_log_input(e))
            all_ok = False
    return all_ok


# ---------------------------------------------------------------------------
# Backend Chat Integration & Job Queue Polling
# ---------------------------------------------------------------------------
FALLBACK_DOWN = "🙏 I am catching my breath. Please send your message again in a few moments."
FALLBACK_GENERIC = (
    "🙏 Something went unexpectedly quiet on my end. Could you rephrase or try again?"
)
FALLBACK_RATE_LIMIT = "🙏 Please wait a moment before your next question."
FALLBACK_QUOTA = (
    "🙏 You've reached today's free question limit on WhatsApp. Please try again tomorrow."
)
FALLBACK_LONG_CHAT = (
    "🙏 This conversation has grown very long. Send RESET to start fresh, then ask again."
)
MEDIA_DECLINE = (
    "🙏 I can't open photos, videos, files, or locations here yet. "
    "Please type your question as text and I'll answer."
)
VOICE_DECLINE = (
    "🙏 I can't listen to voice notes yet. Please type your question as text and I'll answer."
)


def _response_text(response: Any) -> str:
    try:
        return str(response.text or "")
    except Exception:
        return ""


def _is_invalid_anon_token(response: Any) -> bool:
    return response.status_code == 400 and "Invalid anonymous session" in _response_text(response)


def call_chat(
    phone: str,
    user_message: str,
    session_token: str | None = None,
    language: str = "en",
) -> dict[str, Any]:
    """Call backend /api/chat as a signed anonymous session.

    Sends the per-phone anon token as `session_id` with no Authorization
    header, so backend quotas, job ownership, and crisis preemption behave
    exactly as for anonymous web seekers. A rotated server secret surfaces
    as 400 Invalid-anonymous-session: the stored token is refreshed once
    and the call retried (the fresh token is persisted for the job poll).
    """
    clean_phone = sanitize_phone(phone)
    token = session_token or get_stored_anon_token(clean_phone) or ""
    state = state_for(clean_phone)
    body = {
        "messages": history_for(clean_phone),
        "user_message": user_message,
        "session_id": token,
        "meditation_step": state["meditation_step"],
        "language": language or state["language"] or "en",
        "last_serene_mind_at": state["last_serene_at"],
    }
    headers = {"Content-Type": "application/json"}
    resp = requests.post(
        f"{API_URL}/api/chat",
        headers=headers,
        data=json.dumps(body),
        timeout=WA_CHAT_TIMEOUT_S,
    )
    if _is_invalid_anon_token(resp):
        log.warning(
            "anon token rejected — re-issuing once for %s", sanitize_phone(clean_phone)[:8] + "***"
        )
        invalidate_anon_token(clean_phone)
        token = ensure_anon_token(clean_phone)
        body["session_id"] = token
        resp = requests.post(
            f"{API_URL}/api/chat",
            headers=headers,
            data=json.dumps(body),
            timeout=WA_CHAT_TIMEOUT_S,
        )
    resp.raise_for_status()
    return resp.json()


def poll_job_until_complete(phone: str, job_id: str, session_token: str | None = None) -> str:
    """Poll asynchronous job queue until completed, failed, or timed out."""
    clean_phone = sanitize_phone(phone)
    token = session_token or get_stored_anon_token(clean_phone) or ""
    headers = {
        "X-Session-Id": token,
        "Content-Type": "application/json",
    }
    deadline = time.time() + WA_CHAT_TIMEOUT_S
    while time.time() < deadline:
        try:
            resp = requests.get(
                f"{API_URL}/api/jobs/{job_id}",
                headers=headers,
                timeout=5,
            )
            resp.raise_for_status()
            job = resp.json()
            status = job.get("status")

            if status == "completed":
                result = job.get("result") or {}
                raw_text = result.get("response", "") or ""
                citations = result.get("citations") or []
                answer_text = format_whatsapp_response(raw_text, citations)
                if not answer_text:
                    answer_text = FALLBACK_GENERIC

                meditation_step = int(result.get("meditation_step") or 0)
                update_state(
                    clean_phone,
                    meditation_step=meditation_step,
                    last_serene_at=int(time.time()) if meditation_step == 0 else None,
                )
                log.info(
                    "Job %s completed for %s",
                    sanitize_log_input(job_id),
                    sanitize_log_input(clean_phone),
                )
                return answer_text

            elif status == "failed":
                log.error(
                    "Job %s failed for %s: %s",
                    sanitize_log_input(job_id),
                    sanitize_log_input(clean_phone),
                    sanitize_log_input(job.get("error")),
                )
                return FALLBACK_GENERIC

        except Exception as e:
            log.warning(
                "Error polling job %s: %s", sanitize_log_input(job_id), sanitize_log_input(e)
            )

        time.sleep(1.0)

    log.warning(
        "Job %s timed out for %s", sanitize_log_input(job_id), sanitize_log_input(clean_phone)
    )
    return FALLBACK_DOWN


def _deliver_outbound(
    channel: str, phone: str, answer_text: str, metadata: dict[str, Any] | None = None
) -> bool:
    """Send one outbound reply, retrying once. Returns True on success."""
    for attempt in (1, 2):
        if channel == "twilio":
            ok = push_twilio_message(phone, answer_text)
        elif channel == "meta":
            phone_number_id = (metadata or {}).get("phone_number_id") or os.getenv(
                "META_PHONE_NUMBER_ID", META_PHONE_NUMBER_ID
            )
            ok = push_meta_message(phone_number_id, phone, answer_text)
        else:
            log.error("unknown channel %s — dropping reply", sanitize_log_input(channel))
            return False
        if ok:
            return True
        log.warning("outbound attempt %d failed for %s", attempt, sanitize_log_input(phone))
    log.error("outbound delivery failed twice for %s — reply dropped", sanitize_log_input(phone))
    return False


def _failure_copy(sc: int, body_text: str) -> str:
    lowered = (body_text or "").lower()
    if sc == 429 and ("quota_exceeded" in lowered or "anonymous quota exceeded" in lowered):
        return FALLBACK_QUOTA
    if sc == 429 and (
        "daily usage" in lowered or "daily budget" in lowered or "user_budget_exceeded" in lowered
    ):
        return FALLBACK_QUOTA
    if sc == 409 or "context_exhausted" in lowered or "conversation context exhausted" in lowered:
        return FALLBACK_LONG_CHAT
    if sc == 503:
        return "🙏 The Guru is deep in meditation. Please try again in a moment."
    if sc == 429:
        return FALLBACK_RATE_LIMIT
    if sc == 500:
        return "🙏 The Guru needs a moment. Please try again shortly."
    return FALLBACK_GENERIC


def _handle_command(clean_phone: str, user_message: str) -> str | None:
    """Serve RESET/HELP/STOP/consent locally. Returns the reply, or None for normal turns.

    T-C8 consent gate: no teaching answer before the seeker consents (YES),
    and STOP opts out (only START/HELP then reply). Crisis messages never
    reach here gated — likely_crisis bypasses so the failsafe footer path in
    the webhooks always runs first.
    """
    word = (user_message or "").strip().upper()
    if likely_crisis(user_message or ""):
        return None
    st = state_for(clean_phone)
    if word in STOP_WORDS:
        update_state(
            clean_phone,
            meditation_step=int(st.get("meditation_step", 0) or 0),
            last_serene_at=st.get("last_serene_at"),
            language=str(st.get("language") or "en"),
            consented=0,
            opted_out=1,
        )
        return STOP_COPY
    if int(st.get("opted_out", 0) or 0):
        if word in HELP_WORDS:
            return HELP_COPY
        if word == "START":
            # Opted-out branch only: START completes opt-in in one step
            # (consented=1, opted_out=0), no second YES round-trip. A fresh,
            # never-consented number's START falls through to RESET_WORDS
            # below, which clears the conversation but grants no consent.
            # clear_conversation preserves both flags.
            update_state(
                clean_phone,
                meditation_step=0,
                last_serene_at=None,
                language=str(st.get("language") or "en"),
                consented=1,
                opted_out=0,
            )
            clear_conversation(clean_phone)
            return RESET_COPY
        return OPTED_OUT_COPY
    if word in RESET_WORDS:
        clear_conversation(clean_phone)
        return RESET_COPY
    if word in HELP_WORDS:
        return HELP_COPY
    if not int(st.get("consented", 0) or 0):
        if word in YES_WORDS:
            update_state(
                clean_phone,
                meditation_step=int(st.get("meditation_step", 0) or 0),
                last_serene_at=st.get("last_serene_at"),
                language=str(st.get("language") or "en"),
                consented=1,
            )
            return CONSENT_WELCOME_COPY
        return CONSENT_COPY
    return None


def process_chat_turn(
    channel: str,
    phone: str,
    user_message: str,
    metadata: dict[str, Any] | None = None,
    *,
    deliver_outbound: bool = True,
) -> str:
    """
    Execute full conversational turn:
      1. Serve RESET/HELP locally (no backend call).
      2. Resolve the per-phone signed anon session + language.
      3. Call /api/chat (or poll job queue if queued).
      4. Format response for WhatsApp (preserving crisis referrals).
      5. Persist to SQLite state.
      6. Send outbound message via provider API (skipped when the caller
         replies synchronously, e.g. Twilio TwiML — avoids double-send).
    """
    clean_phone = sanitize_phone(phone)

    command_reply = _handle_command(clean_phone, user_message)
    if command_reply is not None:
        append_message(clean_phone, "assistant", command_reply)
        if deliver_outbound:
            _deliver_outbound(channel, clean_phone, command_reply, metadata)
        return command_reply

    detected = detect_language(user_message)
    state = state_for(clean_phone)
    language = detected or state["language"] or "en"
    if detected and detected != state["language"]:
        update_state(
            clean_phone,
            meditation_step=state["meditation_step"],
            last_serene_at=state["last_serene_at"],
            language=detected,
        )

    try:
        try:
            session_token = ensure_anon_token(clean_phone)
        except Exception as exc:
            # Token issuance failed (backend likely unreachable): proceed with
            # any cached token so call_chat surfaces the real transport error
            # and maps it to honest failure copy below.
            log.warning(
                "anon token issue failed for %s: %s",
                sanitize_log_input(clean_phone),
                sanitize_log_input(exc),
            )
            session_token = get_stored_anon_token(clean_phone) or ""
        resp = call_chat(clean_phone, user_message, session_token, language)
        job_id = resp.get("job_id")
        if job_id:
            answer_text = poll_job_until_complete(clean_phone, job_id, session_token)
        else:
            raw_text = resp.get("response", "") or ""
            citations = resp.get("citations") or []
            answer_text = format_whatsapp_response(raw_text, citations)
            meditation_step = int(resp.get("meditation_step") or 0)
            update_state(
                clean_phone,
                meditation_step=meditation_step,
                last_serene_at=int(time.time()) if meditation_step == 0 else None,
                language=language,
            )
        if not answer_text:
            answer_text = FALLBACK_GENERIC
    except requests.Timeout:
        log.warning("chat timeout for %s", sanitize_log_input(clean_phone))
        answer_text = with_helplines_if_crisis(
            "🙏 The Guru is taking longer than usual. Please try again.", user_message
        )
    except requests.ConnectionError:
        log.error("chat connection error for %s", sanitize_log_input(clean_phone))
        answer_text = with_helplines_if_crisis(
            "🙏 Unable to reach the Guru right now. Please try again shortly.",
            user_message,
        )
    except requests.HTTPError as e:
        sc = e.response.status_code if e.response is not None else 0
        log.error(
            "chat HTTP %d for %s: %s",
            int(sc),
            sanitize_log_input(clean_phone),
            sanitize_log_input(e),
        )
        try:
            err_body = e.response.text if e.response is not None else ""
        except Exception:
            err_body = ""
        answer_text = with_helplines_if_crisis(_failure_copy(int(sc), err_body), user_message)
    except Exception as e:
        log.exception(
            "chat call failed for %s: %s", sanitize_log_input(clean_phone), sanitize_log_input(e)
        )
        answer_text = with_helplines_if_crisis(FALLBACK_GENERIC, user_message)

    # Persist assistant response
    append_message(clean_phone, "assistant", answer_text)

    # Dispatch outbound message via provider (unless caller replies inline)
    if deliver_outbound:
        _deliver_outbound(channel, clean_phone, answer_text, metadata)

    return answer_text


# ---------------------------------------------------------------------------
# TwiML Helper
# ---------------------------------------------------------------------------
def _twiml(message: str) -> tuple[str, int, dict]:
    if not message:
        return (
            "<?xml version='1.0' encoding='UTF-8'?>\n<Response></Response>",
            200,
            {"Content-Type": "application/xml"},
        )
    chunks = _chunk_text(message)
    parts = []
    for chunk in chunks:
        safe = html.escape(chunk)
        parts.append(f"<Message>{safe}</Message>")
    body = "<?xml version='1.0' encoding='UTF-8'?>\n<Response>" + "".join(parts) + "</Response>"
    return (body, 200, {"Content-Type": "application/xml"})


# ---------------------------------------------------------------------------
# Inbound Webhook Routes: Twilio (/whatsapp/twilio & /twilio/whatsapp)
# ---------------------------------------------------------------------------
def _twilio_media_kind(form: Any) -> str | None:
    """Return 'voice' for audio attachments, 'media' for any other, else None."""
    try:
        count = int(form.get("NumMedia", 0) or 0)
    except (TypeError, ValueError):
        count = 0
    if count <= 0:
        return None
    ctype = str(form.get("MediaContentType0", "") or "").lower()
    if ctype.startswith("audio/"):
        return "voice"
    return "media"


@app.route("/twilio/whatsapp", methods=["POST"])
@app.route("/whatsapp/twilio", methods=["POST"])
def twilio_webhook():
    if not validate_twilio_signature(request):
        log.warning("Twilio signature invalid — rejecting request")
        abort(403)

    raw_phone = request.form.get("From", "").strip()
    body = (request.form.get("Body") or "").strip()
    if not raw_phone:
        return _twiml("")

    clean_phone = sanitize_phone(raw_phone)
    media_kind = _twilio_media_kind(request.form)

    # Delivery receipts / status callbacks carry no Body and no media:
    # acknowledge quietly instead of answering a question nobody asked.
    if not body and media_kind is None:
        return _twiml("")

    if media_kind is not None:
        decline = VOICE_DECLINE if media_kind == "voice" else MEDIA_DECLINE
        append_message(clean_phone, "user", f"[{media_kind} attachment]")
        append_message(clean_phone, "assistant", decline)
        return _twiml(decline)

    append_message(clean_phone, "user", body)
    metadata = {"from_raw": raw_phone}
    async_ack = os.getenv("WA_ASYNC_ACK", "true").lower() == "true"
    word = body.upper()
    # RP-C1: a crisis-flagged message is never rate-limited; it must reach the
    # backend's reviewed crisis path. Skipping the check also spares the budget
    # bucket (is_rate_limited consumes one entry per call). Local commands and
    # consent words (RESET/HELP/STOP/START, plus YES while consent is pending)
    # are served without a backend call and must always reach _handle_command
    # — rate-limiting them could swallow consent itself.
    is_crisis = likely_crisis(body)
    if (
        not _is_rate_limit_exempt(word, clean_phone)
        and not is_crisis
        and is_rate_limited(clean_phone)
    ):
        append_message(clean_phone, "assistant", FALLBACK_RATE_LIMIT)
        # Synchronous TwiML reply: instant, needs no REST credentials.
        return _twiml(FALLBACK_RATE_LIMIT)
    # RP-C1 companion: bound concurrent crisis processing per phone.
    # A repeated crisis match bypasses rate-limiting but must not trigger
    # unbounded backend calls. Always deliver the local footer; only spawn
    # a backend thread when capacity allows.
    if is_crisis and not _crisis_capacity_acquire(clean_phone):
        log.warning("Crisis capacity full for %s — returning local footer", clean_phone[:6])
        append_message(clean_phone, "assistant", _HELPLINE_FOOTER)
        return _twiml(_HELPLINE_FOOTER)
    if async_ack:

        def _twilio_crisis_worker():
            try:
                process_chat_turn("twilio", clean_phone, body, metadata)
            finally:
                if is_crisis:
                    _crisis_capacity_release(clean_phone)

        try:
            threading.Thread(target=_twilio_crisis_worker, daemon=True).start()
        except Exception as exc:
            # Thread spawn itself failed (e.g. out of threads): the acquired
            # crisis slot must not leak, and the seeker still gets the local
            # footer — a crisis message always gets an answer.
            log.warning("Crisis worker thread failed to start for %s: %s", clean_phone[:6], exc)
            if is_crisis:
                _crisis_capacity_release(clean_phone)
            append_message(clean_phone, "assistant", _HELPLINE_FOOTER)
            return _twiml(_HELPLINE_FOOTER)
        # Immediately acknowledge webhook within <15s
        return _twiml("")
    else:
        # Synchronous reply carries the answer — skip the outbound push
        # inside process_chat_turn to avoid double-delivery.
        try:
            answer = process_chat_turn(
                "twilio", clean_phone, body, metadata, deliver_outbound=False
            )
        finally:
            if is_crisis:
                _crisis_capacity_release(clean_phone)
        return _twiml(answer)


# ---------------------------------------------------------------------------
# Inbound Webhook Routes: Meta Cloud API (/whatsapp/meta & /meta/whatsapp)
# ---------------------------------------------------------------------------
@app.route("/whatsapp/meta", methods=["GET"])
@app.route("/meta/whatsapp", methods=["GET"])
def meta_webhook_verify():
    """Required verification challenge route for Meta App Webhook registration."""
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")
    expected_token = os.getenv("META_VERIFY_TOKEN", META_VERIFY_TOKEN)

    if mode == "subscribe" and token and token == expected_token:
        log.info("Meta webhook verification successful")
        return str(challenge or ""), 200, {"Content-Type": "text/plain"}

    log.warning("Meta webhook verification failed: Token mismatch or missing")
    return "Forbidden", 403


_META_TEXT_TYPES = ("text",)


def parse_meta_inbound(payload: dict[str, Any]) -> dict[str, Any]:
    """Classify one Meta webhook payload for the message handler.

    Returns a dict with `kind` in:
      text       — answerable inbound (body, from_number, phone_number_id)
      voice      — audio attachment, gets the voice-note decline
      media      — image/video/document/sticker/location/contacts/unknown
                   content, gets the honest media decline
      status     — receipts/statuses only, acknowledge silently
      ignore     — reactions and other non-queries, acknowledge silently
      incomplete — message present but missing sender or usable content
      malformed  — not a message payload at all
    Only text turns reach the backend; nothing user-sent is dropped without
    either an answer or an honest decline.
    """
    empty: dict[str, Any] = {"kind": "malformed"}
    try:
        entry = (payload.get("entry") or [{}])[0] or {}
        changes = (entry.get("changes") or [{}])[0] or {}
        value = changes.get("value") or {}
        messages = value.get("messages") or []
        if not messages:
            return {"kind": "status"}
        message = messages[0] or {}
        if not message:
            return {"kind": "status"}

        from_number = str(message.get("from") or "").strip()
        raw_phone_id = str((value.get("metadata") or {}).get("phone_number_id") or "").strip()
        phone_number_id = (
            str(int(raw_phone_id))
            if raw_phone_id.isdigit()
            else os.getenv("META_PHONE_NUMBER_ID", META_PHONE_NUMBER_ID)
        )
        msg_type = str(message.get("type") or "").strip().lower()

        if msg_type == "reaction":
            return {"kind": "ignore"}

        body = ""
        if msg_type in _META_TEXT_TYPES or not msg_type:
            body = str((message.get("text") or {}).get("body") or "").strip()
        elif msg_type == "interactive":
            interactive = message.get("interactive") or {}
            reply = interactive.get("button_reply") or interactive.get("list_reply") or {}
            body = str(reply.get("title") or "").strip()

        if body:
            if not from_number:
                return {"kind": "incomplete"}
            return {
                "kind": "text",
                "body": body,
                "from_number": from_number,
                "phone_number_id": phone_number_id,
            }

        if msg_type == "audio":
            kind = "voice"
        elif msg_type in (
            "image",
            "video",
            "document",
            "sticker",
            "location",
            "contacts",
            "unknown",
            "unsupported",
        ) or (
            msg_type
            and any(
                k in message
                for k in ("audio", "image", "video", "document", "sticker", "location", "contacts")
            )
        ):
            kind = "media"
        elif not msg_type:
            # Message shell with no type and no text (e.g. redacted/protocol).
            return {"kind": "incomplete"}
        else:
            kind = "media"
        if not from_number:
            return {"kind": "incomplete"}
        return {
            "kind": kind,
            "from_number": from_number,
            "phone_number_id": phone_number_id,
        }
    except (IndexError, KeyError, AttributeError, ValueError, TypeError):
        return empty


@app.route("/whatsapp/meta", methods=["POST"])
@app.route("/meta/whatsapp", methods=["POST"])
def meta_webhook():
    """Incoming message handler for Meta WhatsApp Cloud API."""
    if not validate_meta_signature(request):
        log.warning("Meta signature invalid — rejecting request")
        abort(403)

    payload = request.get_json(silent=True) or {}
    parsed = parse_meta_inbound(payload)
    kind = parsed["kind"]

    # Delivery/read receipts and reactions are not inbound queries.
    if kind in ("status", "ignore"):
        return jsonify({"status": "no_message"}), 200
    if kind == "incomplete":
        return jsonify({"status": "incomplete_payload"}), 200
    if kind == "malformed":
        return jsonify({"status": "ignored_non_message"}), 200

    clean_phone = sanitize_phone(parsed["from_number"])
    metadata = {
        "phone_number_id": parsed["phone_number_id"],
        "from_raw": parsed["from_number"],
    }

    if kind in ("voice", "media"):
        decline = VOICE_DECLINE if kind == "voice" else MEDIA_DECLINE
        append_message(clean_phone, "user", f"[{kind} attachment]")
        append_message(clean_phone, "assistant", decline)
        # Local, instant, needs no inference: push synchronously (<15s).
        _deliver_outbound("meta", clean_phone, decline, metadata)
        return jsonify({"status": "declined_media"}), 200

    msg_body = parsed["body"]
    append_message(clean_phone, "user", msg_body)

    is_crisis_meta = likely_crisis(msg_body)
    # Same exemption as the Twilio path: crisis, local commands, and consent
    # words (STOP/START, plus YES while consent is pending) always reach
    # _handle_command.
    if (
        not _is_rate_limit_exempt(msg_body.upper(), clean_phone)
        and not is_crisis_meta
        and is_rate_limited(clean_phone)
    ):
        append_message(clean_phone, "assistant", FALLBACK_RATE_LIMIT)
        _deliver_outbound("meta", clean_phone, FALLBACK_RATE_LIMIT, metadata)
        return jsonify({"status": "rate_limited"}), 200

    # RP-C1 companion: bound concurrent crisis processing per phone (mirrors Twilio branch).
    if is_crisis_meta and not _crisis_capacity_acquire(clean_phone):
        log.warning("Crisis capacity full for %s — returning local footer (meta)", clean_phone[:6])
        append_message(clean_phone, "assistant", _HELPLINE_FOOTER)
        _deliver_outbound("meta", clean_phone, _HELPLINE_FOOTER, metadata)
        return jsonify({"status": "crisis_capacity_full"}), 200

    async_ack = os.getenv("WA_ASYNC_ACK", "true").lower() == "true"
    if async_ack:

        def _meta_crisis_worker():
            try:
                process_chat_turn("meta", clean_phone, msg_body, metadata)
            finally:
                if is_crisis_meta:
                    _crisis_capacity_release(clean_phone)

        try:
            threading.Thread(target=_meta_crisis_worker, daemon=True).start()
        except Exception as exc:
            log.warning(
                "Crisis worker thread failed to start for %s (meta): %s", clean_phone[:6], exc
            )
            if is_crisis_meta:
                _crisis_capacity_release(clean_phone)
            append_message(clean_phone, "assistant", _HELPLINE_FOOTER)
            _deliver_outbound("meta", clean_phone, _HELPLINE_FOOTER, metadata)
            return jsonify({"status": "crisis_thread_failed"}), 200
        # Immediately acknowledge webhook within <15s
        return jsonify({"status": "received"}), 200
    else:
        # Sync mode has no TwiML channel: the answer must still be pushed.
        try:
            answer = process_chat_turn("meta", clean_phone, msg_body, metadata)
        finally:
            if is_crisis_meta:
                _crisis_capacity_release(clean_phone)
        return jsonify({"status": "processed", "response": answer}), 200


# ---------------------------------------------------------------------------
# Health & Diagnostic Endpoints
# ---------------------------------------------------------------------------
@app.route("/health", methods=["GET"])
def health():
    backend_ready = False
    try:
        resp = requests.get(f"{API_URL}/api/health", timeout=3)
        backend_ready = resp.status_code == 200
    except Exception:
        backend_ready = False

    db_ready = False
    try:
        with closing(_db()) as conn:
            conn.execute("SELECT 1").fetchone()
        db_ready = True
    except Exception:
        db_ready = False

    twilio_configured = bool(os.getenv("TWILIO_AUTH_TOKEN", TWILIO_AUTH_TOKEN))
    meta_configured = bool(os.getenv("META_APP_SECRET", META_APP_SECRET))

    ready = db_ready and (backend_ready or True)
    return jsonify(
        {
            "status": "ok",
            "ready": ready,
            "backend_url": API_URL,
            "backend_ready": backend_ready,
            "db_ready": db_ready,
            "twilio_configured": twilio_configured,
            "meta_configured": meta_configured,
        }
    ), 200


@app.route("/healthz", methods=["GET"])
def healthz():
    return jsonify({"status": "ok", "db": WA_DB_PATH}), 200


# ---------------------------------------------------------------------------
# Bootstrap
# ---------------------------------------------------------------------------
_init_db()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8080"))
    app.run(host="0.0.0.0", port=port, debug=False)
