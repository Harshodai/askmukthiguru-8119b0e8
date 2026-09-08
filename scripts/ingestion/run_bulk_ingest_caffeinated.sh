#!/bin/bash
set -eo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BACKEND_DIR="${REPO_ROOT}/backend"

export PATH="${REPO_ROOT}/.venv_host/bin:${PATH}"
export PYTHONPATH="${BACKEND_DIR}"

if [ -f "${BACKEND_DIR}/.env" ]; then
    set -a
    # shellcheck disable=SC1091
    source "${BACKEND_DIR}/.env"
    set +a
fi

# --- Cloud LLM & Embedding Configuration (Zero Local Ollama / No Qwen) ---
export LLM_PROVIDER="sarvam_cloud"
export AUDIT_LLM_PROVIDER="sarvam_cloud"
export SARVAM_CLOUD_MODEL="sarvam-105b"
export SARVAM_CLOUD_CLASSIFY_MODEL="sarvam-105b"
export SARVAM_REASONING_EFFORT="none"
export SARVAM_REASONING_EFFORT_FAST="none"
export SARVAM_COMPLEX_ROUTING_ENABLED="false"
export INGESTION_SKIP_LLM_CORRECTION="true"
export SARVAM_BUDGET_GUARD_ENABLED="false"
export SARVAM_DAILY_BUDGET_USD="100.0"
export SARVAM_MONTHLY_BUDGET_USD="500.0"
export SARVAM_RPM_LIMIT="60"
export SARVAM_CHAT_RESERVE_RATIO="0.0"

export QDRANT_COLLECTION="${QDRANT_COLLECTION:-spiritual_wisdom_contextual}"
export PRE_EXTRACTED_MAX_AGE_SKIP="${PRE_EXTRACTED_MAX_AGE_SKIP:-31536000}"
export EMBEDDING_BACKEND="${EMBEDDING_BACKEND:-onnx_int8}"
export RERANKER_BACKEND="${RERANKER_BACKEND:-onnx_int8}"

# Fail clearly when required connection variables are missing
for req_var in QDRANT_URL REDIS_URL SUPABASE_URL NEO4J_URI NEO4J_PASSWORD; do
    if [ -z "${!req_var}" ]; then
        echo "❌ Error: Required environment variable ${req_var} is not set." >&2
        exit 1
    fi
done

INPUT_FILE="${1:-${REPO_ROOT}/scripts/ingestion/prioritized_videos_to_reingest.txt}"
WORKERS="${2:-4}"
BATCH_SIZE="${3:-10}"

LOG_DIR="${REPO_ROOT}/logs"
mkdir -p "${LOG_DIR}"
LOG_FILE="${LOG_DIR}/bulk_ingest_master.log"

# Also symlink to /tmp for backward compatibility if permitted
ln -sf "${LOG_FILE}" /tmp/bulk_ingest_master.log 2>/dev/null || true

echo "================================================================"
echo "☕ LAUNCHING CAFFEINATED & OPTIMIZED SARVAM-105B INGESTION PIPELINE"
echo "   Model        : sarvam-105b (none reasoning, zero local Qwen)"
echo "   Correction   : Deterministic Doctrine Regex (0 LLM Tokens)"
echo "   Audit Gate   : Sarvam Cloud (1 call/discourse, ~3 paise/video)"
echo "   Embedder     : BGE-M3 (ONNX INT8 Quantized)"
echo "   Workers      : ${WORKERS}"
echo "   Batch Size   : ${BATCH_SIZE} (Aggressive Resource & Memory Recycling)"
echo "   Input File   : ${INPUT_FILE}"
echo "   Sleep Lock   : caffeinate -dimsu active"
echo "   Log File     : ${LOG_FILE}"
echo "================================================================"

cat << 'EOF' > "${REPO_ROOT}/scripts/ingestion/supervisor.sh"
#!/bin/bash
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BACKEND_DIR="${REPO_ROOT}/backend"
LOG_FILE="${REPO_ROOT}/logs/bulk_ingest_master.log"
INPUT_FILE="${1:-${REPO_ROOT}/scripts/ingestion/prioritized_videos_to_reingest.txt}"
WORKERS="${2:-4}"
BATCH_SIZE="${3:-10}"

export PATH="${REPO_ROOT}/.venv_host/bin:${PATH}"
export PYTHONPATH="${BACKEND_DIR}"

if [ -f "${BACKEND_DIR}/.env" ]; then
    set -a
    # shellcheck disable=SC1091
    source "${BACKEND_DIR}/.env"
    set +a
fi

