# Sharing model memory across backend worker processes (research, 2026-11-27)

Question: one backend process costs about 2.5 GB, and every extra uvicorn worker duplicates the
BGE-M3 INT8 ONNX session (~0.9 GB) and the tokenizers. Can workers share that memory, without a
model server?

Short answer: yes, for the encoder. Loading a host-built, memory-mapped, prepacked copy of the
model (new flag `ONNX_MMAP_PREPACKED_ENABLED`, default OFF) gives bit-identical embeddings and cuts
one process from 977 MB to 710 MB (PSS). Sharing the tokenizer by forking after it loads, and
creating each ORT session after the fork, brings the marginal cost of a worker down to about
100 MB. Pre-fork ORT sessions are not needed and should not be relied on.

## Environment and method

- Throwaway container `mmtest` from the backend image (Linux aarch64, Python 3.12, ORT 1.30.0,
  tokenizers 0.23.3), `--memory=2400m`, model copied in; the live backend was not touched.
- The Docker VM was starved during the work (7.7 GB total, swap exhausted, load average 20-48,
  other containers at 70-270 % CPU, `/proc/pressure/cpu` some avg10 = 56). **Timings are
  meaningless; memory numbers are not affected.** Per the coordinator's instruction N=3 was not
  run; N=3 rows are extrapolated and marked so.
- Memory = summed PSS from `/proc/<pid>/smaps_rollup` (never RSS), split anon / file. cgroup
  `memory.current` is logged by the scripts but includes page cache left by earlier runs, so it is
  not used for the table.
- Identical outputs: sha256 over dense, sparse and colbert outputs of five texts (incl. a 512-token
  one) equals the baseline hash `c6107e0b619e6489` for every variant below; the multi-process
  workers additionally `np.array_equal` every output against the baseline under concurrent encodes.
- Scripts are in the session scratchpad only (not committed): `common.py`, `memtest.py`,
  `multi.py`, `fork_multi.py`, `fork_*.py`, `build_opt.py`.

## 1. Fork hang: root cause

**Not reproduced; I cannot prove a cause, and I will not state one as fact.**

What I measured (model 570 MB file, same `InferenceSession` + `Tokenizer` as `/tmp/fork_test.py`):

| Test | Result |
| --- | --- |
| original `fork_test.py`, N=2, intra=1, 4 runs (also with compose env `OMP_NUM_THREADS=2`, `TOKENIZERS_PARALLELISM=false`) | all children finished; PSS per child ~380 MB, cgroup delta 3-43 MB |
| child after parent inference, intra 1 / 2 / 4, 30 encodes | child finished; child had 1 thread, parent 11-14 |
| parent and forked child encoding concurrently, per-encode time compared, intra=2 x3, intra=1 x3, intra=1 with tokenizer created after fork x2 | child always finished; child time equals parent time in the same run (1.1/1.1, 1.4/1.5, 13.2/13.2 s ...) |
| 9 sequential forks, intra=2 | 0 hung |
| 9 sequential forks, intra=1 | 1 child "HUNG" at 12 s, state `R` (running, not a futex wait), while the parent's own encode time in that run had degraded from 1.5 to 8.8 s |

Reading: every "hang" I saw was a runnable process on a CPU-starved VM, and parent and child slowed
together (the per-encode time went 1.1 to 13 s in the parent too). One earlier run (intra=2, two
children, 30 encodes) was still in state `R` after more than two minutes under the same load; I did
not capture CPU-tick growth, so I cannot say whether that was starvation or a livelock. A deadlock
would normally show a sleeping futex wait, which I never observed.

Mechanism, from reading the design, **not proven here**:
- `fork()` keeps only the calling thread. With `intra_op_num_threads=N>1` ORT has N-1 worker
  threads; in the child they do not exist (observed: parent 12 threads, child 1). ORT's pool state,
  queues and spin flags are copied mid-flight. Runs may still complete because the calling thread
  can execute its own tasks, which is consistent with intra=2 and 4 working in my tests, but
  nothing guarantees it. With intra=1 there is no worker pool at all.
