# Agentic Lessons & Environment Context

This file serves as a knowledge base for AI agents interacting with this workspace.

## Plan & Review
### Before starting work
- **CRITICAL: First read `lessons.md`** — search for keywords matching the task scope. Existing lessons contain fixes for repeated regressions (Serene Mind double-wrap, telemetry blocking, Lovable key hard-dependency). Reading first prevents re-debugging known issues.
- Always in plan mode to make a plan.
- After getting the plan, write the plan to `.claude/tasks/TASK_NAME.md`.
- The plan should be a detailed implementation plan with the reasoning behind it, and tasks broken down.
- If the task requires external knowledge or certain packages, research to get the latest knowledge (using appropriate tools).
- Don't over-plan: always think MVP.
- Once you write the plan, ask the user to review it. Do NOT continue until the user approves the plan.
### While implementing
- Update the plan file as you work.
- After completing tasks in the plan, update and append detailed descriptions of the changes you made, so following tasks can be easily handed over to other engineers.

## Docker Execution on Host
- **Docker Path**: The Docker binary is not in the default `/usr/local/bin` or `/opt/homebrew/bin`. It is located at `/Users/harshodaikolluru/.docker/bin/docker`.
- **Command Prefix & Makefile Usage**: Whenever executing `docker` or `docker compose` commands, agents MUST explicitly set the PATH or use the absolute path. Alternatively, and preferably, use the workspace `Makefile` commands which automatically configure the correct PATH.
  - **Preferred (Makefile)**: `make docker-rebuild-web` (to rebuild and restart frontend and backend services without data loss or volume purges).
  - **Other Makefile commands**: `make docker-up` (start full stack), `make docker-down` (stop full stack), `make logs` (view logs).
  - **Raw Command Example**: `export PATH="/Users/harshodaikolluru/.docker/bin:$PATH" && docker compose up -d --build backend frontend`
- Failure to do this will result in "unexpected user interaction type: not permission" errors from the agent runner, or `command not found: docker` errors in standard shells.
- **Keychain Credentials Error (-25293) & .docker_clean**: If Docker image pulls/builds fail on macOS with keychain credential errors (e.g., `-25293`), we bypass this by pointing `DOCKER_CONFIG` to a clean folder `.docker_clean/` with a custom `config.json` containing `"credsStore": ""`.
  - **CLI Plugins & Contexts Symlinks**: When overriding `DOCKER_CONFIG`, Docker hides the host's plugins and context directories. To prevent errors like `unknown shorthand flag: 'd' in -d`, you MUST symlink the host's `cli-plugins` and `contexts` into the clean directory:
    ```bash
    ln -s /Users/harshodaikolluru/.docker/cli-plugins .docker_clean/cli-plugins
    ln -s /Users/harshodaikolluru/.docker/contexts .docker_clean/contexts
    ```



## Supabase
- The application stack relies on Supabase for auth and persistence.
- **Local Supabase**: Can be run via `npx supabase start`, but requires the Docker path to be properly mapped if executed programmatically.
- **Google OAuth (Local)**: To test Google Sign-in locally, set `VITE_USE_NATIVE_OAUTH=true` in `.env.local` and ensure `supabase/config.toml` has valid Google credentials. Restart the stack with `npx supabase stop` and `npx supabase start` after changes.
- **Environment Variable Binding**: Missing `SUPABASE_URL` and `SUPABASE_KEY` must be populated in `backend/.env` for Docker builds.
- **Benchmark Auth Backdoor (local only)**: The `X-Test-Key` header is accepted only when ALL THREE conditions are met:
  1. `IS_PRODUCTION=false` (or unset)
  2. `ENABLE_TEST_AUTH=true`
  3. `BENCHMARK_SECRET` is set (non-empty)
  The `X-Test-Key` value must match `BENCHMARK_SECRET`. Without these, `ruthless_benchmark.py` and manual `curl -H X-Test-Key` will receive 401. Never enable this in production.