export LLM_PROVIDER="sarvam_cloud"
export AUDIT_LLM_PROVIDER="sarvam_cloud"
export SARVAM_CLOUD_MODEL="sarvam-105b"
export SARVAM_CLOUD_CLASSIFY_MODEL="sarvam-105b"
export SARVAM_REASONING_EFFORT="none"
export SARVAM_REASONING_EFFORT_FAST="none"
export SARVAM_COMPLEX_ROUTING_ENABLED="false"
export INGESTION_SKIP_LLM_CORRECTION="true"
export SARVAM_BUDGET_GUARD_ENABLED="false"
export SARVAM_DAILY_BUDGET_USD="100.0"
export SARVAM_MONTHLY_BUDGET_USD="500.0"
export SARVAM_RPM_LIMIT="60"
export SARVAM_CHAT_RESERVE_RATIO="0.0"

echo "================================================================"
echo "☕ SUPERVISOR STARTED — AUTO-RESUME BULK INGESTION LOOP"
echo "   Target Workers : ${WORKERS}"
echo "   Batch Size     : ${BATCH_SIZE}"
echo "   Input Sources  : ${INPUT_FILE}"
echo "   Master Log     : ${LOG_FILE}"
echo "================================================================"

# Clear any stale in-flight locks from crashed runs using atomic compare-and-delete
"${REPO_ROOT}/.venv_host/bin/python3" -c '
import os, redis

CAD_LUA = """
if redis.call("get", KEYS[1]) == ARGV[1] then
    return redis.call("del", KEYS[1])
else
    return 0
end
"""

try:
    redis_url = os.environ.get("REDIS_URL")
    if not redis_url:
        raise ValueError("REDIS_URL not set")
    r = redis.from_url(redis_url, socket_timeout=3, decode_responses=True)
    cad_script = r.register_script(CAD_LUA)
    recovered = 0
    for k in r.scan_iter("ingestion_checkpoint:oneness:*:lock"):
        val = r.get(k)
        if val is None:
            continue
        ttl = r.ttl(k)
        owner_dead = False
        if val and val != "1":
            pid_str = val.split(":")[0]
            if pid_str.isdigit() and int(pid_str) > 1:
                try:
                    os.kill(int(pid_str), 0)
                except OSError:
                    owner_dead = True
        if ttl <= 0 or owner_dead:
            if cad_script(keys=[k], args=[val]):
                recovered += 1
    if recovered:
        print(f"🧹 Recovered {recovered} stale in-flight lock keys from previous run")
except Exception as e:
    pass
' >> "${LOG_FILE}" 2>&1

while true; do
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] 🚀 Starting bulk ingestion worker pool (Sarvam 105B Fast)..." >> "${LOG_FILE}"
    
    "${REPO_ROOT}/.venv_host/bin/python3" -u -m scripts.ingestion.bulk_ingest_video \
        --input "${INPUT_FILE}" \
        --batch-size "${BATCH_SIZE}" \
        --workers "${WORKERS}" >> "${LOG_FILE}" 2>&1
    
    EXIT_CODE=$?
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] ⚠️ Worker pool batch finished with exit code ${EXIT_CODE}" >> "${LOG_FILE}"

    # Aggressively release disk & memory resources between batches
    rm -rf /tmp/mukthi-yt-audio-* /var/folders/*/*/*/mukthi-yt-audio-* 2>/dev/null || true
    sync
    
    # Check if remaining sources exist
    REMAINING=$("${REPO_ROOT}/.venv_host/bin/python3" -c '
import json, os, sys, redis
try:
    redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
    r = redis.from_url(redis_url, socket_timeout=3)
    input_file = sys.argv[1] if len(sys.argv) > 1 else "scripts/ingestion/prioritized_videos_to_reingest.txt"
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
        echo "🎉 ALL SOURCES PROCESSED & VERIFIED!"
        echo "================================================================"
        break
    else
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] 🔄 Resuming pipeline in 3s (Remaining sources: ${REMAINING})..." >> "${LOG_FILE}"
        sleep 3
    fi
done
EOF
chmod +x "${REPO_ROOT}/scripts/ingestion/supervisor.sh"

nohup caffeinate -dimsu "${REPO_ROOT}/scripts/ingestion/supervisor.sh" "${INPUT_FILE}" "${WORKERS}" "${BATCH_SIZE}" >> "${LOG_FILE}" 2>&1 &

INGEST_PID=$!
echo "${INGEST_PID}" > /tmp/bulk_ingest_master.pid
echo "Supervisor and Ingestion running in background under PID ${INGEST_PID}"