- Other fork hazards that were not isolated: HF `tokenizers` rayon pool (it disables parallelism
  after fork with a warning; not exercised because I used `encode`, not `encode_batch`),
  OpenBLAS/numpy threads (10 threads in the parent), Python and logging locks.
- Not run: `TOKENIZERS_PARALLELISM`/`OMP_WAIT_POLICY` sweeps and `allow_spinning=0` (the key exists in
  ORT 1.30.0). I therefore cannot name a "safe pre-fork combination" and recommend none.

Conclusion: no combination is proven safe, none is proven broken. The pattern that is safe by
construction is to **create the ORT session after the fork** (pattern F below); it also costs
almost nothing once the weights are file-backed.

## 2. Why 570 MB on disk becomes ~0.9 GB

Model facts (host `onnx` inspection): 194 `MatMulInteger`, a 244 MB UINT8 word-embedding table,
289 MB of INT8 MatMul weights, 1.2 MB float.

Measured anon memory of one process (imports 13-21 MB):

| Stage | anon |
| --- | --- |
| default session created | 838 MB |
| `session.disable_prepacking=1`, created | 581 MB (~ file size) |
| `disable_prepacking=1` after 5 encodes | 894 MB, hash identical |
| default after 5 encodes | 905 MB |

So load = a private copy of every initializer (~580 MB) plus an MLAS prepacked copy of the INT8
weights (~257 MB); disabling prepack only moves the packed copy to run time. The BGE-M3 tokenizer
is a separate **276 MB anon** (`Tokenizer.from_file`, measured alone) that this repo loads again for
the reranker. Large pools were not the cause: `enable_mem_pattern=0` and `enable_cpu_mem_arena=0`
saved only 35-40 MB with identical output.

## 3. Patterns measured

PSS in MB. Workload: 2 concurrent encode threads per process unless stated. "indep" = separate
processes started fresh (no fork).

| Pattern | N=1 | N=2 | N=3 |
| --- | --- | --- | --- |
| baseline: default session, indep | 977 (20 threads: 1326) | 1954 (extrapolated, sum of two) | 2931 (extrapolated) |
| `disable_prepacking` | no gain (894 anon after use) | - | - |
| **mmap prepacked model, indep** | 710 = 388 anon + 322 file (20 threads: 1053) | 1082 measured | ~1486 (extrapolated) |
| fork after session (parent loads ORT, children inherit), default model | - | 1236 measured | - |
| fork after session, mmap prepacked | - | 778 measured (intra=1); 1014 (intra=2, 8 threads) | - |
| **F: fork after tokenizer only, per-child mmap session** | 716 | 817 measured (marginal worker ~100 MB); 1108 (intra=2, 8 threads) | ~918 (extrapolated) |

- Every run: 0 output mismatches, all encode threads finished, no hang (20 threads x 1 process,
  8 threads x 2 children at intra=2, 2 threads x 2 children).
- The 20-thread rows grow by ~400 MB anon in both baseline and mmap runs: that is concurrent
  activation memory, not weights. It is the same cost either way.
- Single process at intra=2 (production setting), after 5 encodes: default 909, mmap prepacked 597
  (anon 347 + file 250), same hash.
- Why the file part is shared: the prepacked weights and the originals sit in a `MAP_PRIVATE`
  mapping of `model.onnx.data` (393 mappings, 543 MB virtual; the 244 MB embedding table is mapped
  lazily and only touched rows count). Page-cache pages are counted once and split between
  processes in PSS. They are not duplicated per worker, but they do count in the container
  cgroup once. How Railway meters that is **unverified**.
- Steady-state caveat: every mmap figure here was taken after only 5-8 encodes. The 244 MB embedding
  table is mapped lazily and the file-backed part (250-325 MB) only counts pages touched so far, so
  as more distinct token rows are hit the file part grows toward the full mapped size. The
  single-process saving (~270 MB, 977 vs 710 at N=1; 909 vs 597 at intra=2) therefore **may be
  smaller at steady state**. The saving at N>=2 is less affected because those pages are shared,
  but it was also measured after few encodes.
