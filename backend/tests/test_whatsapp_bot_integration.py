"""
Regression and Integration Tests for AskMukthiGuru WhatsApp Bot Bridge Service
=============================================================================

Validates:
  1. Fail-closed signature rejection (Twilio & Meta)
  2. Cryptographic signature acceptance (RFC HMAC-SHA1 & HMAC-SHA256)
  3. Meta webhook GET challenge verification
  4. Markdown-to-WhatsApp formatting & clickable link conversion
  5. Indian crisis helpline preservation (Tele-MANAS 14416, Kiran 1800-599-0019, 112)
  6. Phone-based session tracking (`wa-<phone_number>`) & JWT minting
  7. SQLite state and message persistence & cross-user isolation
  8. Immediate asynchronous webhook acknowledgment (<15s) and queue polling
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import jwt
import pytest

# Ensure whatsapp_bot directory is importable
_REPO_ROOT = Path(__file__).resolve().parents[2]
_WA_BOT_DIR = _REPO_ROOT / "whatsapp_bot"
if str(_WA_BOT_DIR) not in sys.path:
    sys.path.insert(0, str(_WA_BOT_DIR))

import wa_bot


@pytest.fixture(autouse=True)
def setup_test_environment(tmp_path, monkeypatch):
    """Isolate SQLite database and test secrets for each test."""
    test_db = tmp_path / "test_wa.db"
    monkeypatch.setenv("WA_DB_PATH", str(test_db))
    monkeypatch.setattr(wa_bot, "WA_DB_PATH", str(test_db))
    monkeypatch.setenv("JWT_SECRET", "test-secret-key-999")
    monkeypatch.setattr(wa_bot, "JWT_SECRET", "test-secret-key-999")
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", "test_twilio_auth_token_xyz")
    monkeypatch.setattr(wa_bot, "TWILIO_AUTH_TOKEN", "test_twilio_auth_token_xyz")
    monkeypatch.setenv("META_APP_SECRET", "test_meta_app_secret_abc123")
    monkeypatch.setattr(wa_bot, "META_APP_SECRET", "test_meta_app_secret_abc123")
    monkeypatch.setenv("META_VERIFY_TOKEN", "test_verify_token_1234")
    monkeypatch.setattr(wa_bot, "META_VERIFY_TOKEN", "test_verify_token_1234")
    wa_bot._init_db()
    yield


@pytest.fixture
def client():
    wa_bot.app.config["TESTING"] = True
    with wa_bot.app.test_client() as c:
        yield c


# ---------------------------------------------------------------------------
# 1. Signature Rejection Tests (Fail-Closed Security)
# ---------------------------------------------------------------------------
def test_twilio_signature_rejection_missing_header(client):
    """Inbound Twilio request without signature must return 403 Forbidden."""
    resp = client.post(
        "/whatsapp/twilio",
        data={"From": "whatsapp:+919876543210", "Body": "Namaste"},
    )
    assert resp.status_code == 403


def test_twilio_signature_rejection_forged_header(client):
    """Inbound Twilio request with invalid signature must return 403 Forbidden."""
    resp = client.post(
        "/whatsapp/twilio",
        data={"From": "whatsapp:+919876543210", "Body": "Namaste"},
        headers={"X-Twilio-Signature": "invalid_forged_signature"},
    )
    assert resp.status_code == 403


def test_twilio_signature_rejection_when_token_unset(client, monkeypatch):
    """When TWILIO_AUTH_TOKEN is unset, all Twilio requests fail closed."""
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", "")
    monkeypatch.setattr(wa_bot, "TWILIO_AUTH_TOKEN", "")
    resp = client.post(
        "/whatsapp/twilio",
        data={"From": "whatsapp:+919876543210", "Body": "Namaste"},
        headers={"X-Twilio-Signature": "any_signature"},
    )
    assert resp.status_code == 403


def test_meta_signature_rejection_missing_header(client):
    """Inbound Meta request without signature must return 403 Forbidden."""
    payload = {
        "entry": [{
            "changes": [{
                "value": {
                    "messages": [{"from": "919876543210", "text": {"body": "Namaste"}}]
                }
            }]
        }]
    }
    resp = client.post("/whatsapp/meta", json=payload)
    assert resp.status_code == 403


def test_meta_signature_rejection_invalid_header(client):
    """Inbound Meta request with invalid signature must return 403 Forbidden."""
    payload = {"entry": []}
    resp = client.post(
        "/whatsapp/meta",
        data=json.dumps(payload),
        headers={"X-Hub-Signature-256": "sha256=0000000000000000000000000000000000000000000000000000000000000000"},
        content_type="application/json",
    )
    assert resp.status_code == 403


def test_meta_signature_rejection_when_secret_unset(client, monkeypatch):
    """When META_APP_SECRET is unset, all Meta requests fail closed."""
    monkeypatch.setenv("META_APP_SECRET", "")
    monkeypatch.setattr(wa_bot, "META_APP_SECRET", "")
    resp = client.post(
        "/whatsapp/meta",
        data=b"{}",
        headers={"X-Hub-Signature-256": "sha256=1234567890abcdef"},
        content_type="application/json",
    )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# 2. Cryptographic Signature Acceptance Tests
# ---------------------------------------------------------------------------
def test_twilio_valid_signature_acceptance():
    """Verify that a legitimate RFC Twilio signature is accepted."""
    url = "http://localhost/whatsapp/twilio"
    params = {"Body": "What is the Beautiful State?", "From": "whatsapp:+919876543210"}
    token = "test_twilio_auth_token_xyz"
    sig = wa_bot.compute_twilio_signature(url, params, token)

    req_mock = MagicMock()
    req_mock.url = url
    req_mock.form.to_dict.return_value = params
    req_mock.headers = {"X-Twilio-Signature": sig}

    assert wa_bot.validate_twilio_signature(req_mock) is True


def test_meta_valid_signature_acceptance():
    """Verify that a legitimate Meta HMAC-SHA256 signature is accepted."""
    raw_body = b'{"object":"whatsapp_business_account"}'
    secret = "test_meta_app_secret_abc123"
    computed_digest = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    sig_header = f"sha256={computed_digest}"

    req_mock = MagicMock()
    req_mock.get_data.return_value = raw_body
    req_mock.headers = {"X-Hub-Signature-256": sig_header}

    assert wa_bot.validate_meta_signature(req_mock) is True


def test_meta_webhook_verification_challenge(client):
    """GET /whatsapp/meta returns challenge when hub.verify_token matches."""
    resp = client.get("/whatsapp/meta?hub.mode=subscribe&hub.verify_token=test_verify_token_1234&hub.challenge=test_challenge_999")
    assert resp.status_code == 200
    assert resp.data.decode("utf-8") == "test_challenge_999"


def test_meta_webhook_verification_token_mismatch(client):
    """GET /whatsapp/meta returns 403 when verify token does not match."""
    resp = client.get("/whatsapp/meta?hub.mode=subscribe&hub.verify_token=wrong_token&hub.challenge=test_challenge_999")
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# 3. Markdown to WhatsApp Formatting & Link Conversion
# ---------------------------------------------------------------------------
def test_markdown_to_whatsapp_formatting():
    """Verify clean conversion of markdown bold, italic, links, headers, and bullet points."""
    md_text = (
        "### The Four Sacred Secrets\n"
        "**Peace** begins within.\n"
        "__Awareness__ is the key.\n"
        "Check this discourse: [Krishnaji on Suffering](https://www.youtube.com/watch?v=abcd1234)\n"
        "* First step: observe\n"
        "- Second step: breathe"
    )
    formatted = wa_bot.md_to_wa(md_text)

    # Headers converted to bold
    assert "*The Four Sacred Secrets*" in formatted
    # Bold converted to single asterisk
    assert "*Peace*" in formatted
    # Italic converted to underscore
    assert "_Awareness_" in formatted
    # Markdown links unwrapped to clean clickable URLs
    assert "Krishnaji on Suffering (https://www.youtube.com/watch?v=abcd1234)" in formatted
    # Bullets normalized
    assert "• First step: observe" in formatted
    assert "• Second step: breathe" in formatted


def test_with_citations_formatting():
    """Verify citations are formatted with sources header and bullets."""
    text = "The beautiful state is a choice."
    citations = ["https://youtube.com/watch?v=111", "https://youtube.com/watch?v=222"]
    with_cites = wa_bot.with_citations(text, citations)

    assert "📜 *Sources:*" in with_cites
    assert "• https://youtube.com/watch?v=111" in with_cites
    assert "• https://youtube.com/watch?v=222" in with_cites


# ---------------------------------------------------------------------------
# 4. Indian Crisis Helpline & Clinical Safety Preservation
# ---------------------------------------------------------------------------
def test_crisis_forwarding_and_helpline_preservation():
    """Verify Indian crisis hotlines survive formatting without truncation or modification."""
    crisis_text = (
        "If you are feeling overwhelmed or having thoughts of self-harm, please know that you are not alone.\n\n"
        "Please connect immediately with dedicated support:\n"
        "• Tele-MANAS (India): **14416** (24x7 toll-free mental health helpline)\n"
        "• Kiran Mental Health Helpline: **1800-599-0019**\n"
        "• National Emergency Services: **112**\n\n"
        "Help is available right now."
    )
    formatted = wa_bot.format_whatsapp_response(crisis_text)

    # Helplines must be preserved completely
    assert "14416" in formatted
    assert "1800-599-0019" in formatted
    assert "112" in formatted
    assert "Tele-MANAS" in formatted
    assert "Kiran" in formatted
    # Bolding of numbers converted cleanly
    assert "*14416*" in formatted
    assert "*1800-599-0019*" in formatted
    assert "*112*" in formatted


# ---------------------------------------------------------------------------
# 5. Session Tracking, Phone Normalization & JWT Minting
# ---------------------------------------------------------------------------
def test_phone_sanitization():
    """Verify phone normalization strips whatsapp: prefix and retains + and digits."""
    assert wa_bot.sanitize_phone("whatsapp:+919876543210") == "+919876543210"
    assert wa_bot.sanitize_phone("+1 (415) 523-8886") == "+14155238886"
    assert wa_bot.sanitize_phone("919876543210") == "919876543210"


def test_jwt_minting_matches_wa_prefix():
    """Verify JWT minting sets sub to wa-<phone> and is signed with JWT_SECRET."""
    phone = "+919876543210"
    token = wa_bot.mint_jwt(phone)
    decoded = jwt.decode(token, "test-secret-key-999", algorithms=["HS256"])

    assert decoded["sub"] == "wa-+919876543210"
    assert decoded["email"] == "wa-919876543210@bot.local"
    assert decoded["role"] == "authenticated"
    assert decoded["iss"] == "askmukthiguru-wa-bot"
    assert decoded["exp"] > time.time()


def test_sqlite_message_persistence_and_isolation():
    """Verify conversation history is persisted and isolated between phones."""
    phone_a = "+919876543210"
    phone_b = "+911122334455"

    wa_bot.append_message(phone_a, "user", "Hello from A")
    wa_bot.append_message(phone_a, "assistant", "Peace to you, A")
    wa_bot.append_message(phone_b, "user", "Hello from B")

    history_a = wa_bot.history_for(phone_a)
    history_b = wa_bot.history_for(phone_b)

    assert len(history_a) == 2
    assert history_a[0] == {"role": "user", "content": "Hello from A"}
    assert history_a[1] == {"role": "assistant", "content": "Peace to you, A"}

    assert len(history_b) == 1
    assert history_b[0] == {"role": "user", "content": "Hello from B"}


def test_sqlite_meditation_state_tracking():
    """Verify meditation steps and serene mind timestamps are persisted."""
    phone = "+919876543210"
    initial_state = wa_bot.state_for(phone)
    assert initial_state["meditation_step"] == 0

    now = int(time.time())
    wa_bot.update_state(phone, meditation_step=2, last_serene_at=now, language="hi")
    updated = wa_bot.state_for(phone)

    assert updated["meditation_step"] == 2
    assert updated["last_serene_at"] == now
    assert updated["language"] == "hi"


# ---------------------------------------------------------------------------
# 6. Asynchronous Immediate Acknowledgment & Outbound Dispatch
# ---------------------------------------------------------------------------
def test_twilio_immediate_acknowledgment(client, monkeypatch):
    """Twilio incoming message must return empty TwiML <Response></Response> immediately."""
    monkeypatch.setattr(wa_bot, "validate_twilio_signature", lambda req: True)
    monkeypatch.setattr(wa_bot, "ASYNC_WEBHOOK_ACK", True)

    with patch.object(wa_bot, "process_chat_turn") as mock_turn:
        resp = client.post(
            "/whatsapp/twilio",
            data={"From": "whatsapp:+919876543210", "Body": "Guide me"},
        )
        assert resp.status_code == 200
        assert "<Response></Response>" in resp.data.decode("utf-8")


def test_meta_immediate_acknowledgment(client, monkeypatch):
    """Meta incoming message must return status: received immediately."""
    monkeypatch.setattr(wa_bot, "validate_meta_signature", lambda req: True)
    monkeypatch.setattr(wa_bot, "ASYNC_WEBHOOK_ACK", True)

    payload = {
        "entry": [{
            "changes": [{
                "value": {
                    "metadata": {"phone_number_id": "123456789"},
                    "messages": [{"from": "919876543210", "text": {"body": "Guide me"}}]
                }
            }]
        }]
    }

    with patch.object(wa_bot, "process_chat_turn") as mock_turn:
        resp = client.post("/whatsapp/meta", json=payload)
        assert resp.status_code == 200
        data = resp.get_json()
        assert data.get("status") == "received"


def test_chat_turn_job_queue_polling():
    """Verify process_chat_turn polls job queue when backend returns 202 queued job_id."""
    phone = "+919876543210"
    jwt_token = wa_bot.mint_jwt(phone)

    mock_chat_resp = {"job_id": "job_queue_test_123", "status": "queued"}
    mock_job_resp = MagicMock()
    mock_job_resp.json.return_value = {
        "status": "completed",
        "result": {
            "response": "**True happiness** is undisturbed.",
            "citations": ["https://youtube.com/watch?v=wisdom"],
            "meditation_step": 1,
        }
    }
    mock_job_resp.status_code = 200

    with patch.object(wa_bot, "call_chat", return_value=mock_chat_resp), \
         patch("requests.get", return_value=mock_job_resp), \
         patch.object(wa_bot, "push_twilio_message") as mock_push:

        answer = wa_bot.process_chat_turn("twilio", phone, "What is joy?")
        assert "*True happiness*" in answer
        assert "📜 *Sources:*" in answer
        assert mock_push.called
