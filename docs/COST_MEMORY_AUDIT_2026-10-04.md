# Cost & Memory Audit — AskMukthiGuru Railway Footprint

**Date:** 2026-10-04 · **Author:** cost-audit subagent (read-only; no `.env`, config, or deploy changes made)
**Owner ceiling:** `<$35/month` infra · **Prior measurement:** 2026-08-22 usage `$28.7854` of a `$30` hard limit, month estimate **`$53.84`**, 94.1% memory
**Deployment status at audit time:** Railway **paused/offline** (verified read-only, below) → no live billing data is being generated right now. Everything Railway-side in this doc is either (a) cited from the Aug-22 measurement, or (b) **derived/estimated**, and is labeled as such. Local numbers are **measured** with the exact command shown.

Legend: **[M]** = measured · **[D]** = derived arithmetic from measured/cited numbers · **[E]** = estimate (not measured).

---

## 1. What was measured locally (2026-10-04)

### 1.1 Docker stack — `docker stats --no-stream` (raw) **[M]**

Command:
```bash
export PATH="/Users/harshodaikolluru/.docker/bin:$PATH"
docker ps -a --format 'table {{.Names}}\t{{.Status}}\t{{.Image}}'
docker stats --no-stream --format 'table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.MemPerc}}'
```

| Container | Status | CPU% | MemUsage / Limit | Mem% |
|---|---|---|---|---|
| mukthiguru-backend | Up 5 h (healthy) | 0.30% | **2.517GiB / 6GiB** | 41.96% |
| mukthiguru-qdrant | Up 4 d (healthy) | 4.93% | 238.7MiB / 3GiB | 7.77% |
| mukthiguru-memgraph | Up 4 d (healthy) | 0.06% | **485MiB / 1GiB** | 47.36% |
| mukthiguru-redis | Up 4 d (healthy) | 0.40% | 6.348MiB / 512MiB | 1.24% |
| mukthiguru-prometheus | Up 4 d | 0.00% | 61.98MiB / 512MiB | 12.11% |
| mukthiguru-grafana | Up 4 d | 0.30% | 59.27MiB / 512MiB | 11.58% |
| mukthiguru-alertmanager | Up 4 d | 0.08% | 24.86MiB / 256MiB | 9.71% |
| mukthiguru-jaeger | Up 4 d | 0.00% | 13.32MiB / 512MiB | 2.60% |
| mukthiguru-frontend | Up 4 d (healthy) | 0.00% | 4.844MiB / 256MiB | 1.89% |
| mukthiguru-liveness-watchdog | Up 4 d | 0.00% | 956KiB / 7.748GiB | 0.01% |
| mukthiguru-autoheal | Up 4 d | 0.00% | 1.691MiB / 7.748GiB | 0.02% |
| supabase_db | Up 4 d (healthy) | 0.23% | 115.9MiB | 1.46% |
| supabase_analytics | Up 4 d (healthy) | 0.99% | 365.8MiB | 4.61% |
| supabase_studio | Up 4 d (healthy) | 0.00% | 165.2MiB | 2.08% |
| supabase_realtime | Up 4 d (healthy) | 0.23% | 130MiB | 1.64% |
| supabase_storage | Up 4 d (healthy) | 0.12% | 93.25MiB | 1.18% |
| supabase_rest | Up 4 d | 0.09% | 68.29MiB | 0.86% |
| supabase_vector | Up 4 d (healthy) | 0.04% | 75.27MiB | 0.95% |
| supabase_pg_meta | Up 4 d (healthy) | 0.38% | 62MiB | 0.78% |
| supabase_kong | Up 4 d (healthy) | 0.01% | 28.2MiB | 0.36% |
| supabase_auth | Up 4 d (healthy) | 0.00% | 22.99MiB | 0.29% |
| supabase_inbucket | Up 4 d (healthy) | 0.00% | 10.36MiB | 0.13% |

**Total across all 22 containers: 4.76 GiB [M]** (sum computed from the raw rows above).

