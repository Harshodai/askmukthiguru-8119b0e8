"""
Mukthi Guru — Ollama LLM Service

Design Patterns:
  - Facade Pattern: Wraps langchain-ollama behind domain-specific methods
  - Template Method: Each LLM task (classify, grade, generate) has its own
    method with tailored prompts and parsing
  - Single Responsibility: Each method does ONE thing with the LLM
  - Dual-Model Strategy: Uses fast 3B model for classification, full 30B for generation

All LLM calls funnel through this service. No other module talks to Ollama directly.
This makes it trivial to swap the LLM provider (e.g., to a Colab-hosted model).
"""

import logging
from typing import Optional, AsyncIterator

from langchain_ollama import ChatOllama
from langchain_core.messages import HumanMessage, SystemMessage

from app.config import settings
from rag.prompts import (
    INTENT_CLASSIFICATION_PROMPT,
    GRADE_RELEVANCE_PROMPT,
    FAITHFULNESS_CHECK_PROMPT,
    HINT_EXTRACTION_PROMPT,
    QUERY_REWRITE_PROMPT,
    VERIFICATION_PROMPT,
    SUMMARIZE_PROMPT,
    DECOMPOSE_QUERY_PROMPT,
    HYDE_PROMPT,
    IS_COMPLEX_QUERY_PROMPT,
    BATCH_GRADE_PROMPT,
    COMBINED_VERIFICATION_PROMPT,
)

logger = logging.getLogger(__name__)


