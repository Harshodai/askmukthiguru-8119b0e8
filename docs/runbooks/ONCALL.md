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

## Tools

| Tool | Where | Access |
|------|-------|--------|
| Railway dashboard | `railway.app/dashboard` | Owner account |
| Logs | `railway logs` (CLI, linked service) | Owner account |
| Metrics | Prometheus/Grafana (local stack) or `GET /api/metrics` (AAL2) | Admin auth |
| Health | `GET /api/health` (public) | Public |

## Acknowledge protocol

1. Name the alert in the channel.
2. Capture the time + the alert name in `docs/runbooks/INCIDENT_LOG.md` (append-only).
3. Follow the linked runbook.
4. When resolved: annotate the incident log with root cause + follow-up issue link. No follow-up → file one.