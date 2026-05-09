# Agentic Lessons & Environment Context

This file serves as a knowledge base for AI agents interacting with this workspace.

## Docker Execution on Host
- **Docker Path**: The Docker binary is not in the default `/usr/local/bin` or `/opt/homebrew/bin`. It is located at `/Users/harshodaikolluru/.docker/bin/docker`.
- **Command Prefix**: Whenever executing `docker` or `docker compose` commands, agents MUST explicitly set the PATH or use the absolute path.
  - Example: `export PATH="/Users/harshodaikolluru/.docker/bin:$PATH" && docker compose up -d --build`
- Failure to do this will result in "unexpected user interaction type: not permission" errors from the agent runner, or `command not found: docker` errors in standard shells.

## Supabase
- The application stack relies on Supabase.
- To use Docker deployment correctly, the missing `SUPABASE_URL` and `SUPABASE_KEY` must be populated in the `backend/.env` file so the Vite build step in the `frontend.Dockerfile` can bake them into the React output.
- **Local Supabase**: Can be run via `npx supabase start`, but requires the Docker path to be properly mapped if executed programmatically.

## Post-Change Documentation Checklist
Agents MUST update the following documentation after completing a fix, feature, or architectural change:
- [ ] **lessons.md**: Document the specific implementation pattern, architectural decision, or "lesson learned".
- [ ] **README.md**: If a new service, route, or environment variable is added, update the README to reflect these changes.
- [ ] **docs/ROADMAP.md**: Mark items as complete or add new technical debt discovered during the change.
- [ ] **docs/DEVELOPER_GUIDE.md**: Update if the onboarding or development workflow has changed.