## Local Benchmarking
- After setting the auth backdoor vars above, run from `backend`:
  ```bash
  JWT_SECRET=$(grep '^JWT_SECRET=' .env | cut -d= -f2- | tr -d '\n\r')
  BENCHMARK_SECRET=$(grep '^BENCHMARK_SECRET=' .env | cut -d= -f2- | tr -d '\n\r')
  .venv/bin/python -u benchmarks/ruthless_benchmark.py --endpoint http://localhost:8000 --test-key "${BENCHMARK_SECRET:-$JWT_SECRET}" --concurrency 2
  ```
- The current working provider for low-latency local runs is `LLM_PROVIDER=nim`. Sarvam and OpenRouter keys are present as fallbacks.


## Cache Management & Ingestion Isolation
- **Query-Side Caches (GPTCache & Redis)**: The application uses GPTCache (for semantic caching) and Redis (for response caching) to optimize frontend query latency.
- **In-Memory Cache Flushing**: Caches can be flushed safely at any time using:
  - **Preferred (Makefile)**: `make flush-cache` (executes `python3 scripts/ops/flush_cache.py` and runs `redis-cli flushall`).
- **Ingestion Pipeline Isolation**: Flushing these query-side caches has **zero** impact on the active or pending ingestion processes. Ingestion is an ETL pipeline that writes exclusively to Qdrant and Neo4j and maintains its own resumption checkpoints in `scripts/ingestion_state.json`. Agents can confidently assure the user that cache flushing is fully isolated and safe to execute.

## Non-Interactive Shell Commands
**ALWAYS use non-interactive flags** with file operations to avoid hanging on confirmation prompts.

Shell commands like `cp`, `mv`, and `rm` may be aliased to include `-i` (interactive) mode on some systems, causing the agent to hang indefinitely waiting for y/n input.

**Use these forms instead:**
```bash
# Force overwrite without prompting
cp -f source dest           # NOT: cp source dest
mv -f source dest           # NOT: mv source dest
rm -f file                  # NOT: rm file

# For recursive operations
rm -rf directory            # NOT: rm -r directory
cp -rf source dest          # NOT: cp -r source dest
```

**Other commands that may prompt:**
- `scp` - use `-o BatchMode=yes` for non-interactive
- `ssh` - use `-o BatchMode=yes` to fail instead of prompting
- `apt-get` - use `-y` flag
- `brew` - use `HOMEBREW_NO_AUTO_UPDATE=1` env var

## Troubleshooting Guidelines for Agents

### React Component Crashing
- **Symptom**: Frontend serves HTTP 200 but renders a blank page, and console shows `ReferenceError: [FunctionName] is not defined`.
- **Action**: When modifying React components, ensure all referenced functions in event handlers (e.g. `onClick={handleSignOut}`) exist in the component scope. If undefined, it will throw a `ReferenceError` during render and unmount the entire app.

### Code-Review-Graph MCP "Context Canceled"
- **Symptom**: `code-review-graph: INFO Starting MCP server 'code-review-graph' with transport 'stdio' : context canceled`
- **Action**: This is normal behavior when the IDE restarts or the agent session ends. Do **NOT** try to "fix" the MCP server code. If it fails to start entirely, verify `mcp_config.json` is valid JSON and points to `.venv/bin/code-review-graph`.

## Post-Change Documentation Checklist
Agents MUST update the following documentation after completing a fix, feature, or architectural change:
- [ ] **lessons.md**: Document the specific implementation pattern, architectural decision, or "lesson learned".
- [ ] **README.md**: If a new service, route, or environment variable is added, update the README to reflect these changes.
- [ ] **docs/ROADMAP.md**: Mark items as complete or add new technical debt discovered during the change.
- [ ] **docs/DEVELOPER_GUIDE.md**: Update if the onboarding or development workflow has changed.
- [ ] **CLAUDE.md**: Update structural directory map, commands, or URL matrix.
- [ ] **AGENTS.md**: Update agent context, checklist, or guidelines if necessary.

## Session Completion
**When ending a work session**, you MUST complete ALL steps below. Work is NOT complete until `git push` succeeds.

**MANDATORY WORKFLOW:**

