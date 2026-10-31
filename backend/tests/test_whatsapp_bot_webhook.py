"""WhatsApp webhook receiver: dedupe, batching, delivery callbacks, 24h window.

Covers the receiver contract from the 2026-10-30 request: signed webhook,
deduplicated inbound messages, outbound attempts and delivery callbacks stored,
replies only inside the 24-hour window (or via an approved template), and no
link between a phone number and a signed-in user's memory.
"""

from __future__ import annotations

import sqlite3
import stat
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_WA_BOT_DIR = Path(__file__).resolve().parents[2] / "whatsapp_bot"
if str(_WA_BOT_DIR) not in sys.path and _WA_BOT_DIR.exists():
    sys.path.insert(0, str(_WA_BOT_DIR))

pytest.importorskip("flask")
pytest.importorskip("twilio")

try:
    import wa_bot
except ImportError:  # pragma: no cover
    wa_bot = None

PHONE = "919876543210"


@pytest.fixture(autouse=True)
def env(tmp_path, monkeypatch):
    if wa_bot is None:
        pytest.skip("whatsapp_bot module not present")
    db = tmp_path / "wa.db"
    monkeypatch.setenv("WA_DB_PATH", str(db))
    monkeypatch.setattr(wa_bot, "WA_DB_PATH", str(db))
    monkeypatch.setenv("WA_ASYNC_ACK", "false")
    monkeypatch.setenv("META_ACCESS_TOKEN", "tok")
    monkeypatch.setenv("META_PHONE_NUMBER_ID", "123456789")
    monkeypatch.setenv("META_TEMPLATE_NAME", "")
    monkeypatch.setattr(wa_bot, "validate_meta_signature", lambda req: True)
    monkeypatch.setattr(wa_bot, "ensure_anon_token", lambda phone: "pay.sig")
    monkeypatch.setattr(
        wa_bot,
        "call_chat",
        lambda *a, **k: {"response": "Peace.", "citations": [], "meditation_step": 0},
    )
    wa_bot._init_db()
    wa_bot.reset_rate_limits()
    wa_bot.update_state(
        "+" + PHONE, meditation_step=0, last_serene_at=None, language="en", consented=1, opted_out=0
    )
    wa_bot.update_state(
        PHONE, meditation_step=0, last_serene_at=None, language="en", consented=1, opted_out=0
    )
    yield


@pytest.fixture
def client():
    wa_bot.app.config["TESTING"] = True
    with wa_bot.app.test_client() as c:
        yield c


def _msg(mid: str, body: str = "Guide me") -> dict:
    return {"id": mid, "from": PHONE, "type": "text", "text": {"body": body}}


def _payload(messages=None, statuses=None) -> dict:
    value: dict = {"metadata": {"phone_number_id": "123456789"}}
    if messages:
        value["messages"] = messages
    if statuses:
        value["statuses"] = statuses
    return {"entry": [{"changes": [{"value": value}]}]}


def _rows(table: str) -> list[sqlite3.Row]:
    with wa_bot._db() as conn:
        return conn.execute(f"SELECT * FROM {table}").fetchall()  # noqa: S608


def _ok_post(wamid: str = "wamid.OUT1"):
    resp = MagicMock()
    resp.raise_for_status.return_value = None
    resp.json.return_value = {"messages": [{"id": wamid}]}
    return resp


def test_duplicate_wamid_is_answered_once(client):
    with patch.object(wa_bot, "push_meta_message", return_value=True) as push:
        first = client.post("/whatsapp/meta", json=_payload([_msg("wamid.A")]))
        second = client.post("/whatsapp/meta", json=_payload([_msg("wamid.A")]))
    assert first.get_json()["status"] == "processed"
    assert second.get_json()["status"] == "duplicate"
    assert push.call_count == 1
    assert len(_rows("wa_inbound")) == 1


