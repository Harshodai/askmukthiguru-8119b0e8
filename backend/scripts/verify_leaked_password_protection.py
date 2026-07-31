"""Verify Supabase leaked-password protection is enabled.

Attempts sign-up with a known-bad password and expects the provider to reject
it with a leaked_password reason. Run only after enabling the setting in the
Supabase dashboard (Auth > Providers > Email > Prevent the use of leaked passwords).

Required env:
    SUPABASE_URL      e.g. https://<project-ref>.supabase.co
    SUPABASE_ANON_KEY project anon/public key

Optional env (for cleanup of test identity when feature is not yet enabled):
    SUPABASE_SERVICE_ROLE_KEY  project service-role key — used to delete the
                               test account created during verification so no
                               orphaned identities accumulate in the auth project.
"""

import json
import os
import sys
import uuid

import requests


def _delete_test_user(supabase_url: str, service_role_key: str, user_id: str) -> None:
    """Best-effort deletion of a test identity via the Admin API."""
    try:
        delete_url = f"{supabase_url}/auth/v1/admin/users/{user_id}"
        requests.delete(
            delete_url,
            headers={"apikey": service_role_key, "Authorization": f"Bearer {service_role_key}"},
            timeout=10,
        )
    except Exception:
        pass  # cleanup is non-fatal


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
    if created_user_id and service_role_key:
        _delete_test_user(supabase_url, service_role_key, created_user_id)

    response_text = json.dumps(data)
    if response.status_code == 200 or "leaked_password" not in response_text:
        print(json.dumps({"ok": False, "response": data}))
        return 1

    print(json.dumps({"ok": True}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
