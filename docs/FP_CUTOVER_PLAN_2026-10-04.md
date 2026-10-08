# FP Production Cutover Plan — alias-based reads + zero-downtime swaps (2026-10-04)

**Status:** PLAN ONLY. Nothing below has been executed. Owner triggers each step.
**Parent rec:** `docs/QDRANT_FP_RESEARCH_2026-10-04.md` rec #9 (read-via-alias + pre-swap golden gate) — still undone.
**Scope:** Qdrant FP path only. Main-graph collection (`spiritual_wisdom*`) untouched. No code changes in this plan (config/env + Qdrant API + existing scripts/tools only).
**Method:** read-only code/config verification + web research (2024–2026, URLs cited at bottom). 0 LLM calls.

## 0. Verified starting state (do not re-derive — checked 2026-10-04)

| # | Fact | Hook |
|---|---|---|
| 1 | NO aliases exist (`GET /aliases` was `[]`) | task brief, confirmed pattern in code |
| 2 | Reads pin the concrete name: `first_person.py:214` (`settings.first_person_collection`), `first_person_bridge.py:332`, `first_person_store.py:200-202` (store binds `self._collection` at `__init__` from settings) | code reads this session |
| 3 | Live env already `FIRST_PERSON_COLLECTION=first_person_v7` (root `.env:165`); **code default is `first_person_v1`** (`config.py:159`) — any env without the override reads the wrong (stale, 580-pt) collection | `.env` grep + `config.py:159` |
| 4 | `QdrantAliasManager` implements the full pattern: `create_shadow_collection` (now derives indexes from **source live schema**, parity fix landed — `qdrant_aliases.py:46-72,257-279`), `atomic_alias_swap` (single `update_collection_aliases` call + post-verify + ledger, `:284-356`), `rollback_alias` (ledger-backed, `:358-384`), `cleanup_old_collections` (protects ALL alias targets, `keep_last_n>=1`, `:386-435`) | `qdrant_aliases.py` full read |
| 5 | Calibration profile `config/first_person_calibration_v7.json` is demoted (`claims:none`) and has **no `collection` key** → the release-gate collection-mismatch check (`first_person_release.py:54-56`) is skipped today. Alias rename does NOT trip the prod release gate. Refits that add a `collection` key must use the **alias name** (see risk R5) | profile + `first_person_release.py:31-59` reads |
| 6 | Exact cache keys on collection string (`first_person_pipeline.py:800-823` per research doc §12) → any collection-name change (incl. alias introduction) **cold-starts the exact cache** (correct, plan the latency bump) | research doc §12 |
| 7 | Backup script defaults to `spiritual_wisdom` (`qdrant_backup.py:56`) — **FP has no confirmed cron coverage** (research §11 gap (a), still open) | `qdrant_backup.py:56` grep |
| 8 | Restore drill exists but **never ran for real** (`docs/operations/drills.md` §2; targets read from settings, which today resolve to stale `first_person_v1` default unless env override active) | `drills.md:117-208` |
| 9 | Golden-25 gate thresholds are pre-ingest floors (`TOP1 0.12 / SAME_VIDEO 0.0 / SAME_CLIP 0.0 / n_errors==0`, `golden25-gate.yml:53-55,141-144`) with **rank metrics already logging informationally** (`--rank-depth 10 --probe-legs`, recall@5/10 + MRR + NDCG@10, `:123-128,157-169`). Post-ingest re-measure mandated in the same change as provenance | `golden25-gate.yml` full read |
| 10 | Mass ingest writes **directly into live `first_person_v7`** (deferred-apply, `deletions=0` proven). So the first cutover is **alias introduction**, not a shadow swap; the shadow-swap runbook below is the repeating pattern for v8+ | session brief + checklist |

## 1. What must be true before Step 1 (Gate 0 — all blocking)

