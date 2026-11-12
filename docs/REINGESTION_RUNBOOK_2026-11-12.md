# Reingestion runbook — first-person corpus (verified 2026-11-12)

**Scope:** rebuild the first-person (fp-context-v1) corpus from a legacy clip
collection, end to end, with the span-boundary repair and the gate-rejection
ledger. Read-only rehearsal first; the apply step is owner-gated.

**Hard rules that this runbook does not weaken**

- `first_person` alias is **not** repointed by this runbook. Alias work is a
  separate, explicitly approved step (public release is still NO-GO, X5/X6).
- No `--apply` without a written owner approval, and never against the
  collection the alias already points at.
- Rights (`domain_rights_status == "licensed"`) come from the register via
  `video_rights_decision`, never from a payload claim (X40).
- `speaker_verified` is set **only** by a span-level ECAPA verdict (B1). A
  legacy clip label alone stays `False`.
- `--dry-run` writes nothing. It reports what it *would* reject under
  `report["rejections_not_persisted"]`.
- Nothing in this runbook turns on `FIRST_PERSON_CONTEXT_HARNESS_ENABLED`.

---

## 0. Preflight (2 minutes)

```bash
cd backend

# 0.1 Container is up and healthy, and the image matches the working tree
export PATH="/Users/harshodaikolluru/.docker/bin:$PATH"
docker compose ps backend --format '{{.Name}} {{.Status}}'
curl -s http://localhost:8000/api/health | python3 -m json.tool | head -20

# 0.2 Collections + alias (note the alias target before you touch anything)
docker compose exec -T backend python -c "
from qdrant_client import QdrantClient
c = QdrantClient(url='http://qdrant:6333')
print(c.get_aliases().aliases)
for n in sorted(x.name for x in c.get_collections().collections):
    if 'first_person' in n or 'fp_' in n:
        print(n, c.get_collection(n).points_count)
"

# 0.3 Query caches only — never FLUSHALL (ingestion state is separate)
cd .. && make flush-cache && cd backend
```

`backend/.venv/bin/python -m pytest tests/test_repo_layout.py tests/test_fp_context_builder_from_v9.py tests/test_fp_context_span_boundaries.py -q`
must be green before a build: it pins script-tree parity, the boundary repair
and the dry-run no-write contract.

---

## 1. (Optional) Raw ingestion layer — only when new source videos exist

The fp-context builder consumes a *legacy clip collection*; it does not fetch
YouTube. If new discourse must enter the corpus, ingest it first.

```bash
cd backend
.venv/bin/python scripts/ingestion/bulk_ingest_video.py --input /path/to/urls.txt --dry-run
.venv/bin/python scripts/ingestion/bulk_ingest_video.py --input /path/to/urls.txt --workers 2
```

Staleness invariant (X32): projected transcripts older than 30 days are
skipped and fall back to the live YouTube API — `touch` them first. Ingestion
uses `OpenRouterService` (`LLM_PROVIDER=openrouter`, `OLLAMA_CLOUD_ONLY=true`),
X33. All provider output must pass `find_artifact()` before it can reach Qdrant.

---

## 2. Rehearsal — dry run against the source collection (safe, no writes)

`--source-collection` must be a **legacy clip** collection (payload carries
`verbatim_text`, `start_ms`, `end_ms`, `speaker`/`teacher_id`, `video_id`).
`first_person_v10` / `first_person_v11` are fp-context collections and cannot
be used as a source. On this host the only legacy first-person collection is
`first_person_v8` (1,801 points); `first_person_v9` does not exist locally.

```bash
cd backend
export PATH="/Users/harshodaikolluru/.docker/bin:$PATH"

docker compose exec -T backend python /app/scripts/ops/build_fp_context_from_v9.py \
  --source-collection first_person_v8 \
  --target-collection fp_context_v1_20261112 \
  --qdrant-url http://qdrant:6333 \
  --transcripts-dir /app/transcripts \
  --dry-run \
  --manifest /tmp/fp_manifest.jsonl \
  --report /tmp/fp_report.json
```

Read the report before going further:

