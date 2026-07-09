from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import time
from typing import Optional

from lightrag.lightrag import LightRAG
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
        self._query_cache = {}  # {query_hash: (results, timestamp)}
        self._cache_ttl_seconds = 300  # 5 min TTL

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

        def sanitize_extraction_output(text: str) -> str:
            """Sanitize extraction to remove thinking blocks, clean up quotes, backslashes, and malformed types."""
            import re
            
            # Remove thinking blocks if any
            text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
            # Remove ```json wrapper if present
            text = re.sub(r"```json\s*", "", text)
            text = re.sub(r"\s*```", "", text)
            
            cleaned_lines = []
            for line in text.splitlines():
                line_str = line.strip()
                if not line_str:
                    cleaned_lines.append("")
                    continue
                
                # Match parenthesized tuples: ("field1", "field2", "field3", ...)
                if line_str.startswith("(") and line_str.endswith(")"):
                    # Find quoted values inside the tuple
                    fields = re.findall(r'"([^"\\]*(?:\\.[^"\\]*)*)"|\'([^\'\\]*(?:\\.[^\'\\]*)*)\'', line_str)
                    field_values = [f[0] or f[1] for f in fields]
                    
                    if len(field_values) >= 3:
                        # Clean each field of literal double quotes and backslashes
                        for i in range(min(len(field_values), 3)):
                            val = field_values[i]
                            val = val.replace('"', '').replace('\\', '')
                            
                            # Normalize entity_type (2nd field of a 3-field entity tuple)
                            if len(field_values) == 3 and i == 1:
                                val_clean = val.strip().upper()
                                if not val_clean or len(val_clean) > 50 or "INCORRECT" in val_clean or "DELIMITER" in val_clean:
                                    val_clean = "CONCEPT"
                                val = val_clean
                            field_values[i] = val
                        
                        # Rebuild quoted fields
                        quoted_fields = [f'"{f}"' for f in field_values]
                        
                        # If relationship tuple (4+ fields), preserve weight as number
                        if len(field_values) >= 4:
                            weight_part = line_str.split(",")[-1].strip(" )\"'")
                            try:
                                weight = float(weight_part)
                                quoted_fields[-1] = str(weight)
                            except ValueError:
                                pass
                        
                        cleaned_lines.append(f"({', '.join(quoted_fields)})")
                    else:
                        if len(line_str) > 100:
                            cleaned_lines.append(line_str.strip("()"))
                        else:
                            cleaned_lines.append(line_str)
                else:
                    if "incorrect" in line_str.lower() or "delimiter" in line_str.lower():
                        continue
                    cleaned_lines.append(line_str)
                    
            return "\n".join(cleaned_lines).strip()

        # Dynamically bridge our main generative LLM to LightRAG
        # We use a fast, non-reasoning classifier model for LightRAG's internal operations.
        # This keeps graph extraction, summaries, and keyword search fast and clean.
        
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

            sys_prompt_str = system_prompt or ""
            prompt_str = prompt or ""
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

            # Route ALL LightRAG internal LLM tasks to a fast non-reasoning model.
            # Prevents reasoning model runaway (15+ KB thinking traces, 15-30s latency)
            # from blocking LightRAG keyword extraction and defeating the anti-hallucination pipeline.
            openrouter = getattr(container, "openrouter", None)
            
            response = ""
            if openrouter and getattr(settings, "openrouter_api_key", None):
                kwargs["model"] = settings.openrouter_classify_model
                kwargs["max_tokens"] = min(kwargs.get("max_tokens", 2048), 2048)

                if is_extraction:
                    kwargs["is_structured"] = True
                    kwargs["operation"] = "extraction"
                    logger.info(
                        f"LightRAG: Routing extraction/keyword task to OpenRouter ({settings.openrouter_classify_model})"
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
                        f"LightRAG: Routing summarization task to OpenRouter ({settings.openrouter_classify_model})"
                    )
                else:
                    logger.info(
                        f"LightRAG: Routing generic query task to OpenRouter ({settings.openrouter_classify_model})"
                    )

                try:
                    response = await openrouter.generate(
                        system_prompt=system_prompt or "You are a helpful assistant.",
                        user_prompt=prompt,
                        context=context,
                        **kwargs,
                    )
                except Exception as e:
                    logger.warning(f"LightRAG: OpenRouter task failed ({e}), falling back to default LLM")
                    response = ""

            if not response:
                provider = settings.llm_provider.lower()
                
                # For Sarvam Cloud, use classification model to prevent reasoning runaway
                if provider == "sarvam_cloud":
                    kwargs["model"] = settings.model_for_classification
                    kwargs["max_tokens"] = min(kwargs.get("max_tokens", 2048), 2048)

                    if is_extraction:
                        kwargs["is_structured"] = True
                        kwargs["operation"] = "extraction"
                        logger.info(
                            f"LightRAG: Routing extraction/keyword task to {settings.model_for_classification} to prevent reasoning runaway"
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
                            f"LightRAG: Routing summarization task to {settings.model_for_classification} to prevent reasoning runaway"
                        )
                    else:
                        logger.info(
                            f"LightRAG: Routing generic query task to {settings.model_for_classification} to prevent reasoning runaway"
                        )

                    response = await container.ollama.generate(
                        system_prompt=system_prompt or "You are a helpful assistant.",
                        user_prompt=prompt,
                        context=context,
                        **kwargs,
                    )
                
                # For OpenRouter, use _generate_fast (which uses classify model internally)
                elif provider == "openrouter":
                    response = await container.openrouter._generate_fast(
                        system_prompt=system_prompt or "You are a helpful assistant.",
                        user_prompt=prompt,
                        context=context,
                        timeout=25,
                        max_retries=2,
                        **kwargs,
                    )
                
                # For Ollama and other providers, use _generate_fast
                else:
                    # Force the fast classification model for ALL LightRAG internals.
                    # timeout=25 gives 3× headroom over typical 5-8s fast-model calls.
                    response = await container.ollama._generate_fast(
                        system_prompt=system_prompt or "You are a helpful assistant.",
                        user_prompt=prompt,
                        context=context,
                        timeout=25,
                        max_retries=2,
                        **kwargs,
                    )

            if is_extraction and isinstance(response, str):
                response = sanitize_extraction_output(response)
                
            return response

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
            logger.error(f"❌ Neo4j unreachable: {e}. GraphRAG requires Neo4j connectivity. Halting startup.")
            raise RuntimeError(f"Neo4j connection failed: {e}") from e

        @retry(stop=stop_after_attempt(5), wait=wait_exponential(multiplier=1, min=2, max=10))
        def _create_lightrag():
            return LightRAG(
                working_dir=working_dir,
                llm_model_func=llm_func,
                embedding_func=embedding_func,
                graph_storage="Neo4JStorage",
                vector_storage="QdrantVectorDBStorage",
                chunk_token_size=settings.rag_chunk_size,
                embedding_func_max_async=8,
                llm_model_max_async=4,
                max_parallel_insert=4,
            )

        try:
            self.rag = _create_lightrag()

            # Inject Custom Spiritual Guidance into LightRAG Prompts
            try:
                import lightrag.prompt
                lightrag.prompt.PROMPTS["default_entity_types_guidance"] = (
                    "- Teacher: Spiritual leaders, guides, or organizations teaching wisdom (e.g. Sadhguru, Sri Preethaji, Sri Krishnaji, Sri Amma Bhagavan, ISKCON)\n"
                    "- Concept: Core spiritual ideas, beliefs, or states of mind (e.g. Karma, Dharma, Consciousness, Beautiful State, Suffering, Oneness)\n"
                    "- Practice: Specific techniques, rituals, exercises, or yoga postures (e.g. Serene Mind, Soul Sync, Meditation, Yoga, Breathwork)\n"
                    "- Event: Spiritual gatherings, retreats, discourses, or festivals\n"
                    "- Organization: Spiritual institutions, foundations, or ashrams\n"
                    "- Location: Sacred sites, temples, centers, or geographical areas\n"
                    "- Other: Entities that do not fit the above categories"
                )
                spiritual_guidance = (
                    "\n\n"
                    "---Spiritual Domain Guidance---\n"
                    "When extracting entities from spiritual transcripts, pay close attention to:\n"
                    "- Teachers: Sadhguru, Sri Preethaji, Sri Krishnaji, Sri Amma Bhagavan, ISKCON.\n"
                    "- Concepts: Karma, Dharma, Consciousness, Beautiful State, Suffering, Oneness, Ego.\n"
                    "- Practices: Serene Mind, Soul Sync, Meditation, Yoga, Breathwork.\n"
                    "Extract relationships showing how teachers expound concepts, teach practices, and how practices lead to beautiful states (e.g. EXPOUNDS, TEACHES, PRACTICE_FOR, CONTRASTS_WITH).\n"
                )
                if "entity_extraction_system_prompt" in lightrag.prompt.PROMPTS:
                    lightrag.prompt.PROMPTS["entity_extraction_system_prompt"] += spiritual_guidance
                if "entity_extraction_json_system_prompt" in lightrag.prompt.PROMPTS:
                    lightrag.prompt.PROMPTS["entity_extraction_json_system_prompt"] += spiritual_guidance
                logger.info("Spiritual domain guidance and custom entity types injected into LightRAG prompts.")
            except Exception as pe:
                logger.warning(f"Failed to inject custom spiritual prompts to LightRAG: {pe}")

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
        Execute GraphRAG query async with 5-min result caching.
        Supported Modes: 'local' (entities), 'global' (community summaries), 'hybrid' (both)
        """
        # ponytail: 5min TTL cache for identical queries
        cache_key = hashlib.md5(f"{query}:{mode}:{only_need_context}".encode()).hexdigest()
        if cache_key in self._query_cache:
            results, ts = self._query_cache[cache_key]
            if time.time() - ts < self._cache_ttl_seconds:
                logger.info(f"LightRAG cache hit for query (age={time.time()-ts:.1f}s)")
                return results

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
            result = await self.rag.aquery(
                query, param=QueryParam(mode=mode, only_need_context=only_need_context)
            )
            # Cache result
            self._query_cache[cache_key] = (result, time.time())
            return result
        except Exception as e:
            # Check for common initialization error and retry once
            if "JsonDocStatusStorage not initialized" in str(e):
                logger.warning("LightRAG storage not initialized, retrying...")
                await self.rag.initialize_storages()
                result = await self.rag.aquery(
                    query, param=QueryParam(mode=mode, only_need_context=only_need_context)
                )
                self._query_cache[cache_key] = (result, time.time())
                return result
            logger.error(f"LightRAG query failed: {e}")
            return ""

    async def ainsert(
        self, text: str, file_paths: str | Optional[list[str]] = None, timeout: float = 180.0
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
        self, text: str, file_paths: str | Optional[list[str]] = None, timeout: float = 180.0
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
        file_paths: str | Optional[list[str]] = None,
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
