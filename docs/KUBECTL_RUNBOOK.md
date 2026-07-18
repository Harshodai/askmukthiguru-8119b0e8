# Kubectl Ops Runbook — AskMukthiGuru on K8s

**Skill applied:** `kubectl`
**Context:** your backend currently runs on Railway (single container). This
runbook is for when you migrate to (or add) the K8s deployment in `k8s/`.
It assumes namespace `askmukthiguru`, deployment `askmukthiguru-backend`.

> First-time safety: always dry-run before applying —
> `kubectl apply -f <file> --dry-run=server` validates against the live API.

---

## 1. Deploy / migrate

```bash
# validate first
kubectl apply -f k8s/backend-deployment.yaml --dry-run=server

# apply
kubectl apply -f k8s/backend-deployment.yaml

# watch the rollout (models take ~7 min to warm; readiness gates traffic)
kubectl -n askmukthiguru rollout status deployment/askmukthiguru-backend -w
kubectl -n askmukthiguru get pods -w
```

## 2. Health & debugging

```bash
# overview
kubectl -n askmukthiguru get all
kubectl -n askmukthiguru get hpa,pdb,networkpolicy

# why is a pod not ready?
kubectl -n askmukthiguru describe pod <pod>
kubectl -n askmukthiguru get events --sort-by=.lastTimestamp | tail -20

# logs (current + previous after a crash)
kubectl -n askmukthiguru logs deploy/askmukthiguru-backend --tail=200 -f
kubectl -n askmukthiguru logs <pod> --previous

# exec in (debug model load, memory)
kubectl -n askmukthiguru exec -it deploy/askmukthiguru-backend -- /bin/bash
```

## 3. The memory-warning playbook (BGE-M3 OOM)

Each replica loads ~1.8 GB (BGE-M3 1.6 GB + CrossEncoder 0.2 GB). If pods
OOMKill on load:

```bash
kubectl -n askmukthiguru get pods | grep -i oom
kubectl -n askmukthiguru describe pod <pod> | grep -A3 "Last State"
# raise memory requests/limits (keep requests == limits for Guaranteed QoS)
kubectl -n askmukthiguru set resources deployment/askmukthiguru-backend \
  --requests=memory=3Gi,cpu=1000m --limits=memory=3Gi,cpu=2000m
```

## 4. Autoscaling checks

```bash
kubectl -n askmukthiguru get hpa backend-hpa
kubectl -n askmukthiguru describe hpa backend-hpa        # current/target, events
kubectl top pods -n askmukthiguru                        # needs metrics-server
# manual override during a known spike
kubectl -n askmukthiguru scale deployment/askmukthiguru-backend --replicas=4
```

## 5. Secrets rotation (vault KEK)

Dual-key migration procedure — never replace the KEK before rewrapping.

1. **Deploy dual-read support** — ensure the app reads from both old and new
   KEK locations (env var `BRAIN_KEK` + `BRAIN_KEK_NEW`). The vault module
   attempts unwrap with `BRAIN_KEK` first, falls back to `BRAIN_KEK_NEW`.
2. **Set the new KEK** — add `BRAIN_KEK_NEW` alongside the existing key:
   ```bash
   kubectl -n askmukthiguru create secret generic brain-vault \
     --from-literal=BRAIN_KEK="${BRAIN_KEK}" \
     --from-literal=BRAIN_KEK_NEW="$(openssl rand -base64 32)" \
     --dry-run=client -o yaml | kubectl apply -f -
   ```
3. **Re-wrap every DEK** — run the re-wrap migration job that unwraps each
   user's DEK with the old key and re-wraps with the new key:
   ```bash
   kubectl -n askmukthiguru create job --from=cronjob/rewrap-deks rewrap-manual-$(date +%s)
   ```
4. **Verify** — spot-check that unwrap + re-wrap + read succeeds for a sample
   of users (Mode-A vault entries).
5. **Retire the old key** — only after verification passes, update the
   ExternalSecret to point at the new value, change `BRAIN_KEK` to match
   `BRAIN_KEK_NEW`, and remove `BRAIN_KEK_NEW` from the Secret.
6. **Rollout** — the ExternalSecret refresh or a pod restart picks up the
   single remaining key.

> Mode-B (session-unlock) users are unaffected by KEK rotation since their
> key is derived from their passphrase via Argon2id, never from BRAIN_KEK.

## 6. Rollback

```bash
kubectl -n askmukthiguru rollout history deployment/askmukthiguru-backend
kubectl -n askmukthiguru rollout undo deployment/askmukthiguru-backend
kubectl -n askmukthiguru rollout undo deployment/askmukthiguru-backend --to-revision=3
```

## 7. Railway → K8s traffic cutover (safe)

1. Deploy to K8s, wait for `ready` (models warm).
2. Point a *staging* hostname at the K8s ingress; run the eval harness against it.
3. Shift 10% of traffic (DNS weighted or ingress canary) → watch error rate + P95.
4. Ramp to 100%; keep Railway warm for one week as instant rollback.

## 8. Cost note (Railway $20 plan vs K8s)

K8s only wins on cost once you need >1 replica always-on or you're bin-packing
several services. On a $20/mo budget, Railway single-container is fine — use
this K8s pack when you outgrow it (traffic HA, or the vault/second-brain
workload needs isolation). Don't run both long-term.
