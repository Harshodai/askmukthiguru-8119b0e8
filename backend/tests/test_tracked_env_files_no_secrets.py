"""Guard against a real secret ever landing in a git-tracked "public" env file.

.env.production and .env.mobile are deliberately git-tracked (force-added,
gitignore explicitly un-ignores .env.mobile; .env.production predates its own
.gitignore rule) because Vite's `.env.[mode]` convention auto-loads them at
build time, and the build pipeline (Lovable) appears to depend on the
tracked file being present in a fresh clone. Their content today is entirely
public-safe: VITE_-prefixed values Vite bakes into the client bundle anyway,
plus a Supabase *publishable* key and a Google OAuth client ID — both meant
to be public. The actual risk flagged in docs/DEPLOY_READINESS.md is not
today's content, it's the pattern: a future edit could add a real secret to
a file that looks like an ordinary .env file and nobody would notice.

This test is the guard: every key in these files must be VITE_-prefixed
(the whole point of the Vite convention — only ever build-time-public values
belong here), and no value may match a known secret-shaped pattern.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]

TRACKED_ENV_FILES = [".env.production", ".env.mobile"]

_SECRET_PATTERNS = [
    re.compile(r"-----BEGIN (RSA |EC )?PRIVATE KEY-----"),
    re.compile(r"\bsb_secret_[A-Za-z0-9_\-]+"),
    re.compile(r"\bsk_live_[A-Za-z0-9]{20,}"),
    re.compile(r"\bsk-[A-Za-z0-9]{20,}"),  # OpenAI/Sarvam-style secret keys
    re.compile(r"\bghp_[A-Za-z0-9]{36}"),  # GitHub PAT
    re.compile(r"\bxox[baprs]-[0-9a-zA-Z\-]{10,}"),  # Slack tokens
    # A three-segment JWT is a secret unless it's a known-public *anon* /
    # *publishable* Supabase token — those are meant to ship to the browser.
    re.compile(r"^eyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+$"),
]


def _parse_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def _looks_like_public_supabase_jwt(value: str) -> bool:
    """A Supabase anon-key JWT has role=anon in its (base64) payload."""
    import base64
    import json

    try:
        payload_b64 = value.split(".")[1]
        padded = payload_b64 + "=" * (-len(payload_b64) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded))
        return payload.get("role") == "anon"
    except Exception:
        return False


@pytest.mark.parametrize("filename", TRACKED_ENV_FILES)
def test_tracked_env_file_keys_are_vite_prefixed(filename: str):
    path = _REPO_ROOT / filename
    if not path.exists():
        pytest.skip(f"{filename} not present")
    values = _parse_env_file(path)
    non_vite = [k for k in values if not k.startswith("VITE_")]
    assert not non_vite, (
        f"{filename} has non-VITE_-prefixed key(s) {non_vite} — this file is "
        "git-tracked and Vite bakes every value into the public client "
        "bundle at build time; only ever put build-time-public values here."
    )


@pytest.mark.parametrize("filename", TRACKED_ENV_FILES)
def test_tracked_env_file_has_no_secret_shaped_values(filename: str):
    path = _REPO_ROOT / filename
    if not path.exists():
        pytest.skip(f"{filename} not present")
    values = _parse_env_file(path)
    offenders = []
    for key, value in values.items():
        for pattern in _SECRET_PATTERNS:
            if pattern.search(value):
                if value.count(".") == 2 and value.startswith("eyJ") and _looks_like_public_supabase_jwt(value):
                    continue
                offenders.append((key, pattern.pattern))
    assert not offenders, (
        f"{filename} has value(s) matching secret-shaped pattern(s): {offenders}. "
        "This file is git-tracked — a real secret here is committed to history "
        "immediately. Move it to an untracked .env.local instead."
    )


if __name__ == "__main__":
    import sys

    sys.exit(pytest.main([__file__, "-v"]))
