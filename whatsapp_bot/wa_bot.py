"""
AskMukthiGuru WhatsApp Bot — Reference Implementation
======================================================

Single-file Flask service that bridges Twilio WhatsApp <-> /api/chat.

What it does (in order, per incoming WhatsApp message):
  1. Verify Twilio's X-Twilio-Signature header (rejects forged webhooks).
  2. Look up (or create) the user's conversation history in SQLite.
  3. Mint a short-lived HS256 JWT signed with backend/.env:JWT_SECRET
     so the chat backend authenticates the bot as the user.
  4. POST /api/chat with the message + last 10 turns of history.
  5. Format the markdown response for WhatsApp (bold conversion, citations).
  6. Persist the response + meditation_step in SQLite.
  7. Return TwiML <Response><Message>...</Message></Response>.

Why this layout:
  - SQLite (file-backed) instead of in-memory dict so a worker restart
    doesn't wipe everyone's meditation_step.
  - Per-phone JWT (option B from WHATSAPP_BOT_INTEGRATION.md) — gives
    correct per-user memory and rate limits on the backend.
  - Twilio signature validation is non-optional. Without it, any internet
    actor can spoof "From" and impersonate users.

NOT included (deliberately):
  - Async/queue offloading for >10s responses (Twilio re-sends after 15s).
    For production, wrap the requests.post call in a background job and
    immediately TwiML-acknowledge, then send the real answer via the
    Twilio REST API as a follow-up message. See README at bottom of file.
  - Multi-tenant isolation (one bot, one backend assumed).
  - Rate limiting (let the backend's chat_rate_limit handle it; bot just
    backs off on 429).

Run:
  pip install -r requirements.txt
  cp .env.example .env  # then edit values
  python wa_bot.py
  # (in another terminal) ngrok http 8080
  # paste ngrok URL into Twilio WhatsApp sandbox webhook setting

Environment variables (all required unless marked optional):
  ASKMUKTHIGURU_API_URL    e.g. https://api.askmukthiguru.com
  JWT_SECRET               same value as backend/.env JWT_SECRET
  TWILIO_AUTH_TOKEN        from Twilio console (used for signature verification)
  TWILIO_FROM              e.g. "whatsapp:+14155238886" (sandbox) or your number
  WA_DB_PATH               sqlite file path (default: ./wa_state.db)
  WA_CHAT_TIMEOUT_S        default 60
  WA_HISTORY_LIMIT         default 10
"""

from __future__ import annotations

import json
import logging
import os
import re
import sqlite3
import time
from contextlib import closing
from pathlib import Path
from typing import Any

import jwt
import requests
from flask import Flask, abort, request
from twilio.request_validator import RequestValidator

# ---------------------------------------------------------------------------
# Config (env-driven, fails fast)
# ---------------------------------------------------------------------------
API_URL = os.environ["ASKMUKTHIGURU_API_URL"].rstrip("/")
JWT_SECRET = os.environ["JWT_SECRET"]
TWILIO_AUTH_TOKEN = os.environ["TWILIO_AUTH_TOKEN"]
TWILIO_FROM = os.environ.get("TWILIO_FROM", "")
WA_DB_PATH = os.environ.get("WA_DB_PATH", "./wa_state.db")
WA_CHAT_TIMEOUT_S = int(os.environ.get("WA_CHAT_TIMEOUT_S", "60"))
WA_HISTORY_LIMIT = int(os.environ.get("WA_HISTORY_LIMIT", "10"))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s | %(message)s")
log = logging.getLogger("wa_bot")

app = Flask(__name__)
twilio_validator = RequestValidator(TWILIO_AUTH_TOKEN)


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------
SCHEMA = """
CREATE TABLE IF NOT EXISTS wa_messages (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  phone           TEXT NOT NULL,
  role            TEXT NOT NULL CHECK (role IN ('user','assistant')),
  content         TEXT NOT NULL,
  created_at      INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_wa_phone_time ON wa_messages(phone, created_at DESC);

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


def history_for(phone: str, limit: int = WA_HISTORY_LIMIT) -> list[dict]:
    """Return last `limit` messages in chronological order (oldest first)."""
    with closing(_db()) as conn:
        rows = conn.execute(
            "SELECT role, content FROM wa_messages WHERE phone=? "
            "ORDER BY created_at DESC LIMIT ?",
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


def update_state(phone: str, *, meditation_step: int, last_serene_at: int | None) -> None:
    with closing(_db()) as conn:
        conn.execute(
            "INSERT INTO wa_state (phone, meditation_step, last_serene_at, updated_at) "
            "VALUES (?, ?, ?, ?) "
            "ON CONFLICT(phone) DO UPDATE SET "
            "  meditation_step=excluded.meditation_step, "
            "  last_serene_at=COALESCE(excluded.last_serene_at, wa_state.last_serene_at), "
            "  updated_at=excluded.updated_at",
            (phone, meditation_step, last_serene_at, int(time.time())),
        )


# ---------------------------------------------------------------------------
# JWT minting (Option B from WHATSAPP_BOT_INTEGRATION.md)
# ---------------------------------------------------------------------------
def mint_jwt(phone: str) -> str:
    """Mint an HS256 JWT the backend will accept via LocalAuthStrategy."""
    now = int(time.time())
    payload = {
        "sub": f"wa-{phone}",
        "email": f"wa-{phone.replace('+', '').replace(':', '')}@bot.local",
        "role": "authenticated",
        "iat": now,
        "exp": now + 3600,
        "iss": "askmukthiguru-wa-bot",
    }
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")


# ---------------------------------------------------------------------------
# Markdown → WhatsApp formatting
# ---------------------------------------------------------------------------
def md_to_wa(text: str) -> str:
    """Convert backend markdown to WhatsApp's limited formatting."""
    # **bold** → *bold*
    text = re.sub(r"\*\*(.+?)\*\*", r"*\1*", text)
    # __italic__ or *italic* (single-asterisk italics from backend) → _italic_
    text = re.sub(r"__(.+?)__", r"_\1_", text)
    # [text](url) → text (url)
    text = re.sub(r"\[(.+?)\]\((.+?)\)", r"\1 (\2)", text)
    # Strip ```code blocks``` markers (WhatsApp supports backticks for inline only)
    text = re.sub(r"```\w*\n?", "", text)
    return text.strip()


