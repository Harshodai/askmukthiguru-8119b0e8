.PHONY: help install dev lint format format-check test coverage type-check quality eval docker-up docker-rebuild-web docker-down clean logs shell backup restore flush-cache minikube-up minikube-down minikube-rebuild minikube-test minikube-logs dev-up dev-down dev-reset test-backend test-frontend benchmark memgraph-up memgraph-down memgraph-cli neo4j-fallback-up neo4j-fallback-down configure-qdrant configure-qdrant-dry-run canonicalize-aliases canonicalize-aliases-dry-run test-advanced-rag railway-clean railway-rebuild railway-worker-pause railway-worker-resume railway-prune-deployments railway-clean-local railway-check-budget

# Resolve Python tooling deterministically. Backend tests run inside backend/,
# so prefer its managed virtual environment over an unrelated root environment.
ROOT_DIR := $(shell dirname $(realpath $(lastword $(MAKEFILE_LIST))))
BACKEND_VENV := $(ROOT_DIR)/backend/.venv
ROOT_VENV := $(ROOT_DIR)/.venv
PYTHON := $(shell if [ -x "$(BACKEND_VENV)/bin/python3" ]; then echo "$(BACKEND_VENV)/bin/python3"; elif [ -x "$(ROOT_VENV)/bin/python3" ]; then echo "$(ROOT_VENV)/bin/python3"; else echo "python3"; fi)
PYTEST := $(shell if [ -x "$(BACKEND_VENV)/bin/pytest" ]; then echo "$(BACKEND_VENV)/bin/pytest"; elif [ -x "$(ROOT_VENV)/bin/pytest" ]; then echo "$(ROOT_VENV)/bin/pytest"; else echo "pytest"; fi)
RUFF := $(shell if [ -x "$(BACKEND_VENV)/bin/ruff" ]; then echo "$(BACKEND_VENV)/bin/ruff"; elif [ -x "$(ROOT_VENV)/bin/ruff" ]; then echo "$(ROOT_VENV)/bin/ruff"; else echo "ruff"; fi)
BANDIT := $(shell if [ -x "$(BACKEND_VENV)/bin/bandit" ]; then echo "$(BACKEND_VENV)/bin/bandit"; elif [ -x "$(ROOT_VENV)/bin/bandit" ]; then echo "$(ROOT_VENV)/bin/bandit"; else echo "bandit"; fi)

