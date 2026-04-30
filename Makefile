.PHONY: help install dev lint format test docker-up docker-down clean logs shell

# Colors for terminal output
YELLOW=\033[1;33m
GREEN=\033[1;32m
NC=\033[0m # No Color

help: ## Show this help message
	@echo "AskMukthiGuru Developer Commands:"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  ${YELLOW}%-15s${NC} %s\n", $$1, $$2}'

# --- Local Development ---

install: ## Install dependencies and pre-commit hooks locally
	@echo "${GREEN}Installing backend dependencies...${NC}"
	@cd backend && if command -v uv >/dev/null; then uv pip install -e ".[dev]"; else pip install -e ".[dev]"; fi
	@echo "${GREEN}Installing frontend dependencies...${NC}"
	@npm install
	@echo "${GREEN}Installing pre-commit hooks...${NC}"
	@pip install pre-commit && pre-commit install

dev: ## Start local development servers (Backend & Frontend)
	@echo "${GREEN}Starting development environment...${NC}"
	@chmod +x backend/start_local.sh
	@cd backend && ./start_local.sh

lint: ## Run Ruff linter on backend
	@echo "${GREEN}Running linter...${NC}"
	@cd backend && ruff check .

format: ## Run Ruff formatter on backend
	@echo "${GREEN}Formatting code...${NC}"
	@cd backend && ruff format .

test: ## Run backend unit tests
	@echo "${GREEN}Running tests...${NC}"
	@cd backend && pytest

# --- Docker Deployment ---

docker-up: ## Build and start the full Docker stack in detached mode
	@echo "${GREEN}Starting full Docker stack...${NC}"
	@cd backend && docker compose up -d --build

docker-down: ## Stop and remove all Docker containers
	@echo "${GREEN}Stopping Docker stack...${NC}"
	@cd backend && docker compose down

clean: ## Stop Docker, remove volumes, and clean local caches
	@echo "${YELLOW}Cleaning up volumes and caches...${NC}"
	@cd backend && docker compose down -v
	@find . -type d -name "__pycache__" -exec rm -rf {} +
	@find . -type d -name ".pytest_cache" -exec rm -rf {} +
	@find . -type d -name ".ruff_cache" -exec rm -rf {} +
	@rm -rf node_modules
	@echo "${GREEN}Clean complete.${NC}"

logs: ## Tail the logs of all Docker services
	@cd backend && docker compose logs -f

shell: ## Open a shell inside the running backend container
	@cd backend && docker compose exec backend /bin/bash || docker compose exec backend /bin/sh