class OllamaService:
    """
    Gateway to all LLM operations.
    
    Uses a dual-model strategy:
    - _llm (Sarvam 30B): Full generation, verification, summarization
    - _llm_fast (llama3.2:3b): Intent classification, grading, complexity checks
    
    Classification tasks use the fast model for ~10x speed improvement
    while generation tasks use the full model for quality.
    """

    def __init__(self) -> None:
        """Initialize the Ollama LLM clients (main + fast classifier)."""
        gen_model = settings.model_for_generation
        cls_model = settings.model_for_classification

        # Main model — for generation and verification
        self._llm = ChatOllama(
            base_url=settings.ollama_base_url,
            model=gen_model,
            temperature=0.1,  # Low temp for factual accuracy
            num_predict=1024,  # Max output tokens (increased for richer spiritual explanations)
        )
        logger.info(f"Ollama main model ready: {gen_model} (preset: {settings.model_preset})")

        # Fast model — for classification tasks
        self._llm_fast = ChatOllama(
            base_url=settings.ollama_base_url,
            model=cls_model,
            temperature=0.0,  # Zero temp for deterministic classification
            num_predict=256,  # Classification outputs are short
        )
        logger.info(f"Ollama fast model ready: {cls_model}")

    async def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        context: str = "",
        **kwargs,
    ) -> str:
        """
        Core generation method using the main (Sarvam 30B) model.
        
        Args:
            system_prompt: Role and constraints for the LLM
            user_prompt: User's input with any injected context
            context: Retrieved documents (inserted into the prompt)
            **kwargs: Additional model parameters (temperature, top_k, etc.)
        """
        messages = [SystemMessage(content=system_prompt)]

        if context:
            full_prompt = f"Context:\n{context}\n\nQuestion: {user_prompt}"
        else:
            full_prompt = user_prompt

        messages.append(HumanMessage(content=full_prompt))

        try:
            # Bind runtime args like temperature
            chain = self._llm.bind(**kwargs) if kwargs else self._llm
            response = await chain.ainvoke(messages)
            return response.content.strip()
        except Exception as e:
            logger.error(f"Ollama generation failed: {e}")
            raise

    async def _generate_fast(
        self,
        system_prompt: str,
        user_prompt: str,
        **kwargs,
    ) -> str:
        """
        Fast classification using the lightweight model (llama3.2:3b).
        
        Used for binary/ternary classification tasks where the full 30B
        model is overkill. ~10x faster for intent, grading, complexity checks.
        """
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ]

        try:
            chain = self._llm_fast.bind(**kwargs) if kwargs else self._llm_fast
            response = await chain.ainvoke(messages)
            return response.content.strip()
        except Exception as e:
            # Fall back to main model if fast model fails
            logger.warning(f"Fast model failed, falling back to main: {e}")
            return await self.generate(system_prompt, user_prompt, **kwargs)

    async def generate_stream(
        self,
        system_prompt: str,
        user_prompt: str,
        context: str = "",
        **kwargs,
    ) -> AsyncIterator[str]:
        """
        Streaming generation using the main model.
        
        Yields tokens as they are generated for SSE streaming.
        """
        messages = [SystemMessage(content=system_prompt)]

        if context:
            full_prompt = f"Context:\n{context}\n\nQuestion: {user_prompt}"
        else:
            full_prompt = user_prompt

        messages.append(HumanMessage(content=full_prompt))

        try:
            chain = self._llm.bind(**kwargs) if kwargs else self._llm
            async for chunk in chain.astream(messages):
                if chunk.content:
                    yield chunk.content
        except Exception as e:
            logger.error(f"Ollama streaming failed: {e}")
            raise

    async def classify_intent(self, message: str) -> str:
        """
        Classify user message into one of three intents.
        
        Returns: 'DISTRESS' | 'QUERY' | 'CASUAL'
        
        Uses the fast model for ~10x speed improvement.
        """
        result = await self._generate_fast(INTENT_CLASSIFICATION_PROMPT, message)
        
        # Parse — be lenient with LLM output
        result_upper = result.upper().strip()
        if "DISTRESS" in result_upper:
            return "DISTRESS"
        elif "QUERY" in result_upper:
            return "QUERY"
        else:
            return "CASUAL"

    async def grade_relevance(self, query: str, document: str) -> bool:
        """
        CRAG: Binary relevance grading of a retrieved document.
        
        Returns True if the document is relevant to the query.
        Uses the fast model for speed.
        """
        prompt = f"Question: {query}\n\nDocument: {document}"
        result = await self._generate_fast(GRADE_RELEVANCE_PROMPT, prompt)
        return "yes" in result.lower()

    async def batch_grade_relevance(self, query: str, documents: list[str]) -> list[bool]:
        """
        CRAG: Batch relevance grading of multiple documents in one LLM call.

        Instead of N separate calls (one per document), grades all documents
        at once with a structured prompt. Reduces LLM calls from N to 1.
        Uses the fast model for speed.

        Returns: List of booleans, one per document (True = relevant).
        """
        if not documents:
            return []

        # Build numbered document list
        numbered_docs = "\n\n".join(
            f"Document {i+1}:\n{doc[:1500]}"  # Truncate individual docs to fit context
            for i, doc in enumerate(documents)
        )

        prompt = f"Question: {query}\n\n{numbered_docs}"
        result = await self._generate_fast(BATCH_GRADE_PROMPT, prompt)

        # Parse "1: yes\n2: no\n3: yes" format
        relevance = [False] * len(documents)
        for line in result.strip().splitlines():
            line = line.strip()
            if ":" in line:
                parts = line.split(":", 1)
                try:
                    idx = int(parts[0].strip()) - 1  # 1-indexed → 0-indexed
                    if 0 <= idx < len(documents):
                        relevance[idx] = "yes" in parts[1].lower()
                except (ValueError, IndexError):
                    continue

        return relevance

    async def check_faithfulness(self, answer: str, context: str) -> bool:
        """
        Self-RAG: Check if the generated answer is faithful to the context.
        
        Returns True if EVERY claim in the answer is supported by the context.
        Returns False if ANY unsupported claim is detected.
        
        Uses the fast model for speed.
        """
        prompt = f"Context:\n{context}\n\nAnswer:\n{answer}"
        result = await self._generate_fast(FAITHFULNESS_CHECK_PROMPT, prompt)
        return "faithful" in result.lower()

    async def extract_hints(self, query: str, documents: list[str]) -> list[str]:
        """
        Stimulus RAG: Extract key evidence hints from retrieved documents.
        
        Instead of dumping raw documents into the generation prompt,
        we first extract the most relevant phrases/sentences. This focuses
        the LLM's attention on precise evidence rather than noisy context.
        
        Returns: List of 3-5 key hint phrases
        """
        combined_docs = "\n---\n".join(documents)
        system = HINT_EXTRACTION_PROMPT
        prompt = f"Question: {query}\n\nDocuments:\n{combined_docs}"
        
        result = await self.generate(system, prompt)
        
        # Parse hints from bullet points
        hints = []
        for line in result.split("\n"):
            line = line.strip()
            if line.startswith("- ") or line.startswith("• "):
                hints.append(line[2:].strip())
            elif line and not line.startswith("#"):
                hints.append(line)
        
        return hints[:5]  # Cap at 5 hints

    async def rewrite_query(self, original_query: str) -> str:
        """
        CRAG: Rewrite a query to improve retrieval quality.
        
        Uses the main model for better query expansion with spiritual terminology.
        """
        return await self.generate(QUERY_REWRITE_PROMPT, f"Original query: {original_query}")

    async def verify_claims(self, answer: str, context: str) -> dict:
        """
        Chain of Verification (CoVe): Generate verification questions and check.
        
        This is the FINAL safety net (layer 11). Uses the main model.
        """
        prompt = f"Answer:\n{answer}\n\nContext:\n{context}"
        result = await self.generate(VERIFICATION_PROMPT, prompt)
        
        # Parse the VERDICT line robustly
        lines = result.upper().strip().splitlines()
        verdict_line = ""
        for line in reversed(lines):
            if "VERDICT" in line:
                verdict_line = line
                break
        
        if verdict_line:
            after_verdict = verdict_line.split("VERDICT", 1)[-1]
            passed = "PASS" in after_verdict and "FAIL" not in after_verdict
        else:
            logger.warning(
                "CoVe: No VERDICT line found in verification output. "
                f"Raw result (first 200 chars): {result[:200]!r}"
            )
            passed = False
        
        return {
            "passed": passed,
            "details": result,
        }

    async def combined_verify(self, answer: str, context: str) -> dict:
        """
        Combined Self-RAG + CoVe verification in a single LLM call.

        Merges faithfulness checking (layer 10) and claim verification (layer 11)
        into one structured prompt, reducing 2 LLM calls to 1.
        Also extracts a confidence score (1-10) for graduated response gating.

        Returns:
            Dict with 'is_faithful' (bool), 'passed' (bool),
            'confidence' (float), 'details' (str)
        """
        system = COMBINED_VERIFICATION_PROMPT
        prompt = f"Answer:\n{answer}\n\nContext:\n{context}"

        result = await self.generate(system, prompt, temperature=0.0)

        result_upper = result.upper().strip()
        lines = result_upper.splitlines()

        # Parse FAITHFULNESS line
        is_faithful = False
        for line in lines:
            if "FAITHFULNESS" in line:
                after = line.split("FAITHFULNESS", 1)[-1]
                is_faithful = "FAITHFUL" in after and "HALLUCINATED" not in after
                break

        # Parse VERDICT line
        passed = False
        for line in reversed(lines):
            if "VERDICT" in line:
                after = line.split("VERDICT", 1)[-1]
                passed = "PASS" in after and "FAIL" not in after
                break

        # Parse CONFIDENCE line (1-10)
        confidence = 5.0  # Default mid-range
        for line in lines:
            if "CONFIDENCE" in line:
                after = line.split("CONFIDENCE", 1)[-1]
                # Extract first number from the line
                import re
                nums = re.findall(r'\d+', after)
                if nums:
                    try:
                        confidence = float(min(int(nums[0]), 10))
                    except (ValueError, IndexError):
                        pass
                break

        # Both must pass
        final_passed = is_faithful and passed

        if not final_passed:
            logger.info(
                f"Combined verify: faithful={is_faithful}, verdict_pass={passed}, "
                f"confidence={confidence}"
            )

        return {
            "is_faithful": is_faithful,
            "passed": final_passed,
            "confidence": confidence,
            "details": result,
        }

    async def summarize(self, texts: list[str]) -> str:
        """
        Summarize a cluster of text chunks (used by RAPTOR).
        
        Creates mid-level tree nodes that capture thematic relationships
        between individual chunks. Uses the main model for quality.
        """
        combined = "\n\n".join(texts)
        return await self.generate(SUMMARIZE_PROMPT, combined)

    async def decompose_query(self, query: str) -> list[str]:
        """
        Query Decomposition: Split complex questions into atomic sub-queries.
        
        Returns: List of 2-3 simpler sub-queries.
        Uses the fast model since this is a classification/parsing task.
        """
        result = await self._generate_fast(DECOMPOSE_QUERY_PROMPT, query)
        
        sub_queries = []
        for line in result.split("\n"):
            line = line.strip()
            if line.startswith("- ") or line.startswith("• "):
                sub_queries.append(line[2:].strip())
            elif line.startswith(("1.", "2.", "3.")):
                sub_queries.append(line[2:].strip())
        
        return sub_queries if sub_queries else [query]

    async def generate_hypothetical_answer(self, query: str) -> str:
        """
        HyDE (Hypothetical Document Embeddings): Generate a fake answer.
        
        Uses the main model for quality hypothetical generation.
        """
        return await self.generate(HYDE_PROMPT, query)

    async def is_complex_query(self, query: str) -> bool:
        """
        Determine if a query needs decomposition.
        
        Uses the fast model since this is a binary classification.
        """
        result = await self._generate_fast(IS_COMPLEX_QUERY_PROMPT, query)
        return "complex" in result.lower()

    async def health_check(self) -> bool:
        """Check if Ollama is reachable (async)."""
        try:
            import httpx
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"{settings.ollama_base_url}/api/tags", timeout=5
                )
            return resp.status_code == 200
        except Exception:
            return False
