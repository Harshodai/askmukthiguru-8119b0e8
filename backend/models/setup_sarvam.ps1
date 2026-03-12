# ============================================================
# Mukthi Guru — Sarvam 30B Model Setup Script (Windows PowerShell)
#
# Downloads the GGUF quantized Sarvam 30B model from HuggingFace
# and imports it into Ollama for local inference.
#
# Usage:
#   .\setup_sarvam.ps1
# ============================================================

$ErrorActionPreference = "Stop"

# --- Configuration ---
$MODEL_NAME = "sarvam-30b"
$QUANTIZATION = "Q4_K_M"
$HF_REPO = "sarvamai/sarvam-30b"
$GGUF_FILENAME = "sarvam-30b-${QUANTIZATION}.gguf"
$MODELS_DIR = Split-Path -Parent $MyInvocation.MyCommand.Path

Write-Host "`n🕉️ Mukthi Guru — Sarvam 30B Setup" -ForegroundColor Cyan
Write-Host "====================================" -ForegroundColor Cyan
Write-Host ""

# --- Step 1: Check Ollama ---
Write-Host "📋 Step 1: Checking Ollama installation..." -ForegroundColor Yellow
$ollamaPath = Get-Command ollama -ErrorAction SilentlyContinue
if (-not $ollamaPath) {
    Write-Host "   ❌ Ollama not found." -ForegroundColor Red
    Write-Host "   Please install Ollama from: https://ollama.com/download/windows" -ForegroundColor Red
    Write-Host "   Then re-run this script." -ForegroundColor Red
    exit 1
}
Write-Host "   ✅ Ollama found." -ForegroundColor Green

# --- Step 2: Check HuggingFace CLI ---
Write-Host "`n📋 Step 2: Checking HuggingFace CLI..." -ForegroundColor Yellow
$hfCli = Get-Command huggingface-cli -ErrorAction SilentlyContinue
if (-not $hfCli) {
    Write-Host "   📦 Installing huggingface-cli..." -ForegroundColor Cyan
    pip install huggingface_hub[cli]
}
Write-Host "   ✅ HuggingFace CLI ready." -ForegroundColor Green

# --- Step 3: Download GGUF ---
Write-Host "`n📋 Step 3: Downloading Sarvam 30B GGUF (${QUANTIZATION})..." -ForegroundColor Yellow
Write-Host "   This may take a while (~18GB)." -ForegroundColor DarkGray

Set-Location $MODELS_DIR

if (Test-Path $GGUF_FILENAME) {
    Write-Host "   ✅ GGUF file already exists: $GGUF_FILENAME" -ForegroundColor Green
} else {
    Write-Host "   📥 Downloading from HuggingFace: $HF_REPO" -ForegroundColor Cyan
    try {
        huggingface-cli download $HF_REPO --include "*.gguf" --local-dir $MODELS_DIR --local-dir-use-symlinks False
    } catch {
        Write-Host "   ⚠️ No GGUF files found. You may need to convert from safetensors." -ForegroundColor Yellow
        Write-Host "   See: https://github.com/ggerganov/llama.cpp" -ForegroundColor DarkGray
    }
}

# --- Step 4: Create Ollama model ---
Write-Host "`n📋 Step 4: Creating Ollama model '$MODEL_NAME'..." -ForegroundColor Yellow

$existing = ollama list 2>&1 | Select-String $MODEL_NAME
if ($existing) {
    Write-Host "   ⚠️ Model '$MODEL_NAME' already exists." -ForegroundColor Yellow
    $recreate = Read-Host "   Recreate? [y/N]"
    if ($recreate -eq "y" -or $recreate -eq "Y") {
        ollama create $MODEL_NAME -f "$MODELS_DIR\Modelfile.sarvam30b"
        Write-Host "   ✅ Model recreated." -ForegroundColor Green
    }
} else {
    ollama create $MODEL_NAME -f "$MODELS_DIR\Modelfile.sarvam30b"
    Write-Host "   ✅ Model '$MODEL_NAME' created in Ollama." -ForegroundColor Green
}

# --- Step 5: Verify ---
Write-Host "`n📋 Step 5: Verification..." -ForegroundColor Yellow
ollama list | Select-Object -First 10

Write-Host "`n🧪 Quick test..." -ForegroundColor Cyan
try {
    "What is the meaning of Mukthi?" | ollama run $MODEL_NAME --nowordwrap 2>&1 | Select-Object -First 5
} catch {
    Write-Host "   ⚠️ Test run failed. Model may need more VRAM/RAM (~20GB)." -ForegroundColor Yellow
}

Write-Host "`n🕉️ Setup Complete!" -ForegroundColor Green
Write-Host "   Model: $MODEL_NAME" -ForegroundColor Cyan
Write-Host "   Use in config: OLLAMA_MODEL=sarvam-30b:latest" -ForegroundColor Cyan
