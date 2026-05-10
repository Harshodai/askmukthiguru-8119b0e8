# Next Steps for Mukthi Guru Integration

This document tracks the pending actions required to finalize the full-stack integration and environment parity.

## Pending User Actions
- [ ] **Add Google OAuth Credentials**:
    - Obtain `client_id` and `client_secret` from the Google Cloud Console.
    - Update `supabase/config.toml` to use these credentials (via `env()` or direct value).
    - Update the root `.env` file with `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET`.
- [ ] **Restart Supabase Stack**:
    - Run `npx supabase stop`
    - Run `npx supabase start`
- [ ] **Verify Local Google Sign-In**:
    - Ensure `.env.local` has `VITE_USE_NATIVE_OAUTH=true`.
    - Test the "Continue with Google" button on the [AuthPage](http://localhost:8081/auth).

## Pending System Actions
- [ ] **Docker Deployment Cleanup**:
    - Monitor the current `docker compose up -d --build` process.
    - Verify all 5 services (Frontend, Backend, Qdrant, Redis, Neo4j) are healthy using `docker ps`.
- [ ] **Realtime Subscription Test**:
    - Upload a daily teaching via the admin console and verify it appears in the chat interface without a refresh.

## Reference
- **Frontend Dev URL**: http://localhost:8081
- **Backend API Docs**: http://localhost:8000/docs
- **Local Supabase Studio**: http://localhost:54323
