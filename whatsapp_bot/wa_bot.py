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
  4. Robust Markdown -> WhatsApp Formatting:
     - **bold** -> *bold*
     - [Title](url) -> Title (url) clickable URLs
     - Header formatting and bullet points
     - Complete preservation of Indian crisis helplines (Tele-MANAS 14416, 112)
  5. Per-Phone State Tracking:
     - Session ID: `wa-<phone_number>`
     - Short-lived HS256 JWT minting matching backend JWT_SECRET
     - File-backed SQLite persistence for conversation history and meditation steps
"""

from __future__ import annotations

import base64
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
API_URL = os.getenv("ASKMUKTHIGURU_API_URL", os.getenv("BACKEND_URL", "http://localhost:8000")).rstrip("/")
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
            "SELECT meditation_step, last_serene_at, language FROM wa_state WHERE phone=?",
            (phone,),
        ).fetchone()
    if row is None:
        return {"meditation_step": 0, "last_serene_at": None, "language": "en"}
    return dict(row)


def update_state(phone: str, *, meditation_step: int, last_serene_at: int | None, language: str = "en") -> None:
    with closing(_db()) as conn:
        conn.execute(
            "INSERT INTO wa_state (phone, meditation_step, last_serene_at, language, updated_at) "
            "VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(phone) DO UPDATE SET "
            "  meditation_step=excluded.meditation_step, "
            "  last_serene_at=COALESCE(excluded.last_serene_at, wa_state.last_serene_at), "
            "  language=excluded.language, "
            "  updated_at=excluded.updated_at",
            (phone, meditation_step, last_serene_at, language, int(time.time())),
        )


# ---------------------------------------------------------------------------
# Phone Normalization & JWT Minting
# ---------------------------------------------------------------------------
def sanitize_phone(phone: str) -> str:
    """Normalize phone number: strip whitespace, whatsapp: prefix, keeping + and digits."""
    clean = str(phone or "").replace("whatsapp:", "").strip()
    clean = re.sub(r"[^\d+]", "", clean)
    return clean or str(phone).strip()


def mint_jwt(phone: str) -> str:
    """Mint an HS256 JWT the backend will accept via LocalAuthStrategy."""
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
    text = re.sub(r'^(?:#{1,6})\s*(.+?)$', r'*\1*', text, flags=re.MULTILINE)

    # 2. Convert bold: **text** -> *text*
    text = re.sub(r'\*\*(.+?)\*\*', r'*\1*', text)

    # 3. Convert underline/italic: __text__ -> _text_
    text = re.sub(r'__(.+?)__', r'_\1_', text)

    # 4. Convert markdown links: [Title](url) -> Title (url)
    text = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'\1 (\2)', text)

    # 5. Clean triple backtick code blocks while preserving inline code
    text = re.sub(r'```[a-zA-Z0-9_-]*\n?', '', text)

    # 6. Normalize bullet points: lines starting with '* ' or '- ' -> '• '
    text = re.sub(r'^\s*[-*]\s+', '• ', text, flags=re.MULTILINE)

    # 7. Strip blockquote markers: '> text' -> text
    text = re.sub(r'^\s*>\s*', '', text, flags=re.MULTILINE)

    return text.strip()


def with_citations(text: str, citations: list[str]) -> str:
    """Format and append up to 3 top citations with clean WhatsApp bullets."""
    if not citations:
        return text
    top = [c.strip() for c in citations if c and c.strip()][:3]
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
        log.error("Missing Twilio credentials (ACCOUNT_SID, AUTH_TOKEN, or FROM); cannot send outbound message")
        return False

    clean_to = sanitize_phone(to_number)
    target = f"whatsapp:{clean_to}" if not str(to_number).startswith("whatsapp:") else str(to_number)
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
            log.warning("TwilioClient send failed; attempting REST fallback: %s", sanitize_log_input(e))

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

    clean_id = str(phone_number_id or os.getenv("META_PHONE_NUMBER_ID", META_PHONE_NUMBER_ID)).strip()
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
FALLBACK_GENERIC = "🙏 Something went unexpectedly quiet on my end. Could you rephrase or try again?"


def call_chat(phone: str, user_message: str, jwt_token: str) -> dict[str, Any]:
    """Call backend /api/chat with user history and state."""
    clean_phone = sanitize_phone(phone)
    state = state_for(clean_phone)
    body = {
        "messages": history_for(clean_phone),
        "user_message": user_message,
        "session_id": f"wa-{clean_phone}",
        "meditation_step": state["meditation_step"],
        "language": state["language"],
        "last_serene_mind_at": state["last_serene_at"],
    }
    headers = {
        "Authorization": f"Bearer {jwt_token}",
        "Content-Type": "application/json",
    }
    resp = requests.post(
        f"{API_URL}/api/chat",
        headers=headers,
        data=json.dumps(body),
        timeout=WA_CHAT_TIMEOUT_S,
    )
    if resp.status_code == 401:
        log.warning("chat 401 — re-minting JWT and retrying once")
        headers["Authorization"] = f"Bearer {mint_jwt(clean_phone)}"
        resp = requests.post(
            f"{API_URL}/api/chat",
            headers=headers,
            data=json.dumps(body),
            timeout=WA_CHAT_TIMEOUT_S,
        )
    resp.raise_for_status()
    return resp.json()


def poll_job_until_complete(phone: str, job_id: str, jwt_token: str) -> str:
    """Poll asynchronous job queue until completed, failed, or timed out."""
    clean_phone = sanitize_phone(phone)
    headers = {
        "Authorization": f"Bearer {jwt_token}",
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
                log.info("Job %s completed for %s", sanitize_log_input(job_id), sanitize_log_input(clean_phone))
                return answer_text

            elif status == "failed":
                log.error("Job %s failed for %s: %s", sanitize_log_input(job_id), sanitize_log_input(clean_phone), sanitize_log_input(job.get("error")))
                return FALLBACK_GENERIC

        except Exception as e:
            log.warning("Error polling job %s: %s", sanitize_log_input(job_id), sanitize_log_input(e))

        time.sleep(1.0)

    log.warning("Job %s timed out for %s", sanitize_log_input(job_id), sanitize_log_input(clean_phone))
    return FALLBACK_DOWN


def process_chat_turn(channel: str, phone: str, user_message: str, metadata: dict[str, Any] | None = None) -> str:
    """
    Execute full conversational turn:
      1. Mint JWT matching backend credentials.
      2. Call /api/chat (or poll job queue if queued).
      3. Format response for WhatsApp (preserving crisis referrals).
      4. Persist to SQLite state.
      5. Send outbound message via provider API.
    """
    clean_phone = sanitize_phone(phone)
    jwt_token = mint_jwt(clean_phone)
    try:
        resp = call_chat(clean_phone, user_message, jwt_token)
        job_id = resp.get("job_id")
        if job_id:
            answer_text = poll_job_until_complete(clean_phone, job_id, jwt_token)
        else:
            raw_text = resp.get("response", "") or ""
            citations = resp.get("citations") or []
            answer_text = format_whatsapp_response(raw_text, citations)
            meditation_step = int(resp.get("meditation_step") or 0)
            update_state(
                clean_phone,
                meditation_step=meditation_step,
                last_serene_at=int(time.time()) if meditation_step == 0 else None,
            )
        if not answer_text:
            answer_text = FALLBACK_GENERIC
    except requests.Timeout:
        log.warning("chat timeout for %s", sanitize_log_input(clean_phone))
        answer_text = "🙏 The Guru is taking longer than usual. Please try again."
    except requests.ConnectionError:
        log.error("chat connection error for %s", sanitize_log_input(clean_phone))
        answer_text = "🙏 Unable to reach the Guru. Please check your connection."
    except requests.HTTPError as e:
        sc = e.response.status_code if e.response is not None else 0
        log.error("chat HTTP %d for %s: %s", int(sc), sanitize_log_input(clean_phone), sanitize_log_input(e))
        if sc == 503:
            answer_text = "🙏 The Guru is deep in meditation. Please try again in a moment."
        elif sc == 429:
            answer_text = "🙏 Please wait a moment before your next question."
        elif sc == 500:
            answer_text = "🙏 The Guru needs a moment. Please try again shortly."
        else:
            answer_text = FALLBACK_GENERIC
    except Exception as e:
        log.exception("chat call failed for %s: %s", sanitize_log_input(clean_phone), sanitize_log_input(e))
        answer_text = FALLBACK_GENERIC

    # Persist assistant response
    append_message(clean_phone, "assistant", answer_text)

    # Dispatch outbound message via provider
    if channel == "twilio":
        push_twilio_message(clean_phone, answer_text)
    elif channel == "meta":
        phone_number_id = (metadata or {}).get("phone_number_id") or os.getenv("META_PHONE_NUMBER_ID", META_PHONE_NUMBER_ID)
        push_meta_message(phone_number_id, clean_phone, answer_text)

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
@app.route("/twilio/whatsapp", methods=["POST"])
@app.route("/whatsapp/twilio", methods=["POST"])
def twilio_webhook():
    if not validate_twilio_signature(request):
        log.warning("Twilio signature invalid — rejecting request")
        abort(403)

    raw_phone = request.form.get("From", "").strip()
    body = (request.form.get("Body") or "").strip()

    if not raw_phone or not body:
        return _twiml("🙏 I didn't receive any text. Please try again.")

    clean_phone = sanitize_phone(raw_phone)
    append_message(clean_phone, "user", body)

    metadata = {"from_raw": raw_phone}
    async_ack = os.getenv("WA_ASYNC_ACK", "true").lower() == "true"
    if async_ack:
        threading.Thread(
            target=process_chat_turn,
            args=("twilio", clean_phone, body, metadata),
            daemon=True,
        ).start()
        # Immediately acknowledge webhook within <15s
        return _twiml("")
    else:
        answer = process_chat_turn("twilio", clean_phone, body, metadata)
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


@app.route("/whatsapp/meta", methods=["POST"])
@app.route("/meta/whatsapp", methods=["POST"])
def meta_webhook():
    """Incoming message handler for Meta WhatsApp Cloud API."""
    if not validate_meta_signature(request):
        log.warning("Meta signature invalid — rejecting request")
        abort(403)

    payload = request.get_json(silent=True) or {}
    try:
        entry = payload.get("entry", [{}])[0]
        changes = entry.get("changes", [{}])[0]
        value = changes.get("value", {})
        message = value.get("messages", [{}])[0]
        if not message:
            return jsonify({"status": "no_message"}), 200

        from_number = str(message.get("from") or "").strip()
        msg_body = message.get("text", {}).get("body", "").strip()
        raw_phone_id = str(value.get("metadata", {}).get("phone_number_id") or "").strip()

        if not msg_body or not from_number:
            return jsonify({"status": "incomplete_payload"}), 200

        clean_phone = sanitize_phone(from_number)
        phone_number_id = str(int(raw_phone_id)) if raw_phone_id.isdigit() else os.getenv("META_PHONE_NUMBER_ID", META_PHONE_NUMBER_ID)

    except (IndexError, KeyError, AttributeError, ValueError):
        return jsonify({"status": "ignored_non_message"}), 200

    append_message(clean_phone, "user", msg_body)
    metadata = {"phone_number_id": phone_number_id, "from_raw": from_number}

    async_ack = os.getenv("WA_ASYNC_ACK", "true").lower() == "true"
    if async_ack:
        threading.Thread(
            target=process_chat_turn,
            args=("meta", clean_phone, msg_body, metadata),
            daemon=True,
        ).start()
        # Immediately acknowledge webhook within <15s
        return jsonify({"status": "received"}), 200
    else:
        answer = process_chat_turn("meta", clean_phone, msg_body, metadata)
        return jsonify({"status": "processed", "response": answer}), 200


# ---------------------------------------------------------------------------
# Health & Diagnostic Endpoints
# ---------------------------------------------------------------------------
@app.route("/health", methods=["GET"])
def health():
    backend_ready = False
    try:
        resp = requests.get(f"{API_URL}/api/health", timeout=3)
        backend_ready = (resp.status_code == 200)
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
    return jsonify({
        "status": "ok",
        "ready": ready,
        "backend_url": API_URL,
        "backend_ready": backend_ready,
        "db_ready": db_ready,
        "twilio_configured": twilio_configured,
        "meta_configured": meta_configured,
    }), 200


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
