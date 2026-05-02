#!/usr/bin/env bash
# ============================================================
# Mukthi Guru — Local Deployment and Portal Dashboard
# ============================================================

set -e

# Colors for terminal output
CYAN='\033[1;36m'
YELLOW='\033[1;33m'
GREEN='\033[1;32m'
NC='\033[0m'

printf "${CYAN}============================================================${NC}\n"
printf "🚀 Starting AskMukthiGuru Deployment Dashboard\n"
printf "${CYAN}============================================================${NC}\n"

# Run make docker-up to start everything
make docker-up

printf "\n"
printf "${GREEN}✅ Full deployment successful! Here are your clickable local URLs:${NC}\n"
printf "${CYAN}============================================================${NC}\n"
printf "  🌐 ${YELLOW}Supabase API/Auth:${NC}       http://localhost:54321\n"
printf "  📊 ${YELLOW}Supabase Studio Dashboard:${NC} http://localhost:54323\n"
printf "  🎨 ${YELLOW}Main App (Vite):${NC}           http://localhost:80\n"
printf "  💬 ${YELLOW}Premium Chat Portal:${NC}       http://localhost/chat\n"
printf "  📥 ${YELLOW}Admin Ingestion Portal:${NC}    http://localhost/ingest\n"
printf "  📜 ${YELLOW}Backend API / Swagger UI:${NC}  http://localhost:8000/docs\n"
printf "${CYAN}============================================================${NC}\n"
