"""Cross-user RLS verifier for local Supabase.

Creates two test users (Alice and Bob), seeds Alice-owned rows in
conversations, chat_messages, meditation_sessions, and user_profiles, then
proves Bob cannot read, update, or delete Alice's rows via Supabase
row-level security policies.

Run from backend/:
    SUPABASE_URL=http://localhost:54321 \
    SUPABASE_SERVICE_ROLE_KEY=<local-service-role> \
    SUPABASE_ANON_KEY=<local-anon-key> \
    .venv/bin/python scripts/verify_rls_policies.py
"""

import json
import os
import sys
import time
import uuid
from typing import Any

import requests
from supabase import Client, ClientOptions, create_client

DEFAULT_SUPABASE_URL = "http://localhost:54321"

SUPABASE_URL = os.environ.get("SUPABASE_URL", DEFAULT_SUPABASE_URL).rstrip("/")
SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
ANON_KEY = os.environ.get("SUPABASE_ANON_KEY")
STAGING_ENVIRONMENT = os.environ.get("STAGING_ENVIRONMENT", "")
ALLOW_STAGING_SYNTHETIC_USERS = os.environ.get("ALLOW_STAGING_SYNTHETIC_USERS", "") == "1"


def _is_local_supabase(url: str) -> bool:
    return url.startswith(("http://localhost:", "http://127.0.0.1:", "http://[::1]:"))


def _fail(error: str, details: dict[str, Any] | None = None) -> None:
    report: dict[str, Any] = {"ok": False, "error": error}
    if details:
        report.update(details)
    print(json.dumps(report, indent=2, default=str))
    sys.exit(1)


def _request_headers() -> dict[str, str]:
    return {
        "apikey": SERVICE_KEY,
        "Authorization": f"Bearer {SERVICE_KEY}",
        "Content-Type": "application/json",
    }


def _healthcheck() -> bool:
    try:
        r = requests.get(f"{SUPABASE_URL}/rest/v1/", timeout=5)
        return r.status_code < 500
    except requests.RequestException:
        return False


def create_user(email: str, password: str) -> str:
    url = f"{SUPABASE_URL}/auth/v1/admin/users"
    payload = {"email": email, "password": password, "email_confirm": True}
    r = requests.post(url, headers=_request_headers(), json=payload, timeout=30)
    r.raise_for_status()
    return r.json()["id"]


def sign_in(email: str, password: str) -> str:
    url = f"{SUPABASE_URL}/auth/v1/token?grant_type=password"
    headers = {"apikey": ANON_KEY, "Content-Type": "application/json"}
    r = requests.post(url, headers=headers, json={"email": email, "password": password}, timeout=30)
    r.raise_for_status()
    return r.json()["access_token"]


def client_for_token(token: str) -> Client:
    return create_client(
        SUPABASE_URL,
        ANON_KEY,
        options=ClientOptions(headers={"Authorization": f"Bearer {token}"}),
    )


def delete_user(user_id: str) -> None:
    url = f"{SUPABASE_URL}/auth/v1/admin/users/{user_id}"
    r = requests.delete(url, headers=_request_headers(), timeout=30)
    if r.status_code not in (200, 204, 404):
        r.raise_for_status()


def delete_rows(table: str, ids: list[str]) -> None:
    if not ids:
        return
    service_client = create_client(SUPABASE_URL, SERVICE_KEY)
    key = "user_id" if table == "user_profiles" else "id"
    service_client.table(table).delete().in_(key, ids).execute()


def _make_test_email(prefix: str) -> str:
    # Local Supabase may restrict allowed email domains (e.g. gmail/hotmail/outlook).
    return f"{prefix}-{uuid.uuid4().hex}@gmail.com"