**Railway-relevant subset only** (backend + qdrant + memgraph + redis, the services that exist on Railway today):
`2.517 GiB + 0.233 GiB + 0.474 GiB + 0.006 GiB ≈ 3.23 GiB` **[M]**.
Prometheus/grafana/jaeger/alertmanager/supabase/ frontend are **local-dev only** — no matching Railway services exist (confirmed in §3) and they contribute **$0** to the Railway bill.

### 1.2 Backend container internals **[M]**

Command:
```bash
docker exec mukthiguru-backend sh -c 'grep -i -E "vmhwm|vmrss|vmpeak" /proc/1/status'
# VmPeak: 8633092 kB   VmHWM: 2956620 kB   VmRSS: 2627096 kB
docker exec mukthiguru-backend sh -c '<walk /proc/*/status for VmRSS>'
# 2627220 kB  python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 ...
```

- **Peak RSS ever (VmHWM): 2,956,620 kB = 2.82 GiB**
- **Current RSS: 2,627,096 kB = 2.51 GiB**, a **single** uvicorn process (`WEB_CONCURRENCY=1`).
- Docker memory limits (from `docker inspect`): backend `6442450944` (6 GiB) / 4 CPU · qdrant `3221225472` (3 GiB) / 2 CPU · memgraph `1073741824` (1 GiB) / 1 CPU · redis `536870912` (512 MiB) / 0.25 CPU.

Corroborating history (cited, `lessons.md` Sep 5–6, L-DOCKER-2): backend measured **3.31 GiB idle / 4.839 GiB under load** after the 4G→6G limit fix; `embedding_service.py` documents the ONNX INT8 encoder (~570 MB data blob) + PyTorch BGE-M3 late-chunk backbone (~2.3 GB) as a deliberate ~2.9 GB coexistence. Today's 2.51 GiB steady state is consistent with the **late-chunk backbone not loaded** (it is lazy — `embedding_service.py:1454` "only loaded when `reingest_late_chunking=True`", and gating is at `:1464`), i.e. the query path legitimately sits at ~2.5 GiB.

### 1.3 Host-side processes (NOT Railway-billed) **[M]**

Command: `ps aux | sort -k6 -nr | head` and `ps -p 18500 -o pid,rss,vsz,etime,command`

| PID | RSS | Process | Note |
|---|---|---|---|
| (sample A) | 1,770,544 KB | `.../mass_ingest_2026-10/stages/run_asr.py` | ASR worker, transient |
| (sample A) | 876,224 KB | `.../mass_ingest_2026-10/stages/run_asr.py` | ASR worker, transient |
| 23175 (sample B, ~min later) | 760,912 KB | `run_asr.py` | footprint fluctuates as jobs finish |
| 18500 | 2,032 KB | `python -m scripts.ingestion.mass_first_person_ingest --workers 2` (elapsed 01:49) | parent driver, spawns ASR children |
| — | 1,170,352 KB | macOS `Virtualization.VirtualMachine` | Docker Desktop VM process (hosts all containers) |

- **ASR/ingest driver tree total: 0.71 GiB (sample B) to ~2.5 GiB (sample A)** — transient, ~41 h job, host-side only. **Not touched, not killed, not Railway-billed.** **[M]**
- Repo invariant respected: this is the ingest driver PID 18500 with 2 ASR workers; audit is read-only toward it.

---

## 2. Historical baseline (cited, 2026-08-22)

From `AGENTS.md` "Cost-effectiveness invariants — Aug 22, 2026":

- 30-minute averages: **backend 8.07 GB, Neo4j 2.45 GB, worker 154 MB, Qdrant 150 MB** (sum **10.824 GB**) **[M-then]**.
- Workspace usage MTD: **$28.7854** of the **$30** hard limit — memory **$27.0931 (94.1%)**, CPU **$1.3513 (4.7%)**, volume **$0.2645 (0.9%)**, egress **$0.0766 (0.3%)**. Month estimate: **$53.84**. **[M-then]**
- Memory is documented as **the first cost target**; worker concurrency must not be cut without queue/SLA evidence; provider-reported LLM cost must never be silently aggregated as zero. This audit obeys all three.

> **Important context change since Aug 22:** the Railway project no longer runs a `neo4j` service or a `celery-worker` service — it now lists **`memgraph`** and **`qdrant`** (§3). The Aug-22 GB composition is therefore a *historical* baseline, not the current topology.