1. **File issues for remaining work** - Create issues for anything that needs follow-up
2. **Run quality gates** (if code changed) - Tests, linters, builds
3. **Update issue status** - Close finished work, update in-progress items
4. **PUSH TO REMOTE** - This is MANDATORY:
   ```bash
   git pull --rebase
   git push
   git status  # MUST show "up to date with origin"
   ```
5. **Clean up** - Clear stashes, prune remote branches
6. **Verify** - All changes committed AND pushed
7. **Hand off** - Provide context for next session

**CRITICAL RULES:**
- Work is NOT complete until `git push` succeeds
- NEVER stop before pushing - that leaves work stranded locally
- NEVER say "ready to push when you are" - YOU must push
## Agent Technical Skills
- **Pre-Compiled Technical Skills**: There are 15 pre-compiled agent skills containing structured summaries, patterns, and cheatsheets from technical books. They are located locally under `.agents/skills/<slug>` and mirrored globally at `~/.config/agents/skills/<slug>`.
- **How to Use**: Agents MUST read the `skill.md` file in these directories to load the core frameworks, or query the specific chapter files (e.g. `chapters/ch01-...`) for deep-dive technical context on topics like LangChain, LangGraph, RAG, System Design, or Database Internals.

<!-- code-review-graph MCP tools -->
## MCP Tools: code-review-graph

**IMPORTANT: This project has a knowledge graph. ALWAYS use the
code-review-graph MCP tools BEFORE using Grep/Glob/Read to explore
the codebase.** The graph is faster, cheaper (fewer tokens), and gives
you structural context (callers, dependents, test coverage) that file
scanning cannot.

### When to use graph tools FIRST

- **Exploring code**: `semantic_search_nodes` or `query_graph` instead of Grep
- **Understanding impact**: `get_impact_radius` instead of manually tracing imports
- **Code review**: `detect_changes` + `get_review_context` instead of reading entire files
- **Finding relationships**: `query_graph` with callers_of/callees_of/imports_of/tests_for
- **Architecture questions**: `get_architecture_overview` + `list_communities`

Fall back to Grep/Glob/Read **only** when the graph doesn't cover what you need.

### Key Tools

| Tool | Use when |
| ------ | ---------- |
| `detect_changes` | Reviewing code changes — gives risk-scored analysis |
| `get_review_context` | Need source snippets for review — token-efficient |
| `get_impact_radius` | Understanding blast radius of a change |
| `get_affected_flows` | Finding which execution paths are impacted |
| `query_graph` | Tracing callers, callees, imports, tests, dependencies |
| `semantic_search_nodes` | Finding functions/classes by name or keyword |
| `get_architecture_overview` | Understanding high-level codebase structure |
| `refactor_tool` | Planning renames, finding dead code |

### Workflow

1. The graph auto-updates on file changes (via hooks).
2. Use `detect_changes` for code review.
3. Use `get_affected_flows` to understand impact.
4. Use `query_graph` pattern="tests_for" to check coverage.

## Local Codebase Intelligence & Memory MCP Layer

In addition to `code-review-graph`, this workspace is integrated with four dedicated local/global MCP servers and plugins:
1. **Graphify**: Offline AST codebase graph tool (provides `code-review-graph` MCP tools).
2. **Claude-Mem**: Long-term episodic/semantic memory worker (SQLite + ChromaDB).
3. **CodeGraph**: AST query engine using WASM-compiled tree-sitter grammars.
4. **Understand Anything**: Multi-agent codebase knowledge graph builder and visualizer.

- **Auto-Sync Hook**: A post-commit hook at `.git/hooks/post-commit` automatically runs `node scripts/ops/update-understand-graph.cjs` in the background on every commit to keep the graph (`.understand-anything/knowledge-graph.json`) fresh.
- **Manual Sync**: Run `node scripts/ops/update-understand-graph.cjs` to force sync the graph.

