import os
os.environ.update({
    "SENTENCE_TRANSFORMERS_HOME": os.environ.get("SENTENCE_TRANSFORMERS_HOME", "/app/model_cache/sentence_transformers"),
    "HF_HOME": os.environ.get("HF_HOME", "/app/model_cache/huggingface"),
    "TRANSFORMERS_CACHE": os.environ.get("TRANSFORMERS_CACHE", "/app/model_cache/huggingface"),
})
from sentence_transformers import CrossEncoder
CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")
print("cross-encoder cache populated")
