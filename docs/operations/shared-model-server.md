# Shared model server (opt-in)

Status: implemented, default OFF. Owner role: platform engineering. Last verified: 2026-11-27 (local Docker, not on Railway).

Authoritative for: how to run BGE-M3 + the reranker once for several API workers. If this conflicts with `backend/services/model_server/`, `backend/start_railway.py` or `backend/app/config.py`, the code wins.

## Why

Each uvicorn worker is a separate process with its own copy of the models. One live process read ~2.6 GB RSS in the container and averaged 2.7 GB on Railway at `WEB_CONCURRENCY=1`; with 2 workers the 7-day average was 4.8 GB (~2.4 GB each). The split (~0.5 GB libraries, the BGE-M3 INT8 ONNX session ~0.9 GB, the reranker) is an estimate, not measured per component. Railway bills memory, so `WEB_CONCURRENCY=2` doubles it. Loading the ONNX session before fork is not adopted: one early test hung forked children, but a controlled re-test could not reproduce a deadlock (cause unproven; see `docs/operations/model-memory-sharing-research-2026-11-27.md`), so the models can instead live in one separate process.

## What it is

- `SERVICE_TYPE=model-server` runs `services/model_server/app.py` (single process): loads the ONNX INT8 encoder and the ONNX INT8 reranker once.
- Routes (all but `/healthz` need the token): `POST /v1/encode` (dense), `POST /v1/encode_batch` (dense + sparse), `POST /v1/rerank` (query/passage pairs to sigmoid scores), `GET /healthz`.
- The API process, when `MODEL_SERVER_URL` is set, gets `RemoteEmbeddingService` from `get_embedding_service()` and a remote reranker in `RerankerService`. They keep the real classes' query expansion, async wrappers, rerank thresholding and circuit breaker; only the model calls go over HTTP.
- Payload is JSON. Floats round-trip exactly (float32 values are emitted as the shortest repr of the float64), so vectors and scores are identical to in-process; this is asserted with exact equality, not a tolerance.
- Not served (ingestion tooling only, run with `MODEL_SERVER_URL` unset): `encode_with_colbert`, `encode_late_chunked`, `encode_query_mean_pooled`. In model-server mode they raise `NotImplementedError`. `ENABLE_COLBERT=true` together with `MODEL_SERVER_URL` is rejected when settings load (the process fails at boot with a `ValueError`), as is a `MODEL_SERVER_URL` without `MODEL_SERVER_TOKEN`.

## Environment variables

| Var | Where | Meaning |
|---|---|---|
| `SERVICE_TYPE=model-server` | model-server service | runs the server instead of the API |
| `MODEL_SERVER_TOKEN` | both | shared secret; the server refuses to start without it, the client refuses to build without it |
| `MODEL_SERVER_URL` | API service only | e.g. `http://model-server.railway.internal:8000`; empty (default) = in-process models, behaviour unchanged |
| `MODEL_SERVER_TIMEOUT_S` | API service | per-call timeout, default 30 |
| `PORT` | model-server | listen port (Railway sets it); binds `::` (dual-stack) |
| `RERANKER_ONNX_MODEL`, `OMP_NUM_THREADS`, `NATIVE_INFERENCE_MAX_CONCURRENT`, HF cache vars | model-server | read by the server's models exactly as before; the API side ignores the reranker model id |

Set `MODEL_SERVER_URL` only on the web API service. Celery/ingestion services must leave it unset (they use late chunking, which is not served, and they should keep their own models).

## Railway setup

