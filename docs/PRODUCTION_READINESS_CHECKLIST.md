# Mukthi Guru Production Readiness Checklist

This checklist validates that the Mukthi Guru system is ready for production deployment.
All items must pass before considering the system production-ready.

## Prerequisites

- All backend tests pass: `pytest backend/tests/ -x`
- Docker infrastructure is running: `docker compose up -d qdrant redis neo4j jaeger`
- Ollama is running on host: `ollama serve`
- Environment variables are configured in `backend/.env`

## Checklist

### 1. Code Quality & Security

- [ ] All Python code follows PEP 8 and project coding standards
- [ ] No hardcoded secrets or credentials in source code
- [ ] All user inputs are validated and sanitized
- [ ] Security review passes with no HIGH or CRITICAL issues
- [ ] Dependencies are up-to-date and vulnerability-free (run `safety check`)
- [ ] License compliance verified (all dependencies are Apache 2.0, MIT, or Meta Community)

### 2. Functional Correctness

- [ ] All backend API endpoints return expected responses
- [ ] RAG pipeline completes without errors for standard queries
- [ ] Citations are correctly formatted and traceable to source documents
- [ ] Guardrails properly block harmful/off-topic inputs
- [ ] Serene Mind distress detection functions correctly
- [ ] Chat history is properly maintained and contextualized

### 3. Performance Benchmarks

- [ ] 95th percentile latency < 3s for standard queries
- [ ] Semantic cache hit rate > 40% for repeated queries
- [ ] Faithfulness score > 0.8 on spiritual queries
- [ ] Doctrine accuracy > 0.8 on core teachings
- [ ] Adversarial resilience > 0.95 (blocks jailbreak/adversarial prompts)
- [ ] Zero RPM limit violations (stays within 40 req/min for Sarvam Cloud)
- [ ] Token efficiency improvement > 25% vs baseline

### 4. Infrastructure & Deployment

- [ ] Docker containers start successfully with proper healthchecks
- [ ] All services report healthy status via `/api/health/detailed`
- [ ] Resource usage is within acceptable limits (no OOM crashes)
- [ ] Logs show no WARN/ERROR messages during normal operation
- [ ] Backup and recovery procedures are documented and tested
- [ ] Rollback procedure is validated and functional

### 5. Monitoring & Observability

- [ ] Metrics endpoint (`/metrics`) returns actionable Prometheus-format data
- [ ] Key metrics are being collected: latency, token usage, cache hits, faithfulness
- [ ] Distributed tracing is functional via Jaeger
- [ ] Alerting thresholds are configured for critical metrics
- [ ] Log aggregation is working and searchable

### 6. Documentation & Runbooks

- [ ] Architecture documentation is up-to-date
- [ ] API documentation is complete and accurate
- [ ] Deployment procedures are documented
- [ ] Troubleshooting guide covers common issues
- [ ] Onboarding documentation for new developers is complete
- [ ] Runbooks for operational procedures are available

### 7. Legal & Compliance

- [ ] All data processing is local (zero external API calls at inference)
- [ ] Only approved data sources are used (Sri Preethaji & Sri Krishnaji teachings)
- [ ] Privacy policy is implemented and respected
- [ ] Terms of service are displayed and accepted
- [ ] Content rights and attributions are properly handled

## Validation Script

Run the automated validation script:
```bash
./scripts/deploy_verification.sh
```

This script should return all checks passing (green light) before production deployment.

## Sign-off

| Role | Name | Signature | Date |
|------|------|-----------|------|
| Developer | | | |
| QA Engineer | | | |
| DevOps Engineer | | | |
| Product Owner | | | |

**Production Readiness: GREEN LIGHT 🚦** when all checklist items pass and sign-off is complete.