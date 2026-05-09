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

### 4. Conversation Memory Hardening
- **Follow-up Resolution**: Implemented a dedicated `resolve_followup` node in the RAG pipeline. This uses LLM-based query rewriting to transform pronoun-heavy follow-up questions ("Tell me more about it") into standalone, context-aware queries based on recent history.
- **Cache Key Integrity**: Updated `RequestCoalescer` in the backend to include a hash of recent conversation history. This prevents cache collisions where identical queries in different conversation threads would return stale or contextually incorrect results.

### 5. Conversation Compaction & Coherence
- **LLM-Driven Summarization**: Integrated an automatic summarization pipeline that triggers every 6 messages. This generates a concise spiritual and emotional summary of the thread, which is then prepended to the context window of future requests.
- **Context Window Management**: Balanced the context window by increasing the frontend "active" message slice (last 20 messages) while maintaining long-term coherence through the generated summary system message.

## Lessons Learned

### Docker & Environment
- **Path Issues**: Always use absolute paths for Docker binaries on host machines (specifically `/Users/harshodaikolluru/.docker/bin/docker`) to avoid "command not found" errors in automated scripts.
- **Volume Persistence**: Critical services (Qdrant, Neo4j, Redis) must use named volumes to ensure data survives container rebuilds.

### RAG Pipeline
- **Distress Detection**: The "Serene Mind" engine should be non-fatal. If detection fails, the pipeline should fall back to a standard compassionate RAG response rather than erroring out.
- **History Hashing**: In RAG systems, user queries are often short and repetitive (e.g., "why?"). Hashing the *query + recent_history* is essential for maintaining unique cache keys across different users or sessions.
