.PHONY: help install dev lint format test eval docker-up docker-rebuild-web docker-down clean logs shell backup restore flush-cache minikube-up minikube-down minikube-rebuild minikube-test minikube-logs

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

eval: ## Run tests plus the >95% benchmark release gate against a running backend
	@echo "${GREEN}Running production eval gate...${NC}"
	@cd backend && pytest
	@cd backend && python3 benchmarks/ruthless_benchmark.py --endpoint "$${BENCHMARK_ENDPOINT:-http://localhost:8000}" --test-key "$${BENCHMARK_TEST_KEY:-$${JWT_SECRET:-}}" --min-score 0.95 --min-category-score 0.90 --stability-runs "$${BENCHMARK_STABILITY_RUNS:-3}"

# --- Docker Deployment ---

# Clean Docker config path (no credential helper – avoids macOS keychain -25293)
DOCKER_CONFIG_CLEAN = /Users/harshodaikolluru/Public/askmukthiguru-8119b0e8/.docker_clean
DOCKER_BIN = /Users/harshodaikolluru/.docker/bin

# Use scripts/docker-safe.sh for any target that builds/pulls images (avoids keychain errors)
# The script temporarily strips 'credsStore' from ~/.docker/config.json to avoid
# Docker Desktop's macOS keychain "The user name or passphrase you entered is
# not correct. (-25293)" error during image pulls.

docker-up: ## Build and start the full Docker stack in detached mode
	@echo "${GREEN}Starting full Docker stack...${NC}"
	@cd backend && bash ../scripts/docker-safe.sh docker compose up -d --build

docker-rebuild: ## Rebuild without cache and restart Docker (automatically backs up and restores data!)
	@echo "${YELLOW}Taking protective snapshot of all databases before rebuilding...${NC}"
	@python3 scripts/backup/snapshot_manager.py backup || true
	@echo "${GREEN}Rebuilding full Docker stack without cache...${NC}"
	@cd backend && bash ../scripts/docker-safe.sh docker compose build --no-cache && bash ../scripts/docker-safe.sh docker compose up -d --force-recreate
	@echo "${YELLOW}Waiting 15 seconds for database containers to boot...${NC}"
	@sleep 15
	@echo "${GREEN}Restoring database state from protective snapshot...${NC}"
	@python3 scripts/backup/snapshot_manager.py restore || true

docker-rebuild-web: ## Rebuild and restart only the stateless frontend and backend services (no data loss!)
	@echo "${GREEN}Rebuilding and starting frontend and backend services...${NC}"
	@cd backend && bash ../scripts/docker-safe.sh docker compose up -d --build frontend backend

docker-down: ## Stop and remove all Docker containers
	@echo "${GREEN}Stopping Docker stack...${NC}"
	@cd backend && DOCKER_CONFIG=$(DOCKER_CONFIG_CLEAN) PATH=$(DOCKER_BIN):$$PATH docker compose down

clean: ## Stop Docker, remove volumes, and clean local caches (automatically backs up first!)
	@echo "${YELLOW}Taking protective snapshot of all databases before clean...${NC}"
	@python3 scripts/backup/snapshot_manager.py backup || true
	@echo "${YELLOW}Cleaning up volumes and caches...${NC}"
	@cd backend && DOCKER_CONFIG=$(DOCKER_CONFIG_CLEAN) PATH=$(DOCKER_BIN):$$PATH docker compose down -v
	@find . -type d -name "__pycache__" -exec rm -rf {} +
	@find . -type d -name ".pytest_cache" -exec rm -rf {} +
	@find . -type d -name ".ruff_cache" -exec rm -rf {} +
	@rm -rf node_modules
	@echo "${GREEN}Clean complete.${NC}"

backup: ## Take a comprehensive snapshot of Qdrant, Neo4j, and Supabase data
	@python3 scripts/backup/snapshot_manager.py backup

restore: ## Restore Qdrant, Neo4j, and Supabase data from snapshots
	@python3 scripts/backup/snapshot_manager.py restore

flush-cache: ## Flush query-side caches (Qdrant semantic cache + Redis) safely without impacting ingestion
	@echo "${GREEN}Flushing query-side caches (Qdrant semantic cache + Redis)...${NC}"
	@cd backend && DOCKER_CONFIG=$(DOCKER_CONFIG_CLEAN) PATH=$(DOCKER_BIN):$$PATH docker compose exec -T backend python3 /app/../scripts/ops/flush_cache.py 2>/dev/null || \
		 DOCKER_CONFIG=$(DOCKER_CONFIG_CLEAN) PATH=$(DOCKER_BIN):$$PATH docker compose exec -T backend python3 scripts/ops/flush_cache.py 2>/dev/null || \
		 (echo "⚠️  Could not exec into container, running host-side fallback (Redis only)..." && python3 scripts/ops/flush_cache.py)

logs: ## Tail the logs of all Docker services
	@cd backend && DOCKER_CONFIG=$(DOCKER_CONFIG_CLEAN) PATH=$(DOCKER_BIN):$$PATH docker compose logs -f

shell: ## Open a shell inside the running backend container
	@cd backend && DOCKER_CONFIG=$(DOCKER_CONFIG_CLEAN) PATH=$(DOCKER_BIN):$$PATH docker compose exec backend /bin/bash || DOCKER_CONFIG=$(DOCKER_CONFIG_CLEAN) PATH=$(DOCKER_BIN):$$PATH docker compose exec backend /bin/sh

deploy: ## Build production images and prepare for remote deployment
	@chmod +x deploy.sh
	@./deploy.sh

# --- Minikube Kubernetes Demo ---

minikube-up: ## Start Minikube and deploy via Helm one-shot
	@chmod +x k8s/minikube/start.sh
	@bash k8s/minikube/start.sh

minikube-down: ## Delete the Minikube cluster and all resources
	@echo "${YELLOW}Deleting Minikube cluster...${NC}"
	@minikube delete -p mukthiguru

minikube-rebuild: ## Rebuild Docker images and restart all deployments in Minikube
	@echo "${GREEN}Rebuilding images in Minikube...${NC}"
	@eval $$(minikube docker-env -p mukthiguru); \
		docker build -t mukthiguru-backend:latest -f backend/Dockerfile . ; \
		docker build -t mukthiguru-frontend:latest -f Dockerfile .
	@echo "${GREEN}Rolling restart all deployments...${NC}"
	@kubectl rollout restart deployment/mukthiguru-backend -n mukthiguru
	@kubectl rollout restart deployment/mukthiguru-frontend -n mukthiguru

minikube-test: ## Run a simple load test against the Minikube deployment
	@echo "${GREEN}Testing deployment...${NC}"
	@if minikube profile list | grep -q "mukthiguru"; then \
		MIP=$$(minikube ip -p mukthiguru); \
		curl -s "http://$$MIP/api/health" || echo "Health check failed"; \
		curl -s "http://$$MIP/api/ready" || echo "Ready check failed"; \
	else \
		echo "Minikube not running, start it with: make minikube-up"; \
	fi

minikube-logs: ## Stream backend logs in Minikube
	@kubectl logs -f deployment/mukthiguru-backend -n mukthiguru
