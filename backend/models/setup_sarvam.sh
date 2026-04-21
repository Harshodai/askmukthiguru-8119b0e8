#!/bin/bash
# ============================================================
# Mukthi Guru — Sarvam 30B Model Setup Script (Linux/Colab)
#
# Downloads the GGUF quantized Sarvam 30B model from HuggingFace
# and imports it into Ollama for local inference.
#
# Usage:
#   chmod +x setup_sarvam.sh
#   ./setup_sarvam.sh
#
# For Google Colab, run each section in separate cells.
# ============================================================

set -e

# --- Configuration ---
MODEL_NAME="sarvam-30b"
QUANTIZATION="Q4_K_M"
# Community GGUF repo (official sarvamai/sarvam-30b only has safetensors)
HF_REPO="Sumitc13/sarvam-30b-GGUF"
GGUF_FILENAME="sarvam-30B-${QUANTIZATION}.gguf"
MODELS_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "🕉️ Mukthi Guru — Sarvam 30B Setup"
echo "===================================="
echo ""

# --- Step 1: Check for Ollama ---
echo "📋 Step 1: Checking Ollama installation..."
if ! command -v ollama &> /dev/null; then
    echo "   ❌ Ollama not found. Installing..."
    curl -fsSL https://ollama.com/install.sh | sh
    echo "   ✅ Ollama installed."
else
    echo "   ✅ Ollama found: $(ollama --version 2>/dev/null || echo 'version unknown')"
fi

# Start Ollama server if not running
if ! pgrep -x "ollama" > /dev/null 2>&1; then
    echo "   🚀 Starting Ollama server..."
    ollama serve &
    sleep 3
fi

# --- Step 2: Check for huggingface-cli ---
echo ""
echo "📋 Step 2: Checking HuggingFace CLI..."
if ! command -v huggingface-cli &> /dev/null; then
    echo "   📦 Installing huggingface-cli..."
    pip install -q huggingface_hub[cli]
fi

# --- Step 3: Download GGUF model ---
echo ""
echo "📋 Step 3: Downloading Sarvam 30B GGUF (${QUANTIZATION})..."
echo "   Source: ${HF_REPO}"
echo "   File: ${GGUF_FILENAME}"
echo "   This may take a while depending on your connection (~19GB)."
echo ""

cd "${MODELS_DIR}"

if [ -f "${GGUF_FILENAME}" ]; then
    echo "   ✅ GGUF file already exists: ${GGUF_FILENAME}"
else
    echo "   📥 Downloading from HuggingFace: ${HF_REPO}"
    huggingface-cli download "${HF_REPO}" \
        "${GGUF_FILENAME}" \
        --local-dir "${MODELS_DIR}" \
        --local-dir-use-symlinks False || {
        echo ""
        echo "   ❌ Download failed!"
        echo ""
        echo "   Possible causes:"
        echo "   1. File '${GGUF_FILENAME}' may not exist in the repo."
        echo "   2. Network issue or HuggingFace rate limit."
        echo ""
        echo "   Available quantizations at ${HF_REPO}:"
        echo "     - sarvam-30B-Q4_K_M.gguf  (~19 GB, recommended)"
        echo "     - sarvam-30B-Q6_K.gguf    (~26 GB, higher quality)"
        echo "     - sarvam-30B-Q8_0.gguf    (~34 GB, highest quality)"
        echo "     - sarvam-30B-full-BF16.gguf (~64 GB, full precision)"
        echo ""
        echo "   Try downloading manually:"
        echo "   huggingface-cli download ${HF_REPO} <filename> --local-dir ${MODELS_DIR}"
        exit 1
    }
    echo "   ✅ Download complete: ${GGUF_FILENAME}"
fi

# --- Step 4: Create Ollama model ---
echo ""
echo "📋 Step 4: Creating Ollama model '${MODEL_NAME}'..."

# Check if model already exists
if ollama list 2>/dev/null | grep -q "${MODEL_NAME}"; then
    echo "   ⚠️  Model '${MODEL_NAME}' already exists in Ollama."
    read -p "   Recreate? [y/N]: " recreate
    if [ "$recreate" != "y" ] && [ "$recreate" != "Y" ]; then
        echo "   ⏭️  Skipping model creation."
    else
        ollama create "${MODEL_NAME}" -f "${MODELS_DIR}/Modelfile.sarvam30b"
        echo "   ✅ Model '${MODEL_NAME}' recreated."
    fi
else
    ollama create "${MODEL_NAME}" -f "${MODELS_DIR}/Modelfile.sarvam30b"
    echo "   ✅ Model '${MODEL_NAME}' created in Ollama."
fi

# --- Step 5: Pull classification model ---
echo ""
echo "📋 Step 5: Pulling classification model (llama3.2:3b)..."
if ollama list 2>/dev/null | grep -q "llama3.2:3b"; then
    echo "   ✅ llama3.2:3b already pulled."
else
    ollama pull llama3.2:3b
    echo "   ✅ llama3.2:3b pulled."
fi

# --- Step 6: Verify ---
echo ""
echo "📋 Step 6: Verification..."
echo ""
ollama list 2>/dev/null | head -10
echo ""

echo "🧪 Quick test (generating a short response)..."
echo "What is the meaning of Mukthi?" | ollama run "${MODEL_NAME}" --nowordwrap 2>/dev/null | head -5 || {
    echo "   ⚠️  Test run failed. The model may need more VRAM/RAM."
    echo "   Recommended: At least 20GB VRAM (GPU) or 24GB RAM (CPU)"
}

echo ""
echo "🕉️ Setup Complete!"
echo "   Generation model: ${MODEL_NAME}:latest"
echo "   Classification model: llama3.2:3b"
echo "   Config: Set MODEL_PRESET=sarvam in your .env"