- Remaining anon in the mmap path is about 35 MB for ORT itself plus the 276 MB tokenizer plus
  working memory. The tokenizer is the largest unshared item; only fork-after-load shares it.

Not worked: saving `model.ort` via `optimized_model_filepath` with `session.save_model_format=ORT`
wrote no file in my run (not investigated), so the ORT-format + `use_memory_mapped_ort_model` /
`use_ort_model_bytes_for_initializers` path was not measured. The Python `InferenceSession(bytes)`
route copies the bytes into a `std::string`, so `use_ort_model_bytes_directly` cannot be zero-copy
from Python (reasoned from the pybind signature, not tested). The external-data route above needs
none of that.

## 4. What the flag does (implemented)

`ONNX_MMAP_PREPACKED_ENABLED=true` (default false; `ONNX_PREPACKED_CACHE_DIR`, default
`<hf_home>/onnx_prepacked`), only with `EMBEDDING_BACKEND=onnx_int8`:

- `services/onnx_prepacked.py` builds the artifact once per host in a child process
  (`optimized_model_filepath` + `session.optimized_model_external_initializers_file_name` +
  `session.save_external_prepacked_constant_initializers=1`, 24 s under load / 9 s idle, ~1 GB
  transient, 832 MB of disk). A child process is used on purpose: building in the serving process
  left ~290 MB of anon heap behind (PSS 947 vs 670 measured).
- Keyed by ORT version, CPU feature digest, architecture, model size and mtime. A mismatch
  rebuilds; ORT itself says an optimized model is only valid in the environment that produced it, so
  never bake the artifact into an image or copy it between machines.
- `flock` + temp dir + atomic rename + `READY` marker: concurrent workers build once. Failures
  raise `PrepackError`; there is no silent fallback to the old path.
- Build timeout: the child is killed after `ONNX_PREPACKED_BUILD_TIMEOUT_S` (default 120 s, under
  the 180 s lifespan startup budget) and the load raises `PrepackError`.
- Cleanup, under the build lock: a SIGKILL or OOM kill skips the `finally`, so a dead builder can
  leave an ~830 MB `tmp.*` dir. Because builders are serialized by the same flock, any `tmp.*` seen
  while holding it is dead, so no age threshold is needed; they are removed before each build, as
  are cache keys other than the current one (superseded ORT version or model). Cleanup only runs
  when a build is about to happen, never on the cached fast path. Caveat: two ORT versions sharing
  one cache dir would delete each other's artifact and rebuild; a Railway volume attaches to one
  container, so this should not occur.
- Integrity: `READY` is JSON with the byte size and sha256 of both files, written at build time.
  Every load checks both sizes and the graph hash (the graph file is ~0.6 MB); with
  `ONNX_PREPACKED_VERIFY_DATA_HASH=true` (default) it also re-hashes the 832 MB data file. Cost:
  one sequential read of 832 MB at build time and at each worker start, which I estimate at
  1-3 s (**not measured**; I did not rerun anything heavy) and which pulls the whole file into
  page cache (reclaimable, not counted in PSS because it is not mapped by that read). With the data
  hash off, a same-size bit flip in the weights is not detected (test documents this). A mismatch
  is logged as an error, the directory is removed and rebuilt; it is never served.
- Threat note: the sha256 values live next to the files, so this detects corruption and
  accidental truncation, not an attacker who can write the cache dir (they could rewrite READY).
  The first-person span hash gates (`source_text_hash`, speaker allowlist) still block fabricated
  teacher text regardless of embeddings. A tampered or corrupted embedding cache can however
  degrade retrieval quality (wrong vectors, wrong clips ranked) without tripping those gates, so
  keep the cache dir writable only by the service user.
- Resource note: the ~1 GB build child runs beside the parent process under the 6 GB container
  cap (parent about 0.7-1 GB at that point), which fits but is the peak of the whole path.