```bash
docker compose exec -T backend python -c "
import json; d = json.load(open('/tmp/fp_report.json'))
for k in ('total_source_points','derived_span_ids','parents','quarantined',
          'quarantine_reasons','release_grade_defects','quality_counters',
          'rejections_persisted','rejections_not_persisted'):
    print(k, '=', json.dumps(d.get(k)))
"
```

Expected shape on the current data (measured 2026-11-12):

```
total_source_points = 1801
derived_span_ids    = 573
parents             = 508
quarantined         = {"speaker_unverified": 1087, "rights_not_cleared": 49,
                       "incomplete_span_no_sentence_boundary": 21,
                       "clip_text_not_locatable": 18}
rejections_persisted= false        # dry run writes nothing
```

**Re-measured 2026-11-12 with B1 verdicts supplied** (first copied from
`docs/PRODUCT_OPPORTUNITIES.md:325`, then **reproduced exactly** by a dry run
against the rebuilt backend: `derived_span_ids` 1,425, `parents` 1,204,
`quarantined` = `clip_text_not_locatable` 48 + `incomplete_span_no_sentence_boundary` 51
+ `rights_not_cleared` 49 + `speaker_unverified` 6, `rejections_persisted=false`,
alias still `first_person -> first_person_v10`, no `fp_context_v1_2026*` collection created).

- Verdicts file: `/tmp/v8_speaker_verdicts.json` on the host (1,116 items, method
  `ecapa_voxceleb_span_slice_v2`, calibration `8daa5065…`), with the per-span rows
  in `/tmp/v8_span_verdicts.jsonl` and the inputs in `/tmp/v8_spans.jsonl`. **These
  live in `/tmp` and are volatile**; copy them somewhere durable before a real
  `--apply`. `.work/` is not mounted in the container, so the dry run read a
  `docker cp` copy at the container's `/tmp/v8_speaker_verdicts.json`.
- Not the old `.work/fp_context/speaker_verdicts.json` (6 entries, v9 build, October).
- Release-grade defects still reported by this dry run: `duration_out_of_band`
  **401**, `boundary_status_repaired_with_defects` **6**. The builder refuses
  `--apply` (I3) while a release-grade defect remains, so B1 and B5 are not the
  only things in the way of a real apply.

- B1 verdicts came from `regenerate_v10_span_ecapa_verdicts.py --spans-jsonl`
  (served-window mode), not `verify_speakers_ecapa.py` (that tool emits
  `ecapa_voxceleb_centroid_v1`, which the builder refuses by design, review D3).
  It scored the 1,116 previously-unverified v8 clips against the pinned anchor
  references (revision `0f99f2d0…`, calibration `8daa5065…`): **1,081 verified**,
  29 `missing_audio`, 5 `refused_below_cosine_floor`, 1 `refused_guru_mismatch`,
  0 schema failures.
- Builder dry run with those verdicts: `speaker_unverified` **1,087 → 6**,
  `derived_span_ids` **573 → 1,425**, `parents` **508 → 1,204**.
- B5 collapses to one video: all 49 `rights_not_cleared` clips come from
  `iKkySU5r_x8` (`status=unverified`, `reason=register_not_licensed`); the
  other 382 videos clear. Licensing that one entry recovers all 49.
- Remaining quarantine: `rights_not_cleared` 49, `clip_text_not_locatable` 48,
  `incomplete_span_no_sentence_boundary` 51, `speaker_unverified` 6.
- B7 (human gold labels) still needs the owner.

**Stop conditions — do not `--apply` while any of these hold**

| Counter | Meaning | Owner asset needed |
|---|---|---|
| `speaker_unverified` (1,087 without verdicts; 6 with the 2026-11-12 verdicts) | no span-level ECAPA verdict for these clips | `--speaker-verdicts` JSON from `regenerate_v10_span_ecapa_verdicts --spans-jsonl` (B1); not `verify_speakers_ecapa` |
| `rights_not_cleared` (49, all from `iKkySU5r_x8`) | register does not admit the source | `docs/rights/CONTENT-RIGHTS.md` + `source_releases` entry for `iKkySU5r_x8` (B5). A real `--apply` is blocked on this one rights row, not on code |
| `incomplete_span_no_sentence_boundary` (21 without verdicts; 51 in the 2026-11-12 re-measure) | repair could not snap the span | human review packet; these are already recorded as candidates |
| `clip_text_not_locatable` (18 without verdicts; 48 in the 2026-11-12 re-measure) | alignment < 0.85 against the transcript | needs ASR word timings (`--asr-dir`, `--asr-model large-v3`) |

