"""Pre-download embedding models to local cache for offline Docker use.

Every model is pinned to an immutable commit SHA (revision), resolved from the
Hugging Face API on 2026-08-01. A repo head is mutable: a later commit can
silently change weights, tokenizer files, or licence metadata and turn the
next build into an unverified model. The resolved commit id of every model is
printed so a build log proves which exact revision was cached.
"""
import os

os.environ["CURL_CA_BUNDLE"] = ""  # Workaround Docker Desktop gRPC-FUSE SSL failures in httpx

os.environ.update({
    "SENTENCE_TRANSFORMERS_HOME": os.environ.get("SENTENCE_TRANSFORMERS_HOME", "/app/model_cache/sentence_transformers"),
    "HF_HOME": os.environ.get("HF_HOME", "/app/model_cache/huggingface"),
    "TRANSFORMERS_CACHE": os.environ.get("TRANSFORMERS_CACHE", "/app/model_cache/huggingface"),
})

# Immutable revisions (commit SHAs), resolved 2026-08-01.
_MODEL_REVISIONS = {
    "intfloat/multilingual-e5-small": "614241f622f53c4eeff9890bdc4f31cfecc418b3",
    "BAAI/bge-m3": "5617a9f61b028005a4858fdac845db406aefb181",
    "BAAI/bge-reranker-v2-m3": "953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e",
    "cross-encoder/ms-marco-MiniLM-L6-v2": "c5ee24cb16019beea0893ab7796b1df96625c6b8",
    "sentence-transformers/all-MiniLM-L6-v2": "1110a243fdf4706b3f48f1d95db1a4f5529b4d41",
    "meta-llama/Llama-Guard-3-1B": "acf7aafa60f0410f8f42b1fa35e077d705892029",
    "protectai/distilroberta-base-rejection-v1": "86520b5f35829cf9209a449e1716b56c70ddd802",
    "temsa/mmarco-mMiniLMv2-L12-H384-v1-onnx-cpu-qint8": "59d3305e534a9abf92f6eb6238c34b748a89dc83",
}


def _pin(model_id: str) -> str:
    """Return the pinned revision for a model id, fail-closed if unpinned."""
    revision = _MODEL_REVISIONS.get(model_id)
    if not revision:
        raise ValueError(
            f"No pinned revision registered for '{model_id}'. "
            "Resolve a commit SHA from the HF API and add it to _MODEL_REVISIONS "
            "before caching — never download an unversioned HEAD."
        )
    print(f"  resolved {model_id} -> {revision}")
    return revision


# 1. SentenceTransformers cache (for SentenceTransformer API)
from sentence_transformers import SentenceTransformer  # noqa: E402

SentenceTransformer("intfloat/multilingual-e5-small", revision=_pin("intfloat/multilingual-e5-small"))
SentenceTransformer("BAAI/bge-m3", revision=_pin("BAAI/bge-m3"))
print("sentence_transformers cache populated")

# 2. BGE Reranker cache (for reranker API — used via CrossEncoder API)
from sentence_transformers import CrossEncoder  # noqa: E402

CrossEncoder("BAAI/bge-reranker-v2-m3", revision=_pin("BAAI/bge-reranker-v2-m3"))
print("bge-reranker cache populated")

# 3. CrossEncoder fallback reranker
CrossEncoder("cross-encoder/ms-marco-MiniLM-L6-v2", revision=_pin("cross-encoder/ms-marco-MiniLM-L6-v2"))
print("ms-marco reranker cache populated")

# 4. SemanticRouter / on-device intent classifier
SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2", revision=_pin("sentence-transformers/all-MiniLM-L6-v2"))
print("all-MiniLM-L6-v2 cache populated")

# 5. Llama Guard / Rejection classifier (optional, skip on failure)
try:
    from transformers import AutoModelForCausalLM, AutoTokenizer  # noqa: E402
    _llama_guard_rev = _pin("meta-llama/Llama-Guard-3-1B")
    AutoTokenizer.from_pretrained("meta-llama/Llama-Guard-3-1B", revision=_llama_guard_rev)
    AutoModelForCausalLM.from_pretrained("meta-llama/Llama-Guard-3-1B", revision=_llama_guard_rev)
    print("llama-guard cache populated")
except Exception as e:
    print(f"llama-guard download skipped: {e}")

# 6. Rejection Classifier (optional) — used by RejectionClassifierHandler
try:
    from transformers import AutoModelForSequenceClassification, AutoTokenizer  # noqa: E402
    _rejection_rev = _pin("protectai/distilroberta-base-rejection-v1")
    AutoTokenizer.from_pretrained("protectai/distilroberta-base-rejection-v1", revision=_rejection_rev)
    AutoModelForSequenceClassification.from_pretrained(
        "protectai/distilroberta-base-rejection-v1", revision=_rejection_rev
    )
    print("rejection classifier cache populated")
except Exception as e:
    print(f"rejection classifier download skipped: {e}")

# 7. ONNX INT8 reranker (temsa) — used by OnnxReranker via snapshot_download.
# The snapshot must land under HF_HOME/hub/models--<org>--<model> (the same
# path services/onnx_reranker.py::_hf_cache_dir computes at runtime) so an
# offline container hits the pre-baked artifact instead of re-downloading.
try:
    from huggingface_hub import snapshot_download  # noqa: E402

    _onnx_reranker_id = "temsa/mmarco-mMiniLMv2-L12-H384-v1-onnx-cpu-qint8"
    _onnx_reranker_rev = _pin(_onnx_reranker_id)
    _onnx_reranker_cache = os.path.join(
        os.environ["HF_HOME"],
        "hub",
        "models--" + _onnx_reranker_id.replace("/", "--"),
    )
    snapshot_download(
        repo_id=_onnx_reranker_id,
        revision=_onnx_reranker_rev,
        local_dir=_onnx_reranker_cache,
        local_dir_use_symlinks=False,
        resume_download=True,
        ignore_patterns=["*.md", "*.py", "requirements.txt"],
    )
    print("onnx int8 reranker cache populated")
except Exception as e:
    print(f"onnx int8 reranker download skipped: {e}")

print("All models cached successfully")
