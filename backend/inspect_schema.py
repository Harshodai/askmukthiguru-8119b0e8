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
        # Fetch a single row to inspect its keys
        res = client.table(table).select("*").limit(1).execute()
        if res.data:
            print(f"Table '{table}' columns: {list(res.data[0].keys())}")
        else:
            # Try to insert a dummy/invalid row to see if we get a postgrest error that lists columns,
            # or try to run an RPC, or just inspect schema cache by fetching /rest/v1/?apikey=...
            # But let's just inspect using a SELECT * on an empty table which still returns empty array, but we can try to find out.
            print(f"Table '{table}' has no rows to inspect columns directly.")
    except Exception as e:
        print(f"Error checking table '{table}': {e}")