- BGE-M3 cache wipe: `EmbeddingService._ensure_encoder` retries a failed `_load_encoder` after
  `_clear_hf_cache_for(model_name)`, which deletes every `*BAAI--bge-m3*` entry under the HF cache
  dirs, including the pinned tokenizer snapshot the ONNX path reads. Read of the code path: before
  this fix any exception from the prepack build (child failure, timeout) would have reached that
  wipe and then failed again. Fixed: `PrepackError` is re-raised before the wipe handler
  (`tests/test_onnx_prepacked.py::test_prepack_failure_never_triggers_hf_cache_wipe`). The
  prepack cache itself lives in `<hf_home>/onnx_prepacked/<hex key>/`, which the wipe's glob
  patterns do not match, and `_prune_unused_hf_variants` returns early for `onnx_int8`.
  Remaining caveat: a non-`PrepackError` failure of the old ONNX load path still takes the
  pre-existing wipe-and-retry route, unchanged.
- `services/embedding_service.py` swaps only the model path; session options, the dimension check
  and tokenizer code are unchanged. Reranker not changed (not measured).
- Verified: unit tests (`tests/test_onnx_prepacked.py`, build mocked, covering timeout, pruning,
  READY content, tampering and the wipe guard); the real module end to end in the container
  before the integrity/timeout changes (fresh build, second call reuses, hash identical to
  baseline). Not verified: the real build with the new READY/hash/timeout code (no containers run in
  the review round), and running through `embedding_service._load_onnx_encoder` itself.

## 5. Recommendation

1. Turn the flag on where more than one process serves traffic (uvicorn `--workers`, `WEB_CONCURRENCY`
   above 1): about 870 MB saved at N=2 versus an extrapolated baseline (1082 measured vs 1954
   extrapolated as twice the measured single-process 977; independent processes do not share
   memory, but I did not run two baselines because the VM could not hold them), growing with N.
   On a single process it saves ~270 MB (710 vs 977, both measured), taken after only 5 encodes
   with the 244 MB table still lazily mapped, so the steady-state saving may be smaller. Needs a
   persistent volume of ~0.9 GB for the cache dir, and a first-start build.
2. For more saving, change the worker bootstrap (outside this task: `start_railway.py` worker logic
   was off limits) to load the tokenizer in the master, fork, and create the ORT session inside each
   child (pattern F). Measured marginal worker: ~100 MB versus ~970 MB today. Do not create the ORT
   session before the fork.
3. Before production: repeat the N=1/2/3 run on the actual Railway x86_64 hardware, with the
   reranker and the second tokenizer included, and confirm how Railway meters mapped page cache.
4. Keep `FIRST_PERSON_*` invariants untouched: this changes memory only; outputs were bit-identical.

## Sources

- ONNX Runtime session option keys `session.use_memory_mapped_ort_model`,
  `session.use_ort_model_bytes_directly`, `session.use_ort_model_bytes_for_initializers`,
  `session.disable_prepacking`, `session.save_external_prepacked_constant_initializers`,
  `session.optimized_model_external_initializers_file_name`: confirmed by extracting the key strings
  from the installed `onnxruntime` 1.30.0 binary in the container (the official header URL returned
  404).
- ORT format models: https://onnxruntime.ai/docs/performance/model-optimizations/ort-format-models.html
- ORT commit adding memory-mapped ORT models (author benchmark: private memory across four processes
  462.6 MB to 98.2 MB with direct initializers); read via search-result summary only, the page itself
  returned HTTP 429: https://app.semanticdiff.com/gh/microsoft/onnxruntime/commit/9d1492a44972f2d4b6415b49811db0034bae7f75
- Fork-after-threads hazards (search results; pages not read in full): gunicorn issue
  https://github.com/benoitc/gunicorn/issues/2478, optimum issue
  https://github.com/huggingface/optimum/issues/1327, CPython fork-with-threads discussion
  https://github.com/python/cpython/issues/93580. No source found that documents an ORT
  `InferenceSession` deadlock after fork; the ORT warning that optimized models are
  environment-specific is printed by ORT 1.30.0 itself when serializing.