---

## 3. Current Railway state (read-only `railway status` / `railway volume list`) **[M]**

```
Project: resilient-embrace · Environment: production
Services
  - askmukthiguru-8119b0e8: ● Failed · https://api.askmukthiguru.com   (stopped → $0 compute)
  - memgraph: ○ Offline                                               (replaces neo4j)
  - qdrant: ○ Offline · qdrant-volume
Databases
  - Redis: ● Sleeping · redis-volume
Volumes (railway volume list)
  qdrant-volume  → attached to qdrant,  1505MB/50000MB, Ready
  redis-volume   → attached to Redis,   1122MB/50000MB, Ready
```

Findings:
1. **No service is running → compute/memory billing ≈ $0 right now.** Paused = free compute (Railway bills per second, "stopped services cost nothing" — official pricing page §5).
2. **Volumes still exist and still bill** (§5 pricing: $0.15/GB-month). Two volumes, **both attached — no orphan volumes** (the historical 596 GB / ~$86-mo orphan leak from `lessons.md` is *not* present today).
3. **No `celery-worker` service** in the resource list → the Aug-22 worker's 154 MB (≈$1.5/mo) is already off the bill.
4. **Neo4j (2.45 GB ≈ $24/mo if sustained) is gone, replaced by `memgraph`** — local equivalent measured at **485 MiB with `--memory-limit=512`** (`backend/docker-compose.yml:45-61`) **[M]** → expected Railway memgraph ≈ 0.3–0.5 GB **[E]**.
5. Service memory limits / heap settings on Railway **could not be read** under this audit's constraints (only `status` was permitted). They are listed as owner verification steps in §8.

---

## 4. Pricing used (with sources)

Primary (official, fetched 2026-10-04): **https://railway.com/pricing**

| Meter | Rate | ≈ per month |
|---|---|---|
| Memory | `$0.00000386 per GB/s` | **$10 per GB** |
| CPU | `$0.00000772 per vCPU/s` | **$20 per vCPU** |
| Volumes | `$0.00000006 per GB/s` | **$0.15 per GB** |
| Egress | `$0.05 per GB` | — |

Plans: **Hobby $5/mo incl. $5 usage credit** (max 48 vCPU/48 GB per service), **Pro $20/mo incl. $20 credit** (max 1,000 vCPU/1 TB), Free $1/mo incl. $1 (1 vCPU/0.5 GB). Railway states bill ≈ `max(plan fee, usage)` because the fee's credit offsets usage; at our scale (usage > $20) **bill ≈ usage regardless of plan [D]** — verify against the invoice line items (§8, V1).

Corroborating sources (all agree on the four rates):
- https://docs.railway.com/pricing/plans — RAM `$10/GB/month`, CPU `$20/vCPU/month`, egress `$0.05/GB`, volume `$0.15/GB/month`
- https://temps.sh/blog/railway-pricing-2026 — same rate card, per-second metering
- https://www.budgetforge.dev/tools/railway-pricing-2026 — same rate card
- https://makerkit.dev/pricing-calculator/railway — same rate card + worked example

Not in scope of the $35 ceiling: **LLM provider spend (OpenRouter/Sarvam/NIM)** is a separate meter with its own budget guards (`OPENROUTER_MONTHLY_BUDGET_USD`, `SARVAM_MONTHLY_BUDGET_USD`, `*_BUDGET_FAIL_CLOSED`). This audit does **not** claim it is zero.

---

## 5. Deriving billable GB from the Aug-22 numbers

**5.1 Split the month estimate by the MTD proportions [D]**

```
ratio_memory = 27.0931 / 28.7854 = 0.941217
ratio_cpu    =  1.3513 / 28.7854 = 0.046944
ratio_vol    =  0.2645 / 28.7854 = 0.009189
ratio_egress =  0.0766 / 28.7854 = 0.002661

full-month memory = 53.84 × 0.941217 = $50.68
full-month cpu    = 53.84 × 0.046944 = $2.53
full-month volume = 53.84 × 0.009189 = $0.49
full-month egress = 53.84 × 0.002661 = $0.14
                                     total = $53.84  ✓
```