1. Create a second service from the same image/repo (`backend/Dockerfile.railway`), name it `model-server`.
2. Variables: `SERVICE_TYPE=model-server`, `MODEL_SERVER_TOKEN=<long random>`, plus the model/HF cache variables the API service already has. Healthcheck path `/healthz`; allow time for model load (the server answers only after the models are loaded).
3. Do not give it a public domain. Use the private network name.
4. On the API service set `MODEL_SERVER_URL=http://model-server.railway.internal:<PORT>` (see Railway's private networking docs for the port) and the same `MODEL_SERVER_TOKEN`; then raise `WEB_CONCURRENCY`.
5. Railway legacy environments resolve `*.railway.internal` to IPv6 only (environments created after 2025-10-16 are dual-stack, per Railway docs), which is why the server binds `::`.

## Memory arithmetic

Per-process numbers from this work are in the table below (measured in local Docker, see "Measurements"); Railway cost is memory-time, so compare totals.

| Layout | Memory |
|---|---|
| 1 worker in-process (today's live setting) | 1 x ~2.5 GB |
| 2 workers in-process | 2 x ~2.5 GB = ~5 GB |
| 1 model server + 2 API workers | server + 2 x API-process (see Measurements) |

It pays off only above one worker: with `WEB_CONCURRENCY=1` the model server adds a process and a network hop for no saving. `start_railway.py` logs a `MEMORY WARNING` at boot when `WEB_CONCURRENCY > 1` and `MODEL_SERVER_URL` is empty; it does not refuse to start.

## Failure behaviour

- No silent fallback. If the server is down, slow, or rejects the token, the call raises `ModelServerError` (transport errors, timeouts and HTTP 5xx other than 503 also feed the existing embedding circuit breaker, which then fails fast with `CircuitOpenException`; a 503 does not, see below). Falling back to in-process loading would silently reintroduce the memory blowup.
- One retry only on a dropped keep-alive connection or connect error (calls are pure). Timeouts are not retried.
- Server overload (`native_inference` gate timeout) or an open server-side breaker returns 503. The client raises `ModelServerError` with `status=503` (the request fails loudly) but does not count it toward its own breaker, so a load burst cannot turn into a breaker-open outage. The server's gate waits `NATIVE_INFERENCE_WAIT_TIMEOUT` (default 60 s) before answering 503, which is longer than the client's `MODEL_SERVER_TIMEOUT_S` (default 30 s): under overload the client times out first, and a timeout does count toward the breaker. Set `NATIVE_INFERENCE_WAIT_TIMEOUT` on the model-server service below `MODEL_SERVER_TIMEOUT_S` (for example 10 s) so overload shows up as a 503.
- Startup: the API's embedding warm-up canary (`encode_single` in `app/main.py`) is the first call; an unreachable server shows there as a warm-up failure.
- If the encoder cannot load as ONNX INT8 the server refuses to start (no torch fallback).

## Concurrency and sizing

The server is one process; routes are sync functions run in FastAPI's threadpool (anyio default: 40 threads, shared by all clients). ONNX `session.run` is thread-safe and the existing `native_inference` gate (`NATIVE_INFERENCE_MAX_CONCURRENT`, default 6) bounds concurrent native inference, so requests from several API workers are served concurrently and correctly (covered by `tests/test_model_server.py` and the real-model `tests/test_model_server_equivalence.py`). Requests beyond the gate size wait for a slot, up to the gate timeout, then get 503.

Pool sizing, per API worker against the one server:

- The client keeps a pool of up to 32 connections (16 kept alive) per worker process; this is a ceiling, not a target. Real in-flight calls per worker are bounded by the embed thread pool (`EMBED_THREAD_WORKERS`, default `min(2, cpus // 2)`), the reranker pool (2 threads) and the few call sites that embed synchronously on the event loop, so roughly 2-5 at once.
- All workers share the server's 40 request threads, but only `NATIVE_INFERENCE_MAX_CONCURRENT` of them run inference at a time; the rest wait in the gate. Extra threads beyond the gate add queueing, not throughput.
- Sizing rule: keep `workers x (embed threads + rerank threads)` around the gate size (6 by default) so waits stay short, and keep `NATIVE_INFERENCE_MAX_CONCURRENT x OMP_NUM_THREADS` (ORT intra-op threads per call, default 2) at or below the server's CPU count. More workers than the gate allows do not add throughput; they queue.
- None of these numbers were load-tested against the real models on Railway; they are derived from the code defaults.

## Security and privacy

- Private network only; no public domain. Every route except `/healthz` (which returns no data) needs `X-Model-Server-Token`, compared with `hmac.compare_digest`; the check runs in middleware before the request body is read or parsed, so an unauthenticated request gets 401 whatever its body (a bad body with a valid token gets 422).
- Requests carry seeker questions. The server and client never log request text, and error responses carry only the exception class name or status. Do not enable uvicorn debug body logging or a proxy that records bodies in front of it.
- The token is a bearer secret in plain HTTP inside the private network; rotate it like any other secret (change both services).

## Tests

- `backend/tests/test_model_server.py`: protocol, auth, failure and timeout behaviour, slicing, concurrent clients, no torch/transformers import in model-server mode, boot warning. Runs on the host.
- `backend/tests/test_model_server_equivalence.py`: client -> server -> real ONNX models vs the in-process service (exact equality). Skips when the model files or the ONNX backend are absent; runs in the backend container.
- `backend/scripts/ops/measure_model_server.py`: RSS and latency measurement used for the numbers below.

## Measurements

Environment: local Docker Desktop VM (2 vCPU, 8 GB shared with other containers), 2026-11-27. The VM was memory-starved by other containers throughout.

Measured:

- Equivalence: real BGE-M3 INT8 + reranker inside the backend container, client -> uvicorn on loopback -> ONNX. Dense vectors, sparse weights and reranker scores equal the in-process results with exact equality (no tolerance), including a rerank list longer than the reranker's internal batch of 8, and 6 concurrent client threads with unique texts. 6 tests passed.
- Transport cost added per call (server with zero-compute fake models returning real-shaped payloads: 1024-d dense, 25 sparse entries; loopback; 3 runs of 60 calls, noisy because the VM was loaded): embed p50 1.8-3.6 ms, p95 3.3-10.7 ms; rerank of 12 pairs p50 2.3-3.5 ms, p95 7.9-10.9 ms. This is the HTTP + JSON + thread-handoff cost only; model compute is identical to in-process. JSON was kept: at these sizes it is a small part of the cost, so msgpack/npy was not pursued.
- Client-side process with the model-server client path loaded (embedder + reranker service, nothing else): ~116 MB RSS, and `torch`, `transformers`, `sentence_transformers` are not in `sys.modules` (also asserted by `test_api_process_in_model_server_mode_imports_no_model_stack`, which passes on the host and in the container).
- Live backend process (in-process models, WEB_CONCURRENCY=1), read from the running container: ~2.6 GB RSS.

NOT measured (the VM did not have the free memory; a real-model server load coincided with the live backend container being OOM-killed, so it was stopped and not retried):

- RSS of the real model-server process.
- RSS of a full API worker in model-server mode. Importing `app.main` still pulls `torch`/`transformers` on a host venv that has the optional `llmlingua` package (via `rag/compressor.py`, unrelated to this feature), so a full API worker will not reach the model-free floor until that import is made lazy; whether the container image does the same was not checked.
- Real-model per-call latency in-process vs via the server, and the total for 1 server + 2 API workers vs 2 in-process workers. Expected arithmetic (not a measurement): 2 in-process workers ~ 2 x 2.5 GB; model server (the ONNX sessions plus libraries, part of that 2.5 GB) + 2 x (full API worker without models).

Reproduce with `backend/scripts/ops/measure_model_server.py` (modes in its docstring) on a host or VM with >= 4 GB free.
