#!/usr/bin/env python3
"""
Mukthi Guru — Idempotent Admin Seeder

Seeds the admin user in Supabase. Safe to re-run — only creates the user if
missing and grants the admin role. Never overwrites an existing password.

Requires the following environment variables (no fallbacks — fails fast):
    ADMIN_EMAIL              — admin email address
    ADMIN_PASSWORD           — admin password (used ONLY when creating a new user)
    SUPABASE_URL             — Supabase project URL
    SUPABASE_SERVICE_ROLE_KEY (or SUPABASE_KEY) — service role key (RLS bypass)
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _require_env(name: str, *aliases: str) -> str:
    for key in (name, *aliases):
        val = os.environ.get(key)
        if val:
            return val
    print(f"❌ Missing required environment variable: {name}")
    sys.exit(2)


def seed_admin() -> None:
    admin_email = _require_env("ADMIN_EMAIL")
    admin_password = _require_env("ADMIN_PASSWORD")
    supabase_url = _require_env("SUPABASE_URL")
    supabase_key = _require_env("SUPABASE_SERVICE_ROLE_KEY", "SUPABASE_KEY")

    try:
        from supabase import create_client
    except ImportError:
        print("❌ supabase-py not installed. Run: pip install supabase")
        sys.exit(1)

    print(f"🔗 Connecting to Supabase at {supabase_url}...")
    client = create_client(supabase_url, supabase_key)

    print(f"👤 Checking for admin user: {admin_email}")
    try:
        result = client.auth.admin.list_users(per_page=200)
        users = result if isinstance(result, list) else getattr(result, "users", [])
        existing = [u for u in users if getattr(u, "email", None) == admin_email]

        if existing:
            user_id = str(existing[0].id)
            print(f"   ✅ Admin user already exists (id={user_id}) — leaving password untouched")
        else:
            result = client.auth.admin.create_user(
                {
                    "email": admin_email,
                    "password": admin_password,
                    "email_confirm": True,
                }
            )
            user_id = str(result.user.id)
            print(f"   ✅ Admin user created (id={user_id})")
    except Exception as e:
        print(f"   ❌ Failed to get/create admin user: {e}")
        sys.exit(1)

    print(f"🔑 Granting admin role to {admin_email}...")
    try:
        client.table("user_roles").upsert(
            {"user_id": user_id, "role": "admin"},
            on_conflict="user_id,role",
        ).execute()
        print("   ✅ Admin role granted")
    except Exception as e:
        print(f"   ❌ Failed to grant role: {e}")
        sys.exit(1)

    print("\n🎉 Admin setup complete.")
    print(f"   Email:   {admin_email}")
    print(f"   User ID: {user_id}")


if __name__ == "__main__":
    seed_admin()
