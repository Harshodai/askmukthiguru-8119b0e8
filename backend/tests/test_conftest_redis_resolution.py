"""The test suite must find a reachable Redis without hand-exported env.

Before this, conftest defaulted to a passwordless `redis://localhost:6379/0`.
Against a password-protected Redis that yields
`AuthenticationError: Authentication required` and `LLMBudgetUnavailable`, which
failed 11 tests for anyone who had not exported REDIS_URL by hand — a local
config problem that reads exactly like a code regression.

The resolver reads the gitignored backend/.env for credentials and rewrites the
host, because that file targets the compose network (`redis:6379`) which does
not resolve on a developer machine, while its credentials do apply to the
published localhost port. No password is ever committed.
"""

import importlib.util
import os
from pathlib import Path

# conftest is not an importable module name from inside the tests package, so
# load it by path. It is already imported by pytest; this is the same file.
_CONFTEST = Path(__file__).resolve().parent / "conftest.py"
_spec = importlib.util.spec_from_file_location("_conftest_under_test", _CONFTEST)
conftest = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(conftest)


def test_exported_url_always_wins(monkeypatch):
    monkeypatch.setenv("REDIS_URL", "redis://:secret@example.invalid:6380/3")
    assert conftest._resolve_test_redis_url() == "redis://:secret@example.invalid:6380/3"


def test_env_file_credentials_are_reused_with_a_local_host(monkeypatch, tmp_path):
    monkeypatch.delenv("REDIS_URL", raising=False)
    env = tmp_path / ".env"
    env.write_text("FOO=1\nREDIS_URL=redis://:p4ss@redis:6379/0\nBAR=2\n", encoding="utf-8")
    monkeypatch.setattr(conftest, "_BACKEND_DIR", str(tmp_path))

    url = conftest._resolve_test_redis_url()
    assert url == f"redis://:p4ss@127.0.0.1:6379/{conftest._TEST_REDIS_DB}"
    assert "redis:6379" not in url, "the compose hostname must not survive"


def test_username_and_password_are_both_preserved(monkeypatch, tmp_path):
    monkeypatch.delenv("REDIS_URL", raising=False)
    (tmp_path / ".env").write_text("REDIS_URL=redis://user:p4ss@redis:6380/2\n", encoding="utf-8")
    monkeypatch.setattr(conftest, "_BACKEND_DIR", str(tmp_path))
    assert (
        conftest._resolve_test_redis_url()
        == f"redis://user:p4ss@127.0.0.1:6380/{conftest._TEST_REDIS_DB}"
    )


def test_falls_back_to_passwordless_localhost(monkeypatch, tmp_path):
    """No .env (CI checkout) must still yield a usable default."""
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.setattr(conftest, "_BACKEND_DIR", str(tmp_path))
    assert conftest._resolve_test_redis_url() == f"redis://localhost:6379/{conftest._TEST_REDIS_DB}"


def test_malformed_env_value_does_not_raise(monkeypatch, tmp_path):
    monkeypatch.delenv("REDIS_URL", raising=False)
    (tmp_path / ".env").write_text("REDIS_URL=\n", encoding="utf-8")
    monkeypatch.setattr(conftest, "_BACKEND_DIR", str(tmp_path))
    assert conftest._resolve_test_redis_url() == f"redis://localhost:6379/{conftest._TEST_REDIS_DB}"


def test_no_password_is_committed_in_conftest():
    """The credential must come from a gitignored file at runtime, never source."""
    src = open(conftest.__file__, encoding="utf-8").read()
    assert "mukthiguru_redis_pass" not in src


def test_suite_process_has_a_redis_url():
    assert os.environ.get("REDIS_URL", "").startswith("redis")


def test_suite_never_uses_the_application_redis_db():
    """The per-test flush must never be able to wipe a running backend's state.

    The app uses /0; the suite is pinned to a dedicated index.
    """
    assert conftest._TEST_REDIS_DB != 0
    assert os.environ["REDIS_URL"].rstrip("/").endswith(f"/{conftest._TEST_REDIS_DB}")
