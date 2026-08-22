"""Prefetch the exact CPU reranker used by the serving path.

This is intentionally separate from the broad development model prefetcher. It
keeps the Railway serving image small and reproducible while avoiding a first
user request downloading the multilingual CrossEncoder.
"""

from __future__ import annotations

import os

MODEL_ID = "cross-encoder/mmarco-mMiniLMv2-L12-H384-v1"
MODEL_REVISION = "1427fd652930e4ba29e8149678df786c240d8825"
CACHE_FOLDER = os.environ.get(
    "SENTENCE_TRANSFORMERS_HOME", "/app/model_cache/sentence_transformers"
)

# Configure the cache before importing sentence-transformers. The installed
# CrossEncoder API does not accept cache_folder; it reads this environment
# variable instead. The runtime sets the same path so the model is reused by
# services/reranker_service.py rather than downloaded on first chat.
os.environ.setdefault("SENTENCE_TRANSFORMERS_HOME", CACHE_FOLDER)
os.environ.setdefault("TRANSFORMERS_CACHE", "/app/model_cache/huggingface")
os.environ.setdefault("HF_HOME", "/app/model_cache/huggingface")

from sentence_transformers import CrossEncoder

CrossEncoder(
    MODEL_ID,
    revision=MODEL_REVISION,
    device="cpu",
)
print(f"runtime CPU reranker cached: {MODEL_ID}@{MODEL_REVISION} -> {CACHE_FOLDER}")
