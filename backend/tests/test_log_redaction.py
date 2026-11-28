"""Regression guard: connection secrets and raw anonymous ids must never reach logs."""

from app.sanitization import pseudonymize_identity, redact_url_credentials


def test_redis_password_is_masked_but_host_kept():
    masked = redact_url_credentials("redis://:s3cr3t@redis:6379/0")
    assert "s3cr3t" not in masked
    assert masked == "redis://***@redis:6379/0"


def test_url_without_credentials_is_unchanged():
    assert redact_url_credentials("redis://redis:6379/0") == "redis://redis:6379/0"


def test_empty_url_is_empty_string():
    assert redact_url_credentials(None) == ""


def test_pseudonym_hides_raw_anonymous_id_and_is_stable():
    raw = "anon:eyJzaWQiOiJhYmMifQ.signature"
    tag = pseudonymize_identity(raw)
    assert raw not in tag
    assert "eyJzaWQi" not in tag
    assert tag == pseudonymize_identity(raw)
    assert tag.startswith("id-") and len(tag) == len("id-") + 12


def test_build_coalescer_logs_masked_url(monkeypatch):
    from unittest import mock

    from app import coalescer

    fake_logger = mock.Mock()
    monkeypatch.setattr(coalescer, "logger", fake_logger)
    coalescer.build_coalescer("redis://:s3cr3t@localhost:6379/0")
    logged = " ".join(str(part) for call in fake_logger.info.call_args_list for part in call.args)
    assert "s3cr3t" not in logged
    assert "redis://***@localhost:6379/0" in logged


def test_coalescer_failure_message_is_masked(monkeypatch):
    from unittest import mock

    from app import coalescer

    def boom(url, ttl):
        raise ValueError(f"cannot connect to {url}")

    fake_logger = mock.Mock()
    monkeypatch.setattr(coalescer, "logger", fake_logger)
    monkeypatch.setattr(coalescer, "RedisCoalescer", boom)
    coalescer.build_coalescer("redis://:s3cr3t@localhost:6379/0")
    logged = " ".join(
        str(part) for call in fake_logger.warning.call_args_list for part in call.args
    )
    assert "s3cr3t" not in logged
    assert "redis://***@localhost:6379/0" in logged


if __name__ == "__main__":
    test_redis_password_is_masked_but_host_kept()
    test_url_without_credentials_is_unchanged()
    test_empty_url_is_empty_string()
    test_pseudonym_hides_raw_anonymous_id_and_is_stable()
    print("log redaction self-check passed")


def test_pseudonymize_identity_default_is_the_unkeyed_digest(monkeypatch):
    """With LOG_PSEUDONYM_KEY unset the tag is exactly what it was before the key existed."""
    import hashlib

    from app.config import settings

    monkeypatch.setattr(settings, "log_pseudonym_key", "")
    assert pseudonymize_identity("anon-1") == "id-" + hashlib.sha256(b"anon-1").hexdigest()[:12]


def test_pseudonymize_identity_with_key_is_keyed_stable_and_not_the_plain_hash(monkeypatch):
    import hashlib

    from app.config import settings

    plain = "id-" + hashlib.sha256(b"anon-1").hexdigest()[:12]
    monkeypatch.setattr(settings, "log_pseudonym_key", "k1-long-random-value")
    keyed = pseudonymize_identity("anon-1")
    assert keyed == pseudonymize_identity("anon-1")  # stable
    assert keyed != plain  # an attacker hashing candidates without the key cannot match it
    assert "anon-1" not in keyed
    monkeypatch.setattr(settings, "log_pseudonym_key", "a-different-key")
    assert pseudonymize_identity("anon-1") != keyed  # depends on the key
    assert pseudonymize_identity(None) == "none" and pseudonymize_identity("") == "none"
