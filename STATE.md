# STATE.md — Mukthi Guru Build State

## Current Status
- **Phase**: All code phases complete (1-8). World-class optimization phases 3-4 applied.
- **Last Updated**: 2026-03-19
- **Next Action**: Full integration test with Docker stack

## Phases
| # | Phase | Status | Files |
|---|-------|--------|-------|
| 1 | Infrastructure | ✅ Done | 10 |
| 2 | Services Layer | ✅ Done | 4 |
| 3 | Ingestion Pipeline | ✅ Done | 5 |
| 4 | LangGraph RAG | ✅ Done | 5 |
| 5 | NeMo Guardrails | ✅ Done | 3 |
| 6 | FastAPI Server | ✅ Done | 2 |
| 7 | Colab Setup | ✅ Done | 1 |
| 8 | World-Class Optimization | ✅ Done | 12 |

## Optimization Items Applied (Phase 8)
- Dual-model strategy (Sarvam 30B + llama3.2:3b for classification)
- SSE streaming (backend `/api/chat/stream` + frontend `sendMessageStream`)
- MMR diversity in retrieval results
- Contextual compression (sentence-level reranking)
- Confidence-based answer gating (graduated responses 1-10)
- Fixed orphaned code in `ollama_service.py`

## Total: 31+ files

## To Run Locally
```bash
cd backend

# Terminal 1: Start Ollama (runs in foreground)
ollama serve

# Terminal 2: Download models (choose your preset)
cd models
./download_models.sh qwen      # Default: Qwen3 (works with ollama pull)
# OR: ./download_models.sh sarvam   # Sarvam (GGUF from HuggingFace)
# OR: ./download_models.sh all      # Both presets
# Windows: .\download_models.ps1 qwen
cd ..

# Terminal 3: Start Docker stack
docker compose up -d

# Terminal 4: Run the app
# Option A: Docker (recommended)
docker compose up -d --build
# Option B: Direct
python -m uvicorn app.main:app --reload
```

## To Run on Colab
```bash
# Native setup: installs deps via pip, Ollama natively (GPU),
# Qdrant in embedded mode, backend via direct uvicorn
python colab/setup.py
```
