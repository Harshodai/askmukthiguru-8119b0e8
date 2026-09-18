# Track E — Ruthless Production-Readiness Audit
Phases 10 (Attachments/OCR/Whisper), 11 (LLM Providers/Failover), 15 (Docker/Deployment)

Date: 2026-09-18. Environment: Docker Compose local-prod stack (backend, qdrant, memgraph, redis, autoheal), backend/.venv for local scripts. `LLM_PROVIDER=openrouter` live.

---

## Phase 10 — Attachments / OCR / Whisper

**Status: PASS with minor findings.**

### What was checked
- `backend/app/chat_uploads.py` — the ephemeral extraction module used by the end-user chat upload endpoint.
- `backend/app/api/chat.py:57` — `POST /api/chat/upload`, the end-user-facing upload endpoint.
- `backend/app/api/speech.py:82` — `POST /api/speech/stt`, end-user-facing audio upload for speech-to-text.
- `backend/app/api/ingest.py:362` — admin/ingestion-only file upload (separate risk profile, not tested here; requires admin auth via `get_current_user_from_supabase`, never `get_optional_user`).
- `backend/app/api/support.py:43` — support-ticket attachments (not deep-tested; same ephemeral bounded pattern as chat_uploads visible at a glance).
- `src/lib/chat/transport.ts` confirms `/api/chat/upload` is genuinely wired into the end-user chat UI, not just an admin tool.

### End-user vs admin/ingestion — confirmed split
- **End-user-facing** (anonymous-allowed, ephemeral, NOT persisted/indexed): `/api/chat/upload`, `/api/speech/stt`. Both explicitly documented in code as bounded and non-persistent — `chat_uploads.py`'s docstring: "Uploads are deliberately converted to bounded evidence text and are not persisted or indexed."
- **Admin/ingestion-only** (persists to Qdrant/Memgraph corpus, different risk class): `app/api/ingest.py`, `ingest-ui/`. Not exercised in this pass — out of scope per task framing, but worth noting it is where a bad upload could actually pollute the doctrine corpus, unlike the chat path.

### Live tests run against `/api/chat/upload` (real HTTP calls, localhost:8000)
| Test | Result | Evidence |
|---|---|---|
| Normal small text file | 200, extracted correctly | `status=text`, context populated |
| Oversized file (11MB, cap is 10MB/file) | **413** "Each attachment must be 10MB or smaller." | Enforced twice: declared `upload.size` check AND a bounded `read(MAX_SINGLE_BYTES+1)` re-check (belt-and-braces against a lying Content-Length) |
| Malformed image (`.png` extension, garbage bytes, declared `image/png`) | 200, `status=ocr_timeout` | See finding AMK-E-004 below — this is the wrong outcome, not the right one |
| Unsupported type (`.exe`, arbitrary binary) | 200, `status=unsupported_type`, no extraction attempted, returned only as evidence metadata | Correct — no crash, no attempted-parse-as-something-else |
| Empty file | **422** "Empty attachments are not supported." | Enforced at the endpoint before `extract_chat_attachments` runs |
| >5 files in one request | 413 (code-verified, not re-tested live — `len(files) > 5` guard at `chat.py:76`) | Static check |
| Duplicate upload (same file twice) | No dedup, no caching — by design (ephemeral, stateless) | Each call independently hashes/extracts; nothing persists between calls so "duplicate" has no special meaning here |

### Size / MIME validation
- MIME is **sniffed from magic bytes** (`_sniff_mime`), not trusted from the client's declared `Content-Type` — PDF/PNG/JPEG/GIF/WEBP/OOXML signatures checked explicitly; only falls back to the declared type for the audio/video/text extension classes where no magic-byte discriminator was implemented. This is a reasonable, deliberate trust boundary — the code does not accept "trust me it's an image" at face value for the formats that matter most (documents).
- Size caps are enforced **before** the body is fully buffered where it matters: `speech.py`'s STT endpoint explicitly documents the ordering rationale (declared-size check → content-type check → bounded read of `MAX+1` bytes → post-read size check) specifically to avoid buffering a hostile 30MB body into memory before rejecting it (comment cites this as "P1-BE-8", a prior finding that was fixed).