- [ ] **G0-1 Ingest complete:** driver exited / `state.json` 0 pending; `first_person_v7` ≈ 2,500 pts; `scripts/ops/reconcile_first_person_v7.py --dry-run` → 0 mismatches; ID audit clean.
- [ ] **G0-2 Phase-1 gates green:** triage log reviewed → harness re-baselined → **golden-25 re-measured, thresholds + provenance updated in ONE change** (`golden25-gate.yml` envs + header, `CLAUDE.md` CI line, checklist §D row 5). The §2 gate below consumes these re-measured floors.
- [ ] **G0-3 Backend up:** local compose stack healthy (`/api/health` `ready:true`); Qdrant `GET /collections/first_person_v7` → `green`; `GET /aliases` → `[]` (confirms no one else created the alias meanwhile).
- [ ] **G0-4 Snapshot taken:** fresh `first_person_v7` snapshot via backup script + downloaded/S3 (covers §3 rollback path B). Record snapshot name in the cutover log.
- [ ] **G0-5 Writer quiesced:** ingest driver stopped (`kill -0 $(cat /tmp/mukthiguru_ingest.pid)` must fail) — alias introduction is read-safe, but a concurrent writer confuses point-count verification.

## 2. Step sequence — Part A: alias introduction (one-time, 6 steps)

Reads move from concrete `first_person_v7` → alias `first_person`. All Qdrant ops are REST (no code); verify each step before the next.

- [ ] **A1 — Create alias** (ms; atomic single action):
  ```bash
  curl -s -X POST http://localhost:6333/collections/aliases \
    -H 'Content-Type: application/json' \
    -d '{"actions":[{"create_alias":{"collection_name":"first_person_v7","alias_name":"first_person"}}]}'
  curl -s http://localhost:6333/aliases  # expect first_person -> first_person_v7
  ```
  Manager equivalent (same effect + ledger): `QdrantAliasManager().atomic_alias_swap("first_person", "first_person_v7")` (no-op path when alias absent → pure create).
- [ ] **A2 — Prove alias serves:** run golden-25 (or ≥5-question smoke) with `--collection first_person` → results identical to `--collection first_person_v7` run. Qdrant resolves aliases on all read/write paths (collections docs), so parity is expected; this step proves it on OUR data.
  ```bash
  cd backend && .venv/bin/python -m evaluation.first_person_harness run \
    --collection first_person \
    --questions evaluation/datasets/first_person_golden_paraphrase_25.json \
    --rank-depth 10 --probe-legs --out /tmp/golden25_alias_parity.json
  ```
- [ ] **A3 — Flip reads to alias:** root `.env`: `FIRST_PERSON_COLLECTION=first_person_v7` → `FIRST_PERSON_COLLECTION=first_person`. (Same key other envs/hosting targets use; repeat per target at deploy time.)
- [ ] **A4 — Restart backend so stores rebind:** `FirstPersonStore` binds the collection string at `__init__` (`first_person_store.py:200-202`) — a config change needs a process restart, not just a request. Compose `restart` does NOT re-evaluate env files (lessons `L-OPS` note) → full recreate:
  ```bash
  docker compose up -d --force-recreate backend   # (via Makefile wrapper; adjusts PATH per AGENTS.md)
  ```
  Then verify live: `/api/health` 200 + a first-person probe returns `coll=first_person` (bridge echoes `first_person_collection`, `first_person_bridge.py:560`).
- [ ] **A5 — Soak:** 24h normal traffic on alias reads. Watch: exact-cache miss rate (cold-start spike expected, decays with 24h TTL), p95 on `/api/first-person/query`, zero 5xx. Alias resolution is server-side per request; no client-side cache to flush (qdrant-client holds no alias→collection map — risk R1 details the one exception to check).
- [ ] **A6 — Record:** cutover log entry (alias target, snapshot name from G0-4, A2 parity report path, soak window). Keep `first_person_v7` concrete reads working in parallel — nothing deleted in Part A.

## 3. Step sequence — Part B: repeating shadow-swap runbook (v8+, 8 steps)

Used for every future reindex (schema change, `rights_cleared` index add, refit, bulk correction). Assumes reads already on alias `first_person`.

- [ ] **B1 — Snapshot current target:** `QDRANT_COLLECTION=<alias-target, e.g. first_person_v7> python3 scripts/ops/qdrant_backup.py` (override env — default covers main corpus only, §0.7). Record snapshot name. (~seconds at 2.5k pts.)
- [ ] **B2 — Create shadow:** `QdrantAliasManager().create_shadow_collection("first_person")` → e.g. `first_person_v<timestamp>`. Inherits vectors/sparse/HNSW/optimizers/WAL + payload indexes from source live schema (parity by construction, `qdrant_aliases.py:46-72`). Confirm index list in returned name + `GET /collections/<shadow>` green.
- [ ] **B3 — Build shadow:** run the index builder targeting the shadow name (builder takes `--collection`, defaulting to settings — pass explicitly):
  ```bash
  cd backend && .venv/bin/python -m scripts.ops.build_first_person_index --collection <shadow>
  ```
  (Host-side embeddings — never in-container, OOM lesson `L-OPS-MOUNT-1` / lessons.md:11222.)
