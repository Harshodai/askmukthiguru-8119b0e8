"""Regression tests for Settings validation."""

from __future__ import annotations

import pytest

from app.config import Settings


def test_sarvam_cloud_requires_api_key():
    with pytest.raises(ValueError, match="sarvam_api_key is required"):
        Settings(llm_provider="sarvam_cloud", sarvam_api_key="")


def test_openrouter_requires_api_key():
    with pytest.raises(ValueError, match="openrouter_api_key is required"):
        Settings(llm_provider="openrouter", openrouter_api_key="")


def test_anthropic_requires_api_key():
    with pytest.raises(ValueError, match="anthropic_api_key is required"):
        Settings(llm_provider="anthropic", anthropic_api_key="")


def test_krutrim_requires_api_key():
    with pytest.raises(ValueError, match="krutrim_api_key is required"):
        Settings(llm_provider="krutrim", krutrim_api_key="")


def test_emergent_requires_api_key():
    with pytest.raises(ValueError, match="emergent_llm_key is required"):
        Settings(llm_provider="emergent", emergent_llm_key="")


def test_sarvam_cloud_accepts_api_key():
    settings = Settings(llm_provider="sarvam_cloud", sarvam_api_key="valid-key")
    assert settings.llm_provider == "sarvam_cloud"


def test_ollama_does_not_require_external_key():
    settings = Settings(llm_provider="ollama")
    assert settings.llm_provider == "ollama"


def test_http_pool_limits_normalization():
    s1 = Settings(http_pool_max_connections=50.5, http_pool_max_keepalive="10.5")
    assert s1.http_pool_max_connections == 50
    assert s1.http_pool_max_keepalive == 20

    s2 = Settings(http_pool_max_connections="nan", http_pool_max_keepalive="inf")
    assert s2.http_pool_max_connections == 50
    assert s2.http_pool_max_keepalive == 20

    s3 = Settings(http_pool_max_connections=0, http_pool_max_keepalive=-5)
    assert s3.http_pool_max_connections == 50
    assert s3.http_pool_max_keepalive == 20

    s4 = Settings(http_pool_max_connections=10, http_pool_max_keepalive=15)
    assert s4.http_pool_max_connections == 10
    assert s4.http_pool_max_keepalive == 10


def test_max_concurrent_chat_rejects_zero_and_negative():
    """max_concurrent_chat=0 or negative must raise ValidationError at startup."""
    from pydantic import ValidationError

    for bad_value in (0, -1, -100):
        with pytest.raises(ValidationError, match="max_concurrent_chat"):
            Settings(max_concurrent_chat=bad_value)


def test_max_concurrent_chat_accepts_positive():
    """max_concurrent_chat accepts any positive integer."""
    s = Settings(max_concurrent_chat=1)
    assert s.max_concurrent_chat == 1

    s = Settings(max_concurrent_chat=20)
    assert s.max_concurrent_chat == 20


def test_embedding_dimension_validation():
    # bge-m3 requires 1024d
    with pytest.raises(ValueError, match="requires embedding_dimension=1024"):
        Settings(embedding_model="BAAI/bge-m3", embedding_dimension=384)

    # e5-small requires 384d
    with pytest.raises(ValueError, match="requires embedding_dimension=384"):
        Settings(embedding_model="intfloat/e5-small", embedding_dimension=1024)

    s_bge = Settings(embedding_model="BAAI/bge-m3", embedding_dimension=1024)
    assert s_bge.embedding_dimension == 1024

    s_e5 = Settings(embedding_model="intfloat/e5-small", embedding_dimension=384)
    assert s_e5.embedding_dimension == 384

    # multilingual-e5-large requires 1024d
    with pytest.raises(ValueError, match="requires embedding_dimension=1024"):
        Settings(embedding_model="intfloat/multilingual-e5-large", embedding_dimension=384)

    s_e5_large = Settings(
        embedding_model="intfloat/multilingual-e5-large", embedding_dimension=1024
    )
    assert s_e5_large.embedding_dimension == 1024


def test_embedding_backend_validation():
    with pytest.raises(ValueError, match="Invalid embedding_backend"):
        Settings(embedding_backend="unsupported_backend")

    s = Settings(embedding_backend="onnx_int8")
    assert s.embedding_backend == "onnx_int8"


def test_reranker_backend_validation():
    with pytest.raises(ValueError, match="Invalid reranker_backend"):
        Settings(reranker_backend="invalid_backend")

    s = Settings(reranker_backend="onnx_int8")
    assert s.reranker_backend == "onnx_int8"


