# Mukthi Guru Rollback Plan

This document outlines the step-by-step procedure for rolling back the Mukthi Guru application to a previous stable state in case of issues during or after deployment.

## Overview

The rollback plan covers scenarios where:
- Newly deployed version introduces critical bugs
- Performance degradation exceeds acceptable thresholds
- Security vulnerabilities are discovered
- Data corruption occurs during migration
- Infrastructure failures persist after restart

## Prerequisites

Before initiating a rollback, ensure:
1. You have access to the production environment
2. Previous stable version is available (git tag or Docker image)
3. Database backups are available if needed
4. Rollback is scheduled during low-traffic period if possible
5. Stakeholders are notified of the rollback

## Rollback Procedure

### Phase 1: Preparation

1. **Assess the Situation**
   - Clearly identify the issue requiring rollback
   - Gather evidence (logs, metrics, error reports)
   - Determine impact scope and severity
   - Confirm rollback is the appropriate action

2. **Notify Stakeholders**
   - Inform development team, operations, and product owners
   - Update status page if applicable
   - Notify users if user-facing impact is expected

3. **Prepare Rollback Resources**
   - Ensure access to previous stable version (git checkout <tag> or docker pull <image:tag>)
   - Verify database backup integrity if data rollback is needed
   - Prepare rollback scripts and documentation
   - Ensure monitoring and alerting are configured to detect rollback completion

### Phase 2: Execution

#### Option A: Code Rollback (No Database Changes)

If the issue is purely in application code and no database migrations were applied:

1. **Stop Traffic (if possible)**
   - Enable maintenance mode
   - Drain connections from load balancer
   - Or schedule during maintenance window

2. **Deploy Previous Version**
   ```bash
   # Code rollback
   git checkout <previous-stable-tag>
   
   # Or Docker image rollback
   docker compose pull <service>=<previous-image-tag>
   docker compose up -d --no-deps --build <service>
   ```

3. **Verify Deployment**
   - Check that services are running correctly
   - Verify health endpoints return healthy status
   - Confirm logs show expected version

4. **Restore Traffic**
   - Disable maintenance mode
   - Resume normal traffic flow
   - Monitor closely for stability

#### Option B: Database Rollback (With Schema Changes)

If database migrations were applied and need to be rolled back:

1. **Backup Current State**
   - Create backup of current database state before rollback
   - Verify backup can be restored if needed

2. **Rollback Database Migrations**
   ```bash
   # For Alembic-style migrations
   alembic downgrade <previous-revision>
   
   # Or restore from backup if migration rollback not possible
   # pg_restore -d <database> <backup-file>
   ```

3. **Deploy Previous Application Version**
   - Follow steps in Option A for code deployment

4. **Verify Data Consistency**
   - Run data validation checks
   - Confirm critical data is intact and accessible
   - Check for any corruption or missing data

#### Option C: Infrastructure Rollback

If infrastructure changes caused the issue:

1. **Review Infrastructure Changes**
   - Identify what infrastructure changes were made
   - Determine if they can be safely reverted

2. **Revert Infrastructure Changes**
   - Rollback Docker compose changes
   - Revert Kubernetes manifests if applicable
   - Restore previous configuration files
   - Restart affected services

3. **Validate Infrastructure**
   - Check that all services are running with previous configuration
   - Verify network connectivity and ports
   - Confirm resource allocations are correct

### Phase 3: Validation

1. **Smoke Testing**
   - Verify core functionality works
   - Check key user flows
   - Confirm API endpoints respond correctly

2. **Performance Validation**
   - Ensure latency is within acceptable ranges
   - Verify cache hit rates are normal
   - Check for any performance regressions

3. **Monitoring & Alerting**
   - Confirm monitoring systems are receiving data
   - Verify alerting thresholds are appropriate
   - Check for any new error patterns

4. **User Validation (if applicable)**
   - Have QA or power users validate key functionality
   - Gather feedback on any remaining issues

