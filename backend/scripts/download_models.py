"""Pre-download embedding models to local cache for offline Docker use."""
import os

os.environ["CURL_CA_BUNDLE"] = ""  # Workaround Docker Desktop gRPC-FUSE SSL failures in httpx

os.environ.update({
    "SENTENCE_TRANSFORMERS_HOME": "/app/model_cache/sentence_transformers",
    "HF_HOME": "/app/model_cache/huggingface",
    "TRANSFORMERS_CACHE": "/app/model_cache/huggingface",
})

# 1. SentenceTransformers cache (for SentenceTransformer API)
from sentence_transformers import SentenceTransformer

SentenceTransformer("intfloat/multilingual-e5-small")
SentenceTransformer("BAAI/bge-m3")
print("sentence_transformers cache populated")

# 2. HuggingFace hub cache (for BGEM3FlagModel / FlagEmbedding API)
from huggingface_hub import snapshot_download

snapshot_download("BAAI/bge-m3")
print("huggingface hub cache populated")
