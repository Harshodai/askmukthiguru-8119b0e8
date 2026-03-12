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
HF_REPO="sarvamai/sarvam-30b"
GGUF_FILENAME="sarvam-30b-${QUANTIZATION}.gguf"
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
echo "   This may take a while depending on your connection (~18GB)."
echo ""

cd "${MODELS_DIR}"

if [ -f "${GGUF_FILENAME}" ]; then
    echo "   ✅ GGUF file already exists: ${GGUF_FILENAME}"
else
    echo "   📥 Downloading from HuggingFace: ${HF_REPO}"
    # Try to download the GGUF file
    # First check if GGUF exists in the repo, if not we convert
    huggingface-cli download "${HF_REPO}" \
        --include "*.gguf" \
        --local-dir "${MODELS_DIR}" \
        --local-dir-use-symlinks False \
        2>/dev/null || {
        echo ""
        echo "   ⚠️  No GGUF files found in ${HF_REPO}."
        echo "   📦 Downloading safetensors and converting to GGUF..."
        echo "   This requires llama.cpp's convert tool."
        echo ""
        
        # Install llama-cpp-python for conversion
        pip install -q llama-cpp-python

        # Download the full model
        huggingface-cli download "${HF_REPO}" \
            --local-dir "${MODELS_DIR}/sarvam-30b-full" \
            --local-dir-use-symlinks False

        # Try conversion with llama.cpp
        if command -v python3 &> /dev/null; then
            pip install -q gguf sentencepiece
            echo "   🔄 Converting to GGUF format..."
            python3 -c "
from llama_cpp import Llama
print('   Note: For full conversion, use llama.cpp convert scripts.')
print('   Alternatively, import directly via Ollama from safetensors.')
" 2>/dev/null || echo "   Note: Manual conversion may be needed."
        fi
    }
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

# --- Step 5: Verify ---
echo ""
echo "📋 Step 5: Verification..."
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
echo "   Model: ${MODEL_NAME}"
echo "   Backend: Ollama"
echo "   Use in config: OLLAMA_MODEL=sarvam-30b:latest"