### Strict Environment Constraints
- **Node.js v22 LTS Only**: Do **NOT** upgrade Node.js to Node `25.x` or run CodeGraph commands under Node 25. Node 25 has a critical WASM compiler Zone allocation bug that causes out-of-memory crashes (`Zone allocation constraints`) during tree-sitter compilation. Always keep the shell environment linked to Node 22 LTS (`/opt/homebrew/opt/node@22/bin`).
- **Bun Dependency for Claude-Mem**: Claude-Mem's background worker service runs on Bun for high-performance sqlite bindings. Ensure `bun` is available at `/opt/homebrew/bin/bun`.
- **Git Worktree Cleanup**: In agentic sessions, temporary git worktrees (`.claude/worktrees/agent-*`) can accumulate. This causes severe local git indexing lag. You **MUST** run `git worktree prune` and explicitly delete any temporary worktrees you created (`git worktree remove --force <path>`) before finishing your session.

### Utilizing Local MCP Tools
- **Explore first, grep last**: Use CodeGraph, Graphify, and Understand Anything rather than running heavy recursive glob/grep commands across thousands of files. It saves token costs, prevents host memory thrashing, and respects structural linkages.
- **Memory Recalls**: Leverage `claude-mem` to recall key patterns or historical insights across conversation checkpoints.

## Ponytail & Headroom Guidelines

### The Ladder (hard rule — runs BEFORE writing any code)
Before writing code, the agent stops at the first rung that holds:

1. Does this need to exist?   → no: skip it (YAGNI)
2. Already in this codebase?  → reuse it, don't rewrite
3. Stdlib does it?            → use it
4. Native platform feature?   → use it
5. Installed dependency?      → use it
6. One line?                  → one line
7. Only then: the minimum that works

The ladder runs after it understands the problem, not instead of it: it reads the code the change touches and traces the real flow before picking a rung. Lazy about the solution, never about reading.

Lazy, not negligent: trust-boundary validation, data-loss handling, security, and accessibility are never on the chopping block.

### Ponytail Principle
Keep implementations lightweight, minimal-diff, and simple:
- **Thin wrappers**: Prefer small, focused helper scripts or inline functions over heavy abstractions or new classes.
- **Self-Checks**: Python files should contain a runnable `if __name__ == "__main__":` block at the bottom for quick verification.
- **Optional/Stubbed Features**: Gracefully degrade or skip components if dependencies are not available on the runtime host.
- **LRU Cache Usage**: Use simple caching patterns (e.g. `lru_cache`) instead of custom state tracking classes where possible.

### Headroom Principle
Implement system configurations and runtime operations with safety margins (headroom):
- **Cost Steering**: Automatically steer LLM prompting towards brevity (`COST_STEERED_BREVITY_LIMIT` words) when context/history length is high to optimize token usage.
- **Reversible Context Compression (CCR)**: Allow the LLM to request full text for compressed text using `[RETRIEVE: <source_url>]` pattern; generation stage will intercept and swap the original text.
- **Timeout and Resource Headroom**: Always configure timeouts with safety margins (e.g. 120s timeouts for sequence calls, or 10% GPU/CUDA headroom) to avoid transient service lockups.

Respond terse like smart caveman. All technical substance stay. Only fluff die.

Rules:
- Drop: articles (a/an/the), filler (just/really/basically), pleasantries, hedging
- Fragments OK. Short synonyms. Technical terms exact. Code unchanged.
- Pattern: [thing] [action] [reason]. [next step].
- Not: "Sure! I'd be happy to help you with that."
- Yes: "Bug in auth middleware. Fix:"

Switch level: /caveman lite|full|ultra|wenyan
Stop: "stop caveman" or "normal mode"

Auto-Clarity: drop caveman for security warnings, irreversible actions, user confused. Resume after.

Boundaries: code/commits/PRs written normal.

## Mobile App

