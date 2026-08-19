"""Verify Supabase leaked-password protection is enabled.

Attempts sign-up with a known-bad password and expects the provider to reject
it with a leaked_password reason. Run only after enabling the setting in the
Supabase dashboard (Auth > Providers > Email > Prevent the use of leaked passwords).

Required env:
    SUPABASE_URL      e.g. https://<project-ref>.supabase.co
    SUPABASE_ANON_KEY project anon/public key

Optional env:
    SUPABASE_SERVICE_ROLE_KEY  project service-role key — required for cleanup on
                               any non-local (remote) target so no orphaned identities
                               accumulate in the auth project. On local targets the
                               script proceeds without it (disposable local DB policy)
                               but prints a warning so the omission is never silent.

Install paths and resolved-version verification:
    Single lockfile policy (P1-OPS-4): backend/requirements.txt is the ONLY
    Python dependency source. uv.lock was removed 2026-08-10 — nothing consumed
    it (Docker, pip-audit CI, and cache-warm all install from requirements.txt).
    Docker:              pip install -r backend/requirements.txt (uv pip wrapper).
                         Verify with `pip show <pkg>` inside the image.
    Local dev:           make install → uv pip install -e ".[dev]" reads
                         pyproject.toml ranges; run `uv pip show <pkg>` to confirm.
                         Re-sync prod parity with `uv pip install -r requirements.txt`.
"""

import json
import os
import sys
import uuid
from urllib.parse import urlparse

import requests


def _delete_test_user(supabase_url: str, service_role_key: str, user_id: str) -> bool:
    """Best-effort deletion of a test identity via the Admin API.

    Returns True on confirmed deletion. Failures don't abort the
    verification run (cleanup is non-fatal) but are printed to stderr so an
    orphaned identity is never silent.
    """
    try:
        delete_url = f"{supabase_url}/auth/v1/admin/users/{user_id}"
        response = requests.delete(
            delete_url,
            headers={"apikey": service_role_key, "Authorization": f"Bearer {service_role_key}"},
            timeout=10,
        )
        response.raise_for_status()
        return True
    except Exception as exc:
        print(f"WARNING: failed to delete test user {user_id}: {exc}", file=sys.stderr)
        return False


def main() -> int:
    supabase_url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    anon_key = os.environ.get("SUPABASE_ANON_KEY", "")
    service_role_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")

    if not supabase_url or not anon_key:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": "Missing SUPABASE_URL or SUPABASE_ANON_KEY environment variables",
                }
            )
        )
        return 1

    # Use exact hostname comparison (not substring) to prevent lookalike bypasses,
    # e.g. https://localhost.evil.com would pass a naive `"localhost" in url` check.
    _APPROVED_LOCAL_HOSTS = {"localhost", "127.0.0.1", "host.docker.internal"}
    _APPROVED_REMOTE_HOSTS = {"supabase.co"}  # rightmost label of allowed SaaS targets

    parsed_host = urlparse(supabase_url).hostname or ""
    is_local_target = parsed_host in _APPROVED_LOCAL_HOSTS

    if not is_local_target and service_role_key:
        # Remote target with a service-role key: validate the key isn't being sent
        # to an unexpected host.
        host_ok = any(
            parsed_host == h or parsed_host.endswith(f".{h}") for h in _APPROVED_REMOTE_HOSTS
        )
        if not host_ok:
            print(
                json.dumps(
                    {
                        "ok": False,
                        "error": (
                            f"Refusing to send SUPABASE_SERVICE_ROLE_KEY to unrecognised "
                            f"host '{parsed_host}'. Add it to _APPROVED_REMOTE_HOSTS if intentional."
                        ),
                    }
                )
            )
            return 1

    if not service_role_key and not is_local_target:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": (
                        "Refusing to sign up a test identity against a non-local "
                        "SUPABASE_URL without SUPABASE_SERVICE_ROLE_KEY set — the "
                        "test account could not be cleaned up afterward."
                    ),
                }
            )
        )
        return 1

    if not service_role_key and is_local_target:
        # Disposable-local-DB policy: local Supabase instances are ephemeral,
        # so an orphaned test user is acceptable. Document explicitly rather than
        # silently skipping cleanup.
        print(
            "WARNING: SUPABASE_SERVICE_ROLE_KEY not set; test identity will NOT be "
            "deleted (local/disposable target — acceptable per disposable-local-DB policy).",
            file=sys.stderr,
        )

    url = f"{supabase_url}/auth/v1/signup"
    headers = {"apikey": anon_key, "Content-Type": "application/json"}
    # @gmail.com is used because prod Supabase rejects @example.com via the
    # email_domain_not_allowed rule. UUIDs in the local-part ensure uniqueness.
    email = f"leak-test-{uuid.uuid4()}@gmail.com"
    payload = {"email": email, "password": "password123"}

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        data = response.json()
    except Exception as exc:  # pragma: no cover - network/env failure path
        print(json.dumps({"ok": False, "error": str(exc)}))
        return 1

    # Cleanup: if signup succeeded (feature not yet enabled), delete the test user
    # so it does not persist as an orphan in the auth project.
    created_user_id: str | None = (
        data.get("id") if isinstance(data, dict) and response.status_code == 200 else None
    )
    cleanup_ok: bool | None = None  # None = cleanup not attempted
    if created_user_id and service_role_key:
        cleanup_ok = _delete_test_user(supabase_url, service_role_key, created_user_id)
    elif created_user_id and not service_role_key:
        # Signup succeeded (feature not enabled) but no key available to clean up.
        # Already warned above for local targets; for safety, surface in output too.
        cleanup_ok = False

    response_text = json.dumps(data)
    if response.status_code == 200 or "leaked_password" not in response_text:
        failure: dict = {"ok": False, "response": data}
        if cleanup_ok is False:
            failure["cleanup_ok"] = False
            failure["cleanup_warning"] = (
                "Test identity may be orphaned — delete manually or set SUPABASE_SERVICE_ROLE_KEY."
            )
        print(json.dumps(failure))
        return 1

    print(json.dumps({"ok": True}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
