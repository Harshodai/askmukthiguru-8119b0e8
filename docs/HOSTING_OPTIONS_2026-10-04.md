# Hosting Options — AskMukthiGuru, 2026-10-04

**Status:** RESEARCH ONLY. No code/infra changes made, no accounts created, no purchases.
**Owner decision:** pursue BOTH hosting change AND cuts. This doc is the hosting half; cuts live in `COST_MEMORY_AUDIT_2026-10-04.md` (scenarios b/c).
**Baseline (measured):** Railway-relevant idle ≈ **3.2 GiB local steady-state** (backend 2.5 + memgraph 0.47 + qdrant 0.23 + redis ~0.01), **~4.3 GiB Railway average basis** after memgraph swap (audit §6a′ ≈ **$46/mo**), peak-window basis ≈ 10.8 GiB. Ceiling **<$35/mo hard**. Traffic now low, target **1k MAU**. LLM ~$10/mo at 1k MAU — not the constraint; idle infra is.
**Stack to place:** FastAPI backend (~2.5 GiB, ONNX embedding, single process `WEB_CONCURRENCY=1`), Qdrant (~240 MB, 89k prod pts × 1024d int8 ≈ 100–300 MB + payloads), Memgraph (512 MB cap), Redis (tiny), optional worker (currently $0 — absent). Single replica. A `docker-compose.yml` already exists.

---

## 1. Options table ($/mo, 2026 pricing, sources in §4)

