# Data Retention Runbook

Source of truth for retention windows and purge scheduling. Executor: `backend/scripts/ops/cleanup_inactive_user_data.py`.

## Retention windows

| Tier | Data | Window | Purge condition |
| ---- | ---- | ------ | --------------- |
| Tier 1 | Redis session/ephemeral keys (`session:*`, `ephemeral:*`) | 24h idle | `OBJECT IDLETIME >= 86400` |
| Tier 2 | Telemetry tables (see below) | 90d | `created_at < now() - 90d` |
| Tier 3 | Qdrant user memory vectors | 365d | user inactive (`profiles.last_active_at < now() - 365d`) **AND** point stale (`updated_at < cutoff`) |
| Orphans | `guru_session_summaries` with NULL `user_id` | 30d | `user_id IS NULL AND created_at < now() - 30d` |

## Telemetry tables (90d)

`chat_queries`, `chat_responses`, `retrieval_events`, `trace_spans`, `trigger_events`, `safety_events`, `app_logs`, `token_usage`, `router_decisions`.

Overrides: `TELEMETRY_RETENTION_DAYS` (module constant), `--days-telemetry`, `--days-inactivity` CLI flags.

## Scheduling

Run nightly. Local: cron; Railway: job/service cron `0 3 * * *`. Always schedule `--dry-run` first and review output before LIVE PURGE.

## Dry run

```bash
cd backend
.env/bin/python scripts/ops/cleanup_inactive_user_data.py --dry-run
```

## Verification

1. Confirm counts printed per table/collection.
2. Spot-check a purged table: `SELECT count(*) FROM chat_responses WHERE created_at < now() - interval '90 days';` → 0.
3. Confirm protected data untouched: user profiles, `user_brain_nodes`, `second_brain_vault`, `guru_memories`.

## Troubleshooting

- Supabase query fails → script falls back to point-level cleanup (stale-by-`updated_at` only); verify RLS/service key permissions.
- Qdrant scroll fails → cleanup skipped for that collection; check `QDRANT_URL`/`QDRANT_API_KEY`.
- Redis unreachable → Redis cleanup skipped, rest continues.