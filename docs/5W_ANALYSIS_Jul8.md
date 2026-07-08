# 5W Analysis — Jul 8, 2026

## What
Knowledge Graph (KG) Concept Map Visualizer for Mukthi Guru. Users can see a 40-ontology-node graph (Teachers, Concepts, Practices) on their profile page at `/profile`, rendered as an SVG with circular layout, pan/zoom, and a dual list/graph toggle.

## Who
- **Frontend**: `MemoryManager.tsx` — SVG-based visualizer, 551 lines, zero new deps
- **Backend**: `memory.py` — KG endpoint with auth fallback; `memory_service_v2.py` — `build_personal_knowledge_graph()` with ontology-only fallback
- **Seed**: `seed_personal_kg.py` — idempotent 40-node ontology seed into Neo4j
- **API Client**: `memoryApi.ts` — `getKnowledgeGraph()` sends auth-optional requests

## Where
- **Endpoint**: `GET /api/memory/knowledge-graph` (FastAPI, mounted at `/api`)
- **Frontend**: Profile page → Memory card → Network icon toggle
- **Data**: Neo4j graph DB (bolt://localhost:7687), 40 ontology nodes
- **Deployment**: Docker stack (backend:8000, frontend:80, neo4j, qdrant, redis, jaeger, prometheus, grafana)

## When
- July 8, 2026 — Session covering KG visualizer build-out, seed script, auth fallback, docs update, and demo readiness verification

## Why (Problem → Solution)
| Problem | Solution |
|---------|----------|
| No visual representation of the spiritual ontology | SVG graph with 40 ontology nodes on profile page |
| KG endpoint errored for unauthenticated users | Auth fallback: authenticated→full graph, unauthenticated→ontology-only |
| Seed script ran only once (CREATE) | Changed to idempotent MERGE + existing-data check |
| No way to see KG structure without logging in | Public ontology view always returns meaningful data |
| Too many deps for a simple graph visualization | Vanilla SVG with manual layout (551 lines, 0 new deps) |

## Demo Readiness Assessment

### Status: **DEMO READY** (Confidence: 90%)

### Running Services
| Service | Status | URL |
|---------|--------|-----|
| Backend API | ✅ Healthy | http://localhost:8000 |
| Frontend (Nginx) | ✅ Serving | http://localhost:80 |
| Neo4j | ✅ Healthy | bolt://localhost:7687, browser at http://localhost:7474 |
| Qdrant | ✅ Healthy | http://localhost:6333 |
| Redis | ✅ Healthy | localhost:6379 |
| Jaeger | ✅ Healthy | http://localhost:16686 |
| Prometheus | ✅ Healthy | http://localhost:9090 |
| Grafana | ✅ Healthy | http://localhost:3000 |

### Test Results
- **435 total tests pass** (297 backend + 32 graph strategy + 106 API/memory)
- 1 pre-existing failure (`test_important_kwd_backfill` — missing module, unrelated)
- 0 new warnings

### Demo Flow
1. Open `http://localhost` in browser
2. Sign in (or skip — KG works without auth)
3. Navigate to `/profile`
4. In the Memory card, click the Network icon (graph toggle, next to List icon)
5. See 40 ontology nodes (Teachers, Concepts, Practices) as colored circles
6. Drag to pan, scroll to zoom, click Reset to center

### What's Visible Without Auth
- 40 ontology nodes: 6 Teachers (Sadhguru, Sri Amma Bhagavan, Sri Preethaji, Sri Krishnaji, ISKCON), 31 Concepts (Oneness, Moksha, Karma, Dharma, etc.), 3 Practices (Serene Mind, Yoga)
- Circular layout with type-based coloring
- Pan/zoom/reset controls
- Node count and connection count display

### What Requires Auth
- Full personal graph (User node + Memories + edges)
- Memory list, Core memory editor, Session reflections
- Adding/forgetting memories

### Risks
| Risk | Mitigation |
|------|------------|
| No edges in public ontology (0 connections) | Expected — public view is a reference map. Edges come from user-specific memories. |
| Build artifacts stale in running container | Already rebuilt: backend container is 4 min old, frontend is 4 min old. |
| KG empty if Neo4j DB is fresh | Seed script must have been run. Confirm: `curl -s http://localhost:8000/api/memory/knowledge-graph \| python3 -c "import sys,json; d=json.load(sys.stdin); print(f'{d[\"count\"]} nodes')"` |
