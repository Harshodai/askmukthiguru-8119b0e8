# Railway Deployment Checklist

## Environment Variables

Set these in Railway dashboard for **both** `askmukthiguru-8119b0e8` and `celery-worker`:

| Variable | Required | Source |
|----------|----------|--------|
| `WEBSHARE_PROXY_URL` | Recommended | webshare.io free tier (10 residential proxies) |
| `YOUTUBE_COOKIES_B64` | Optional | Export cookies.txt from logged-in YouTube, base64-encode |
| `YOUTUBE_COOKIES_FILE` | Optional | Path to cookies.txt inside container |
| `SUPADATA_API_KEY` | Optional | supadata.ai free tier (100 req/month) |
| `REDIS_URL` | Required | Railway Redis add-on |
| `SUPABASE_URL` | Required | Supabase project |
| `SUPABASE_KEY` | Required | Supabase service_role key |
| `IS_PRODUCTION` | Required | `true` |

## Services

| Service | Image | Port | Health |
|---------|-------|------|--------|
| `askmukthiguru-8119b0e8` | Dockerfile.railway | 8000 | `/api/healthz` |
| `celery-worker` | Dockerfile.railway (SERVICE_TYPE=celery) | — | Celery ping |
| Redis | railway/internal | 6379 | — |
| Qdrant | railway/internal | 6333 | — |
| Neo4j | Template | 7687 | — |

## Worker Config

- Concurrency: 2 (CPU-bound Whisper tasks)
- Queues: `embedding,indexing,ingestion,okf`
- Max tasks per child: 50 (prevents memory leak)
- Visibility timeout: 3600s (set in `celery_config.py`)

## First Deploy

```bash
railway link --project resilient-embrace --service askmukthiguru-8119b0e8
railway up
```

## Verification

```bash
curl https://api.askmukthiguru.com/api/healthz
# → {"status":"healthy",...}
curl -H "Authorization: Bearer <admin_jwt>" \
  https://api.askmukthiguru.com/api/ingest/status/<task_id>
# → {"task_id":"...","status":"SUCCESS","progress":100,...}
```
