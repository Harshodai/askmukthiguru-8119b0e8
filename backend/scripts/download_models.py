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

# 2. BGE Reranker cache (for reranker API — used via CrossEncoder API)
from sentence_transformers import CrossEncoder
CrossEncoder("BAAI/bge-reranker-v2-m3")
print("bge-reranker cache populated")

# 3. CrossEncoder fallback reranker
CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")
print("ms-marco reranker cache populated")

# 4. SemanticRouter / on-device intent classifier
from sentence_transformers import SentenceTransformer
SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
print("all-MiniLM-L6-v2 cache populated")

# 5. Llama Guard / Rejection classifier (optional, skip on failure)
try:
    from transformers import AutoModelForCausalLM, AutoTokenizer
    AutoTokenizer.from_pretrained("meta-llama/Llama-Guard-3-1B")
    AutoModelForCausalLM.from_pretrained("meta-llama/Llama-Guard-3-1B")
    print("llama-guard cache populated")
except Exception as e:
    print(f"llama-guard download skipped: {e}")

# 6. Rejection Classifier (optional) — used by RejectionClassifierHandler
try:
    from transformers import AutoModelForSequenceClassification, AutoTokenizer
    AutoTokenizer.from_pretrained("protectai/distilroberta-base-rejection-v1")
    AutoModelForSequenceClassification.from_pretrained("protectai/distilroberta-base-rejection-v1")
    print("rejection classifier cache populated")
except Exception as e:
    print(f"rejection classifier download skipped: {e}")

print("All models cached successfully")

