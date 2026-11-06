# K8S_MANIFESTS_REVIEW

| Field | Value |
|---|---|
| Status | Draft review. Static read only. No cluster, no `kubectl`, no `helm` run. |
| Date | 2026-11-06 |
| Head | `fb5cab0f` (branch `feature/audit-strengthen-rag-qdrant`) |
| Scope | Every tracked file matching `k8s|kubernetes|helm|kustomiz`, the Makefile, CI, scripts and docs that reference them, and the compose files |
| Evidence labels | `[V-STATIC]` read at this head. `[V-GIT]` from `git log`. `[INF]` inference. `[LIVE-R]` needs a deployed stack. See `../CONVENTIONS.md` section 3 |
| Out of scope | Cluster behaviour. Helm template rendering (Helm is not run; see section 7) |

Decision label: PROPOSED D-PK8S1 (section 5). It is a proposal. It needs the owner.

---

## 1. Inventory

Last-commit dates from `git log -1 --format=%cs -- <path>` `[V-GIT]`. All Kubernetes paths were last touched between 2026-06-01 and 2026-10-10. None changed after the Railway migration notes of 2026-09 except the files dated 2026-10-10 (a bulk commit; see Unknown U1).

| Path | Kind | Purpose | Last commit |
|---|---|---|---|
| `infrastructure/k8s/README.md` | doc | Helm and Minikube guide | 2026-10-10 |
| `infrastructure/k8s/helm/mukthiguru/Chart.yaml`, `Chart.lock` | Helm chart | Chart `mukthiguru` 0.1.0; declares `redis 19.x.x` from Bitnami (`Chart.yaml:11-13`) | 2026-10-10 |
| `infrastructure/k8s/helm/mukthiguru/charts/redis-19.6.4.tgz` | binary | Vendored Bitnami Redis subchart | 2026-10-10 |
| `.../templates/_helpers.tpl`, `namespace.yaml` | template | Names, namespace | 2026-10-10 |
| `.../templates/backend.yaml` | Service + Deployment | FastAPI API pod | 2026-10-10 |
| `.../templates/frontend.yaml` | Service + Deployment | Nginx static pod | 2026-10-10 |
| `.../templates/configmap.yaml`, `secrets.yaml`, `externalsecret.yaml` | ConfigMap, Secret, ExternalSecret | Env, secrets, vault KEK | 2026-10-10 |
| `.../templates/qdrant.yaml`, `redis.yaml`, `neo4j.yaml`, `jaeger.yaml` | StatefulSet / Deployment | In-cluster data stores and tracing | 2026-10-10 |
| `.../templates/hpa.yaml`, `pdb.yaml`, `ingress.yaml`, `networkpolicy.yaml` | HPA, PDB, Ingress, NetworkPolicy | Scale, disruption, routing, egress | 2026-10-10 |
| `.../values.yaml`, `values-minikube.yaml`, `values-production.yaml` | values | Defaults and overrides | 2026-10-10 |
| `infrastructure/k8s/backend-deployment.yaml` | Deployment, ConfigMap, Service, HPA (4 docs) | Stand-alone hardened backend | 2026-10-10 |
| `infrastructure/k8s/minikube/start.sh` | script | Minikube bootstrap and `helm upgrade --install` (`start.sh:56`) | 2026-10-10 |
| `infrastructure/k8s/skaffold.yaml`, `nginx/nginx.conf` | Skaffold, nginx | Dev loop, edge config | 2026-10-10 |
| `infrastructure/k8s_deployment.yaml` | 25 YAML docs | "Production" manifest set with Celery workers, Postgres, Neo4j | 2026-09-17 |
| `infrastructure/k8s_deploy.sh` | script | `envsubst < k8s_deployment.yaml \| kubectl apply -f -` (`k8s_deploy.sh:24`) | 2026-06-27 |
| `backend/infrastructure/k8s.yaml` | 13 YAML docs | Second manifest set, namespace `mukthi-guru`, GPU backend | 2026-09-17 |
| `docs/kubernetes-deployment.md` | doc | 518-line K8s reference | 2026-06-01 |

