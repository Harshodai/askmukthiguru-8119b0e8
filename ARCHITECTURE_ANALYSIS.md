# AskMukthiGuru — Complete End-to-End System Architecture

![End-to-End System Architecture Diagram](/Users/harshodaikolluru/.gemini/antigravity-ide/brain/a89764c5-3c8a-4394-92ae-01e1dcd1c071/antigravity_architecture_diagram_1780301226669.png)

This guide describes the complete, comprehensive technical architecture of the **AskMukthiGuru** project, mapping how information flows from the user interface down to your background orchestrator and specialized databases.

---

## 1. System Architecture Diagram

This diagram visualizes the multi-tier flow from your frontend client down to your LangGraph FastAPI service and database engines.

```mermaid
graph TD
    subgraph Client Layer (Vite + React)
        UI[ChatInterface.tsx] -->|Streaming SSE Request| AIService[aiService.ts]
        Pills[ThinkingPills.tsx] <-->|UI Phase Updates| UI
        LocalStore[chatStorage.ts] <-->|Anonymous Chats| UI
    end

    subgraph Authentication & Gateway Layer
        Auth[Supabase Auth] -->|Google / Email Signup| Trigger[on_auth_user_created]
        Trigger -->|Auto-Profile| Profiles[(Profiles Table)]
    end

    subgraph Service & Orchestration Layer (FastAPI on :8000)
        API[app/main.py] -->|1. Input Safety Rail| NeMoIn[NeMo Guardrails]
        NeMoIn -->|2. Fast-Path| Depression[Depression Detector]
        
        subgraph 12-Layer Processing Pipeline (LangGraph)
            Router{3. intent_router} -->|DISTRESS / CASUAL| FastResp[Casual Response]
            Router -->|QUERY| Decompose[4. Decompose Query]
            Decompose -->|5. Retrieve Docs| QdrantClient[Qdrant Retriever]
            QdrantClient -->|6. Rerank| Rerank[Reranking Model]
            Rerank -->|7. Grade Docs| Irrelevant{Irrelevant?}
            Irrelevant -->|Yes: CRAG Loop max 3x| Rewrite[8. Query Rewrite]
            Rewrite --> QdrantClient
            Irrelevant -->|No| Hints[9. Extract Hints]
            Hints --> Gen[10. Generate Answer]
            Gen --> Faith[11. Check Faithfulness]
            Faith --> Verify[12. Verify & Format]
        end
        
        Verify -->|13. Output Safety Rail| NeMoOut[NeMo Guardrails]
    end

    subgraph Database & Persistence Layer
        NeMoOut -->|Event Stream| AIService
        Verify -->|Persist Auth Chats| DB[(Supabase DB)]
        QdrantClient <-->|Cosine Search| Qdrant[(Qdrant Vector DB)]
        Decompose <-->|Graph Traversal| Neo4j[(Neo4j Graph DB)]
        Gen <-->|Local Inference| Ollama[(Ollama: sarvam-30b)]
    end
    
    classDef client fill:#38bdf8,stroke:#0369a1,stroke-width:2px;
    classDef api fill:#4ade80,stroke:#15803d,stroke-width:2px;
    classDef db fill:#fb7185,stroke:#be123c,stroke-width:2px;
    
    class UI,AIService,Pills,LocalStore client;
    class API,NeMoIn,Depression,Router,Decompose,QdrantClient,Rerank,Hints,Gen,Faith,Verify,NeMoOut api;
    class DB,Qdrant,Neo4j,Ollama,Profiles db;
```

---

## 2. Structural Layer Breakdowns

### A. Client Layer (React + Vite)
- **Chat Interface (`ChatInterface.tsx`)**: Captures user queries, presents immediate pipeline status updates via `<ThinkingPills />`, and streams tokens in real-time.
- **Server-Sent Events (SSE)**: Communications go through `aiService.ts`. Streaming events are mapped from backend status changes into UI labels:
  - `Checking message safety...` $\rightarrow$ **Safety check**
  - `Understanding your question...` $\rightarrow$ **Understanding**
  - `Searching knowledge base...` $\rightarrow$ **Searching wisdom**
  - `Composing / Generating / Verifying` $\rightarrow$ **Composing & Verifying**
- **User Storage**:
  - *Anonymous users*: Saved purely to browser `localStorage` (`chatStorage.ts`).
  - *Authenticated users*: Synchronized seamlessly with your PostgreSQL database (`chatPersistence.ts`).

### B. Service & Orchestration Layer (FastAPI + LangGraph)
- **Entry point**: `app/main.py` hosts the `/api/chat/stream` SSE endpoint.
- **Input Moderation**: NeMo Guardrails check the query for semantic safety before it hits the pipeline.
- **Depression Detector**: A fast-path classifier that checks for user distress. If distress is detected, it returns an immediate fallback prompt pointing directly to meditation, bypassing RAG.
- **RAG State Machine (`rag/graph.py`)**: A 12-layer processing state machine:
  1.  **Decompose Query**: Breaks compound queries into focused search terms.
  2.  **CRAG (Corrective RAG) Loop**: Retrieves documents from Qdrant, grades their relevance, and if irrelevant, rewrites the query and tries again (max 3x).
  3.  **Local Generation**: Prompts your locally hosted Ollama model (`sarvam-30b`).
  4.  **Faithfulness & Output Verification**: Grades the answer against source contexts to prevent hallucination, formats it, and runs output guardrail moderation.

### C. Database & Persistence Layer
This architecture leverages three databases, each highly optimized for a different kind of query:
1.  **Supabase (SQL Database)**: Handles relational and transactional user data (User Auth, display profiles, meditation session logs, daily teachings, and chat history).
2.  **Qdrant (Vector Database)**: Stores semantic embeddings of your wisdom text chunks, executing high-speed cosine-similarity retrieval.
3.  **Neo4j (Graph Database)**: Houses highly structured entity relationship graphs, executing semantic traversal and node path searches.
4.  **Ollama**: Hosts your `sarvam-30b` model locally, running GPU-accelerated inference.