def run_verification() -> dict[str, Any]:
    failures: list[dict[str, Any]] = []
    cleanup_failures: list[dict[str, Any]] = []
    seeded_ids: dict[str, list[str]] = {
        "conversations": [],
        "chat_messages": [],
        "meditation_sessions": [],
        "user_profiles": [],
    }
    alice_email = _make_test_email("alice")
    bob_email = _make_test_email("bob")
    password = "Password123!x"

    try:
        alice_id = create_user(alice_email, password)
        bob_id = create_user(bob_email, password)
    except requests.RequestException as exc:
        _fail("failed to create test users", {"details": str(exc)})

    try:
        alice_token = sign_in(alice_email, password)
        bob_token = sign_in(bob_email, password)
    except requests.RequestException as exc:
        _fail("failed to sign in test users", {"details": str(exc)})

    alice_client = client_for_token(alice_token)
    bob_client = client_for_token(bob_token)
    service_client = create_client(SUPABASE_URL, SERVICE_KEY)

    # conversations
    try:
        conv_resp = (
            alice_client.table("conversations")
            .insert({"user_id": alice_id, "title": "Alice private conv"})
            .execute()
        )
        conv_id = conv_resp.data[0]["id"]
        seeded_ids["conversations"].append(conv_id)

        bob_select = bob_client.table("conversations").select("*").eq("id", conv_id).execute()
        bob_update = (
            bob_client.table("conversations")
            .update({"title": "Hacked by Bob"})
            .eq("id", conv_id)
            .execute()
        )
        bob_delete = bob_client.table("conversations").delete().eq("id", conv_id).execute()

        if bob_select.data:
            failures.append(
                {"table": "conversations", "op": "select", "expected": [], "got": bob_select.data}
            )
        if bob_update.data:
            failures.append(
                {
                    "table": "conversations",
                    "op": "update",
                    "expected": 0,
                    "got": len(bob_update.data),
                }
            )
        if bob_delete.data:
            failures.append(
                {
                    "table": "conversations",
                    "op": "delete",
                    "expected": 0,
                    "got": len(bob_delete.data),
                }
            )
    except Exception as exc:
        failures.append({"table": "conversations", "error": str(exc)})

    # chat_messages
    try:
        msg_resp = (
            alice_client.table("chat_messages")
            .insert(
                {
                    "conversation_id": conv_id,
                    "role": "user",
                    "content": "Alice private message",
                }
            )
            .execute()
        )
        msg_id = msg_resp.data[0]["id"]
        seeded_ids["chat_messages"].append(msg_id)

        bob_select = bob_client.table("chat_messages").select("*").eq("id", msg_id).execute()
        bob_update = (
            bob_client.table("chat_messages")
            .update({"content": "Hacked by Bob"})
            .eq("id", msg_id)
            .execute()
        )
        bob_delete = bob_client.table("chat_messages").delete().eq("id", msg_id).execute()

        if bob_select.data:
            failures.append(
                {"table": "chat_messages", "op": "select", "expected": [], "got": bob_select.data}
            )
        if bob_update.data:
            failures.append(
                {
                    "table": "chat_messages",
                    "op": "update",
                    "expected": 0,
                    "got": len(bob_update.data),
                }
            )
        if bob_delete.data:
            failures.append(
                {
                    "table": "chat_messages",
                    "op": "delete",
                    "expected": 0,
                    "got": len(bob_delete.data),
                }
            )
    except Exception as exc:
        failures.append({"table": "chat_messages", "error": str(exc)})

    # meditation_sessions
    try:
        sess_resp = (
            alice_client.table("meditation_sessions")
            .insert({"user_id": alice_id, "duration_seconds": 60})
            .execute()
        )
        sess_id = sess_resp.data[0]["id"]
        seeded_ids["meditation_sessions"].append(sess_id)

        bob_select = bob_client.table("meditation_sessions").select("*").eq("id", sess_id).execute()
        bob_update = (
            bob_client.table("meditation_sessions")
            .update({"duration_seconds": 9999})
            .eq("id", sess_id)
            .execute()
        )
        bob_delete = bob_client.table("meditation_sessions").delete().eq("id", sess_id).execute()

        if bob_select.data:
            failures.append(
                {
                    "table": "meditation_sessions",
                    "op": "select",
                    "expected": [],
                    "got": bob_select.data,
                }
            )
        if bob_update.data:
            failures.append(
                {
                    "table": "meditation_sessions",
                    "op": "update",
                    "expected": 0,
                    "got": len(bob_update.data),
                }
            )
        if bob_delete.data:
            failures.append(
                {
                    "table": "meditation_sessions",
                    "op": "delete",
                    "expected": 0,
                    "got": len(bob_delete.data),
                }
            )
    except Exception as exc:
        failures.append({"table": "meditation_sessions", "error": str(exc)})

    # user_profiles
    try:
        now = time.time()
        prof_resp = (
            service_client.table("user_profiles")
            .insert(
                {
                    "user_id": alice_id,
                    "preferred_language": "en",
                    "created_at": now,
                    "updated_at": now,
                }
            )
            .execute()
        )
        prof_id = prof_resp.data[0]["user_id"]
        seeded_ids["user_profiles"].append(prof_id)

        bob_select = bob_client.table("user_profiles").select("*").eq("user_id", prof_id).execute()
        bob_update = (
            bob_client.table("user_profiles")
            .update({"preferred_language": "hi"})
            .eq("user_id", prof_id)
            .execute()
        )
        bob_delete = bob_client.table("user_profiles").delete().eq("user_id", prof_id).execute()

        if bob_select.data:
            failures.append(
                {"table": "user_profiles", "op": "select", "expected": [], "got": bob_select.data}
            )
        if bob_update.data:
            failures.append(
                {
                    "table": "user_profiles",
                    "op": "update",
                    "expected": 0,
                    "got": len(bob_update.data),
                }
            )
        if bob_delete.data:
            failures.append(
                {
                    "table": "user_profiles",
                    "op": "delete",
                    "expected": 0,
                    "got": len(bob_delete.data),
                }
            )
    except Exception as exc:
        failures.append({"table": "user_profiles", "error": str(exc)})

    # user_streaks
    try:
        streak_resp = (
            service_client.table("user_streaks")
            .insert(
                {
                    "user_id": alice_id,
                    "current_streak": 5,
                    "longest_streak": 10,
                    "total_practice_days": 12,
                }
            )
            .execute()
        )
        if streak_resp.data:
            seeded_ids["user_streaks"] = [alice_id]

        bob_select = bob_client.table("user_streaks").select("*").eq("user_id", alice_id).execute()
        bob_update = (
            bob_client.table("user_streaks")
            .update({"current_streak": 0})
            .eq("user_id", alice_id)
            .execute()
        )
        bob_delete = bob_client.table("user_streaks").delete().eq("user_id", alice_id).execute()

        if bob_select.data:
            failures.append(
                {"table": "user_streaks", "op": "select", "expected": [], "got": bob_select.data}
            )
        if bob_update.data:
            failures.append(
                {
                    "table": "user_streaks",
                    "op": "update",
                    "expected": 0,
                    "got": len(bob_update.data),
                }
            )
        if bob_delete.data:
            failures.append(
                {
                    "table": "user_streaks",
                    "op": "delete",
                    "expected": 0,
                    "got": len(bob_delete.data),
                }
            )
    except Exception as exc:
        failures.append({"table": "user_streaks", "error": str(exc)})

    # Cleanup rows before deleting users so FKs don't block.
    for table, ids in seeded_ids.items():
        if ids:
            try:
                delete_rows(table, ids)
            except Exception as exc:
                cleanup_failures.append({"table": table, "error": str(exc)})

    for user_id in (alice_id, bob_id):
        try:
            delete_user(user_id)
        except Exception as exc:
            cleanup_failures.append({"table": "auth.users", "user_id": user_id, "error": str(exc)})

    tables = ["conversations", "chat_messages", "meditation_sessions", "user_profiles", "user_streaks"]
    return {
        "ok": len(failures) == 0 and len(cleanup_failures) == 0,
        "tests": 15,
        "failures": len(failures),
        "cleanup_failures": len(cleanup_failures),
        "tables": tables,
        "details": failures,
    }


def main() -> int:
    if not _is_local_supabase(SUPABASE_URL) and not (
        STAGING_ENVIRONMENT == "staging" and ALLOW_STAGING_SYNTHETIC_USERS
    ):
        _fail(
            "refusing non-local RLS verification target",
            {
                "hint": "Set STAGING_ENVIRONMENT=staging and ALLOW_STAGING_SYNTHETIC_USERS=1 for an approved staging project"
            },
        )

    if not _healthcheck():
        _fail("cannot connect to supabase", {"url": SUPABASE_URL})

    if not SERVICE_KEY:
        _fail("missing env", {"hint": "SUPABASE_SERVICE_ROLE_KEY is required"})

    if not ANON_KEY:
        _fail(
            "SUPABASE_ANON_KEY required for anon probes (service_role bypasses RLS; never use it as a fallback)"
        )

    report = run_verification()
    print(json.dumps(report, indent=2, default=str))
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
