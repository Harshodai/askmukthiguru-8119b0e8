# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 1.x     | :white_check_mark: |

## Reporting a Vulnerability

Report vulnerabilities to security@askmukthiguru.com. Do not file public issues.

## Security Architecture

### Authentication & Authorization
- **Frontend**: Supabase Auth (email/password + Google OAuth)
- **Backend**: JWT-based auth via Supabase `go_true` middleware
- **Admin APIs**: Supabase RBAC enforced server-side
- **Test Auth Backdoor**: `X-Test-Key` header accepted only when `IS_PRODUCTION=false` AND `ENABLE_TEST_AUTH=true`

### API Security
- Rate limiting on `/api/chat` endpoint (token bucket, per-tenant + per-user)
- Input sanitization via `sanitize_user_input()` on all user messages
- Request size limits enforced at Nginx (1MB) and FastAPI (`max_input_length`)
- CORS restricted to configured origins

### LLM Safety Measures
- Input guardrails: harmful content detection, crisis resource injection
- Output guardrails: harmful content filtering, rejection of adversarial premises
- Serene Mind: distress detection with graceful disengagement
- CoVe (optional): factual consistency verification

### Infrastructure Security
- All services run in Docker containers with least-privilege networking
- Secrets managed via environment variables (never hardcoded)
- Neo4j/Qdrant/Redis not exposed to public internet
- Health check endpoint (`/api/health`) returns minimal info

## Security.txt
Contact: security@askmukthiguru.com
Preferred-Languages: en
