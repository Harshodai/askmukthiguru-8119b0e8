# First-Person v5/v10 — Phase 0 reconciliation (2026-10-21)

Read-only snapshot taken before any mutation of source, Qdrant, aliases or env.
Machine-readable companion: `audits/evidence/phase0_state_2026-10-21.json`
(produced by `backend/scripts/ops/capture_first_person_state.py`).

## Git identity

| Item | Value |
|---|---|
| `HEAD` | `6183326ff1de430d23e587a9d05a8bca4acd7a2f` |
| `origin/main` | `6183326ff1de430d23e587a9d05a8bca4acd7a2f` |
| Branch | `main` (up to date with origin) |
| Remote | `https://github.com/Harshodai/askmukthiguru-8119b0e8.git` |
| Dirty entries | 224 (modified + untracked), incl. 19 untracked first-person source/test files |
| Worktrees | none created by this session |

The tree was already dirty when this run started (peer work: first-person
harness, store, selector, domain models, builders, auditors, tests, docs). No
file was reset, cleaned, checked out or discarded.

## Docker runtime

| Item | Value |
|---|---|
| Docker binary | `/Users/harshodaikolluru/.docker/bin/docker` |
| Context | `desktop-linux` |
| Backend image | `backend-backend:latest` `57f07e071de5` created `2026-10-21T08:29:04Z` |
| Backend container | started `2026-10-21T09:38:40Z` (recreated during this run) |
| Qdrant | `qdrant/qdrant:v1.18.0`, healthy, `localhost:6333` |
| Redis | `redis:7-alpine`, healthy, password-protected |
| Memgraph | `memgraph/memgraph-mage:latest`, healthy |
| Supabase | 8 services up (separate compose project, untouched) |

Serving code identity was verified by hashing the in-container files against the
worktree: `app/config.py`, `app/pipeline/stages/first_person_bridge.py`,
`services/first_person_pipeline.py`, `services/first_person_context_*.py` and
`domain/first_person_context.py` were byte-identical. `backend/scripts/` is
**not** bind-mounted (`L-OPS-MOUNT-1`), so `scripts.ops.*` imports failed inside
the image — see the defect log.

## First-person environment

`backend/.env` is the compose project env (`--project-directory backend`), so
its values win the `${VAR:-default}` interpolation in `docker-compose.yml`.
The repo-root `.env` is a secondary `env_file` and is overridden for every key
the compose `environment:` block lists.

| Variable | `backend/.env` | In container |
|---|---|---|
| `FIRST_PERSON_CONTEXT_HARNESS_ENABLED` | **true** | **true** |
| `FIRST_PERSON_COLLECTION` | `first_person_v10` | `first_person_v10` |
| `FIRST_PERSON_CONTEXT_COLLECTION` | `first_person_v10` | `first_person_v10` |
| `FIRST_PERSON_MODE` | (unset) | `retrieval_only` (compose default) |
| `FIRST_PERSON_RELEVANCE_MIN_SCORE` | `2` | `2` |
| `FIRST_PERSON_RELEVANCE_MODEL` | (root `.env`) | `anthropic/claude-haiku-5.5` |
| `FIRST_PERSON_DISTRESS_SERVE_CLIP_ENABLED` | `true` | `true` |

**The harness was already enabled when this run started.** `backend/.env` mtime
`2026-10-21T15:08:23 IST`; the backend container was recreated 12 s later
(`15:08:36`). The evidence file
`audits/evidence/first_person_phase_status_2026-10-20.md` (15:02) still says
"Serving is confirmed disabled in both `backend/.env` and the running backend",
so the enablement happened after that snapshot and was never re-verified. No
post-enable health, correctness, load, metric or rollback proof existed.

## Qdrant census (before)

```
alias first_person -> first_person_v10
first_person_v10: 4197 points (2737 retrieval_child + 1460 parent_unit)
  vectors: passage_dense (1024, Cosine) + passage_sparse
  payload indexes: record_type, guru_id, video_id, parent_unit_id,
                   source_span_id, rights_cleared, speaker_verified
  status green, optimizer ok, indexed_vectors_count 2737
```

Legacy `first_person_v1..v9`, `first_person_v8_shrunk_20261018`,
`first_person_v9_pilot` and `fp_context_v1_local` had already been purged
(2026-10-21), with snapshots retained under
`/qdrant/snapshots/{first_person_v7,v8,v9,fp_context_v1_local}`.

**Stale pointer found:** the repo-root `.env` still says
`FIRST_PERSON_COLLECTION=first_person_v9` — a purged collection. It is
currently masked by the compose `environment:` block, so it is latent, but it
is a footgun for any invocation whose project directory is the repository root.

## Collection payload census (before)

Every `retrieval_child` in `first_person_v10` carries
`asr_engine=parakeet_mlx`, `asr_model_version=parakeet-tdt-0.6b-v3`,
`rights_cleared=true`, `speaker_verified=true`,
`voice_verification_method=ecapa_voxceleb_centroid_v1`. The `asr_*` fields
were added by an additive enrichment between the 14:49 readiness audit (which
reported them missing on 2,737/2,737 points) and the 15:08 container recreate.

## Backend posture at start

```
Serving posture: faculty_gate=OFF first_person(route=True bridge=True
collection=first_person_v10 fallback=False weak_match=True min_score=2
model=anthropic/claude-haiku-5.5)
```

## Working-tree hygiene

- `scripts/ingestion/` deletions reported by AGENTS.md are **not** present in
  the current tree (224 dirty entries, all modifications/additions).
- `backend/scripts/ingestion/` exists as untracked peer work.
- No temporary worktree was created by this run; `git worktree prune` was
  executed at the end.
