# Corpus Rebuild Plan — full audit, re-ingest, and knowledge-layer rebuild

**Written** 2026-08-03. **Audience:** whoever picks this up next, including a fresh
Claude session with no memory of how we got here.

Read [`handoff.md`](../../handoff.md) (Round 3) and `lessons.md` (L-CORRUPT-1..18)
before executing. This file is the *plan*; those two are the *why*.

---

## 0. The finding that reframes everything

The migration strategy this project has been pursuing — copy `spiritual_wisdom`
into `spiritual_wisdom_contextual`, re-chunking as you go — **can only ever
salvage 3.5% of the corpus.**

Measured 2026-08-03 against the live blue collection (89,061 chunks, 720 sources):

| verdict | sources | chunks | share of corpus |
|---|---|---|---|
| `REFETCH_FROM_ORIGIN` | 232 | 70,041 | **78.6%** |
| `MIGRATE_THEN_VERIFY` | 49 | 15,915 | 17.9% |
| `MIGRATE` | 439 | 3,105 | **3.5%** |

The 439 "migratable" sources are migratable *because they are nearly empty* —
they average 4.3 chunks each. Every large source is contaminated. The single
biggest source in the corpus (`o_eg6YTifRE`, 2,494 chunks) is 50.7% poisoned.

Re-chunking **amplifies** contamination rather than diluting it — measured on one
real source, 46.4% → 98.8%, because a repetition loop that occupied part of one
old chunk gets redistributed across many new ones. So migrating the contaminated
78.6% does not produce a smaller mess; it produces a bigger one.

**Therefore: this is not a migration. It is a re-ingest from origin.**

719 of the 720 sources are YouTube videos. The one non-YouTube source is the book
(1,196 chunks, `MIGRATE`). So "re-ingest from origin" concretely means
**re-transcribe 719 YouTube videos through the current 4-tier pipeline** — which
is exactly what the pipeline was built for, and what the book pilot proved works.

> **Do not** spend another session tuning the migration path. It is the wrong tool.
> `contextual_reingest.py` remains correct and useful — for the book, and as the
> chunk/embed/upsert engine the re-ingest calls into. Its *source* should be a
> fresh transcript, not a blue-collection payload.

---

## 1. What is already done (do not redo)

| thing | state | evidence |
|---|---|---|
| Book pilot | **done** — 25/25 sections, 451 chunks in green | `spiritual_wisdom_contextual` = 453 points |
| Section-aware chunking | **done** — chunks never straddle a section | `test_contextual_reingest.py` |
| Parent–child rebuild | **done** — parents 2,000–6,000 chars, deterministic ids | `_build_parents` |
| Per-chunk provenance | **done** — 23 distinct page ranges on the real PDF | `_origin_index_map` |
| Uniform pooling | **done** — mean-pooled throughout; raises on mixed | `_ingest_unit` |
| Per-section incremental writes + resume | **done** | `_STATE_KEY_SECTIONS` |
| Doctrine lexicon | **done** — replaces the hand-typed lists | `services/doctrine_lexicon.py` |
| `apply_corrections` routed through it | **done** 2026-08-03 | `test_doctrine_terms.py` |
| Thread saturation | **done** — `OMP_NUM_THREADS`/`MKL_NUM_THREADS` set | 125% → 720% CPU |

The lexicon ships at **100% measured precision**: 12,000 random live chunks,
0.117% changed, 12 distinct rules, all 12 correct. `Ujash`/`Ujasi`/`Ojasi`/`UJASH`
→ `Ojas`; `peace`, `piece`, `soar`, `steel`, `bodhi`, `citta` untouched.

---

## 2. The plan

### Phase A — decide the scope (30 min, human)

This is the only genuinely blocking decision, because it sets the budget.

**Option A1 — re-ingest all 719 videos.** Clean corpus, no asterisks. Costs
719 × (download + Whisper + contextualise + embed). At the book pilot's measured
rate this is the multi-day, few-hundred-dollar option. Choose if the corpus is
the product.

**Option A2 — re-ingest the top 281 (`REFETCH` + `MIGRATE_THEN_VERIFY`), keep the
439 tiny clean ones as-is.** Recovers 96.5% of the chunk mass for 39% of the
sources. The 439 stragglers migrate cheaply afterwards. **Recommended.**

