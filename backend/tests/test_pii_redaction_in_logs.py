"""P1-SEC-3: PII auto-redaction in log output.

Verifies that the JSONFormatter attached to the app logger scrubs PII from the
message field that actually lands in the log (not just the raw redact()
function), and that the PIIScrubber filter mutates record.msg for handlers
that bypass the JSON formatter.
"""

import io
import json
import logging

from app.main import JSONFormatter, PIIScrubber


def _formatted_message(msg: str) -> str:
    """Format a log record exactly as production stdout logs are formatted."""
    record = logging.LogRecord(
        name="test.pii",
        level=logging.INFO,
        pathname=__file__,
        lineno=0,
        msg=msg,
        args=None,
        exc_info=None,
    )
    formatter = JSONFormatter(datefmt="%Y-%m-%dT%H:%M:%S%z")
    return json.loads(formatter.format(record))["message"]


def test_email_redacted():
    out = _formatted_message("user email is user@example.com")
    assert "[REDACTED_EMAIL]" in out
    assert "user@example.com" not in out


def test_phone_redacted():
    out = _formatted_message("call me at +1 (555) 123-4567")
    assert "[REDACTED_PHONE]" in out
    assert "123-4567" not in out


def test_ip_redacted():
    out = _formatted_message("blocked attempt from 192.168.1.10")
    assert "[REDACTED_IP]" in out
    assert "192.168.1.10" not in out


def test_url_query_params_redacted():
    out = _formatted_message("debug: https://example.com/?token=abc123&email=x@y.com")
    assert "[REDACTED_QUERY_PARAM]" in out
    assert "abc123" not in out
    assert "x@y.com" not in out


def test_scrubber_filter_mutates_record_msg():
    record = logging.LogRecord(
        name="test.pii.filter",
        level=logging.INFO,
        pathname=__file__,
        lineno=0,
        msg="contact user@example.com at 192.168.1.10",
        args=None,
        exc_info=None,
    )
    assert PIIScrubber().filter(record) is True
    assert record.msg == "contact [REDACTED_EMAIL] at [REDACTED_IP]"
    assert record.args == ()


def test_stream_output_redacted():
    """End-to-end: a log record flowing through the real JSONFormatter with the
    PIIScrubber filter attached (the exact wiring used in app.main) must land
    with PII scrubbed in the emitted output."""
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JSONFormatter(datefmt="%Y-%m-%dT%H:%M:%S%z"))
    handler.addFilter(PIIScrubber())
    logger = logging.getLogger("test.pii.stream")
    logger.handlers = [handler]
    logger.setLevel(logging.INFO)
    logger.propagate = False
    logger.info("contact user@example.com at 192.168.1.10")
    emitted = stream.getvalue()
    assert "[REDACTED_EMAIL]" in emitted
    assert "[REDACTED_IP]" in emitted
    assert "user@example.com" not in emitted
    assert "192.168.1.10" not in emitted


def test_non_pii_message_unchanged():
    out = _formatted_message("meditation session completed")
    assert "meditation session completed" == out


if __name__ == "__main__":
    import pytest

    pytest.main([__file__, "-v"])
