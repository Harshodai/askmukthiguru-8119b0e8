# Supabase Test Setup

Tests in `backend/tests/test_supabase_connection.py` verify that the Supabase
client initializes and can reach the server. They **skip gracefully** when
Supabase credentials are not configured — no CI breakage.

## How to Get Credentials

### Local Supabase (recommended for development)

1. Start the local Supabase stack:
   ```bash
   npx supabase start
   ```
2. Copy the service role key from the output:
   ```bash
   npx supabase status
   ```
   Look for `SERVICE_ROLE_KEY` (or use the value labelled `sb_secret_*`).

3. Ensure these are set in `backend/.env` (already configured for most devs):
   ```
   SUPABASE_URL=http://host.docker.internal:54321
   SUPABASE_KEY=sb_secret_...
   ```

### Production / Cloud Supabase

From the [Supabase Dashboard](https://supabase.com/dashboard):
- **Project Settings → API → Project URL** → set as `SUPABASE_URL`
- **Project Settings → API → service_role key** → set as `SUPABASE_KEY`

## Running the Tests

```bash
cd backend
.venv/bin/python -m pytest tests/test_supabase_connection.py -v
```

### Expected output (configured):
```
test_supabase_settings_loaded PASSED
test_supabase_client_initializes PASSED
test_supabase_list_tables        PASSED
test_supabase_rpc_health         PASSED  (or SKIPPED if no version RPC)
```

### Expected output (unconfigured):
```
test_supabase_settings_loaded PASSED
test_supabase_client_initializes SKIPPED
test_supabase_list_tables        SKIPPED
test_supabase_rpc_health         SKIPPED
```

All existing tests that mock Supabase (e.g. `test_memory_service.py`,
`test_quality_gate.py`) continue to work as before — they use `MagicMock`
and do not depend on the fixture in `conftest.py`.