**5.2 Convert to physical averages at current rates [D]**

```
avg billable memory = $50.68 / ($10/GB)      = 5.07 GB
avg vCPU            =  $2.53 / ($20/vCPU)    = 0.126 vCPU
avg billed volume   =  $0.49 / ($0.15/GB)    = 3.30 GB
avg egress          =  $0.14 / ($0.05/GB)    = 2.87 GB
```

**5.3 Sanity check against the 30-min window [D]**

```
window sum      = 8.07 + 2.45 + 0.154 + 0.15 = 10.824 GB
monthly average = 5.07 GB  →  5.07 / 10.824 = 47%
```
⇒ the Aug-22 30-minute window ran at ~2.1× the monthly average (ingestion was active). Two bases, both kept visible:
- **Average basis (used for all scenarios below): 5.07 GB → $50.68/mo memory.**
- **Peak-window basis (upper bound): 10.824 GB × $10 = $108.24/mo memory, ~$111.7/mo total [D]** — this is what you pay if the Aug-22 window were sustained. It is the reason **hard per-service memory limits** matter: limits cap billed usage during leaks/spikes (there is precedent: `lessons.md` records a Qdrant 110 GB and backend 66 GB leak incident).

**5.4 MTD elapsed fraction [D]**: `28.7855 / 53.84 = 0.535` ⇒ the Aug-22 usage figure covered ≈53% of the billing period (~16–17 days of a 31-day cycle). Internally consistent; used only to validate the derivation, not as an independent data point.

---

## 6. Three scenarios (arithmetic shown)

Common non-memory tail (unchanged in all scenarios): **CPU $2.53 + volume $0.49 + egress $0.14 = $3.16 [D]**.
Memory line = `avg GB × $10`. All GB deltas not measured are **[E]**.

### Scenario (a) — Status quo, Aug-22 stack, current pricing

```
memory 5.07 GB × $10 = $50.68
total = 50.68 + 3.16 = $53.84   (matches Railway's own estimate ✓)
```
**Status quo = ~$54/mo.** Over the $35 ceiling by **$18.84**; over $30 by $23.84.

### Scenario (a′) — Status quo under the *current* topology (memgraph replaces neo4j, worker service gone), no other change

```
neo4j share of window = 2.45 / 10.824 = 22.64%  →  avg 1.147 GB
memgraph expected avg  = 0.40 GB  [E] (local measured 485 MiB, `--memory-limit=512`)
delta = 1.147 − 0.40 = −0.75 GB  →  −$7.50
memory = 5.07 − 0.75 = 4.32 GB → $43.18
total  = 43.18 + 3.16 = $46.34
```
**a′ ≈ $46/mo [E]** — still over ceiling. The topology change alone is not enough.

### Scenario (b) — After P0 reductions (§7)

```
b1 (conservative): backend −1.00 GB [E] (from pro-rata 3.78 GB → 2.78 GB avg)
   memory = 5.07 − 0.75 − 1.00 = 3.32 GB → $33.20
   total  = 33.20 + 3.16 = $36.36   → slightly OVER $35

b2 (backend target = today's measured local steady state 2.5 GiB): −1.30 GB [E]
   memory = 5.07 − 0.75 − 1.30 = 3.02 GB → $30.18
   total  = 30.18 + 3.16 = $33.34   → UNDER $35 ✓
```
**Scenario (b) = $33–36 [E]. Meets $35 iff the Railway backend averages ≤ ~2.6 GB.**
Backend pro-rata share used above: `3.78/10.824 → 5.07 × 0.7456 = 3.78 GB [D]`.

### Scenario (c) — Aggressive-but-safe floor

Adds to (b2): memgraph capped 512→384 MB (−0.15 GB), qdrant cache/quantization trim (−0.05 GB), no worker service / concurrency 1 if re-added (−0.07 GB), backend floor held at 2.4 GB via `PYTHON_MEMORY_LIMIT_MB=2048` + 3 GB hard limit + recycle policy (−0.10 GB). All **[E]**.

```
memory = 3.02 − 0.37 = 2.65 GB → $26.50
total  = 26.50 + 3.16 = $29.66   ≈ $30
```
**Scenario (c) ≈ $29–31 [E]** — right at the $30 line, comfortably under $35.

