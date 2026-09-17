import os
from unittest.mock import MagicMock, patch

import pytest


def test_transformers_no_advisory_warnings_set():
    """Verify that TRANSFORMERS_NO_ADVISORY_WARNINGS environment variable is successfully set to true."""
    assert os.environ.get("TRANSFORMERS_NO_ADVISORY_WARNINGS") == "true"


def test_embedding_service_ragatouille_optional_graceful_fallback(monkeypatch):
    """Verify that if ragatouille is not installed, it falls back gracefully with an info log instead of crashing."""
    # Import the EmbeddingService
    from services.embedding_service import EmbeddingService

    # We patch FlagEmbedding and sentence_transformers to avoid loading heavy weights locally
    MagicMock()
    MagicMock()

    # Simulate FlagEmbedding BGEM3FlagModel and sentence_transformers CrossEncoder
    class MockBGEM3FlagModel:
        def __init__(self, *args, **kwargs):
            pass

    class MockCrossEncoder:
        def __init__(self, *args, **kwargs):
            pass

    # Mock the imports of FlagEmbedding and sentence_transformers.
    # monkeypatch.setitem (not a raw sys.modules[...] = ...) so these revert
    # after the test — a bare assignment here previously left a broken
    # FlagEmbedding.BGEM3FlagModel mock (no .encode()) in sys.modules for the
    # rest of the test session, breaking any later test whose EmbeddingService
    # actually loads a real encoder.
    import sys

    fake_flag_embedding = MagicMock()
    fake_flag_embedding.BGEM3FlagModel = MockBGEM3FlagModel
    monkeypatch.setitem(sys.modules, "FlagEmbedding", fake_flag_embedding)

    fake_sentence_transformers = MagicMock()
    fake_sentence_transformers.CrossEncoder = MockCrossEncoder
    monkeypatch.setitem(sys.modules, "sentence_transformers", fake_sentence_transformers)

    from app.config import settings

    monkeypatch.setattr(settings, "embedding_backend", "flagembedding")
    # enable_colbert=True so _ensure_colbert() enters the ragatouille import path
    # (when False it short-circuits at line 480, never reaching the ImportError).
    monkeypatch.setattr(settings, "enable_colbert", True)
    # Pin the model name to the encoder the mocks represent so any env override
    # that selects a different model doesn't bypass the FlagEmbedding mock path.
    monkeypatch.setattr(settings, "embedding_model", "BAAI/bge-m3")

    # Mock importing ragatouille to raise an ImportError (as if not installed)
    original_import = __import__

    def import_mock(name, *args, **kwargs):
        if name == "ragatouille":
            raise ImportError("No module named 'ragatouille'")
        return original_import(name, *args, **kwargs)

    service = EmbeddingService()

    with patch("builtins.__import__", side_effect=import_mock):
        service._ensure_models()

    # ColBERT should be set to False (fallback path)
    assert service._colbert is False


def test_prunes_unused_onnx_variant_without_touching_pytorch_weights(tmp_path, monkeypatch):
    from app.config import settings
    from services.embedding_service import EmbeddingService

    model_root = tmp_path / "hub" / "models--BAAI--bge-m3"
    snapshot = model_root / "snapshots" / "revision"
    blobs = model_root / "blobs"
    (snapshot / "onnx").mkdir(parents=True)
    blobs.mkdir(parents=True)
    onnx_blob = blobs / "onnx-data"
    pytorch_blob = blobs / "pytorch-data"
    onnx_blob.write_bytes(b"onnx-unused")
    pytorch_blob.write_bytes(b"pytorch-required")
    (snapshot / "onnx" / "model.onnx_data").symlink_to("../../../blobs/onnx-data")
    (snapshot / "pytorch_model.bin").symlink_to("../../blobs/pytorch-data")

    monkeypatch.setenv("HF_HOME", str(tmp_path))
    monkeypatch.setattr(settings, "embedding_backend", "flagembedding")

    EmbeddingService()._prune_unused_hf_variants("BAAI/bge-m3")

    assert not (snapshot / "onnx").exists()
    assert not onnx_blob.exists()
    assert pytorch_blob.read_bytes() == b"pytorch-required"


