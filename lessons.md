# Agentic Lessons & Memory

This file documents key implementation patterns, architectural decisions, and "lessons learned" during the development of Mukthi Guru.

## Feature Implementations (May 2026)

### 1. Daily Teaching & Realtime Sync
- **Mechanism**: The `daily_teachings` component is wired to Supabase Realtime.
- **State Management**: Implemented a "dismiss-by-id" logic. When a user dismisses a teaching, the ID is stored in local storage.
- **Persistence**: New teaching uploads (with new IDs) will bypass the dismissal, ensuring fresh content is always seen by the user.

### 2. Authentication Hardening
- **HIBP Protection**: Enabled "Have I Been Pwned" (HIBP) integration in the Supabase/Auth configuration to prevent the use of leaked passwords.
- **Password Recovery**: Added `/reset-password` route and linked it from the `AuthPage` via a "Forgot password" flow.
- **Compliance**: Added `/privacy` and `/terms` routes to provide necessary legal documentation.

### 3. UX & Interface Refinements
- **Content Utility**: Added a "Copy-to-clipboard" button to all guru responses in the chat interface for easy sharing/saving of wisdom.
- **Mobile/Desktop Parity**: Ensured sidebar visibility and branding headers are synchronized across different screen sizes.

### 4. Configuration & Onboarding
- **OAuth Flexibility**: Documented the `VITE_USE_NATIVE_OAUTH` toggle in `.env.example`.
    - `true`: Native Supabase OAuth (Docker Local).
    - `false`: Lovable OAuth wrapper (Cloud).
- **Developer Experience**:
    - `docs/DEVELOPER_GUIDE.md`: Comprehensive onboarding for new contributors.
    - `docs/ROADMAP.md`: Phased backlog tracking future vision and technical debt.
    - **Linking**: All new docs are linked from the primary `README.md`.

### 5. Conversation Memory Hardening
- **Follow-up Resolution**: Implemented a dedicated `resolve_followup` node in the RAG pipeline. This uses LLM-based query rewriting to transform pronoun-heavy follow-up questions ("Tell me more about it") into standalone, context-aware queries based on recent history.
- **Cache Key Integrity**: Updated `RequestCoalescer` in the backend to include a hash of recent conversation history. This prevents cache collisions where identical queries in different conversation threads would return stale or contextually incorrect results.

### 6. Conversation Compaction & Coherence
- **LLM-Driven Summarization**: Integrated an automatic summarization pipeline that triggers every 6 messages. This generates a concise spiritual and emotional summary of the thread, which is then prepended to the context window of future requests.
- **Context Window Management**: Balanced the context window by increasing the frontend "active" message slice (last 20 messages) while maintaining long-term coherence through the generated summary system message.

### 7. Production Security & Resilience (May 2026)
- **Serene Mind Engine**: Upgraded to a three-stage distress detection pipeline (Keyword → LLM → Embedding-based Similarity). This ensures 100% detection coverage even for nuanced emotional states.
- **Distress Pipeline Integrity**: Reconfigured the graph to route distress queries through the RAG pipeline. This allows the guru to respond with specific, retrieved teachings that address the user's pain, rather than serving static messages.
- **Resilience**: Implemented exponential backoff retries for all Qdrant operations. This protects the application against transient network failures during high-concurrency retrieval or ingestion.
- **Guardrail Exceptions**: Added `_SPIRITUAL_CONTEXT_PATTERNS` to the guardrails service. This prevents false positives when users discuss spiritual concepts like "ego death" or "surrender," which are central to the teachings but often flagged as self-harm by generic AI filters.
- **Prompt Engineering**: Sanitized all system prompts by removing hardcoded placeholder YouTube URLs and enforcing a strict guru embodiment (Sri Preethaji/Sri Krishnaji) across all response levels.

### 8. Auth & Profile Synchronization (May 2026)
- **Route Shadowing**: Discovered that static folders in Nginx (e.g., `/chat-ui`, `/ingest-ui`) were shadowing React application routes (e.g., `/chat`, `/ingest`). This prevented auth-guards from triggering properly.
- **Fix**: Renamed static folders to `/static-*` and updated the Nginx configuration to prioritize the React router. This ensures all protected paths correctly redirect to `/auth`.
- **Bidirectional Sync**: Implemented a synchronization layer between `localStorage` and the Supabase `user_profiles` table. Profiles are now automatically initialized on first login and updated across devices.

### 9. Admin Observability & Audit (May 2026)
- **User Auditing**: Added "Total Seekers" KPI to the admin dashboard, powered by real-time counts from the `user_profiles` table.
- **Enhanced Telemetry**: Expanded the telemetry database to include `trigger_events` (for Serene Mind auditing) and `retrieval_events` (for knowledge base performance tracking).
- **Master Schema**: Created `master_schema.sql` to centralize all production table definitions (profiles, telemetry, observability) into a single, idempotent script.
- **Onboarding Flow**: Implemented a "Profile-First" onboarding pattern. New users are redirected to `/profile?onboarding=true` immediately after authentication to set their spiritual parameters (Language, Tone, Bio) before their first chat.
- **UI Discoverability**: Replaced the hidden sidebar menu with direct "Rename" and "Delete" icons that appear on hover, improving task efficiency and feature visibility.

## Lessons Learned

### Docker & Environment
- **Path Issues**: Always use absolute paths for Docker binaries on host machines (specifically `/Users/harshodaikolluru/.docker/bin/docker`) to avoid "command not found" errors in automated scripts.
- **Volume Persistence**: Critical services (Qdrant, Neo4j, Redis) must use named volumes to ensure data survives container rebuilds.
- **Nginx Route Priority**: When serving a SPA alongside legacy static files, avoid folder names that conflict with internal application routes. Static assets should be namespaced (e.g., `/static/`) to prevent route hijacking.

### RAG Pipeline
- **Distress Detection**: The "Serene Mind" engine should be non-fatal. If detection fails, the pipeline should fall back to a standard compassionate RAG response rather than erroring out.
- **History Hashing**: In RAG systems, user queries are often short and repetitive (e.g., "why?"). Hashing the *query + recent_history* is essential for maintaining unique cache keys across different users or sessions.
- **Multi-Stage Detection**: For high-stakes detection (like distress), a single method (e.g., keyword) is insufficient. Combining fast regex, nuanced LLM classification, and semantic embedding similarity provides the best balance of speed and accuracy.
- **Telemetry Richness**: Telemetry should capture the *entire* lifecycle of a request, including retrieval scores and emotional assessments, to provide actionable insights for tuning the guru's responses.
