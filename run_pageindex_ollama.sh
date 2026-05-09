#!/bin/bash
set -e

# Export Ollama API base for litellm
export OLLAMA_API_BASE="http://localhost:11434"
export PYTHONPATH=$(pwd)/scripts:$(pwd)/backend

echo "=== Smart PDF Extraction + Qdrant Ingestion ==="
echo "Using local Ollama (deepseek-r1:7b) for LLM summarization"
echo "Using programmatic detection for section structure"
echo ""

backend/.venv/bin/python scripts/smart_extract_and_ingest.py \
  --pdf_path "The_Four_Sacred_Secrets.pdf" \
  --model "ollama/deepseek-r1:7b" \
  --ingest

echo ""
echo "================================================"
echo "Done! Mukthi Guru is now updated with 'The Four Sacred Secrets'."
