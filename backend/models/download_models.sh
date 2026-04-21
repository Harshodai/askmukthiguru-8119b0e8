#!/bin/bash
# ============================================================
# Mukthi Guru — Unified Model Download Script (Linux/macOS)
#
# Downloads all required models based on MODEL_PRESET.
# Run this BEFORE starting the backend.
#
# Usage:
#   chmod +x download_models.sh
#   ./download_models.sh              # Uses MODEL_PRESET from .env or default (qwen)
#   ./download_models.sh qwen         # Qwen preset only
#   ./download_models.sh sarvam       # Sarvam preset only
#   ./download_models.sh all          # Download everything
# ============================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PRESET="${1:-${MODEL_PRESET:-qwen}}"

echo "🕉️ Mukthi Guru — Model Download"
echo "====================================="
echo "   Preset: ${PRESET}"
echo ""

# --- Check Ollama ---
if ! command -v ollama &> /dev/null; then
    echo "❌ Ollama not found!"
    echo "   Linux:   curl -fsSL https://ollama.com/install.sh | sh"
    echo "   macOS:   brew install ollama"
    echo "   Windows: https://ollama.com/download/windows"
    exit 1
fi

# Ensure Ollama server is running
if ! curl -sf http://localhost:11434/api/tags > /dev/null 2>&1; then
    echo "⚠️  Ollama server not reachable. Starting..."
    ollama serve &
    sleep 3
fi

# --- Helper: Pull model if not already present ---
pull_if_missing() {
    local model="$1"
    if ollama list 2>/dev/null | grep -q "$model"; then
        echo "   ✅ ${model} — already downloaded"
    else
        echo "   📥 Pulling ${model}..."
        ollama pull "$model"
        echo "   ✅ ${model} — done"
    fi
}

# --- Qwen Models ---
download_qwen() {
    echo "📦 Downloading Qwen models..."
    pull_if_missing "qwen3:30b-a3b"    # Generation model (~18 GB)
    pull_if_missing "qwen3:14b"         # Classification model (~10 GB)
    echo ""
}

# --- Sarvam Models ---
download_sarvam() {
    echo "📦 Downloading Sarvam models..."
    echo "   (Sarvam 30B requires GGUF import — running setup script)"
    echo ""
    bash "${SCRIPT_DIR}/setup_sarvam.sh"
    echo ""
}

# --- Execute based on preset ---
case "${PRESET,,}" in
    qwen)
        download_qwen
        ;;
    sarvam)
        download_sarvam
        ;;
    all)
        download_qwen
        download_sarvam
        ;;
    custom)
        echo "ℹ️  Custom preset — no models to auto-download."
        echo "   Set OLLAMA_MODEL and OLLAMA_CLASSIFY_MODEL in your .env"
        echo "   and pull them manually: ollama pull <model-name>"
        ;;
    *)
        echo "❌ Unknown preset: ${PRESET}"
        echo "   Valid options: qwen, sarvam, all, custom"
        exit 1
        ;;
esac

echo ""
echo "🕉️ Model Download Complete!"
echo ""
echo "📋 Currently available models:"
ollama list 2>/dev/null | head -15
echo ""
echo "💡 Set MODEL_PRESET=${PRESET} in .env (or pass it as an argument)"
