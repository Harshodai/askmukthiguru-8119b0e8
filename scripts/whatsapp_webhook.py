import hashlib
import hmac
import html
import json
import logging
import os
import re
import threading
import time
import urllib.parse
from typing import Any

import requests
from flask import Flask, abort, jsonify, request
from twilio.request_validator import RequestValidator
from twilio.twiml.messaging_response import MessagingResponse

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)


# Configuration (loaded from environment or defaults)
BACKEND_URL = os.getenv('BACKEND_URL', 'http://localhost:8000')
BACKEND_TOKEN = os.getenv('BACKEND_TOKEN', '')
VERIFY_TOKEN = os.getenv('VERIFY_TOKEN', '')
TWILIO_AUTH_TOKEN = os.getenv('TWILIO_AUTH_TOKEN', '')
META_APP_SECRET = os.getenv('META_APP_SECRET', '')
PORT = int(os.getenv('PORT', 5000))
# This legacy broker is intentionally frozen until its identity, consent,
# replay/idempotency, deletion, redaction, and production-runtime controls have
# passed the release gate. Accidental deployments return 404 for every route.
WHATSAPP_WEBHOOK_ENABLED = os.getenv('WHATSAPP_WEBHOOK_ENABLED', '').lower() == 'true'


@app.before_request
def reject_when_broker_is_disabled():
    if not WHATSAPP_WEBHOOK_ENABLED:
        abort(404)


def sanitize_log_input(text: Any, max_length: int = 500) -> str:
    """Sanitize log input against CRLF and log injection (CWE-117)."""
    if text is None:
        return ""
    cleaned = str(text).replace("\r", "").replace("\n", " ")
    cleaned = "".join(ch for ch in cleaned if ch.isprintable() or ch == " ")
    return cleaned[:max_length]


def validate_twilio_signature(req) -> bool:
    """Validates X-Twilio-Signature against TWILIO_AUTH_TOKEN."""
    if not TWILIO_AUTH_TOKEN:
        logger.error("TWILIO_AUTH_TOKEN is not configured; rejecting request.")
        return False

    signature = req.headers.get('X-Twilio-Signature', '')
    validator = RequestValidator(TWILIO_AUTH_TOKEN)
    url = req.url
    # Twilio POST parameters
    post_vars = req.form.to_dict()
    return validator.validate(url, post_vars, signature)