Also present, not tracked (not reviewed): `.claude/worktrees/agent-a95e2c3d4ac0da7bb/infrastructure/k8s/*` (agent worktree copy). `docs/KUBECTL_RUNBOOK.md` is tracked and matched by the grep, not by the name filter.

Result: three independent manifest sets exist (Helm chart, `k8s_deployment.yaml`, `backend/infrastructure/k8s.yaml`) plus a fourth stand-alone file (`backend-deployment.yaml`). They use four different namespaces or names: `mukthiguru` (`k8s_deployment.yaml`, Helm), `mukthi-guru` (`backend/infrastructure/k8s.yaml:5`), `askmukthiguru` (`docs/KUBECTL_RUNBOOK.md`, `backend-deployment.yaml` secret name `askmukthiguru-secrets:125`). `[V-STATIC]`

Parse check: `yaml.safe_load_all` parses `infrastructure/k8s_deployment.yaml` (25 docs), `backend/infrastructure/k8s.yaml` (13 docs) and `infrastructure/k8s/backend-deployment.yaml` (4 docs) without error. Helm templates were not parsed (Go templates). Parsing proves syntax only. `[V-STATIC]`

---

## 2. Usage: who references the manifests

| Referrer | Reference | Kind of use |
|---|---|---|
| `.github/workflows/*` (23 files) | No match for `kubectl`, `helm`, `k8s`, `kubeconfig` | None. No CI job applies, lints or renders any manifest. `[V-STATIC]` |
| `Makefile:239-267` | `minikube-up`, `minikube-down`, `minikube-rebuild`, `minikube-test`, `minikube-logs` | Developer-run local demo only (local Minikube profile `mukthiguru`). |
| `infrastructure/k8s_deploy.sh:24` | `kubectl apply` of `k8s_deployment.yaml` | Manual script. Nothing calls it (grep over `.github`, `Makefile`, `scripts/` found no caller). |
| `backend/tests/test_prod_compose_invariants.py:38,91-96` | Reads Helm `values.yaml` `qdrant.image.tag` and compares it to compose | The only automated check. It guards one value (Qdrant tag). Both are `v1.18.0` today (`values.yaml:~178`, `docker-compose.prod.yml:141`). |
| `docs/wiki/operations/deployment-and-ci.md:145` | `kubectl rollout undo deployment/askmukthiguru-backend` as a rollback option | Doc. The deployment name does not exist in any manifest (Helm names it `<release>-backend`; `k8s_deployment.yaml` uses its own names). |
| `docs/KUBECTL_RUNBOOK.md:1-6` | States "your backend currently runs on Railway"; the runbook is "for when you migrate to (or add) the K8s deployment in `k8s/`" | Doc. Says Railway is live. Path `k8s/` does not exist (real path is `infrastructure/k8s/`). |
| `README.md:210`, `.dockerignore:52` | Lists `k8s/`; ignores `k8s/` in Docker context | Doc / build hygiene. |
| `infrastructure/k8s/README.md`, `docs/kubernetes-deployment.md` | Describe Helm and Minikube as "production cloud clusters" | Doc. Carries no "not deployed" warning. |
| `CLAUDE.md` | "Railway is scaled down and stays stopped until Harsha says otherwise"; k8s -> `infrastructure/k8s/` | Layout rule. No statement that k8s is live. |
| `specifications/ARCHITECTURE_DECISION_RECORDS_HISTORICAL.md:182,253` | Railway chosen; R-11 "Kubernetes manifests, Helm charts, 10k and 100k SPOF tiers as build targets: No deploy, no baseline" | Audit package: k8s is a target, not a deployment. |
| `.railway/railway.ts:17-18` | `healthcheck: "/api/healthz"`, `healthcheckTimeout: 330` | Railway IaC; the declared deployment source. |

