# Agentic Lessons & Environment Context

This file serves as a knowledge base for AI agents interacting with this workspace.

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
- If push fails, resolve and retry until it succeeds

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
