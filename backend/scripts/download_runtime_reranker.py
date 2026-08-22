"""Prefetch the exact CPU reranker used by the serving path.

This is intentionally separate from the broad development model prefetcher. It
keeps the Railway serving image small and reproducible while avoiding a first
user request downloading the multilingual CrossEncoder.
"""

from __future__ import annotations

import os

from sentence_transformers import CrossEncoder

MODEL_ID = "cross-encoder/mmarco-mMiniLMv2-L12-H384-v1"
MODEL_REVISION = "1427fd652930e4ba29e8149678df786c240d8825"
CACHE_FOLDER = os.environ.get(
    "SENTENCE_TRANSFORMERS_HOME", "/app/model_cache/sentence_transformers"
)

# CrossEncoder accepts an immutable revision and an explicit cache folder. The
# runtime sets SENTENCE_TRANSFORMERS_HOME to the same folder, so this load is
# reused by services/reranker_service.py instead of downloading on first chat.
CrossEncoder(
    MODEL_ID,
    revision=MODEL_REVISION,
    cache_folder=CACHE_FOLDER,
    device="cpu",
)
print(f"runtime CPU reranker cached: {MODEL_ID}@{MODEL_REVISION} -> {CACHE_FOLDER}")
