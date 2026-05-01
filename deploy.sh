#!/usr/bin/env bash
# ============================================================
# Mukthi Guru — Deployment Script
# ============================================================
# Builds and pushes Docker images to a container registry,
# then provides instructions for deploying to the remote server.

set -e

# Configuration
REGISTRY="ghcr.io/your-username"
VERSION=$(git rev-parse --short HEAD 2>/dev/null || echo "latest")
BACKEND_IMAGE="${REGISTRY}/askmukthiguru-backend:${VERSION}"
FRONTEND_IMAGE="${REGISTRY}/askmukthiguru-frontend:${VERSION}"

echo "============================================================"
echo "🚀 Starting AskMukthiGuru Deployment Prep"
echo "============================================================"

# 1. Build Backend
echo "📦 Building Backend Image: $BACKEND_IMAGE"
docker build -t "$BACKEND_IMAGE" -f backend/Dockerfile .
docker tag "$BACKEND_IMAGE" "${REGISTRY}/askmukthiguru-backend:latest"

# 2. Build Frontend
echo "📦 Building Frontend Image: $FRONTEND_IMAGE"
docker build -t "$FRONTEND_IMAGE" -f frontend.Dockerfile .
docker tag "$FRONTEND_IMAGE" "${REGISTRY}/askmukthiguru-frontend:latest"

# 3. Push Images (Commented out by default to prevent accidental pushes)
echo "============================================================"
echo "✅ Images built successfully!"
echo ""
echo "To push these images to your registry, run:"
echo "  docker push ${REGISTRY}/askmukthiguru-backend:latest"
echo "  docker push ${REGISTRY}/askmukthiguru-frontend:latest"
echo ""
echo "To deploy to your VPS, copy 'docker-compose.prod.yml' and run:"
echo "  docker compose -f docker-compose.prod.yml up -d"
echo "============================================================"
