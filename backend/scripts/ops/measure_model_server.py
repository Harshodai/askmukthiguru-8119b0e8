"""Measure the shared model server: RSS and added per-call latency (read-only).

Run inside the backend image, from backend/ (models come from HF_HOME). Modes:

  server           start the model server on 127.0.0.1:PORT (blocks)
  api-rss          import the API in model-server mode, build the embedder and
                   reranker, report RSS and whether torch/transformers loaded
  inproc-rss       load the in-process EmbeddingService + OnnxReranker, report RSS
  fake-server      server with zero-compute fake models returning real-shaped payloads
                   (1024-d dense, ~25 sparse entries): isolates the transport cost
                   added per call, no model memory needed
  latency-inproc   per-call latency of encode / rerank with in-process models
  latency-remote   the same calls through the server (run `server` first); run
                   the two latency modes separately so models are never doubled

Usage:  MODEL_SERVER_TOKEN=t python scripts/ops/measure_model_server.py server 8765
        MODEL_SERVER_URL=http://127.0.0.1:8765 MODEL_SERVER_TOKEN=t \
            python scripts/ops/measure_model_server.py api-rss
"""

from __future__ import annotations

import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import psutil  # noqa: E402

QUERY = "How do I find stillness when my mind is restless and full of worry?"
DOCS = [f"Passage {i}: awareness, breath and compassion in daily life. " * 8 for i in range(12)]


def rss_mb() -> float:
    return psutil.Process().memory_info().rss / 1e6


def report_rss(label: str) -> None:
    heavy = [m for m in ("torch", "transformers", "onnxruntime") if m in sys.modules]
    print(f"{label}: RSS={rss_mb():.0f} MB heavy_modules_imported={heavy}")


def pct(values: list[float], q: float) -> float:
    return sorted(values)[min(len(values) - 1, int(len(values) * q))]


def timed(fn, n: int = 60) -> list[float]:
    for _ in range(5):
        fn()
    out = []
    for _ in range(n):
        t0 = time.perf_counter()
        fn()
        out.append((time.perf_counter() - t0) * 1000)
    return out


def summarize(name: str, ms: list[float]) -> None:
    print(f"{name}: p50={statistics.median(ms):.1f} ms p95={pct(ms, 0.95):.1f} ms n={len(ms)}")


def main() -> None:
    mode = sys.argv[1]
    if mode == "server":
        import uvicorn

        from services.model_server.app import create_app

        uvicorn.run(create_app(), host="127.0.0.1", port=int(sys.argv[2]), log_level="warning")
    elif mode == "fake-server":
        import numpy as np
        import uvicorn

        from services.model_server.app import create_app

        rng = np.random.default_rng(0)

        class FakeEmbedding:
            def encode(self, texts):
                return [rng.random(1024, dtype=np.float32).tolist() for _ in texts]

            def encode_batch(self, texts):
                sparse = [{str(i): np.float32(0.5) for i in range(25)} for _ in texts]
                return {"dense": self.encode(texts), "sparse": sparse}

        class FakeReranker:
            def predict(self, pairs):
                return rng.random(len(pairs)).tolist()

        uvicorn.run(
            create_app(FakeEmbedding(), FakeReranker()),
            host="127.0.0.1",
            port=int(sys.argv[2]),
            log_level="warning",
        )
    elif mode == "api-rss":
        from services.embedding_service import get_embedding_service
        from services.reranker_service import RerankerService

        svc = get_embedding_service()
        rr = RerankerService()
        rr.warm_up()
        svc.warm_up()
        svc.encode_single_full(QUERY)
        report_rss("api process, model-server mode")
        print("embedder class:", type(svc).__name__)
    elif mode == "inproc-rss":
        from services.embedding_service import EmbeddingService
        from services.onnx_reranker import OnnxReranker

        emb = EmbeddingService()
        emb.encode_single_full(QUERY)
        rr = OnnxReranker()
        rr.predict([(QUERY, DOCS[0])])
        report_rss("in-process models")
    elif mode in ("latency-inproc", "latency-remote"):
        import uuid

        pairs = [(QUERY, d) for d in DOCS]
        # unique text per call so the embedding cache cannot answer
        fresh = lambda: uuid.uuid4().hex + QUERY  # noqa: E731
        if mode == "latency-inproc":
            from services.embedding_service import EmbeddingService
            from services.onnx_reranker import OnnxReranker

            emb, rr = EmbeddingService(), OnnxReranker()
            summarize("embed in-process", timed(lambda: emb.encode_single_full(fresh())))
            summarize("rerank 12 pairs in-process", timed(lambda: rr.predict(pairs)))
        else:
            from services.model_server.client import RemoteEmbeddingService, RemoteOnnxReranker

            emb, rr = RemoteEmbeddingService(), RemoteOnnxReranker()
            summarize("embed via server", timed(lambda: emb.encode_single_full(fresh())))
            summarize(
                "embed via server, server cache hit", timed(lambda: emb.encode_single_full(QUERY))
            )
            summarize("rerank 12 pairs via server", timed(lambda: rr.predict(pairs)))
        report_rss(mode)
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main()
