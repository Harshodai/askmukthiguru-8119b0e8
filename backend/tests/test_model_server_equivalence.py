"""Real-model equivalence: client -> model server -> ONNX == the in-process service.

Skips cleanly when the ONNX model files are not on disk (host checkouts); runs
in the backend container, where HF_HOME points at the baked model cache.
One model copy is loaded and used as the server's; the in-process reference is
computed on the same session, bypassing the embedding cache so the server path
and the reference are independent computations of the same inputs.
"""

from __future__ import annotations

import os
import socket
import threading
import time
from pathlib import Path

import pytest
import uvicorn

from app.config import settings
from services.model_server.app import create_app
from services.model_server.client import (
    ModelServerClient,
    RemoteEmbeddingService,
    RemoteOnnxReranker,
)

TOKEN = "equivalence-token"
_HUB = Path(os.environ.get("HF_HOME") or Path.home() / ".cache" / "huggingface") / "hub"
_ENCODER_DIR = _HUB / "models--gpahal--bge-m3-onnx-int8"
_RERANKER_DIR = _HUB / "models--temsa--mmarco-mMiniLMv2-L12-H384-v1-onnx-cpu-qint8"

pytestmark = pytest.mark.skipif(
    not (
        settings.embedding_backend == "onnx_int8"
        and list(_ENCODER_DIR.rglob("*.onnx"))
        and list(_RERANKER_DIR.rglob("*.onnx"))
    ),
    reason="ONNX INT8 backend not configured or BGE-M3 / reranker ONNX files not present",
)

TEXTS = [
    "What is the meaning of karma?",
    "How do I find stillness when my mind is restless?",
    "शांति क्या है?",
    "అంతర్గత శాంతి ఎలా పొందాలి?",
    "a",
    "A longer passage about breathing, awareness and compassion. " * 12,
]
PAIRS = [(TEXTS[0], t) for t in TEXTS] + [(TEXTS[1], t) for t in TEXTS] + [(TEXTS[2], TEXTS[3])]


@pytest.fixture(scope="module")
def stack():
    from services.embedding_service import EmbeddingService
    from services.onnx_reranker import OnnxReranker

    embedding = EmbeddingService()
    embedding._ensure_encoder()
    assert embedding._onnx_session is not None
    reranker = OnnxReranker()
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    server = uvicorn.Server(
        uvicorn.Config(
            create_app(embedding, reranker, TOKEN), host="127.0.0.1", port=port, log_level="error"
        )
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.time() + 30
    while not server.started and time.time() < deadline:
        time.sleep(0.05)
    assert server.started
    client = ModelServerClient(f"http://127.0.0.1:{port}", TOKEN, 60)
    yield embedding, reranker, RemoteEmbeddingService(client), client
    server.should_exit = True
    thread.join(10)


def _reference_batch(embedding, texts):
    prefixed = [f"{embedding.instruction}{t}" for t in texts]
    dense, sparse = embedding._encode_batch_onnx(prefixed, time.monotonic())
    return dense, [{k: float(v) for k, v in row.items()} for row in sparse]


def test_dense_encode_identical(stack):
    embedding, _, remote, _ = stack
    assert remote.encode(TEXTS) == embedding.encode(TEXTS)


def test_dense_and_sparse_encode_batch_identical(stack):
    embedding, _, remote, _ = stack
    got = remote.encode_batch(TEXTS)
    ref_dense, ref_sparse = _reference_batch(embedding, TEXTS)
    assert got["dense"] == ref_dense  # exact float equality, no tolerance
    assert got["sparse"] == ref_sparse
    assert all(isinstance(k, str) for row in got["sparse"] for k in row)


def test_encode_single_full_identical(stack):
    embedding, _, remote, _ = stack
    got = remote.encode_single_full(TEXTS[0])
    ref = embedding.encode_single_full(TEXTS[0])
    assert got["dense"] == ref["dense"]
    assert got["sparse"] == {k: float(v) for k, v in ref["sparse"].items()}


def test_reranker_pairs_identical_across_internal_batching(stack):
    _, reranker, _, client = stack
    assert len(PAIRS) > 8  # crosses OnnxReranker's per-session batch size
    assert RemoteOnnxReranker(client).predict(PAIRS) == reranker.predict(PAIRS)


def test_remote_rerank_matches_in_process_rerank(stack):
    import asyncio

    embedding, reranker, remote, _ = stack
    embedding._reranker, embedding._reranker_outputs_probs = reranker, True
    docs = [{"text": t} for t in TEXTS]

    async def run(svc):
        return await svc.rerank(TEXTS[0], [dict(d) for d in docs], top_k=len(docs), min_score=0.0)

    assert asyncio.run(run(remote)) == asyncio.run(run(embedding))


def test_concurrent_clients_match_reference(stack):
    embedding, reranker, remote, client = stack
    ref_scores = reranker.predict(PAIRS)
    errors: list[str] = []

    def worker(n: int) -> None:
        for i in range(4):
            # unique texts per call so the server's embedding cache cannot answer
            texts = [f"{t} [{n}-{i}]" for t in TEXTS]
            ref_dense, ref_sparse = _reference_batch(embedding, texts)
            got = remote.encode_batch(texts)
            if got["dense"] != ref_dense or got["sparse"] != ref_sparse:
                errors.append("encode_batch")
            if RemoteOnnxReranker(client).predict(PAIRS) != ref_scores:
                errors.append("rerank")

    threads = [threading.Thread(target=worker, args=(n,)) for n in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors
