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

## Burn-rate policy & Alerting Rules

Alerting rules defined in `infrastructure/prometheus/alerting-rules.yml` follow standard multi-window multi-burn-rate alerting principles (Google SRE standard) to minimize false positives and alert quickly on significant error budget consumption:

| Alert | Window | Burn Rate | Condition | Severity |
|-------|--------|-----------|-----------|----------|
| `ChatLatencySLOPage` | 1h (long) & 5m (short) | 2× | Latency error rate > 10% on `slo_latency_seconds_bucket{le="8.0"}` | **page** |
| `ChatLatencySLOHigh` | 6h | 1× | Latency p95 > 8s (sustained slow burn) | warn |
| `HealthReadySLOPage` | 15m | - | `result="not_ready"` > 0.5% of probes | **page** |
| `FiveXXRateSLOPage` | 30m | 1× | 5xx share > 0.1% | **page** |
| `FiveXXRateElevated` | 1h | 0.5× | 5xx share > 0.05% | warn |

### Latency Burn-Rate Math (SLO 1)
- **Objective:** 95% of chat requests complete in < 8.0s (error budget = 5% of requests exceeding 8.0s).
- **Good requests:** `slo_latency_seconds_bucket{le="8.0"}`
- **Total requests:** `slo_latency_seconds_count`
- **Error Rate calculation:**
  $$\text{ErrorRate} = \frac{\text{rate}(\text{slo\_latency\_seconds\_count}[W]) - \text{rate}(\text{slo\_latency\_seconds\_bucket}\{le="8.0"\}[W])}{\text{rate}(\text{slo\_latency\_seconds\_count}[W]) + 10^{-9}}$$
- **2× Burn Rate Trigger:** $\text{ErrorRate} > 0.10$ (10% of requests exceeding 8s) simultaneously across a 1-hour long window and a 5-minute short window (`for: 2m`).

## Active vs. Aspirational Alerting Infrastructure

To ensure clear operational ownership, the alerting landscape is categorized into active production components and aspirational/staging components:

### 1. Active Production Infrastructure (Railway Cloud)
- **Health & Readiness Monitoring:** Direct HTTP polling on `/api/health` and `/api/healthz` (ready/degraded/error state).
- **Platform Telemetry:** Railway native container metrics (CPU, RAM, network) and real-time streaming logs (`railway logs`).
- **Application Metrics API:** Prometheus-formatted metric exports exposed at `/api/metrics` (protected by AAL2 / admin authentication).
- **Incident Protocol:** Solo-operator triage via `docs/runbooks/ONCALL.md` and manual log analysis.

### 2. Aspirational / Staging Observability Stack
- **Prometheus Server:** Dedicated daemon scraping `/metrics` defined in `infrastructure/prometheus/prometheus.yml`.
- **Prometheus Alerting Engine:** Real-time evaluation of `infrastructure/prometheus/alerting-rules.yml`.
- **Alertmanager Routing:** PagerDuty (`page` severity) and Slack (`warn` severity) dispatchers in `infrastructure/prometheus/alertmanager.yml`.
- **Grafana Dashboards:** Pre-provisioned visual telemetry in `infrastructure/grafana/`.
- **Synthetic Testing:** Staging validation via Docker Compose (`docker compose up -d prometheus alertmanager`) to test rule triggers against injected faults.

## Exclusions

- Health-check endpoints (`/api/health`, `/api/healthz`) are excluded from `guru_requests_total` (audit middleware skip list) so monitoring traffic cannot drag the 5xx SLO.
- SLO 3 counts only requests that reach the app (audit middleware); platform-level 5xx (Railway LB) are out of scope and surfaced by Railway's own monitoring.

## Review cadence

- **Monthly:** SLO attainment review (Prometheus `slo` recording rules or Grafana dashboard) + alert tuning (quarterly at minimum).
- **Quarterly:** full capacity + SLO review (see also `docs/runbooks/CAPACITY.md` when it exists — P1-OPS-7 writes it).