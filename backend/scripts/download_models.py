"""Pre-download embedding models to local cache for offline Docker use.

Every model is pinned to an immutable commit SHA (revision), resolved from the
Hugging Face API on 2026-08-01. A repo head is mutable: a later commit can
silently change weights, tokenizer files, or licence metadata and turn the
next build into an unverified model. The resolved commit id of every model is
printed so a build log proves which exact revision was cached.
"""

import os

os.environ["CURL_CA_BUNDLE"] = ""  # Workaround Docker Desktop gRPC-FUSE SSL failures in httpx

os.environ.update(
    {
        "SENTENCE_TRANSFORMERS_HOME": os.environ.get(
            "SENTENCE_TRANSFORMERS_HOME", "/app/model_cache/sentence_transformers"
        ),
        "HF_HOME": os.environ.get("HF_HOME", "/app/model_cache/huggingface"),
        "TRANSFORMERS_CACHE": os.environ.get("TRANSFORMERS_CACHE", "/app/model_cache/huggingface"),
    }
)

# Immutable revisions (commit SHAs), resolved 2026-08-01 / 2026-08-11.
_MODEL_REVISIONS = {
    "intfloat/multilingual-e5-small": "614241f622f53c4eeff9890bdc4f31cfecc418b3",
    "BAAI/bge-m3": "5617a9f61b028005a4858fdac845db406aefb181",
    "BAAI/bge-reranker-v2-m3": "953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e",
    "cross-encoder/ms-marco-MiniLM-L6-v2": "c5ee24cb16019beea0893ab7796b1df96625c6b8",
    # PyTorch CrossEncoder fallback for CPU deployments (reranker_model_cpu in
    # app/config.py) when RERANKER_BACKEND=onnx_int8's OnnxReranker fails to
    # load — resolved 2026-09-17.
    "cross-encoder/mmarco-mMiniLMv2-L12-H384-v1": "1427fd652930e4ba29e8149678df786c240d8825",
    "sentence-transformers/all-MiniLM-L6-v2": "1110a243fdf4706b3f48f1d95db1a4f5529b4d41",
    "meta-llama/Llama-Guard-3-1B": "acf7aafa60f0410f8f42b1fa35e077d705892029",
    "protectai/distilroberta-base-rejection-v1": "86520b5f35829cf9209a449e1716b56c70ddd802",
    "temsa/mmarco-mMiniLMv2-L12-H384-v1-onnx-cpu-qint8": "59d3305e534a9abf92f6eb6238c34b748a89dc83",
    # ONNX INT8 quantized BGE-M3 model for CPU inference (EMBEDDING_BACKEND=onnx_int8)
    "gpahal/bge-m3-onnx-int8": "2b34e84df040034d4b9eabb62383a87c18955822",
    # LettuceDetect token classification model for hallucination / faithfulness verification
    "KRLabsOrg/lettucedect-base-modernbert-en-v1": "bbd77832f52f9bd87546a3924c032467921f5c34",
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


QUANTIZED_ONLY = os.environ.get("QUANTIZED_ONLY", "").lower() in ("true", "1", "yes")
if QUANTIZED_ONLY:
    print("QUANTIZED_ONLY=true: Skipping unquantized PyTorch FP32 models (saving ~7.5GB)")

# 1. SentenceTransformers cache (for SentenceTransformer API)
from sentence_transformers import SentenceTransformer  # noqa: E402

if not QUANTIZED_ONLY:
    SentenceTransformer(
        "intfloat/multilingual-e5-small", revision=_pin("intfloat/multilingual-e5-small")
    )
    SentenceTransformer("BAAI/bge-m3", revision=_pin("BAAI/bge-m3"))
    print("sentence_transformers cache populated")

    # 2. BGE Reranker cache (for reranker API — used via CrossEncoder API)
    from sentence_transformers import CrossEncoder  # noqa: E402

    CrossEncoder("BAAI/bge-reranker-v2-m3", revision=_pin("BAAI/bge-reranker-v2-m3"))
    print("bge-reranker cache populated")

    # 3. CrossEncoder fallback reranker
    CrossEncoder(
        "cross-encoder/ms-marco-MiniLM-L6-v2", revision=_pin("cross-encoder/ms-marco-MiniLM-L6-v2")
    )
    print("ms-marco reranker cache populated")

    # 3b. CrossEncoder CPU fallback reranker
    CrossEncoder(
        "cross-encoder/mmarco-mMiniLMv2-L12-H384-v1",
        revision=_pin("cross-encoder/mmarco-mMiniLMv2-L12-H384-v1"),
    )
    print("mmarco-mMiniLMv2-L12 (reranker_model_cpu fallback) cache populated")

# 4. SemanticRouter / on-device intent classifier
SentenceTransformer(
    "sentence-transformers/all-MiniLM-L6-v2",
    revision=_pin("sentence-transformers/all-MiniLM-L6-v2"),
)
print("all-MiniLM-L6-v2 cache populated")

if not QUANTIZED_ONLY:
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
        AutoTokenizer.from_pretrained(
            "protectai/distilroberta-base-rejection-v1", revision=_rejection_rev
        )
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

# 8. ONNX INT8 embedding model (gpahal/bge-m3-onnx-int8)
# Used by EmbeddingService._load_onnx_encoder. It expects the model snapshot under
# HF_HOME/hub/models--gpahal--bge-m3-onnx-int8
try:
    from huggingface_hub import snapshot_download  # noqa: E402

    _onnx_embed_id = "gpahal/bge-m3-onnx-int8"
    _onnx_embed_rev = _pin(_onnx_embed_id)
    _onnx_embed_cache = os.path.join(
        os.environ["HF_HOME"],
        "hub",
        "models--" + _onnx_embed_id.replace("/", "--"),
    )
    snapshot_download(
        repo_id=_onnx_embed_id,
        revision=_onnx_embed_rev,
        local_dir=_onnx_embed_cache,
        local_dir_use_symlinks=False,
        resume_download=True,
        ignore_patterns=["*.md", "*.py", "requirements.txt"],
    )
    print("onnx int8 bge-m3 embedder cache populated")
except Exception as e:
    print(f"onnx int8 embedder download skipped: {e}")

# 9. BGE-M3 Tokenizer (BAAI/bge-m3)
# Explicitly cached for EmbeddingService._load_onnx_encoder
try:
    from transformers import AutoTokenizer  # noqa: E402

    _bge_m3_rev = _pin("BAAI/bge-m3")
    AutoTokenizer.from_pretrained("BAAI/bge-m3", revision=_bge_m3_rev)
    print("bge-m3 tokenizer cache populated")
except Exception as e:
    print(f"bge-m3 tokenizer download skipped: {e}")

# 10. LettuceDetect ModernBERT model (KRLabsOrg/lettucedect-base-modernbert-en-v1)
# Used by LettuceDetectService._load_real_detector.
try:
    from huggingface_hub import snapshot_download  # noqa: E402

    _lettuce_id = "KRLabsOrg/lettucedect-base-modernbert-en-v1"
    _lettuce_rev = _pin(_lettuce_id)
    _lettuce_path = snapshot_download(
        repo_id=_lettuce_id,
        revision=_lettuce_rev,
        resume_download=True,
    )
    try:
        from lettucedetect.models.inference import HallucinationDetector  # noqa: E402

        HallucinationDetector(method="transformer", model_path=_lettuce_path)
        print("lettucedect detector cache populated and pre-warmed")
    except Exception as e:
        from transformers import AutoModelForTokenClassification, AutoTokenizer  # noqa: E402

        AutoTokenizer.from_pretrained(_lettuce_path)
        AutoModelForTokenClassification.from_pretrained(_lettuce_path)
        print(f"lettucedect token classification cache populated (fallback: {e})")
except Exception as e:
    print(f"lettucedect download skipped: {e}")

print("All models cached successfully")
