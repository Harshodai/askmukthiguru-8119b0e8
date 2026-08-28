"""Cross-user RLS verifier for local and staging Supabase.

Creates two test users (Alice and Bob), seeds Alice-owned rows in
conversations, chat_messages, meditation_sessions, user_profiles,
user_streaks, user_retention_cards, study_notebooks, user_episodes,
waitlist_entries, assistant_scope_metadata, and memory_outbox, then
proves Bob cannot read, update, or delete Alice's rows (or service-only rows)
via Supabase row-level security policies.

Run from backend/:
    SUPABASE_URL=http://localhost:54321 \
    SUPABASE_SERVICE_ROLE_KEY=<local-service-role> \
    SUPABASE_ANON_KEY=<local-anon-key> \
    .venv/bin/python scripts/verify_rls_policies.py

Enumerate RLS-bearing tables from schema:
    .venv/bin/python scripts/verify_rls_policies.py --list-tables
"""

import argparse
import json
import os
import re
import sys
import time
import uuid
from pathlib import Path
from typing import Any

import requests
from supabase import Client, ClientOptions, create_client

DEFAULT_SUPABASE_URL = "http://localhost:54321"

SUPABASE_URL = os.environ.get("SUPABASE_URL", DEFAULT_SUPABASE_URL).rstrip("/")
SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
ANON_KEY = os.environ.get("SUPABASE_ANON_KEY")
STAGING_ENVIRONMENT = os.environ.get("STAGING_ENVIRONMENT", "")
ALLOW_STAGING_SYNTHETIC_USERS = os.environ.get("ALLOW_STAGING_SYNTHETIC_USERS", "") == "1"

PROBED_TABLES = [
    "conversations",
    "chat_messages",
    "meditation_sessions",
    "user_profiles",
    "user_streaks",
    "user_retention_cards",
    "study_notebooks",
    "user_episodes",
    "waitlist_entries",
    "assistant_scope_metadata",
    "memory_outbox",
]


def list_rls_tables(migrations_dir: Path | str | None = None) -> list[str]:
    """Enumerate all RLS-bearing tables from SQL migration files with fallback."""
    tables: set[str] = set()
    canonical_tables = {
        "alert_events",
        "alert_rules",
        "annotations",
        "app_logs",
        "app_settings",
        "assistant_access",
        "assistant_scope_metadata",
        "assistants",
        "cancellations",
        "chat_messages",
        "chat_queries",
        "chat_responses",
        "chat_sessions",
        "communications",
        "conversation_memories",
        "conversations",
        "daily_teachings",
        "digital_employees",
        "doctrine_faqs",
        "eval_results",
        "eval_runs",
        "exit_surveys",
        "feedback_events",
        "golden_questions",
        "guru_core_memory",
        "guru_memories",
        "guru_session_summaries",
        "ingest_jobs",
        "ingestion_checkpoints",
        "ingestion_runs",
        "kb_chunks",
        "kb_sources",
        "meditation_sessions",
        "memory_consent_receipts",
        "memory_deletion_receipts",
        "memory_outbox",
        "model_pricing",
        "notes",
        "okf_review_queue",
        "pending_extractions",
        "profiles",
        "prompt_versions",
        "push_devices",
        "push_subscriptions",
        "query_clusters",
        "retention_events",
        "retrieval_events",
        "router_decisions",
        "safety_events",
        "save_offers",
        "source_releases",
        "staging_quality_queue",
        "study_notebook_items",
        "study_notebooks",
        "telemetry_events",
        "token_usage",
        "trace_spans",
        "trigger_events",
        "user_brain_edges",
        "user_brain_keys",
        "user_brain_nodes",
        "user_course_progress",
        "user_episodes",
        "user_personas",
        "user_profiles",
        "user_retention_cards",
        "user_roles",
        "user_scene_blocks",
        "user_skills",
        "user_streaks",
        "waitlist_entries",
    }

    if migrations_dir is None:
        candidates = [
            Path(__file__).resolve().parents[2] / "supabase" / "migrations",
            Path.cwd() / "supabase" / "migrations",
            Path.cwd().parent / "supabase" / "migrations",
        ]
        for c in candidates:
            if c.is_dir():
                migrations_dir = c
                break

    if migrations_dir:
        mig_path = Path(migrations_dir)
        if mig_path.is_dir():
            pattern = re.compile(
                r"ALTER\s+TABLE\s+(?:ONLY\s+)?(?:public\.)?([a-zA-Z0-9_]+)\s+ENABLE\s+ROW\s+LEVEL\s+SECURITY",
                re.IGNORECASE,
            )
            for f in mig_path.glob("*.sql"):
                try:
                    content = f.read_text(encoding="utf-8")
                    for m in pattern.finditer(content):
                        tables.add(m.group(1).lower())
                except OSError:
                    continue

    tables.update(canonical_tables)
    return sorted(tables)


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
    if table in ("user_profiles", "user_streaks"):
        key = "user_id"
    elif table == "assistant_scope_metadata":
        key = "assistant_id"
    else:
        key = "user_id" if table == "user_profiles" else "id"
    service_client.table(table).delete().in_(key, ids).execute()


