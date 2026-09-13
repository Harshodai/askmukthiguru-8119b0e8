# Service Level Objectives (SLOs)

Single source of truth for AskMukthiGuru SLOs. Alerting rules in `infrastructure/prometheus/alerting-rules.yml` implement the burn-rate policy below.

## SLOs

| # | Objective | SLI (measurement) | Target | Error budget (30d) |
|---|-----------|-------------------|--------|--------------------|
| 1 | Chat answer delivered fast (per-tier) | p95 `slo_latency_seconds` by `tier` (see tier table) | per-tier p95 (fast 1s / standard 3s / hindi 12s / cold 25s / comparative 65s / deep·fallback 30s) | 5% slow-request budget per tier |
| 2 | Readiness | `health_check_total{result="ready"}` share of /api/health probes | 99.5% | 3.6h |
| 3 | Reliability | 5xx share of `guru_requests_total` | < 0.1% | 43m |

## Per-tier latency SLOs (A3 — replaces the retired single 8s SLO)

Measured distribution: `backend/benchmarks/reports/isolated_latency_2026-09-06.json`
(n=35). Single-threshold 8s hid fast-path headroom and guaranteed Hindi /
comparative breach. Thresholds are p95 targets per `tier` label on
`SLO_CHAT_LATENCY` (`slo_latency_seconds`), implemented as `SLO_THRESHOLDS` in
`backend/app/metrics.py` and observed via `observe_slo_latency()` at the
whole-request wall-time point (`PipelineCoordinator.execute`, cache-hit
patched). Prometheus pattern per tier (Google SRE multi-tier + multi-window
burn-rate): good =
`sum(rate(slo_latency_seconds_bucket{tier="<t>",le="<th>"}[W]))`,
total = `sum(rate(slo_latency_seconds_count{tier="<t>"}[W]))`,
error-rate = `(total − good) / total`; page at 2× burn (1h + 5m), ticket at
1× burn (6h + 30m). Histogram buckets
`[0.5,1,2,3,4,8,12,20,25,30,65]` contain every tier boundary; `le="8.0"`
is retained for alert-rule continuity during migration.

| tier | p95 target | Basis (isolated_latency_2026-09-06.json) |
|------|-----------|-------------------------------------------|
| `fast` | < 1s | casual 0.02–0.03 (n=3), distress 0.02–0.10 (n=3), meditation 0.04–0.08 (n=3), off-topic 0.03 (n=3); p100 0.10s → 1s headroom |
| `standard` | < 3s | doctrine-direct warm 1.48–2.08 (7/8 warm reps), doctrine-colloquial warm 1.8/2.78 |
| `hindi` | < 12s | hindi 9.65/10.08/10.79 (p100 10.79s) |
| `cold` | < 25s | doctrine-direct cold 15.65, doctrine-colloquial cold 7.59, four-secrets 1.58/3.49/20.93, multi-teacher 5.7–9.41 |
| `comparative` | < 65s | comparative 14.67/15.38/64.74 (p100 64.74s) |
| `deep`, `fallback` | < 30s | legacy long-tail cap (unchanged behavior) |

- **SLO 1 measurement:** `SLO_CHAT_LATENCY` histogram (`slo_latency_seconds`),
  observed via `observe_slo_latency(tier, seconds)` in `backend/app/metrics.py`
  at `pipeline_coordinator.py` on every pipeline completion (cache-hit latency
  patched to real elapsed time), labeled by route tier. Per-tier thresholds in
  `SLO_THRESHOLDS`; unknown tiers normalize to `standard`.
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

### Latency Burn-Rate Math (SLO 1, per tier; legacy 8s retired)
- **Objective (example — fast tier):** 95% of `tier="fast"` requests complete
  in < 1.0s (error budget = 5% exceeding 1.0s). Same formula per tier with its
  own `le` boundary from the tier table.
- **Good requests (fast):** `slo_latency_seconds_bucket{tier="fast",le="1.0"}`
- **Total requests (fast):** `slo_latency_seconds_count{tier="fast"}`
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