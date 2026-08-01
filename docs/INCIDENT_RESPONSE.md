# Incident Response Runbook — AskMukthiGuru

**Status**: Active  
**Owner**: Harshodai Kolluru  
**Contact**: security@askmukthiguru.com  
**Last updated**: 2026-08-01

---

## 1. Severity Levels

| Severity | Definition | Response SLA |
|----------|-----------|-------------|
| P0 — Critical | Active data breach / credential exposure / service down for all users | Immediate (< 1 hour) |
| P1 — High | Auth bypass / cross-tenant data access / sustained performance degradation | < 4 hours |
| P2 — Medium | Elevated error rates / partial service degradation / suspicious activity | < 24 hours |
| P3 — Low | Single-user issues / non-critical bugs | Next business day |

---

## 2. Common Scenarios

### 2.1 Credential Exposure (API keys / JWT secret in git or logs)

**Detection**: Alert from gitleaks in CI, GitHub secret scanner, or manual discovery.

**Containment**:
```bash
# 1. Rotate the exposed credential IMMEDIATELY:
#    - Supabase service-role key: Dashboard → Settings → API → Regenerate
#    - JWT_SECRET: generate new secret, update Railway env vars
#    - LLM API keys: provider dashboard → revoke old key → create new
#    - Redis password: update redis-server config + REDIS_PASSWORD env var

# 2. Kill active sessions that used the old JWT secret
#    (Supabase: Auth → Users → sign out all, or rotate JWT secret which invalidates all)

# 3. Scrub from git history if committed:
git-filter-repo --path '<filename>' --invert-paths --force
git push --force-with-lease origin main
```

**Recovery verification**:
- `curl -H "Authorization: Bearer <OLD_TOKEN>" https://your-api.railway.app/api/health` → should return 401
- Monitor Railway logs for authentication errors normalizing

---

### 2.2 Cross-Tenant Data Leak (User A reads User B's data)

**Detection**: Nightly RLS CI job failure (`nightly-rls.yml`), user report, or audit log anomaly.

**Containment**:
```bash
# 1. Run cross-user verifier immediately:
python3 backend/scripts/verify_rls_policies.py

# 2. If breach confirmed, take backend offline:
#    Railway: project → deploy → rollback OR set replicas to 0

# 3. Identify affected tables and time window from Postgres audit log:
#    Supabase Dashboard → Logs → Postgres logs → filter by affected user_id

# 4. Notify affected users (legal obligation under GDPR Art. 33 — 72hr window)
```

**Recovery**:
```bash
# Re-apply RLS migration if policy was wrong:
# Supabase Dashboard → SQL Editor → run migration
# Verify all policies:
python3 backend/scripts/verify_rls_policies.py
```

---

### 2.3 LLM Hallucination Incident (Doctrinally incorrect / harmful answer)

**Detection**: User report, faithfulness_score < 0.5 in `/api/chat` metadata, benchmark regression.

**Containment**:
```bash
# 1. Check recent chat logs for pattern:
# Supabase → Table Editor → chat_messages → filter by timestamp
# Look for responses where faithfulness_flag = false

# 2. If systematic (not one-off), check:
#    - SEMANTIC_CACHE_SIMILARITY threshold (may be caching bad answers)
#    - CRAG grading thresholds in backend/rag/nodes/grade_documents.py
#    - Embedding dimension mismatch (the 2026-07-16 incident class)

# 3. Emergency: disable semantic cache to force fresh retrieval:
make flush-cache
```

**Recovery**:
```bash
# Run faithfulness benchmark:
python3 backend/benchmarks/ruthless_benchmark.py --endpoint https://your-api.railway.app

# If cache poisoning suspected, flush and verify:
make flush-cache
python3 backend/benchmarks/ruthless_benchmark.py --endpoint http://localhost:8000
```

---

### 2.4 Denial of Service / Railway OOM

**Detection**: Railway OOM kill notifications, health check failures, `/api/health` returning 503.

**Containment**:
```bash
# Railway: project → service → metrics → identify memory spike source
# Check: was an ingestion job running? (scripts/ingest_lightrag_data.py)
# Immediate: Railway → deploy → rollback to last stable deploy

# Check for runaway requests:
# Railway logs → filter by status 200 → sort by duration → find long-running requests
```

**Recovery**:
```bash
# Scale down concurrent workers if needed:
# Railway env var: WEB_CONCURRENCY=1

# After stabilization, identify root cause:
# - Embedding model loaded twice? (EMBEDDING_BACKEND mismatch)
# - Memory leak in streaming handler?
# - Large payload (check max_input_length setting)
```

---

### 2.5 Data Loss (Qdrant / Neo4j corruption)

**Detection**: Retrieval returning 0 results, embedding dimension mismatch errors, Neo4j entity count drop.

**Containment**:
```bash
# Do NOT restart databases until you know the cause — restarts don't fix corruption

# Check Qdrant collection integrity:
curl http://localhost:6333/collections/spiritual_wisdom | python3 -m json.tool | grep '"vectors_count"'

# Check Neo4j node count:
# Neo4j Browser: MATCH (n) RETURN count(n) as count

# If corruption confirmed, restore from backup:
python3 backend/scripts/ops/backup_qdrant.py --restore
python3 backend/scripts/ops/backup_neo4j.py --restore
```

---

## 3. Escalation Contacts

| Role | Contact |
|------|---------|
| Primary on-call | Harshodai Kolluru — direct message |
| Supabase support | https://supabase.com/support (Pro tier) |
| Railway support | https://railway.app/help |
| Security disclosure | security@askmukthiguru.com |

---

## 4. Post-Incident Review Template

After any P0/P1 incident, complete within 48 hours:

```
Incident: [brief title]
Date/time detected: 
Duration: 
Severity: 
Affected users: 

Timeline:
- [time] — [event]

Root cause:

What went well:

What failed:

Action items:
- [ ] [action] — owner — deadline
```

File the review in `backend/incidents/` (gitignored — may contain PII).

---

## 5. Useful Commands

```bash
# Check backend health
curl https://askmukthiguru-production.up.railway.app/api/health

# Flush all caches
make flush-cache

# Run RLS verifier
python3 backend/scripts/verify_rls_policies.py

# Run security audit scripts
bash scripts/security/audit_endpoints.sh
bash scripts/security/audit_headers.sh

# Check for leaked secrets in current tree
gitleaks detect --source . -v

# Run Bandit SAST
cd backend && bandit -r . -x tests/,benchmarks/ --severity-level medium
```
