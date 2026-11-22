#!/usr/bin/env bash
# ==============================================================================
# AskMukthiGuru - WhatsApp Business Credentials Secure Configurator
# ==============================================================================
# This script prompts for Meta WhatsApp credentials interactively with hidden
# input (read -s) so your secrets are never displayed on screen, never logged
# to shell history, and NEVER seen by the AI assistant.
# It pushes them directly to your Railway production service.
# ==============================================================================

set -euo pipefail

SERVICE_NAME="askmukthiguru-8119b0e8"

echo ""
echo "=================================================================="
echo "  🔒 AskMukthiGuru - Secure WhatsApp Credentials Setup"
echo "=================================================================="
echo "  Target Railway Service: ${SERVICE_NAME}"
echo "  Your inputs are hidden on screen for privacy."
echo "=================================================================="
echo ""

# 1. Meta App Secret (Hidden input)
while true; do
    read -r -s -p "🔑 Enter META_APP_SECRET (hidden): " APP_SECRET
    echo ""
    if [[ -n "${APP_SECRET// }" ]]; then
        break
    fi
    echo "⚠️  App Secret cannot be empty. Please try again."
done

# 2. Meta Phone Number ID (Visible input, not a secret)
while true; do
    read -r -p "📱 Enter META_PHONE_NUMBER_ID (e.g., 104829104857201): " PHONE_ID
    if [[ -n "${PHONE_ID// }" ]]; then
        break
    fi
    echo "⚠️  Phone Number ID cannot be empty. Please try again."
done

# 3. Meta Access Token (Hidden input)
while true; do
    read -r -s -p "🎫 Enter META_ACCESS_TOKEN (starts with EAA..., hidden): " ACCESS_TOKEN
    echo ""
    if [[ -n "${ACCESS_TOKEN// }" ]]; then
        break
    fi
    echo "⚠️  Access Token cannot be empty. Please try again."
done

echo ""
echo "⏳ Uploading variables directly to Railway service '${SERVICE_NAME}'..."

# Configure Railway variables securely using railway CLI
railway variable set \
    "META_APP_SECRET=${APP_SECRET}" \
    "META_PHONE_NUMBER_ID=${PHONE_ID}" \
    "META_ACCESS_TOKEN=${ACCESS_TOKEN}" \
    --service "${SERVICE_NAME}"

echo ""
echo "=================================================================="
echo "  ✅ SUCCESS! WhatsApp credentials configured on Railway."
echo "  Railway is now restarting '${SERVICE_NAME}' with your credentials."
echo "=================================================================="
echo ""