**Answer to question 1.** No CI workflow, no Makefile target other than the Minikube demo, and no script other than the manual `k8s_deploy.sh` applies these manifests. The only automated link is one value comparison in a test. The paths are not a live deployment path. They are dead for production and live only as a manual local Minikube demo. `[V-STATIC]` Whether anyone applied them to a real cluster is unknown (U2).

---

## 3. Findings

Severity follows `CONVENTIONS.md` section 4. The prefix `K8S-` is local to this file. The Lead should register it (U5).

### K8S-01 (P2) Four manifest sets, no source-of-truth header

Evidence: section 1 inventory. No manifest file carries a "not deployed" or "reference only" header (`head` of `k8s_deployment.yaml`, `backend/infrastructure/k8s.yaml`, `Chart.yaml`). `infrastructure/k8s/README.md:3` calls the chart "for deploying Mukthi Guru on Minikube (local demo) and production cloud clusters." `k8s_deployment.yaml:1` is titled "Kubernetes Production Deployment."
Impact: a coding agent or new engineer can read the files as the production definition. See section 5, question 4.
Fix: add a header to each file and a CI drift guard (NEW-K8S-1, NEW-K8S-2).

### K8S-02 (P2) Graph store: manifests use Neo4j, config and compose default to Memgraph

Evidence:
- Config default graph backend is `MemgraphStorage` (`backend/app/config.py:847`), with Memgraph aliases (`config.py:829-833`).
- `docker-compose.prod.yml:87-88` requires `NEO4J_URI` such as `bolt://memgraph:7687` and sets `NEO4J_USER` default `memgraph`.
- Helm ships `neo4j.yaml` with image `neo4j:5.17` (`values.yaml` neo4j block) and plugins `apoc, n10s, graph-data-science` (`templates/neo4j.yaml`). `k8s_deployment.yaml:558` uses `neo4j:5-community`. `backend/infrastructure/k8s.yaml:212` uses `neo4j:5-community`.
- No manifest contains a Memgraph workload (`grep -i memgraph` over the K8s paths: no match).
Impact: a cluster built from these files would run a different graph engine than the one the code and CLAUDE.md name as the live store. Graph data and Cypher compatibility are untested on that path. `[INF]`
Fix: decide D-PK8S1 first. If kept, replace with Memgraph or label the Neo4j choice as legacy.

### K8S-03 (P2) Health probes use `/api/health` (comprehensive), not `/api/healthz`

Evidence: Helm `values.yaml:38` (startup) and `:45` (liveness) use `/api/health`; readiness uses `/api/ready` (`:53`). `backend-deployment.yaml:130,140,149` use `/api/health` for all three. `k8s_deployment.yaml` uses `/api/health` (lines ~89, ~95). `backend/infrastructure/k8s.yaml:52,58` use `/health`. The code exposes `/api/healthz` (`backend/app/api/health.py:163`) as the cheap liveness endpoint and `/api/health` (`:194`) as the per-dependency check. `docker-compose.prod.yml:121` and `.railway/railway.ts:17` use `/api/healthz`. A test pins the compose side (`test_backend_healthcheck_uses_cheap_liveness_endpoint`, `test_prod_compose_invariants.py:~74`) and its message says `/api/health` "restart-loops on any non-critical dependency degradation."
Impact: a liveness probe on `/api/health` can restart pods when Qdrant, Redis or the graph store degrades. `/health` in `backend/infrastructure/k8s.yaml` may not exist. I did not search for a `/health` route; treat as likely 404 (U3).
Fix: liveness and startup -> `/api/healthz`; readiness stays `/api/ready`. Add `/api/ready` route existence to the drift test.

### K8S-04 (P2) Env var names and values drift from `backend/app/config.py`