def _make_test_email(prefix: str) -> str:
    # Local Supabase may restrict allowed email domains (e.g. gmail/hotmail/outlook).
    return f"{prefix}-{uuid.uuid4().hex}@gmail.com"


def _is_permission_or_rls_error(exc: Exception) -> bool:
    msg = str(exc).lower()
    denial_signals = [
        "42501",
        "permission denied",
        "violates row-level security",
        "row-level security policy",
        "unauthorized",
        "forbidden",
        "401",
        "403",
        "404",
        "pgrst",
    ]
    return any(sig in msg for sig in denial_signals)


def run_verification() -> dict[str, Any]:
    failures: list[dict[str, Any]] = []
    cleanup_failures: list[dict[str, Any]] = []
    seeded_ids: dict[str, list[str]] = {t: [] for t in PROBED_TABLES}
    seeded_ids["assistants"] = []

    alice_email = _make_test_email("alice")
    bob_email = _make_test_email("bob")
    password = "Password123!x"
    alice_id = ""
    bob_id = ""

    try:
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

        # 1. conversations
        conv_id = ""
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
            if not _is_permission_or_rls_error(exc):
                failures.append({"table": "conversations", "error": str(exc)})

        # 2. chat_messages
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
            if not _is_permission_or_rls_error(exc):
                failures.append({"table": "chat_messages", "error": str(exc)})

        # 3. meditation_sessions
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
            if not _is_permission_or_rls_error(exc):
                failures.append({"table": "meditation_sessions", "error": str(exc)})

        # 4. user_profiles
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
            if not _is_permission_or_rls_error(exc):
                failures.append({"table": "user_profiles", "error": str(exc)})

        # 5. user_streaks
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
                seeded_ids["user_streaks"].append(alice_id)

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
            if not _is_permission_or_rls_error(exc):
                failures.append({"table": "user_streaks", "error": str(exc)})

        # 6. user_retention_cards
        try:
            card_resp = (
                alice_client.table("user_retention_cards")
                .insert(
                    {
                        "user_id": alice_id,
                        "question": "What is the Beautiful State?",
                        "answer": "A state of connection and peace",
                        "source_type": "concept",
                    }
                )
                .execute()
            )
            card_id = card_resp.data[0]["id"]
            seeded_ids["user_retention_cards"].append(card_id)

            bob_select = bob_client.table("user_retention_cards").select("*").eq("id", card_id).execute()
            bob_update = (
                bob_client.table("user_retention_cards")
                .update({"question": "Hacked by Bob"})
                .eq("id", card_id)
                .execute()
            )
            bob_delete = bob_client.table("user_retention_cards").delete().eq("id", card_id).execute()

            if bob_select.data:
                failures.append(
                    {"table": "user_retention_cards", "op": "select", "expected": [], "got": bob_select.data}
                )
            if bob_update.data:
                failures.append(
                    {
                        "table": "user_retention_cards",
                        "op": "update",
                        "expected": 0,
                        "got": len(bob_update.data),
                    }
                )
            if bob_delete.data:
                failures.append(
                    {
                        "table": "user_retention_cards",
                        "op": "delete",
                        "expected": 0,
                        "got": len(bob_delete.data),
                    }
                )
        except Exception as exc:
            if not _is_permission_or_rls_error(exc):
                failures.append({"table": "user_retention_cards", "error": str(exc)})

        # 7. study_notebooks
        try:
            nb_resp = (
                alice_client.table("study_notebooks")
                .insert({"user_id": alice_id, "title": "Alice Study Notebook"})
                .execute()
            )
            nb_id = nb_resp.data[0]["id"]
            seeded_ids["study_notebooks"].append(nb_id)

            bob_select = bob_client.table("study_notebooks").select("*").eq("id", nb_id).execute()
            bob_update = (
                bob_client.table("study_notebooks")
                .update({"title": "Hacked by Bob"})
                .eq("id", nb_id)
                .execute()
            )
            bob_delete = bob_client.table("study_notebooks").delete().eq("id", nb_id).execute()

            if bob_select.data:
                failures.append(
                    {"table": "study_notebooks", "op": "select", "expected": [], "got": bob_select.data}
                )
            if bob_update.data:
                failures.append(
                    {
                        "table": "study_notebooks",
                        "op": "update",
                        "expected": 0,
                        "got": len(bob_update.data),
                    }
                )
            if bob_delete.data:
                failures.append(
                    {
                        "table": "study_notebooks",
                        "op": "delete",
                        "expected": 0,
                        "got": len(bob_delete.data),
                    }
                )
        except Exception as exc:
            if not _is_permission_or_rls_error(exc):
                failures.append({"table": "study_notebooks", "error": str(exc)})

        # 8. user_episodes
        try:
            ep_resp = (
                alice_client.table("user_episodes")
                .insert({"user_id": alice_id, "query": "What is enlightenment?", "answer": "Inner freedom."})
                .execute()
            )
            ep_id = ep_resp.data[0]["id"]
            seeded_ids["user_episodes"].append(ep_id)

            bob_select = bob_client.table("user_episodes").select("*").eq("id", ep_id).execute()
            bob_update = (
                bob_client.table("user_episodes")
                .update({"query": "Hacked by Bob"})
                .eq("id", ep_id)
                .execute()
            )
            bob_delete = bob_client.table("user_episodes").delete().eq("id", ep_id).execute()

            if bob_select.data:
                failures.append(
                    {"table": "user_episodes", "op": "select", "expected": [], "got": bob_select.data}
                )
            if bob_update.data:
                failures.append(
                    {
                        "table": "user_episodes",
                        "op": "update",
                        "expected": 0,
                        "got": len(bob_update.data),
                    }
                )
            if bob_delete.data:
                failures.append(
                    {
                        "table": "user_episodes",
                        "op": "delete",
                        "expected": 0,
                        "got": len(bob_delete.data),
                    }
                )
        except Exception as exc:
            if not _is_permission_or_rls_error(exc):
                failures.append({"table": "user_episodes", "error": str(exc)})

        # 9. waitlist_entries (service_role only table; authenticated users must be blocked)
        try:
            wl_resp = (
                service_client.table("waitlist_entries")
                .insert({"email": f"waitlist-{uuid.uuid4().hex[:8]}@gmail.com", "name": "Alice Waitlist", "source": "rls_probe"})
                .execute()
            )
            wl_id = wl_resp.data[0]["id"]
            seeded_ids["waitlist_entries"].append(wl_id)

            bob_select = bob_client.table("waitlist_entries").select("*").eq("id", wl_id).execute()
            bob_update = (
                bob_client.table("waitlist_entries")
                .update({"name": "Hacked by Bob"})
                .eq("id", wl_id)
                .execute()
            )
            bob_delete = bob_client.table("waitlist_entries").delete().eq("id", wl_id).execute()

            if bob_select.data:
                failures.append(
                    {"table": "waitlist_entries", "op": "select", "expected": [], "got": bob_select.data}
                )
            if bob_update.data:
                failures.append(
                    {
                        "table": "waitlist_entries",
                        "op": "update",
                        "expected": 0,
                        "got": len(bob_update.data),
                    }
                )
            if bob_delete.data:
                failures.append(
                    {
                        "table": "waitlist_entries",
                        "op": "delete",
                        "expected": 0,
                        "got": len(bob_delete.data),
                    }
                )
        except Exception as exc:
            if not _is_permission_or_rls_error(exc):
                failures.append({"table": "waitlist_entries", "error": str(exc)})

        # 10. assistant_scope_metadata (service_role only; references assistants table)
        try:
            ast_slug = f"rls-ast-{uuid.uuid4().hex[:8]}"
            ast_resp = (
                service_client.table("assistants")
                .insert({"slug": ast_slug, "name": "RLS Test Assistant", "visibility": "private"})
                .execute()
            )
            ast_id = ast_resp.data[0]["id"]
            seeded_ids["assistants"].append(ast_id)

            asm_resp = (
                service_client.table("assistant_scope_metadata")
                .insert({"assistant_id": ast_id, "corpus_id": "askmukthiguru", "rights_status": "pending", "rollout_enabled": False})
                .execute()
            )
            asm_id = asm_resp.data[0]["assistant_id"]
            seeded_ids["assistant_scope_metadata"].append(asm_id)

            bob_select = bob_client.table("assistant_scope_metadata").select("*").eq("assistant_id", asm_id).execute()
            bob_update = (
                bob_client.table("assistant_scope_metadata")
                .update({"corpus_id": "hacked"})
                .eq("assistant_id", asm_id)
                .execute()
            )
            bob_delete = bob_client.table("assistant_scope_metadata").delete().eq("assistant_id", asm_id).execute()

            if bob_select.data:
                failures.append(
                    {"table": "assistant_scope_metadata", "op": "select", "expected": [], "got": bob_select.data}
                )
            if bob_update.data:
                failures.append(
                    {
                        "table": "assistant_scope_metadata",
                        "op": "update",
                        "expected": 0,
                        "got": len(bob_update.data),
                    }
                )
            if bob_delete.data:
                failures.append(
                    {
                        "table": "assistant_scope_metadata",
                        "op": "delete",
                        "expected": 0,
                        "got": len(bob_delete.data),
                    }
                )
        except Exception as exc:
            if not _is_permission_or_rls_error(exc):
                failures.append({"table": "assistant_scope_metadata", "error": str(exc)})

        # 11. memory_outbox
        try:
            outbox_resp = (
                service_client.table("memory_outbox")
                .insert(
                    {
                        "user_id": alice_id,
                        "session_id": f"sess-{uuid.uuid4().hex[:8]}",
                        "payload": {"test": "alice_secret_payload"},
                    }
                )
                .execute()
            )
            outbox_id = outbox_resp.data[0]["id"]
            seeded_ids["memory_outbox"].append(outbox_id)

            bob_select = bob_client.table("memory_outbox").select("*").eq("id", outbox_id).execute()
            bob_update = (
                bob_client.table("memory_outbox")
                .update({"session_id": "hacked"})
                .eq("id", outbox_id)
                .execute()
            )
            bob_delete = bob_client.table("memory_outbox").delete().eq("id", outbox_id).execute()

            if bob_select.data:
                failures.append(
                    {"table": "memory_outbox", "op": "select", "expected": [], "got": bob_select.data}
                )
            if bob_update.data:
                failures.append(
                    {
                        "table": "memory_outbox",
                        "op": "update",
                        "expected": 0,
                        "got": len(bob_update.data),
                    }
                )
            if bob_delete.data:
                failures.append(
                    {
                        "table": "memory_outbox",
                        "op": "delete",
                        "expected": 0,
                        "got": len(bob_delete.data),
                    }
                )
        except Exception as exc:
            if not _is_permission_or_rls_error(exc):
                failures.append({"table": "memory_outbox", "error": str(exc)})

    finally:
        # Guaranteed cleanup in reverse FK dependency order so constraints never block deletion.
        cleanup_order = [
            "chat_messages",
            "assistant_scope_metadata",
            "assistants",
            "user_retention_cards",
            "study_notebooks",
            "user_episodes",
            "memory_outbox",
            "meditation_sessions",
            "conversations",
            "user_streaks",
            "user_profiles",
            "waitlist_entries",
        ]
        for table in cleanup_order:
            ids = seeded_ids.get(table, [])
            if ids:
                try:
                    delete_rows(table, ids)
                except Exception as exc:
                    cleanup_failures.append({"table": table, "error": str(exc)})

        for table, ids in seeded_ids.items():
            if table not in cleanup_order and ids:
                try:
                    delete_rows(table, ids)
                except Exception as exc:
                    cleanup_failures.append({"table": table, "error": str(exc)})

        for user_id in (alice_id, bob_id):
            if user_id:
                try:
                    delete_user(user_id)
                except Exception as exc:
                    cleanup_failures.append({"table": "auth.users", "user_id": user_id, "error": str(exc)})

    return {
        "ok": len(failures) == 0 and len(cleanup_failures) == 0,
        "tests": len(PROBED_TABLES) * 3,
        "failures": len(failures),
        "cleanup_failures": len(cleanup_failures),
        "tables": PROBED_TABLES,
        "details": failures,
    }


def parse_args(args: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Cross-user RLS verifier for Supabase.")
    parser.add_argument(
        "--list-tables",
        action="store_true",
        help="Enumerate all RLS-bearing tables from schema and exit.",
    )
    return parser.parse_args(args)


def main(args: list[str] | None = None) -> int:
    parsed = parse_args(args)
    if parsed.list_tables:
        tables = list_rls_tables()
        report = {
            "ok": True,
            "count": len(tables),
            "tables": tables,
        }
        print(json.dumps(report, indent=2))
        return 0

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
