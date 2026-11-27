"""Shared model server: protocol, auth, failure behaviour, concurrency.

Runs on the host without any model files: the server is driven with fake
models. The real-model equivalence check is tests/test_model_server_equivalence.py.
"""

from __future__ import annotations

import asyncio
import hashlib
import socket
import subprocess
import sys
import threading
import time

import httpx
import numpy as np
import pytest
import uvicorn
from fastapi.testclient import TestClient

import start_railway
from services.circuit_breaker import CircuitOpenException
from services.embedding_service import EmbeddingService
from services.model_server.app import MAX_ITEMS, TOKEN_HEADER, create_app
from services.model_server.client import (
    ModelServerClient,
    ModelServerError,
    RemoteEmbeddingService,
    RemoteOnnxReranker,
)
from services.native_inference_gate import NativeInferenceBusy

TOKEN = "unit-test-token"


def _vec(text: str) -> list[float]:
    seed = int.from_bytes(hashlib.sha256(text.encode()).digest()[:4], "big")
    return np.random.default_rng(seed).random(8, dtype=np.float32).tolist()


class FakeEmbedding:
    """float32-derived dense vectors and numpy-float32 sparse weights, like the real one."""

    def __init__(self, delay: float = 0.0) -> None:
        self.delay = delay
        self.active = 0
        self.max_active = 0
        self._lock = threading.Lock()

    def _work(self) -> None:
        with self._lock:
            self.active += 1
            self.max_active = max(self.max_active, self.active)
        time.sleep(self.delay)
        with self._lock:
            self.active -= 1

    def encode(self, texts):
        self._work()
        return [_vec(t) for t in texts]

    def encode_batch(self, texts):
        self._work()
        sparse = [{str(i + 1): np.float32(0.1 * (len(t) + i + 1))} for i, t in enumerate(texts)]
        return {"dense": [_vec(t) for t in texts], "sparse": sparse}


class OnnxReranker:  # class name matters: EmbeddingService._is_onnx_reranker matches it
    def predict(self, pairs):
        return [float(1 / (1 + np.exp(-(len(q) - len(d))))) for q, d in pairs]


def _remote(app) -> tuple[RemoteEmbeddingService, TestClient]:
    tc = TestClient(app, base_url="http://model-server")
    tc.__enter__()
    return RemoteEmbeddingService(ModelServerClient("http://model-server", TOKEN, 5, http=tc)), tc


@pytest.fixture
def served():
    app = create_app(FakeEmbedding(), OnnxReranker(), TOKEN)
    svc, tc = _remote(app)
    yield svc
    tc.__exit__(None, None, None)


def test_server_refuses_to_start_without_token():
    with pytest.raises(RuntimeError, match="MODEL_SERVER_TOKEN"):
        create_app(FakeEmbedding(), OnnxReranker(), token="")


def test_client_refuses_unconfigured_server():
    with pytest.raises(ModelServerError):
        ModelServerClient("", TOKEN, 5)
    with pytest.raises(ModelServerError):
        ModelServerClient("http://x", "", 5)


@pytest.mark.parametrize("headers", [{}, {TOKEN_HEADER: "wrong"}, {TOKEN_HEADER: TOKEN + "x"}])
def test_auth_required_even_for_malformed_body(headers):
    with TestClient(create_app(FakeEmbedding(), OnnxReranker(), TOKEN)) as tc:
        assert tc.post("/v1/encode", json={"texts": ["q"]}, headers=headers).status_code == 401
        assert tc.post("/v1/rerank", json={"bogus": 1}, headers=headers).status_code == 401
        # unparseable JSON: the token is checked before the body is read
        bad = tc.post("/v1/encode", content=b"{not json", headers=headers)
        assert bad.status_code == 401
        assert tc.get("/healthz").status_code == 200  # carries no data
        ok = tc.post("/v1/encode", json={"texts": ["q"]}, headers={TOKEN_HEADER: TOKEN})
        assert ok.status_code == 200