Evidence `[V-STATIC]`:
- `templates/configmap.yaml:17` sets `NEO4J_BOLT_URL`. Config reads `neo4j_uri` (`config.py:826`), env `NEO4J_URI`. `NEO4J_BOLT_URL` is not a Settings field in the lines I read (grep of `config.py` for `neo4j_bolt`: no match). The variable is probably ignored, so the backend would use its default `bolt://localhost:7687`. `[INF]`
- `configmap.yaml:15` sets `OLLAMA_URL`. Config field is `ollama_base_url` (`config.py:585`). `OLLAMA_URL` is ignored. `[INF]`
- `configmap.yaml:20-21` sets `JAEGER_AGENT_HOST/PORT` (port 16686 is the Jaeger UI port, not the agent port). I did not find these names in `config.py` (grep `jaeger`: no match). `[INF]` ignored.
- `values.yaml:134-135` sets `LLM_PROVIDER=sarvam_cloud`. Config default and the live default are `openrouter` (`config.py:71`; CLAUDE.md: "`LLM_PROVIDER=openrouter` is the live default").
- Secrets template carries four keys only: `SARVAM_API_KEY, NEO4J_PASSWORD, REDIS_PASSWORD, JWT_SECRET` (`templates/secrets.yaml`). Missing: `OPENROUTER_API_KEY`, `SUPABASE_URL`, `SUPABASE_KEY` (`config.py:793-794`; the default `SUPABASE_URL` is `host.docker.internal`, `:793`), `BRAIN_KEK` is wired only through the optional ExternalSecret. `k8s_deployment.yaml:42-46` does carry Supabase and OpenRouter keys.
- `configmap.yaml:19` puts the Redis password inside `REDIS_URL` in a ConfigMap (see K8S-06).
Impact: a Helm install would start with the wrong graph URI, the wrong LLM provider and no Supabase or OpenRouter credentials. Chat and auth would fail or fall back. `[INF]`
Fix: generate a manifest env list from `Settings`, or drop the chart (D-PK8S1 option C).

### K8S-05 (P2) No Celery worker or beat in the Helm chart; no Memgraph; images unpinned

Evidence:
- Compose runs `celery-worker` (queues `transcription,embedding,indexing,ingestion,okf,memory,celery`, `docker-compose.prod.yml:243-252`) and `celery-beat` (`:272-275`). The Helm templates list has no worker or beat (section 1; `ls templates`). `k8s_deployment.yaml` has three Celery worker Deployments (`:139`, `:212`, `:276`) for queues `transcription`, `embedding`, `indexing` only, no beat and no `ingestion`, `okf`, `memory` queues. `backend/infrastructure/k8s.yaml:244` has one worker without `-Q`.
- Images: `tag: latest` for backend and frontend (`values.yaml:21,65`; `values-production.yaml` too). `k8s_deployment.yaml:72,160,233,297` use `mukthiguru/...:latest` with image names that do not match compose (`ghcr.io/${GHCR_ORG}/askmukthiguru-backend`, `docker-compose.prod.yml:62`). `backend/infrastructure/k8s.yaml:23` uses `mukthi-guru/backend:latest`. Only `backend-deployment.yaml:80` has a digest placeholder, and it is literally `@sha256:REPLACE_WITH_REAL_DIGEST`, so it cannot pull. `jaeger` and `neo4j`, `redis:7-alpine` use floating minor or major tags.
- Frontend: CLAUDE.md-adjacent comment in `.github/workflows/build-deploy.yml:138` says the frontend is hosted on Lovable. The chart ships a frontend Deployment anyway.
Impact: retention, stale-job sweep and background indexing would not run on a chart-only install. `latest` tags make rollback impossible by tag.
Fix: see NEW-K8S-3.

### K8S-06 (P1) Default credentials and password-bearing values committed

