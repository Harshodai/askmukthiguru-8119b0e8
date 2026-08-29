# On-Call Runbook

Solo-operator on-call policy for AskMukthiGuru (Railway production).

## Schedule

- **Primary on-call:** the maintainer (solo operator), 24/7.
- **Escalation:** if no acknowledgment within the SLA, escalate to the listed emergency contact in `CREDENTIALS_GUIDE.md` (owner's phone).
- **Acknowledge SLA:** 30 minutes for `page` severity, 4 hours for `warn`. Acknowledgment = reply in the alert channel ("acknowledging") OR open the incident in the incident log.

## Escalation tree

1. Pager fires (Slack/PagerDuty/webhook) → acknowledge within 30 min.
2. Diagnose (see ALERTING.md → linked runbook for the alert).
3. ✗ resolved within 1h → announce "noise / resolved" and close.
4. ✗ within 4h or data-loss risk → **call the owner directly** (number in CREDENTIALS_GUIDE.md). Do not wait for the next alert cycle.
5. Sev-1 (user data exposure or full outage) → start `docs/INCIDENT_RESPONSE.md` immediately; the runbook takes priority over this schedule.

## Tools & Infrastructure

### Active Production Observability (Railway)
| Tool | Where | Access | Purpose |
|------|-------|--------|---------|
| Railway Dashboard | `railway.app/dashboard` | Owner account | Container CPU, memory, deployment status |
| Streaming Logs | `railway logs` (CLI, linked service) | Owner account | Live stdout/stderr audit lines (`AUDIT <method> <path> -> <status>`) |
| Health Probes | `GET /api/health`, `/api/healthz` | Public | Real-time readiness check across all subsystems |
| Metrics Endpoint | `GET /api/metrics` | Admin auth (AAL2) | Prometheus text metrics including latency & error counters |

### Aspirational / Staging Alerting Pipeline
The repository provides a complete Prometheus + Alertmanager stack configured in `infrastructure/prometheus/`:
- **Alerting Rules (`infrastructure/prometheus/alerting-rules.yml`):** Evaluates multi-window burn rates and readiness/error rate thresholds against Prometheus metrics.
- **Alertmanager (`infrastructure/prometheus/alertmanager.yml`):** Routes `page` alerts to PagerDuty/webhooks and `warn` alerts to Slack (`#alerts`).
- **Grafana (`infrastructure/grafana/`):** Pre-provisioned dashboards for visual analytics.
- **Local/Staging Testing:** Run `docker compose up -d prometheus alertmanager` to simulate or test alerts locally.

## SLO Burn-Rate Rules Summary

Alerting thresholds follow the multi-window multi-burn-rate standard defined in `docs/SLO.md`:

1. **SLO 1: Chat Latency (p95 < 8s)**
   - `ChatLatencySLOPage` (**page**): >2× burn rate (>10% latency violations on `slo_latency_seconds_bucket{le="8.0"}`) across 1h (long) and 5m (short) windows (`for: 2m`).
   - `ChatLatencySLOHigh` (warn): p95 latency > 8s sustained for 6h.
2. **SLO 2: Readiness (> 99.5%)**
   - `HealthReadySLOPage` (**page**): `not_ready` probe rate > 0.5% over 15m window.
3. **SLO 3: Reliability (5xx < 0.1%)**
   - `FiveXXRateSLOPage` (**page**): 5xx error rate > 0.1% over 30m window.
   - `FiveXXRateElevated` (warn): 5xx error rate > 0.05% sustained for 1h.

## Acknowledge protocol

1. Name the alert in the channel.
2. Capture the time + the alert name in `docs/runbooks/INCIDENT_LOG.md` (append-only).
3. Follow the linked runbook in `docs/runbooks/ALERTING.md`.
4. When resolved: annotate the incident log with root cause + follow-up issue link. No follow-up → file one.