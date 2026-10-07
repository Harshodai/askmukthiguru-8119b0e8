"""Unit tests for IETF RFC IdempotencyMiddleware."""

from unittest.mock import AsyncMock, patch

import pytest
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from app.middleware.idempotency import IdempotencyMiddleware


async def feedback_endpoint(request: Request):
    data = await request.json()
    return JSONResponse({"status": "received", "data": data}, status_code=200)


def create_test_app(mock_redis):
    app = Starlette(
        routes=[
            Route("/api/feedback", feedback_endpoint, methods=["POST"]),
        ]
    )
    middleware = IdempotencyMiddleware(app, idempotent_paths=["/api/feedback"])
    middleware._redis = mock_redis
    app.add_middleware(IdempotencyMiddleware, idempotent_paths=["/api/feedback"])
    return app, middleware


@pytest.mark.asyncio
async def test_idempotency_fresh_request_and_replay():
    cache = {}

    mock_redis = AsyncMock()

    async def get_mock(key):
        return cache.get(key)

    async def set_mock(key, val, nx=False, px=None):
        if nx and key in cache:
            return False
        cache[key] = val
        return True

    async def setex_mock(key, ttl, val):
        cache[key] = val
        return True

    async def delete_mock(key):
        cache.pop(key, None)
        return True

    mock_redis.get.side_effect = get_mock
    mock_redis.set.side_effect = set_mock
    mock_redis.setex.side_effect = setex_mock
    mock_redis.delete.side_effect = delete_mock

    app, middleware = create_test_app(mock_redis)

    with patch.object(IdempotencyMiddleware, "_get_redis", return_value=mock_redis):
        client = TestClient(app)

        # 1. Fresh request
        headers = {"Idempotency-Key": "test-key-1"}
        payload = {"rating": 5, "comment": "Excellent guidance"}
        res1 = client.post("/api/feedback", json=payload, headers=headers)
        assert res1.status_code == 200
        assert res1.json()["data"]["rating"] == 5
        assert "X-Idempotent-Replayed" not in res1.headers

        # 2. Replayed identical request
        res2 = client.post("/api/feedback", json=payload, headers=headers)
        assert res2.status_code == 200
        assert res2.json()["data"]["rating"] == 5
        assert res2.headers.get("x-idempotent-replayed") == "true"

        # 3. Reused key with DIFFERENT payload -> 422 Unprocessable Entity
        payload_different = {"rating": 1, "comment": "Changed my mind"}
        res3 = client.post("/api/feedback", json=payload_different, headers=headers)
        assert res3.status_code == 422
        assert "Fingerprint-Mismatch" in res3.headers.get("x-idempotency-error", "")


@pytest.mark.asyncio
async def test_idempotency_concurrent_in_progress_returns_409():
    mock_redis = AsyncMock()
    mock_redis.get.return_value = None
    # set nx returns False -> lock already held by another request in flight
    mock_redis.set.return_value = False

    app, _ = create_test_app(mock_redis)

    with patch.object(IdempotencyMiddleware, "_get_redis", return_value=mock_redis):
        client = TestClient(app)
        headers = {"Idempotency-Key": "test-concurrent-key"}
        payload = {"rating": 5}
        res = client.post("/api/feedback", json=payload, headers=headers)
        assert res.status_code == 409
        assert "in progress" in res.json().get("error", "")


@pytest.mark.asyncio
async def test_idempotency_key_is_scoped_per_caller():
    """Another user presenting the same Idempotency-Key and payload must NOT be
    replayed the first user's stored response."""
    cache = {}
    mock_redis = AsyncMock()

    async def get_mock(key):
        return cache.get(key)

    async def set_mock(key, val, nx=False, px=None):
        if nx and key in cache:
            return False
        cache[key] = val
        return True

    async def setex_mock(key, ttl, val):
        cache[key] = val
        return True

    async def delete_mock(key):
        cache.pop(key, None)
        return True

    mock_redis.get.side_effect = get_mock
    mock_redis.set.side_effect = set_mock
    mock_redis.setex.side_effect = setex_mock
    mock_redis.delete.side_effect = delete_mock
    app, _ = create_test_app(mock_redis)

    with patch.object(IdempotencyMiddleware, "_get_redis", return_value=mock_redis):
        client = TestClient(app)
        payload = {"rating": 5}
        a = {"Idempotency-Key": "shared-key", "Authorization": "Bearer user-a"}
        b = {"Idempotency-Key": "shared-key", "Authorization": "Bearer user-b"}
        assert client.post("/api/feedback", json=payload, headers=a).status_code == 200
        res_b = client.post("/api/feedback", json=payload, headers=b)
        assert res_b.status_code == 200
        assert "x-idempotent-replayed" not in res_b.headers
        res_a = client.post("/api/feedback", json=payload, headers=a)
        assert res_a.headers.get("x-idempotent-replayed") == "true"
