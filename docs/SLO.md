# Service Level Objectives (SLOs)

Single source of truth for AskMukthiGuru SLOs. Alerting rules in `infrastructure/prometheus/alerting-rules.yml` implement the burn-rate policy below.

## SLOs

| # | Objective | SLI (measurement) | Target | Error budget (30d) |
|---|-----------|-------------------|--------|--------------------|
| 1 | Chat answer delivered fast | p95 `slo_latency_seconds` (chat end-to-end, all tiers) | p95 < 8s | 12h |
| 2 | Readiness | `health_check_total{result="ready"}` share of /api/health probes | 99.5% | 3.6h |
| 3 | Reliability | 5xx share of `guru_requests_total` | < 0.1% | 43m |

- **SLO 1 measurement:** `SLO_CHAT_LATENCY` histogram, observed at `pipeline_coordinator.py` on every non-cached pipeline completion, labeled by route tier.
- **SLO 2 measurement:** `HEALTH_CHECK_TOTAL` counter, incremented in `app/api/health.py` on every `/api/health` probe (startup + result).
- **SLO 3 measurement:** `guru_requests_total{status="5xx"}` — the audit middleware (`app/middleware/audit.py`) increments `REQUEST_COUNT` by HTTP status class (`2xx/4xx/5xx`) for every request outside the skip list.

## Burn-rate policy

| Multi-window | Condition | Alert |
|--------------|-----------|-------|
| 2× over 1h equivalent | budget exhausted in 1h | **page** |
| 1× over 6h equivalent | sustained slow-burn | warn |

Implementation: `histogram_quantile` ratio rules (SLO 1) and share-of-total rules (SLO 2/3) in `alerting-rules.yml`.

## Exclusions

- Health-check endpoints (`/api/health`, `/api/healthz`) are excluded from `guru_requests_total` (audit middleware skip list) so monitoring traffic cannot drag the 5xx SLO.
- SLO 3 counts only requests that reach the app (audit middleware); platform-level 5xx (Railway LB) are out of scope and surfaced by Railway's own monitoring.

## Review cadence

- **Monthly:** SLO attainment review (Prometheus `slo` recording rules or Grafana dashboard) + alert tuning (quarterly at minimum).
- **Quarterly:** full capacity + SLO review (see also `docs/runbooks/CAPACITY.md` when it exists — P1-OPS-7 writes it).