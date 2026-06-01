#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
PROFILE="mukthiguru"

echo "=== Mukthi Guru Minikube Setup ==="

# Check if minikube is installed
if ! command -v minikube &> /dev/null; then
    echo "Error: minikube is not installed. Please install it first:"
    echo "  brew install minikube    # macOS"
    echo "  or visit https://minikube.sigs.k8s.io/docs/start/"
    exit 1
fi

# Check if helm is installed
if ! command -v helm &> /dev/null; then
    echo "Error: helm is not installed. Please install it first:"
    echo "  brew install helm    # macOS"
    exit 1
fi

# Start minikube
echo ""
echo "Starting Minikube cluster..."
minikube start \
  --profile "$PROFILE" \
  --cpus 8 \
  --memory 16384 \
  --driver docker \
  --kubernetes-version v1.30.0

# Enable addons
echo ""
echo "Enabling addons..."
minikube addons enable ingress -p "$PROFILE"
minikube addons enable metrics-server -p "$PROFILE"

# Build Docker images within minikube's Docker daemon
echo ""
echo "Building Docker images in minikube's Docker environment..."
eval $(minikube docker-env -p "$PROFILE")

echo "Building backend image..."
docker build -t mukthiguru-backend:latest -f "$PROJECT_ROOT/../backend/Dockerfile" "$PROJECT_ROOT/../"

echo "Building frontend image..."
docker build -t mukthiguru-frontend:latest -f "$PROJECT_ROOT/../Dockerfile" "$PROJECT_ROOT/../"

# Deploy via Helm
echo ""
echo "Deploying via Helm..."
helm upgrade --install "$PROFILE" \
  "$PROJECT_ROOT/helm/mukthiguru" \
  -f "$PROJECT_ROOT/helm/mukthiguru/values-minikube.yaml" \
  --create-namespace \
  --namespace "$PROFILE"

# Wait for deployment
echo ""
echo "Waiting for backend to be ready..."
kubectl wait --for=condition=ready pod \
  -l app.kubernetes.io/component=backend \
  -n "$PROFILE" \
  --timeout=300s

echo ""
echo "=== Setup complete! ==="
echo ""
echo "Frontend: http://mukthiguru.local (add to /etc/hosts)"
echo "API Docs: http://mukthiguru.local/api/docs"
echo "Jaeger:   http://mukthiguru.local/jaeger (if enabled)"
echo ""
echo "Add to /etc/hosts:"
echo "  $(minikube ip -p "$PROFILE")  mukthiguru.local"
echo ""
echo "Useful commands:"
echo "  kubectl get pods -n $PROFILE"
echo "  kubectl get svc -n $PROFILE"
echo "  kubectl logs -f deployment/backend -n $PROFILE"
