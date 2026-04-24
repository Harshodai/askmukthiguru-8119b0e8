# Alerts

## Pre-seeded rules

| Name | Condition | Window |
|---|---|---|
| Hallucination rate >15% | `hallucination_rate > 0.15` | 60 min |
| p95 latency >5s | `p95_latency_ms > 5000` | 30 min |
| Error rate >2% | `error_rate > 0.02` | 60 min |
| Cost burn >$5/h | `cost_burn_usd > 5` | 60 min |
| Retrieval hit rate <80% | `retrieval_hit_rate < 0.80` | 120 min |

## Evaluator pseudocode

```ts
for each active rule:
  value = computeMetric(rule.metric, window=rule.window_minutes)
  if compare(value, rule.comparator, rule.threshold):
    if no open event for this rule:
      insert alert_events (rule_id, value, fired_at=now())
      dispatchChannel(rule.channel, rule.target, rule, value)
  else:
    update alert_events set resolved_at=now()
      where rule_id=rule.id and resolved_at is null
```

Run every 60s from `/api/public/cron/alerts` (HMAC-protected).

## Channel adapters

- **email** — Resend or SendGrid
- **webhook** — POST JSON to `target`
- **slack** — Slack incoming webhook URL in `target`

Each adapter receives `{ rule, value, fired_at }`.