### Sensitivity S1 — if the $53.84 estimate *includes* the plan fee
Then usage ≈ $33.84 → memory ≈ 3.19 GB avg; scenario (b) lands ≈ **$24–27 [E]**, (c) ≈ **$22–24 [E]**. **Owner must read the invoice to disambiguate — it moves the verdict by ~$20 (§8 V1).**

### Sensitivity S2 — if the Aug-22 peak window were sustained
Status quo ≈ **$111 [D]**; scenario (b) ≈ **$86 [E]**; still far over ceiling → only hard per-service memory limits (which cap billed bytes) or scale-to-zero would control it. This is the tail-risk case the P0 limits also defend against.

---

## 7. Ranked reduction plan

Every entry: what it touches, expected GB saved **[E unless noted]**, $/mo at $10/GB, risk, rollback, and the exact owner command. **Nothing here was applied by this audit.**

### P0 — do these first (config/env only, low risk)

**P0-1 · Backend memory right-size + hard cap → −1.0 to −1.3 GB → −$10 to −$13/mo [E]**
- *Why:* backend is 74.6% of the window footprint; pro-rata average 3.78 GB vs a **measured** local steady state of 2.51 GiB / 2.82 GiB peak (§1.2). The gap is un-capped growth, warm caches, and possible in-process ingestion — all avoidable.
- *Touches:* Railway service `askmukthiguru-8119b0e8` env + dashboard resource limit (no repo file edit required; equivalent knobs live in `backend/docker-compose.yml:218` `PYTHON_MEMORY_LIMIT_MB`, `:351` `WEB_CONCURRENCY`).
- *Owner commands/settings:*
  ```bash
  railway variables --json '{"PYTHON_MEMORY_LIMIT_MB":"2048","WEB_CONCURRENCY":"1"}' \
    --service askmukthiguru-8119b0e8
  # Dashboard → askmukthiguru-8119b0e8 → Resources → Memory = 4 GB, CPU = 2
  ```
  plus: confirm `GUARDRAILS_PROVIDER=lightweight` (repo decision `docs/GUARDRAILS_DECISION.md`), `CELERY_TASK_ALWAYS_EAGER=false` so ingestion never inflates the API process, and a weekly redeploy/recycle to release growth.
- *Risk:* low. `PYTHON_MEMORY_LIMIT_MB` is documented as a glibc-arena ceiling, **not** RLIMIT_DATA (comment at `backend/docker-compose.yml:221-226` — a prior ceiling here broke thread creation).
- *Rollback:* `railway variables --json '{"PYTHON_MEMORY_LIMIT_MB":"0"}'` and restore the previous dashboard limit.

**P0-2 · Confirm the memgraph swap banked the Neo4j saving → −0.75 GB → −$7.50/mo [E]**
- *Why:* Aug-22 ran Neo4j at 2.45 GB; the project now lists `memgraph` only (§3). Local memgraph measured **485 MiB** with `--memory-limit=512`.
- *Touches:* Railway service `memgraph` (config already in `backend/docker-compose.yml:45-61`).
- *Owner command:* `railway variables --service memgraph` (verify a memory limit exists; set `MEMGRAPH_MEMORY_LIMIT`/`--memory-limit=512` in its start command if unset).
- *Risk:* low (service already swapped; this is verification).
- *Rollback:* n/a — `legacy-neo4j` profile still exists locally.

**P0-3 · Verify volume billing basis / resize → $0 to −$14/mo conditional [E]**
- *Why:* two volumes show `1505MB/50000MB` and `1122MB/50000MB`. If Railway bills the **provisioned** 50 GB each → 100 GB × $0.15 = **$15/mo**; if it bills used/auto-grown size (~2.6 GB) → **~$0.40/mo**. The Aug-22 volume line ($0.2645 MTD ≈ $0.49/mo full month ⇒ ~3.3 GB **[D]**) strongly suggests used-size billing, so likely **no action needed** — but the invoice decides.
- *Owner command:* Dashboard → Billing → usage breakdown line "Volumes", or `railway volume list` after resize.
- *Risk:* low-medium (shrink must stay above used size: 1505 MB → 5 GB, 1122 MB → 3 GB).
- *Rollback:* volume can be grown back; data is preserved while ≥ used size.
- **Orphan check already done: both volumes attached, none orphaned [M].**

