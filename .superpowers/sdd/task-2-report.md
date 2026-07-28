# Task 2 Report: Config-Driven Quantization + Search Param Support

## What Changed

### 1. `backend/app/config.py`
- Added `qdrant_quantization: str = "scalar_int8"` with default matching existing production behavior.
- Added `qdrant_quantization_oversampling: float = 3.0`.
- Updated `__main__` self-check to print both new settings.

### 2. `backend/services/qdrant/client.py`
- Imported `BinaryQuantization`, `BinaryQuantizationConfig`, `TurboQuantization`, `TurboQuantQuantizationConfig`, `TurboQuantBitSize` from `qdrant_client.http.models`.
- Added `QdrantClientManager._build_quantization_config(quantization: str)` static helper that builds the correct Qdrant quantization config for:
  - `scalar_int8` → exact legacy `ScalarQuantization(INT8, always_ram=True)`
  - `binary` → `BinaryQuantization(always_ram=True)`
  - `turboquant_1bit` / `turboquant_2bit` / `turboquant_4bit` → `TurboQuantization` with `TurboQuantBitSize.BITS1/BITS2/BITS4`
- Replaced hardcoded `ScalarQuantization(...)` in `init_collection()` with the helper driven by `settings.qdrant_quantization`.
- Kept dense vector `on_disk=True` and quantized index `always_ram=True`.
- Added `__main__` self-check block that prints each valid config and verifies invalid settings raise `ValueError`.

### 3. `backend/services/qdrant/searcher.py`
- Imported `QuantizationSearchParams` and `SearchParams`.
- Added `_dense_quantization_search_params()` method returning `None` for `scalar_int8`, otherwise `SearchParams(quantization=QuantizationSearchParams(rescore=True, oversampling=settings.qdrant_quantization_oversampling))`.
- Wired the params into `_dense_search` and into the dense `Prefetch` used in hybrid search.
- Sparse-only/BM25 paths are not modified and do not receive search params.

### 4. `backend/.env.example`
- Added `QDRANT_QUANTIZATION=scalar_int8` and `QDRANT_QUANTIZATION_OVERSAMPLING=3.0`.

### 5. `backend/tests/test_qdrant_quantization.py` (new)
- Unit tests covering:
  - All valid quantization configs map to the expected Qdrant model types.
  - Invalid settings raise `ValueError`.
  - `scalar_int8` default passes no extra `search_params`.
  - Binary/TurboQuant modes pass `rescore=True` and the configured `oversampling` in dense-only search.
  - Hybrid search dense `Prefetch` receives the quantization search params.

## Self-Check / Test Output

```
Quantization configs by setting:
  scalar_int8: scalar=ScalarQuantizationConfig(type=<ScalarType.INT8: 'int8'>, quantile=None, always_ram=True)
    json: {"scalar": {"type": "int8", "quantile": null, "always_ram": true}}
  binary: binary=BinaryQuantizationConfig(always_ram=True, encoding=None, query_encoding=None)
    json: {"binary": {"always_ram": true, "encoding": null, "query_encoding": null}}
  turboquant_1bit: turbo=TurboQuantQuantizationConfig(always_ram=True, bits=<TurboQuantBitSize.BITS1: 'bits1'>)
    json: {"turbo": {"always_ram": true, "bits": "bits1"}}
  turboquant_2bit: turbo=TurboQuantQuantizationConfig(always_ram=True, bits=<TurboQuantBitSize.BITS2: 'bits2'>)
    json: {"turbo": {"always_ram": true, "bits": "bits2"}}
  turboquant_4bit: turbo=TurboQuantQuantizationConfig(always_ram=True, bits=<TurboQuantBitSize.BITS4: 'bits4'>)
    json: {"turbo": {"always_ram": true, "bits": "bits4"}}
  scalar_int4: raised ValueError (Unsupported qdrant_quantization: scalar_int4. ...)
  turboquant_8bit: raised ValueError (Unsupported turboquant setting: turboquant_8bit. ...)
  unknown: raised ValueError (Unsupported qdrant_quantization: unknown. ...)

Settings ok: {"kg_max_query_len": 4000, "kg_query_timeout_s": 5.0, "qdrant_quantization": "scalar_int8", "qdrant_quantization_oversampling": 3.0}

tests:
...............
13 passed in 3.72s
```

Commands run:
```bash
cd backend
. .venv/bin/activate
python services/qdrant/client.py
LLM_PROVIDER=ollama python app/config.py
pytest tests/test_qdrant_dimension_validation.py tests/test_qdrant_quantization.py -q
ruff check app/config.py services/qdrant/client.py tests/test_qdrant_quantization.py  # passed
```

## Any Issues or Concerns

1. **ruff pre-existing warning**: `services/qdrant/searcher.py` still has a pre-existing `F841` warning (`query_phonetic_tokens` assigned but never used). This warning existed before Task 2 changes and was not introduced by this task. The unused assignment was not removed to keep the diff minimal and focused.
2. **TurboQuant field names**: The qdrant-client 1.18.0 models use `TurboQuantization(turbo=TurboQuantQuantizationConfig(bits=..., always_ram=True))` rather than the names initially guessed from the brief (`bit_size`, `turbo_quant`). Verified empirically via `help()` and the self-check now passes.
3. **No live Qdrant create test**: Tests use mocks and static config construction. A real end-to-end collection create with each quantizer would require dropping/recreating the local collection and is out of scope for this config-driven wiring task.

## Commit Hash

`8284e5559249502d02b7bc54db1ca44e2d021a59`

## Task 2 Fix Verification

```
$(.venv/bin/python -m pytest tests/test_qdrant_quantization.py -v 2>&1)
```