- [ ] **B4 — Pre-swap gate (BLOCKING, §4):** all green or no swap. Gate runs against `<shadow>`.
- [ ] **B5 — Atomic swap** (ms; single transaction, no request sees a half-state):
  ```bash
  curl -s -X POST http://localhost:6333/collections/aliases -H 'Content-Type: application/json' \
    -d '{"actions":[{"delete_alias":{"alias_name":"first_person"}},{"create_alias":{"collection_name":"<shadow>","alias_name":"first_person"}}]}'
  curl -s http://localhost:6333/aliases  # expect first_person -> <shadow>
  ```
  (Manager: `atomic_alias_swap("first_person", "<shadow>")` — adds post-verify + ledger entry rollback needs.)
- [ ] **B6 — Serve-verify (5 min):** 5-question smoke via alias + `GET /api/health`; exact-cache cold-start expected (key includes collection string) — warm with the top ~20 golden questions if p95 matters immediately.
- [ ] **B7 — Soak + observe (24–48h):** golden-25 nightly green on alias; error/latency watch. **Do NOT delete the predecessor during soak** — it is the instant-rollback path (§5, seconds).
- [ ] **B8 — Cleanup (only after soak green):** `cleanup_old_collections("first_person", keep_last_n=3, dry_run=True)` → review → `dry_run=False`. Manager protects every alias target unconditionally; `keep_last_n>=1` enforced. Never `keep_last_n=0`.

## 4. Pre-swap gate definition (B4 — ALL must pass; any red blocks B5)