def test_batched_messages_are_all_handled(client):
    with patch.object(wa_bot, "push_meta_message", return_value=True) as push:
        resp = client.post(
            "/whatsapp/meta", json=_payload([_msg("wamid.A", "One"), _msg("wamid.B", "Two")])
        )
    assert resp.status_code == 200
    assert push.call_count == 2
    assert {r["provider_msg_id"] for r in _rows("wa_inbound")} == {"wamid.A", "wamid.B"}


def test_outbound_accept_is_recorded_but_not_delivery(client):
    with patch("requests.post", return_value=_ok_post()):
        assert wa_bot.push_meta_message("123456789", PHONE, "Peace") is True
    row = _rows("wa_outbound")[0]
    assert (row["provider_msg_id"], row["status"], row["mode"]) == (
        "wamid.OUT1",
        "accepted",
        "text",
    )


def test_status_callbacks_advance_and_never_regress(client):
    wa_bot.record_outbound("meta", PHONE, "text", "accepted", provider_msg_id="wamid.OUT1")

    def post(status, ts, errors=None):
        st = {"id": "wamid.OUT1", "status": status, "timestamp": str(ts), "recipient_id": PHONE}
        if errors:
            st["errors"] = errors
        return client.post("/whatsapp/meta", json=_payload(statuses=[st]))

    assert post("sent", 1).get_json()["status"] == "no_message"
    post("read", 3)
    post("delivered", 2)  # late callback must not move read back to delivered
    assert _rows("wa_outbound")[0]["status"] == "read"
    post("delivered", 2)  # duplicate callback is ignored
    assert len(_rows("wa_status_events")) == 3
    post("failed", 4, [{"code": 131047, "title": "Re-engagement message"}])
    row = _rows("wa_outbound")[0]
    assert (row["status"], row["error"]) == ("failed", "131047")


def test_closed_window_blocks_free_form(client):
    wa_bot.open_window(PHONE, at=int(time.time()) - 25 * 3600)
    with patch.object(wa_bot, "push_meta_message") as push:
        assert wa_bot._deliver_outbound("meta", PHONE, "late reply", {}) is False
    push.assert_not_called()
    row = _rows("wa_outbound")[0]
    assert (row["mode"], row["status"], row["error"]) == (
        "blocked_window",
        "failed",
        "window_closed",
    )


def test_closed_window_uses_approved_template_only(client, monkeypatch):
    monkeypatch.setenv("META_TEMPLATE_NAME", "reopen_chat")
    wa_bot.open_window(PHONE, at=int(time.time()) - 25 * 3600)
    with patch("requests.post", return_value=_ok_post("wamid.T1")) as post:
        assert wa_bot._deliver_outbound("meta", PHONE, "free text", {}) is True
    sent = post.call_args.kwargs["json"]
    assert sent["type"] == "template" and sent["template"]["name"] == "reopen_chat"
    assert "text" not in sent
    assert _rows("wa_outbound")[0]["mode"] == "template"


def test_inbound_message_reopens_window(client):
    wa_bot.open_window(PHONE, at=int(time.time()) - 25 * 3600)
    assert wa_bot.window_open(PHONE) is False
    with patch.object(wa_bot, "push_meta_message", return_value=True) as push:
        client.post("/whatsapp/meta", json=_payload([_msg("wamid.NEW")]))
    assert push.call_count == 1


def test_twilio_status_callback_is_stored_not_answered(client, monkeypatch):
    monkeypatch.setattr(wa_bot, "validate_twilio_signature", lambda req: True)
    wa_bot.record_outbound("twilio", PHONE, "text", "accepted", provider_msg_id="SM1")
    with patch.object(wa_bot, "push_twilio_message") as push:
        resp = client.post(
            "/whatsapp/twilio",
            data={"MessageSid": "SM1", "MessageStatus": "delivered", "From": "whatsapp:+1555"},
        )
    assert resp.status_code == 200
    push.assert_not_called()
    assert _rows("wa_outbound")[0]["status"] == "delivered"


