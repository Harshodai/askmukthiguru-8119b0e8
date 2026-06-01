# Kubernetes Deployment — Mukthi Guru

Complete deployment reference for Minikube (local demo) and production cloud K8s. Covers Helm chart architecture, horizontal scaling design, probes, capacity planning, and operational checklists.

## Table of Contents

1. [Quick Start (Minikube)](#quick-start-minikube)
2. [Architecture](#architecture)
3. [How Horizontal Scaling Works](#how-horizontal-scaling-works)
4. [Helm Chart Structure](#helm-chart-structure)
5. [Backend Deployment](#backend-deployment)
6. [Infrastructure Services](#infrastructure-services)
7. [HPA & Autoscaling](#hpa--autoscaling)
8. [Probes](#probes)
9. [Capacity Planning](#capacity-planning)
10. [Production Checklist](#production-checklist)
11. [Troubleshooting](#troubleshooting)

---

## Quick Start (Minikube)

```bash
# 1. Install prerequisites
brew install minikube helm

# 2. One-command deploy (8 CPU, 16GB RAM allocated to minikube)
make minikube-up

# 3. Add to /etc/hosts
echo "$(minikube ip -p mukthiguru)  mukthiguru.local" | sudo tee -a /etc/hosts

# 4. Access
open http://mukthiguru.local
```

The `make minikube-up` target:
1. Starts minikube with 8 CPUs, 16GB RAM, Docker driver
2. Enables `ingress` and `metrics-server` addons
3. Builds backend and frontend Docker images inside minikube's Docker daemon
4. Installs the Helm chart with `values-minikube.yaml` overrides
5. Waits for all pods to be ready (up to 5 minutes for backend)

---

## Architecture

```
                        ┌─────────────────────────────────────┐
                        │  Ingress                            │
                        │  Host: mukthiguru.local             │
                        │  /       → frontend (port 80)       │
                        │  /api    → backend  (port 8000)     │
                        │  /ui     → backend  (port 8000)     │
                        └─────────────┬───────────────────────┘
                                      │
              ┌───────────────────────┼───────────────────────┐
              ↓                       ↓                       ↓
┌──────────────────────┐  ┌──────────────────────┐           │
│ Frontend (Nginx)     │  │ Backend (FastAPI)    │           │
│ Vite SPA             │  │ Gunicorn+Uvicorn     │
│ replicas: 1          │  │ replicas: 2 → 20     │
│ 128Mi–256Mi          │  │ 4Gi–8Gi              │
└──────────────────────┘  └──────────┬───────────┘
                                     │
         ┌───────────────────────────┼───────────────────────┐
         ↓               ↓           ↓               ↓       ↓
┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐
│ Redis        │  │ Qdrant       │  │ Neo4j        │  │ Jaeger       │
│ StatefulSet  │  │ StatefulSet  │  │ StatefulSet  │  │ Deployment   │
│ 5Gi PVC,AOF  │  │ 20Gi PVC     │  │ 10Gi PVC     │  │ Ephemeral    │
│ Password     │  │ v1.17.1      │  │ APOC, Auth   │  │ Demo only    │
└──────────────┘  └──────────────┘  └──────────────┘  └──────────────┘
```

---

## How Horizontal Scaling Works

The backend is **stateless** when using Sarvam Cloud as the LLM provider. Three Redis-backed mechanisms replace in-memory state to make pods safely horizontally scalable:

### 1. Request Coalescing (`backend/app/coalescer.py`)

Identical concurrent queries to different pods share a single RAG pipeline execution:

```
Pod A receives: "What is the beautiful state?"
  → RedisCoalescer.acquire("coalesce:lock:hash") → becomes LEADER
  → Runs full RAG pipeline (~15 seconds)
  → Stores result: "coalesce:result:hash" in Redis (TTL 60s)
  → Responds with result

Pod B receives: "What is the beautiful state?" (same time)
  → RedisCoalescer.acquire("coalesce:lock:hash") → becomes FOLLOWER
  → Polls Redis "coalesce:result:hash" every 100ms
  → Leader finishes → result lands in Redis
  → Pod B reads result and responds (no second RAG run)
```

This saves LLM quota and reduces latency for concurrent identical requests.

### 2. Rate Limiting (`backend/app/core/limiter.py`)

Uses `slowapi` with Redis `Limiter` backend. When `REDIS_URL` is set:
- A user hitting 5 pods is subject to the same rate limit
- Per-pod in-memory counters are replaced with shared Redis counters

### 3. Ingestion Status (`backend/services/ingestion_tracker.py`)

Tracks content ingestion progress in Redis hashes:
- `ingest:status:{url_hash}` → `{url, message, progress, updated_at, status}`
- TTL: 24 hours
- Any pod can query `/api/ingest/status` and see global state

### Fallback Chain

Each component falls back gracefully:

| Component | Redis available | Redis unavailable |
|-----------|----------------|-------------------|
| Coalescer | `RedisCoalescer` (cross-pod) | `_InMemoryCoalescer` (per-process) |
| Rate Limiter | `slowapi` + Redis storage | `slowapi` + in-memory storage |
| Ingestion Tracker | `RedisIngestionTracker` | `_InMemoryIngestionTracker` |

The in-memory fallbacks work for single-pod deployments but will be inconsistent under multiple pods. Always deploy Redis for production.

---

## Helm Chart Structure

```text
k8s/helm/mukthiguru/
├── Chart.yaml                  # Helm v2, type: application
├── values.yaml                 # Production defaults
├── values-minikube.yaml        # Minikube overrides
├── values-production.yaml      # Cloud overrides (EKS/GKE/AKS)
└── templates/
    ├── _helpers.tpl            # Naming helpers (fullname, labels, selectors)
    ├── namespace.yaml          # Managed namespace
    ├── backend.yaml            # Deployment + Service + probes
    ├── frontend.yaml           # Nginx static Deployment + Service
    ├── ingress.yaml            # Per-host routing: /, /api, /ui
    ├── configmap.yaml          # Non-sensitive env vars
    ├── secrets.yaml            # Sensitive values (base64)
    ├── hpa.yaml                # Horizontal Pod Autoscaler
    ├── pdb.yaml                # Pod Disruption Budget
    ├── redis.yaml              # StatefulSet + PVC + AOF
    ├── qdrant.yaml             # StatefulSet + PVC
    ├── neo4j.yaml              # StatefulSet + PVC
    └── jaeger.yaml             # Deployment (demo only)
```

### Values Files

| File | Replicas | HPA | Resources | Images | Purpose |
|------|----------|-----|-----------|--------|---------|
| `values.yaml` | 2 | Enabled (2→20) | Full | Local tags | Defaults |
| `values-minikube.yaml` | 2 | Disabled | Reduced | `pullPolicy: Never` | Local demo |
| `values-production.yaml` | 3 | Enabled (3→20) | Full | Registry refs | Cloud |

---

## Backend Deployment

### Critical Fields

```yaml
spec:
  replicas: 2                    # Scale via HPA
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 50%              # Scale up before scaling down
      maxUnavailable: 0          # Zero-downtime deploys
  template:
    spec:
      containers:
      - name: backend
        resources:
          requests:
            memory: "4Gi"        # PyTorch + sentence-transformers
            cpu: "2"
          limits:
            memory: "8Gi"        # Hard ceiling
            cpu: "4"
```

### EnvFrom

The backend container sources configuration from:
- **ConfigMap** (`mukthiguru-config`): Qdrant URL, Neo4j URL, Redis URL, provider, env
- **Secret** (`mukthiguru-secrets`): Sarvam API key, Neo4j/Redis/JWT passwords

### Entrypoint

```bash
gunicorn -k uvicorn.workers.UvicornWorker \
  --bind 0.0.0.0:8000 \
  app.main:app
```

`WEB_CONCURRENCY` env var controls worker count. Default: 2 per pod.

---

## Infrastructure Services

| Service | Kind | Storage | CPU | Memory | Notes |
|---------|------|---------|-----|--------|-------|
| **Redis** | StatefulSet | 5Gi PVC, AOF | 1–4 | 2Gi–8Gi | Auth enabled, standalone |
| **Qdrant** | StatefulSet | 20Gi PVC | 2–4 | 4Gi–8Gi | v1.17.1 |
| **Neo4j** | StatefulSet | 10Gi PVC | 2–4 | 4Gi–8Gi | APOC plugin, auth |
| **Jaeger** | Deployment | Ephemeral | 1–2 | 2Gi–4Gi | All-in-one (demo) |

### Qdrant (`k8s/helm/mukthiguru/templates/qdrant.yaml`)

- Image: `qdrant/qdrant:v1.17.1`
- Ports: 6333 (HTTP), 6334 (gRPC)
- Persistence: 20Gi PVC mounted at `/qdrant/storage`
- Vector index survives pod restarts and node migrations

### Neo4j (`k8s/helm/mukthiguru/templates/neo4j.yaml`)

- Image: `neo4j:5.17`
- Ports: 7687 (Bolt), 7474 (HTTP)
- Persistence: 10Gi PVC mounted at `/data`
- APOC plugin for advanced graph operations
- Auth: `neo4j/{password}` from secret

### Redis (`k8s/helm/mukthiguru/templates/redis.yaml`)

- Image: `redis:7-alpine`
- Port: 6379
- Persistence: 5Gi PVC + AOF (append-only file) for durability
- Password-protected (`requirepass`)

---

## HPA & Autoscaling

```yaml
autoscaling:
  enabled: true
  minReplicas: 2
  maxReplicas: 20
  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: 60
    - type: Resource
      resource:
        name: memory
        target:
          type: Utilization
          averageUtilization: 70
  behavior:
    scaleUp:
      stabilizationWindowSeconds: 30
      policies:
        - type: Percent
          value: 100
          periodSeconds: 15
    scaleDown:
      stabilizationWindowSeconds: 300
      policies:
        - type: Percent
          value: 10
          periodSeconds: 60
```

### Scale-Up Behavior
- After 30s of sustained CPU > 60% or memory > 70%
- Adds 100% more pods every 15 seconds
- Example: 2 → 4 → 8 → 16 → 20 (peaks within ~1 minute of sustained load)

### Scale-Down Behavior
- After 5 minutes of lower utilization
- Removes 10% of pods every 60 seconds
- Prevents flapping during traffic dips

### Pod Disruption Budget

```yaml
minAvailable: 1
```

Ensures at least 1 backend pod is always running during node drains, maintenance, or rolling updates.

---

## Probes

| Probe | Endpoint | Delay (s) | Period (s) | Timeout (s) | Failures | Purpose |
|-------|----------|-----------|------------|-------------|----------|---------|
| **Startup** | `/api/health` | 10 | 10 | — | 30 | Allow 5min for model load + DB init |
| **Liveness** | `/api/health` | 60 | 30 | 10 | 3 | Restart if process hung |
| **Readiness** | `/api/ready` | 30 | 10 | 5 | 3 | Gate traffic until Qdrant + LLM ready |

### Why the startup probe is critical

The backend takes 60–120 seconds to initialize:
1. Load sentence-transformers model (`all-MiniLM-L6-v2`) from HuggingFace cache
2. Initialize Qdrant client and verify collection
3. Initialize LightRAG with Neo4j
4. Warm up Ollama/Sarvam connection

Without a startup probe, K8s would kill the pod after liveness fails during this initialization period.

### What each endpoint checks

- **`/api/health`** (liveness): Process alive, all service checks pass, returns status for Qdrant/Ollama/OCR/Guardrails/Semantic Cache
- **`/api/ready`** (readiness): Returns 200 only if Qdrant AND LLM are both healthy. Returns 503 otherwise.

---

## Ingress Routing

```
mukthiguru.local
  ├─ /           → frontend (port 80)    ← Vite SPA, Nginx
  ├─ /api        → backend (port 8000)   ← FastAPI (chat, health, ingest)
  └─ /ui         → backend (port 8000)   ← Gradio chat UI proxy
```

In Minikube, `nginx-ingress` addon handles this. In production, use cloud-native ingress controllers.

---

## Capacity Planning

### Per-Pod Capacity

| Metric | Value |
|--------|-------|
| Request latency (P50) | 5–8s |
| Request latency (P95) | 12–15s |
| Concurrent requests per pod | 3–5 |
| Memory per pod | 4–6 GiB |
| CPU per pod | 1.5–3 cores |

### Scaling Projection

| Pods | Concurrent Users | Active Users (10% concurrency) | DAU (5% active) |
|------|-----------------|-------------------------------|-----------------|
| 2 | 6–10 | 60–100 | 1,200–2,000 |
| 5 | 15–25 | 150–250 | 3,000–5,000 |
| 10 | 30–50 | 300–500 | 6,000–10,000 |
| 20 | 60–100 | 600–1,000 | 12,000–20,000 |

### Bottlenecks

| Rank | Bottleneck | Current | Scaled |
|------|-----------|---------|--------|
| 1 | Sarvam Cloud API quota | Free tier (~50 RPM) | Unbounded (paid plan) |
| 2 | Backend CPU/Memory | 1 pod × 4 CPU | 20 pods × 4 CPU |
| 3 | Qdrant vector queries | Single instance | Add replicas |
| 4 | Neo4j graph queries | Single instance | Neo4j Enterprise cluster |
| 5 | Redis throughput | Single instance | Redis Cluster |

### Recommendations

1. **Semantic Cache first**: 60–70% of queries can be cached (already implemented via `SemanticCacheAdapter`)
2. **Request coalescing**: Identical concurrent queries share one LLM call (already implemented via `RedisCoalescer`)
3. **Separate ingestion pods**: CPU-heavy YouTube processing should run on a dedicated `IngestionWorker` deployment to avoid competing with chat serving
4. **Circuit breaker**: If Sarvam returns 429, fallback gracefully to `handle_fallback` (already implemented in the RAG graph)

---

## Production Checklist

### Before Going Live

- [ ] Update `backend.image.repository` and `frontend.image.repository` to your container registry
- [ ] Set `ingress.className` based on cloud provider: `alb` (AWS), `gce` (GKE), `nginx` (bare metal)
- [ ] Set `ingress.annotations` for cloud-specific ALB/load balancer configuration
- [ ] Configure TLS via `cert-manager` + Let's Encrypt cluster issuer
- [ ] Replace base64 `secrets.*` with External Secrets Operator → cloud secret manager
- [ ] Disable `jaeger.enabled`, use cloud-native APM:
  - AWS X-Ray
  - GCP Cloud Trace
  - DataDog APM
- [ ] Configure node auto-scaling to match HPA (at least `t3.large` on EKS)
- [ ] Enable managed services for stateful workloads:
  - Redis → AWS ElastiCache / GCP Memorystore
  - Qdrant → Qdrant Cloud / managed deployment
  - Neo4j → Neo4j AuraDB
- [ ] Set up PVC backups (Velero or cloud-native snapshots)
- [ ] Configure production WAF/DDoS protection on the ingress
- [ ] Set up Grafana dashboards for HPA metrics, pod health, and error rates

### Post-Deployment Smoke Tests

```bash
# 1. All pods running
kubectl get pods -n mukthiguru

# 2. Backend health
curl https://mukthiguru.example.com/api/health

# 3. Backend ready
curl https://mukthiguru.example.com/api/ready

# 4. Chat API
curl -X POST https://mukthiguru.example.com/api/chat \
  -H "Content-Type: application/json" \
  -d '{"messages":[],"user_message":"What is the beautiful state?"}'

# 5. HPA operational
kubectl get hpa -n mukthiguru
```

### Load Testing

```bash
k6 run --vus 10 --duration 60s - <<'EOF'
import http from 'k6/http';
import { check } from 'k6';

export default function () {
  const res = http.post('https://mukthiguru.example.com/api/chat', JSON.stringify({
    messages: [],
    user_message: 'What is the beautiful state?'
  }), { headers: { 'Content-Type': 'application/json' } });
  check(res, { 'status 200': (r) => r.status === 200 });
}
EOF
```

---

## Troubleshooting

### Backend stuck in CrashLoopBackOff
```bash
kubectl logs -n mukthiguru -l app.kubernetes.io/component=backend --tail=100
kubectl describe pod -n mukthiguru -l app.kubernetes.io/component=backend
```
- Check OOM: `kubectl top pod -n mukthiguru`
- Check Qdrant/Neo4j connectivity
- Increase `startupProbe.failureThreshold` if startup takes > 5min

### HPA shows `<unknown>` for metrics
```bash
kubectl get --raw /apis/metrics.k8s.io/v1beta1/nodes
```
- `metrics-server` addon not enabled
- Run: `minikube addons enable metrics-server -p mukthiguru`

### Ingress returns 503
```bash
kubectl get ingress -n mukthiguru
kubectl describe ingress mukthiguru-ingress -n mukthiguru
kubectl get svc -n mukthiguru
```
- Ensure backend Service exists and has ready endpoints
- Check readiness probe is passing

### Redis connection refused
```bash
kubectl logs -n mukthiguru -l app.kubernetes.io/component=redis
kubectl exec -n mukthiguru mukthiguru-redis-0 -- redis-cli -a <password> PING
```
- PVC may be unavailable (check storage class)
- Redis password mismatch between secret and StatefulSet

### Coalescer not merging requests
- Check `COALESCER_REDIS_URL` is set and reachable
- Verify `redis` package is installed in the backend image
- Check logs for "Using Redis coalescer" vs "falling back to in-memory"

---

## Makefile Targets

| Target | Description |
|--------|------------|
| `make minikube-up` | Start cluster, build images, helm install, wait for ready |
| `make minikube-down` | Delete cluster and all resources |
| `make minikube-rebuild` | Rebuild Docker images + restart deployments |
| `make minikube-test` | Health + readiness check via minikube IP |
| `make minikube-logs` | Stream backend logs |

---

## File Inventory

```text
k8s/
├── helm/mukthiguru/              # Helm chart (12 templates, 3 values files)
├── nginx/nginx.conf              # Nginx SPA routing config
├── skaffold.yaml                 # Dev hot-reload (Skaffold)
├── minikube/start.sh             # One-command setup (chmod +x)
└── README.md                     # Quick reference guide

Dockerfile                        # Frontend multi-stage build (Vite -> Nginx)
backend/Dockerfile                # Backend multi-stage build (Python deps -> app)
backend/docker-entrypoint.sh      # Worker count + privilege drop

Makefile                          # Convenience targets (minikube-up, etc.)

backend/app/coalescer.py          # RedisCoalescer + _InMemoryCoalescer
backend/app/core/limiter.py       # slowapi + Redis-backed rate limiter
backend/services/ingestion_tracker.py  # RedisIngestionTracker + _InMemoryIngestionTracker
backend/app/config.py             # Pydantic Settings (includes redis_url)
backend/app/dependencies.py       # ServiceContainer (composition root)
backend/app/main.py               # FastAPI app, health/ready endpoints

docs/kubernetes-deployment.md     # This document
.claude/skills/k8s-deploy.md      # Claude Code skill for future sessions
```

---

**Last updated**: 2026-05-27
**Chart version**: 0.1.0
**App version**: 1.0.0