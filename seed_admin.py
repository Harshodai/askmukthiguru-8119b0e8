import os
from supabase import create_client, Client

# Local Supabase settings
url = "http://127.0.0.1:54321"
# Service role key from supabase_status.json
key = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZS1kZW1vIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImV4cCI6MTk4MzgxMjk5Nn0.EGIM96RAZx35lJzdJsyH-qQwv8Hdp7fsn3W0YpN81IU"

supabase: Client = create_client(url, key)

def seed_admin():
    email = "admin@example.com"
    password = "password123"
    
    print(f"Attempting to create admin user: {email}")
    
    try:
        # 1. Create user in Auth
        res = supabase.auth.admin.create_user({
            "email": email,
            "password": password,
            "email_confirm": True
        })
        user_id = res.user.id
        print(f"User created with ID: {user_id}")
        
        # 2. Assign admin role in public.user_roles
        # Note: roles is an enum 'admin'
        supabase.table("user_roles").insert({
            "user_id": user_id,
            "role": "admin"
        }).execute()
        
        print("Admin role assigned successfully!")
        
    except Exception as e:
        if "already exists" in str(e).lower() or "unique constraint" in str(e).lower():
            print("Admin user already exists. Checking role...")
            # Try to just assign role if user exists
            try:
                user = supabase.auth.admin.list_users()
                target_user = next((u for u in user if u.email == email), None)
                if target_user:
                    supabase.table("user_roles").upsert({
                        "user_id": target_user.id,
                        "role": "admin"
                    }).execute()
                    print("Admin role verified/updated.")
            except Exception as e2:
                print(f"Error during fallback: {e2}")
        else:
            print(f"Error: {e}")

if __name__ == "__main__":
    seed_admin()