Evidence (file and line only; values not repeated here):
- `infrastructure/k8s/helm/mukthiguru/values.yaml:153` Redis password set to a literal default.
- `infrastructure/k8s/helm/mukthiguru/values.yaml:189` Neo4j password set to a literal default.
- `templates/configmap.yaml:19` embeds the Redis password in `REDIS_URL` in a ConfigMap (ConfigMaps are not secret objects).
- `templates/neo4j.yaml` (env `NEO4J_AUTH`) renders the Neo4j password as a plain container env value in the StatefulSet.
- `templates/secrets.yaml` falls back to the Redis default for `REDIS_PASSWORD` when `secrets.REDIS_PASSWORD` is empty.
No live API key was found in the K8s files. `k8s_deployment.yaml:40-46` uses `${VAR}` placeholders (resolved by `envsubst`, `k8s_deploy.sh:24`). `backend/infrastructure/k8s.yaml` uses `secretKeyRef` (`:38-42`, `:171-175`, `:219-223`). The two literal defaults look like documented demo values; I did not test whether any live system uses them (U4).
Severity: P1 because a default password works as a real credential if the chart is installed with defaults and a Service is reachable. It is P2 if the chart is formally retired. Not P0: no real key found; manifests are not deployed (section 2).
Fix: remove defaults, require values (`required` in Helm), or retire.

### K8S-07 (P2) Hardening is incomplete in the Helm chart and in two other sets

Evidence `[V-STATIC]`:
- `grep securityContext|runAsNonRoot|readOnlyRootFilesystem` over `helm/mukthiguru/templates`: no match. Pods run with the image default user, root filesystem writable, no capability drop.
- `backend-deployment.yaml:41-43,68-70,87-90` set `runAsNonRoot: true`, `runAsUser: 1000`. `readOnlyRootFilesystem: false` with the comment "app writes logs/tmp; tighten after audit" (`:90`). This is the best-hardened file and it is the only one.
- `k8s_deployment.yaml` and `backend/infrastructure/k8s.yaml`: no `securityContext` match.
- NetworkPolicy exists only in the Helm chart and is disabled by default (`values.yaml:215-216` `enabled: false`). When enabled it allows ingress only from namespace `ingress-nginx` and egress to Qdrant, Neo4j, Redis and DNS (`templates/networkpolicy.yaml`). It has no rule for Jaeger, Memgraph or LLM providers. The comment "no LLM providers; inference runs local" (in the egress block) contradicts the live OpenRouter use. With the policy on, calls to OpenRouter would be blocked. The template also fails render if `supabaseEgressCIDRs` is empty and the egress proxy is off (`fail` call).
- Exposure: `backend/infrastructure/k8s.yaml:382` sets a Service `type: LoadBalancer`. Helm services are `ClusterIP` with an Ingress on `/`, `/api`, `/ui` (`values.yaml:~87`). The `/ui` path routes to the backend (ingest portal, see CLAUDE.md "Ingest portal :8000/ingest/"). I did not verify that `/ui` exists as a backend route (U3).
- Data stores: Neo4j, Qdrant and Redis StatefulSets have no auth beyond the defaults in K8S-06; Qdrant has no API key setting in the template (grep `api-key`: none).
Impact: the chart is not a safe baseline to deploy.
Fix: NEW-K8S-3 if kept.

### K8S-08 (P3) Stale docs that describe K8s as an operating path

Evidence: `docs/wiki/operations/deployment-and-ci.md:145` (rollback command for a deployment that no manifest defines), `docs/KUBECTL_RUNBOOK.md` (namespace `askmukthiguru`, path `k8s/`), `docs/kubernetes-deployment.md` (last change 2026-06-01, before the Railway migration noted in CLAUDE.md for 2026-09-12), `infrastructure/k8s/README.md:50-53` ("StartupProbe ... LivenessProbe: /api/health"). Rollback command would fail with "not found". `[INF]`
Fix: NEW-K8S-4.

