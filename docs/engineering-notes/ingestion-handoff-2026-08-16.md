# Ingestion run handoff — 2026-08-16

## TL;DR for the next agent (read this first)

- **Two jobs vanished without a trace** (`efe9bcdf-...` and `4fca8b01-...`,
  both the `BMJrDu-folk` test video, submitted at different points). Neither
  ever appears in `railway logs --service celery-worker | grep -i
  <job_id>`, not even a "received" line. Both submissions happened shortly
  before/during a celery-worker redeploy (I redeployed it several times this
  session for other fixes). **This looks like task loss on worker
  restart, not a content/logic bug** — `task_acks_late=True` in
  `backend/celery_config.py` is supposed to redeliver unacked tasks after a
  worker dies, so this shouldn't happen. Worth investigating directly:
  is `broker_transport_options={"visibility_timeout": 3600}` (1h) simply too
  long for redelivery to kick in during this session's testing window, or is
  something else swallowing the task? **Don't redeploy celery-worker
  immediately after submitting a test job** — wait for it to actually
  complete first, or you'll reproduce this.
- **OpenRouter model fix status: inconclusive, not confirmed either way.**
  No new 404s seen in the current log window, but no confirmed *successful*
  completion either — the window only showed 2 tasks "received", still
  in-flight (model loading), nothing has reached the LLM-call stage yet in
  view. Needs a longer/re-check.