- **Capacitor 8** wraps the Vite/React build for Android + iOS. Same codebase, no separate mobile repo.
- **Package id** `com.askmukthiguru.app`, display name `AskMukthiGuru`.
- **Router**: HashRouter on native, BrowserRouter on web — selected in `src/App.tsx` (BrowserRouter breaks in the Capacitor WebView because assets are served from `https://localhost/` with no server fallback).
- **Backend URL**: `src/lib/backendUrl.ts` forces Railway prod on native (`Capacitor.isNativePlatform()` check) because `window.location.hostname` is `localhost` inside the WebView and the prod-host regex would miss it.
- **Push (frontend)**: `src/components/common/PushNotificationsManager.tsx` — registers device token via `@capacitor/push-notifications`, sends to backend. `addListener` returns a Promise → use a `disposed` flag for race-safe cleanup.
- **Push (backend)**: `backend/app/api/push.py` (routes) + `backend/services/push_service.py` (FCM + APNs dispatch). Device tokens stored in `push_devices` table (migration `20260713000000_create_push_devices.sql`).
- **OAuth deep link**: scheme `com.askmukthiguru.app://auth-callback` — captured via `App.addListener('appUrlOpen')` in `src/App.tsx`. Android intent-filter + iOS CFBundleURLTypes wired by Capacitor config. Add this URL to Supabase Auth redirect URLs.
- **Storage**: `@capacitor/preferences` (SharedPreferences / NSUserDefaults) via a `SupportedStorage` adapter for supabase-js — `localStorage` is unreliable in the WebView.
- **Build cmd**: `npm run cap:sync` (vite build + cap sync). Native open: `npm run cap:open:android` / `cap:open:ios`.
- **Re-create native projects**: `rm -rf android ios && npx cap add android && npx cap add ios` — only when package id or Capacitor plugins change drastically. Discards native-side customizations.
- **Icons/splash**: `python3 scripts/ops/generate_mobile_assets.py` (regenerates from `public/icon-512.png`).
- **Store submission**: `docs/MOBILE_RELEASE_RUNBOOK.md` — full Play + App Store guide.
- **Store listing copy**: `docs/STORE_LISTING.md`.
- **Signing + push creds**: `CREDENTIALS_GUIDE.md` → "Mobile App Credentials" (keystore, `google-services.json`, APNs `.p8`, backend env: `FIREBASE_CREDENTIALS_JSON`, `APNS_KEY_ID`, `APNS_TEAM_ID`, `APNS_KEY_PATH`, `APNS_KEY_PEM`, `APNS_BUNDLE_ID`).
- **Known TODOs**: ~~Apple Sign-In~~ ✅ implemented (native iOS, `AuthPage.tsx` — requires Supabase Apple provider config before submission). ~~Delete-account flow~~ ✅ implemented (`ProfilePage.tsx` + `delete-my-account` edge function).

# Session Handoff — Jul 11, 2026

## Session Summary
Full 5-phase emergent security audit. 93% pass rate. 30+ fixes across rate limiting, model validation, PII logging, CORS/nginx, access control (IDOR), container security, and CI/CD hardening.

## What Was Done
- **Phase 1 (Critical)**: STT/TTS rate limits (10/min), OpenRouter classify model name fix, audit scripts created (`scripts/security/`), secrets scan, Supabase RLS enabled on 5 tables, PGRST202 schema cache reloaded.
- **Phase 2 (Hardening)**: PII log redaction across 6 files, per-user rate limiting via `TenantContext.get_user_id()`, HSTS+CSP headers in nginx, CORS origin doc fix in docker-compose.
- **Phase 3 (Access Control)**: 2 IDOR fixes on notebook routes, Swagger/docs gated in production, metrics endpoint admin-only, per-user LLM call usage monitor, breath-teaching rate limit added.
- **Phase 4 (Pipeline)**: Non-root users in 3 Dockerfiles, HEALTHCHECK on 2 containers, Trivy + Bandit in CI workflows, `gptcache` image pinned to version.
- **Phase 5 (Report)**: Audit scripts run, report at `scripts/security/report.md`, score 28/30 PASS.
- **Remaining (fixed)**: `.env.example` created at root with `!.env.example` gitignore exception, `password` removed from `check_docker_health.py` `SERVICES` dict.

## Running Services
- Backend: `http://localhost:8000` (healthy)
- Frontend: `http://localhost:80` (Nginx proxy)
- Neo4j: `bolt://localhost:7687` (browser at `http://localhost:7474`)
- Local Supabase: Postgres :54322, API :54321, Studio :54323
- Celery Worker: healthy
- All infra: Qdrant, Redis, Jaeger, Prometheus, Grafana

