# Security Checklist — Mukthi Guru

Status as of E7 (Deployment Hardening). Pentest/SAST covered separately under E11.

| # | Area | Item | Status | Notes |
|---|------|------|--------|-------|
| 1 | API Security | HTTPS/TLS termination at edge (Nginx/Vercel) | TODO | `docker-compose.prod.yml` exposes 80/443 but no TLS cert config; edge CDN needed |
| 2 | API Security | Rate limiting on `/api/chat` and auth endpoints | DONE | Coalescer + circuit breaker in pipeline; add edge-level rate limit (WAF) for prod |
| 3 | API Security | CORS allowlist (no `*` in prod) | TODO | Verify `CORS_ORIGINS` env in prod is scoped to domain, not wildcard |
| 4 | Auth | OAuth2 (Google via Supabase) | DONE | Supabase Auth + Google OAuth; `VITE_USE_NATIVE_OAUTH` flag for local |
| 5 | Auth | JWT signing + verification | DONE | `JWT_SECRET` env; backend verifies via Supabase JWKS |
| 6 | Auth | Session expiry / refresh token rotation | DONE | Supabase-managed session lifecycle |
| 7 | Auth | Benchmark test-key backdoor disabled in prod | DONE | `X-Test-Key` only honored when `IS_PRODUCTION=false AND ENABLE_TEST_AUTH=true` |
| 8 | Input Validation | Pydantic request schemas on all endpoints | DONE | FastAPI + Pydantic; `InputGuardrail` stage in pipeline |
| 9 | Input Validation | Prompt injection / jailbreak guardrails | DONE | `InputGuardrail` + `OutputGuardrail` stages; doctrinal keyword checks |
| 10 | Input Validation | Distress/self-harm detection | DONE | `DistressStage` routes to crisis resources |
| 11 | Secrets Management | No secrets in git / images | DONE | `.env` gitignored; secrets via env vars |
| 12 | Secrets Management | External secret manager in K8s prod | TODO | `values-production.yaml` notes ESO → AWS Secrets Manager/GCP SM; not wired |
| 13 | Secrets Management | Service-role key restricted to backend only | DONE | `SUPABASE_SERVICE_ROLE_KEY` only in backend env, never frontend |
| 14 | WAF | Web Application Firewall at edge | TODO | Add Cloudflare/AWS WAF in front of Vercel/Railway; not yet configured |
| 15 | DDoS | Edge DDoS protection | TODO | Cloudflare/AWS Shield; rely on hosting provider defaults |
| 16 | Dependency Scanning | SAST / dependency vulnerability scan | DONE | E11 covered SAST + red-team; see E11 report |
| 17 | Dependency Scanning | Container image scanning (Trivy/Grype) | TODO | Add to CI pipeline; GHCR images not scanned currently |
| 18 | Dependency Scanning | SBOM generation | TODO | Add `syft`/`cyclonedx` to release pipeline |
| 19 | Data Protection | PII not logged | DONE | Telemetry redacts query text; `DEPENDENCY_PHI` gauge only emits booleans |
| 20 | Data Protection | Encryption at rest (Qdrant/Neo4j volumes) | TODO | Local volumes unencrypted; prod needs KMS-encrypted EBS/PV |
| 21 | Observability | Security event audit logging | DONE | `docs/ADMIN_AUDIT_REPORT.md` + admin audit trail |
| 22 | Network | Backend not exposed publicly (only via frontend/ingress) | DONE | Backend container has no published port in prod compose |

## Priority Remediation (before public prod launch)

1. **WAF + DDoS** (#14, #15) — Cloudflare in front of hosting provider.
2. **TLS cert automation** (#1) — Let's Encrypt + cert-manager (K8s) or Vercel auto-TLS.
3. **External Secrets Operator** (#12) — wire ESO to AWS Secrets Manager.
4. **Container image scanning in CI** (#17) — Trivy on GHCR push.
5. **Encrypted volumes** (#20) — KMS-encrypted EBS for Qdrant/Neo4j persistence.

## References
- E11 report (SAST + red-team): see session handoff / `lessons.md`.
- `docs/ADMIN_AUDIT_REPORT.md` — admin audit trail.
- `docs/PRODUCTION_READINESS_CHECKLIST.md` — broader readiness items.