**Option A3 — re-ingest the top 50 by chunk count.** ~35,000 chunks, roughly 40%
of the corpus, in a day. Choose to get a demonstrably clean corpus fast and defer
the long tail.

Whichever you pick, write it at the top of `handoff.md` so the next session does
not re-litigate it.

### Phase B — prove the re-ingest path on one video (1 hour)

Do not start a 700-video run without this. The book pilot proved the *book* path;
the YouTube path has a different first mile (yt-dlp → ffmpeg → Whisper →
polisher) and has never been run end-to-end under the new chunker.

```bash
cd backend
docker compose up -d qdrant redis neo4j
```

```bash
docker run --rm --network backend_default -v "$PWD:/app" -w /app -e PYTHONDONTWRITEBYTECODE=1 -e OMP_NUM_THREADS=10 -e MKL_NUM_THREADS=10 --entrypoint python backend-backend -u run_pilot.py "https://www.youtube.com/watch?v=o_eg6YTifRE"
```

`--entrypoint python` is **not optional**. The image sets
`ENTRYPOINT ["/app/docker-entrypoint.sh"]`, which swallows the command and starts
uvicorn instead — the container then reports healthy for as long as you let it
while your script never runs. This cost 11 minutes once (L-CORRUPT-14).

**Gates that must all pass before Phase C:**

1. Chunk spans located: `len(spans) == len(chunks)`, not 0. Late chunking is the
   entire justification for the re-ingest and it fails *silently* when spans
   don't resolve — every other gate still reports success (L-CORRUPT-13).
2. Coverage ≥85% of source characters survive each stage boundary.
3. Contamination of the new chunks <2% by `corpus_forensics`.
4. Per-chunk provenance varies — more than one distinct `page_range`/`title`.
5. Pooling mode uniform (it raises otherwise, so this is free).

### Phase C — the run

Generate the target list from the audit rather than by hand:

```bash
.venv/bin/python -m scripts.ops.corpus_forensics feasibility --url http://localhost:6333 --json data/feasibility.json
```

```bash
python3 -c "
import json
rows = json.load(open('data/feasibility.json'))['sources']
keep = {'REFETCH_FROM_ORIGIN', 'MIGRATE_THEN_VERIFY'}   # Option A2
rows = [r for r in rows if r['verdict'] in keep]
rows.sort(key=lambda r: -r['chunks'])                    # biggest first, fail fast
open('data/refetch_targets.txt','w').write('\n'.join(r['source_url'] for r in rows))
print(len(rows), 'targets', sum(r['chunks'] for r in rows), 'chunks replaced')
"
```

Biggest-first ordering matters: if the pipeline is going to break on something,
it breaks in the first ten minutes rather than after two days of small videos.

```bash
docker run -d --name reingest --network backend_default -v "$PWD:/app" -w /app -e PYTHONDONTWRITEBYTECODE=1 -e OMP_NUM_THREADS=10 -e MKL_NUM_THREADS=10 --entrypoint python backend-backend -u run_pilot.py --from-file /app/data/refetch_targets.txt
```

The run is resumable — kill it and re-run; it picks up from
`scripts/ingestion/ingestion_state.json`.

**Monitor, don't babysit.** Check every few hours:

```bash
docker logs --tail 50 reingest
```

```bash
curl -s localhost:6333/collections/spiritual_wisdom_contextual | python3 -c "import json,sys; print(json.load(sys.stdin)['result']['points_count'])"
```

### Phase D — verify green before anything reads from it

```bash
.venv/bin/python -m scripts.ops.corpus_forensics forensic --collection spiritual_wisdom_contextual --url http://localhost:6333
```

Ship gates: contamination <2%, no source at 100%, parent–child present on >95% of
chunks, provenance varied, dimension matches `settings.embedding_dimension`.

Only after this passes: flip `QDRANT_COLLECTION=spiritual_wisdom_contextual`,
restart, and run `benchmarks/RUN_ME.sh`.

> **Keep blue.** Do not delete `spiritual_wisdom` until green has served real
> traffic for a week. It is 89k chunks of contaminated text, but it is also the
> only copy of anything the re-ingest fails to recover.

