# Concurrency, crashes and the real ceiling — 2026-09-18

Supersedes the root-cause statements in `audit/track_B_findings.md` (AMK-B-002)
and `audit/track_C_findings.md` (AMK-C-001). The findings' *evidence* held up.
Their *diagnosis* did not.

## What the audit concluded

Both findings concluded the backend was dying of native memory pressure: the
ONNX/torch stack allocating more than the box had, with `max_concurrent_chat=8`
admitting more work than the memory budget could serve. The recommended fix was
to lower the concurrency ceiling and/or raise the memory limits.

## What actually kills it

```
Fatal Python error: Segmentation fault

Current thread (most recent call first):
  File ".../torch/nn/modules/linear.py", line 134 in forward
  File ".../transformers/models/modernbert/modeling_modernbert.py", line 492 in forward
  ...
  File ".../lettucedetect/detectors/transformer.py", line 385 in predict
  File "/app/services/lettuce_detect_service.py", line 388 in _score_with_real_detector
```

Reproduced 2026-09-18 at concurrency 6. At the moment of death:

| Signal | Value |
| :--- | :--- |
| Container memory | 4.11 GiB of a 6 GiB limit |
| `State.OOMKilled` | `false` |
| `State.ExitCode` | 0 (the entrypoint masks the child's signal) |
| Host VM total | 7.75 GiB |

It is not memory. `LettuceDetectService._shared_detector` is a `ClassVar` — one
torch module for the whole process — and `score_faithfulness` runs from a thread
per in-flight chat. Concurrent `forward()` on one transformers model races and
takes the interpreter down.

This explains what the memory hypothesis could not: why every crash dump named
`modernbert`/`lettucedetect`, and why the box died with a third of its memory
budget unused.

`embedding_service.rerank()` already carried the comment *"PyTorch CrossEncoder
fallback: not thread-safe, serialize"* and held `_inference_lock`. The rule was
known in this codebase. Two call sites — `lettuce_detect_service` and
`reranker_service._run_cross_encoder` — had missed it.

## The fixes

1. **`LettuceDetectService._shared_predict_lock`** — exclusive access to the
   shared torch module. On timeout the request sheds to the heuristic scorer;
   the faithfulness gate is never skipped.
2. **`RerankerService._torch_predict_lock`** — same, for the PyTorch
   CrossEncoder path. The ONNX path does not need it (`session.run()` is
   thread-safe) and is left alone.
3. **`services/native_inference_gate.py`** — a process-wide bound on concurrent
   native inference. This is a *memory* bound and only a memory bound. It did
   not fix the crash and was never going to; it exists so peak RSS stays
   predictable.
4. **`liveness-watchdog` sidecar** — `autoheal` watches Docker HEALTHCHECK
   transitions, so it only ever sees a container that is running and reporting
   unhealthy. It logged nothing across the entire outage window. The new sidecar
   restarts containers in `Exited`/`dead` state, skipping exit codes 0 and 143
   so an intentional `docker stop` is respected. Verified against a probe
   container killed with SIGKILL under `--restart=no`: recovered with
   `RestartCount=0`, so only the watchdog could have done it.

## Measured ceiling

`backend/scripts/ops/gate1_load_test.py` now asserts container survival, not
just latency: it samples `docker stats` throughout, then checks the container is
running, did not restart underneath the run, and stayed under a memory budget
expressed as a fraction of the **host's** total memory.

(Its live-HTTP mode had never worked — it passed `base_url=None` to httpx and
raised `TypeError` before the first request. Only the in-process mode had ever
been exercised. Fixed.)

Three runs, 24 requests at concurrency 6, against the same box:

| Run | Gate | Survived | Peak | Queueing in the gate |
| :--- | :--- | :--- | :--- | :--- |
| Before the lock | 2 | **No** — segfault, restart 0→1 | 4111 MB | 787 s |
| After the lock | 2 | Yes, restarts 0→0 | 3613 MB | 787 s |
| After the lock | 6 | Yes, restarts 0→0 | 4242 MB | 155 s |

Marginal cost per concurrent request: **~324 MB** (baseline ~2300 MB of resident
models, peak 4242 MB at 6 concurrent).

Memory-only ceiling, at 80% of the service allocation:

| Service memory | Concurrent chats before memory binds |
| :--- | :--- |
| 4 GB | ~3 |
| 8 GB | ~13 |
| 16 GB | ~33 |
| 32 GB | ~73 |

## Why `max_concurrent_chat` stays at 8

The deploy target is Railway Pro (32 GB / 32 vCPU), where memory does not bind
until roughly 73 concurrent chats. Memory is not the constraint. Two other
things are, and neither is fixed by moving this number:

* **Provider rate limiting.** One 24-request run spent **347 s across 79 sleeps**
  in the OpenRouter limiter. That is an account-level throughput cap, not a
  defect in this code.
* **Serialized verification.** The faithfulness NLI pass is now exclusive by
  construction, so verification throughput is one at a time per process.

Raising the admission ceiling would deepen queues behind both without serving
one more seeker. Lowering it would refuse traffic the box can hold. It stays at
8 until one of those two is addressed — the next real lever is a small **pool**
of detector instances (one torch module per slot, ~600 MB each) rather than one
shared module, which is affordable at 32 GB and would lift the verification
ceiling directly.

Do not change `max_concurrent_chat` or `native_inference_max_concurrent` from a
guess. Re-derive:

```bash
cd backend && .venv/bin/python3 scripts/ops/gate1_load_test.py \
  --base-url http://localhost:8000 --concurrency 6 --requests 24 \
  --container mukthiguru-backend --mem-budget-pct 60
```

It exits non-zero when the container does not survive.