| # | Check | Command / where | Threshold (post-ingest floors from G0-2) |
|---|---|---|---|
| G1 | Point-count + ID reconciliation | `scripts/ops/reconcile_first_person_v7.py` retargeted at `<shadow>` (or `--collection` if supported; else env override) | **0 mismatches** |
| G2 | Rights/servability audit | scroll `<shadow>`: `rights_cleared=true` fraction; `points_servable` spot-check | **100% servable-expected; 0 un-cleared served** |
| G3 | Golden-25 attribution | harness `--collection <shadow>` (same dataset SHA pin) | **top1 ≥ re-measured floor; same_video/same_clip ≥ floors; `n_errors==0`** |
| G4 | Rank metrics recorded | same run (`--rank-depth 10 --probe-legs`) | **recall@5/10, MRR, NDCG@10 logged** (info-only until 2 windows set floors per lessons.md rule; fail only on harness error) |
| G5 | Collection health | `GET /collections/<shadow>` | **`status: green`** |
| G6 | Index parity | `test_fp_shadow_index_parity.py` logic / compare `<shadow>` payload_schema vs source | **no missing filter indexes** (esp. `rights_cleared` once rec#1 lands) |
| G7 | Calibration consistency | profile `threshold`/`score_kind` unchanged OR refit recorded with `fitted_at` bump (cache invalidates cleanly) | **no silent threshold change** |
| G8 | Writer state | ingest driver liveness check | **stopped** (no concurrent writer during swap) |

## 5. Rollback procedure (in priority order — fastest first)

| Path | When | Steps | Time estimate |
|---|---|---|---|
| **R1 alias flip-back (preferred)** | Wrong-content / quality regression detected during B6/B7 soak; predecessor intact | `QdrantAliasManager().rollback_alias("first_person")` (ledger) — or explicit `atomic_alias_swap("first_person", "<predecessor>")`. Verify via `GET /aliases` + 5-question smoke. Restart backend NOT needed (reads resolve alias per request; store holds the alias *name*). Exact cache cold-starts again — expected. | **seconds** (alias ops are ms; verification ~2–5 min) |
| **R2 snapshot restore** | Predecessor deleted/corrupted, or alias itself broken | `recover_snapshot` of B1/G0-4 snapshot into a fresh collection name → alias-swap to it (B5 shape) → smoke. Needs ~2× collection disk during restore (migration-recovery docs). | **minutes** at 2.5k pts (snapshot create+download seconds; restore+verify ~5–15 min) |
| **R3 full rebuild** | Snapshots lost too | Re-run mass ingest from passages (hours of yt-dlp + embed) | **hours** (this is why B1 + §0.7 backup coverage are blocking, not nice-to-have) |

Rollback keeps: predecessors until B8; ledger file (`~/mukthiguru_attribution_data/qdrant_alias_ledger.json`) — back it up with the snapshot record; one known-good snapshot per generation.

## 6. Risk table

| ID | Risk | Likelihood / impact | Mitigation in this plan | Residual |
|---|---|---|---|---|
| R1 | **Stale collection binding:** stores bind the name at `__init__`; a swap without understanding binding serves old data until restart | Med / High | Part A A4 documents restart-on-rename. Post-B5: reads hold the *alias name* so future swaps need NO restart — but verify on first B5 with the A4 probe (`coll=` echo) that the stack resolves per-request and doesn't cache the resolved target in-process | Low after first proof |
| R2 | **In-flight writes during swap:** ingest driver writing concrete `v7` while alias moves → new points land on the de-served collection (silent divergence) | Med / High | G8 + G0-5: writer stopped before A1 and every B5. Writes always use concrete names, never the alias — document as invariant | Low with discipline; no lock exists — procedural only |
| R3 | **Exact-cache cold start on every rename:** key includes collection string; alias introduction + every swap flushes effective cache → p95 spike | Certain / Low-Med | Expected + planned (A5 soak, B6 warm-up). Never "fix" by sharing cache across names (would serve wrong-collection answers) | Accepted transient |
| R4 | **Premature predecessor delete kills R1:** cleanup before soak ends | Low / High | B7/B8 ordering (48h soak before delete), manager's protected-target + `keep_last_n>=1` enforcement; dry-run review mandatory | Low |
| R5 | **Calibration `collection` field vs alias:** today's profile has no `collection` key (safe). A future refit adding `collection: first_person_v7` while reads use `first_person` fails the prod release gate (`first_person_release.py:54-56`) and blocks startup | Low now / High later | Convention recorded here: refit profiles store the **alias name**. G7 checks it | Low with convention |
| R6 | **Backup gap:** FP not in default backup scope; snapshot-restore drill never run — R2/R3 paths unproven | Certain gap / High if R1 unavailable | G0-4 + B1 force per-cutover snapshots; follow-up: add FP to cron matrix + run `restore_drill.py --apply` on shadow (rec#8, still open) | Med until drill runs |
| R7 | **Full-snapshot alias semantics:** full-instance snapshots recreate aliases on restore — a careless full restore could move the alias unexpectedly | Low / Med | Prefer per-collection `recover_snapshot` + explicit B5-shaped alias set (R2), never full-instance restore for FP rollback | Low |
| R8 | **Single-node Qdrant:** no rolling-update HA; server restart during cutover = brief unavailability (blue-green cluster docs assume replication ≥2) | Low / Low-Med | Schedule A1/B5 outside peak; each op is ms-scale; health-probe before/after | Accepted |
| R9 | **Shadow-schema drift (rec#1 residue):** any tool bypassing `create_shadow_collection` (manual `init_collection`) reintroduces the old main-corpus index list | Low / Med | B2 mandates the manager path; G6 parity check catches drift before swap | Low |

## 7. Part A vs Part B sequencing note

Part A (alias introduction) can run **as soon as Gate 0 holds** — it changes no data, only the read path name, and is itself rollback-trivial (flip env back + recreate backend; alias delete is one call). Part B runs per reindex thereafter. Do NOT combine A1 with any data write (ingest, refit, index add) — one variable per cutover.

## 8. Step count / blockers (for handoff)

- **Part A: 6 steps** (create → parity-prove → env flip → restart → soak → record). **Part B: 8 steps** (snapshot → shadow → build → gate → swap → serve-verify → soak → cleanup). **Gate: 8 checks. Rollback: 3 paths.**
- **Riskiest step: B5 (atomic swap)** — not because the op is unsafe (single atomic transaction, ms) but because every procedural control (writer stopped, gate green, predecessor retained) converges there; a swap with a live writer (R2) is the only silent-divergence mode. Second: **A4 (restart)** — compose env-file re-evaluation gotcha is documented but remains the likeliest fumble.
- **Blockers (must clear before Step 1):** mass-ingest completion (running, hours); golden-25 post-ingest re-measure (pending ingest); FP backup-cron coverage + restore drill (rec#8, still open — G0-4/B1 work around it per-cutover but do not close it).

## 9. Implementation status (2026-10-04)

**Executed (ingest still running — writer live, backend container STOPPED):**

- **A1 DONE — alias created:** `first_person` → `first_person_v7` via single `create_alias` action (`POST /collections/aliases`, `{"result":true}`). Pre-state `GET /aliases` was `[]`; post-state `first_person -> first_person_v7`. Metadata-only op; writer uses concrete names so zero ingest impact. Ingest driver/log/state/workdir untouched.
- **A2 PARTIAL (counts + spot sample) — parity proven at point level:** exact `points/count` via concrete `first_person_v7` = **1343** vs via alias `first_person` = **1343** (equal, back-to-back calls). Scroll spot sample (`limit 3`, payload on): identical point IDs + `video_id` + text prefix on both paths (3/3 match). Collection `status: green`, `indexed_vectors_count: 1716` at check time. Count will grow as ingest continues — re-verify post-ingest. Full golden-25 `--collection first_person` parity run NOT done (backend stopped; harness needs backend env) — deferred to post-ingest.
- **A3 PREPARED, NOT executed — env flip:** file = repo-root `.env:165`, current `FIRST_PERSON_COLLECTION=first_person_v7` → change to `FIRST_PERSON_COLLECTION=first_person`. NOT applied (backend stopped for ingest; flip rides the L1 docker restore).

**Remaining (all post-ingest, owner-triggered):**

- Gate 0 in full (G0-1 ingest complete + reconcile 0 mismatches; G0-2 golden-25 re-measure; G0-3 backend up + `GET /aliases` still single entry; G0-4 fresh snapshot + record name; G0-5 writer quiesced).
- A2 remainder: golden-25 (or ≥5-question smoke) `--collection first_person` vs `--collection first_person_v7`, identical results.
- A3: apply the `.env:165` flip above (repeat per hosting target at deploy time).
- A4: `docker compose up -d --force-recreate backend` — compose bare `restart` does NOT re-evaluate env files, so `--force-recreate` is REQUIRED (plan §2 A4 + lessons `L-OPS`). Then verify `/api/health` 200 + first-person probe `coll=first_person`.
- A5 soak (24h) → A6 cutover log entry. Nothing deleted in Part A.
- Part B (B1–B8), pre-swap gate (G1–G8), rollback paths R1–R3: entirely post-ingest, none started.

## Sources

- Alias atomicity ("no concurrent requests affected; build second collection, switch alias"): https://qdrant.tech/documentation/manage-data/collections/ ; API atomic-actions contract: https://api.qdrant.tech/api-reference/aliases/update-aliases ; https://apis.io/apis/qdrant/qdrant-aliases-api
- Zero-downtime reindex pattern (new collection → verify → atomic swap → keep old for ms rollback): https://qdrant.tech/documentation/faq/qdrant-fundamentals ; https://computingforgeeks.com/qdrant-collections-guide ; ES-pattern rollback writeup (same atomic-swap semantics): https://www.mironsoft.de/en/blog/elasticsearch-zero-downtime-reindexing
- Blue-green Qdrant runbook (green load doesn't affect blue; rollback = config change while blue/snapshot exists; snapshot before decommission): https://qdrant.tech/documentation/tutorials-operations/blue-green-deployment
- Snapshots (per-collection create/download/`recover_snapshot` `priority=snapshot`; ~2× disk during restore; collection snapshots exclude aliases per community note — hence R7): https://qdrant.tech/documentation/snapshots/ ; https://qdrant.tech/documentation/tutorials-operations/create-snapshot/ ; https://qdrant.tech/documentation/migration-recovery-options ; https://qdrant-qdrant-18.mintlify.app/operations/backup-restore ; https://www.nextround.in/tech/Qdrant/Snapshots%20and%20Backups/what-is-a-qdrant-snapshot-and-what-two-purposes-does-it-commonly-serve-6aa50f044d169453ed9e08e3
- In-repo hooks cited inline: `backend/services/qdrant_aliases.py`, `backend/services/first_person_store.py:200-202`, `backend/app/api/first_person.py:214`, `backend/app/pipeline/stages/first_person_bridge.py:332,560`, `backend/app/config.py:159`, `backend/services/first_person_release.py:31-59`, `backend/config/first_person_calibration_v7.json`, `scripts/ops/qdrant_backup.py:56`, `docs/operations/drills.md`, `.github/workflows/golden25-gate.yml`, root `.env:157-165`
