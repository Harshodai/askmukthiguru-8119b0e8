import os
from supabase import create_client

SUPABASE_URL = "http://host.docker.internal:54321"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZS1kZW1vIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImV4cCI6MTk4MzgxMjk5Nn0.EGIM96RAZx35lJzdJsyH-qQwv8Hdp7fsn3W0YpN81IU"
client = create_client(SUPABASE_URL, SUPABASE_KEY)

result = client.auth.admin.list_users()
users = getattr(result, "users", result)
for u in users:
    if getattr(u, "email", None) == "kharshaengineer@gmail.com":
        print(f"Updating password for {u.id}...")
        client.auth.admin.update_user_by_id(
            str(u.id),
            {"password": "Admin@123456", "email_confirm": True}
        )
        print("Updated successfully!")
