import os
import asyncio
import logging
from typing import Optional
from tenacity import retry, stop_after_attempt, wait_exponential

from lightrag import LightRAG
from lightrag.llm.ollama import ollama_model_complete, ollama_embed
from lightrag.utils import EmbeddingFunc

from app.config import settings

logger = logging.getLogger(__name__)

class LightRAGService:
    """
    Singleton service wrapper around LightRAG.
    Orchestrates graph-based extraction and retrieval using Neo4j and Qdrant.
    """
    _instance = None
    _initialized = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(LightRAGService, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        self.rag: Optional[LightRAG] = None

    async def initialize(self):
        if self._initialized:
            return

        logger.info("Initializing LightRAG Service (Neo4j Graph + Qdrant Vector)...")
        
        # Working directory for LightRAG internal states (e.g., pipeline completion files)
        working_dir = "data/lightrag"
        os.makedirs(working_dir, exist_ok=True)
        
        # Inject Neo4j Configuration
        os.environ["NEO4J_URI"] = settings.neo4j_uri
        os.environ["NEO4J_USERNAME"] = settings.neo4j_user
        os.environ["NEO4J_PASSWORD"] = settings.neo4j_password
        
        # LightRAG Native Qdrant Configuration
        os.environ["QDRANT_URL"] = settings.qdrant_url
        os.environ["QDRANT_COLLECTION"] = f"{settings.qdrant_collection}_lightrag"

        # Dynamically bridge our main generative LLM to LightRAG
        async def llm_func(prompt, system_prompt=None, history_messages=[], **kwargs) -> str:
            from app.dependencies import get_container
            container = get_container()
            if container.ollama is None:
                logger.warning("LLM service not ready in container")
                return ""
            
            # Format history (lightrag provides dicts like {"role": "user", "content": "..."})
            context = ""
            for msg in history_messages:
                context += f"\n{msg.get('role', 'user')}: {msg.get('content', '')}"
                
            return await container.ollama.generate(
                system_prompt=system_prompt or "You are a helpful assistant.",
                user_prompt=prompt,
                context=context
            )

        # Use our local BGE-M3 model already loaded in memory instead of calling Ollama API
        import numpy as np
        import asyncio
        async def embed_func(texts: list[str]) -> np.ndarray:
            from app.dependencies import get_container
            container = get_container()
            if container.embedding is None:
                logger.warning("Embedding service not ready in container")
                return np.zeros((len(texts), settings.embedding_dimension))
            # encode_batch returns {'dense': list[list[float]], 'sparse': ...}
            # LightRAG requires a numpy array. Run in thread pool to avoid blocking event loop.
            batch_result = await asyncio.to_thread(container.embedding.encode_batch, texts)
            dense_vectors = batch_result['dense']
            return np.array(dense_vectors)

        embedding_func = EmbeddingFunc(
            embedding_dim=settings.embedding_dimension,
            max_token_size=8192,
            func=embed_func
        )

        @retry(stop=stop_after_attempt(5), wait=wait_exponential(multiplier=1, min=2, max=10))
        def _create_lightrag():
            return LightRAG(
                working_dir=working_dir,
                llm_model_func=llm_func,
                embedding_func=embedding_func,
                graph_storage="Neo4JStorage",
                vector_storage="QdrantVectorDBStorage",
                chunk_token_size=settings.rag_chunk_size,
            )

        try:
            self.rag = _create_lightrag()
            
            # Async initialize storages (checks DB connections)
            await self.rag.initialize_storages()
            
            self._initialized = True
            logger.info("✅ LightRAG Service successfully initialized.")
        except Exception as e:
            logger.error(f"❌ Failed to initialize LightRAG: {e}", exc_info=True)

    async def aquery(self, query: str, mode: str = "hybrid") -> str:
        """
        Execute GraphRAG query async.
        Supported Modes: 'local' (entities), 'global' (community summaries), 'hybrid' (both)
        """
        if not self._initialized:
            await self.initialize()

        if not self.rag:
            logger.warning("LightRAG is not active, skipping graph query.")
            return "Knowledge graph is currently offline."
            
        from lightrag import QueryParam
        try:
            logger.info(f"Querying LightRAG graph (mode={mode})...")
            return await self.rag.aquery(query, param=QueryParam(mode=mode))
        except Exception as e:
            # Check for common initialization error and retry once
            if "JsonDocStatusStorage not initialized" in str(e):
                logger.warning("LightRAG storage not initialized, retrying...")
                await self.rag.initialize_storages()
                return await self.rag.aquery(query, param=QueryParam(mode=mode))
            logger.error(f"LightRAG query failed: {e}")
            return ""

    async def ainsert(self, text: str):
        """Insert new content into the graph asynchronously."""
        if not self._initialized:
            await self.initialize()

        if not self.rag:
            logger.warning("LightRAG is not active, skipping graph extraction.")
            return
        
        logger.info(f"Extracting graph entities for inserted text ({len(text)} chars)...")
        try:
            await self.rag.ainsert(text)
        except Exception as e:
            # Check for common initialization error and retry once
            if "JsonDocStatusStorage not initialized" in str(e):
                logger.warning("LightRAG storage not initialized during insertion, retrying...")
                await self.rag.initialize_storages()
                await self.rag.ainsert(text)
            else:
                raise

    async def ainsert_chunked(self, text: str, max_chunk_size: int = 8000, overlap: int = 500, sleep_between: float = 3.0):
        """Insert large texts into the graph in chunks to prevent SIGSEGV or OOM errors."""
        if not self._initialized:
            await self.initialize()

        if not self.rag:
            logger.warning("LightRAG is not active, skipping graph extraction.")
            return

        def chunk_text(t: str, size: int, ov: int) -> list[str]:
            chunks = []
            start = 0
            while start < len(t):
                end = min(start + size, len(t))
                if end < len(t):
                    for boundary_char in ['. ', '.\n', '!\n', '?\n', '! ', '? ']:
                        last_boundary = t.rfind(boundary_char, start + size // 2, end)
                        if last_boundary != -1:
                            end = last_boundary + len(boundary_char)
                            break
                chunk = t[start:end].strip()
                if chunk:
                    chunks.append(chunk)
                start = max(start + 1, end - ov)
            return chunks

        chunks = chunk_text(text, max_chunk_size, overlap)
        total = len(chunks)
        logger.info(f"LightRAG: Splitting {len(text):,} chars into {total} chunks")

        for i, chunk in enumerate(chunks, 1):
            logger.info(f"LightRAG: Inserting chunk {i}/{total} ({len(chunk):,} chars)")
            try:
                await self.ainsert(chunk)
            except Exception as e:
                logger.error(f"LightRAG: Chunk {i}/{total} failed: {e}")
            if i < total:
                await asyncio.sleep(sleep_between)

# Singleton export
lightrag_service = LightRAGService()
