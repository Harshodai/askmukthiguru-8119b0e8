# Kubernetes Deployment Guide

Complete Helm chart and Kubernetes manifests for deploying Mukthi Guru on Minikube (local demo) and production cloud clusters.

## Quick Start (Minikube)

```bash
# 1. Install prerequisites
brew install minikube helm

# 2. One-command deploy
make minikube-up

# 3. Add to /etc/hosts (run as sudo)
echo "$(minikube ip -p mukthiguru)  mukthiguru.local" | sudo tee -a /etc/hosts

# 4. Access the app
open http://mukthiguru.local
```

## Helm Chart Structure

```text
k8s/helm/mukthiguru/
├── Chart.yaml              # Helm metadata
├── values.yaml             # Production default values
├── values-minikube.yaml    # Minikube overrides (smaller resources, no HPA)
├── values-production.yaml  # Cloud K8s overrides (EKS/GKE/AKS)
└── templates/
    ├── _helpers.tpl        # Naming helpers
    ├── namespace.yaml      # Helm-managed namespace
    ├── backend.yaml        # FastAPI Deployment + Service + HTTP probes
    ├── frontend.yaml       # Nginx static Deployment + Service
    ├── ingress.yaml        # K8s Ingress (per-host routing)
    ├── configmap.yaml      # Non-sensitive env vars
    ├── secrets.yaml        # Sensitive values
    ├── hpa.yaml            # Horizontal Pod Autoscaler (2–20 replicas)
    ├── pdb.yaml            # Pod Disruption Budget
    ├── redis.yaml          # StatefulSet with PVC + AOF
    ├── qdrant.yaml         # StatefulSet with PVC for vector index
    ├── neo4j.yaml          # StatefulSet with PVC for graph data
    └── jaeger.yaml         # Deployment for distributed tracing (demo only)
```

### Backend Deployment (Critical Fields)

- **Replicas**: 2 (scales up to 20 via HPA)
- **Update strategy**: RollingUpdate (maxSurge: 50%, maxUnavailable: 0)
- **Resources**: 4Gi/2 CPU requests, 8Gi/4 CPU limits
- **StartupProbe**: Every 10s, up to 30 failures (5 min max startup)
- **LivenessProbe**: /api/health every 30s
- **ReadinessProbe**: /api/ready every 10s, gates traffic
- **EnvFrom**: mukthiguru-config + mukthiguru-secrets

### Infrastructure Services

| Service | Type | Storage | Resources | Notes |
|---------|------|---------|-----------|-------|
| Redis | StatefulSet | 5Gi PVC, AOF | 2Gi/8Gi, 1/4 CPU | Auth enabled, standalone |
| Qdrant | StatefulSet | 20Gi PVC | 4Gi/8Gi, 2/4 CPU | Vector DB persistence |
| Neo4j | StatefulSet | 10Gi PVC | 4Gi/8Gi, 2/4 CPU | APOC plugin enabled |
| Jaeger | Deployment | Ephemeral | 2Gi/4Gi, 1/2 CPU | All-in-one (demo only) |

## HPA Configuration

```yaml
minReplicas: 2
maxReplicas: 20
metrics:
  - cpu: 60% utilization
  - memory: 70% utilization
behavior:
  scaleUp:   30s stabilization, 100% per 15s
  scaleDown: 300s stabilization, 10% per 60s
```

## Minikube Commands

| Target | What it does |
|--------|-------------|
| make minikube-up | Start minikube, build images, helm install, wait for ready |
| make minikube-down | Tear everything down |
| make minikube-rebuild | Rebuild Docker images + restart deployments |
| make minikube-test | Health/readiness check via minikube IP |
| make minikube-logs | Stream backend logs |

## Production Checklist

- [ ] Update image registry in values-production.yaml
- [ ] Set ingress className (alb/gce/nginx)
- [ ] Configure TLS via cert-manager
- [ ] Replace secrets with External Secrets Operator
- [ ] Disable Jaeger, enable cloud APM
- [ ] Use managed services for Redis/Qdrant/Neo4j where possible
