"""Unit tests for BenchmarkSessionPool (Invariant B1)."""

import asyncio
import pytest
import httpx
from unittest.mock import AsyncMock, MagicMock
from evaluation.session_pool import BenchmarkSessionPool


@pytest.mark.asyncio
async def test_session_pool_warmup_and_lease():
    # Mock httpx client
    mock_client = AsyncMock()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"token": "test_hmac_token_12345", "session_id": "test_hmac_token_12345"}
    mock_resp.raise_for_status = MagicMock()
    mock_client.post.return_value = mock_resp

    pool = BenchmarkSessionPool(
        endpoint="http://localhost:8000",
        pool_size=2,
        client=mock_client,
        warmup_delay_s=0.01,  # Fast for test
    )

    minted = await pool.warm_up()
    assert minted == 2
    assert pool.is_warmed is True
    assert pool.available_count == 2

    # Lease session 1
    async with pool.acquire_session() as token1:
        assert token1 == "test_hmac_token_12345"
        assert pool.available_count == 1

    # Returned after exit
    assert pool.available_count == 2


@pytest.mark.asyncio
async def test_session_pool_add_token_manually():
    pool = BenchmarkSessionPool(endpoint="http://localhost:8000", pool_size=1)
    pool.add_token("manual_token_abc")
    assert pool.available_count == 1
    assert pool.is_warmed is True

    async with pool.acquire_session() as t:
        assert t == "manual_token_abc"