## Security Audit Scripts
- `scripts/security/audit_log_pii.sh` — scan for PII in log statements
- `scripts/security/audit_secrets.sh` — scan for hardcoded secrets
- `scripts/security/audit_endpoints.sh` — audit API endpoint exposure
- `scripts/security/audit_cors_headers.sh` — check CORS and security headers
- `scripts/security/run_emergent_audit.sh` — run all audits in sequence
- `scripts/security/report.md` — latest audit report (93% pass)
- `scripts/security_audit.py` — programmatic security audit runner

## Critical Context
- Celery worker uses same `backend/Dockerfile` as backend — both must be rebuilt together.
- `docker-rebuild-web` only rebuilds `backend` and `frontend` — run `docker compose up -d --build celery-worker` separately.
- PGRST204 fix: `NOTIFY pgrst, 'reload schema'` after schema changes.
- Swagger docs gated behind `IS_PRODUCTION` check in `main.py`.
- `.env.example` has a `!.env.example` exception in `.gitignore`.
- Security audit report regenerated by running `bash scripts/security/run_emergent_audit.sh`.

## What Was Done
- **MD quality**: Added `resource` field (clean YouTube URL) to all 22 files. Normalized `title` quoting. Added wiki-link cross-references `[[concept-id]]` to 15 files (Karpathy pattern). Created `_scripts/add_wikilinks.py` batch injection tool. See `.claude/tasks/transcript-md-quality.md`.
- **Fixed Neo4j seed Cypher**: `SET t:Teacher:$label_type` → f-string safe interpolation in `backend/app/db/seed_ontology.py`.
- **Fixed celery `/memory` path**: `_BACKEND.parent` → `/app/memory/okf` in `backend/scripts/extract_okf_from_stores.py`.
- **Synced `scripts/` copy**: `backend/scripts/extract_okf_from_stores.py` and `scripts/extract_okf_from_stores.py` byte-identical again.
- **Anonymous user guard**: `memory_service.py` — `_is_anonymous` check returns early for `"anonymous"` user_id to prevent UUID insert errors.
- **PGRST204 retry**: Service retries without `claim`/`confidence`/`decay_score` columns.
- **Celery time limits doubled**: soft 600s→1800s, hard 900s→2400s for LLM retry chains.
- **Guru_memories columns applied**: Added `claim TEXT`, `confidence DOUBLE PRECISION`, `decay_score DOUBLE PRECISION DEFAULT 1.0` to local Supabase + migration file. Reloaded PostgREST schema cache.
- **Migration created**: `supabase/migrations/20260710000000_add_guru_memories_missing_columns.sql`.
- **Reranker JSON error fixed**: Added `json.JSONDecodeError` catch + HF cache clear retry in `_ensure_reranker()` and `_load_fallback()`.
- **Guardrails set to lightweight**: `GUARDRAILS_PROVIDER=lightweight` — skips Llama Guard / Rejection Classifier / NeMo loading (no startup noise).
- **LightRAG timeout default raised**: `lightrag_retrieval_timeout` 3→30s in config.py (matches `.env` value).
- **Knowledge graph query enabled**: `knowledge_graph_query_enabled=True` — LightRAG now queried for RELATIONAL/FACTUAL/QUERY intents (2,200+ relations available).
- **download_models.py fixed**: Rejection classifier model corrected from `meta-llama/Llama-Guard-3-1B` → `protectai/distilroberta-base-rejection-v1`.
- **All containers rebuilt**: backend, celery-worker, frontend — all healthy.
- **Chat pipeline verified**: End-to-end query returns response with context.

## Running Services
- Backend: `http://localhost:8000` (healthy)
- Frontend: `http://localhost:80` (Nginx proxy)
- Neo4j: `bolt://localhost:7687` (browser at `http://localhost:7474`)
- Local Supabase: Postgres :54322, API :54321, Studio :54323
- Celery Worker: healthy, tasks registered (okf_compile, okf_extract, ingestion)
- All infra: Qdrant, Redis, Jaeger, Prometheus, Grafana