| # | Option | Idle $/mo (today's ~4.3 GiB) | 2× footprint (~8.6 GiB) | Ops burden | Migration from compose | Solo-dev fit <$35 |
|---|---|---|---|---|---|---|
| (a) | **Hetzner Cloud VPS** (all-in-one) | **~$11–15** (CX32 4vCPU/8GB ≈ €9–12 post-Apr-2026 increase; ARM CAX32 cheaper) | **~$22** (CX42 16GB ≈ €20) | You own OS patches, backups, deploys (unattended-upgrades + snapshots + Coolify) | **4–8 h**: `scp` compose file, env, volumes; DNS cutover | ✅ Best fit |
| (b) | **Oracle Cloud Always Free** (all-in-one) | **$0** (fits: free allowance now **2 OCPU / 12 GB**, halved Jun-2026) | **$0** (8.6 < 12 GB) | Highest: capacity errors, idle-reclamation risk, card required, worst support | 6–12 h + provisioning lottery (days–weeks to get capacity) | ⚠️ Cheapest, riskiest |
| (c) | **Stay on Railway** (scale-to-zero / credits) | **~$46** (audit a′); sleep saves ≈ $0 (worker already gone; API can't sleep) | **~$80–110** (2nd replica doubles RAM $) | Lowest (managed) | 0 h | ❌ No math path under $35 without cuts; even with cuts (b2 ≈ $33) zero headroom |
| (d1) | **Render** | **≥$85** (backend 2.5 GB needs 4 GB tier ≈ $85; ×4 services worse) | ≥$150 | Low (managed) | 4–6 h, per-service render.yaml | ❌ Dead on arrival |
| (d2) | **Fly.io** (4 Machines always-on) | **~$45–55** (backend 4 GB ≈ $30 + 3 small machines + volumes + IPv4 $2) | ~$90+ | Low-medium (fly.toml, volumes per app) | 6–10 h (one Fly app per service + private networking) | ❌ Autostop doesn't apply to always-warm API + stateful Qdrant/Memgraph/Redis |
| (d3) | **Coolify on VPS** | **Same as (a) + $0** (Coolify is free self-hosted; Hetzner one-click app) | Same as (a) | Medium-low: you own host, Coolify gives PaaS UX (git push, TLS, backups) | 6–10 h (first Coolify setup, then compose import) | ✅ Good if owner wants Railway-like UX |
| (e) | **Split: Qdrant Cloud free + cheap compute** | **~$11–13** (Qdrant free 1 GB/4 GB disk fits corpus + CX32 8 GB for rest) | **~$22–25** (Qdrant Standard from ~$25 if corpus outgrows 1 GB) | Low for vectors (managed), you own rest | 3–6 h (endpoint swap + snapshot restore) | ✅ Best hybrid; de-risks self-hosted state |
| (f) | **Supabase (Postgres/auth)** | **$0** (Free: 500 MB DB, 50k MAU, 5 GB egress — 1k MAU fits) | **$0–25** (Pro $25 only if DB > 8 GB or MAU/egress force it) | None (already hosted) | 0 h — **keep, no change** | ✅ Keep |

**Cheapest honest floor:** (b) $0 Oracle > (a)/(e) ~$11–15 Hetzner > (c) ~$46 Railway ≈ (d2) ~$45–55 Fly > (d1) ≥$85 Render.

---

## 2. Recommended path (with math)

**Primary: (a) Hetzner CX32 (x86, 4 vCPU / 8 GB RAM, ~€10–12/mo ≈ $11–13) + existing `docker-compose.yml` as-is. Keep (f) Supabase hosted. Keep Qdrant self-hosted initially; (e) Qdrant Cloud free tier as ready fallback.**

Why this one:
- **Fits ceiling with headroom:** idle ~$11–13/mo vs $35 → **~$22/mo spare** for LLM (~$10 at 1k MAU), snapshots (~€0.02/GB-mo), domain, and growth. At 2× footprint a one-click resize to 16 GB ≈ $22 — still under ceiling. Nothing else metered-by-RAM survives 2× under $35.
- **Zero architecture change:** compose file already defines backend/qdrant/memgraph/redis with limits; move is lift-and-shift, not re-platform. Cuts work (audit scenarios b/c) stacks on top instead of competing with it.
- **x86, not ARM:** current images (ONNX encoder, BGE-M3, memgraph) are built/run x86 today. ARM CAX is ~10–20% cheaper but adds a rebuild-and-revalidate step for every image; not worth it for ~$2/mo. Revisit ARM only if bill pressure returns.
- **8 GB sizing, not 4 GB:** backend 2.5 + memgraph 0.5 + qdrant 0.25 + redis 0.1 + OS/docker ~0.7 ≈ 4.1 GiB — a 4 GB VPS leaves no spike room (audit S2: leak-class incidents hit 44–110 GB historically; caps contain billing on flat-rate but OOM-kill the process). 8 GB gives ~2× headroom for the price of a coffee.
- **Qdrant Cloud free as fallback, not day one:** 89k × 1024d int8 ≈ 100–300 MB + payloads fits the free 1 GB/4 GB-disk single node, but self-hosted Qdrant is currently healthy (238 MB, stable 4 d uptime) — don't pay migration risk for a working component. If the VPS ever feels tight, offloading Qdrant to the free tier frees ~0.3 GB and removes one stateful volume for $0.

Math recap (idle, incl. ~$1–2 snapshots/backups):
- Recommended: **~$12–15/mo all-in** (VPS $11–13 + snapshots ~$1 + Supabase $0 + LLM ~$10 at 1k MAU billed separately to OpenRouter, outside infra ceiling).
- 2× footprint: **~$23–25/mo** (resize to 16 GB). Still under $35.
- vs Railway status quo $46–54: **saves ~$33–40/mo (~70%)**.

**Runner-up:** (b) Oracle $0 — accept only if owner explicitly trades reliability for $12/mo savings (see risks). **Do not choose:** (c) Railway without cuts (no path), (d1) Render / (d2) Fly (per-service/per-machine billing punishes exactly this 4-service shape).

---

## 3. Migration sketch (NOT executed)

1. **Prep (local, 1 h):** snapshot Qdrant (`scripts/ops/qdrant_backup.py` exists) + memgraph dump; record env (`railway variables --service …` read-only); confirm image arches are x86; point a staging DNS record at the new host.
2. **Provision (1 h):** Hetzner CX32 (Falkenstein/Nuremberg for EU latency; Ashburn if users are US/IN-diaspora — pick one, latency to India ~150–200 ms either way; LLM calls dominate anyway) with Docker CE one-click image; attach firewall (443/80 only + ssh from owner IP), enable unattended-upgrades, weekly snapshot schedule.
3. **Deploy (1–2 h):** copy compose file + `.env` (secrets via `scp`, never committed); `docker compose up -d backend qdrant memgraph redis`; restore Qdrant snapshot + memgraph dump; verify `/api/healthz` + `/api/health` + one anon chat turn.
4. **Cutover (1 h):** flip DNS (low TTL first), keep Railway paused (not deleted) for 1 week as instant rollback; monitor logs + `docker stats` for 48 h; confirm 7-day memory average stays < 6 GB.
5. **Decommission (30 min, after bake-in):** delete Railway volumes only after VPS snapshots verified (volumes bill $0.15/GB-mo even while paused).
6. **Optional later:** import compose into Coolify (one-click Hetzner app) for git-push deploys; move Qdrant to Cloud free tier if desired.

**Effort total: ~4–8 h solo** (one evening + a monitoring tail). Rollback: DNS flip back to Railway unpause (< 15 min) within the 1-week overlap.

---

## 4. Risks

| Risk | Likelihood / impact | Mitigation |
|---|---|---|
| You own uptime (no managed SLA; single VPS = single point of failure, same as Railway 1-replica today) | Med / med | Hetzner 99.9% SLA; weekly snapshots; health endpoint + liveness watchdog already in compose; accept — parity with today, not regression |
| OOM on flat host kills processes instead of billing more (audit S2 leak precedent) | Med / med | Keep compose memory caps (backend 4 GB, memgraph 512 MB, qdrant 2 GB, redis 512 MB); alertmanager already in compose |
| Hetzner Apr-2026 +20–37% increases; future hikes | Low-med / low | Even +40% keeps CX32 ≈ $17 — still half the ceiling; exit cost is one `scp` |
| Oracle (if chosen): "Out of Capacity" provisioning failures; idle reclamation; Jun-2026 halving to 2 OCPU/12 GB could repeat | High / high | Don't bet prod on it without a paid fallback; treat as dev/staging host at most |
| Qdrant Cloud free: single node, no HA, 4 GB disk cap; corpus growth forces Standard (~$25+) | Low now / med later | Corpus grows via deliberate ingest, not organically — revisit only past ~500k vectors |
| Data residency (Hetzner EU default; spiritual-content + user vault data) | Low / low | EU/GDPR hosting is arguably a plus; Supabase region unchanged; note in privacy policy |
| Solo-dev on-call burden (OS patches, Docker, disk-full) | Med / low | unattended-upgrades + snapshot schedule + existing watchdog/autoheal containers; ~1 h/quarter real work |

## 5. Sources (all fetched 2026-10-04)

- Hetzner cloud pricing post-increase (€3.79+ plans; CX22 2vCPU/4GB ≈ €3.79–4.99; up to +37% Apr-2026): https://www.bitdoze.com/hetzner-cloud-cost-optimized-plans/ · https://tuxai.dev/best-linux-vps-hosting/ · https://docs.hetzner.com/general/infrastructure-and-availability/price-adjustment/ · https://www.hetzner.com/cloud/ (plan structure; prices JS-rendered, verify at checkout)
- Hetzner dedicated AX41 64 GB ≈ €59/mo (overkill reference): https://www.hetzner.com/dedicated-rootserver/ax41/
- Oracle free tier halved to 2 OCPU/12 GB (Jun-2026): https://www.reddit.com/r/oraclecloud/comments/1ubk2qy/new_always_free_tier_limits_21june2026_update/ · https://www.infoq.com/news/2026/07/oracle-cloud-free-tier-limits/ · https://terminalbytes.com/oracle-cloud-free-tier-changes-2026/ · capacity-error workaround: https://community.amperecomputing.com/t/how-to-get-around-the-out-of-capacity-error-on-the-always-free-tier-of-oci/3432
- Railway rates ($10/GB-mo RAM, $20/vCPU-mo, Hobby $5 incl $5 credit, stopped = $0 compute): https://railway.com/pricing · https://temps.sh/blog/railway-pricing-2026 · https://makerkit.dev/pricing-calculator/railway
- Render (Starter $7/svc, 2 GB $25, 4 GB $85): https://render.com/pricing · https://checkthat.ai/brands/render/pricing
- Fly.io (preset table; +$6/GB-mo extra RAM; volumes $0.15/GB; IPv4 $2; autostop/suspend): https://fly.io/pricing/ (fetched verbatim) · https://docs.fly.io/about/pricing · https://community.fly.io/t/how-to-optimize-billing-costs-and-shut-down-machines-when-not-in-use/23974
- Qdrant Cloud free (1 GB RAM / 0.5 vCPU / 4 GB disk, ~1 M × 768d vectors; Standard ≈ $0.078/GB-h ≈ $57/GB-mo): https://qdrant.tech/pricing/ · https://qdrant.tech/documentation/cloud/create-cluster/ · https://leanopstech.com/blog/qdrant-cloud-pricing-2026/
- Supabase (Free $0: 500 MB DB, 50k MAU; Pro $25): https://supabase.com/pricing · https://makerkit.dev/blog/saas/supabase-pricing
- Cross-comparison (Railway vs Render vs Fly 2026): https://sota.io/blog/railway-vs-render-vs-fly-pricing-2026 · https://bex.co/blog/2026/08/17/railway-render-flyio-july-2026-pricing-benchmark