### K8S-09 (P3) Resource requests are not sized to any measured Railway or compose limit

Evidence: backend request 6Gi / limit 8Gi (`values.yaml`, comment cites a 2026-09-06 measurement, `~4.3GiB` idle RSS; `[DOC-CLAIM]`, not re-run). `backend-deployment.yaml` uses 6Gi limit and `PYTHON_MEMORY_LIMIT_MB=3500` (`:113`) with replicas 1 (`:25`). Helm default replicas 2, HPA 2-20 (`values.yaml:~92`), memory-percent HPA at 70%. Compose caps the backend container at 6 GiB (CLAUDE.md invariant 18). Per-pod 6Gi request x 2 replicas + Qdrant 4Gi + Neo4j 4Gi + Redis 2Gi + Jaeger 2Gi = 24Gi requested on a default install (arithmetic from `values.yaml`). The Railway runbook sets no such totals. `[INF]` No capacity test exists for this layout.
Fix: none until D-PK8S1 decides the path.

---

## 4. Comparison: manifests vs compose vs Railway runbook

"Railway" column reads `.railway/railway.ts` and the runbook name `specifications/RAILWAY_DEPLOYMENT_AND_PRODUCTION_OPERATIONS_RUNBOOK.md`. I did not re-read every runbook section; entries without a cite are marked "not checked".

| Topic | Helm chart | `k8s_deployment.yaml` | Compose (`docker-compose.prod.yml`) | Railway |
|---|---|---|---|---|
| Backend image | `mukthiguru-backend:latest` (`values.yaml:21`) | `mukthiguru/backend:latest` (`:160`) | `ghcr.io/${GHCR_ORG}/askmukthiguru-backend:${IMAGE_TAG}` (`:62`) | Dockerfile build (`railway.ts:19`) |
| Liveness | `/api/health` | `/api/health` | `/api/healthz` (`:121`) | `/api/healthz` (`railway.ts:17`) |
| Readiness | `/api/ready` | not separate | not present in compose healthcheck | not checked |
| Startup budget | 10 s x 30 = 300 s | not checked | not checked | 330 s (`railway.ts:18`) |
| Graph store | Neo4j 5.17 | Neo4j 5-community | Memgraph (`NEO4J_URI` example `bolt://memgraph:7687`, `:87`) | not checked |
| Qdrant | `v1.18.0` | `v1.18.0` (`:362`) | `v1.18.0` (`:141`) | not checked |
| Redis | `redis:7-alpine`, auth on | `redis:7-alpine` | `redis:7-alpine`, `noeviction` (test pins) | not checked |
| Redis eviction policy | not set in template (not checked line by line) | not checked | `--maxmemory-policy noeviction` | not checked |
| Celery worker | none | 3 Deployments, 3 queues | 1 worker, 7 queues (`:246-252`) | not checked |
| Celery beat | none | none | present (`:272`) | not checked |
| Replicas | 2 (HPA 2-20) | backend 3 | 1 per service | not checked |
| LLM provider | `sarvam_cloud` | `SARVAM_API_KEY`, `OPENROUTER_API_KEY` | `openrouter` default via config | not checked |
| Secrets | Secret from values, 4 keys | `envsubst` stringData | `.env` / compose env | Railway variables |
| securityContext | none | none | not checked | n/a |
| NetworkPolicy | off by default | none | compose network | n/a |
| Frontend | Nginx pod | present | `ghcr.io/.../askmukthiguru-frontend` (`:34`) | CI comment says Lovable-hosted (`build-deploy.yml:138`) |

Agreement: Qdrant tag only (test-enforced).

---

## 5. Recommendation and decision

### Answers to questions 2 to 4

