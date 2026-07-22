"""Pre-download and cache reranker models for Railway/Docker builds.

Run during Docker image build to avoid cold-start model downloads:
  python scripts/download_reranker.py
"""
import os

os.environ.update({
    "SENTENCE_TRANSFORMERS_HOME": os.environ.get(
        "SENTENCE_TRANSFORMERS_HOME", "/app/model_cache/sentence_transformers"
    ),
    "HF_HOME": os.environ.get("HF_HOME", "/app/model_cache/huggingface"),
    "TRANSFORMERS_CACHE": os.environ.get("TRANSFORMERS_CACHE", "/app/model_cache/huggingface"),
})

from sentence_transformers import CrossEncoder  # noqa: E402

# CPU reranker: multilingual mMiniLMv2 — same 22M params as ms-marco-MiniLM
# but covers Hindi, Telugu, Tamil, Kannada, Marathi, and all 6 app languages.
# Swapped from ms-marco-MiniLM-L-6-v2 (English-only) which degraded multilingual queries.
CPU_RERANKER = "cross-encoder/mmarco-mMiniLMv2-L12-H384-v1"

# GPU/MPS reranker: 568M param bge model — only loaded on GPU servers (Railway GPU, A100)
GPU_RERANKER = "BAAI/bge-reranker-v2-m3"

def main() -> None:
    print(f"Downloading CPU reranker: {CPU_RERANKER}")
    CrossEncoder(CPU_RERANKER)
    print(f"✓ {CPU_RERANKER} cached")

    if os.environ.get("DOWNLOAD_GPU_RERANKER", "").lower() in ("1", "true", "yes"):
        print(f"Downloading GPU reranker: {GPU_RERANKER}")
        CrossEncoder(GPU_RERANKER)
        print(f"✓ {GPU_RERANKER} cached")
    else:
        print(f"Skipping GPU reranker {GPU_RERANKER} (set DOWNLOAD_GPU_RERANKER=1 to include)")

    print("Reranker pre-cache complete.")


if __name__ == "__main__":
    main()
