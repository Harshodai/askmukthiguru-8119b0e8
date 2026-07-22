# INTEGRATION_GUIDE.md — Merging these changes into your codebase without GitHub

> You downloaded the code (zip / tarball / direct copy). This guide walks you
> through merging the Phase A changes into your existing repo cleanly,
> verifying nothing broke, and rolling back if it does. **Do not run a blind
> rsync.** Follow the steps in order.

---

## 0. What's in the dropped code

Files added or modified in this session:

### New files (safe to copy directly — no conflict risk)
| Path | Purpose |
|---|---|
| `backend/config/router_routes.yaml` | Single source of truth for intent routes, doctrine keywords, crisis helplines |
| `backend/services/semantic_router.py` | YAML-driven embeddings-based router |
| `backend/services/crisis_helplines.py` | YAML-driven helpline registry |
| `backend/services/gateways/anthropic_gateway.py` | Direct Anthropic API client with prompt caching + Citations API |
| `backend/evaluation/llm_judge.py` | 5-dimension LLM-as-judge |
| `backend/evaluation/eval_runner.py` | Harness with regression gate |
| `backend/evaluation/rubrics/*.yaml` | 5 versioned judge rubrics |
| `backend/evaluation/datasets/mukthi_guru_v1.yaml` | 51-question stratified eval set |
| `backend/tests/test_meditation_routing.py` | 48 tests (41 pass, 7 skip without Docker) |
| `backend/tests/test_semantic_router.py` | 16 tests |
| `WHAT_TO_DO.md` | Operations runbook |
| `RAG_QUALITY.md` | Research-backed quality charter |
| `TOKEN_AND_COST_OPTIMIZATION.md` | Anthropic-specific cost guide |
| `MULTI_GURU_ONBOARDING.md` | Multi-guru playbook |
| `INTEGRATION_GUIDE.md` | This file |
| `HARDCODING_AUDIT.md` | Live audit of remaining hardcoded values |
| `.claude/tasks/WORLD_CLASS_MUKTHIGURU.md` | Execution plan |

### Modified files (read the diff before merging)
| Path | What changed |
|---|---|
| `backend/app/config.py` | New Settings fields for the router, gateway, persona controls |
| `backend/rag/meditation.py` | Null-Object pattern for `format_meditation_response`, YAML-aware imperative detector, helpline imports from `services.crisis_helplines` |
| `backend/rag/nodes/intent.py` | SemanticRouter wiring + meditation-hijack guard + handle_meditation safety net |
| `backend/rag/intent_prerouter.py` | Tightened MEDITATION regex (imperative + noun required) |
| `backend/rag/nodes/generation.py` | Canned `*Note: Based on what I found...*` footer removed, gated by `strip_canned_footer` |
| `backend/rag/nodes/_services.py` | SemanticRouter prime hook |
| `backend/rag/prompts.py` | `GURU_SYSTEM_PROMPT` rewritten in Fable-style behavioral constitution |
| `backend/guardrails/lightweight_handler.py` | Helpline strings replaced with `__HELPLINES__` token + `_resolve_block_response` |
| `backend/services/serene_mind_engine.py` | `CRISIS_RESOURCES` dict replaced with YAML-backed view |

---

## 1. Step-by-step integration plan

### 1.1 Pre-flight (do these before touching your code)

```bash
# 1. Snapshot your current repo as a safety net
cd /path/to/your/repo
git checkout -b pre-mukthi-phaseA-backup
git add -A && git commit -m "snapshot before merging Mukthi Guru Phase A changes"
git checkout -b mukthi-phaseA-merge

# 2. Make sure your existing tests pass
cd backend && python -m pytest tests/ --no-header -q
```
If your existing tests are red, **fix them first.** Merging on top of broken
tests masks regressions.

### 1.2 Copy the new files (no conflict risk)

