"""Pre-download embedding models to local cache for offline Docker use."""
import os

os.environ["CURL_CA_BUNDLE"] = ""  # Workaround Docker Desktop gRPC-FUSE SSL failures in httpx

os.environ.update({
    "SENTENCE_TRANSFORMERS_HOME": os.environ.get("SENTENCE_TRANSFORMERS_HOME", "/app/model_cache/sentence_transformers"),
    "HF_HOME": os.environ.get("HF_HOME", "/app/model_cache/huggingface"),
    "TRANSFORMERS_CACHE": os.environ.get("TRANSFORMERS_CACHE", "/app/model_cache/huggingface"),
})

# 1. SentenceTransformers cache (for SentenceTransformer API)
from sentence_transformers import SentenceTransformer

SentenceTransformer("intfloat/multilingual-e5-small")
SentenceTransformer("BAAI/bge-m3")
print("sentence_transformers cache populated")

# 2. HuggingFace hub cache (for BGEM3FlagModel / FlagEmbedding API)
# Commented out to avoid redundant/hanging download (SentenceTransformer already caches it under the same HF_HOME)
# from huggingface_hub import snapshot_download
# snapshot_download("BAAI/bge-m3")
# print("huggingface hub cache populated")

# 3. CrossEncoder cache (for reranker API)
from sentence_transformers import CrossEncoder
CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")
print("cross-encoder cache populated")