- Q2 (match): No. Findings K8S-02 to K8S-05.
- Q3 (security): No committed live provider key found. Two default passwords, no securityContext in the chart, NetworkPolicy off. K8S-06, K8S-07.
- Q4 (drift risk): High. Four sets, three namespaces, "production" wording in `k8s_deployment.yaml:1` and `infrastructure/k8s/README.md:3`, a manual script that applies one set, and a doc that gives a `kubectl rollout undo`. A coding agent searching for "deployment" or "health probe" would find these before the Railway IaC. CLAUDE.md says Railway is the target, but it is the slimmed rules file; the manifests themselves give no warning. `[INF]`

### PROPOSED D-PK8S1: status of Kubernetes manifests

| Option | Action | Pros | Cons |
|---|---|---|---|
| A. Keep as reference (proposed) | Keep under `infrastructure/k8s/`. Add a header "REFERENCE ONLY, NOT DEPLOYED, Railway is the target." Add a drift test. Consolidate the two loose files (`k8s_deployment.yaml`, `backend/infrastructure/k8s.yaml`) into `infrastructure/k8s/legacy/` or delete them. | Keeps the HA and SPOF tier plan (CLAUDE.md "SPOF & Replication Policy" and R-11). Keeps the Minikube demo. Low effort. Reversible. | Reference files can still rot. Needs a test to bind them. |
| B. Fix | Bring the chart to parity with compose (Memgraph, worker, beat, probes, env names, pinned images, securityContext). | Gives a portable path off Railway. | Large effort with no deployment target now; no cluster to test on; adds maintenance. Not justified while Railway is the target. |
| C. Retire | Delete the manifests, `k8s_deploy.sh`, the Makefile Minikube targets and the docs. | Removes drift and the committed default passwords. | Loses the planned 10k/100k tier design; R-11 would need rewording; breaks `test_qdrant_version_matches_across_manifests` (must be edited). Owner decision needed. |

Proposal: option A now, with D-PK8S1 recorded for owner approval. Re-evaluate B or C if a cluster migration is not planned within a time the owner sets. `[HUMAN]`

Respect CLAUDE.md: k8s manifests stay under `infrastructure/k8s/`. The two loose files at `infrastructure/k8s_deployment.yaml` and `backend/infrastructure/k8s.yaml` do not follow that rule today (`[V-STATIC]`). Moving them is part of NEW-K8S-1.

---

## 6. Tasks

None of these tasks was started. This review changed no manifest.

| ID | Task | Files | Non-goals | Rollback |
|---|---|---|---|---|
| NEW-K8S-1 | Add a header comment to each manifest and `values*.yaml`: "REFERENCE ONLY. Not deployed. Source of truth: `.railway/railway.ts` and `docker-compose.prod.yml`. Last verified: <date>." Move `k8s_deployment.yaml`, `k8s_deploy.sh` and `backend/infrastructure/k8s.yaml` under `infrastructure/k8s/legacy/` (or delete after owner approval). Update `Makefile` and docs paths. | `infrastructure/k8s/**`, `infrastructure/k8s_deployment.yaml`, `infrastructure/k8s_deploy.sh`, `backend/infrastructure/k8s.yaml` | Do not change any image, port or value. Do not touch Railway config. | `git revert` the move commit. |
| NEW-K8S-2 | Add `backend/tests/test_k8s_reference_drift.py`: (a) each K8s file has the header; (b) probe paths used for liveness equal `/api/healthz`; (c) every env name in `configmap.yaml` and `secrets.yaml` is a `Settings` field alias; (d) image tags are not `latest`; (e) Qdrant tag equals compose (extend existing test); (f) no `password:` literal in `values.yaml`. Use `yaml` parse for plain files and text match for Helm templates. Do not install Helm. | new test file; `backend/tests/test_prod_compose_invariants.py` | No Helm rendering in CI. No cluster. | Delete the test file. |
| NEW-K8S-3 (only if option B) | Parity fix: probes `/api/healthz`, env names, Memgraph, Celery worker and beat, pinned digests, `securityContext`, NetworkPolicy including LLM egress, remove default passwords. | `infrastructure/k8s/helm/mukthiguru/**` | No production cutover. | `git revert`. |
| NEW-K8S-4 | Correct stale docs: replace `kubectl rollout undo` in the wiki with the Railway rollback; mark `docs/kubernetes-deployment.md`, `docs/KUBECTL_RUNBOOK.md` and `infrastructure/k8s/README.md` as reference. Fix path `k8s/` to `infrastructure/k8s/`. | `docs/wiki/operations/deployment-and-ci.md`, `docs/kubernetes-deployment.md`, `docs/KUBECTL_RUNBOOK.md`, `infrastructure/k8s/README.md` | No new content about Railway beyond a link. | `git revert`. |
| NEW-K8S-5 | Remove the default passwords at `values.yaml:153` and `:189`; use Helm `required`. Do this even under option A, because the literals are in Git history anyway and any reuse elsewhere must be rotated. Check whether either literal is used on any live system first. | `values.yaml`, `templates/neo4j.yaml`, `templates/configmap.yaml` | No history rewrite. | `git revert`. |
| NEW-K8S-6 | Register the `K8S-` prefix and NEW-K8S ids with the Lead (`CONVENTIONS.md` section 5 lists no owner for them). | `audits/audit-output-2026-11-04/CONVENTIONS.md` (Lead) | n/a | n/a |

