# Smoke Load Test — How to Run + Acceptance Criteria

**Scope:** light smoke (~50 RPS, 2 min) per user direction. Not a stress/soak test.

## Run

```bash
export PROJECT_REF=fynkjimvuimakgtidvuq
export ANON_KEY=eyJhbGciOi...     # publishable anon key from src/integrations/supabase/client.ts
export TEST_USER_JWT=...          # optional, real signed-in user JWT for chat-rate-limit phase
./scripts/benchmarks/smoke.sh
```

Output files land in `docs/load-test-output/`.

## Acceptance criteria

| Phase | Metric | Target |
| --- | --- | --- |
| `/healthz` warmup | HTTP 200 on every call | yes |
| `/healthz` sustained | error rate | < 1% |
| `/healthz` sustained | p95 latency | < 500 ms |
| `/healthz` sustained | p99 latency | < 1500 ms |
| `chat-rate-limit` burst | first ~20 reqs | 200 (token bucket full) |
| `chat-rate-limit` burst | remaining reqs | 429 (Retry-After header set) |
| `chat-rate-limit` burst | non-(200/429) responses | 0 |

## Interpreting the `hey` report

```
Summary:
  Total:        120.0042 secs
  Slowest:      0.6213 secs
  Fastest:      0.0421 secs
  Average:      0.1187 secs
  Requests/sec: 50.01
Status code distribution:
  [200]  6001 responses
Latency distribution:
  50% in 0.1051 secs
  95% in 0.2812 secs
  99% in 0.4533 secs
```

If p95 > 500 ms repeatedly:
1. Check `supabase--db_health` — is connection pool saturated?
2. Check `supabase--edge_function_logs healthz` for cold-start spikes.
3. Reduce `/healthz` work (fewer dependency probes per call).

If 5xx > 1%:
- Inspect logs via `supabase edge_function_logs healthz` + check WAL/disk pressure.

## Why this is "enough"

50 RPS × 120 s = 6 000 invocations — sufficient to (a) prove cold-start spikes are gone after the first 1-2 hits, (b) expose any per-user token-bucket lock contention, (c) catch regressions in CI before each deploy. It is **not** a substitute for a real load test (k6 with 500 VUs over 30 min) before a major launch.

## README badge

Already added — green/red pill driven by latest `/healthz` response. If you want a richer "uptime over 30 days" badge, point UptimeRobot at `https://fynkjimvuimakgtidvuq.supabase.co/functions/v1/healthz` and embed their SVG.
