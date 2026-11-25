# Data Retention Runbook

Source of truth for retention windows and purge scheduling. The machine-readable inventory is
[`docs/operations/memory-plane-inventory.json`](../operations/memory-plane-inventory.json).
The scheduled executor is `backend/tasks/retention_tasks.py`, which delegates to
`scripts/ops/cleanup_inactive_user_data.py` and the compliance/launch-subscriber services.

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

The production scheduler is Celery Beat task
`tasks.retention_tasks.cleanup_retention_data`, every 86,400 seconds, consumed by the
`celery` queue. The direct cleanup script remains an operator-invoked dry-run/live-purge
tool; do not schedule it alongside Beat or the same rows may be processed twice.
`corpus_gate_rejections` is never purged automatically (X40: rejections must stay recorded).

## Dry run

```bash
cd backend
.venv/bin/python scripts/ops/cleanup_inactive_user_data.py          # dry run (default)
.venv/bin/python scripts/ops/cleanup_inactive_user_data.py --apply  # live purge
```

## Verification

1. Confirm the per-surface result keys from the task or the counts printed per table/collection.
2. Spot-check a purged table: `SELECT count(*) FROM chat_responses WHERE created_at < now() - interval '90 days';` → 0.
3. Confirm protected data untouched: user profiles, `user_brain_nodes`, `second_brain_vault`, `guru_memories`.

## Troubleshooting

- Supabase query fails → script falls back to point-level cleanup (stale-by-`updated_at` only); verify RLS/service key permissions.
- Qdrant scroll fails → cleanup skipped for that collection; check `QDRANT_URL`/`QDRANT_API_KEY`.
- Redis unreachable → Redis cleanup skipped, rest continues.
