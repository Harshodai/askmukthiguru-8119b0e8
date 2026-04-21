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
# Community GGUF repo (official sarvamai/sarvam-30b only has safetensors)
$HF_REPO = "Sumitc13/sarvam-30b-GGUF"
$GGUF_FILENAME = "sarvam-30B-${QUANTIZATION}.gguf"
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
Write-Host "   Source: $HF_REPO" -ForegroundColor DarkGray
Write-Host "   File: $GGUF_FILENAME" -ForegroundColor DarkGray
Write-Host "   This may take a while (~19GB)." -ForegroundColor DarkGray

Set-Location $MODELS_DIR

if (Test-Path $GGUF_FILENAME) {
    Write-Host "   ✅ GGUF file already exists: $GGUF_FILENAME" -ForegroundColor Green
} else {
    Write-Host "   📥 Downloading from HuggingFace: $HF_REPO" -ForegroundColor Cyan
    try {
        huggingface-cli download $HF_REPO $GGUF_FILENAME --local-dir $MODELS_DIR --local-dir-use-symlinks False
        Write-Host "   ✅ Download complete: $GGUF_FILENAME" -ForegroundColor Green
    } catch {
        Write-Host "   ❌ Download failed!" -ForegroundColor Red
        Write-Host ""
        Write-Host "   Available quantizations at ${HF_REPO}:" -ForegroundColor Yellow
        Write-Host "     - sarvam-30B-Q4_K_M.gguf  (~19 GB, recommended)" -ForegroundColor DarkGray
        Write-Host "     - sarvam-30B-Q6_K.gguf    (~26 GB, higher quality)" -ForegroundColor DarkGray
        Write-Host "     - sarvam-30B-Q8_0.gguf    (~34 GB, highest quality)" -ForegroundColor DarkGray
        Write-Host "     - sarvam-30B-full-BF16.gguf (~64 GB, full precision)" -ForegroundColor DarkGray
        Write-Host ""
        Write-Host "   Try downloading manually:" -ForegroundColor Yellow
        Write-Host "   huggingface-cli download $HF_REPO <filename> --local-dir $MODELS_DIR" -ForegroundColor DarkGray
        exit 1
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

# --- Step 5: Pull classification model ---
Write-Host "`n📋 Step 5: Pulling classification model (llama3.2:3b)..." -ForegroundColor Yellow
$classifyExists = ollama list 2>&1 | Select-String "llama3.2:3b"
if ($classifyExists) {
    Write-Host "   ✅ llama3.2:3b already pulled." -ForegroundColor Green
} else {
    ollama pull llama3.2:3b
    Write-Host "   ✅ llama3.2:3b pulled." -ForegroundColor Green
}

# --- Step 6: Verify ---
Write-Host "`n📋 Step 6: Verification..." -ForegroundColor Yellow
ollama list | Select-Object -First 10

Write-Host "`n🧪 Quick test..." -ForegroundColor Cyan
try {
    "What is the meaning of Mukthi?" | ollama run $MODEL_NAME --nowordwrap 2>&1 | Select-Object -First 5
} catch {
    Write-Host "   ⚠️ Test run failed. Model may need more VRAM/RAM (~20GB)." -ForegroundColor Yellow
}

Write-Host "`n🕉️ Setup Complete!" -ForegroundColor Green
Write-Host "   Generation model: ${MODEL_NAME}:latest" -ForegroundColor Cyan
Write-Host "   Classification model: llama3.2:3b" -ForegroundColor Cyan
Write-Host "   Config: Set MODEL_PRESET=sarvam in your .env" -ForegroundColor Cyan