def test_dense_and_sparse_round_trip_is_exact(served):
    texts = ["what is karma", "stillness", "नमस्ते"]
    ref = FakeEmbedding()
    assert served.encode(texts) == ref.encode(texts)
    got, want = served.encode_batch(texts), ref.encode_batch(texts)
    assert got["dense"] == want["dense"]
    assert [{k: float(v) for k, v in row.items()} for row in want["sparse"]] == got["sparse"]
    assert all(isinstance(k, str) for row in got["sparse"] for k in row)
    assert served.encode([]) == [] and served.encode_batch([]) == {"dense": [], "sparse": []}


def test_inputs_larger_than_the_request_cap_are_sliced(served):
    texts = [f"t{i}" for i in range(MAX_ITEMS * 2 + 5)]
    assert served.encode(texts) == FakeEmbedding().encode(texts)
    assert len(served.encode_batch(texts)["sparse"]) == len(texts)


def test_encode_single_full_uses_server_with_query_expansion(served):
    out = served.encode_single_full("karma")
    assert set(out) == {"dense", "sparse"} and len(out["dense"]) == 8


def test_rerank_matches_in_process_rerank(served):
    local = EmbeddingService()
    local._reranker = OnnxReranker()
    local._reranker_outputs_probs = True
    docs = [{"text": t} for t in ["a", "a longer passage here", "mid length", "x" * 40]]

    async def run(svc):
        return await svc.rerank("query text", [dict(d) for d in docs], top_k=4, min_score=0.0)

    assert asyncio.run(run(served)) == asyncio.run(run(local))
    scorer = RemoteOnnxReranker(served._remote)
    pairs = [("q", "d1"), ("query", "d")]
    assert scorer.predict(pairs) == OnnxReranker().predict(pairs)
    assert scorer.predict([]) == []


def test_unsupported_in_process_only_ops_raise(served):
    with pytest.raises(NotImplementedError):
        served.encode_with_colbert(["x"])
    with pytest.raises(NotImplementedError):
        served.encode_late_chunked("doc", [(0, 1)])
    with pytest.raises(NotImplementedError):
        served.encode_query_mean_pooled("q")


def test_server_error_raises_and_never_falls_back_in_process():
    class Boom(FakeEmbedding):
        def encode_batch(self, texts):
            raise ValueError("secret seeker question must not leak")

    app = create_app(Boom(), OnnxReranker(), TOKEN)
    tc = TestClient(app, base_url="http://model-server", raise_server_exceptions=False)
    with tc:
        svc = RemoteEmbeddingService(ModelServerClient("http://m", TOKEN, 5, http=tc))
        with pytest.raises(ModelServerError) as err:
            svc.encode_batch(["x"])
        assert err.value.status == 500
        assert "secret seeker question" not in str(err.value)
        assert svc._onnx_session is None  # nothing was loaded locally


def test_unreachable_server_raises_clear_error():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    svc = RemoteEmbeddingService(ModelServerClient(f"http://127.0.0.1:{port}", TOKEN, 2))
    with pytest.raises(ModelServerError, match="unreachable"):
        svc.encode(["x"])
    with pytest.raises(ModelServerError):
        svc.warm_up()


def test_timeout_raises_and_is_not_retried():
    calls: list[int] = []

    def slow(_request):
        calls.append(1)
        raise httpx.ReadTimeout("slow")

    http = httpx.Client(base_url="http://m", transport=httpx.MockTransport(slow))
    with pytest.raises(ModelServerError, match="ReadTimeout"):
        ModelServerClient("http://m", TOKEN, 1, http=http).post("/v1/encode", {"texts": ["x"]})
    assert len(calls) == 1


