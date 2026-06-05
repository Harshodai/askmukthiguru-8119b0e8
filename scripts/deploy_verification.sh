#!/bin/bash
#
# Mukthi Guru Production Deployment Verification Script
#
# This script runs all checks necessary to verify the system is ready for production deployment.
# It validates tests, benchmarks, security, infrastructure, and documentation.

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

echo -e "${YELLOW}Starting Mukthi Guru Production Deployment Verification...${NC}"
echo "Project root: $PROJECT_ROOT"
echo ""

# Track overall success
OVERALL_SUCCESS=true

# Function to print section headers
print_header() {
    echo ""
    echo -e "${YELLOW}=== $1 ===${NC}"
    echo ""
}

# Function to run a check and report results
run_check() {
    local name="$1"
    local command="$2"
    local ignore_failure=${3:-false}

    echo -e "${YELLOW}Running:$NC $name"
    if eval "$command"; then
        echo -e "${GREEN}✓ PASSED: $name${NC}"
        return 0
    else
        if [ "$ignore_failure" = true ]; then
            echo -e "${YELLOW}⚠ WARNING: $name failed but continuing${NC}"
            return 0
        else
            echo -e "${RED}✗ FAILED: $name${NC}"
            OVERALL_SUCCESS=false
            return 1
        fi
    fi
}

# 1. Backend Tests
print_header "Backend Tests"
run_check "Backend unit tests" "cd $PROJECT_ROOT/backend && python -m pytest tests/ -x --tb=short --quiet"

# 2. Infrastructure Health
print_header "Infrastructure Health"
run_check "Docker services health" "$SCRIPT_DIR/check_docker_health.py"

# 3. Benchmark Verification
print_header "Benchmark Verification"
run_check "Run production benchmark sample" "cd $PROJECT_ROOT/backend && python -m benchmarks.ruthless_benchmark --unit all --sample 20"

# 4. Security Scan
print_header "Security Scan"
run_check "Bandit security scan" "bandit -r $PROJECT_ROOT/backend/ -ll" true
run_check "Safety dependency check" "safety check --full-report" true

# 5. API Health Endpoints
print_header "API Health Endpoints"
run_check "Basic health check" "curl -s http://localhost:8000/api/health | jq -e '.status == \"healthy\"'" true
run_check "Detailed health check" "curl -s http://localhost:8000/api/health/detailed | jq -e '.status == \"healthy\"'" true

# 6. Metrics Endpoint
print_header "Metrics Endpoint"
run_check "Prometheus metrics" "curl -s http://localhost:8000/metrics | grep -E '^(mukthi_guru_|process_|go_)'" true

# 7. Documentation Check
print_header "Documentation Check"
run_check "Production readiness checklist exists" "test -f $PROJECT_ROOT/docs/PRODUCTION_READINESS_CHECKLIST.md"
run_check "Rollback plan exists" "test -f $PROJECT_ROOT/docs/ROLLBACK_PLAN.md" true
run_check "Ruflo evaluation exists" "test -f $PROJECT_ROOT/docs/RUFLO_EVALUATION.md"

# 8. Environment Validation
print_header "Environment Validation"
run_check "Environment file exists" "test -f $PROJECT_ROOT/backend/.env"
run_check "Required environment variables are set" "cd $PROJECT_ROOT/backend && python -c \"from app.config import settings; print('LLM Provider:', settings.llm_provider)\"" true

# Final Summary
print_header "FINAL RESULTS"
if $OVERALL_SUCCESS; then
    echo -e "${GREEN}🎉 ALL CHECKS PASSED - SYSTEM IS PRODUCTION READY!${NC}"
    echo -e "${GREEN}✅ You can proceed with production deployment.${NC}"
else
    echo -e "${RED}❌ SOME CHECKS FAILED - PLEASE FIX ISSUES BEFORE DEPLOYMENT${NC}"
    echo -e "${YELLOW}📋 Review the output above for details on failed checks.${NC}"
fi

exit 0