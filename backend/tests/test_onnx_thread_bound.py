"""A1 guard: ONNX embedding session must bound threads + reuse singleton.

Root cause: EmbeddingService._load_onnx_encoder created
ort.InferenceSession(model_file, providers=[...]) with default
SessionOptions (intra_op_num_threads=0 = all physical cores). Under
asyncio.to_thread concurrency each request spawns a full-core Eigen
pool -> oversubscription. Reference fix: onnx_reranker.py:127-129.
Second fault: no module-level singleton, so repeated
EmbeddingService() re-loads the 570MB model per instance.
"""

from __future__ import annotations

import importlib


def _load_module():
    try:
        return importlib.import_module("services.embedding_service")
    except ImportError:
        return importlib.import_module("backend.services.embedding_service")


def test_embedding_session_bounded():
    m = _load_module()
    src = open(m.__file__).read()
    assert "intra_op_num_threads" in src, "missing intra_op_num_threads bound"
    assert "inter_op_num_threads" in src, "missing inter_op_num_threads bound"


def test_embedding_session_singleton():
    m = _load_module()
    src = open(m.__file__).read()
    assert "get_embedding_service" in src or "_EMBEDDING_SERVICE_SINGLETON" in src or "_instance" in src, (
        "missing module-level singleton accessor for EmbeddingService"
    )
