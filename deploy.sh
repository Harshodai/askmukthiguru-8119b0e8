#!/bin/bash
# Quick deploy script
export PATH="/Applications/Docker.app/Contents/Resources/bin:$PATH"

echo "=== Checking Docker ==="
docker --version
docker compose version

echo ""
echo "=== Checking running containers ==="
docker ps

echo ""
echo "=== Starting all services ==="
cd /Users/harshodaikolluru/Public/askmukthiguru-8119b0e8/backend
docker compose up -d --build 2>&1

echo ""
echo "=== Done ==="
docker compose ps