- **Transcript quality (raw, pre-Railway-cleaning) — inspected directly,
  genuinely decent.** Refetched `BMJrDu-folk` locally via
  `1_fetch_transcripts_local.py` and read the full 9324-char output
  (auto-captions). Content is real, substantive, on-topic spiritual teaching
  (presence/past-mind/future-mind material, consistent with this project's
  Preethaji/Krishnaji corpus). Rough edges expected of auto-captions:
  `[music]` tags scattered inline, filler words preserved verbatim ("uh",
  "um"), occasional run-on/repeated phrasing, no punctuation restoration, no
  `[t=XXs]` timestamp markers (this local-fetch path is deliberately
  lighter-weight than the full `_ingest_video` pipeline — timestamps only get
  added by `chunk_youtube_transcript`, which this script doesn't call).
  **This raw text depends on Railway's `_corrector.correct_transcript()`
  LLM step to clean it up** — which uses the same `OPENROUTER_GENERATION_MODEL`
  that was 404ing. If that's still broken, uploaded transcripts will index
  with the filler words/artifacts intact rather than getting cleaned.

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

## OPENROUTER_GENERATION_MODEL 404 — biggest single finding, fixed live (no commit, Railway env var)

**This was silently killing almost every video in the run, independent of
the yt-dlp issue.** Live celery logs showed every successfully-transcribed
video getting auto-rejected:

```
Content rejected by Data Quality Gate: score 40/100. Reasons: QUALITY_UNKNOWN:
LLM scoring unavailable: Client error '404 Not Found' for url
'https://openrouter.ai/api/v1/chat/completions'
OpenRouter call failed during correction (model=meta-llama/llama-3.3-70b-instruct:free)
```

Root cause: `meta-llama/llama-3.3-70b-instruct:free` no longer exists in
OpenRouter's catalog — confirmed via `curl -s https://openrouter.ai/api/v1/models`,
the `:free` tier of that model was discontinued (the paid
`meta-llama/llama-3.3-70b-instruct`, no `:free` suffix, still exists, but
that costs money — against this project's $0-budget rule). Every call using
this model 404s: transcript correction, quality scoring, and — since
`OPENROUTER_GENERATION_MODEL` is very likely the same var driving live chat
answer generation, not just ingestion — **possibly live chat too**.

**Fix applied**: `railway variable set "OPENROUTER_GENERATION_MODEL=openai/gpt-oss-20b:free" --service <name>`
on both `askmukthiguru-8119b0e8` and `celery-worker` (confirmed present in
OpenRouter's live catalog, Apache-2.0, general-purpose 20B instruction model).
Both services auto-rebuilt on the var change.

**Next agent — verify, don't assume**:
1. `railway logs --service celery-worker | grep -i "openrouter.ai/api/v1/chat/completions"` —
   confirm no more 404s, and no NEW errors with the replacement model.
2. Re-check a video that was previously rejected (any playlist video ID from
   the "0 chunks" pattern in earlier logs) or the `BMJrDu-folk` test video —
   does it now get `chunks_indexed > 0` and `status: success` instead of
   `status: rejected`?
3. **Spot-check live chat is not broken**: send a real message through the
   chat UI (not admin), confirm a real generated answer comes back — not an
   error, not a fallback/degraded response. If `OPENROUTER_GENERATION_MODEL`
   really is shared with the chat path, this bug may have been live in
   production chat, not just ingestion — worth confirming and flagging to the
   user with urgency if so.
4. Also worth checking `OPENROUTER_GENERATION_MODEL_FALLBACK=google/gemini-2.5-flash`
   (found while investigating, not touched) — a fallback var exists but the
   404s weren't caught by it, meaning the failover logic either isn't wired to
   this specific call site or isn't triggering on 404s specifically. Not
   chased further this session — worth checking `services/model_failover.py`
   / wherever `OPENROUTER_GENERATION_MODEL_FALLBACK` is actually read, if any.

## youtube-transcript-api proxy gap — found, NOT fixable by an agent

Separate from yt-dlp's bot-block: `youtube-transcript-api` (used for Tier-1/2
manual+auto caption fetch, `ingest/youtube_loader.py:_fetch_youtube_captions_api`)
is also subject to YouTube blocking/rate-limiting requests from cloud/datacenter
IPs (confirmed via web search — this is a known, common failure mode for any
server-hosted use of this library, distinct from bot-block and from PoToken
requirements). The codebase already has proxy support wired:
`_apply_proxy()` in `ingest/youtube_loader.py` reads `WEBSHARE_PROXY_URL` and
sets `HTTP_PROXY`/`HTTPS_PROXY` — **but no such variable is set on Railway**
(confirmed via `railway variable list --service celery-worker --kv | grep -i proxy`,
empty). This is likely why more videos than expected fall through to the
broken Tier-3/4 yt-dlp path in the first place, instead of succeeding cleanly
at Tier-1/2 captions.

**This needs a Webshare (or equivalent) proxy account — signup and payment
info, something only the user can do, not fixable by an agent.** If the user
sets one up: set `WEBSHARE_PROXY_URL` on both Railway services, no code
change needed, `_apply_proxy()` already picks it up.

## Split-pipeline architecture — local transcript fetch, Railway does the rest (TWO PHASES)

Built this session as a workaround for both IP-block problems above: fetch
transcripts from a residential IP (bypasses the whole class of
datacenter-IP-block problems), then separately upload the raw text to
Railway for everything downstream (chunk, embed, Qdrant, RAPTOR, LightRAG,
OKF) — which already works fine there, the blocking only happens on the
fetch step.

**Deliberately two separate phases/scripts, not one combined script** — the
user explicitly asked for this after an initial combined version, and it's a
real improvement: fetching 20 playlists can take a long time, and a Supabase
admin token expires in ~1h, so gating the whole fetch run on a live token was
fragile. Splitting means Phase 1 needs no token at all; only the fast Phase 2
(upload) does.

**Explicitly NOT using Apify** (`scripts/ingestion/extract_transcripts.py`,
a pre-existing paid-third-party-API transcript extractor already in this
repo) — user's explicit instruction. Kept as a flag/reference only: the new
scripts' output `.md` format deliberately matches `extract_transcripts.py`'s
`write_md()` format (`# Title`, `**Video ID:**`, `**URL:**`, `## Transcript`)
so either tool's output is interchangeable with Phase 2's uploader, but the
new scripts use `youtube_transcript_api` — $0, no third-party account needed
(matches the project's $0-budget rule; Apify is small-but-nonzero cost and
needs a signup/token).

**New pieces:**
- `POST /api/ingest/raw-text` (`backend/app/api/ingest.py`) — admin-only
  (`require_aal2`), takes `{text, source_url, title, tags, max_accuracy}`
  JSON, dispatches the same `ingest_document_task` the PDF-upload feature
  uses. The receiving end, lives on Railway.
- `scripts/ingestion/1_fetch_transcripts_local.py` — **Phase 1**. No admin
  token needed. Expands playlists via a flat `yt-dlp` extract (metadata
  only, no download), fetches manual-then-auto captions via
  `youtube_transcript_api`, writes one `.md` file per video to
  `scripts/ingestion/transcripts/` (gitignored). Resumable — skips videos
  that already have a `.md` file.
- `scripts/ingestion/2_upload_transcripts_to_railway.py` — **Phase 2**. Reads
  every `.md` in `scripts/ingestion/transcripts/`, parses out video_id/url/
  title/transcript text, POSTs each to `/api/ingest/raw-text`. Resumable via
  `scripts/ingestion/upload_state.json` (gitignored).
- `scripts/ingestion/Dockerfile.local-fetch` + `requirements-local-fetch.txt`
  — one minimal image (no ML/DB deps, just yt-dlp + youtube-transcript-api +
  httpx) runs either phase by passing the script name as the docker command.

**Verified this session** (both bare-Python and Docker):
- `docker build -f scripts/ingestion/Dockerfile.local-fetch -t mg-local-fetch scripts/ingestion/` — succeeds.
- Phase 1 actually fetched the real `BMJrDu-folk` transcript (9324 chars, auto-captions) both via bare Python (`backend/.venv/bin/python3 scripts/ingestion/1_fetch_transcripts_local.py --url ...`) and inside the Docker container with a mounted volume — both wrote a correctly-formatted `.md` file, and the resume-skip logic correctly detected the already-fetched file on a second run.
- Phase 2's `parse_transcript_md()` correctly extracted video_id/url/title/text back out of that real fetched file (verified via direct function call — the actual upload POST was NOT tested, no admin token available in this sandbox).
- **Not yet verified**: the full fetch → upload → Railway `/api/ingest/raw-text` → `ingest_document_task` → Qdrant round trip, and whether it actually runs successfully from the *user's actual home machine* (this session's sandbox network worked, which is a good sign but not the same environment).

**How the user runs it:**
```bash
# Phase 1 — no token needed, run from anywhere:
python3 scripts/ingestion/1_fetch_transcripts_local.py --limit 3   # test 3 videos first
# ...or via Docker:
docker build -f scripts/ingestion/Dockerfile.local-fetch -t mg-local-fetch scripts/ingestion/
docker run --rm -v "$(pwd)/scripts/ingestion:/data" mg-local-fetch \
  1_fetch_transcripts_local.py --limit 3

# Once transcripts/ looks right, get an admin token (expires ~1h, re-copy if
# stale): log into askmukthiguru.lovable.app as admin, DevTools ->
# Application -> Local Storage -> "sb-<project-ref>-auth-token" key -> copy
# the "access_token" field out of that JSON value.
export MUKTHI_ADMIN_TOKEN="<paste it>"

# Phase 2 — upload:
python3 scripts/ingestion/2_upload_transcripts_to_railway.py --limit 3
# ...or via Docker:
docker run --rm -e MUKTHI_ADMIN_TOKEN -v "$(pwd)/scripts/ingestion:/data" mg-local-fetch \
  2_upload_transcripts_to_railway.py --limit 3

# Once both test batches look right in the admin dashboard, drop --limit on
# Phase 1 to fetch the full 20 playlists, then run Phase 2 (no --limit) to
# upload everything. Both phases are safe to re-run/interrupt.
```

**Next agent**: check the actual upload round trip once the user has run
Phase 2 for real — `railway logs --service celery-worker | grep -i
"<video_id>"` the same way as the rest of this doc.

## yt-dlp bot-block / JS-runtime fix (commit `173d6abb`, deployed)

Root cause found via web search + code audit: `youtube_loader.py`'s
Python-API yt-dlp calls already carry `_get_js_runtime_opts()` /
`_get_cookies_opts()` and multi-client player spoofing (`android`,
`android_vr`, `tv_simply`, `tv_embedded`, `mweb`, `web`, `ios`) — but
`ingest/audio_transcriber.py::download_audio_stream` (the Tier-4 Whisper
fallback, invoked via a raw `yt-dlp` CLI subprocess) had none of that
hardening. `nodejs` is already installed in `backend/Dockerfile.railway`
(`apt-get install ... nodejs`) — yt-dlp just wasn't told to use it (it only
probes `deno` by default). Ported the same `--js-runtimes`,
`--extractor-args player_client=...`, and cookie-passthrough hardening to
this call site. No Dockerfile change needed — reused what was already
installed.