def test_twilio_duplicate_message_sid_answered_once(client, monkeypatch):
    monkeypatch.setattr(wa_bot, "validate_twilio_signature", lambda req: True)
    form = {"MessageSid": "SMIN1", "From": f"whatsapp:+{PHONE}", "Body": "Guide me"}
    with patch.object(wa_bot, "push_twilio_message", return_value=True):
        first = client.post("/whatsapp/twilio", data=form)
        second = client.post("/whatsapp/twilio", data=form)
    assert "Peace." in first.get_data(as_text=True)
    assert "Peace." not in second.get_data(as_text=True)


def test_phone_is_never_linked_to_a_user_account():
    """Only an anonymous per-phone token exists; no user/account column anywhere."""
    with wa_bot._db() as conn:
        cols = {
            f"{t['name']}.{c['name']}"
            for t in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
            for c in conn.execute(f"PRAGMA table_info({t['name']})")  # noqa: S608
        }
    assert not [c for c in cols if any(w in c for w in ("user", "memory", "account", "receipt"))]


def test_database_file_is_owner_only():
    mode = stat.S_IMODE(Path(wa_bot.WA_DB_PATH).stat().st_mode)
    assert mode == 0o600


def test_safety_notices_are_appended_to_the_whatsapp_reply():
    """Platform copy (support line, boundaries) left the answer body; WhatsApp must add it back."""
    text = wa_bot.with_safety_notices('"A clip."', ["Boundary line.", " ", "Support line."])
    assert text.endswith("Boundary line.\n\nSupport line.")
    assert wa_bot.with_safety_notices("only quote", None) == "only quote"
    assert wa_bot.with_safety_notices("only quote", []) == "only quote"


def _seed_delivery_rows(phone: str, at: int) -> None:
    wa_bot.claim_inbound("meta", f"in-{at}", phone, "text")
    wa_bot.open_window(phone, at=at)
    wa_bot.record_outbound("meta", phone, "text", "accepted", provider_msg_id=f"out-{at}")
    wa_bot.record_status_event("meta", f"out-{at}", "delivered", event_ts=at)


def test_old_delivery_rows_age_out_of_every_phone_table():
    old = int(time.time()) - wa_bot.WA_RECORD_RETENTION_S - 60
    _seed_delivery_rows(PHONE, old)
    with wa_bot.closing(wa_bot._db()) as conn:
        conn.execute("UPDATE wa_inbound SET received_at=?", (old,))
        conn.execute("UPDATE wa_outbound SET created_at=?", (old,))
        conn.execute("UPDATE wa_status_events SET received_at=?", (old,))
    wa_bot._prune_db()
    for table in ("wa_inbound", "wa_window", "wa_outbound", "wa_status_events"):
        assert _rows(table) == [], table


def test_recent_delivery_rows_survive_the_prune():
    _seed_delivery_rows(PHONE, int(time.time()))
    wa_bot._prune_db()
    for table in ("wa_inbound", "wa_window", "wa_outbound", "wa_status_events"):
        assert len(_rows(table)) == 1, table


def test_reset_and_stop_erase_send_attempts_and_receipts():
    for erase in (
        lambda: wa_bot.clear_conversation(PHONE),
        lambda: wa_bot._handle_command(PHONE, "STOP"),
    ):
        _seed_delivery_rows(PHONE, int(time.time()))
        erase()
        assert _rows("wa_outbound") == []
        assert _rows("wa_status_events") == []


def test_retention_floor_keeps_the_service_window_open():
    assert wa_bot.WA_RECORD_RETENTION_S >= 25 * 3600


def test_failed_turn_releases_the_claim_so_the_retry_is_processed(client):
    """Claim-before-process made a crashed turn look like a duplicate on retry."""
    client.application.config["PROPAGATE_EXCEPTIONS"] = False
    with patch.object(wa_bot, "_handle_meta_message", side_effect=RuntimeError("boom")):
        failed = client.post("/whatsapp/meta", json=_payload([_msg("wamid.R")]))
    assert failed.status_code == 500
    assert _rows("wa_inbound") == []
    with patch.object(wa_bot, "push_meta_message", return_value=True) as push:
        retry = client.post("/whatsapp/meta", json=_payload([_msg("wamid.R")]))
    assert retry.get_json()["status"] == "processed"
    assert push.call_count == 1