## Remaining Issues
- None critical. ColBERTv2 fallback to CrossEncoder is expected (model not cached).
- `test_openrouter_provider_delegation` is a pre-existing test failure unrelated to these changes.

## Demo
1. Open `http://localhost` → Chat with the guru
2. Navigate to `/profile` → Click graph toggle (Network icon in Memory card)
3. See 40 ontology nodes (Teachers, Concepts, Practices) as SVG
4. Drag to pan, scroll to zoom

## Files Changed (This Session)
- `memory/okf/*.md` — 22 files with `resource` field, wiki-links, quoted titles
- `memory/okf/_scripts/add_wikilinks.py` — batch wiki-link injection
- `.claude/tasks/transcript-md-quality.md` — quality plan
- `backend/services/memory_service.py` — anonymous guard + PGRST204 retry
- `backend/celery_config.py` — doubled time limits
- `backend/scripts/extract_okf_from_stores.py` — fixed `/memory` → `/app/memory`
- `scripts/extract_okf_from_stores.py` — synced copy
- `backend/app/db/seed_ontology.py` — fixed Cypher f-string
- `supabase/migrations/20260710000000_add_guru_memories_missing_columns.sql` — new migration
- `backend/services/embedding_service.py` — HF cache clear retry for reranker JSON error
- `backend/services/reranker_service.py` — HF cache clear retry for fallback reranker
- `backend/app/config.py` — `lightrag_retrieval_timeout` 3→30, `knowledge_graph_query_enabled` True
- `backend/.env` — `GUARDRAILS_PROVIDER=lightweight`
- `backend/scripts/download_models.py` — fixed rejection classifier model ID

## Critical Context
- Celery worker uses same `backend/Dockerfile` as backend — both must be rebuilt together.
- `docker-rebuild-web` only rebuilds `backend` and `frontend` — run `docker compose up -d --build celery-worker` separately.
- PGRST204 fix: `NOTIFY pgrst, 'reload schema'` after schema changes.
- Supabase `anond` key is set in `.env` files (local).
- `npx supabase db query "..."` to run SQL against local Postgres.
- `GUARDRAILS_PROVIDER=lightweight` skips all ML guardrails (Llama Guard, Rejection Classifier, NeMo). Lightweight handler covers 13 regex-based topic categories, prompt injection, and emotional wellness redirects.
- `knowledge_graph_query_enabled=True` enables LightRAG graph traversal for RELATIONAL/FACTUAL/QUERY intents with 30s timeout. LightRAG holds 2,365 entities + 2,200 relations.

## Railway Deployment (Production)
- **Project**: `resilient-embrace` | **Service**: `askmukthiguru-8119b0e8` | **Environment**: `production`
- **Deploy method**: Use `railway up` (tarball upload) — **NOT** `railway redeploy --from-source`
  - `railway up` uploads a tarball and deploys reliably
  - `railway redeploy --from-source` gets stuck at INITIALIZING on this repo
- **Replicas**: Set to **1 replica** in `railway.json` — 2 replicas caused second replica to fail init timeout
- **Health checks**: 
  - `/api/healthz` — intercepted by `start_railway.py` wrapper, returns 200 for 90s grace period
  - `/api/health` — real per-service health, returns `ready: false` until `startup_complete=True`
- **Docker path for CLI**: `export PATH="/Users/harshodaikolluru/.docker/bin:$PATH" && railway <cmd>`
- **Link service**:
  ```bash
  railway link --project resilient-embrace --service askmukthiguru-8119b0e8
  ```
- **View logs**: `railway logs` (shows interleaved from all deployments; use `--deployment <id>` for specific)
- **Environment variables**: Set via `railway variables --json '{"KEY": "value"}'` or dashboard
- **Key env vars for backend**: `OPENROUTER_API_KEY`, `SUPABASE_URL`, `SUPABASE_KEY`, `QDRANT_URL`, `QDRANT_API_KEY`, `REDIS_URL`, `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD`, `IS_PRODUCTION=true`