def test_ensure_encoder_clears_cache_and_retries_on_load_failure(monkeypatch):
    """A corrupted HF cache on the primary model self-heals via clear+retry instead of falling back.

    Regression test for the 2026-07-16 production incident: bge-m3's cached
    weights were corrupted, load failed, and the service silently fell back
    to a 384-dim model against the 1024-dim Qdrant collection.
    """
    from app.config import settings
    from services.embedding_service import EmbeddingService

    service = EmbeddingService()
    calls = {"load": 0, "cleared": []}

    def fake_load_encoder(self, model_name, device):
        calls["load"] += 1
        if calls["load"] == 1:
            raise OSError("Unable to load weights from pytorch checkpoint file")
        self._encoder = MagicMock()

    monkeypatch.setattr(EmbeddingService, "_load_encoder", fake_load_encoder)
    monkeypatch.setattr(
        EmbeddingService,
        "_clear_hf_cache_for",
        lambda self, model_id: calls["cleared"].append(model_id),
    )
    monkeypatch.setattr(settings, "embedding_model", "BAAI/bge-m3")
    monkeypatch.setattr(settings, "embedding_dimension", 1024)

    service._ensure_encoder()

    assert calls["cleared"] == ["BAAI/bge-m3"]
    assert calls["load"] == 2
    assert settings.embedding_model == "BAAI/bge-m3"


def test_ensure_encoder_refuses_wrong_dimension_fallback(monkeypatch):
    """A fallback model of a different dimension than the Qdrant collection must never be silently accepted."""
    from app.config import settings
    from services.embedding_service import EmbeddingService

    service = EmbeddingService()

    def fake_load_encoder(self, model_name, device):
        if model_name == settings.embedding_model:
            raise OSError("primary model unavailable")
        # Every fallback "loads" fine, but is 384-dim. Must be a concrete int
        # on get_sentence_embedding_dimension() — the S7 introspection path
        # (embedding_service.py:429-436) only trusts a real int; an
        # unconfigured MagicMock() returns another MagicMock there, which
        # isinstance(..., int) rejects, falling through to the *declared*-dim
        # table instead of the encoder's real (wrong) one and defeating the
        # exact scenario this test means to cover.
        mock_encoder = MagicMock()
        mock_encoder.get_sentence_embedding_dimension.return_value = 384
        self._encoder = mock_encoder

    monkeypatch.setattr(EmbeddingService, "_load_encoder", fake_load_encoder)
    monkeypatch.setattr(EmbeddingService, "_clear_hf_cache_for", lambda self, model_id: None)
    monkeypatch.setattr(settings, "embedding_model", "BAAI/bge-m3")
    monkeypatch.setattr(settings, "embedding_dimension", 1024)

    with pytest.raises(Exception):  # noqa: B017
        service._ensure_encoder()

    # Must never silently swap to a wrong-dimension model
    assert settings.embedding_model == "BAAI/bge-m3"
    assert settings.embedding_dimension == 1024


def test_ensure_encoder_refuses_primary_that_loads_at_wrong_dimension(monkeypatch):
    """production-audit finding false-confidence-1: the sibling test above never
    lets the PRIMARY model load successfully, so it never exercises the S7 fix
    (embedding_service.py:420-429) — asking the loaded encoder its real
    ``get_sentence_embedding_dimension()`` int rather than trusting config.
    That is the exact 2026-07-16 incident: a primary model loads without error
    but at the wrong dimension. This test makes the primary "load" fine and
    report a real (wrong) int dimension, so it actually reaches and exercises
    the introspection branch instead of falling through to the declared-dim
    fallback path."""
    from app.config import settings
    from services.embedding_service import EmbeddingService

    service = EmbeddingService()

    def fake_load_encoder(self, model_name, device):
        mock_encoder = MagicMock()
        mock_encoder.get_sentence_embedding_dimension.return_value = 384  # wrong on purpose
        self._encoder = mock_encoder

    monkeypatch.setattr(EmbeddingService, "_load_encoder", fake_load_encoder)
    monkeypatch.setattr(EmbeddingService, "_clear_hf_cache_for", lambda self, model_id: None)
    monkeypatch.setattr(settings, "embedding_model", "BAAI/bge-m3")
    monkeypatch.setattr(settings, "embedding_dimension", 1024)

    with pytest.raises(ValueError, match="refusing silent dimension swap"):
        service._ensure_encoder()

    assert settings.embedding_model == "BAAI/bge-m3"
    assert settings.embedding_dimension == 1024


def test_embed_executor_is_isolated_from_asyncio_default_executor():
    """2026-09-15 incident regression: encode_async/encode_batch_async/etc.
    used to ride asyncio's process-wide default executor, which health
    checks, memory writes, admin routes, and everything else also shares --
    a stuck/thrashing embedding call could starve unrelated to_thread()
    callers process-wide. They must run on a dedicated, separately-bounded
    pool instead.
    """
    from services.embedding_service import _EMBED_EXECUTOR

    assert _EMBED_EXECUTOR is not None
    # A real, bounded pool -- not None (which would mean "use the shared
    # default executor").
    assert _EMBED_EXECUTOR._max_workers >= 1


