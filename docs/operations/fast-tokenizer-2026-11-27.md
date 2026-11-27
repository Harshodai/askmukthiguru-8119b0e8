# FastTokenizer for the ONNX serving path (2026-11-27)

`backend/services/fast_tokenizer.py` replaces `transformers.AutoTokenizer` in
`EmbeddingService` and `OnnxReranker` (setting `ONNX_TOKENIZER_BACKEND`,
default `tokenizers`; `transformers` is the rollback).

## Memory (measured in the backend image)
- Shipped path, both services loaded: ~320-350 MB less RSS (2004 MB vs 2354 MB
  after load; 2131 MB vs 2447 MB after inference), because torch is still
  imported by `EmbeddingService._thread_setup`.
- Tokenizer alone: ~860 MB less (AutoTokenizer 1171 MB vs FastTokenizer 311 MB).
- Torch alone is ~522 MB. Removing the torch import from the ONNX path is a
  separate decision (it changes torch thread pinning for other consumers).

## Index-build note: read before any partial re-embed
- FastTokenizer reproduces transformers 5.x XLM-R behaviour (what the container
  and `requirements.txt` pin, 5.19.0).
- The live v13 index was built host-side through `EmbeddingService`
  (`ingest_corpus_gaps_v13.py` ~line 389) with transformers 4.57.6. 4.x tokenizes
  215 of 11,070 real transcript lines differently from 5.x: trailing whitespace
  gets an extra token id 6 (the bare word-start marker) in 4.x.
- Production queries were already tokenized the 5.x way in the container, so
  that index/query mismatch pre-exists this change.
- Future host builds now match query-time tokenization, but they will not
  reproduce existing points byte-for-byte. Record this before any partial
  re-embed, otherwise old and new points in one collection differ for those lines.

## Dependency
`tokenizers` is only a transitive dependency (pinned via transformers in
`requirements.lock`). Pin it explicitly in `requirements.txt` if transformers is
ever dropped from the image.

## Failure behaviour (no silent fallback)
With the fast backend, a missing `tokenizer.json`, a non-XLM-R `tokenizer_class`,
or an unexpected normalizer/pre-tokenizer raises `FastTokenizerLoadError`.
`EmbeddingService._ensure_reranker` and `RerankerService._load_fallback` normally
turn any ONNX reranker load failure into a warning plus a torch `CrossEncoder`
fallback; they now re-raise this one error instead, and `_ensure_encoder` skips
its "clear the HF cache and retry" step for it. Other ONNX load failures (model
download, session creation) keep their existing fallback. One residual case: a
corrupt `tokenizer.json` makes `tokenizers.Tokenizer.from_file` raise a bare
`Exception`, which the generic handlers still treat as an ordinary ONNX load
failure (warning, then fallback); wrapping it would need a new broad `except`
and the exception ceiling is 759.

## Proving equivalence against transformers 5.19 (image)
The host venv has transformers 4.57.6, so the 5.x cases skip there. With
`REQUIRE_TRANSFORMERS_5=1` the test fails instead of skipping (and fails if
transformers is not 5.x). `scripts/ops/verify_fast_tokenizer_in_image.sh` runs it
inside `backend-backend:latest` (`--memory 1600m`, no network, code mounted
read-only, model cache from `backend/.model_cache`); it prints the Docker VM's
MemAvailable first and refuses below 3 GB. Expected: all passed, 0 skipped.
