# Test Credentials

## Admin Account (Local Supabase)
- Email: admin@example.com
- Password: Admin123!@#

## Test User (Local Supabase)
- Email: test@example.com
- Password: Test123!@#

## OAuth Test Accounts
- **Google OAuth**: Use a personal Gmail account for testing
- **Facebook OAuth**: Use a personal Facebook account for testing

## API Credentials (in backend/.env)
- **Sarvam API Key**: sk_placeholder_key_here
- **OpenRouter Key**: sk-or-v1-placeholder_key_here
- **Supabase URL**: http://127.0.0.1:54321
- **Supabase Anon Key**: sb_publishable_placeholder_key_here

## Health Check Endpoints
- `GET /api/health` — liveness probe
- `GET /api/healthz` — deep health check
- `GET /api/ready` — K8s readiness probe
- `GET /docs` — Swagger UI

---

*Created June 2026 — for local development and manual testing only.*
