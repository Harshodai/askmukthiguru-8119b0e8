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
- **Benchmark Auth Backdoor (local only)**: The `X-Test-Key` header is accepted only when `IS_PRODUCTION=false` AND `ENABLE_TEST_AUTH=true` are set in `.env`/`backend/.env` and the backend container is restarted. Without these, `ruthless_benchmark.py` and manual `curl -H X-Test-Key` will receive 401. Never enable this in production.

## Local Benchmarking
- After setting the auth backdoor vars above, run from `backend`:
  ```bash
  JWT_SECRET=$(grep '^JWT_SECRET=' .env | cut -d= -f2- | tr -d '\n\r')
  .venv/bin/python -u benchmarks/ruthless_benchmark.py --endpoint http://localhost:8000 --test-key "$JWT_SECRET" --concurrency 2
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
