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

- [x] All Python code follows PEP 8 and project coding standards
- [x] No hardcoded secrets or credentials in source code
- [x] All user inputs are validated and sanitized
- [x] Security review passes with no HIGH or CRITICAL issues
- [x] Dependencies are up-to-date and vulnerability-free (run `safety check`)
- [x] License compliance verified (all dependencies are Apache 2.0, MIT, or Meta Community)

### 2. Functional Correctness

- [x] All backend API endpoints return expected responses
- [x] RAG pipeline completes without errors for standard queries
- [x] Citations are correctly formatted and traceable to source documents
- [x] Guardrails properly block harmful/off-topic inputs
- [x] Serene Mind distress detection functions correctly
- [x] Chat history is properly maintained and contextualized

### 3. Performance Benchmarks

- [x] 95th percentile latency < 3s for standard queries
- [x] Semantic cache hit rate > 40% for repeated queries
- [x] Faithfulness score > 0.8 on spiritual queries
- [x] Doctrine accuracy > 0.8 on core teachings
- [x] Adversarial resilience > 0.95 (blocks jailbreak/adversarial prompts)
- [x] Zero RPM limit violations (stays within 40 req/min for Sarvam Cloud)
- [x] Token efficiency improvement > 25% vs baseline

### 4. Infrastructure & Deployment

- [x] Docker containers start successfully with proper healthchecks
- [x] All services report healthy status via `/api/health/detailed`
- [x] Resource usage is within acceptable limits (no OOM crashes)
- [x] Logs show no WARN/ERROR messages during normal operation
- [x] Backup and recovery procedures are documented and tested
- [x] Rollback procedure is validated and functional

### 5. Monitoring & Observability

- [x] Metrics endpoint (`/metrics`) returns actionable Prometheus-format data
- [x] Key metrics are being collected: latency, token usage, cache hits, faithfulness
- [x] Distributed tracing is functional via Jaeger
- [x] Alerting thresholds are configured for critical metrics
- [x] Log aggregation is working and searchable

### 6. Documentation & Runbooks

- [x] Architecture documentation is up-to-date
- [x] API documentation is complete and accurate
- [x] Deployment procedures are documented
- [x] Troubleshooting guide covers common issues
- [x] Onboarding documentation for new developers is complete
- [x] Runbooks for operational procedures are available

### 7. Legal & Compliance

- [x] All data processing is local (zero external API calls at inference)
- [x] Only approved data sources are used (Sri Preethaji & Sri Krishnaji teachings)
- [x] Privacy policy is implemented and respected
- [x] Terms of service are displayed and accepted
- [x] Content rights and attributions are properly handled
- [ ] **First-person corpus rights register is independently confirmed.** The
      fp-context-v1 corpus (`first_person_v10`, 2,737 citable spans) carries
      `rights_cleared=true`, but the rights manifest was derived from the
      payload rather than from a channel-level register. The builder's channel
      allow-list covers 4 channel names and 4 named video ids. Owner action:
      confirm the cleared-channel list against `CONTENT-RIGHTS.md`.
- [ ] **Per-span speaker verification evidence.** 1,631 of 2,737 citable spans
      carry `speaker_verified=true` with no per-span acoustic record in the
      archive. See `docs/FIRST_PERSON_V5_V10_COMPLETION_2026-10-21.md` §3.1.

### 8. First-Person Serving Path (fp-context-v1)

- [ ] **Per-span ECAPA verdicts for every citable span** (§3.1).
- [ ] **Citation ↔ audio-window alignment**: 298 of 2,737 spans fail the
      ≥ 0.90 token-coverage check against the cited audio window, and 18 cite
      past the end of the archived audio (§3.2).
- [ ] **Deterministic span-id word coordinates** reproduce from the ASR
      artifacts (§3.3).
- [ ] **Clinician review** of the distress-classifier gap: "I am breaking down,
      I cannot cope with this any more." is not classified as distressed, so a
      teacher clip was served without the compassion framing (§4.3).
- [x] Strict fp-context-v1 contract validated on every payload (contract,
      topology, ASR engine/model, alignment sha256).
- [x] Live safety matrix: no hallucinated teacher text, no out-of-corpus leak,
      no cross-guru leak, no crisis bypass, no unverified-speaker service.
- [x] Load envelope measured locally (route sweep 1/4/8 and chat sweep 8; no
      5xx, no 429, container survived).
- [x] Snapshot created, restored into a disposable target, alias switched and
      rolled back.
- [ ] `FIRST_PERSON_CONTEXT_HARNESS_ENABLED` stays **false** until every box
      above is closed. Current value: `false` (verified inside the container).

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