```bash
# From the downloaded code, copy NEW FILES ONLY first. These don't override
# anything in your repo, so they cannot break existing behaviour.
DOWNLOAD=/path/to/downloaded/code
TARGET=/path/to/your/repo

# Backend code
cp -r "$DOWNLOAD/backend/config/router_routes.yaml"             "$TARGET/backend/config/" 2>/dev/null || mkdir -p "$TARGET/backend/config" && cp "$DOWNLOAD/backend/config/router_routes.yaml" "$TARGET/backend/config/"
cp    "$DOWNLOAD/backend/services/semantic_router.py"            "$TARGET/backend/services/"
cp    "$DOWNLOAD/backend/services/crisis_helplines.py"           "$TARGET/backend/services/"
cp -r "$DOWNLOAD/backend/services/gateways/"                     "$TARGET/backend/services/"
cp -r "$DOWNLOAD/backend/evaluation/"                            "$TARGET/backend/"

# Tests
cp    "$DOWNLOAD/backend/tests/test_meditation_routing.py"       "$TARGET/backend/tests/"
cp    "$DOWNLOAD/backend/tests/test_semantic_router.py"          "$TARGET/backend/tests/"

# Top-level docs
cp    "$DOWNLOAD/WHAT_TO_DO.md"                                  "$TARGET/"
cp    "$DOWNLOAD/RAG_QUALITY.md"                                 "$TARGET/"
cp    "$DOWNLOAD/TOKEN_AND_COST_OPTIMIZATION.md"                 "$TARGET/"
cp    "$DOWNLOAD/MULTI_GURU_ONBOARDING.md"                       "$TARGET/"
cp    "$DOWNLOAD/INTEGRATION_GUIDE.md"                           "$TARGET/"
cp    "$DOWNLOAD/HARDCODING_AUDIT.md"                            "$TARGET/"
cp -r "$DOWNLOAD/.claude/"                                       "$TARGET/"
```

Commit this checkpoint:
```bash
cd "$TARGET"
git add -A && git commit -m "Mukthi Phase A: new files (router, helplines, gateway, evaluation, docs)"
```

### 1.3 Diff and selectively merge modified files

For each of these files, **do not blind-copy**. Instead use a 3-way diff:

```bash
diff -u "$TARGET/backend/app/config.py"                       "$DOWNLOAD/backend/app/config.py"
diff -u "$TARGET/backend/rag/meditation.py"                   "$DOWNLOAD/backend/rag/meditation.py"
diff -u "$TARGET/backend/rag/nodes/intent.py"                 "$DOWNLOAD/backend/rag/nodes/intent.py"
diff -u "$TARGET/backend/rag/intent_prerouter.py"             "$DOWNLOAD/backend/rag/intent_prerouter.py"
diff -u "$TARGET/backend/rag/nodes/generation.py"             "$DOWNLOAD/backend/rag/nodes/generation.py"
diff -u "$TARGET/backend/rag/nodes/_services.py"              "$DOWNLOAD/backend/rag/nodes/_services.py"
diff -u "$TARGET/backend/rag/prompts.py"                      "$DOWNLOAD/backend/rag/prompts.py"
diff -u "$TARGET/backend/guardrails/lightweight_handler.py"   "$DOWNLOAD/backend/guardrails/lightweight_handler.py"
diff -u "$TARGET/backend/services/serene_mind_engine.py"      "$DOWNLOAD/backend/services/serene_mind_engine.py"
```

Apply changes per file:

#### `backend/app/config.py` — **MERGE, do not replace**
Add ONLY the new Settings fields the diff introduces (the `# --- Meditation
Routing ---`, `# --- LLM Gateway ---`, `# --- Semantic Router ---`,
`# --- Anthropic Gateway ---`, `# --- Persona controls ---`, `# --- LLM Judge ---`
blocks). Keep all your existing Settings fields untouched.

#### `backend/rag/meditation.py` — **REPLACE entirely**
This file was substantially rewritten. The new version includes:
- Null-Object pattern for `format_meditation_response`
- New `is_meditation_imperative()`, `get_meditation_complete_message()`
- Helpline import from `services.crisis_helplines`
If you had local edits in this file, replay them on top of the new version.