**P0-4 · Re-verify per-service memory limits at unpause (leak insurance) [E]**
- Precedent: `lessons.md` records Qdrant 110 GB / backend 66 GB / Neo4j 44 GB leak-class incidents. A 4 GB backend + 2 GB memgraph + 2 GB qdrant + 0.5 GB redis cap ⇒ worst-case billable ≈ 8.5 GB ≈ $85/mo [D] instead of unbounded.

### P1 — medium effort, medium reward

**P1-1 · Backend floor trim (model/cache discipline) → additional 0.3–0.5 GB → −$3 to −$5/mo [E]**
- Verify on Railway logs that the **late-chunk PyTorch backbone (~2.3 GB) is never loaded** in the API process (gated at `backend/services/embedding_service.py:1464`, only `ingest/contextual_reingest.py:1376` calls it — ingestion must run in the worker, not the API service).
- Verify `SEMANTIC_CACHE_ENABLED`/GPTCache (`gptcache_max_size=1000`, `app/config.py:1236`) and LightRAG query caches (`_cache_lock` bounded `TTLCache`) stay bounded.
- *Risk:* low (verification-first; no behavior change).
- *Rollback:* n/a unless a flag is flipped.

**P1-2 · Memgraph headroom trim 512→384 MB → −0.15 GB → −$1.50/mo [E]**
- *Touches:* `backend/docker-compose.yml:51` `command: ["--memory-limit=512", ...]` (local) and the Railway memgraph start command (prod).
- *Risk:* low-medium — graph is tiny (data footprint ~20 MB per `lessons.md` "Evidence-Based Database Memory Sizing"), but re-verify traversal p95 after.
- *Rollback:* set `--memory-limit=512` back.

**P1-3 · Qdrant in-RAM vectors — leave as-is, document**
- `first_person_v7` has `on_disk:false` (vectors in RAM) but the collection is small: Railway Qdrant measured **150 MB [M-then]** ≈ **$1.50/mo**. Enabling `on_disk` saves ≤$1/mo and costs latency — **not worth it**. If Qdrant ever grows 10×, revisit with `on_disk:true` + scalar quantization (`lessons.md`: `QUANTIZATION=scalar`, `CACHE_SIZE=2GB`).

**P1-4 · Redis — no change**
- Local: `--maxmemory 450mb --maxmemory-policy allkeys-lru` (`backend/docker-compose.yml:116-117`). Railway Redis is **Sleeping** now; at ~0.1 GB running it is ≈$1/mo. `REDIS_CACHE_MAX_KEYS` invariants apply to key counts, not cost.

### P2 — evidence-gated or marginal (do not do blind)

**P2-1 · Worker concurrency — DO NOT cut without queue/SLA evidence (repo invariant).**
The `celery-worker` service is currently **absent from the Railway resource list** (i.e. $0). If/when re-added, default `--concurrency=${CELERY_CONCURRENCY:-1}` (`backend/docker-compose.yml`) is already the floor; measured Aug-22 footprint 154 MB ≈ $1.50/mo. Any further cut requires queue-depth + user-memory SLA data per `AGENTS.md`.

**P2-2 · Scale-to-zero / sleep idle services.** Railway bills stopped services $0 compute (official pricing). Only viable for non-critical services (e.g. a staging backend); the user-facing API must stay up. Would beat scenario (c) if applied to long idle windows — availability tradeoff, owner decision.

**P2-3 · Plan tier.** Hobby ($5) and Pro ($20) both net out to ≈ usage because the fee is credited; downgrade saves nothing at usage > $20 **[D]**, but confirm on the invoice (V1). Hobby caps 48 vCPU/48 GB per service — far above our needs.

---

## 8. Owner verification steps (read-only; none run here beyond `status`/`volume list`)