---

## 7. Verified / Assumptions / Unknowns

### Verified (`[V-STATIC]` / `[V-GIT]`)

- Tracked K8s paths and last-commit dates in section 1.
- No file under `.github/` mentions `kubectl`, `helm`, `k8s` or `kubeconfig`.
- Makefile targets `minikube-*` call Minikube and `kubectl` locally (`Makefile:239-267`).
- `infrastructure/k8s_deploy.sh` is the only apply script and has no caller I found.
- Qdrant tag `v1.18.0` agrees across Helm, compose and the two loose manifests.
- Code exposes `/api/healthz` (`health.py:163`), `/api/health` (`:194`) and `/api/ready` (`:603`). Compose and Railway use `/api/healthz`.
- Config default `llm_provider` is `openrouter` (`config.py:71`); graph default is Memgraph (`config.py:847`).
- Three loose plain-YAML manifest files parse with `yaml.safe_load_all`.
- Helm templates have no `securityContext`. NetworkPolicy defaults to off.
- Two literal default passwords at `values.yaml:153` and `:189`.

### Assumptions

- A1: `NEO4J_BOLT_URL`, `OLLAMA_URL`, `JAEGER_AGENT_HOST/PORT` are ignored by the backend because I found no matching Settings field with grep. A field could read them through an alias I did not search.
- A2: Railway is the live target (CLAUDE.md, `.railway/railway.ts`, `KUBECTL_RUNBOOK.md:1-6`). CLAUDE.md also says the Railway project is scaled down. So "live" means "intended target," not "currently serving."
- A3: Memory figures in `values.yaml` comments are `[DOC-CLAIM]`.
- A4: The chart installs with `helm` only if Bitnami `redis` and Go templates resolve. I did not render it. The chart also ships its own `redis.yaml` template in addition to the Redis subchart dependency (`Chart.yaml:11-13`), which may create two Redis instances or a name clash. `[INF]`

### Unknowns

- U1: Why 24 files share the single commit date 2026-10-10 (likely a bulk move or format commit). Not checked in `git log` detail.
- U2: Whether any real cluster ever ran these manifests. No evidence in the repo either way.
- U3: Whether routes `/health` and `/ui` exist on the backend. I read only `health.py` route names.
- U4: Whether the two default passwords are reused on any real Redis or Neo4j. Needs the owner.
- U5: Whether the Lead wants a `K8S-` prefix or a different one.
- U6: Railway runbook details for worker, beat and graph store (cells marked "not checked" in section 4). `[LIVE-R]` for deployed state.
