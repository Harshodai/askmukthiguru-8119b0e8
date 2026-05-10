#!/bin/bash
set -e

# Load environment variables from backend/.env
set -a
source backend/.env
set +a

# Export Sarvam API key and base URL for litellm extra_headers
export SARVAM_API_KEY="${SARVAM_API_KEY}"
export OPENAI_API_KEY="${SARVAM_API_KEY}"
export OPENAI_API_BASE="${SARVAM_BASE_URL:-https://api.sarvam.ai/v1}"

# Run PageIndex using Sarvam API
echo "Running PageIndex using Sarvam API (sarvam-30b)..."
echo "  API Base: $OPENAI_API_BASE"
export PYTHONPATH=$(pwd)/scripts
backend/.venv/bin/python scripts/run_pageindex.py \
  --pdf_path "The_Four_Sacred_Secrets.pdf" \
  --model "openai/sarvam-30b" \
  --if-add-node-text yes

# If extraction succeeds, proceed to ingestion
if [ $? -eq 0 ]; then
  echo "------------------------------------------------"
  echo "Extraction successful. Starting ingestion into Qdrant..."
  backend/.venv/bin/python scripts/ingest_four_sacred_secrets.py
  echo "Ingestion complete! Mukthi Guru is now updated with 'The Four Sacred Secrets'."
else
  echo "------------------------------------------------"
  echo "Extraction failed. Ingestion aborted."
  exit 1
fi