def test_request_text_is_never_logged(caplog):
    caplog.set_level("DEBUG")
    app = create_app(FakeEmbedding(), OnnxReranker(), TOKEN)
    svc, tc = _remote(app)
    svc.encode_batch(["very private seeker question"])
    svc.encode(["very private seeker question"])
    tc.__exit__(None, None, None)
    assert "very private seeker question" not in caplog.text


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_concurrent_clients_get_their_own_correct_results():
    fake = FakeEmbedding(delay=0.02)
    port = _free_port()
    server = uvicorn.Server(
        uvicorn.Config(
            create_app(fake, OnnxReranker(), TOKEN), host="127.0.0.1", port=port, log_level="error"
        )
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.time() + 10
    while not server.started and time.time() < deadline:
        time.sleep(0.02)
    assert server.started
    svc = RemoteEmbeddingService(ModelServerClient(f"http://127.0.0.1:{port}", TOKEN, 10))
    errors: list[str] = []

    def worker(n: int) -> None:
        for i in range(5):
            text = f"client {n} question {i}"
            got = svc.encode_batch([text, text + "!"])
            if got["dense"] != [_vec(text), _vec(text + "!")]:
                errors.append(text)

    threads = [threading.Thread(target=worker, args=(n,)) for n in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    server.should_exit = True
    thread.join(5)
    assert not errors
    assert fake.max_active > 1  # requests really were served concurrently


# onnxruntime itself may be imported by qdrant_client->fastembed; that loads no model.
def test_api_process_in_model_server_mode_imports_no_model_stack():
    code = (
        "import sys;"
        "from app.config import settings;"
        "settings.model_server_url='http://m';settings.model_server_token='t';"
        "from services.embedding_service import get_embedding_service;"
        "from services.reranker_service import RerankerService;"
        "svc=get_embedding_service();"
        "assert type(svc).__name__=='RemoteEmbeddingService', type(svc);"
        "r=RerankerService();r._load_fallback();"
        "assert getattr(r._fallback_reranker,'is_remote',False);"
        "bad=[m for m in ('torch','transformers','sentence_transformers') if m in sys.modules];"
        "assert not bad, bad;print('ok')"
    )
    proc = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, timeout=120, cwd="."
    )
    assert proc.returncode == 0, proc.stderr[-2000:]


def test_model_duplication_warning_only_when_workers_exceed_one_without_server():
    assert start_railway.model_duplication_warning(1, "") is None
    assert start_railway.model_duplication_warning(3, "http://model-server:8000") is None
    msg = start_railway.model_duplication_warning(2, "")
    assert msg and "WEB_CONCURRENCY=2" in msg and "2.5 GB" in msg and "model-server" in msg


def test_valid_token_with_malformed_body_is_a_validation_error_not_auth():
    with TestClient(create_app(FakeEmbedding(), OnnxReranker(), TOKEN)) as tc:
        resp = tc.post("/v1/encode", content=b"{not json", headers={TOKEN_HEADER: TOKEN})
        assert resp.status_code == 422


def _breaker_after(exc: Exception, calls: int = 8):
    class Failing(FakeEmbedding):
        def encode_batch(self, texts):
            raise exc

    app = create_app(Failing(), OnnxReranker(), TOKEN)
    tc = TestClient(app, base_url="http://model-server", raise_server_exceptions=False)
    with tc:
        svc = RemoteEmbeddingService(ModelServerClient("http://m", TOKEN, 5, http=tc))
        outcomes = []
        for _ in range(calls):
            try:
                svc.encode_batch(["x"])
            except (ModelServerError, CircuitOpenException) as err:
                outcomes.append(err)
        return svc, outcomes


def test_busy_503_fails_loudly_but_never_opens_the_breaker():
    svc, outcomes = _breaker_after(NativeInferenceBusy("slot"))
    assert len(outcomes) == 8
    assert all(isinstance(e, ModelServerError) and e.status == 503 for e in outcomes)
    assert svc._circuit.can_execute()  # threshold is 5; 8 busy replies did not trip it


def test_genuine_server_errors_still_open_the_breaker():
    svc, outcomes = _breaker_after(ValueError("boom"))
    assert any(isinstance(e, CircuitOpenException) for e in outcomes)
    assert not svc._circuit.can_execute()


def test_colbert_with_model_server_fails_at_settings_load():
    from app.config import Settings

    with pytest.raises(ValueError, match="ENABLE_COLBERT"):
        Settings(model_server_url="http://m", model_server_token="t", enable_colbert=True)
    with pytest.raises(ValueError, match="MODEL_SERVER_TOKEN"):
        Settings(model_server_url="http://m", model_server_token="")
    Settings(model_server_url="http://m", model_server_token="t", enable_colbert=False)
