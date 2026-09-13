"""MultiProviderLLMService must actually construct.

`TokenBucket` calls `time.time()` but `services/multi_provider_llm.py` never
imported `time`. `get_llm_service()` therefore raised NameError, which
`app/container.py` caught and logged as
"MultiProviderLLMService init skipped: name 'time' is not defined" — leaving
`container.multi_provider_llm = None`. The OKF extraction chain is documented as
multi-provider -> OpenRouter -> Ollama, so its first leg was silently absent.

Found 2026-09-13 in a container-build log while probing something unrelated.
"""

import services.multi_provider_llm as mod
from services.multi_provider_llm import get_llm_service


def test_time_is_imported():
    assert hasattr(mod, "time"), "module uses time.time() and must import time"


def test_service_constructs():
    svc = get_llm_service()
    assert svc is not None
    assert type(svc).__name__ == "MultiProviderLLMService"


def test_token_bucket_can_refill():
    """The exact call that raised: TokenBucket touching time.time()."""
    bucket = mod.TokenBucket(rate=1, capacity=1) if hasattr(mod, "TokenBucket") else None
    assert bucket is not None
    assert isinstance(bucket.last_refill, float)