| # | Check | Why it matters |
|---|---|---|
| V1 | Invoice line items: does "$53.84 estimate" include the plan fee? | Moves verdict ±$20 (Sensitivity S1) |
| V2 | `railway variables --service askmukthiguru-8119b0e8` → confirm `PYTHON_MEMORY_LIMIT_MB`, `WEB_CONCURRENCY`, `GUARDRAILS_PROVIDER`, `CELERY_TASK_ALWAYS_EAGER`, `OTEL_ENABLED` | P0-1 precondition |
| V3 | Dashboard → service Resources: current memory limits for backend/memgraph/qdrant/Redis | P0-4 |
| V4 | Dashboard → Billing → "Volumes" line: provisioned vs used basis | P0-3 (−$0 to −$14) |
| V5 | 7–14 days after unpause: export per-service GB-day averages and re-run §5 math | Confirms/rejects every **[E]** in this doc |

---

## 9. Verdict vs the $35 ceiling

| Scenario | Basis | $/mo | vs $35 | vs $30 |
|---|---|---|---|---|
| (a) Status quo (Aug-22 stack) | measured estimate | **$53.84 [D]** | ✗ +$18.84 | ✗ +$23.84 |
| (a′) Current topology only (memgraph, no worker) | derived | **$46.34 [E]** | ✗ +$11.34 | ✗ +$16.34 |
| (b) P0 applied, backend ≤2.6 GB avg | derived | **$33.34 [E]** | **✓ −$1.66** | ✗ +$3.34 |
| (b1) P0 applied, conservative backend delta | derived | $36.36 [E] | ✗ +$1.36 | ✗ |
| (c) Aggressive-safe floor | derived | **$29.66 [E]** | **✓ −$5.34** | **✓ ≈ −$0.34** |
| (c) with S1 (estimate included plan fee) | derived | ~$23–25 [E] | ✓ | ✓ |

**Verdict:**
1. **≤$35/mo is reachable** with P0-1 + P0-2 alone (scenario b2 ≈ $33), *provided* the Railway backend averages ≤ ~2.6 GB — a target already demonstrated locally today (2.51 GiB **[M]**).
2. **≤$30/mo is borderline, not guaranteed**: needs P0 + P1 floor trims (scenario c ≈ $29.7) **or** S1 to be true (invoice includes plan fee). If neither holds, the honest floor is ~$30–31; going lower requires scale-to-zero on idle services (P2-2) or accepting the $30–31 plateau.
3. **Head-room discipline:** because Railway bills per second with no idle markup, memory limits (P0-4) are the single control that converts a leak/spike from an unbounded bill into a bounded one. The peak-window sensitivity ($111/mo) shows exactly what that protection is worth.
4. **Local stack ≠ Railway bill:** 4.76 GiB of local containers includes 13 Supabase + 4 observability containers that have no Railway counterpart. Do not price the local table directly.

---

## 10. Appendix — exact commands used (all read-only)

```bash
# local containers
export PATH="/Users/harshodaikolluru/.docker/bin:$PATH"
docker ps -a --format 'table {{.Names}}\t{{.Status}}\t{{.Image}}'
docker stats --no-stream --format 'table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.MemPerc}}'
docker exec mukthiguru-backend sh -c 'grep -i -E "vmhwm|vmrss|vmpeak" /proc/1/status'
docker exec mukthiguru-backend sh -c 'for p in /proc/[0-9]*; do r=$(grep -m1 VmRSS $p/status 2>/dev/null | awk "{print \$2}"); c=$(tr "\0" " " < $p/cmdline 2>/dev/null | cut -c1-70); [ -n "$r" ] && echo "$r $c"; done | sort -rn | head -8'
docker inspect --format '{{.HostConfig.Memory}} {{.HostConfig.MemoryReservation}} {{.HostConfig.NanoCpus}}' <container>

# host
ps aux | sort -k6 -nr | head -22
ps -p 18500 -o pid,rss,vsz,etime,command

# railway (read-only)
railway status
railway volume list

# config/code reads (no modification)
backend/docker-compose.yml (services, limits, env), backend/app/config.py,
backend/services/embedding_service.py:597,:1454-1474, docs/GUARDRAILS_DECISION.md, lessons.md
```

**No `.env`/`.yml`/config edits, no container restarts, no Railway state changes, no LLM API calls, no git commits were made by this audit.**