**Status: deployed, not yet confirmed effective.** New celery-worker booted
at `08:59:25` (hostname `c0f200be2a38`, concurrency:2) with this fix. No
bot-block errors seen in the ~30s since, but that's too short to conclude
anything — the fix needs to actually reach a Tier-4 audio-download attempt to
prove out. **Next agent: grep celery-worker logs after this timestamp for
`Sign in to confirm` / `Audio download failed` / `Council: Both sources
failed` — if those are gone, the fix worked; if they persist, YouTube's
IP-reputation-based bot-block on Railway's datacenter IP is bigger than
client-spoofing can beat, and the real fix is `YOUTUBE_COOKIES_B64` (base64
a real `cookies.txt` exported from an authenticated browser session, set as
a Railway env var — `_get_cookies_opts()` in `youtube_loader.py` already
reads it, this is the one missing piece and needs a human to export cookies,
not something an agent can source itself).**

Regardless: any video with **zero** captions of any kind (manual or auto)
will still fail — nothing can be done for those short of cookies working.

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

# Verify the yt-dlp bot-block fix (see section above) actually worked:
railway logs --service celery-worker | grep -iE "Sign in to confirm|Audio download failed|Council: Both sources failed" | tail -20
```

Note on `railway status`: this session repeatedly saw it label a deploy
"Deploy failed" immediately after `railway up`, while the deploy's own build
+ deploy logs showed a clean build, successful healthcheck, and live traffic
being served. Confirmed at least twice by checking `railway logs -b
<deployment-id>` and the boot banner in `railway logs --service <name>` after
waiting ~1-2 min — the label appears to be a CLI/dashboard display lag, not a
real failure, but ALWAYS verify against actual logs (new boot banner /
`concurrency:` line / fresh `ForkPoolWorker` hostname) rather than trusting
the status label at face value.

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