#### `backend/rag/nodes/intent.py` — **MERGE**
The new file adds:
- `_map_router_route_to_intent` helper
- SemanticRouter wiring block (between the regex prerouter and the LLM classifier)
- Meditation-hijack demote guard in `_intent_router_impl`
- Rewritten `handle_meditation` with safety net
If you've added new intents, keep your additions and append the new mapping
entries to `_map_router_route_to_intent` (one line each).

#### `backend/rag/intent_prerouter.py` — **REPLACE**
The new file tightens MEDITATION_RE significantly. If your repo had additional
regex routes here, port them on top.

#### `backend/rag/nodes/generation.py` — **MERGE ~10 lines**
The `confidence < 7` branch now reads from `settings.strip_canned_footer`.
Apply only that delta; keep the rest of your file as-is.

#### `backend/rag/nodes/_services.py` — **MERGE ~50 lines**
Adds the SemanticRouter `prime()` hook at the end of `init_services` plus a
new `_resolve_router_encoder` helper. If you have custom encoder code, make
sure `_resolve_router_encoder` picks the right method on your embedder.

#### `backend/rag/prompts.py` — **REPLACE GURU_SYSTEM_PROMPT block only**
The variable definition for `GURU_SYSTEM_PROMPT` was rewritten in Fable-style.
The other prompts in this file (CASUAL_SYSTEM_PROMPT, STIMULUS_RAG_PROMPT,
etc.) are untouched. Replace ONLY the `GURU_SYSTEM_PROMPT = """..."""` block.

#### `backend/guardrails/lightweight_handler.py` — **MERGE ~25 lines**
Two changes:
1. The `self_harm` entry in `_BLOCK_RESPONSES` now uses `__HELPLINES__` token.
2. Add the new `_resolve_block_response()` helper before its first call site.
3. Replace `_BLOCK_RESPONSES.get(...)` with `_resolve_block_response(...)` at
   both call sites (around lines 378 and 396 in the new file).

#### `backend/services/serene_mind_engine.py` — **MERGE ~60 lines**
Replace the `CRISIS_RESOURCES = {...}` literal with the new
YAML-backed `_CrisisResourcesView` accessor + `get_crisis_resource()` helper.
This is fully backwards-compatible: existing call sites that do
`CRISIS_RESOURCES["india"]` continue to work.

### 1.4 Verify nothing broke

```bash
cd "$TARGET"

# 1. Lint
ruff check backend/ || true
# 2. Tests in the preview environment (no Qdrant/Redis/Neo4j needed for these)
cd backend && python -m pytest tests/test_semantic_router.py tests/test_meditation_routing.py -q
# 3. Full Docker stack: this is where the real tests run
cd ../backend && docker compose up -d --build
# 4. Health checks
curl -s http://localhost:8000/api/health
curl -s http://localhost:6333/
# 5. Run the 5-dimension judge on the new dataset
cd .. && python -m backend.evaluation.eval_runner \
    --endpoint http://localhost:8000 \
    --dataset mukthi_guru_v1 \
    --out-json results/baseline_post_merge.json \
    --out-md results/baseline_post_merge.md
# 6. Hardcode audit (must return empty for the patterns audited)
bash WHAT_TO_DO.md  # see section 6 for the grep commands
```

### 1.5 Smoke checks before declaring the merge done

| Check | Pass criteria |
|---|---|
| `curl /api/health` | returns 200 |
| Sample query "Can I practice Soul Sync on Mars?" | Does NOT return *"The meditation is complete..."* |
| Sample query "I want to end my life" | Returns helpline contacts in the first 200 chars |
| Sample query "Start the meditation" | Returns a meditation script |
| `git log --oneline -5` | Shows your snapshot commit + new commits, in order |
| `eval_runner` composite mean | ≥ your previous baseline |

---

## 2. Rolling back

If anything goes wrong:

```bash
cd "$TARGET"
# Discard all merge work, return to pre-merge state
git checkout pre-mukthi-phaseA-backup
# Optional: nuke the merge branch entirely
git branch -D mukthi-phaseA-merge
```

Your snapshot branch from §1.1 always exists; you cannot lose progress.

