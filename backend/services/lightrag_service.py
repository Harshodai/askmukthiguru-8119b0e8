import os
import asyncio
import logging
from typing import Optional

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
            return await ollama_model_complete(
                settings.model_for_generation,
                prompt,
                system_prompt=system_prompt,
                history_messages=history_messages,
                host=settings.ollama_base_url,
                **kwargs,
            )

        # Assuming we are hosting bge-m3 via Ollama, or fallback to nomic-embed-text
        embedding_func = EmbeddingFunc(
            embedding_dim=settings.embedding_dimension,
            max_token_size=8192,
            func=lambda texts: ollama_embed(
                texts, 
                embed_model="bge-m3", # Will fallback gracefully to server config
                host=settings.ollama_base_url
            )
        )

        try:
            self.rag = LightRAG(
                working_dir=working_dir,
                llm_model_func=llm_func,
                embedding_func=embedding_func,
                graph_storage="Neo4JStorage",
                vector_storage="QdrantVectorDBStorage",
                chunk_token_size=settings.rag_chunk_size,
            )
            
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
        if not self.rag:
            logger.warning("LightRAG is not active, returning empty context.")
            return ""
            
        from lightrag import QueryParam
        try:
            logger.info(f"Querying LightRAG graph (mode={mode})...")
            return await self.rag.aquery(query, param=QueryParam(mode=mode))
        except Exception as e:
            logger.error(f"LightRAG query failed: {e}")
            return ""

    def insert(self, text: str):
        """Insert new content into the graph (synchronously triggered)."""
        if not self.rag:
            logger.warning("LightRAG is not active, skipping graph extraction.")
            return
        
        logger.info(f"Extracting graph entities for inserted text ({len(text)} chars)...")
        self.rag.insert(text)

# Singleton export
lightrag_service = LightRAGService()
