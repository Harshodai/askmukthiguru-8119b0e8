#!/usr/bin/env bash
# Prove FastTokenizer == transformers 5.x AutoTokenizer inside the backend image.
#
# Why: the host venv has transformers 4.57.6, so the 5.x equivalence cases skip
# there. Serving pins transformers==5.19.0 (the image). This runs the equivalence
# test in a throwaway container with REQUIRE_TRANSFORMERS_5=1, which turns any
# skip into a failure, so "passed, 0 skipped" is the proof.
#
# Run it when the Docker VM has more than 3 GB of free memory. It refuses below
# that, because the test loads two tokenizers (old and new) and AutoTokenizer
# alone is ~1.2 GB resident.
#
# Usage:  scripts/ops/verify_fast_tokenizer_in_image.sh
# Env:    IMAGE (default backend-backend:latest), MODEL_CACHE_DIR
#         (default <repo>/backend/.model_cache, must hold
#         huggingface/hub/models--gpahal--bge-m3-onnx-int8 and
#         huggingface/hub/models--temsa--mmarco-mMiniLMv2-L12-H384-v1-onnx-cpu-qint8)
set -euo pipefail

export PATH="$HOME/.docker/bin:$PATH"
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BACKEND="$REPO/backend"
IMAGE="${IMAGE:-backend-backend:latest}"
MODEL_CACHE_DIR="${MODEL_CACHE_DIR:-$BACKEND/.model_cache}"
MIN_AVAILABLE_KB=3145728 # 3 GiB

[ -d "$MODEL_CACHE_DIR/huggingface/hub" ] || {
  echo "ERROR: model cache not found at $MODEL_CACHE_DIR/huggingface/hub (set MODEL_CACHE_DIR)" >&2
  exit 2
}

# /proc/meminfo inside a container reports the Docker VM's memory.
AVAILABLE_KB="$(docker run --rm --network none --entrypoint cat "$IMAGE" /proc/meminfo |
  awk '/^MemAvailable:/ {print $2}')"
echo "Docker VM MemAvailable: $((AVAILABLE_KB / 1024)) MiB (need >= $((MIN_AVAILABLE_KB / 1024)) MiB)"
if [ "${AVAILABLE_KB:-0}" -lt "$MIN_AVAILABLE_KB" ]; then
  echo "REFUSING to run: free up Docker VM memory (stop containers) and retry." >&2
  exit 3
fi

# The image holds the pinned transformers 5.19.0 + tokenizers 0.23.3. Only the
# code under test (app, services, tests) is mounted, read-only, from this checkout.
docker run --rm \
  --memory 1600m --memory-swap 1600m \
  --network none \
  --entrypoint python \
  -w /app \
  -e REQUIRE_TRANSFORMERS_5=1 \
  -e HF_HOME=/app/model_cache/huggingface \
  -e HF_HUB_OFFLINE=1 \
  -e TRANSFORMERS_OFFLINE=1 \
  -e TOKENIZERS_PARALLELISM=false \
  -e PYTHONDONTWRITEBYTECODE=1 \
  -v "$BACKEND/app:/app/app:ro" \
  -v "$BACKEND/services:/app/services:ro" \
  -v "$BACKEND/tests:/app/tests:ro" \
  -v "$MODEL_CACHE_DIR:/app/model_cache:ro" \
  "$IMAGE" \
  -m pytest tests/test_fast_tokenizer_equivalence_2026_11_27.py -q -rs -p no:cacheprovider
