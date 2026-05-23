#!/usr/bin/env python3
"""
Mukthi Guru — Idempotent Admin Seeder

Seeds the admin user in Supabase. Safe to re-run — uses upsert logic.

Usage (from backend container):
    python3 scripts/seed_admin.py

Usage (from host via Docker):
    export PATH="/Users/harshodaikolluru/.docker/bin:$PATH"
    docker exec mukthiguru-backend python3 scripts/seed_admin.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ADMIN_EMAIL = "kharshaengineer@gmail.com"
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "Admin@123456")

# Use service role key — this key allows bypassing RLS
SUPABASE_URL = os.getenv("SUPABASE_URL", "http://host.docker.internal:54321")
# Local Supabase default service role key (safe for local dev only)
SUPABASE_SERVICE_KEY = os.getenv(
    "SUPABASE_KEY",
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZS1kZW1vIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImV4cCI6MTk4MzgxMjk5Nn0.EGIM96RAZx35lJzdJsyH-qQwv8Hdp7fsn3W0YpN81IU",
)


def seed_admin():
    try:
        from supabase import create_client
    except ImportError:
        print("❌ supabase-py not installed. Run: pip install supabase")
        sys.exit(1)

    print(f"🔗 Connecting to Supabase at {SUPABASE_URL}...")
    client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)

    # Step 1: Check / create admin user
    print(f"👤 Checking for admin user: {ADMIN_EMAIL}")
    try:
        result = client.auth.admin.list_users()
        users = result if isinstance(result, list) else getattr(result, "users", [])
        existing = [u for u in users if getattr(u, "email", None) == ADMIN_EMAIL]

        if existing:
            user_id = str(existing[0].id)
            print(f"   ✅ Admin user already exists (id={user_id})")
            client.auth.admin.update_user_by_id(
                user_id, {"password": ADMIN_PASSWORD, "email_confirm": True}
            )
            print(f"   ✅ Admin password forcefully updated to {ADMIN_PASSWORD}")
        else:
            result = client.auth.admin.create_user(
                {
                    "email": ADMIN_EMAIL,
                    "password": ADMIN_PASSWORD,
                    "email_confirm": True,
                }
            )
            user_id = str(result.user.id)
            print(f"   ✅ Admin user created (id={user_id})")

    except Exception as e:
        print(f"   ❌ Failed to get/create admin user: {e}")
        sys.exit(1)

    # Step 2: Grant admin role (idempotent via upsert)
    print(f"🔑 Granting admin role to {ADMIN_EMAIL}...")
    try:
        client.table("user_roles").upsert(
            {"user_id": user_id, "role": "admin"},
            on_conflict="user_id,role",
        ).execute()
        print("   ✅ Admin role granted")
    except Exception as e:
        print(f"   ❌ Failed to grant role: {e}")
        sys.exit(1)

    # Step 3: Verify
    try:
        roles = client.table("user_roles").select("*").eq("user_id", user_id).execute()
        print(f"   ✅ Verified roles: {[r['role'] for r in roles.data]}")
    except Exception as e:
        print(f"   ⚠️  Could not verify roles (RLS may apply): {e}")

    print()
    print("🎉 Admin setup complete!")
    print(f"   Email:    {ADMIN_EMAIL}")
    print(f"   Password: {ADMIN_PASSWORD}")
    print(f"   User ID:  {user_id}")
    print()
    print("   Login at: http://localhost/admin/login")


if __name__ == "__main__":
    seed_admin()