def validate_meta_signature(req) -> bool:
    """Validates X-Hub-Signature-256 against META_APP_SECRET."""
    if not META_APP_SECRET:
        logger.error("META_APP_SECRET is not configured; rejecting request.")
        return False

    header_sig = req.headers.get('X-Hub-Signature-256', '')
    if not header_sig.startswith('sha256='):
        return False

    expected_sig = header_sig[7:]
    raw_body = req.get_data()
    computed_sig = hmac.new(META_APP_SECRET.encode('utf-8'), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(computed_sig, expected_sig)


# In-memory conversation cache with TTL
# { session_id: {"messages": [{role, content}], "timestamp": epoch_seconds} }
conversations = {}
CACHE_TTL_SECONDS = 1800
MAX_CACHE_SIZE = 1000
_CACHE_LOCK = threading.Lock()


def _prune_cache():
    with _CACHE_LOCK:
        now = time.time()
        expired = [
            sid for sid, data in conversations.items()
            if now - data.get("timestamp", 0) > CACHE_TTL_SECONDS
        ]
        for sid in expired:
            del conversations[sid]
        if len(conversations) > MAX_CACHE_SIZE:
            sorted_by_age = sorted(conversations.items(), key=lambda x: x[1].get("timestamp", 0))
            for sid, _ in sorted_by_age[:100]:
                del conversations[sid]


def get_session_history(session_id: str) -> list:
    with _CACHE_LOCK:
        _prune_cache()
        data = conversations.get(session_id)
        if data is None:
            return []
        return data["messages"][-10:]


def save_to_history(session_id: str, role: str, content: str):
    with _CACHE_LOCK:
        now = time.time()
        if session_id not in conversations:
            conversations[session_id] = {"messages": [], "timestamp": now}
        conversations[session_id]["messages"].append({"role": role, "content": content})
        conversations[session_id]["timestamp"] = now
        if len(conversations[session_id]["messages"]) > 20:
            conversations[session_id]["messages"] = conversations[session_id]["messages"][-20:]
        _prune_cache()


def strip_markdown(text: str) -> str:
    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
    text = re.sub(r'\*(.+?)\*', r'\1', text)
    text = re.sub(r'###?\s*', '', text)
    text = re.sub(r'`(.+?)`', r'\1', text)
    return text.strip()


MAX_MSG_LENGTH = 4096


def _chunk_text(text: str) -> list[str]:
    if len(text) <= MAX_MSG_LENGTH:
        return [text]
    return [text[i:i + MAX_MSG_LENGTH] for i in range(0, len(text), MAX_MSG_LENGTH)]


_ALLOWED_META_HOST = "graph.facebook.com"
_PHONE_NUMBER_ID_RE = re.compile(r"^\d{1,32}$")


def _send_meta_whatsapp_message(
    phone_number_id: str,
    to_number: str,
    body_text: str,
    whatsapp_token: str,
) -> bool:
    """
    Safely send WhatsApp message via Meta Cloud API.
    Strictly validates phone_number_id and destination URL to prevent SSRF (CWE-918).
    """
    if not phone_number_id or not _PHONE_NUMBER_ID_RE.match(str(phone_number_id)):
        logger.error(
            "Invalid phone_number_id format rejected: %s",
            sanitize_log_input(phone_number_id),
        )
        return False

    safe_phone_id = urllib.parse.quote(str(phone_number_id), safe="")
    url = f"https://{_ALLOWED_META_HOST}/v18.0/{safe_phone_id}/messages"

    parsed = urllib.parse.urlparse(url)
    if (
        parsed.scheme != "https"
        or parsed.netloc.lower() != _ALLOWED_META_HOST
        or not parsed.path.startswith("/v18.0/")
        or not parsed.path.endswith("/messages")
    ):
        logger.error("SSRF guard rejected URL: %s", sanitize_log_input(url))
        return False

    try:
        meta_response = requests.post(
            url,
            json={
                "messaging_product": "whatsapp",
                "to": to_number,
                "text": {"body": body_text},
            },
            headers={
                "Authorization": f"Bearer {whatsapp_token}",
                "Content-Type": "application/json",
            },
            timeout=10,
        )
        meta_response.raise_for_status()
        return True
    except Exception as exc:
        logger.error("Failed to send Meta WhatsApp message: %s", sanitize_log_input(exc))
        return False


@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({"status": "ok", "backend_url": BACKEND_URL}), 200


# ── 1. TWILIO WEBHOOK ROUTE ──
@app.route('/whatsapp/twilio', methods=['POST'])
def twilio_webhook():
    """Webhook handler for Twilio WhatsApp incoming messages."""
    if not validate_twilio_signature(request):
        logger.warning("Invalid Twilio signature rejected.")
        return 'Unauthorized signature', 403

    incoming_msg = request.values.get('Body', '').strip()
    from_number = request.values.get('From', '').replace('whatsapp:', '').strip()

    if not incoming_msg:
        logger.warning("Received empty message body from Twilio.")
        return '', 200

    session_id = f"whatsapp_{from_number}"
    logger.info(
        "Incoming Twilio message from %s: %s",
        sanitize_log_input(from_number),
        sanitize_log_input(incoming_msg),
    )

    # Retrieve last 10 messages for conversation context
    history = get_session_history(session_id)

    try:
        response = requests.post(
            f"{BACKEND_URL}/api/chat",
            json={
                "messages": history,
                "user_message": incoming_msg,
                "session_id": session_id,
                "language": "en",
            },
            headers={
                "Authorization": f"Bearer {BACKEND_TOKEN}",
                "Content-Type": "application/json",
            },
            timeout=30,
        )

        if response.status_code == 503:
            ai_response = "🙏 The Guru is deep in meditation. Please try again in a moment."
        elif response.status_code == 429:
            ai_response = "🙏 Please wait a moment before your next question."
        elif response.status_code == 500:
            ai_response = "🙏 The Guru needs a moment. Please try again shortly."
        else:
            response.raise_for_status()
            data = response.json()
            ai_response = data.get("response", "I apologize, something went wrong.")

        ai_response = strip_markdown(ai_response)

        save_to_history(session_id, "user", incoming_msg)
        # Only save assistant response if backend call was successful (2xx)
        if 200 <= response.status_code < 300:
            save_to_history(session_id, "assistant", ai_response)

        resp = MessagingResponse()
        for chunk in _chunk_text(ai_response):
            resp.message(chunk)
        return str(resp)

    except requests.exceptions.Timeout:
        logger.error("Timeout connecting to AskMukthiGuru backend.")
        resp = MessagingResponse()
        resp.message("🙏 The Guru is taking longer than usual. Please try again.")
        return str(resp)
    except requests.exceptions.ConnectionError:
        logger.error("Connection error connecting to AskMukthiGuru backend.")
        resp = MessagingResponse()
        resp.message("🙏 Unable to reach the Guru. Please check your connection.")
        return str(resp)
    except Exception as e:
        logger.error("Error handling Twilio webhook: %s", sanitize_log_input(e), exc_info=True)
        resp = MessagingResponse()
        resp.message("🙏 Something went unexpectedly quiet on my end. Could you try again?")
        return str(resp)


# ── 2. META CLOUD API WEBHOOK ROUTES ──
@app.route('/whatsapp/meta', methods=['GET'])
def verify_meta_webhook():
    """Required verification route for Meta Developer webhook registration."""
    mode = request.args.get('hub.mode')
    token = request.args.get('hub.verify_token')
    challenge = request.args.get('hub.challenge')

    if mode == 'subscribe' and token == VERIFY_TOKEN:
        logger.info("Meta webhook verification successful.")
        return html.escape(str(challenge or "")), 200
    else:
        logger.warning("Meta webhook verification failed: Invalid verify token.")
        return 'Forbidden', 403


@app.route('/whatsapp/meta', methods=['POST'])
def meta_webhook():
    """Webhook handler for Meta Cloud API incoming messages."""
    if not validate_meta_signature(request):
        logger.warning("Invalid Meta signature rejected.")
        return 'Unauthorized signature', 403

    body = request.get_json()
    logger.info("Incoming Meta payload: %s", sanitize_log_input(json.dumps(body)))

    # Extract message details
    try:
        entry = body.get('entry', [{}])[0]
        changes = entry.get('changes', [{}])[0]
        value = changes.get('value', {})
        message = value.get('messages', [{}])[0]

        if not message:
            return 'No message payload', 200

        from_number = message.get('from')
        msg_body = message.get('text', {}).get('body', '').strip()
        phone_number_id = value.get('metadata', {}).get('phone_number_id')

        if not msg_body or not from_number or not phone_number_id:
            return 'Incomplete payload', 200

    except (IndexError, KeyError, AttributeError):
        return 'Ignored non-message event', 200

    session_id = f"whatsapp_{from_number}"
    history = get_session_history(session_id)

    try:
        response = requests.post(
            f"{BACKEND_URL}/api/chat",
            json={
                "messages": history,
                "user_message": msg_body,
                "session_id": session_id,
                "language": "en",
            },
            headers={
                "Authorization": f"Bearer {BACKEND_TOKEN}",
                "Content-Type": "application/json",
            },
            timeout=30,
        )

        if response.status_code == 503:
            ai_response = "🙏 The Guru is deep in meditation. Please try again in a moment."
        elif response.status_code == 429:
            ai_response = "🙏 Please wait a moment before your next question."
        elif response.status_code == 500:
            ai_response = "🙏 The Guru needs a moment. Please try again shortly."
        else:
            response.raise_for_status()
            data = response.json()
            ai_response = data.get("response", "I apologize, something went wrong.")

        ai_response = strip_markdown(ai_response)

        save_to_history(session_id, "user", msg_body)
        # Only save assistant response if backend call was successful (2xx)
        if 200 <= response.status_code < 300:
            save_to_history(session_id, "assistant", ai_response)

        whatsapp_token = os.getenv('WHATSAPP_TOKEN')
        if not whatsapp_token:
            logger.error("Missing WHATSAPP_TOKEN environment variable. Cannot reply to Meta.")
            return 'Missing WHATSAPP_TOKEN', 500

        for chunk in _chunk_text(ai_response):
            sent = _send_meta_whatsapp_message(
                phone_number_id=phone_number_id,
                to_number=from_number,
                body_text=chunk,
                whatsapp_token=whatsapp_token,
            )
            if not sent:
                return 'Failed to send WhatsApp message', 500
        return 'OK', 200

    except requests.exceptions.Timeout:
        logger.error("Timeout connecting to AskMukthiGuru backend for Meta webhook.")
        whatsapp_token = os.getenv('WHATSAPP_TOKEN')
        if whatsapp_token and 'from_number' in locals() and 'phone_number_id' in locals():
            _send_meta_whatsapp_message(
                phone_number_id=phone_number_id,
                to_number=from_number,
                body_text="🙏 The Guru is taking longer than usual. Please try again.",
                whatsapp_token=whatsapp_token,
            )
        return '🙏 The Guru is taking longer than usual. Please try again.', 200
    except requests.exceptions.ConnectionError:
        logger.error("Connection error connecting to AskMukthiGuru backend for Meta webhook.")
        whatsapp_token = os.getenv('WHATSAPP_TOKEN')
        if whatsapp_token and 'from_number' in locals() and 'phone_number_id' in locals():
            _send_meta_whatsapp_message(
                phone_number_id=phone_number_id,
                to_number=from_number,
                body_text="🙏 Unable to reach the Guru. Please check your connection.",
                whatsapp_token=whatsapp_token,
            )
        return '🙏 Unable to reach the Guru. Please check your connection.', 200
    except Exception as e:
        logger.error("Error handling Meta webhook: %s", sanitize_log_input(e), exc_info=True)
        whatsapp_token = os.getenv('WHATSAPP_TOKEN')
        if whatsapp_token and 'from_number' in locals() and 'phone_number_id' in locals():
            _send_meta_whatsapp_message(
                phone_number_id=phone_number_id,
                to_number=from_number,
                body_text="🙏 Something went unexpectedly quiet on my end. Could you try again?",
                whatsapp_token=whatsapp_token,
            )
        return '🙏 Something went unexpectedly quiet on my end. Could you try again?', 200


if __name__ == '__main__':
    if not WHATSAPP_WEBHOOK_ENABLED:
        logger.error(
            'WhatsApp webhook broker is disabled; set WHATSAPP_WEBHOOK_ENABLED=true only after release approval.'
        )
        raise SystemExit(1)
    logger.info("Starting WhatsApp Webhook broker on port %s...", sanitize_log_input(PORT))
    app.run(host='0.0.0.0', port=PORT)

