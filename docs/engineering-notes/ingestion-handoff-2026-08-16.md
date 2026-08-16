# Ingestion run handoff — 2026-08-16

Full-corpus reingestion in progress (20 YouTube playlists,
`spiritual_wisdom_contextual` collection, `max_accuracy=true`). Prior session
hit its cost cap mid-run — this doc is the handoff so a fresh agent can pick
up monitoring/fixing without re-deriving context.

## What's already done (commits on `main`, all pushed + deployed)

1. `51bdae15` — Celery worker concurrency was hardcoded to `--concurrency=1` in
   `backend/start_railway.py`, serializing every queued job. Fixed to read
   `CELERY_CONCURRENCY` env var, default `2`. **Confirmed live**: celery-worker
   boot log shows `concurrency: 2 (prefork)`.
2. `51bdae15` — Hierarchical parent-child chunking + RAPTOR parent-summaries in
   `backend/ingest/pipeline.py` were gated behind `max_accuracy`; now
   unconditional (only Sarvam STT diarization stays gated). Preserves YouTube
   `[t=XXs]` timestamp markers through the hierarchical split.
3. `51bdae15` — New `POST /api/ingest/upload` (multipart PDF) + `ingest_document_task`,
   and a "Re-ingest Four Sacred Secrets Book" button wired to the
   pre-existing-but-unwired `POST /api/admin/ingest/book` endpoint. Both in the
   admin Ingestion tab (`src/admin/pages/IngestionPage.tsx`). **Not yet usable
   live** — needs a Lovable "Publish" click (see Pending below).
4. `026ba515` — Two content-loss bugs found via live celery-worker logs during
   this run:
   - `ingest_playlist` never accepted/propagated `max_accuracy` to its
     per-video `orchestrate_ingestion` chord tasks — every playlist video
     silently ran at the task's own default (`True`) regardless of the admin
     UI toggle. Now threaded through (`app/api/ingest.py` → `ingest_playlist`
     → `orchestrate_ingestion` kwargs).
   - `_ingest_video`: `max_accuracy=True` disables auto-captions
     (`allow_auto=not max_accuracy`), and Railway's yt-dlp audio fallback is
     broken (see Known issue below) — videos with only auto-captions were
     being lost outright. Now retries with `max_accuracy=False` (admits
     auto-captions) as a last resort before giving up.
5. `f7025ff4` — Same content-loss fix applied to `_ingest_video_enhanced`
   (the Sarvam-diarization path), which had the identical bug.

All of the above are deployed to both Railway services
(`askmukthiguru-8119b0e8` and `celery-worker`). The backend deploy's Railway
CLI status label showed "Deploy failed" but its own deploy logs show a clean
boot and live 200s including `/api/health` — treat that label as a known CLI
display flake, not a real failure, unless fresh logs say otherwise.

## Known issue — NOT fixed, root cause only mitigated

Railway's `celery-worker` container's yt-dlp cannot download audio:
`ERROR: [youtube] <id>: Sign in to confirm you're not a bot` plus
`No supported JavaScript runtime could be found` (no `deno` in the image).
This breaks the Tier-4 Whisper/audio-fallback path entirely on Railway.
Item 4 above stops this from losing videos outright (falls back to
auto-captions), but any video with **zero** captions of any kind (manual or
auto) will still fail — nothing can be done for those without fixing yt-dlp's
environment (install a JS runtime in `backend/Dockerfile.railway`, and/or
configure yt-dlp cookies to dodge the bot-block). Out of scope for this
session; worth a dedicated pass if failure volume stays high.

## Pending — needs a human click, not something an agent can do

**Lovable frontend publish.** `git push` only syncs the Lovable editor; the
live site at `askmukthiguru.lovable.app` needs a manual "Publish" click in the
Lovable UI before the PDF-upload control and "Re-ingest Book" button (item 3
above) actually appear. Ask the user to publish, then the book can be
re-ingested through the UI the same way the 20 playlists were submitted.

## How to check status (commands, not tools — any LLM/CLI session can run these)

```bash
# Railway CLI — needs PATH export first on this machine:
export PATH="$HOME/.docker/bin:$PATH"

railway status                                    # service health at a glance
railway logs --service celery-worker | tail -100   # live worker activity
railway logs --service celery-worker | grep -iE "error|failed|traceback" | tail -60
railway logs --service askmukthiguru-8119b0e8 | tail -60
```

Signal that ingestion is actively progressing (not stuck): new
`ForkPoolWorker-N` process numbers appearing over time in celery-worker logs
(workers recycle every 10 tasks per `worker_max_tasks_per_child=10` in
`backend/celery_config.py`), each one re-loading the embedding model and
compiling the LangGraph pipelines. That startup sequence per task is expected
overhead, not a hang.

To check via the admin dashboard instead (needs a real login + completed AAL2
MFA step-up — see "Auth state" below):
`https://askmukthiguru.lovable.app/admin/ingestion` — Runs table shows
completed jobs; TOTAL RUNS / OK / PARTIAL / FAILED counters update as chord
callbacks (`playlist_complete` task) land. "Active Jobs" panel is
client-side-only state and does *not* persist across a page reload — its
being empty after a refresh does not mean nothing is running.

## Auth state (for whoever drives the browser next)

Admin account (`kharshaengineer@gmail.com`) has TOTP MFA enrolled and
verified as of this session — AAL2 step-up works. If a fresh browser session
needs to re-authenticate: Google OAuth login → may redirect to
`/profile?tab=settings` for an MFA challenge (not re-enrollment, unless the
factor was removed) → then `/admin` is reachable directly.

## Playlist source list (for reference / re-submission if a job needs a retry)

All 20 URLs are in `scripts/ingestion/bulk_ingest_async.py::PLAYLIST_URLS`
(repo root). Submit via the admin Ingestion tab's "Content URL" field with
"Max accuracy mode" toggled on, or `POST /api/ingest` with
`{"url": "<playlist_url>", "max_accuracy": true, "tags": ["general"]}`
(needs an AAL2 admin bearer token — the endpoint is `require_aal2`-gated, no
bypass).

## What NOT to do

- Don't flip `settings.raptor_parent_summaries_enabled` or re-add the
  `max_accuracy` gate around hierarchical chunking — that was the fix, not a
  bug.
- Don't raise `CELERY_CONCURRENCY` past 2 without checking memory headroom
  first — each worker process loads its own copy of the embedding/reranker
  models (prefork pool), and the celery-worker service caps at 12GB
  (`PYTHON_MEMORY_LIMIT_MB=12288`).
- Don't try to extract the browser's Supabase auth token via injected
  JavaScript to bypass the UI — the sandbox's security classifier blocks this
  pattern (session-token extraction) regardless of intent. Drive the UI
  through normal clicks/typing instead.
