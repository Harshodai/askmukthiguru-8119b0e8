#!/usr/bin/env bash
# ============================================================
# Mukthi Guru — Kubernetes Production Deploy
# ============================================================
# Usage:
#   export SUPABASE_URL="https://xxx.supabase.co"
#   export SUPABASE_KEY="eyJxxx"
#   export NEO4J_PASSWORD="changeme"
#   export SARVAM_API_KEY="sk-xxx"
#   export OPENROUTER_API_KEY="sk-xxx"
#   ./infrastructure/k8s_deploy.sh
#
# Prerequisites:
#   - kubectl configured for target cluster
#   - envsubst (part of gettext) installed
#   - Helm (for Grafana/Prometheus if monitoring is needed)
# ============================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NAMESPACE="${NAMESPACE:-mukthiguru}"

# Resolve ${VAR} placeholders from environment before applying
envsubst < "${SCRIPT_DIR}/k8s_deployment.yaml" | kubectl apply -f -

echo "✅ K8s manifests applied to namespace '${NAMESPACE}'"

# Optionally seed secrets from a .env file if one exists
ENV_FILE="${SCRIPT_DIR}/../.env.production"
if [[ -f "$ENV_FILE" ]]; then
    echo "📄 .env.production found — exporting variables before deploy"
    set -a
    source "$ENV_FILE"
    set +a
    envsubst < "${SCRIPT_DIR}/k8s_deployment.yaml" | kubectl apply -f -
fi
