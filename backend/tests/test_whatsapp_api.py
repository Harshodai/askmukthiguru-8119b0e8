"""
Tests for WhatsApp Meta Cloud API Webhook, Account Linking, and DPDP Consent.
=============================================================================
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import hmac
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from services.whatsapp_service import (
    CRISIS_HELPLINE_COPY,
    clean_phone,
    create_link_challenge,
    format_whatsapp_message,
    generate_link_token,
    get_link_status,
    hash_phone,
    hash_token,
    likely_crisis,
    mask_phone,
    unlink_account,
    update_link_consent,
    validate_meta_signature,
    verify_link_challenge,
)
from tasks.whatsapp_tasks import process_whatsapp_turn_task


@pytest.fixture
def client():
    return TestClient(app)


# ---------------------------------------------------------------------------
# Unit Tests: Phone Utilities & Cryptography
# ---------------------------------------------------------------------------

def test_clean_and_mask_phone():
    assert clean_phone("whatsapp:+919876543210") == "+919876543210"
    assert clean_phone("  +91 98765 43210  ") == "+919876543210"
    assert clean_phone(None) == ""

    assert mask_phone("+919876543210") == "+9198*** **210"
    assert mask_phone("+14155238886") == "+1415*** **886"
    assert mask_phone("123") == "+1***23"
    assert mask_phone("") == ""


def test_hash_phone_deterministic():
    h1 = hash_phone("+919876543210")
    h2 = hash_phone("whatsapp:+91 98765 43210")
    assert h1 == h2
    assert len(h1) == 64
    assert hash_phone(None) == ""


def test_challenge_tokens_are_unique_and_hashed():
    t1 = generate_link_token()
    t2 = generate_link_token()
    assert t1 != t2
    assert len(t1) >= 32

    h1 = hash_token(t1)
    h2 = hash_token(t1)
    assert h1 == h2
    assert len(h1) == 64


def test_meta_signature_validation():
    secret = "test_meta_secret_key"
    body = b'{"object":"whatsapp_business_account"}'
    computed = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    valid_header = f"sha256={computed}"

    assert validate_meta_signature(body, valid_header, secret) is True
    assert validate_meta_signature(body, "sha256=invalid_hex", secret) is False
    assert validate_meta_signature(body, None, secret) is False
    assert validate_meta_signature(body, valid_header, "") is False


def test_crisis_preemption_detection():
    assert likely_crisis("I want to kill myself") is True
    assert likely_crisis("I want to end my life right now") is True
    assert likely_crisis("Feeling suicidal and hopeless") is True
    assert likely_crisis("मरना चाहता हूँ") is True
    assert likely_crisis("What is the nature of suffering according to Krishnaji?") is False
    assert likely_crisis("How do I meditate?") is False
    assert likely_crisis("") is False


def test_whatsapp_formatting():
    markdown = "Here is **bold teaching** and a link to [AskMukthiGuru](https://askmukthiguru.com)."
    formatted = format_whatsapp_message(markdown, ["Sri Preethaji - The Art of Inner Peace"])
    assert "*bold teaching*" in formatted
    assert "AskMukthiGuru (https://askmukthiguru.com)" in formatted
    assert "Sri Preethaji - The Art of Inner Peace" in formatted


# ---------------------------------------------------------------------------
# Integration Tests: Meta Webhook GET Verification
# ---------------------------------------------------------------------------

def test_meta_webhook_verification_success(client, monkeypatch):
    monkeypatch.setattr(settings, "meta_verify_token", "my_secret_verify_token")

    response = client.get(
        "/api/whatsapp/webhook",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": "my_secret_verify_token",
            "hub.challenge": "1158201211",
        },
    )
    assert response.status_code == 200
    assert response.text == "1158201211"


def test_meta_webhook_verification_token_mismatch(client, monkeypatch):
    monkeypatch.setattr(settings, "meta_verify_token", "correct_token")

    response = client.get(
        "/api/whatsapp/webhook",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": "wrong_token",
            "hub.challenge": "1158201211",
        },
    )
    assert response.status_code == 403


def test_meta_webhook_verification_invalid_mode(client, monkeypatch):
    monkeypatch.setattr(settings, "meta_verify_token", "my_token")

    response = client.get(
        "/api/whatsapp/webhook",
        params={
            "hub.mode": "unsubscribe",
            "hub.verify_token": "my_token",
            "hub.challenge": "1158201211",
        },
    )
    assert response.status_code == 403


# ---------------------------------------------------------------------------
# Integration Tests: Meta Webhook POST Inbound Handling
# ---------------------------------------------------------------------------

def test_meta_webhook_post_signature_rejected(client, monkeypatch):
    monkeypatch.setattr(settings, "meta_app_secret", "super_secret_app_key")

    response = client.post(
        "/api/whatsapp/webhook",
        json={"entry": []},
        headers={"X-Hub-Signature-256": "sha256=invalid"},
    )
    assert response.status_code == 403


def test_meta_webhook_post_crisis_preemption(client, monkeypatch):
    monkeypatch.setattr(settings, "meta_app_secret", "")

    payload = {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "metadata": {"phone_number_id": "100200300"},
                            "messages": [
                                {
                                    "id": "wamid.crisis_1",
                                    "from": "919876543210",
                                    "type": "text",
                                    "text": {"body": "I want to end my life"},
                                }
                            ],
                        }
                    }
                ]
            }
        ]
    }

    with patch("tasks.whatsapp_tasks._send_meta_outbound") as mock_send:
        resp = client.post("/api/whatsapp/webhook", json=payload)
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}
        assert mock_send.called
        args, _ = mock_send.call_args
        assert args[0] == "100200300"
        assert args[1] == "+919876543210"
        assert "Tele-MANAS" in args[2]
        assert "14416" in args[2]


def test_meta_webhook_post_link_command(client, monkeypatch):
    monkeypatch.setattr(settings, "meta_app_secret", "")

    payload = {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "metadata": {"phone_number_id": "100200300"},
                            "messages": [
                                {
                                    "id": "wamid.link_1",
                                    "from": "919876543210",
                                    "type": "text",
                                    "text": {"body": "LINK"},
                                }
                            ],
                        }
                    }
                ]
            }
        ]
    }

    mock_db = MagicMock()
    mock_db.table.return_value.insert.return_value.execute.return_value = MagicMock(data=[{}])

    with patch("app.dependencies.ServiceContainer.supabase_client", mock_db, create=True), \
         patch("tasks.whatsapp_tasks._send_meta_outbound") as mock_send:
        resp = client.post("/api/whatsapp/webhook", json=payload)
        assert resp.status_code == 200
        assert mock_send.called
        args, _ = mock_send.call_args
        assert "Connect AskMukthiGuru Account" in args[2]
        assert "/link-whatsapp#code=" in args[2]


def test_meta_webhook_post_privacy_commands(client, monkeypatch):
    monkeypatch.setattr(settings, "meta_app_secret", "")

    # STOP command
    payload_stop = {
        "entry": [{
            "changes": [{
                "value": {
                    "metadata": {"phone_number_id": "100200300"},
                    "messages": [{"id": "wamid.stop_1", "from": "919876543210", "type": "text", "text": {"body": "STOP"}}],
                }
            }]
        }]
    }
    with patch("tasks.whatsapp_tasks._send_meta_outbound") as mock_send:
        resp = client.post("/api/whatsapp/webhook", json=payload_stop)
        assert resp.status_code == 200
        assert "opted out" in mock_send.call_args[0][2]

    # RESET command
    payload_reset = {
        "entry": [{
            "changes": [{
                "value": {
                    "metadata": {"phone_number_id": "100200300"},
                    "messages": [{"id": "wamid.reset_1", "from": "919876543210", "type": "text", "text": {"body": "RESET"}}],
                }
            }]
        }]
    }
    with patch("tasks.whatsapp_tasks._send_meta_outbound") as mock_send:
        resp = client.post("/api/whatsapp/webhook", json=payload_reset)
        assert resp.status_code == 200
        assert "Fresh page" in mock_send.call_args[0][2]


def test_meta_webhook_deduplication(client, monkeypatch):
    monkeypatch.setattr(settings, "meta_app_secret", "")

    payload = {
        "entry": [{
            "changes": [{
                "value": {
                    "metadata": {"phone_number_id": "100200300"},
                    "messages": [{"id": "wamid.dedup_test_100", "from": "919876543210", "type": "text", "text": {"body": "HELP"}}],
                }
            }]
        }]
    }
    with patch("tasks.whatsapp_tasks._send_meta_outbound") as mock_send:
        # First delivery
        client.post("/api/whatsapp/webhook", json=payload)
        assert mock_send.call_count == 1

        # Second delivery of same wamid
        client.post("/api/whatsapp/webhook", json=payload)
        assert mock_send.call_count == 1  # Not sent again


# ---------------------------------------------------------------------------
# Account Linking & DPDP Consent Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_account_linking_lifecycle():
    fake_db = MagicMock()
    phone = "+919876543210"
    user_id = "user_12345_uuid"

    # 1. Create challenge
    fake_db.table.return_value.insert.return_value.execute.return_value = MagicMock(data=[{}])
    token, challenge = await create_link_challenge(fake_db, phone, confirmed_whatsapp=True)
    assert token
    assert challenge["phone_number_masked"] == "+9198*** **210"

    # 2. Verify challenge
    challenge_row = {
        "id": "challenge_uuid_1",
        "challenge_token_hash": hash_token(token),
        "phone_number_hash": challenge["phone_number_hash"],
        "phone_number_masked": challenge["phone_number_masked"],
        "phone_number_raw": phone,
        "consumed_at": None,
        "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat(),
    }
    fake_db.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
        data=[challenge_row]
    )
    fake_db.table.return_value.upsert.return_value.execute.return_value = MagicMock(
        data=[{
            "user_id": user_id,
            "phone_number_masked": "+9198*** **210",
            "status": "active",
            "sync_history_consent": False,
            "memory_write_consent": False,
            "linked_at": datetime.now(timezone.utc).isoformat(),
        }]
    )

    linked = await verify_link_challenge(fake_db, token, user_id)
    assert linked["user_id"] == user_id
    assert linked["sync_history_consent"] is False
    assert linked["memory_write_consent"] is False

    # 3. Attempt replay (should fail)
    challenge_row["consumed_at"] = datetime.now(timezone.utc).isoformat()
    with pytest.raises(ValueError, match="already been used"):
        await verify_link_challenge(fake_db, token, user_id)

    # 4. Attempt expired token (should fail)
    challenge_row["consumed_at"] = None
    challenge_row["expires_at"] = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
    with pytest.raises(ValueError, match="expired"):
        await verify_link_challenge(fake_db, token, user_id)

    # 5. Consent decoupling update
    fake_db.table.return_value.update.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
        data=[{
            "phone_number_masked": "+9198*** **210",
            "sync_history_consent": True,
            "memory_write_consent": False,
            "linked_at": datetime.now(timezone.utc).isoformat(),
        }]
    )
    consent = await update_link_consent(fake_db, user_id, sync_history_consent=True)
    assert consent["sync_history_consent"] is True
    assert consent["memory_write_consent"] is False

    # 6. Unlink
    fake_db.table.return_value.update.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
        data=[{"status": "unlinked"}]
    )
    assert await unlink_account(fake_db, user_id) is True


# ---------------------------------------------------------------------------
# Celery Durable Task Tests
# ---------------------------------------------------------------------------

def test_celery_task_crisis_preemption():
    with patch("tasks.whatsapp_tasks._send_meta_outbound") as mock_send:
        result = process_whatsapp_turn_task(
            channel="meta",
            phone="+919876543210",
            user_message="I cannot take this anymore, I want to kill myself",
            metadata={"phone_number_id": "100200300"},
        )
        assert result["status"] == "crisis_preempted"
        assert mock_send.called
        assert "Tele-MANAS" in mock_send.call_args[0][2]
