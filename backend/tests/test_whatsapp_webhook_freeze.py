"""Regression checks for the intentionally disabled legacy WhatsApp broker."""

from __future__ import annotations

from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "whatsapp_webhook.py"


def test_legacy_whatsapp_broker_is_fail_closed_by_default() -> None:
    source = _SCRIPT.read_text(encoding="utf-8")

    assert (
        "WHATSAPP_WEBHOOK_ENABLED = os.getenv('WHATSAPP_WEBHOOK_ENABLED', '').lower() == 'true'"
        in source
    )
    assert "@app.before_request" in source
    assert "def reject_when_broker_is_disabled():" in source
    assert "if not WHATSAPP_WEBHOOK_ENABLED:\n        abort(404)" in source


def test_legacy_whatsapp_broker_refuses_standalone_start_when_disabled() -> None:
    source = _SCRIPT.read_text(encoding="utf-8")

    assert "if __name__ == '__main__':\n    if not WHATSAPP_WEBHOOK_ENABLED:" in source
    assert "raise SystemExit(1)" in source


def test_signature_validation_never_bypasses_missing_provider_secrets() -> None:
    source = _SCRIPT.read_text(encoding="utf-8")
    assert "TWILIO_AUTH_TOKEN is not configured; rejecting request." in source
    assert "META_APP_SECRET is not configured; rejecting request." in source
    assert "bypassing Twilio signature verification" not in source
    assert "bypassing Meta signature verification" not in source