# Colors for terminal output
YELLOW=\033[1;33m
GREEN=\033[1;32m
NC=\033[0m # No Color

help: ## Show this help message
	@echo "AskMukthiGuru Developer Commands:"
	@echo ""
	@grep -E '^[a-zA-Z0-9_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  ${YELLOW}%-19s${NC} %s\n", $$1, $$2}'

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

supabase-edge: ## Start Supabase Edge Functions runtime with env vars
	@echo "${GREEN}Starting Edge Functions runtime...${NC}"
	@cd supabase && (npx supabase functions serve --env-file functions/.env &)

lint: ## Run Ruff linter on backend
	@echo "${GREEN}Running linter...${NC}"
	@cd backend && $(RUFF) check .

format: ## Run Ruff formatter on backend
	@echo "${GREEN}Formatting code...${NC}"
	@cd backend && $(RUFF) format .

format-check: ## Verify Ruff formatting without writing changes (CI-equivalent)
	@echo "${GREEN}Checking formatting...${NC}"
	@cd backend && $(RUFF) format --check .

test: ## Run backend unit tests
	@echo "${GREEN}Running tests...${NC}"
	@cd backend && $(PYTEST)

coverage: ## Run backend tests with the coverage floor enforced (pyproject [tool.coverage.report] fail_under)
	@echo "${GREEN}Running tests with coverage (floor in backend/pyproject.toml)...${NC}"
	@cd backend && $(PYTEST) --cov=app --cov=rag --cov=domain --cov=services --cov=routers --cov=ingest --cov=schemas --cov=tasks --cov-report=term

type-check: ## mypy ratchet against the recorded baseline (tests/test_type_check_baseline.py)
	@echo "${GREEN}Running mypy ratchet...${NC}"
	@cd backend && $(PYTEST) tests/test_type_check_baseline.py -v

quality: ## Full local quality battery — same verdict as CI (lint, format, security, coverage floor, mypy ratchet, wiring/perf guards)
	@echo "${GREEN}[1/5] Ruff lint...${NC}"
	@cd backend && $(RUFF) check .
	@echo "${GREEN}[2/5] Ruff format check...${NC}"
	@cd backend && $(RUFF) format --check .
	@echo "${GREEN}[3/5] Bandit security scan...${NC}"
	@cd backend && $(BANDIT) -r app rag services routers domain ingest schemas tasks --severity-level medium --confidence-level medium --quiet --ini .bandit
	@echo "${GREEN}[4/5] JWT_SECRET benchmark-backdoor guard...${NC}"
	@$(PYTHON) scripts/security/check_benchmark_backdoor.py
	@echo "${GREEN}[5/5] pytest — coverage floor, mypy ratchet, wiring/perf guards, full suite...${NC}"
	@cd backend && $(PYTEST) --cov=app --cov=rag --cov=domain --cov=services --cov=routers --cov=ingest --cov=schemas --cov=tasks --cov-report=term
	@echo "${GREEN}make quality: all gates passed.${NC}"

eval: ## Run tests plus the >95% benchmark release gate against a running backend
	@echo "${GREEN}Running production eval gate...${NC}"
	@cd backend && $(PYTEST)
	@cd backend && $(PYTHON) benchmarks/ruthless_benchmark.py --endpoint "$${BENCHMARK_ENDPOINT:-http://localhost:8000}" --test-key "$${BENCHMARK_TEST_KEY:-$${JWT_SECRET:-$$([ -f .env ] && grep -E '^JWT_SECRET=' .env | cut -d= -f2- || echo "")}}" --min-score 0.95 --min-category-score 0.90 --stability-runs "$${BENCHMARK_STABILITY_RUNS:-2}"

# --- Docker Deployment ---

# Clean Docker config path (no credential helper – avoids macOS keychain -25293)
DOCKER_CONFIG_CLEAN = /Users/harshodaikolluru/Public/askmukthiguru-8119b0e8/.docker_clean
DOCKER_BIN = /Users/harshodaikolluru/.docker/bin

# Use scripts/docker-safe.sh for any target that builds/pulls images (avoids keychain errors)
# The script temporarily strips 'credsStore' from ~/.docker/config.json to avoid
# Docker Desktop's macOS keychain "The user name or passphrase you entered is
# not correct. (-25293)" error during image pulls.

docker-pull-models: ## Pre-download embedding + reranker models to local cache before Docker build
	@echo "${GREEN}Pre-downloading ML models to build cache...${NC}"
	@cd backend && $(PYTHON) scripts/download_models.py
	@echo "${GREEN}Models downloaded.${NC}"

docker-up: ## Build and start the full Docker stack in detached mode
	@echo "${GREEN}Starting full Docker stack (all services)...${NC}"
	@cd backend && bash ../scripts/docker-safe.sh docker compose up -d --build

docker-rebuild: ## Rebuild without cache and restart Docker (automatically backs up and restores data!)
	@echo "${YELLOW}Taking protective snapshot of all databases before rebuilding...${NC}"
	@$(PYTHON) scripts/backup/snapshot_manager.py backup || true
	@echo "${GREEN}Rebuilding full Docker stack without cache...${NC}"
	@cd backend && bash ../scripts/docker-safe.sh docker compose build --no-cache && bash ../scripts/docker-safe.sh docker compose up -d --force-recreate
	@echo "${YELLOW}Waiting 15 seconds for database containers to boot...${NC}"
	@sleep 15
	@echo "${GREEN}Restoring database state from protective snapshot...${NC}"
	@$(PYTHON) scripts/backup/snapshot_manager.py restore || true

docker-rebuild-web: ## Rebuild and restart only the stateless frontend and backend services (no data loss!)
	@echo "${GREEN}Rebuilding and starting frontend and backend services...${NC}"
	@cd backend && bash ../scripts/docker-safe.sh docker compose up -d --build frontend backend

docker-down: ## Stop and remove all Docker containers
	@echo "${GREEN}Stopping Docker stack...${NC}"
	@cd backend && DOCKER_CONFIG=$(DOCKER_CONFIG_CLEAN) PATH=$(DOCKER_BIN):$$PATH docker compose down

clean: ## Stop Docker, remove volumes, and clean local caches (automatically backs up first!)
	@echo "${YELLOW}Taking protective snapshot of all databases before clean...${NC}"
	@$(PYTHON) scripts/backup/snapshot_manager.py backup || true
	@echo "${YELLOW}Cleaning up volumes and caches...${NC}"
	@cd backend && DOCKER_CONFIG=$(DOCKER_CONFIG_CLEAN) PATH=$(DOCKER_BIN):$$PATH docker compose down -v
	@find . -type d -name "__pycache__" -exec rm -rf {} +
	@find . -type d -name ".pytest_cache" -exec rm -rf {} +
	@find . -type d -name ".ruff_cache" -exec rm -rf {} +
	@rm -rf node_modules
	@echo "${GREEN}Clean complete.${NC}"

backup: ## Take a comprehensive snapshot of Qdrant, Neo4j, and Supabase data
	@$(PYTHON) scripts/backup/snapshot_manager.py backup

restore: ## Restore Qdrant, Neo4j, and Supabase data from snapshots
	@$(PYTHON) scripts/backup/snapshot_manager.py restore

flush-cache: ## Flush all four cache layers (Redis + Qdrant semantic + in-process restart + frontend note)
	@echo "${GREEN}[1-2/4] Flushing Redis + Qdrant semantic cache...${NC}"
	@cd backend && DOCKER_CONFIG=$(DOCKER_CONFIG_CLEAN) PATH=$(DOCKER_BIN):$$PATH docker compose exec -T backend python3 /app/../scripts/ops/flush_cache.py 2>/dev/null || \
		 DOCKER_CONFIG=$(DOCKER_CONFIG_CLEAN) PATH=$(DOCKER_BIN):$$PATH docker compose exec -T backend python3 scripts/ops/flush_cache.py 2>/dev/null || \
		 (echo "⚠️  Could not exec into container, running host-side fallback (Redis only)..." && $(PYTHON) scripts/ops/flush_cache.py)
	@echo "${GREEN}[3/4] Restarting backend to clear in-process caches (hot / in-mem semantic / TurboQuant vector / doctrine_terms)...${NC}"
	@cd backend && DOCKER_CONFIG=$(DOCKER_CONFIG_CLEAN) PATH=$(DOCKER_BIN):$$PATH docker compose restart backend
	@echo "${YELLOW}[4/4] Frontend responseCache lives in the browser's localStorage — it cannot be cleared from here.${NC}"
	@echo "${YELLOW}      Clear it in the app's DevTools console:${NC}"
	@echo "        Object.keys(localStorage).filter(k=>/cache|response|conversation/i.test(k)).forEach(k=>localStorage.removeItem(k))"
	@echo "${GREEN}Cache flush complete (3/4 server-side; the frontend layer is a one-line manual step above).${NC}"

logs: ## Tail the logs of all Docker services
	@cd backend && DOCKER_CONFIG=$(DOCKER_CONFIG_CLEAN) PATH=$(DOCKER_BIN):$$PATH docker compose logs -f

shell: ## Open a shell inside the running backend container
	@cd backend && DOCKER_CONFIG=$(DOCKER_CONFIG_CLEAN) PATH=$(DOCKER_BIN):$$PATH docker compose exec backend /bin/bash || DOCKER_CONFIG=$(DOCKER_CONFIG_CLEAN) PATH=$(DOCKER_BIN):$$PATH docker compose exec backend /bin/sh

deploy: ## Build production images and prepare for remote deployment
	@chmod +x deploy.sh
	@./deploy.sh

# --- Graph Database Management (Memgraph & Neo4j Fallback) ---

memgraph-up: ## Start Memgraph container (primary graph database on port 7687)
	@echo "${GREEN}Starting Memgraph (primary graph database)...${NC}"
	@cd backend && bash ../scripts/docker-safe.sh docker compose up -d memgraph

memgraph-down: ## Stop Memgraph container
	@echo "${YELLOW}Stopping Memgraph...${NC}"
	@docker stop mukthiguru-memgraph 2>/dev/null || true

memgraph-cli: ## Open interactive mgconsole shell in Memgraph
	@docker exec -it mukthiguru-memgraph mgconsole --username neo4j --password $${NEO4J_PASSWORD:-mukthiguru_neo4j_pass}

neo4j-fallback-up: ## Start legacy Neo4j container on port 7689 (fallback)
	@echo "${GREEN}Starting legacy Neo4j fallback on port 7689...${NC}"
	@cd backend && bash ../scripts/docker-safe.sh docker compose --profile legacy-neo4j up -d neo4j

neo4j-fallback-down: ## Stop legacy Neo4j fallback container
	@echo "${YELLOW}Stopping legacy Neo4j...${NC}"
	@docker stop mukthiguru-neo4j 2>/dev/null || true

# --- Advanced RAG Management (Qdrant, Memgraph, LightRAG) ---

configure-qdrant: ## Configure Qdrant INT8 quantization, payload indexes, and run verification probes
	@echo "${GREEN}Configuring Qdrant advanced architecture (quantization & indexes)...${NC}"
	@cd backend && $(PYTHON) scripts/ops/configure_qdrant_advanced.py --apply

configure-qdrant-dry-run: ## Inspect Qdrant collections and verify Universal Queries in dry-run mode
	@echo "${YELLOW}Running Qdrant advanced architecture inspect/dry-run...${NC}"
	@cd backend && $(PYTHON) scripts/ops/configure_qdrant_advanced.py

canonicalize-aliases: ## Resolve and link teacher and concept aliases to canonical nodes in Memgraph
	@echo "${GREEN}Running teacher & concept alias canonicalization in Memgraph...${NC}"
	@cd backend && $(PYTHON) scripts/ops/canonicalize_teacher_aliases.py --apply

canonicalize-aliases-dry-run: ## Dry-run teacher and concept alias canonicalization
	@echo "${YELLOW}Running teacher & concept alias canonicalization (dry-run)...${NC}"
	@cd backend && $(PYTHON) scripts/ops/canonicalize_teacher_aliases.py

test-advanced-rag: ## Run complete advanced RAG test suite (Qdrant, LightRAG, Memgraph)
	@echo "${GREEN}Running advanced RAG test suite...${NC}"
	@cd backend && $(PYTEST) tests/test_qdrant_quantization.py tests/test_qdrant_advanced_architecture.py tests/test_lightrag_dual_level_and_aliases.py tests/test_atomic_graphrag_and_guardrails.py

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

# --- Dev Loop (qdrant + redis only) ---

dev-up: ## Start minimal dev stack (qdrant + redis) via docker compose
	@bash scripts/dev-up.sh

dev-down: ## Stop minimal dev stack
	@bash scripts/dev-down.sh

dev-reset: ## Wipe dev volumes and recreate stack
	@bash scripts/dev-reset.sh

test-backend: ## Run backend pytest suite
	@cd backend && $(PYTEST)

test-frontend: ## Run frontend Vitest suite
	@npm test

benchmark: ## Run smoke doctrine benchmark (golden_eval pending Phase 1.5b)
	@cd backend && $(PYTHON) benchmarks/smoke_doctrine.py

# --- Railway Operations & Cost Management ---

railway-clean: ## Run safe Railway state cleanup (flush query caches, release dead locks, clean temp files)
	@echo "${GREEN}Running safe Railway cleanup...${NC}"
	@$(PYTHON) scripts/ops/railway_cleanup.py --mode safe

railway-rebuild: ## Clean state and rebuild/deploy services to Railway
	@echo "${YELLOW}Executing clean rebuild and deploy to Railway...${NC}"
	@bash deploy_railway.sh --rebuild

railway-worker-pause: ## Pause Railway Celery worker to save compute budget (protects \$25 limit)
	@echo "${YELLOW}Pausing Railway Celery worker...${NC}"
	@$(PYTHON) scripts/ops/railway_cleanup.py --worker-action pause

railway-worker-resume: ## Resume Railway Celery worker for ingestion jobs
	@echo "${GREEN}Resuming Railway Celery worker...${NC}"
	@$(PYTHON) scripts/ops/railway_cleanup.py --worker-action resume

railway-prune-deployments: ## Prune dead/failed deployments from Railway project history
	@echo "${GREEN}Pruning inactive/failed deployments on Railway...${NC}"
	@$(PYTHON) scripts/ops/railway_cleanup.py --mode deployments

railway-clean-local: ## Clean local workspace build caches (__pycache__, test caches, logs)
	@echo "${GREEN}Cleaning local workspace build artifacts...${NC}"
	@$(PYTHON) scripts/ops/railway_cleanup.py --mode local

railway-check-budget: ## Check projected Railway monthly spend against \$25 hard limit
	@$(PYTHON) scripts/ops/railway_cleanup.py --check-budget
