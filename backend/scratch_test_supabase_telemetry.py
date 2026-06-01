import sys

from supabase import create_client

url = "http://localhost:54321"
key = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZS1kZW1vIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImV4cCI6MTk4MzgxMjk5Nn0.EGIM96RAZx35lJzdJsyH-qQwv8Hdp7fsn3W0YpN81IU"

try:
    client = create_client(url, key)
    print("Supabase client created successfully.")
except Exception as e:
    print(f"Error creating Supabase client: {e}")
    sys.exit(1)

tables = [
    "chat_queries",
    "chat_responses",
    "retrieval_events",
    "trace_spans",
    "trigger_events",
    "safety_events",
]

for table in tables:
    try:
        res = client.table(table).select("count", count="exact").limit(1).execute()
        count = res.count
        print(f"Table '{table}': exists, count = {count}")
    except Exception as e:
        print(f"Table '{table}': error or does not exist: {e}")