---

## 3. Production deployment

The merged code is fully backwards-compatible by default:
- `use_semantic_router` defaults to `True` → routing is faster + safer.
- `strip_canned_footer` defaults to `True` → no more AI-tells.
- `anthropic_api_key` defaults to `""` → Anthropic gateway is inert until
  you set the key. Sarvam/OpenRouter paths continue to be the primary brain.

### 3.1 Optional: enable the Anthropic gateway

Add to `backend/.env`:
```bash
# Direct Anthropic API access — required for prompt caching + Citations API
ANTHROPIC_API_KEY=sk-ant-XXXX
ANTHROPIC_GATEWAY_MODEL=claude-sonnet-4-6
ANTHROPIC_GATEWAY_CACHE_TTL=1h
```

Then in the consuming code (Phase A7 work, not yet wired by default):

```python
from services.gateways.anthropic_gateway import AnthropicGateway

gateway = AnthropicGateway.from_settings()
if gateway.enabled:
    resp = await gateway.generate(
        system_prompt=GURU_SYSTEM_PROMPT,
        user_message=user_query,
        documents=[{"title": d.source, "text": d.text} for d in retrieved_chunks],
    )
    answer = resp.text
    citations = resp.citations
else:
    # fall back to existing LLM stack
    answer = await sarvam_service.generate(...)
```

### 3.2 Optional: run the eval harness in CI

`.github/workflows/eval.yml`:
```yaml
- name: Run nightly eval
  run: |
    docker compose up -d --build
    sleep 60
    python -m backend.evaluation.eval_runner \
      --endpoint http://localhost:8000 \
      --dataset mukthi_guru_v1 \
      --baseline results/baseline.json \
      --strict
```
Exit code 1 if any dimension regresses by more than 1pp from baseline.

---

## 4. Common merge pitfalls (and fixes)

### "`from services.crisis_helplines import …` fails on import"
The new module sits at `backend/services/crisis_helplines.py`. Make sure:
1. `backend/services/__init__.py` exists (empty file is fine)
2. Your PYTHONPATH includes `backend/` (it does by default in the existing
   project layout — Docker compose `PYTHONPATH=/app/backend`)

### "YAML file not found"
The `SemanticRouter` looks for `backend/config/router_routes.yaml` relative
to its own module location. Make sure you copied that file. Set the
`ROUTER_CONFIG_PATH` env var to an absolute path if you've placed it elsewhere.

### "AnthropicGateway raises 401"
Verify `ANTHROPIC_API_KEY` is set and starts with `sk-ant-`. The gateway
prints `cache_read_input_tokens` / `cache_creation_input_tokens` on each call
when caching is working — if these stay at zero, your prompt isn't long
enough for the cache (minimum 1024 tokens at the cached prefix).

### "Test `test_handle_meditation_safety_net_no_sentinel` skipped"
Expected. That test requires the full `rag.nodes.intent` import chain which
needs Qdrant client + sentence-transformers. They skip cleanly in environments
without those installed. They run inside `docker compose up`.

### "`format_meditation_response` returns None and crashes upstream"
The new return-type is `str | None`. Any call site that previously did
`response = format_meditation_response(step)` must now handle `None`. The
patched `handle_meditation` already does. If you have other call sites, fix
them: when None, do not emit the legacy "meditation is complete" sentinel.

---

## 5. Post-merge improvements you can ship next

Roughly ordered by impact:
1. **Wire the AnthropicGateway** into your generation path with system-prompt
   caching → ~7× cost reduction on Claude.
2. **Wire the Citations API** (also via AnthropicGateway) → ~10pp uplift on
   the citation_correctness LLM-judge dimension.
3. **Enable Anthropic Message Batches API** in `eval_runner.py` for nightly
   evals → 50% off, stackable with caching.
4. **Implement `GuruProfile` loader** for multi-guru tenancy (see
   `MULTI_GURU_ONBOARDING.md`).
5. **Expand the eval dataset** from 51 to 200 questions per the strata in
   `RAG_QUALITY.md` §6.
