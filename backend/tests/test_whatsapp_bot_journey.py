"""
WhatsApp user-journey tests for AskMukthiGuru (whatsapp_bot/wa_bot.py).

Covers the complete journey gaps beyond test_whatsapp_bot_integration.py:
  1. Anonymous session identity (per-phone token, chat body + job poll headers,
     invalid-token refresh) — parity with anonymous web chat quotas.
  2. Backend Citation-object normalization (dicts -> "Title (url)").
  3. Non-text inbound honesty (voice/media declines, receipts ignored).
  4. Per-phone rate limiting with honest wait copy (no backend burn).
  5. Quota (429) / context-exhausted (409) honest copy.
  6. RESET / HELP local commands.
  7. Indic script language detection persisted to state.
  8. Crisis helpline fail-safe when the backend is unreachable.
  9. Single-send sync delivery (no Twilio double-send; Meta sync pushes).
  10. Outbound retry on first-attempt failure.

The whatsapp_bot/requirements (Flask) are expected; Twilio is optional and
never required here — wa_bot.py degrades to the HMAC fallback without it.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import requests

_REPO_ROOT = Path(__file__).resolve().parents[2]
_WA_BOT_DIR = _REPO_ROOT / "whatsapp_bot"
if str(_WA_BOT_DIR) not in sys.path and _WA_BOT_DIR.exists():
    sys.path.insert(0, str(_WA_BOT_DIR))

pytest.importorskip("flask")

import wa_bot  # noqa: E402


@pytest.fixture(autouse=True)
def setup_test_environment(tmp_path, monkeypatch):
    test_db = tmp_path / "test_wa_journey.db"
    monkeypatch.setenv("WA_DB_PATH", str(test_db))
    monkeypatch.setattr(wa_bot, "WA_DB_PATH", str(test_db))
    monkeypatch.setenv("JWT_SECRET", "test-secret-key-999")
    monkeypatch.setattr(wa_bot, "JWT_SECRET", "test-secret-key-999")
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", "test_twilio_auth_token_xyz")
    monkeypatch.setattr(wa_bot, "TWILIO_AUTH_TOKEN", "test_twilio_auth_token_xyz")
    monkeypatch.setenv("META_APP_SECRET", "test_meta_app_secret_abc123")
    monkeypatch.setattr(wa_bot, "META_APP_SECRET", "test_meta_app_secret_abc123")
    monkeypatch.setenv("WA_ASYNC_ACK", "false")
    wa_bot._init_db()
    wa_bot.reset_rate_limits()
    yield


@pytest.fixture
def client():
    wa_bot.app.config["TESTING"] = True
    with wa_bot.app.test_client() as c:
        yield c


def _ok_response(payload: dict, status: int = 200) -> MagicMock:
    m = MagicMock()
    m.status_code = status
    m.json.return_value = payload
    m.text = json.dumps(payload)
    m.raise_for_status.return_value = None
    return m


def _http_error(status: int, body: str) -> requests.HTTPError:
    resp = requests.Response()
    resp.status_code = status
    resp._content = body.encode("utf-8")
    err = requests.HTTPError(f"HTTP {status}")
    err.response = resp
    return err


def _meta_payload(message: dict, phone_number_id: str = "123456789") -> dict:
    return {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "metadata": {"phone_number_id": phone_number_id},
                            "messages": [message],
                        }
                    }
                ]
            }
        ]
    }


# ---------------------------------------------------------------------------
# 1. Anonymous session identity
# ---------------------------------------------------------------------------
def test_call_chat_sends_anon_token_without_jwt(monkeypatch):
    """chat POST carries session_id=<anon token> and no Authorization header."""
    monkeypatch.setattr(wa_bot, "ensure_anon_token", lambda phone: "pay.sig")
    seen: dict = {}

    def _fake_post(url, **kwargs):
        seen["url"] = url
        seen["headers"] = kwargs.get("headers")
        seen["body"] = json.loads(kwargs.get("data") or "{}")
        return _ok_response({"response": "Peace.", "citations": [], "meditation_step": 0})

    monkeypatch.setattr(wa_bot.requests, "post", _fake_post)
    out = wa_bot.call_chat("+919876543210", "What is joy?", "pay.sig", "en")
    assert out["response"] == "Peace."
    assert seen["url"].endswith("/api/chat")
    assert seen["body"]["session_id"] == "pay.sig"
    assert "Authorization" not in (seen["headers"] or {})


def test_call_chat_refreshes_invalid_token_once(monkeypatch):
    """A rotated server secret triggers one re-issue + retry with fresh token."""
    calls: list = []

    def _fake_post(url, **kwargs):
        calls.append(url)
        if url.endswith("/api/auth/anon-session"):
            return _ok_response({"token": "new.sig", "session_id": "anon:new"})
        body = json.loads(kwargs.get("data") or "{}")
        if body.get("session_id") == "stale.sig":
            m = MagicMock()
            m.status_code = 400
            m.text = "Invalid anonymous session token"
            return m
        return _ok_response({"response": "Peace.", "citations": [], "meditation_step": 0})

    monkeypatch.setattr(wa_bot.requests, "post", _fake_post)
    out = wa_bot.call_chat("+919876543210", "Guide me", "stale.sig", "en")
    assert out["response"] == "Peace."
    assert wa_bot.get_stored_anon_token("+919876543210") == "new.sig"
    assert sum(u.endswith("/api/chat") for u in calls) == 2


def test_poll_job_sends_x_session_id(monkeypatch):
    """Job poll authenticates via X-Session-Id (backend job ownership)."""
    seen: dict = {}

    def _fake_get(url, **kwargs):
        seen["headers"] = kwargs.get("headers")
        return _ok_response(
            {
                "status": "completed",
                "result": {"response": "Peace.", "citations": [], "meditation_step": 0},
            }
        )

    monkeypatch.setattr(wa_bot.requests, "get", _fake_get)
    answer = wa_bot.poll_job_until_complete("+919876543210", "job-1", "pay.sig")
    assert "Peace." in answer
    assert seen["headers"]["X-Session-Id"] == "pay.sig"
    assert "Authorization" not in seen["headers"]


# ---------------------------------------------------------------------------
# 2. Citation normalization
# ---------------------------------------------------------------------------
def test_citation_dicts_render_as_title_url():
    cites = [
        {"url": "https://youtube.com/watch?v=111", "title": "Krishnaji on Fear"},
        "https://example.com/plain",
        {"title": "No URL here"},
        {"url": "https://example.com/a"},
        {"url": "https://example.com/b"},
    ]
    out = wa_bot.with_citations("Peace.", cites)
    assert "Krishnaji on Fear (https://youtube.com/watch?v=111)" in out
    assert "https://example.com/plain" in out
    assert "No URL here" not in out
    # capped at 3 sources
    assert out.count("• ") == 3
    assert "https://example.com/b" not in out


def test_process_chat_turn_forwards_dict_citations(monkeypatch):
    monkeypatch.setattr(wa_bot, "ensure_anon_token", lambda phone: "pay.sig")
    monkeypatch.setattr(
        wa_bot,
        "call_chat",
        lambda *a, **k: {
            "response": "Peace.",
            "citations": [{"url": "https://youtube.com/watch?v=111", "title": "Talk"}],
            "meditation_step": 0,
        },
    )
    with patch.object(wa_bot, "push_twilio_message") as mock_push:
        answer = wa_bot.process_chat_turn("twilio", "+919876543210", "What is joy?")
    assert "Talk (https://youtube.com/watch?v=111)" in answer
    assert mock_push.called


# ---------------------------------------------------------------------------
# 3. Non-text inbound honesty
# ---------------------------------------------------------------------------
def test_meta_audio_gets_voice_decline(client, monkeypatch):
    monkeypatch.setattr(wa_bot, "validate_meta_signature", lambda req: True)
    with (
        patch.object(wa_bot, "call_chat") as mock_chat,
        patch.object(wa_bot, "push_meta_message", return_value=True) as mock_push,
    ):
        resp = client.post(
            "/whatsapp/meta",
            json=_meta_payload({"from": "919876543210", "type": "audio", "audio": {"id": "x"}}),
        )
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "declined_media"
    assert not mock_chat.called
    assert "voice notes" in mock_push.call_args[0][2]


def test_meta_image_gets_media_decline(client, monkeypatch):
    monkeypatch.setattr(wa_bot, "validate_meta_signature", lambda req: True)
    with (
        patch.object(wa_bot, "call_chat") as mock_chat,
        patch.object(wa_bot, "push_meta_message", return_value=True) as mock_push,
    ):
        resp = client.post(
            "/whatsapp/meta",
            json=_meta_payload({"from": "919876543210", "type": "image", "image": {"id": "x"}}),
        )
    assert resp.status_code == 200
    assert not mock_chat.called
    assert "type your question as text" in mock_push.call_args[0][2]


def test_meta_button_reply_is_answered(client, monkeypatch):
    monkeypatch.setattr(wa_bot, "validate_meta_signature", lambda req: True)
    monkeypatch.setenv("WA_ASYNC_ACK", "true")
    payload = _meta_payload(
        {
            "from": "919876543210",
            "type": "interactive",
            "interactive": {"button_reply": {"id": "b1", "title": "Tell me more"}},
        }
    )
    with patch.object(wa_bot, "process_chat_turn", return_value="Peace.") as mock_turn:
        resp = client.post("/whatsapp/meta", json=payload)
    assert resp.get_json()["status"] == "received"
    assert mock_turn.call_args[0][2] == "Tell me more"


def test_meta_status_receipts_are_ignored(client, monkeypatch):
    monkeypatch.setattr(wa_bot, "validate_meta_signature", lambda req: True)
    payload = {"entry": [{"changes": [{"value": {"statuses": [{"id": "wamid.x"}]}}]}]}
    with (
        patch.object(wa_bot, "call_chat") as mock_chat,
        patch.object(wa_bot, "push_meta_message") as mock_push,
    ):
        resp = client.post("/whatsapp/meta", json=payload)
    assert resp.get_json()["status"] == "no_message"
    assert not mock_chat.called
    assert not mock_push.called


def test_twilio_voice_note_gets_voice_decline(client, monkeypatch):
    monkeypatch.setattr(wa_bot, "validate_twilio_signature", lambda req: True)
    with patch.object(wa_bot, "process_chat_turn") as mock_turn:
        resp = client.post(
            "/whatsapp/twilio",
            data={
                "From": "whatsapp:+919876543210",
                "Body": "",
                "NumMedia": "1",
                "MediaContentType0": "audio/ogg",
            },
        )
    assert resp.status_code == 200
    assert "voice notes" in resp.data.decode("utf-8")
    assert not mock_turn.called


def test_twilio_status_callback_acknowledged_quietly(client, monkeypatch):
    monkeypatch.setattr(wa_bot, "validate_twilio_signature", lambda req: True)
    with patch.object(wa_bot, "process_chat_turn") as mock_turn:
        resp = client.post(
            "/whatsapp/twilio",
            data={"From": "whatsapp:+919876543210", "Body": "", "NumMedia": "0"},
        )
    assert "<Response></Response>" in resp.data.decode("utf-8")
    assert not mock_turn.called


# ---------------------------------------------------------------------------
# 4. Per-phone rate limiting
# ---------------------------------------------------------------------------
def test_twilio_rate_limit_returns_wait_copy_without_backend(client, monkeypatch):
    monkeypatch.setattr(wa_bot, "validate_twilio_signature", lambda req: True)
    monkeypatch.setenv("WA_RATE_LIMIT_COUNT", "2")
    with patch.object(wa_bot, "process_chat_turn", return_value="Peace.") as mock_turn:
        for i in range(2):
            client.post(
                "/whatsapp/twilio",
                data={"From": "whatsapp:+919876543210", "Body": f"Question {i}"},
            )
        resp = client.post(
            "/whatsapp/twilio",
            data={"From": "whatsapp:+919876543210", "Body": "Question 3"},
        )
    assert resp.status_code == 200
    assert "wait a moment" in resp.data.decode("utf-8")
    # sync mode (WA_ASYNC_ACK=false in fixture): process serves the first two
    assert mock_turn.call_count == 2


def test_rate_limit_is_per_phone(client, monkeypatch):
    monkeypatch.setattr(wa_bot, "validate_twilio_signature", lambda req: True)
    monkeypatch.setenv("WA_RATE_LIMIT_COUNT", "1")
    with patch.object(wa_bot, "process_chat_turn", return_value="Peace."):
        client.post(
            "/whatsapp/twilio",
            data={"From": "whatsapp:+911111111111", "Body": "One"},
        )
        resp = client.post(
            "/whatsapp/twilio",
            data={"From": "whatsapp:+912222222222", "Body": "One"},
        )
    assert "Peace." in resp.data.decode("utf-8")


def test_twilio_crisis_message_bypasses_rate_limit(client, monkeypatch):
    """RP-C1: a crisis-flagged message must reach the backend with a full bucket."""
    monkeypatch.setattr(wa_bot, "validate_twilio_signature", lambda req: True)
    monkeypatch.setenv("WA_RATE_LIMIT_COUNT", "1")
    with patch.object(wa_bot, "process_chat_turn", return_value="Peace.") as mock_turn:
        client.post(
            "/whatsapp/twilio",
            data={"From": "whatsapp:+919876543210", "Body": "What is joy?"},
        )
        resp = client.post(
            "/whatsapp/twilio",
            data={"From": "whatsapp:+919876543210", "Body": "I want to end my life"},
        )
    assert mock_turn.call_count == 2
    body = resp.data.decode("utf-8")
    assert "Peace." in body
    assert "wait a moment" not in body


def test_meta_crisis_message_bypasses_rate_limit(client, monkeypatch):
    """RP-C1: same exemption on the Meta route."""
    monkeypatch.setattr(wa_bot, "validate_meta_signature", lambda req: True)
    monkeypatch.setenv("WA_RATE_LIMIT_COUNT", "1")
    with patch.object(wa_bot, "process_chat_turn", return_value="Peace.") as mock_turn:
        client.post(
            "/whatsapp/meta",
            json=_meta_payload({"from": "919876543210", "text": {"body": "What is joy?"}}),
        )
        resp = client.post(
            "/whatsapp/meta",
            json=_meta_payload({"from": "919876543210", "text": {"body": "I want to end my life"}}),
        )
    assert mock_turn.call_count == 2
    assert resp.get_json()["status"] == "processed"


@pytest.mark.parametrize(
    "text",
    [
        "I want to end my life",
        "I want to kill myself",
        "मला जीव देणे वाटते",  # Marathi idiom (review P2-2)
        "ആത്മഹത്യ",  # Malayalam
        "ಆತ್ಮಹತ್ಯೆ",  # Kannada
    ],
)
def test_likely_crisis_covers_english_and_indic_idioms(text):
    assert wa_bot.likely_crisis(text)


def test_likely_crisis_leaves_benign_text_alone():
    assert not wa_bot.likely_crisis("I want to learn meditation")
    assert not wa_bot.likely_crisis("")


def test_crisis_quota_429_still_shows_helplines(monkeypatch):
    """RP-C1: a backend 429 quota reply to a crisis message carries helplines."""
    monkeypatch.setattr(wa_bot, "ensure_anon_token", lambda phone: "pay.sig")

    def _raise(*a, **k):
        raise _http_error(429, '{"error": "Anonymous quota exceeded", "quota_exceeded": true}')

    monkeypatch.setattr(wa_bot, "call_chat", _raise)
    with patch.object(wa_bot, "push_twilio_message") as mock_push:
        wa_bot.process_chat_turn("twilio", "+919876543210", "I want to end my life")
    pushed = mock_push.call_args[0][1]
    assert "today's free question limit" in pushed
    assert "14416" in pushed


def test_no_withdrawn_kiran_number_in_bot_copy():
    """RP-C2/QBUG-1: KIRAN 1800-599-0019 is withdrawn; bot copy must match the yaml."""
    import yaml

    readme = (_REPO_ROOT / "whatsapp_bot" / "README.md").read_text(encoding="utf-8")
    assert "1800-599-0019" not in wa_bot._HELPLINE_FOOTER
    assert "Kiran" not in wa_bot._HELPLINE_FOOTER
    # The number may appear in README only inside its own withdrawal note.
    leftovers = [ln for ln in readme.splitlines() if "1800-599-0019" in ln]
    assert leftovers and all("withdrawn" in ln.lower() for ln in leftovers), leftovers
    # Load-bearing: every footer number must be a contact in the yaml registry.
    registry = yaml.safe_load(
        (_REPO_ROOT / "config" / "helplines.yaml").read_text(encoding="utf-8")
    )
    contact_numbers = set()
    for entry in registry.get("crisis_helplines", []):
        contact_numbers.update(re.findall(r"\d+", entry.get("contact", "")))
    # Footer numbers must each be a contact in the yaml registry. The token
    # regex only catches longer numbers (14416/112 are too short for it), so
    # extract short ones explicitly with a digit-only pass on each ;-separated
    # field, then assert they are all registered.
    for tok in set(re.findall(r"\+?[\d][\d\s\-/()]{5,}[\d]", wa_bot._HELPLINE_FOOTER)):
        digits = re.sub(r"\D", "", tok)
        assert digits in contact_numbers, f"footer number {tok!r} is not a registry contact"
    # Short standalone numbers that the token regex misses.
    short_numbers = set(re.findall(r"\b(\d{3,5})\b", wa_bot._HELPLINE_FOOTER))
    for num in short_numbers:
        assert num in contact_numbers, f"short footer number {num!r} is not a registry contact"
    assert {"14416", "112"} <= contact_numbers


# ---------------------------------------------------------------------------
# 5. Quota / context-exhausted honesty
# ---------------------------------------------------------------------------
def test_quota_429_yields_daily_limit_copy(monkeypatch):
    monkeypatch.setattr(wa_bot, "ensure_anon_token", lambda phone: "pay.sig")

    def _raise(*a, **k):
        raise _http_error(429, '{"error": "Anonymous quota exceeded", "quota_exceeded": true}')

    monkeypatch.setattr(wa_bot, "call_chat", _raise)
    with patch.object(wa_bot, "push_twilio_message") as mock_push:
        wa_bot.process_chat_turn("twilio", "+919876543210", "What is joy?")
    assert "today's free question limit" in mock_push.call_args[0][1]


def test_context_409_suggests_reset(monkeypatch):
    monkeypatch.setattr(wa_bot, "ensure_anon_token", lambda phone: "pay.sig")

    def _raise(*a, **k):
        raise _http_error(409, '{"error_code": "CONTEXT_EXHAUSTED"}')

    monkeypatch.setattr(wa_bot, "call_chat", _raise)
    with patch.object(wa_bot, "push_twilio_message") as mock_push:
        wa_bot.process_chat_turn("twilio", "+919876543210", "More?")
    assert "RESET" in mock_push.call_args[0][1]


# ---------------------------------------------------------------------------
# 6. RESET / HELP commands
# ---------------------------------------------------------------------------
def test_reset_clears_history(client, monkeypatch):
    monkeypatch.setattr(wa_bot, "validate_twilio_signature", lambda req: True)
    wa_bot.append_message("+919876543210", "user", "earlier question")
    with patch.object(wa_bot, "call_chat") as mock_chat:
        resp = client.post(
            "/whatsapp/twilio",
            data={"From": "whatsapp:+919876543210", "Body": "RESET"},
        )
    assert "Fresh page" in resp.data.decode("utf-8")
    assert not mock_chat.called
    remaining = wa_bot.history_for("+919876543210")
    assert all("earlier question" not in m["content"] for m in remaining)
    assert remaining[-1]["role"] == "assistant"


def test_help_lists_capabilities_without_backend(client, monkeypatch):
    monkeypatch.setattr(wa_bot, "validate_twilio_signature", lambda req: True)
    with patch.object(wa_bot, "call_chat") as mock_chat:
        resp = client.post(
            "/whatsapp/twilio",
            data={"From": "whatsapp:+919876543210", "Body": "help"},
        )
    assert "voice notes" in resp.data.decode("utf-8")
    assert not mock_chat.called


# ---------------------------------------------------------------------------
# 7. Language detection
# ---------------------------------------------------------------------------
def test_hindi_turn_sets_language_hindi(monkeypatch):
    seen: dict = {}
    monkeypatch.setattr(wa_bot, "ensure_anon_token", lambda phone: "pay.sig")

    def _fake_chat(phone, msg, token, lang):
        seen["language"] = lang
        return {"response": "शांति।", "citations": [], "meditation_step": 0}

    monkeypatch.setattr(wa_bot, "call_chat", _fake_chat)
    with patch.object(wa_bot, "push_twilio_message"):
        wa_bot.process_chat_turn("twilio", "+919876543210", "दुःख क्या है और इससे कैसे निकलें")
    assert seen["language"] == "hi"
    assert wa_bot.state_for("+919876543210")["language"] == "hi"


def test_telugu_turn_sets_language_telugu(monkeypatch):
    seen: dict = {}
    monkeypatch.setattr(wa_bot, "ensure_anon_token", lambda phone: "pay.sig")

    def _fake_chat(phone, msg, token, lang):
        seen["language"] = lang
        return {"response": "శాంతి.", "citations": [], "meditation_step": 0}

    monkeypatch.setattr(wa_bot, "call_chat", _fake_chat)
    with patch.object(wa_bot, "push_twilio_message"):
        wa_bot.process_chat_turn("twilio", "+919876543210", "బాధ అంటే ఏమిటి నాకు చెప్పండి")
    assert seen["language"] == "te"


# ---------------------------------------------------------------------------
# 8. Crisis fail-safe on backend failure
# ---------------------------------------------------------------------------
def test_crisis_message_backend_down_includes_helplines(monkeypatch):
    # RP-C2/QBUG-1: footer follows config/helplines.yaml — KIRAN withdrawn.
    monkeypatch.setattr(wa_bot, "ensure_anon_token", lambda phone: "pay.sig")

    def _raise(*a, **k):
        raise requests.ConnectionError("backend down")

    monkeypatch.setattr(wa_bot, "call_chat", _raise)
    with patch.object(wa_bot, "push_twilio_message") as mock_push:
        wa_bot.process_chat_turn("twilio", "+919876543210", "I want to kill myself")
    body = mock_push.call_args[0][1]
    assert "14416" in body
    assert "1800-599-0019" not in body
    assert "Kiran" not in body
    assert "112" in body


def test_benign_message_backend_down_has_no_helplines(monkeypatch):
    monkeypatch.setattr(wa_bot, "ensure_anon_token", lambda phone: "pay.sig")

    def _raise(*a, **k):
        raise requests.ConnectionError("backend down")

    monkeypatch.setattr(wa_bot, "call_chat", _raise)
    with patch.object(wa_bot, "push_twilio_message") as mock_push:
        wa_bot.process_chat_turn("twilio", "+919876543210", "What is the Beautiful State?")
    body = mock_push.call_args[0][1]
    assert "14416" not in body


# ---------------------------------------------------------------------------
# 9. Single-send sync delivery
# ---------------------------------------------------------------------------
def test_sync_twilio_does_not_double_send(client, monkeypatch):
    monkeypatch.setattr(wa_bot, "validate_twilio_signature", lambda req: True)
    monkeypatch.setattr(wa_bot, "ensure_anon_token", lambda phone: "pay.sig")
    monkeypatch.setattr(
        wa_bot,
        "call_chat",
        lambda *a, **k: {"response": "Peace.", "citations": [], "meditation_step": 0},
    )
    with patch.object(wa_bot, "push_twilio_message") as mock_push:
        resp = client.post(
            "/whatsapp/twilio",
            data={"From": "whatsapp:+919876543210", "Body": "Guide me"},
        )
    assert "Peace." in resp.data.decode("utf-8")
    assert not mock_push.called


def test_sync_meta_pushes_outbound(client, monkeypatch):
    monkeypatch.setattr(wa_bot, "validate_meta_signature", lambda req: True)
    monkeypatch.setattr(wa_bot, "ensure_anon_token", lambda phone: "pay.sig")
    monkeypatch.setattr(
        wa_bot,
        "call_chat",
        lambda *a, **k: {"response": "Peace.", "citations": [], "meditation_step": 0},
    )
    with patch.object(wa_bot, "push_meta_message", return_value=True) as mock_push:
        resp = client.post(
            "/whatsapp/meta",
            json=_meta_payload({"from": "919876543210", "text": {"body": "Guide me"}}),
        )
    assert resp.get_json()["status"] == "processed"
    assert "Peace." in resp.get_json()["response"]
    assert "Peace." in mock_push.call_args[0][2]


# ---------------------------------------------------------------------------
# 10. Outbound retry
# ---------------------------------------------------------------------------
def test_outbound_retry_on_first_failure(monkeypatch):
    monkeypatch.setattr(wa_bot, "ensure_anon_token", lambda phone: "pay.sig")
    monkeypatch.setattr(
        wa_bot,
        "call_chat",
        lambda *a, **k: {"response": "Peace.", "citations": [], "meditation_step": 0},
    )
    with patch.object(wa_bot, "push_twilio_message", side_effect=[False, True]) as mock_push:
        answer = wa_bot.process_chat_turn("twilio", "+919876543210", "Guide me")
    assert answer == "Peace."
    assert mock_push.call_count == 2