### Phase E — rebuild the knowledge layers *from the corrected text*

This is the part of the original goal that is still entirely untouched, and the
ordering is not arbitrary — each layer reads the one before it.

```
green Qdrant (clean) → Neo4j + LightRAG → ontology → OKF staging → review → compile
```

1. **Neo4j + LightRAG — delete and rebuild, do not patch.** Measured 41.4%
   contaminated. They were built by extracting entities from poisoned text, so
   every repetition-loop artifact became a node. `scripts/ops/heal_neo4j_poison.py`
   is a scalpel for a problem that needs a reset.

2. **Ontology** — re-run the seeder against the rebuilt graph. Baseline to beat:
   11,136 relationships / 7,512 nodes (verified 2026-07-10). Materially fewer
   means the re-ingest lost content; materially more is fine.

3. **OKF** — re-extract, then **review**. This is where the discipline has to hold.

```bash
.venv/bin/python -m scripts.extract_okf_from_stores --all --dry-run
```

```bash
.venv/bin/python -m scripts.extract_okf_from_stores --all --limit 20
```

**Never pass `--auto-approve` on a bulk run.** Entries in `memory/okf/` are
injected *verbatim* into answers as doctrine. Auto-extracted entries are
unreviewed by definition. Approval is an editorial act performed by a human who
knows the teachings — not a formality, and not something to delegate to the model
that wrote them.

After approval: `.venv/bin/python -m scripts.okf_compile`, **then restart the
backend** — `_OKF_CACHE` in `rag/nodes/retrieval.py` is per-process.

---

## 3. Standing constraints

- **Docker only** for the local stack. **Never** `docker compose down -v` — it
  destroys the Qdrant volume, and blue is the only copy of the un-recovered text.
- **Never deploy to Railway** as part of this work.
- **Never** `git stash` with uncommitted work in the tree. It reverted an hour of
  edits on 2026-08-03; recovered via `git stash pop`, but only by noticing in time.
- Secrets stay in env vars. Only `backend/.env.example` is committed.
- Dependencies must be OSS (Apache-2.0 / MIT / Meta Community). No
  `chonkie[coref]` (CC BY-NC-SA), no `[parsing]` (AGPL).
- **The OpenRouter key printed to a 2026-08-02 transcript is still unrotated.**
  Rotate at <https://openrouter.ai/keys>. This is the only item here with a
  security clock on it.

---

## 4. Known-open, not blocking

- **recall@k is still unmeasurable.** Only 1 of the 68 golden queries references a
  source that is actually loaded. Until the re-ingest lands, any retrieval-quality
  number quoted about this corpus is unsupported. Fix by regenerating the golden
  set *from* the green corpus once Phase D passes.
- **34 config fields are read by nothing.** Notably `csrf_secret` /
  `csrf_token_ttl` (working helpers in `security_utils.py`, zero callers) and
  `auth_rate_limit_per_ip` / `_per_account` / `_burst`. Each is either a missing
  feature or dead weight; decide per field, don't bulk-delete.
- **`tests/test_qdrant_embedded_mode.py`** needs a live local Qdrant and is slow
  (~3 min). Not part of the fast suite.

---

## 5. The four lessons most likely to be re-learned

Full list in `lessons.md`. These are the ones that cost the most:

1. **A silent success is worse than a loud failure.** `_chunk_spans` located 0 of 2
   spans for weeks while every gate reported green, because it matched literally
   against text whose whitespace had been normalised. Assert the *count*, not the
   absence of an exception.
2. **Similarity cannot separate a real error from a real word — coverage can.**
   `piece`/`peace` scores 0.880; `ujash`/`ojas` scores 0.783. No threshold exists.
   The fix was a 193k-word vocabulary, not a better metric.
3. **Repetition is not evidence when the errors share a cause.** `akam` reached 26
   independent sources and 401 uses purely because Whisper fails the same way every
   time. Consensus admitted it as "authority" until dominance-ratio gating stopped it.
4. **Your trusted source is also dirty.** The book is 0% contaminated *and* full of
   OCR fragments (`ealth`, `ense`). Rank sources by which failure mode it is free
   of, never by prestige.