### Storage / cleanup
- Every temp file created by `extract_chat_attachment` (`tempfile.NamedTemporaryFile(..., delete=False)`) is unlinked in a `finally:` block (`app/chat_uploads.py:248-253`), including on the exception paths for office-doc extraction. Verified by code read — this is correct.
- No uploaded file content is written anywhere durable on the chat path: everything lives in-process as `bytes`, gets a bounded temp file only for tools that need a filesystem path (pdftotext, zipfile, OCR, Whisper), and that temp file is deleted immediately after. `retention_seconds: 900` in the response is metadata describing the caller's own client-side retention contract (frontend), not a server-side TTL the backend enforces — nothing server-side needs to expire because nothing server-side persists.
- Could not directly inspect `/tmp` inside the running container (`docker exec` is blocked by this environment's permission policy — every `docker exec` invocation, even `whoami`, was denied outright; `docker top`/`docker inspect`/`docker stats`/`docker logs`/`docker kill` all worked). This is recorded as **UNKNOWN (tooling-blocked)**, not a pass — the `finally:` cleanup is verified by code reading and by the fact that memory/disk did not visibly grow across the test burst, but a live `find /tmp -newer <marker>` check inside the container could not be performed.

### OCR / Whisper failure handling
- **Timeouts are wall-clock bounded**: `_OCR_TIMEOUT_SECONDS = 30`, `_TRANSCRIPTION_TIMEOUT_SECONDS = 60`, both enforced via `asyncio.wait_for`. The code comment explicitly documents why: "a crafted small file... could take far longer to process than its byte size suggests... neither OCR nor Whisper transcription had a wall-clock bound... (audit P1-06, 2026-08-25)" — i.e. this was already found and fixed in a prior audit pass.
- Whole-endpoint outer timeout: `asyncio.wait_for(extract_chat_attachments(...), timeout=45.0)` at `chat.py:92` — even if per-file timeouts somehow didn't fire, the endpoint itself is capped at 45s and returns HTTP 408 on expiry.
- Concurrency is bounded: `_ATTACHMENT_EXTRACTION_SEMAPHORE = asyncio.Semaphore(2)` (`chat.py:54`) — only 2 concurrent extraction jobs process-wide, which caps worst-case memory/CPU blast radius from concurrent hostile uploads.

### AMK-E-004 — Malformed image does not fail fast; consumes the full OCR timeout
Severity: LOW
Launch Blocker: NO
Evidence: Live test — POSTing a file named `bad.png`, declared `image/png`, containing `b"NOTAPNGCONTENT" * 100` (1400 bytes of non-image garbage) to `/api/chat/upload` returned `status=200`, `status: "ocr_timeout"` after the full 30s OCR budget was consumed, rather than a fast decode-failure rejection.
Root Cause: `_extract_media_text` (`app/chat_uploads.py:157-170`) hands the file straight to `ocr_service.extract_text_from_file(path)` inside `asyncio.wait_for(..., timeout=30)`. There is no upfront "can this even be decoded as an image" check (e.g. `PIL.Image.open(...).verify()`) before committing the full OCR budget — the underlying OCR library apparently hangs/retries on unparseable input rather than raising promptly.
User Impact: A single malformed image makes that one request take ~30s to return instead of instantly. Not a crash and not unbounded (still time- and concurrency-bounded by the semaphore(2) + 45s endpoint timeout), so it degrades gracefully rather than failing catastrophically — but it is a real latency/DoS-amplification surface: 2 concurrent bad-image uploads occupy both extraction slots for 30s each, queueing every other user's legitimate upload behind them.
Required Fix: Add a fast pre-check (image header/magic-byte validation, or `PIL.Image.verify()`) before invoking OCR, so a non-decodable image fails in milliseconds with `status="invalid_image"` instead of riding out the full timeout.
Regression Test: Extend `backend/tests/test_chat_uploads.py` with a case asserting a garbage-bytes `.png` returns in well under 1s with a specific failure status, not `ocr_timeout`.
Verification: Re-run the same malformed-image POST and confirm sub-second response with a distinct status code/field.

### AMK-E-005 — No server-side visibility into `/tmp` cleanup (tooling gap, not a code gap)
Severity: LOW
Launch Blocker: NO
Evidence: `docker exec mukthiguru-backend <anything>` was denied by this environment's permission policy on every attempt (including `whoami`, `find /tmp`), so the `finally: os.unlink(temp_path)` cleanup path in `app/chat_uploads.py:249-253` could not be verified by direct filesystem inspection inside the container, only by static code read.
Root Cause: Environment/tooling restriction in this audit session, not an application defect.
User Impact: None directly — this is an audit-coverage gap, recorded as UNKNOWN rather than PASS.
Required Fix: N/A for this codebase; a future audit pass with `docker exec` access should run `find /tmp -type f -newer <marker>` before/after an upload burst to close this gap definitively.
Regression Test: N/A.
Verification: N/A.

---

## Phase 11 — LLM Providers / Failover

**Status: PASS — with the root CLAUDE.md's "failover removed" claim CONFIRMED, and extended further than documented.**

### What was checked
- `backend/services/llm_factory.py`, `services/openrouter_service.py` (1443 lines — this is the only LLM service class that matters; it's the live provider), `services/sarvam_service.py`, `services/ollama_service.py`, `services/llm/*` (Strategy-pattern adapters), `services/model_failover.py`, `services/multi_provider_llm.py`, `services/sarvam_failover.py`.
- `app/container.py` (the actual composition root — NOT `app/dependencies.py`, which is a much smaller 133-line file; `app/dependencies.py` re-exports `ServiceContainer` but the real `_build_llm_services()` wiring lives in `app/container.py:182-234`).
- Live tests: direct HTTP call to OpenRouter with a garbage API key; static trace of the exception-handling path through `rag/nodes/generation.py` → `app/pipeline/stages/stage_runner.py` → `app/services/job_queue.py` → `app/api/job_routes.py` to see what a real end user ultimately receives.

### Does cross-provider failover genuinely exist on the live chat path? **NO — confirmed, and the dead code is more extensive than the CLAUDE.md note describes.**

The root CLAUDE.md says: *"Cross-provider failover via NIM was removed per security audit... `failover_provider.py` remains as a module but is no longer instantiated in the container."*

Verified directly:
- `services/failover_provider.py` **does not exist in this repo at all** (`find . -iname failover_provider.py` returns nothing) — the file was apparently deleted entirely at some point after that note was written, not merely "left uninstantiated." The CLAUDE.md claim is stale in its specifics but directionally correct (no NIM failover fires).
- However, `app/container.py:215-230` **does** build and wire three other cross-provider-failover-shaped objects that the CLAUDE.md note doesn't mention:
  - `self.multi_provider_llm = get_multi_provider_llm()` (`services/multi_provider_llm.py`) — a real Sarvam→OpenRouter failover router with circuit breakers and token-bucket rate limiting per provider.
  - `self.model_registry = SarvamFailoverService(self.ollama._service, self.krutrim)` (when not on the Ollama provider path) — wraps the primary LLM with Krutrim as a fallback on any exception.
  - Both are constructed at container-build time (real init cost, real background wiring) but were confirmed via `grep -rn '\.model_registry\b'` and `grep -rn 'multi_provider_llm'` across `app/`, `rag/`, `services/` to have **zero consumers anywhere in the request-serving code path** — the only other reference to `multi_provider_llm` is `services/transcript_polisher.py` (an offline ingest tool), matching that module's own docstring: *"Only used by offline ingest tooling (OKF extraction, transcript polishing), not the chat path."*
- The actual live generation path (`rag/nodes/generation.py:2517`, `_generate_with(ollama, ...)`) calls `provider.generate(...)` on the single `LLMProviderFactory`-created provider (`OpenRouterProvider` wrapping `OpenRouterService`, since `LLM_PROVIDER=openrouter`). There is no fallback to a second provider anywhere in this call chain.

**Conclusion: cross-provider failover is dead weight in the container — built, wired, costs init time, but unreachable from any real request.** This is a stronger finding than the CLAUDE.md note: not just "NIM failover removed," but "three separate failover-shaped objects (`multi_provider_llm`, `model_registry`/`SarvamFailoverService`) exist fully wired and functional in isolation, yet are orphaned from the chat path entirely." Recorded as AMK-E-001.

### What DOES exist: real, bounded, within-provider resilience in `OpenRouterService`
This is genuinely well-built and was verified by both code read and a live test:
- **Bounded retries**: `tenacity.AsyncRetrying(stop=stop_after_attempt(self._max_retries), wait=wait_exponential_jitter(initial=1, max=8, jitter=1))`. `settings.llm_max_retries=2` (from `.env`/config default). Not infinite — confirmed by reading `_call_api` (`services/openrouter_service.py:504-518`).
- **429 handling is deliberately NOT retried at the same model** (`_is_retryable_openrouter_error` explicitly excludes 429 — comment: "the quota that's exhausted doesn't refill that fast"). Instead, on 429/5xx/connection-error/malformed-payload, it does a **same-provider, different-model fallback**: `deepseek/deepseek-chat` → `meta-llama/llama-3.3-70b-instruct` (`self._gen_model_fallback`), explicitly a "different rate-limit bucket." This is real, working, single-retry model-level failover — confirmed by reading `_call_api` lines 627-648.
- **Circuit breaker**: `CircuitBreakerConfig.from_provider("openrouter")`, default `failure_threshold=5`, `recovery_timeout=90.0` (`services/circuit_breaker.py:60-61`). Opens after 5 consecutive non-429 failures; while open, further calls short-circuit immediately to a canned graceful-degradation string (standalone path) or raise `CircuitOpenException` (strict-gateway path) rather than hammering a down provider.
- **Rate limiting is Redis-backed and cross-process/cross-replica** (`RedisBackedRateLimiter`), with documented history of why: a 2026-08-27 finding that per-instance rate limiting under-counted real aggregate traffic because ~53 `OpenRouterService` instances get created during a single ingestion run.

### Live test: invalid API key
Performed a direct HTTP call to `https://openrouter.ai/api/v1/chat/completions` with a garbage bearer token (bypassing the app to isolate provider behavior, since mutating the running container's live `.env` key was out of scope for a read-mostly audit):
```
STATUS 401
{"error":{"message":"User not found.","code":401}}
```
Traced how `_call_api`'s exception classifier (`services/openrouter_service.py:610-660`) handles this:
- `is_rate_limit` = False (not 429), `is_server_error` = False (not ≥500), `is_connection_error` = False (not a timeout/connect error), `is_malformed_payload` = False.
- **But** `_is_retryable_openrouter_error` (used by the `tenacity` retry predicate) returns `True` for *any* `httpx.HTTPError` except 429 — and `httpx.HTTPStatusError` (which 401 raises) is an `HTTPError` subclass. So **a 401 IS retried** up to `max_retries=2` times with exponential-jitter backoff (~1-8s per attempt) before finally exhausting retries.
- After retries exhaust, none of the `has_fallback`/graceful-degradation branches match (401 isn't in the handled-reasons list), so it falls to the final `else`: `self._circuit.record_failure(); raise`. **The raw exception propagates** rather than returning the friendly canned message that 429/5xx/timeout get.

### AMK-E-002 — Invalid API key wastes ~2-9s on futile retries, then leaks a raw exception to the end user instead of a friendly message
Severity: MEDIUM
Launch Blocker: NO
Evidence: `services/openrouter_service.py:30-32` (`_is_retryable_openrouter_error`) classifies any non-429 `httpx.HTTPError` as retryable, which includes 401 (bad/revoked credentials) — a condition retrying can never fix. Confirmed by code trace plus a live 401 response captured directly from OpenRouter's API (see above). The exception then propagates un-caught through `rag/nodes/generation.py:2517` (`_generate_with`, no try/except at the call site) → `app/pipeline/stages/stage_runner.py:158` (re-raises after telemetry) → `app/services/job_queue.py:410-412` (`except Exception as exc: return {"error": str(exc)}`) → `app/api/job_routes.py:41` (`return job`, the raw dict including that `error` string, unsanitized) for a polling client, or → `app/api/chat.py:642` (`raise HTTPException(status_code=500, detail=job.get("error", ...))`) for a `?wait=true` synchronous caller.
Root Cause: (1) The retry predicate doesn't distinguish "will never succeed" (401/403/400) from "might succeed on retry" (5xx/timeout) — only 429 gets special-cased out. (2) The exception-classification block in `_call_api`'s `except` clause only has friendly-degradation branches for `is_rate_limit`/`is_server_error`/`is_connection_error`/`is_malformed_payload` — a 401/403/400 falls through to a bare `raise`, which every other 429/5xx path avoids by design. (3) The final error surface (`job.get("error")` / `HTTPException(..., detail=job.get("error"))`) passes the raw `str(exc)` through with no sanitization or user-friendly wrapping.
User Impact: If the OpenRouter API key is ever revoked, rotated incorrectly, or hits an account-level block, every chat request takes several extra seconds of pointless retrying, then returns either a raw Python/httpx exception string as the visible error (via the `?wait=true` 500 path or the job-status poll response) instead of the same "I'm experiencing a temporary connectivity issue, please try again" message that a rate-limit or timeout gets. This is a real UX inconsistency and a (minor) internal-detail leak, not a crash or hang.
Required Fix: (1) Add explicit handling for 401/403 in `_is_retryable_openrouter_error` (return `False`, same as 429). (2) Add a branch in `_call_api`'s exception handler for auth-class errors (401/403) that routes to `_graceful_degradation` like the other transient-failure classes, rather than falling through to bare `raise`. (3) Separately, sanitize `job["error"]` before it reaches `job_routes.py`'s `return job` or `chat.py`'s `HTTPException(detail=...)` — return a generic message to the client and log the raw exception server-side only.
Regression Test: Unit test mocking a 401 response from the OpenRouter client and asserting (a) no retry attempts occur, (b) `generate()` returns the graceful-degradation string rather than raising.
Verification: Point the service at a deliberately invalid key in a test/staging environment and confirm a chat request returns the friendly degradation message within ~1s, not a multi-second delay followed by a raw exception.

### What happens if OpenRouter is entirely unreachable (all "providers" down, since there's effectively one)
Traced, not directly reproduced (would require severing the container's egress, out of scope for a non-destructive network test): a connection/timeout error is `is_connection_error=True` in `_call_api`'s classifier, which — with no `fallback_model` remaining after the first fallback attempt, or immediately if `_is_fallback_attempt` — returns `_graceful_degradation(...)`'s canned string rather than raising. So a full-outage scenario is the **best-handled** case: the user gets a clear, friendly "temporary connectivity issue" message, not a hang or a 500. This is confirmed by code read of `_call_api` lines 616-656 and is consistent with the circuit-breaker's own short-circuit behavior once `failure_threshold=5` is crossed.

### Observability
- Every OpenRouter call logs structured `OPENROUTER_HTTP_TIMING` / `OPENROUTER_CALL_TIMING` / `OPENROUTER_CALL_ERROR_TIMING` lines with model, operation, attempt count, elapsed ms, and error type (`services/openrouter_service.py:494-606`) — a provider failure is visible in logs, not silent.
- Circuit breaker state changes are registered with `get_circuit_breaker_registry()`, which is provider-agnostic and presumably surfaced via `/api/health` (the live `/api/health` response captured during this audit shows an `llm: {ok:true, latency_ms:256, critical:true}` entry — confirms LLM health is part of the readiness probe).
- Cost control: `OpenRouterBudgetGuard` (`app/openrouter_budget.py`, referenced at `services/openrouter_service.py:412` `reservation = await self._budget_guard.reserve()`) plus `OPENROUTER_DAILY_BUDGET_USD` / `OPENROUTER_MONTHLY_BUDGET_USD` / `OPENROUTER_MAX_REQUEST_COST_USD` / `OPENROUTER_BUDGET_GUARD_ENABLED` / `OPENROUTER_BUDGET_FAIL_CLOSED` env vars (`backend/docker-compose.yml:236-240`) — a real spend cap exists, not just an aspiration. Not independently load-tested in this pass (would require driving real spend).

### AMK-E-003 — Dead failover machinery wired into the container adds real startup cost for zero live benefit
Severity: LOW
Launch Blocker: NO
Evidence: `app/container.py:215-230` constructs `MultiProviderLLMService` (opens an `aiohttp.ClientSession` lazily, registers 3 circuit breakers, 3 token-bucket rate limiters) and `SarvamFailoverService` at every container build, confirmed to have zero consumers on the request-serving path (see above).
Root Cause: Left over from an architecture where Sarvam Cloud was the live provider and cross-provider failover mattered more; not removed when OpenRouter became the sole live provider (2026-09-12 per root CLAUDE.md).
User Impact: None functionally (it's genuinely inert on the chat path) — this is a code-hygiene/startup-cost finding, not a correctness or safety one.
Required Fix: Either wire `multi_provider_llm`/`model_registry` into the actual generation path as real cross-provider failover (a product decision, not just a code fix), or remove them from `container.py`'s eager-build path to stop paying their init cost for nothing.
Regression Test: N/A (removal) or an integration test proving the wired failover actually engages on a simulated OpenRouter outage (addition).
Verification: `grep` confirms zero call sites after the change, or a live failover demonstration if wired in for real.

---

## Phase 15 — Docker / Production Deployment

**Status: PASS — core workflow survives a hard kill and recovers automatically, but recovery time is longer than the Dockerfile's own health-check tuning implies, and is worth knowing before an on-call engineer assumes "it'll bounce back in seconds."**

### BUILD → START → HEALTH (baseline, confirmed at audit start)
`docker compose ps` showed all 5 services (`backend`, `qdrant`, `memgraph`, `redis`, `autoheal`) `Up ... (healthy)` before any testing began.

### Dockerfile analysis (`backend/Dockerfile`)
- **Non-root at runtime, confirmed live**: image declares `USER root` (needed so the entrypoint can `chown` mounted volumes), but `docker-entrypoint.sh` execs `gosu appuser python -m uvicorn ...` (single-worker path) or `gosu appuser gunicorn ...` (multi-worker path) to drop privileges before starting the app. **Verified live** via `docker top mukthiguru-backend` (couldn't use `docker exec whoami` — see below): the running `python -m uvicorn app.main:app` process has `UID 1000`, i.e. `appuser`, not root. `docker inspect --format '{{.Config.User}}'` alone would have been misleading (shows `root`, the image-declared default) — the entrypoint's runtime privilege drop is what actually matters and it works.
- **No secrets baked into image layers**: `HF_TOKEN` is passed via `RUN --mount=type=secret,id=hf_token,...` (BuildKit secret mount), explicitly not `ARG`/`ENV`, with a comment explaining this is deliberate ("keeps HF_TOKEN out of the image layers entirely... extractable via `docker history`"). All other provider API keys (`OPENROUTER_API_KEY`, `SARVAM_API_KEY`, etc.) are runtime env vars from `.env`/compose, never `ARG`/baked into the Dockerfile. Not independently verified with `docker history` in this pass (would be a good follow-up) but the Dockerfile's own mechanism is sound.
- **Health check defined at two layers with different tuning — a real drift, not just cosmetic**: the `Dockerfile`'s own `HEALTHCHECK` directive uses `--start-period=420s --retries=8` (comment: "long start period for ML model download/loading"), but `backend/docker-compose.yml`'s `backend.healthcheck` block **overrides** it with `start_period: 180s`, `retries: 10`. Docker Compose's `healthcheck:` key fully replaces the image's built-in `HEALTHCHECK` when both are present — so the actually-enforced `start_period` in this stack is 180s, not the 420s the Dockerfile author intended for a genuinely cold model download. See AMK-E-006.
- **Graceful shutdown**: `exec gosu ...` / `exec gunicorn ...` (not backgrounded, not wrapped in a script that would eat the signal) means SIGTERM reaches the actual server process directly, not a shell wrapper — this is correct Docker signal-handling practice. `gunicorn` is invoked with `--graceful-timeout 60`, giving in-flight requests up to 60s to finish before a hard stop. Not independently load-tested (would need an in-flight long-running request during a `docker stop`), but the configuration is correct by inspection.

### Kill test — the actual "kill the backend and watch it recover" exercise
```
docker kill mukthiguru-backend        # hard SIGKILL, not graceful
```
Measured via polling `docker inspect --format '{{.State.Status}}'` / `{{.State.Health.Status}}` every 3s:

| t (elapsed) | container status | health |
|---|---|---|
| 0s–89s | `exited` | `unhealthy` |
| 92s | `running` | `starting` |
| 92s–116s | `running` | `starting` |
| **120s** | `running` | **`healthy`** |

Cross-checked against `docker inspect` timestamps: `FinishedAt=09:30:08.69Z`, `StartedAt=09:31:50.13Z` — **~101 seconds between the container dying and Docker's `restart: unless-stopped` policy actually starting it again.** After restart, it took another ~30s to pass health checks (models re-warm: embedding warm-up, semantic router warm-up, LangGraph strategy compilation for STANDARD/DEEP graphs — all visible in `docker logs` as INFO lines completing within a few seconds each, so the 30s is mostly FastAPI lifespan + model load, not a hang).

**Post-recovery end-to-end verification**: issued a real `POST /api/auth/anon-session` → `POST /api/chat?wait=true` with `"What is the Beautiful State?"` immediately after health turned green. Got `200` with a full grounded answer and a citation (`youtube.com/watch?v=x-mTRlE0TC4`) — **the core user workflow works correctly after a hard-kill recovery**, not just the health endpoint.

**No corruption observed**: `docker logs` post-restart shows `"JobQueue: started 5 workers, recovered 0/0 pending jobs"` — clean state, no orphaned/stuck jobs (expected, since no job was mid-flight at kill time; a job genuinely in-flight during a hard kill would be lost, not corrupted-and-retried, per the Redis-backed queue's design — the reservation is only committed via `_claim_anon_quota` on success, so a killed-mid-job request's quota reservation would simply never be released either, which is its own minor finding but not tested live here since it requires precise timing of the kill against a slow generation).

### AMK-E-006 — `docker-compose.yml`'s health-check `start_period` (180s) is shorter than the Dockerfile's own documented intent (420s), and a real kill-recovery cycle took ~120s total
Severity: MEDIUM
Launch Blocker: NO
Evidence: `backend/Dockerfile:86-87` sets `--start-period=420s` with an explicit comment ("long start period for ML model download/loading"); `backend/docker-compose.yml`'s `backend.healthcheck` block (confirmed at compose-file line ~275 in this checkout) sets `start_period: 180s`. Docker Compose's `healthcheck:` stanza overrides the image's baked-in `HEALTHCHECK` entirely when both exist, so 180s — not 420s — is what's actually enforced when running via `docker compose up`. Live-measured kill-to-healthy time in this pass was 120s (with models already warm/cached from a prior run, i.e. the *best case* — no fresh HF download needed).
Root Cause: The compose file's healthcheck block was authored (or edited) independently of the Dockerfile's, and the two were never reconciled. On a genuinely cold start (fresh volumes, no cached HF models — e.g. after a `docker volume rm` or on a brand-new host), the Dockerfile author clearly expected downloads could take up to 420s; the compose override gives only 180s before Docker starts counting health-check retries, and only 180s + (10 retries × 30s interval) = ~480s total before Compose would consider it permanently unhealthy. This is close enough to marginal that a slow/cold model download on a resource-constrained host could plausibly blow through it.
User Impact: On a genuinely fresh deployment (new host, empty volumes) rather than a warm restart, the container could be marked "unhealthy" by Compose/orchestration tooling before model loading actually finishes, potentially triggering unwanted intervention (an orchestrator killing/replacing a container that was about to become healthy on its own) — this was not reproduced live in this pass (the audit's kill-test was a warm restart with cached models, not a from-scratch build), so it is a **plausible risk identified by config inspection, not a directly observed failure**.
Required Fix: Reconcile the two health-check definitions — either remove `docker-compose.yml`'s override (letting the image's own `HEALTHCHECK` govern) or raise the compose `start_period` to match the Dockerfile's 420s. Pick one source of truth and delete the other to prevent future drift.
Regression Test: A from-scratch `docker compose build --no-cache && docker compose up` timing test (deliberately clearing `hf_model_cache` volume first) measuring actual first-healthy time against the configured `start_period`.
Verification: After the fix, confirm `docker inspect backend --format '{{json .Config.Healthcheck}}'` (post-compose-up) shows the intended `start_period`, not the shorter one.

### AMK-E-007 — Hard-kill recovery takes ~2 minutes end-to-end on a single-replica deployment; no fast-path exists
Severity: MEDIUM
Launch Blocker: NO
Evidence: Live-measured: `docker kill` → ~101s before Docker's `restart: unless-stopped` policy actually restarted the container → ~19s more to `running`+`health: starting` → ~30s more to `health: healthy`. Total ≈120s of complete backend unavailability. `mukthiguru-autoheal` (the `willfarrell/autoheal` sidecar) only intervenes on containers Docker reports as `unhealthy` while still *running* — a container that has fully `exited` (as this one was for the first ~101s) is outside autoheal's purview; only Compose's own `restart: unless-stopped` policy governs the exited→restarting transition, and that policy applies its own internal backoff.
Root Cause: Single replica (`railway.json`/deployment docs elsewhere in this repo confirm "1 replica" is the deliberate production topology), combined with Docker's restart-policy backoff after a container has died. With one replica and no fast standby, any hard crash (OOM-kill, unhandled panic, `docker kill`, a bad deploy) means ~2 minutes of total outage before recovery, not seconds.
User Impact: Matches the documented SPOF/Replication policy in `backend/CLAUDE.md` — the repo's own 1k-tier SLA target is "RTO < 15 min," so 2 minutes is well within the *documented* target. This is not a launch blocker under the repo's own stated SLA, but it is worth an operator knowing concretely: a hard backend crash is a real ~2-minute full outage today, not a sub-second blip, and there is no load balancer or second replica to absorb it.
Required Fix: None required to meet the documented 1k-tier SLA (RTO < 15 min is comfortably met). If tighter recovery is ever wanted, the 10k-tier policy in `backend/CLAUDE.md`'s SPOF table (multi-replica, causal cluster) is the documented next step — not needed now.
Regression Test: Re-run this same kill-test periodically (e.g. quarterly or before major releases) to confirm recovery time hasn't regressed further, especially if `WEB_CONCURRENCY`/replica count changes.
Verification: N/A — informational/confirmatory finding, current behavior already meets the documented SLA.

### Memory headroom
| Container | Usage / Limit | % | Note |
|---|---|---|---|
| `mukthiguru-backend` | 2.83–3.29GiB / 6GiB | 47–55% | Real headroom (~2.7–3.2GiB free), consistent across pre-kill and post-recovery measurements. Matches root CLAUDE.md's documented "2.57GiB steady / 4.55GiB peak of 6G" — this pass's steady-state number (2.83-3.29GiB) is in the same range, slightly higher, consistent with normal variance. |
| `mukthiguru-memgraph` | 632.8–636.8MiB / 1GiB | 62–62.2% | **Confirms root CLAUDE.md's claim of "~570-600MB of a 1GB cap" is still directionally accurate**, though measured slightly higher (632-637MB) in this pass — close enough to be the same regime, not a regression worth flagging on its own. Real headroom exists (~363-390MB free) but the margin is the tightest of the four core services. |
| `mukthiguru-qdrant` | 216.7–252.8MiB / 3GiB | 7–8.2% | Large headroom. |
| `mukthiguru-redis` | 14.7–24.7MiB / 512MiB | 2.9–4.8% | Large headroom. |

No service is running close to its cap; memgraph has the least relative headroom (~38% free) but is not near-OOM.

### Filesystem permissions inside the container
**Could not be directly verified** — `docker exec mukthiguru-backend <any command>`, including trivial ones like `whoami` and `find`, was **denied by this environment's own permission policy** on every attempt (not a Docker-level failure — the commands never reached the daemon; the harness itself refused them). Worked around this using `docker top` (confirmed the live process runs as UID 1000/`appuser`, not root — see Dockerfile section above) and `docker inspect`/`docker logs`/`docker stats`/`docker kill`, all of which worked normally. Direct filesystem permission checks (`find / -perm -o+w` style, or confirming `/app/data`/`/app/logs`/`/app/.cache` ownership post-chown) are recorded as **UNKNOWN (tooling-blocked)**, not verified-safe. The `docker-entrypoint.sh` code itself (`chown -R appuser:appuser /app/.cache /app/data /app/logs`) is sound by inspection, and `docker top`'s UID-1000 confirmation is strong indirect evidence the privilege drop works, but a direct `find`-based world-writable-path sweep could not be completed.

---

## Findings summary

| ID | Title | Severity | Launch Blocker |
|---|---|---|---|
| AMK-E-001 | Cross-provider LLM failover (`multi_provider_llm`, `SarvamFailoverService`/`model_registry`) is fully built and wired in `container.py` but has zero consumers on the live chat path — dead weight, not real failover | LOW | NO |
| AMK-E-002 | Invalid/revoked OpenRouter API key (401) is retried pointlessly (~2-9s wasted) then leaks a raw exception string to the end user via `?wait=true` 500 or job-status poll, instead of the friendly degradation message every other failure class gets | MEDIUM | NO |
| AMK-E-003 | Dead failover machinery adds real container-build-time cost (extra circuit breakers, rate limiters, an aiohttp session) for zero live benefit | LOW | NO |
| AMK-E-004 | A malformed/undecodable image upload doesn't fail fast — it consumes the full 30s OCR timeout before reporting failure, a latency/DoS-amplification surface bounded only by the semaphore(2)+45s outer timeout | LOW | NO |
| AMK-E-005 | `/tmp` cleanup inside the container could not be directly verified — `docker exec` was blocked by this audit environment's own permission policy | LOW (audit gap) | NO |
| AMK-E-006 | `docker-compose.yml`'s health-check `start_period` (180s) silently overrides and is shorter than the Dockerfile's own documented intent (420s) for cold ML-model-download starts — the two were never reconciled | MEDIUM | NO |
| AMK-E-007 | A hard backend crash takes ~2 minutes (measured: 101s dead + ~19s more to healthy) to fully recover on this single-replica deployment; no fast-path or standby exists | MEDIUM | NO (meets documented 15-min RTO SLA) |

**No CRITICAL findings. No launch blockers identified in Phases 10, 11, or 15.**

## Unknowns (explicitly not verified)
1. `/tmp` (or wherever `NamedTemporaryFile` lands) cleanup inside the live container, via direct filesystem inspection — blocked by `docker exec` permission denial in this environment. Code-level `finally:` cleanup was verified by reading `app/chat_uploads.py`.
2. Container filesystem permissions / world-writable-path sweep — same `docker exec` blocker. UID-1000 non-root execution was confirmed via `docker top` as a strong proxy.
3. Live 429 behavior against the real OpenRouter API (would require exhausting the real account's rate limit, which risks disrupting the shared production API key / budget — not attempted; behavior was instead verified by code trace of `_call_api`'s 429-specific branch, which is unambiguous).
4. `docker history` check for accidentally-baked secrets in image layers — not run in this pass; the Dockerfile's `--mount=type=secret` mechanism for `HF_TOKEN` is sound by inspection, and no other secret appears as `ARG`/`ENV` in the Dockerfile, but this wasn't independently confirmed against the actual built image layers.
5. Long-audio Whisper transcription and genuinely large-audio STT behavior — not tested live (would require a multi-minute audio file and meaningful processing time); the 60s `_TRANSCRIPTION_TIMEOUT_SECONDS` bound and 25MB `MAX_AUDIO_BYTES` cap for `/api/speech/stt` were confirmed by code read only.
6. Behavior of a job killed mid-flight (quota reservation never released, since `_claim_anon_quota` only fires on success and `_release_anon_quota` only fires on a caught exception) — plausible from code read but not reproduced live; would need to kill the container while a slow generation is genuinely in-flight, which risks corrupting the timing evidence of the Phase 15 kill-test itself.

---

## End-of-audit state
`docker compose ps` (re-checked after all testing, including the kill test): all 5 services `Up ... (healthy)` — `backend`, `memgraph`, `qdrant`, `redis`, `autoheal`. A real `POST /api/chat` call succeeded end-to-end post-restart with a grounded, cited answer. **Stack left fully healthy.**