### Phase 4: Post-Rollback Activities

1. **Document the Incident**
   - Write detailed post-mortem of what happened
   - Document rollback procedure effectiveness
   - Identify root cause and prevention measures

2. **Update Knowledge Base**
   - Add lessons learned to team wiki
   - Update runbooks if procedures need improvement
   - Share findings with wider team

3. **Plan for Re-deployment**
   - Fix issues identified in rollback analysis
   - Test fixes thoroughly in staging
   - Schedule re-deployment after confidence is restored

## Specific Rollback Scenarios

### Scenario 1: High Latency / Timeout Issues

If latency exceeds 3s P95 after deployment:
1. Check if new feature flags caused performance regression
2. Rollback application code to previous version
3. Verify latency returns to acceptable levels
4. Investigate performance cause in isolated environment

### Scenario 2: Faithfulness Score Drop

If Self-RAG/CoVe verification score drops below 0.8:
1. Check if prompt or retrieval changes caused regression
2. Rollback RAG pipeline changes
3. Verify faithfulness score recovers
4. Prompt engineering team investigates root cause

### Scenario 3: Security Vulnerability Discovered

If critical security issue is found in deployment:
1. Immediately block external access if needed
2. Rollback to last known secure version
3. Apply security patch to codebase
4. Re-deploy with vulnerability fixed

### Scenario 4: Database Connection Failures

If application cannot connect to databases:
1. Verify database infrastructure is healthy
2. Check network connectivity and security groups
3. Rollback any recent infrastructure changes
4. Validate connection strings and credentials

### Scenario 5: Cache Storm / Cache Penetration

If semantic cache is causing issues:
1. Temporarily disable semantic cache via feature flag
2. Monitor if issue resolves
3. Rollback cache-related changes if needed
4. Investigate cache warming and TTL strategies

## Rollback Verification Checklist

After rollback, verify:
- [ ] Application version matches previous stable version
- [ ] All services report healthy status
- [ ] Core functionality works (chat, ingestion, etc.)
- [ ] Performance metrics are within acceptable ranges
- [ ] No error spikes in logs
- [ ] Monitoring and alerting systems are functional
- [ ] Security controls are working correctly
- [ ] Data integrity is preserved (if applicable)
- [ ] User-facing features work as expected

## Emergency Procedures

### Complete Site Outage

If the entire site is down:
1. Check infrastructure health (servers, network, load balancer)
2. Verify Docker daemon is running on all hosts
3. Check if containers are crashing and restart if needed
4. Rollback to last known good infrastructure state
5. Contact infrastructure provider if underlying issue

### Data Loss Incident

If data corruption or loss is suspected:
1. Immediately stop all writes to prevent further damage
2. Isolate affected databases
3. Verify most recent clean backup
4. Restore from backup if data loss is confirmed
5. Application rollback to version that existed at backup time
6. Engage data recovery specialists if needed

## Communication Plan

During rollback:
- Internal: Use designated Slack channel or video bridge
- Status Updates: Every 15 minutes during active rollback
- Stakeholders: Engineering lead provides updates to product/management
- Users: Status page updates if user impact expected
- Post-Incident: Detailed report within 24 hours

## Aborting Rollback

Only abort rollback if:
- New information shows rollback would worsen situation
- Critical data would be lost by proceeding
- Infrastructure damage would occur
- Approved by incident commander and tech lead

If aborting:
1. Clearly communicate decision to all stakeholders
2. Document reasons for aborting
3. Prepare alternative mitigation strategy
4. Continue monitoring and investigation

## Testing the Rollback Plan

This plan should be tested:
- Quarterly as part of disaster recovery drills
- Before major releases
- When infrastructure or deployment processes change
- After any modifications to rollback procedures

Maintain a rollback test environment that mirrors production for validation.

---

**Remember**: The goal of rollback is to restore service stability and availability as quickly as possible while preserving data integrity. Always prioritize user experience and system reliability.