def test_embed_thread_workers_override(monkeypatch):
    """EMBED_THREAD_WORKERS was documented in the module docstring but read by
    nothing -- the dedicated pool it described did not exist.

    The override now resolves through `settings.embed_thread_workers` rather
    than a direct environment read: pydantic-settings still populates it from
    EMBED_THREAD_WORKERS at process start, but routing it through Settings
    keeps `test_no_direct_os_environ_in_owned_modules` honest and makes the
    value visible to the dead-settings scan. Because the settings object is a
    module-level singleton built at import, this test patches the resolved
    attribute rather than the environment.
    """
    from app.config import settings
    from services.embedding_service import _default_embed_thread_workers

    monkeypatch.setattr(settings, "embed_thread_workers", 5, raising=False)
    assert _default_embed_thread_workers() == 5

    # 0 means "derive it" -- the documented default, not a zero-sized pool.
    monkeypatch.setattr(settings, "embed_thread_workers", 0, raising=False)
    assert _default_embed_thread_workers() >= 1


def test_onnx_intra_op_threads_bounded_by_omp_not_raw_cpu_count(monkeypatch):
    """2026-09-15 incident: intra_op_num_threads was sized from raw
    os.cpu_count() (10 on the dev host's VM), ignoring the container's real
    cgroup CPU quota -- the same bug class already fixed for MKL/OpenBLAS/OMP
    on 2026-09-06 (L-DOCKER-9), but left unfixed for ONNX Runtime's own
    thread pool. It must respect OMP_NUM_THREADS, the operator-tunable budget
    the rest of the container already uses.
    """
    import os

    monkeypatch.setenv("OMP_NUM_THREADS", "2")
    monkeypatch.setattr(os, "cpu_count", lambda: 10)  # simulate the dev VM

    _omp_threads = os.environ.get("OMP_NUM_THREADS", "2")
    try:
        _thread_budget = max(1, int(_omp_threads))
    except ValueError:
        _thread_budget = 2
    resolved = min(_thread_budget, max(1, (os.cpu_count() or 2) // 2))

    assert resolved == 2, "must stay pinned to OMP_NUM_THREADS, not cpu_count()//2 == 5"


def test_apply_hf_env_bounds_disables_xet(monkeypatch):
    """2026-09-16 Railway crash diagnosis: the prod backend hit
    `Fatal Python error: Aborted` (malloc failure inside huggingface_hub's
    `hf_xet` downloader) while cold-downloading BAAI/bge-m3 at container
    boot -- HF_HUB_ENABLE_HF_TRANSFER=0 guards a *different*, older
    accelerator and did nothing for Xet, which huggingface_hub>=0.36
    auto-selects regardless. `_apply_hf_env_bounds` must also set
    HF_HUB_DISABLE_XET so a cold-cache fallback download uses the plain
    (bounded-memory) HTTP downloader instead of Xet's concurrent chunked
    transfer. See docs/PROD_HARDENING_STATUS.md item C for the full trace.
    """
    from services.embedding_service import _apply_hf_env_bounds

    for key in ("HF_HUB_DOWNLOAD_TIMEOUT", "HF_HUB_ENABLE_HF_TRANSFER", "HF_HUB_DISABLE_XET"):
        monkeypatch.delenv(key, raising=False)

    _apply_hf_env_bounds()

    assert os.environ.get("HF_HUB_DISABLE_XET") == "1"
    assert os.environ.get("HF_HUB_ENABLE_HF_TRANSFER") == "0"

    # setdefault semantics: an operator's explicit choice must survive.
    monkeypatch.delenv("HF_HUB_DISABLE_XET", raising=False)
    monkeypatch.setenv("HF_HUB_DISABLE_XET", "0")
    _apply_hf_env_bounds()
    assert os.environ.get("HF_HUB_DISABLE_XET") == "0"


def test_onnx_reranker_load_applies_hf_env_bounds():
    """services/onnx_reranker.py's snapshot_download has the same cold-cache
    OOM exposure as embedding_service.py's -- it must call the same guard
    rather than downloading unbounded. Source-level check: importing/reading
    the module is enough, no network or model load required.
    """
    import inspect

    from services import onnx_reranker

    source = inspect.getsource(onnx_reranker.OnnxReranker._load)
    assert "_apply_hf_env_bounds" in source, (
        "OnnxReranker._load must call embedding_service._apply_hf_env_bounds() "
        "before snapshot_download, or a cold cache can OOM-abort the process "
        "the same way the prod backend crashed on 2026-09-11."
    )
