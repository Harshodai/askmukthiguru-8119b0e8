# Security Checklist — Mukthi Guru

Status as of E7 (Deployment Hardening) + E8 (Remediation). Pentest/SAST covered separately under E11.

| # | Area | Item | Status | Notes | Priority |
|---|------|------|--------|-------|----------|
| 1 | API Security | HTTPS/TLS termination at edge (Nginx/Vercel) | TODO | `docker-compose.prod.yml` exposes 80/443 but no TLS cert config; edge CDN needed | HIGH |
| 2 | API Security | Rate limiting on `/api/chat` and auth endpoints | DONE | Coalescer + circuit breaker in pipeline; TokenBucketMiddleware (Redis) for /api/chat; TTL-based in-memory limiter for auth POST paths (5 req/60s); SlowAPI default 200/min across all routes. **E8:** Added admin rate limiter (30 req/60s) + AuditLogMiddleware | HIGH |
| 3 | API Security | CORS allowlist (no `*` in prod) | TODO | Verify `CORS_ORIGINS` env in prod is scoped to domain, not wildcard | HIGH |
| 4 | Auth | OAuth2 (Google via Supabase) | DONE | Supabase Auth + Google OAuth; `VITE_USE_NATIVE_OAUTH` flag for local | HIGH |
| 5 | Auth | JWT signing + verification | DONE | `JWT_SECRET` env; backend verifies via Supabase JWKS; AuthBridge abstraction supports multiple strategies | HIGH |
| 6 | Auth | Session expiry / refresh token rotation | DONE | Supabase-managed session lifecycle | HIGH |
| 7 | Auth | Benchmark test-key backdoor disabled in prod | DONE | `X-Test-Key` only honored when `IS_PRODUCTION=false AND ENABLE_TEST_AUTH=true` | HIGH |
| 8 | Input Validation | Pydantic request schemas on all endpoints | DONE | FastAPI + Pydantic; `InputGuardrail` stage in pipeline | HIGH |
| 9 | Input Validation | Prompt injection / jailbreak guardrails | DONE | `InputGuardrail` + `OutputGuardrail` stages; doctrinal keyword checks; 13 blocked topic categories with regex + LLM guard | HIGH |
| 10 | Input Validation | Distress/self-harm detection | DONE | `DistressStage` routes to crisis resources; Serene Mind engine | HIGH |
| 11 | Secrets Management | No secrets in git / images | DONE | `.env` gitignored; secrets via env vars | HIGH |
| 12 | Secrets Management | External secret manager in K8s prod | TODO | `values-production.yaml` notes ESO → AWS Secrets Manager/GCP SM; not wired | MEDIUM |
| 13 | Secrets Management | Service-role key restricted to backend only | DONE | `SUPABASE_SERVICE_ROLE_KEY` only in backend env, never frontend | HIGH |
| 14 | WAF | Web Application Firewall at edge | PARTIAL | nginx.conf has `limit_conn per_ip 100` + security headers (X-Frame-Options, HSTS, CSP, etc.). No Cloudflare/AWS WAF. Edge WAF needed for prod. | HIGH |
| 15 | DDoS | Edge DDoS protection | PARTIAL | nginx `limit_conn` + backend rate limiting (SlowAPI 200/min default). No Cloudflare/AWS Shield. Rely on hosting provider defaults. | HIGH |
| 16 | Dependency Scanning | SAST / dependency vulnerability scan | DONE | E11 covered SAST + red-team; `test_security_redteam.py` covers SSRF, injection, path traversal, DoS; `redteam_harness.py` for automated attacks | MEDIUM |
| 17 | Dependency Scanning | Container image scanning (Trivy/Grype) | TODO | Add to CI pipeline; GHCR images not scanned currently | MEDIUM |
| 18 | Dependency Scanning | SBOM generation | TODO | Add `syft`/`cyclonedx` to release pipeline | LOW |
| 19 | Data Protection | PII not logged | DONE | Telemetry redacts query text; `DEPENDENCY_PHI` gauge only emits booleans | HIGH |
| 20 | Data Protection | Encryption at rest (Qdrant/Neo4j volumes) | TODO | Local volumes unencrypted; prod needs KMS-encrypted EBS/PV | MEDIUM |
| 21 | Observability | API request audit logging | DONE | `AuditLogMiddleware` logs method, path, status, duration for all requests (skips health/metrics/static). `ADMIN_AUDIT_REPORT.md` documents admin data audit. JSONFormatter for structured logging. | HIGH |
| 22 | Network | Backend not exposed publicly (only via frontend/ingress) | DONE | Backend container has no published port in prod compose; ingress via frontend nginx | HIGH |
| 23 | SSRF | Server-Side Request Forgery protection | DONE | `check_url_safety()` in `web_search_guardrails.py`: blocks private IPs (RFC1918, link-local, loopback, IPv6), non-http schemes, embedded credentials, localhost, suspicious fragments. `is_valid_youtube_url()` strict regex domain check. OCR service validates URL IP. Image URL regex validation. **E8:** Added `check_url_safety()` to ingest endpoint for defense-in-depth. | HIGH |
| 24 | Backup | Backup scripts & verification | DONE | `scripts/ops/backup_neo4j.py` — neo4j-admin dump + APOC Cypher export, SHA256 checksums, archive validation, test-restore, retention cleanup. `scripts/ops/backup_qdrant.py` — snapshot create/download/verify, test-restore to temp collection. **Needed:** cron/scheduler integration for automated periodic backups | MEDIUM |
| 25 | Response | Incident response runbook | TODO | No IR runbook document exists. **Needed:** create `docs/INCIDENT_RESPONSE.md` covering: detection, containment, eradication, recovery steps for common scenarios (LLM hallucination, data leak, DoS, credential exposure) | MEDIUM |
| 26 | Secrets | Secrets rotation policy | TODO | No rotation policy document. **Needed:** document rotation cadence for JWT_SECRET, SUPABASE_SERVICE_ROLE_KEY, API keys. Automate via ESO (item #12) | MEDIUM |
| 27 | Auth | Comprehensive RBAC | DONE | Supabase Auth with roles (authenticated, service_role, admin). `get_current_user_from_supabase()` FastAPI dependency on all protected routes. Admin check via `user.get("is_superuser", False)` + `user_roles` table. Sufficient for current architecture; full role-permission matrix not needed. | HIGH |

## Priority Remediation (before public prod launch)

1. **WAF + DDoS** (#14, #15) — Cloudflare in front of hosting provider.
2. **TLS cert automation** (#1) — Let's Encrypt + cert-manager (K8s) or Vercel auto-TLS.
3. **External Secrets Operator** (#12) — wire ESO to AWS Secrets Manager.
4. **Container image scanning in CI** (#17) — Trivy on GHCR push.
5. **Encrypted volumes** (#20) — KMS-encrypted EBS for Qdrant/Neo4j persistence.
6. **Incident response runbook** (#25) — document detection/recovery procedures.
7. **Secrets rotation policy** (#26) — document rotation cadence and automate.

## References
- E11 report (SAST + red-team): see session handoff / `lessons.md`.
- `docs/ADMIN_AUDIT_REPORT.md` — admin audit trail.
- `docs/PRODUCTION_READINESS_CHECKLIST.md` — broader readiness items.
- `backend/services/web_search_guardrails.py` — SSRF/URL safety guardrails.
- `backend/app/middleware/audit.py` — API request audit logging.
- `scripts/ops/backup_neo4j.py`, `scripts/ops/backup_qdrant.py` — backup scripts with verification.