def test_production_test_auth_restriction():
    with pytest.raises(
        ValueError, match="enable_test_auth must be False when is_production is True"
    ):
        Settings(
            is_production=True,
            enable_test_auth=True,
            anon_session_hmac_secret="valid-secret-key-at-least-32-chars-long",
            brain_kek="ZGV2LW9ubHktMzJiYXNlNjR1cmwtZW5jb2RlZC1rZXk=",
        )

    s_dev = Settings(is_production=False, enable_test_auth=True)
    assert s_dev.enable_test_auth is True

    s_prod = Settings(
        is_production=True,
        enable_test_auth=False,
        anon_session_hmac_secret="valid-secret-key-at-least-32-chars-long",
        brain_kek="ZGV2LW9ubHktMzJiYXNlNjR1cmwtZW5jb2RlZC1rZXk=",
    )
    assert s_prod.enable_test_auth is False


def test_anon_quota_degraded_limit_validation():
    # Equality is allowed
    s_equal = Settings(anon_quota_messages=5, anon_quota_degraded_limit=5)
    assert s_equal.anon_quota_degraded_limit == 5

    # Degraded limit greater than normal limit is rejected
    with pytest.raises(
        ValueError, match="anon_quota_degraded_limit .* must be <= anon_quota_messages"
    ):
        Settings(anon_quota_messages=5, anon_quota_degraded_limit=6)


def test_timeout_and_concurrency_validation():
    with pytest.raises(ValueError, match="must be strictly less than pipeline_timeout"):
        Settings(llm_timeout=120, pipeline_timeout=60)

    with pytest.raises(ValueError, match="llm_timeout must be > 0"):
        Settings(llm_timeout=0, pipeline_timeout=60)

    with pytest.raises(ValueError, match="queue_concurrency must be positive"):
        Settings(queue_concurrency=0)


def test_allowed_hosts_and_forwarded_ips_normalization():
    s = Settings(
        allowed_hosts=" localhost , 127.0.0.1 , example.com ",
        forwarded_allow_ips=" 10.0.0.0/8 , 127.0.0.1 ",
    )
    assert s.allowed_hosts == "localhost,127.0.0.1,example.com"
    assert s.forwarded_allow_ips == "10.0.0.0/8,127.0.0.1"

    with pytest.raises(
        ValueError, match="Wildcard '\\*' in allowed_hosts is forbidden in production"
    ):
        Settings(
            is_production=True,
            enable_test_auth=False,
            allowed_hosts="*",
            anon_session_hmac_secret="valid-secret-key-at-least-32-chars-long",
            brain_kek="ZGV2LW9ubHktMzJiYXNlNjR1cmwtZW5jb2RlZC1rZXk=",
        )

    with pytest.raises(
        ValueError, match="Wildcard '\\*' in forwarded_allow_ips is forbidden in production"
    ):
        Settings(
            is_production=True,
            enable_test_auth=False,
            forwarded_allow_ips="*",
            anon_session_hmac_secret="valid-secret-key-at-least-32-chars-long",
            brain_kek="ZGV2LW9ubHktMzJiYXNlNjR1cmwtZW5jb2RlZC1rZXk=",
        )


def test_brain_kek_required_in_production(monkeypatch: pytest.MonkeyPatch):
    """brain_kek (Second Brain Mode-A KEK) is optional in dev, required in prod."""
    monkeypatch.delenv("BRAIN_KEK", raising=False)
    s_dev = Settings(is_production=False, brain_kek=None)
    assert s_dev.brain_kek is None

    with pytest.raises(ValueError, match="brain_kek is required in production"):
        Settings(
            is_production=True,
            enable_test_auth=False,
            anon_session_hmac_secret="valid-secret-key-at-least-32-chars-long",
            brain_kek=None,
        )

    s_prod = Settings(
        is_production=True,
        enable_test_auth=False,
        anon_session_hmac_secret="valid-secret-key-at-least-32-chars-long",
        brain_kek="ZGV2LW9ubHktMzJiYXNlNjR1cmwtZW5jb2RlZC1rZXk=",
    )
    assert s_prod.brain_kek is not None


def test_graphrag_total_timeout_gte_traversal():
    with pytest.raises(
        ValueError, match="graphrag_total_timeout .* must be >= graphrag_traversal_timeout"
    ):
        Settings(graphrag_traversal_timeout=30.0, graphrag_total_timeout=10.0)

    s = Settings(graphrag_traversal_timeout=10.0, graphrag_total_timeout=10.0)
    assert s.graphrag_total_timeout == 10.0


def test_backend_aliases_rejected_and_normalized():
    """Only factory-implemented backends are accepted; values are lowercased."""
    for alias in ("auto", "onnx", "sentence_transformers"):
        with pytest.raises(ValueError, match="Invalid embedding_backend"):
            Settings(embedding_backend=alias)

    for alias in ("auto", "cross_encoder", "cross-encoder", "none", "disabled"):
        with pytest.raises(ValueError, match="Invalid reranker_backend"):
            Settings(reranker_backend=alias)

    s = Settings(embedding_backend="ONNX_INT8", reranker_backend="FLAGEMBEDDING")
    assert s.embedding_backend == "onnx_int8"
    assert s.reranker_backend == "flagembedding"
