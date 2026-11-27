"""Client for the shared model server (``settings.model_server_url``).

``RemoteEmbeddingService`` is an ``EmbeddingService`` whose encoder and
reranker live in another process; ``get_embedding_service()`` returns it when
``MODEL_SERVER_URL`` is set. It inherits the real class's query expansion,
async wrappers and ``rerank()`` post-processing unchanged and only swaps the
three model calls (dense encode, dense+sparse encode, pair scoring) for HTTP.

No silent fallback: if the server is unreachable, slow or refuses the token,
the call RAISES ``ModelServerError``. Falling back to loading the models
in-process would quietly bring back the per-worker memory cost this mode exists
to remove. This module must stay importable without torch/transformers/ORT.
"""

from __future__ import annotations

import logging
import threading
from typing import Any, Optional

import httpx

from app.config import settings
from services.circuit_breaker import CircuitOpenException
from services.embedding_service import EmbeddingService
from services.model_server.app import MAX_ITEMS, TOKEN_HEADER

logger = logging.getLogger(__name__)

_NOT_SERVED = (
    "{} is not served by the model server (late chunking / ColBERT run in-process "
    "in the ingestion tooling); run it with MODEL_SERVER_URL unset"
)


class ModelServerError(RuntimeError):
    """The model server could not complete a call. ``status`` is None for transport errors."""

    def __init__(self, message: str, status: Optional[int] = None) -> None:
        super().__init__(message)
        self.status = status


class ModelServerClient:
    """Pooled, thread-safe httpx wrapper. Request text is never logged."""

    def __init__(
        self,
        base_url: str,
        token: str,
        timeout_s: float,
        http: Optional[httpx.Client] = None,
    ) -> None:
        if not base_url or not token:
            raise ModelServerError("MODEL_SERVER_URL and MODEL_SERVER_TOKEN must both be set")
        self._http = http or httpx.Client(
            base_url=base_url.rstrip("/"),
            timeout=httpx.Timeout(timeout_s, connect=min(5.0, timeout_s)),
            limits=httpx.Limits(max_connections=32, max_keepalive_connections=16),
        )
        self._headers = {TOKEN_HEADER: token}
        self._base_url = base_url

    def post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        # One retry on a dropped keep-alive connection; the calls are pure, so
        # a replay is safe. Timeouts are NOT retried (it would double the wait).
        for attempt in (1, 2):
            try:
                resp = self._http.post(path, json=payload, headers=self._headers)
                break
            except (httpx.RemoteProtocolError, httpx.ConnectError) as exc:
                if attempt == 2:
                    raise ModelServerError(
                        f"model server unreachable at {self._base_url}: {type(exc).__name__}"
                    ) from exc
            except httpx.HTTPError as exc:
                raise ModelServerError(f"model server call failed: {type(exc).__name__}") from exc
        if resp.status_code != 200:
            raise ModelServerError(
                f"model server {path} returned HTTP {resp.status_code}", resp.status_code
            )
        return resp.json()

    def healthz(self) -> None:
        try:
            resp = self._http.get("/healthz")
        except httpx.HTTPError as exc:
            raise ModelServerError(
                f"model server unreachable at {self._base_url}: {type(exc).__name__}"
            ) from exc
        if resp.status_code != 200:
            raise ModelServerError(
                f"model server unhealthy: HTTP {resp.status_code}", resp.status_code
            )


_client: Optional[ModelServerClient] = None
_client_lock = threading.Lock()


def get_client() -> ModelServerClient:
    """One pooled client per process, shared by the embedder and the reranker."""
    global _client
    if _client is None:
        with _client_lock:
            if _client is None:
                _client = ModelServerClient(
                    settings.model_server_url,
                    settings.model_server_token or "",
                    settings.model_server_timeout_s,
                )
    return _client


def _slices(items: list, size: int = MAX_ITEMS):
    for start in range(0, len(items), size):
        yield items[start : start + size]


class RemoteOnnxReranker:
    """Drop-in for ``OnnxReranker.predict`` (sigmoid probabilities in [0, 1])."""

    is_remote = True

    def __init__(self, client: Optional[ModelServerClient] = None) -> None:
        self._remote = client or get_client()

    def predict(self, pairs: list[tuple[str, str]]) -> list[float]:
        scores: list[float] = []
        for part in _slices([[q, d] for q, d in pairs]):
            scores.extend(self._remote.post("/v1/rerank", {"pairs": part})["scores"])
        return scores

    def predict_single(self, query: str, doc: str) -> float:
        return self.predict([(query, doc)])[0]


def make_onnx_reranker(model_id: str) -> Any:
    """In-process ``OnnxReranker`` normally; the remote one when a server is configured."""
    if settings.model_server_url:
        return RemoteOnnxReranker()
    from services.onnx_reranker import OnnxReranker

    return OnnxReranker(model_id=model_id)


class RemoteEmbeddingService(EmbeddingService):
    """``EmbeddingService`` with the encoder and reranker behind the model server."""

    def __init__(self, client: Optional[ModelServerClient] = None) -> None:
        super().__init__()
        self._remote = client or get_client()

    def _call(self, path: str, texts: list[str]) -> dict[str, Any]:
        if not self._circuit.can_execute():
            raise CircuitOpenException(
                provider="embedding",
                message="Circuit breaker OPEN for embedding (model server) — failing fast",
            )
        try:
            out = self._remote.post(path, {"texts": texts})
        except ModelServerError as exc:
            # A 503 is the server shedding load (inference gate busy / its own
            # breaker open), not a broken server: the request still fails
            # loudly, but overload must not open this breaker and turn a burst
            # into an outage. Transport errors, timeouts and other 5xx count.
            if exc.status is None or (exc.status >= 500 and exc.status != 503):
                self._circuit.record_failure()
            raise
        self._circuit.record_success()
        return out

    def _call_sliced(self, path: str, texts: list[str], keys: tuple[str, ...]) -> dict[str, list]:
        merged: dict[str, list] = {k: [] for k in keys}
        for part in _slices(texts):
            out = self._call(path, part)
            for k in keys:
                merged[k].extend(out[k])
        return merged

    def warm_up(self) -> None:
        self._remote.healthz()

    def _ensure_encoder(self) -> None:  # models live in the server
        return None

    def _ensure_reranker(self) -> None:
        if self._reranker is None:
            self._reranker = RemoteOnnxReranker(self._remote)
            self._reranker_outputs_probs = True  # the server applies the sigmoid

    def _is_onnx_reranker(self) -> bool:
        return True

    def encode(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        return self._call_sliced("/v1/encode", texts, ("dense",))["dense"]

    def encode_batch(self, texts: list[str]) -> dict:
        if not texts:
            return {"dense": [], "sparse": []}
        return self._call_sliced("/v1/encode_batch", texts, ("dense", "sparse"))

    def encode_with_colbert(self, texts: list[str]) -> dict:
        raise NotImplementedError(_NOT_SERVED.format("encode_with_colbert"))

    def encode_late_chunked(self, document: str, spans: list[tuple[int, int]]) -> list:
        raise NotImplementedError(_NOT_SERVED.format("encode_late_chunked"))

    def encode_query_mean_pooled(self, query: str) -> list[float]:
        raise NotImplementedError(_NOT_SERVED.format("encode_query_mean_pooled"))


if __name__ == "__main__":
    try:
        ModelServerClient("", "")
    except ModelServerError as exc:
        print("PASS - client refuses an unconfigured server:", exc)
