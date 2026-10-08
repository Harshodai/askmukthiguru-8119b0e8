"""L-LLM-429-RETRY-1: backoff honours Retry-After, is capped, and never zero."""
import httpx

from services.openrouter_service import OpenRouterService as S


def _exc(headers):
    req = httpx.Request("POST", "https://x")
    return httpx.HTTPStatusError("429", request=req, response=httpx.Response(429, headers=headers, request=req))


def test_retry_after_header_used():
    assert S._rate_limit_backoff_s(_exc({"retry-after": "3"}), 0) == 3.0


def test_capped():
    assert S._rate_limit_backoff_s(_exc({"retry-after": "120"}), 0) == 8.0


def test_exponential_without_header():
    assert S._rate_limit_backoff_s(_exc({}), 0) == 1.0
    assert S._rate_limit_backoff_s(_exc({}), 2) == 4.0


def test_garbage_header_falls_back():
    assert S._rate_limit_backoff_s(_exc({"retry-after": "soon"}), 1) == 2.0