def with_citations(text: str, citations: list[str]) -> str:
    if not citations:
        return text
    top = citations[:3]
    return text + "\n\n📜 _Sources:_\n" + "\n".join(f"• {c}" for c in top)


# ---------------------------------------------------------------------------
# Chat backend caller
# ---------------------------------------------------------------------------
def call_chat(phone: str, user_message: str) -> dict[str, Any]:
    """POST /api/chat. Raises requests.HTTPError on non-2xx; caller handles."""
    state = state_for(phone)
    body = {
        "messages": history_for(phone),
        "user_message": user_message,
        "session_id": f"wa-{phone}",
        "meditation_step": state["meditation_step"],
        "language": state["language"],
        "last_serene_mind_at": state["last_serene_at"],
    }
    headers = {
        "Authorization": f"Bearer {mint_jwt(phone)}",
        "Content-Type": "application/json",
    }
    resp = requests.post(
        f"{API_URL}/api/chat",
        headers=headers,
        data=json.dumps(body),
        timeout=WA_CHAT_TIMEOUT_S,
    )
    if resp.status_code == 401:
        # Re-mint once (clock skew or stale cache) and retry
        log.warning("chat 401 — re-minting JWT and retrying once")
        headers["Authorization"] = f"Bearer {mint_jwt(phone)}"
        resp = requests.post(
            f"{API_URL}/api/chat", headers=headers, data=json.dumps(body),
            timeout=WA_CHAT_TIMEOUT_S,
        )
    resp.raise_for_status()
    return resp.json()


# ---------------------------------------------------------------------------
# Twilio webhook
# ---------------------------------------------------------------------------
def _verify_twilio(req) -> bool:
    sig = req.headers.get("X-Twilio-Signature", "")
    url = req.url
    params = req.form.to_dict()
    return twilio_validator.validate(url, params, sig)


def _twiml(message: str) -> tuple[str, int, dict]:
    safe = (message or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return (
        f"<?xml version='1.0' encoding='UTF-8'?>\n<Response><Message>{safe}</Message></Response>",
        200,
        {"Content-Type": "application/xml"},
    )


FALLBACK_DOWN = (
    "🙏 I am catching my breath. Please send your message again in a few moments."
)
FALLBACK_GENERIC = (
    "🙏 Something went unexpectedly quiet on my end. Could you rephrase or try again?"
)


@app.route("/twilio/whatsapp", methods=["POST"])
def incoming():
    # 1. Authenticate the webhook
    if not _verify_twilio(request):
        log.warning("Twilio signature invalid — rejecting request")
        abort(403)

    phone = request.form.get("From", "")
    body = (request.form.get("Body") or "").strip()
    if not phone or not body:
        return _twiml("🙏 I didn't receive any text. Please try again.")

    # 2. Persist the user's message
    append_message(phone, "user", body)

    # 3. Call the chat backend
    try:
        resp = call_chat(phone, body)
    except requests.Timeout:
        log.warning("chat timeout for %s", phone)
        return _twiml(FALLBACK_DOWN)
    except requests.HTTPError as e:
        sc = e.response.status_code if e.response is not None else 0
        log.error("chat HTTP %s for %s: %s", sc, phone, e)
        return _twiml(FALLBACK_DOWN if sc in (429, 502, 503, 504) else FALLBACK_GENERIC)
    except Exception:
        log.exception("chat call failed for %s", phone)
        return _twiml(FALLBACK_GENERIC)

    # 4. Format response
    answer_text = md_to_wa(resp.get("response", "") or "")
    answer_text = with_citations(answer_text, resp.get("citations") or [])
    if not answer_text:
        answer_text = FALLBACK_GENERIC

    # 5. Persist response and updated state
    append_message(phone, "assistant", answer_text)
    update_state(
        phone,
        meditation_step=int(resp.get("meditation_step") or 0),
        last_serene_at=int(time.time()) if int(resp.get("meditation_step") or 0) == 0 else None,
    )

    # 6. Log trace_id for incident debugging
    log.info(
        "OK %s | trace=%s | tier=%s | latency=%sms",
        phone,
        resp.get("trace_id", "?"),
        resp.get("query_tier", "?"),
        resp.get("latency_ms", "?"),
    )

    return _twiml(answer_text)


@app.route("/healthz", methods=["GET"])
def healthz():
    return {"status": "ok", "db": WA_DB_PATH}


# ---------------------------------------------------------------------------
# Bootstrap
# ---------------------------------------------------------------------------
_init_db()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8080"))
    app.run(host="0.0.0.0", port=port, debug=False)
