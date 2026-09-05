#!/bin/bash
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BACKEND_DIR="${REPO_ROOT}/backend"
LOG_FILE="${REPO_ROOT}/logs/bulk_ingest_master.log"
INPUT_FILE="${REPO_ROOT}/scripts/ingestion/all_ingest_urls.txt"
WORKERS="${1:-6}"

export PATH="${REPO_ROOT}/.venv_host/bin:${PATH}"
export PYTHONPATH="${BACKEND_DIR}"
export OLLAMA_BASE_URL="http://localhost:11434"
export OLLAMA_CLOUD_ONLY="false"
export OLLAMA_REINGEST_MODEL="qwen2.5:1.5b"
export OLLAMA_MODEL="qwen2.5:1.5b"
export OLLAMA_CLASSIFY_MODEL="qwen2.5:1.5b"
export QDRANT_URL="http://localhost:6333"
export QDRANT_COLLECTION="spiritual_wisdom_contextual"
if [ -f "${BACKEND_DIR}/.env" ]; then
    set -a
    # shellcheck disable=SC1091
    source "${BACKEND_DIR}/.env"
    set +a
fi
export REDIS_URL="${REDIS_URL:-redis://localhost:6379/0}"
export SUPABASE_URL="${SUPABASE_URL:-http://localhost:54321}"
export NEO4J_URI="${NEO4J_URI:-bolt://localhost:7687}"
export NEO4J_PASSWORD="${NEO4J_PASSWORD:-}"
export PRE_EXTRACTED_MAX_AGE_SKIP="31536000"
export LLM_PROVIDER="ollama"
export EMBEDDING_BACKEND="onnx_int8"
export RERANKER_BACKEND="onnx_int8"

echo "================================================================"
echo "☕ SUPERVISOR STARTED — AUTO-RESUME BULK INGESTION LOOP"
echo "   Target Workers : ${WORKERS}"
echo "   Input Sources  : ${INPUT_FILE}"
echo "   Master Log     : ${LOG_FILE}"
echo "================================================================"

while true; do
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] 🚀 Starting bulk ingestion worker pool..." >> "${LOG_FILE}"
    
    "${REPO_ROOT}/.venv_host/bin/python3" -u -m scripts.ingestion.bulk_ingest_video \
        --input "${INPUT_FILE}" \
        --batch-size 25 \
        --workers "${WORKERS}" >> "${LOG_FILE}" 2>&1
    
    EXIT_CODE=$?
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] ⚠️ Worker pool finished/interrupted with exit code ${EXIT_CODE}" >> "${LOG_FILE}"
    
    # Check if remaining sources exist
    REMAINING=$("${REPO_ROOT}/.venv_host/bin/python3" -c '
import json, os, sys, redis
try:
    redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
    r = redis.from_url(redis_url, socket_timeout=3)
    input_file = sys.argv[1] if len(sys.argv) > 1 else "scripts/ingestion/all_ingest_urls.txt"
    with open(input_file) as f:
        urls = [l.strip() for l in f if l.strip()]
    pending = []
    for u in urls:
        val = r.get(f"ingestion_checkpoint:oneness:{u}")
        if not val:
            pending.append(u)
        else:
            try:
                data = json.loads(val)
                if isinstance(data, dict) and data.get("status") in ("failed", "error"):
                    pending.append(u)
            except Exception:
                pass
    print(len(pending))
except Exception as e:
    print("-1")
' "${INPUT_FILE}" 2>/dev/null || echo "-1")

    if [ "${REMAINING}" = "0" ]; then
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] 🎉 ALL SOURCES COMPLETED & CHECKPOINTED (0 remaining)!" >> "${LOG_FILE}"
        echo "================================================================"
        echo "🎉 ALL 763 SOURCES PROCESSED & VERIFIED!"
        echo "================================================================"
        break
    else
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] 🔄 Resuming pipeline in 3s (Remaining sources: ${REMAINING})..." >> "${LOG_FILE}"
        sleep 3
    fi
done
