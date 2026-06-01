import asyncio
import logging
import os

from lightrag import LightRAG
from lightrag.utils import EmbeddingFunc
from tenacity import retry, stop_after_attempt, wait_exponential

from app.config import settings

logger = logging.getLogger(__name__)


class LightRAGService:
    """
    Singleton service wrapper around LightRAG.
    Orchestrates graph-based extraction and retrieval using Neo4j and Qdrant.
    """

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
            cls._instance.rag = None
        return cls._instance

    def __init__(self):
        pass

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
        async def llm_func(prompt, system_prompt=None, history_messages=None, **kwargs) -> str:
            from app.dependencies import get_container

            if history_messages is None:
                history_messages = []
            container = get_container()
            if container.ollama is None:
                logger.warning("LLM service not ready in container")
                return ""

            # Format history (lightrag provides dicts like {"role": "user", "content": "..."})
            context = ""
            for msg in history_messages:
                if isinstance(msg, dict):
                    context += f"\n{msg.get('role', 'user')}: {msg.get('content', '')}"
                elif isinstance(msg, str):
                    context += f"\n{msg}"
                else:
                    context += f"\n{str(msg)}"

            # Route ALL LightRAG internal LLM tasks to a fast non-reasoning model.
            # Prevents reasoning model runaway (15+ KB thinking traces, 15-30s latency)
            # from blocking LightRAG keyword extraction and defeating the anti-hallucination pipeline.
            if settings.llm_provider == "sarvam_cloud":
                sys_prompt_str = system_prompt or ""
                prompt_str = prompt or ""

                # All LightRAG operations run on sarvam-m for high throughput and zero reasoning overhead
                kwargs["model"] = "sarvam-m"
                kwargs["max_tokens"] = min(kwargs.get("max_tokens", 2048), 2048)

                is_extraction = (
                    "Knowledge Graph" in sys_prompt_str
                    or "entity" in sys_prompt_str
                    or "relation" in sys_prompt_str
                    or "Extract entities" in prompt_str
                    or "Data to be Processed" in prompt_str
                    or kwargs.get("keyword_extraction", False)
                    or "keyword" in prompt_str.lower()
                    or "keyword" in sys_prompt_str.lower()
                )

                if is_extraction:
                    kwargs["is_structured"] = True
                    kwargs["operation"] = "extraction"
                    logger.info(
                        "LightRAG: Routing extraction/keyword task to sarvam-m to prevent reasoning runaway"
                    )
                elif (
                    "summary" in sys_prompt_str.lower()
                    or "merge" in sys_prompt_str.lower()
                    or "summary" in prompt_str.lower()
                    or "merge" in prompt_str.lower()
                ):
                    kwargs["is_structured"] = True
                    kwargs["operation"] = "summarize"
                    logger.info(
                        "LightRAG: Routing summarization task to sarvam-m to prevent reasoning runaway"
                    )
                else:
                    logger.info(
                        "LightRAG: Routing generic query task to sarvam-m to prevent reasoning runaway"
                    )

            # Route LightRAG calls to the fast model (no reasoning).
            # The main reasoning model produces 15+ KB thinking traces on broad queries,
            # causing 30s timeouts in LightRAG's internal keyword extraction pipeline.
            # The fast model (llama3.2:3b / qwen3:3b) handles extraction in 1-3s with zero overhead.
            # sarvam_cloud already routes to sarvam-m above; this handles the Ollama path.
            if settings.llm_provider == "sarvam_cloud":
                return await container.ollama.generate(
                    system_prompt=system_prompt or "You are a helpful assistant.",
                    user_prompt=prompt,
                    context=context,
                    **kwargs,
                )
            else:
                # Ollama: force the fast classification model for ALL LightRAG internals.
                # timeout=25 gives 3× headroom over typical 5-8s fast-model calls.
                return await container.ollama._generate_fast(
                    system_prompt=system_prompt or "You are a helpful assistant.",
                    user_prompt=prompt,
                    context=context,
                    timeout=25,
                    max_retries=2,
                    **kwargs,
                )

        # Use our local BGE-M3 model already loaded in memory instead of calling Ollama API
        import asyncio

        import numpy as np

        async def embed_func(texts: list[str]) -> np.ndarray:
            from app.dependencies import get_container

            container = get_container()
            if container.embedding is None:
                logger.warning("Embedding service not ready in container")
                return np.zeros((len(texts), settings.embedding_dimension))
            # encode_batch returns {'dense': list[list[float]], 'sparse': ...}
            # LightRAG requires a numpy array. Run in thread pool to avoid blocking event loop.
            batch_result = await asyncio.to_thread(container.embedding.encode_batch, texts)
            dense_vectors = batch_result["dense"]
            return np.array(dense_vectors)

        embedding_func = EmbeddingFunc(
            embedding_dim=settings.embedding_dimension,
            max_token_size=8192,
            func=embed_func,
            model_name=settings.embedding_model,
        )

        # Pre-flight: Verify Neo4j is reachable before attempting LightRAG construction
        # NOTE: verify_connectivity() is synchronous — must run in thread to avoid blocking event loop
        def _check_neo4j():
            from neo4j import GraphDatabase

            driver = GraphDatabase.driver(
                settings.neo4j_uri,
                auth=(settings.neo4j_user, settings.neo4j_password),
            )
            driver.verify_connectivity()
            driver.close()

        try:
            await asyncio.to_thread(_check_neo4j)
            logger.info("Neo4j connectivity verified.")
        except Exception as e:
            logger.warning(
                f"⚠️ Neo4j unreachable ({e}). LightRAG will operate in DEGRADED mode — "
                f"graph enrichment is disabled. Vector-only retrieval remains active."
            )
            self._initialized = False
            return

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

    async def aquery(
        self, query: str, mode: str = "hybrid", only_need_context: bool = False
    ) -> str:
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
            logger.info(
                f"Querying LightRAG graph (mode={mode}, only_need_context={only_need_context})..."
            )
            return await self.rag.aquery(
                query, param=QueryParam(mode=mode, only_need_context=only_need_context)
            )
        except Exception as e:
            # Check for common initialization error and retry once
            if "JsonDocStatusStorage not initialized" in str(e):
                logger.warning("LightRAG storage not initialized, retrying...")
                await self.rag.initialize_storages()
                return await self.rag.aquery(
                    query, param=QueryParam(mode=mode, only_need_context=only_need_context)
                )
            logger.error(f"LightRAG query failed: {e}")
            return ""

    async def ainsert(
        self, text: str, file_paths: str | list[str] | None = None, timeout: float = 180.0
    ):
        """Insert new content into the graph asynchronously.

        Args:
            text: Text to extract entities from and insert into graph.
            file_paths: Optional source file paths for provenance tracking.
            timeout: Maximum seconds to wait for LightRAG internal extraction + merging.
                     Default 180s prevents runaway Sarvam API retry storms from blocking indefinitely.
        """
        if not self._initialized:
            await self.initialize()

        if not self.rag:
            logger.warning("LightRAG is not active, skipping graph extraction.")
            return

        logger.info(f"Extracting graph entities for inserted text ({len(text)} chars)...")
        try:
            await asyncio.wait_for(self.rag.ainsert(text, file_paths=file_paths), timeout=timeout)
        except TimeoutError:
            logger.warning(
                f"LightRAG ainsert timed out after {timeout:.0f}s for text ({len(text)} chars). "
                f"Skipping this chunk — Qdrant vectors are already indexed."
            )
        except Exception as e:
            # Check for common initialization error and retry once
            if "JsonDocStatusStorage not initialized" in str(e):
                logger.warning("LightRAG storage not initialized during insertion, retrying...")
                await self.rag.initialize_storages()
                try:
                    await asyncio.wait_for(
                        self.rag.ainsert(text, file_paths=file_paths), timeout=timeout
                    )
                except TimeoutError:
                    logger.warning(
                        f"LightRAG ainsert timed out after retry ({timeout:.0f}s). Skipping."
                    )
            else:
                raise

    async def safe_ainsert(
        self, text: str, file_paths: str | list[str] | None = None, timeout: float = 180.0
    ) -> bool:
        """Insert into graph with full error suppression. Returns True on success, False on failure.

        Used by ingestion scripts where LightRAG is enrichment (not critical path).
        Qdrant vector ingestion is the primary store — graph extraction is bonus.
        """
        try:
            await self.ainsert(text, file_paths=file_paths, timeout=timeout)
            return True
        except Exception as e:
            logger.error(f"LightRAG safe_ainsert failed (non-fatal): {e}")
            return False

    async def ainsert_chunked(
        self,
        text: str,
        file_paths: str | list[str] | None = None,
        max_chunk_size: int = 8000,
        overlap: int = 500,
        sleep_between: float = 3.0,
    ):
        """Insert large texts into the graph in chunks to prevent SIGSEGV or OOM errors."""
        if not self._initialized:
            await self.initialize()

        if not self.rag:
            logger.warning("LightRAG is not active, skipping graph extraction.")
            return

        def chunk_text(t: str, size: int, ov: int) -> list[str]:
            """FIXED: 1-char sliding window bug. See bulk_ingest_whisper.py."""
            chunks = []
            start = 0
            while start < len(t):
                end = min(start + size, len(t))
                if end < len(t):
                    for boundary_char in [". ", ".\n", "!\n", "?\n", "! ", "? "]:
                        last_boundary = t.rfind(boundary_char, start + size // 2, end)
                        if last_boundary != -1:
                            end = last_boundary + len(boundary_char)
                            break
                chunk = t[start:end].strip()
                if chunk:
                    chunks.append(chunk)
                if end >= len(t):
                    break
                # Advance window — MUST make meaningful progress
                next_start = end - ov
                if next_start <= start:
                    next_start = end  # Skip overlap to prevent 1-char slide
                start = next_start
            return chunks

        chunks = chunk_text(text, max_chunk_size, overlap)
        total = len(chunks)
        logger.info(f"LightRAG: Splitting {len(text):,} chars into {total} chunks")

        for i, chunk in enumerate(chunks, 1):
            logger.info(f"LightRAG: Inserting chunk {i}/{total} ({len(chunk):,} chars)")
            try:
                await self.ainsert(chunk, file_paths=file_paths)
            except Exception as e:
                logger.error(f"LightRAG: Chunk {i}/{total} failed: {e}")
            if i < total:
                await asyncio.sleep(sleep_between)


# Singleton export
lightrag_service = LightRAGService()