With verdicts supplied the same command gains `--speaker-verdicts <json>`.
Never hand-edit a verdict file to raise the verified count.

---

## 3. Apply (owner approval required) — new collection only

```bash
# APPROVED-BY: <name> <date>   (record it in the task file before running)
docker compose exec -T backend python /app/scripts/ops/build_fp_context_from_v9.py \
  --source-collection first_person_v8 \
  --target-collection fp_context_v1_20261112 \
  --qdrant-url http://qdrant:6333 \
  --transcripts-dir /app/transcripts \
  --speaker-verdicts /app/.work/fp_context/speaker_verdicts.json \
  --asr-dir /app/asr \
  --apply
```

`--apply` here creates a **new** collection. Do not pass `--recreate` unless the
goal is to destroy an existing target. The builder refuses (I3) before creating
anything when a release-grade defect remains.

---

## 4. Verify the new collection (all three, in order)

```bash
# 4.1 Span-boundary + rights residue; --check exits 1 on a blocker
docker compose exec -T backend python -m scripts.ops.audit_fp_context_span_boundaries \
  --collection fp_context_v1_20261112 --url http://qdrant:6333 --check \
  --out /tmp/span_audit.json

# 4.2 Strict contract audit (ids, hashes, topology, rights)
docker compose exec -T backend python /app/scripts/ops/audit_first_person_v10_strict.py \
  --qdrant-url http://qdrant:6333 --collection fp_context_v1_20261112

# 4.3 Candidate validator (needs the manifests)
.venv/bin/python scripts/ops/validate_fp_context_candidate.py \
  --source-spans /tmp/fp_manifest.jsonl \
  --asr-manifest  .work/fp_context/asr_manifest.json \
  --rights-manifest .work/fp_context/rights_manifest.json \
  --speaker-manifest .work/fp_context/speaker_manifest.json \
  --candidate-out /tmp/fp_candidates.jsonl \
  --quarantine-out /tmp/fp_quarantine.jsonl
```

Then a serving smoke against the **new** collection without touching the alias:

```bash
# FIRST_PERSON_COLLECTION is a project .env value (backend/.env) — X25
docker compose exec -T backend env FIRST_PERSON_COLLECTION=fp_context_v1_20261112 \
  python -c "import asyncio; print('smoke: point the pipeline at the new collection explicitly')"
```

---

## 5. Alias flip — separate approval, not part of reingestion

Only after §4 is green **and** the owner approves:

1. record the current alias target (`first_person -> first_person_v10`);
2. `PUT /collections/<alias>` to the new collection (no delete of the old one);
3. re-create the backend (`docker compose up -d --no-deps --force-recreate backend`,
   `restart` never re-reads `env_file`);
4. smoke one doctrine query and one abstain query;
5. roll the alias back by re-pointing it if either smoke regresses.

The public-release verdict stays **NO-GO** while B1/B5/B7 are open
(`docs/FIRST_PERSON_PUBLIC_RELEASE_STATUS_2026-10-21.md`). Aliasing a better
corpus does not close those defects.

---

## 6. What this runbook deliberately does not do

- It does not run the 675-question graded benchmark (explicit authorisation
  required).
- It does not `FLUSHALL`, drop a collection, or mutate Neo4j.
- It does not write `speaker_verified=true` for a clip that has no verdict.
- It does not clear or rewrite the 3,088 historical
  `corpus_gate_rejections` rows produced by pre-fix dry runs
  (`gate_layer='fp_context_builder_v9'`); they are audit history and their
  cleanup is a separate, approved decision.
