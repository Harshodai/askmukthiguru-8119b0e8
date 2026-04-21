# ============================================================
# Mukthi Guru — Unified Model Download Script (Windows PowerShell)
#
# Downloads all required models based on MODEL_PRESET.
# Run this BEFORE starting the backend.
#
# Usage:
#   .\download_models.ps1              # Uses MODEL_PRESET from env or default (qwen)
#   .\download_models.ps1 qwen         # Qwen preset only
#   .\download_models.ps1 sarvam       # Sarvam preset only
#   .\download_models.ps1 all          # Download everything
# ============================================================

$ErrorActionPreference = "Stop"

$SCRIPT_DIR = Split-Path -Parent $MyInvocation.MyCommand.Path
$PRESET = if ($args.Count -gt 0) { $args[0] } elseif ($env:MODEL_PRESET) { $env:MODEL_PRESET } else { "qwen" }

Write-Host "`n🕉️ Mukthi Guru — Model Download" -ForegroundColor Cyan
Write-Host "=====================================" -ForegroundColor Cyan
Write-Host "   Preset: $PRESET" -ForegroundColor DarkGray
Write-Host ""

# --- Check Ollama ---
$ollamaPath = Get-Command ollama -ErrorAction SilentlyContinue
if (-not $ollamaPath) {
    Write-Host "❌ Ollama not found!" -ForegroundColor Red
    Write-Host "   Install from: https://ollama.com/download/windows" -ForegroundColor Yellow
    exit 1
}

# --- Helper: Pull model if not already present ---
function Pull-IfMissing {
    param([string]$ModelName)
    $existing = ollama list 2>&1 | Select-String $ModelName
    if ($existing) {
        Write-Host "   ✅ $ModelName — already downloaded" -ForegroundColor Green
    } else {
        Write-Host "   📥 Pulling $ModelName..." -ForegroundColor Cyan
        ollama pull $ModelName
        Write-Host "   ✅ $ModelName — done" -ForegroundColor Green
    }
}

# --- Qwen Models ---
function Download-Qwen {
    Write-Host "📦 Downloading Qwen models..." -ForegroundColor Yellow
    Pull-IfMissing "qwen3:30b-a3b"    # Generation model (~18 GB)
    Pull-IfMissing "qwen3:14b"         # Classification model (~10 GB)
    Write-Host ""
}

# --- Sarvam Models ---
function Download-Sarvam {
    Write-Host "📦 Downloading Sarvam models..." -ForegroundColor Yellow
    Write-Host "   (Sarvam 30B requires GGUF import — running setup script)" -ForegroundColor DarkGray
    Write-Host ""
    & "$SCRIPT_DIR\setup_sarvam.ps1"
    Write-Host ""
}

# --- Execute based on preset ---
switch ($PRESET.ToLower()) {
    "qwen" {
        Download-Qwen
    }
    "sarvam" {
        Download-Sarvam
    }
    "all" {
        Download-Qwen
        Download-Sarvam
    }
    "custom" {
        Write-Host "ℹ️  Custom preset — no models to auto-download." -ForegroundColor Cyan
        Write-Host "   Set OLLAMA_MODEL and OLLAMA_CLASSIFY_MODEL in your .env" -ForegroundColor DarkGray
        Write-Host "   and pull them manually: ollama pull <model-name>" -ForegroundColor DarkGray
    }
    default {
        Write-Host "❌ Unknown preset: $PRESET" -ForegroundColor Red
        Write-Host "   Valid options: qwen, sarvam, all, custom" -ForegroundColor Yellow
        exit 1
    }
}

Write-Host ""
Write-Host "🕉️ Model Download Complete!" -ForegroundColor Green
Write-Host ""
Write-Host "📋 Currently available models:" -ForegroundColor Yellow
ollama list 2>&1 | Select-Object -First 15
Write-Host ""
Write-Host "💡 Set MODEL_PRESET=$PRESET in .env" -ForegroundColor Cyan
