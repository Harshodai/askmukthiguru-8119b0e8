# Feature Inventory

This inventory classifies major user and operator capabilities by executable evidence rather than by function existence.

| Feature | Classification | Evidence and residual gap |
|---|---|---|
| Public landing, guides, and practices | Implemented; route fixes verified | Frontend build and route tests pass. `/guides` compatibility redirect was added; browser E2E remains unavailable. |
| Anonymous chat | Partial; admission behavior verified | API returns bounded 202/429 behavior; local quota state prevented a clean throughput run. |
| Authenticated chat | Partial | Source and unit coverage exist; live session/provider journey not verified. |
| Streaming chat and citations | Partial | Guardrail and streaming tests pass; browser SSE journey not completed. |
| Profile Memory | Implemented with missing live proof | Supabase-native client and component exist; local Supabase integration tests are skipped. |
| My Reflections / Second Brain | Implemented with missing live proof | Encrypted vault client and error path exist; backend vault journey is not live-verified. |
| Guided practices / Serene Mind | Implemented | Practice detail route and content exist; actual browser navigation requires E2E completion. |
| Notebooks and knowledge graph | Implemented/partially verified | Routes and source exist; Neo4j-backed behavior is not live-verified. |
| Upload and multimodal paths | Partial | Malformed/upload regression tests pass; provider and resource-exhaustion matrix remains. |
| Background jobs and cancellation | Implemented with test coverage | Queue ownership/cancellation tests pass; worker restart and duplicate delivery are unproven. |
| Retrieval and grounding | Partial; quality unproven | Tenant/corpus filters and strict harness exist; current corpus labels mismatch golden evaluation labels. |
| Admin/observability surfaces | Partial | Routes and telemetry code exist; alert delivery and least-privilege live checks remain. |
| Mobile packaging | Experimental/partial | Capacitor Android/iOS projects exist; device/emulator parity is not verified. |
| Backup/restore | Missing production proof | Backup utilities exist; no completed restore drill or RPO/RTO evidence. |
