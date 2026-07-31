"""Verify Supabase leaked-password protection is enabled.

Attempts sign-up with a known-bad password and expects the provider to reject
it with a leaked_password reason. Run only after enabling the setting in the
Supabase dashboard (Auth > Providers > Email > Prevent the use of leaked passwords).

Required env:
    SUPABASE_URL      e.g. https://<project-ref>.supabase.co
    SUPABASE_ANON_KEY project anon/public key
"""

import json
import os
import sys
import uuid

import requests


def main() -> int:
    supabase_url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    anon_key = os.environ.get("SUPABASE_ANON_KEY", "")

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
    email = f"leak-test-{uuid.uuid4()}@gmail.com"
    payload = {"email": email, "password": "password123"}

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        data = response.json()
    except Exception as exc:  # pragma: no cover - network/env failure path
        print(json.dumps({"ok": False, "error": str(exc)}))
        return 1

    response_text = json.dumps(data)
    if response.status_code == 200 or "leaked_password" not in response_text:
        print(json.dumps({"ok": False, "response": data}))
        return 1

    print(json.dumps({"ok": True}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
