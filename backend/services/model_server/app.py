"""Model-server FastAPI app (SERVICE_TYPE=model-server, opt-in).

Loads the ONNX INT8 BGE-M3 encoder and the ONNX INT8 reranker ONCE and exposes
exactly the operations the backend calls, so several API workers can share one
copy of the models instead of each holding ~2 GB. Private-network only by
design: every route except /healthz needs the shared secret
(``MODEL_SERVER_TOKEN``) in the ``X-Model-Server-Token`` header, compared in
constant time before the body is read. The server refuses to start without a token.

Privacy: request bodies are seeker questions. This module never logs them and
never echoes exception text back (clients get the exception class name only).

Concurrency: routes are sync ``def`` so FastAPI runs them in its threadpool.
ONNX ``InferenceSession.run`` is thread-safe and the existing process-wide
``native_inference`` gate (inside the services) bounds concurrent native
allocations, so no extra lock is added here.
"""

from __future__ import annotations

import hmac
import logging
from contextlib import asynccontextmanager
from typing import Any, Optional

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.config import settings
from services.circuit_breaker import CircuitOpenException
from services.native_inference_gate import NativeInferenceBusy

logger = logging.getLogger(__name__)

TOKEN_HEADER = "X-Model-Server-Token"
# Per-request item cap; the client slices larger inputs to stay under it.
MAX_ITEMS = 512


class TextsIn(BaseModel):
    texts: list[str] = Field(max_length=MAX_ITEMS)


class PairsIn(BaseModel):
    pairs: list[tuple[str, str]] = Field(max_length=MAX_ITEMS)


def load_models() -> tuple[Any, Any]:
    """Load the real encoder and reranker (once). Refuses a torch fallback."""
    from services.embedding_service import EmbeddingService
    from services.onnx_reranker import OnnxReranker

    embedding = EmbeddingService()
    embedding._ensure_encoder()
    if embedding._onnx_session is None:
        raise RuntimeError(
            "model server needs the ONNX INT8 encoder; the encoder fell back to "
            "another backend, refusing to serve it"
        )
    reranker = OnnxReranker(model_id=settings.reranker_onnx_model)
    return embedding, reranker


def create_app(embedding: Any = None, reranker: Any = None, token: Optional[str] = None) -> FastAPI:
    """Build the app. Models/token are injectable for tests; default = real ones."""
    secret = token if token is not None else settings.model_server_token
    if not secret:
        raise RuntimeError("MODEL_SERVER_TOKEN is required to run the model server")
    secret_bytes = secret.encode("utf-8")
    state: dict[str, Any] = {"embedding": embedding, "reranker": reranker}

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        if state["embedding"] is None or state["reranker"] is None:
            state["embedding"], state["reranker"] = load_models()
        logger.info("Model server ready (encoder + reranker loaded)")
        yield

    app = FastAPI(
        title="Mukthi Guru model server", lifespan=lifespan, docs_url=None, redoc_url=None
    )

    @app.middleware("http")
    async def require_token(request: Request, call_next):
        # Middleware, not a route dependency: it runs before FastAPI reads or
        # parses the body, so an unauthenticated request never reaches JSON
        # decoding or validation (a malformed body gets 401, not 422).
        if request.url.path.startswith("/v1/"):
            supplied = request.headers.get(TOKEN_HEADER, "").encode("utf-8")
            if not hmac.compare_digest(supplied, secret_bytes):
                return JSONResponse({"error": "invalid token"}, status_code=401)
        return await call_next(request)

    @app.exception_handler(NativeInferenceBusy)
    async def _busy(_req: Request, _exc: NativeInferenceBusy) -> JSONResponse:
        return JSONResponse({"error": "NativeInferenceBusy"}, status_code=503)

    @app.exception_handler(CircuitOpenException)
    async def _circuit_open(_req: Request, _exc: CircuitOpenException) -> JSONResponse:
        return JSONResponse({"error": "CircuitOpen"}, status_code=503)

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/v1/encode")
    def encode(body: TextsIn) -> dict[str, Any]:
        return {"dense": state["embedding"].encode(body.texts)}

    @app.post("/v1/encode_batch")
    def encode_batch(body: TextsIn) -> dict[str, Any]:
        out = state["embedding"].encode_batch(body.texts)
        # Sparse weights are numpy float32 in-process; float() is lossless.
        sparse = [{k: float(v) for k, v in row.items()} for row in out["sparse"]]
        return {"dense": out["dense"], "sparse": sparse}

    @app.post("/v1/rerank")
    def rerank(body: PairsIn) -> dict[str, Any]:
        return {"scores": state["reranker"].predict([(q, d) for q, d in body.pairs])}

    return app


if __name__ == "__main__":
    try:
        create_app(token="")
    except RuntimeError as exc:
        print("PASS - refuses to start without a token:", exc)
