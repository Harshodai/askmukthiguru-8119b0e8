from __future__ import annotations

import pytest

from start_railway import _parse_celery_concurrency, _parse_celery_queues


def test_default_worker_queue_profile_is_stable() -> None:
    assert _parse_celery_queues("ingestion,embedding,indexing,okf,memory") == [
        "ingestion",
        "embedding",
        "indexing",
        "okf",
        "memory",
    ]
    assert _parse_celery_concurrency("2") == 2


def test_worker_queue_profile_rejects_unknown_queue() -> None:
    with pytest.raises(ValueError, match="invalid"):
        _parse_celery_queues("ingestion,private_user_queue")


def test_worker_concurrency_is_bounded() -> None:
    assert _parse_celery_concurrency("1") == 1
    assert _parse_celery_concurrency("32") == 32
    with pytest.raises(ValueError):
        _parse_celery_concurrency("0")
    with pytest.raises(ValueError):
        _parse_celery_concurrency("33")
    with pytest.raises(ValueError):
        _parse_celery_concurrency("not-a-number")
