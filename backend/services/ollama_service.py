"""
Mukthi Guru — Ollama LLM Service

Design Patterns:
  - Facade Pattern: Wraps langchain-ollama behind domain-specific methods
  - Template Method: Each LLM task (classify, grade, generate) has its own
    method with tailored prompts and parsing
  - Single Responsibility: Each method does ONE thing with the LLM

All LLM calls funnel through this service. No other module talks to Ollama directly.
This makes it trivial to swap the LLM provider (e.g., to a Colab-hosted model).
"""

import logging
from typing import Optional

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
    
    Every method is a specific "capability" of the LLM:
    - generate(): Free-form generation with context
    - classify_intent(): DISTRESS / QUERY / CASUAL routing
    - grade_relevance(): Binary doc relevance check (CRAG)
    - check_faithfulness(): Is the answer grounded? (Self-RAG)
    - extract_hints(): Pull key phrases from docs (Stimulus RAG)
    - rewrite_query(): Expand/rephrase for better retrieval
    - verify_claims(): Generate verification sub-questions (CoVe)
    - summarize(): Condensed summary for RAPTOR tree nodes
    """

    def __init__(self) -> None:
        """Initialize the Ollama LLM client."""
        self._llm = ChatOllama(
            base_url=settings.ollama_base_url,
            model=settings.ollama_model,
            temperature=0.1,  # Low temp for factual accuracy
            num_predict=1024,  # Max output tokens (increased for richer spiritual explanations)
        )
        logger.info(f"Ollama service ready: {settings.ollama_model}")

    async def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        context: str = "",
        **kwargs,
    ) -> str:
        """
        Core generation method. All other methods build on top of this.
        
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

    async def classify_intent(self, message: str) -> str:
        """
        Classify user message into one of three intents.
        
        Returns: 'DISTRESS' | 'QUERY' | 'CASUAL'
        
        This is the first decision point in the pipeline:
        - DISTRESS → triggers Serene Mind meditation
        - QUERY → enters the 11-layer RAG pipeline
        - CASUAL → warm, brief conversational reply
        """
        system = INTENT_CLASSIFICATION_PROMPT

        result = await self.generate(system, message)
        
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
        
        This is layer 6 in the anti-hallucination pipeline.
        If no documents pass this gate, the query gets rewritten (up to 3x).
        """
        system = GRADE_RELEVANCE_PROMPT
        prompt = f"Question: {query}\n\nDocument: {document}"
        
        result = await self.generate(system, prompt)
        return "yes" in result.lower()

    async def batch_grade_relevance(self, query: str, documents: list[str]) -> list[bool]:
        """
        CRAG: Batch relevance grading of multiple documents in one LLM call.

        Instead of N separate calls (one per document), grades all documents
        at once with a structured prompt. Reduces LLM calls from N to 1.

        Returns: List of booleans, one per document (True = relevant).
        """
        if not documents:
            return []

        # Build numbered document list
        numbered_docs = "\n\n".join(
            f"Document {i+1}:\n{doc[:800]}"  # Truncate individual docs to fit context
            for i, doc in enumerate(documents)
        )

        system = BATCH_GRADE_PROMPT
        prompt = f"Question: {query}\n\n{numbered_docs}"

        result = await self.generate(system, prompt)

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
        """
        Self-RAG: Check if the generated answer is faithful to the context.
        
        Returns True if EVERY claim in the answer is supported by the context.
        Returns False if ANY unsupported claim is detected.
        
        This is layer 10 — the post-generation safety net.
        If this fails, the entire answer is discarded.
        """
        system = FAITHFULNESS_CHECK_PROMPT
        prompt = f"Context:\n{context}\n\nAnswer:\n{answer}"
        
        result = await self.generate(system, prompt)
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
        
        When retrieved documents aren't relevant (CRAG grading fails),
        this rewrites the query with:
        - Expanded spiritual terminology
        - Synonym injection
        - Rephrased structure
        
        Part of the self-correcting retrieval loop (max 3 attempts).
        """
        system = QUERY_REWRITE_PROMPT
        
        return await self.generate(system, f"Original query: {original_query}")

    async def verify_claims(self, answer: str, context: str) -> dict:
        """
        Chain of Verification (CoVe): Generate verification questions and check.
        
        This is the FINAL safety net (layer 11). It:
        1. Generates 2-3 verification questions from the answer
        2. Checks if the context can answer them
        3. Returns pass/fail with details
        
        If ANY verification question cannot be answered from context,
        the answer is rejected.
        """
        system = VERIFICATION_PROMPT
        prompt = f"Answer:\n{answer}\n\nContext:\n{context}"
        
        result = await self.generate(system, prompt)
        
        # Parse the VERDICT line robustly
        lines = result.upper().strip().splitlines()
        verdict_line = ""
        for line in reversed(lines):
            if "VERDICT" in line:
                verdict_line = line
                break
        
        if verdict_line:
            # Check the text AFTER "VERDICT" on that line
            after_verdict = verdict_line.split("VERDICT", 1)[-1]
            passed = "PASS" in after_verdict and "FAIL" not in after_verdict
        else:
            # No VERDICT line found — treat as verification failure.
            # Absence of a clear safe verdict must be treated as rejection
            # to prevent unverified answers from reaching the user.
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

        Returns:
            Dict with 'is_faithful' (bool), 'passed' (bool), 'details' (str)
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

        # Both must pass
        final_passed = is_faithful and passed

        if not final_passed:
            logger.info(
                f"Combined verify: faithful={is_faithful}, verdict_pass={passed}"
            )

        return {
            "is_faithful": is_faithful,
            "passed": final_passed,
            "details": result,
        }
        """
        Summarize a cluster of text chunks (used by RAPTOR).
        
        Creates mid-level tree nodes that capture thematic relationships
        between individual chunks.
        """
        combined = "\n\n".join(texts)
        system = SUMMARIZE_PROMPT
        
        return await self.generate(system, combined)

    async def decompose_query(self, query: str) -> list[str]:
        """
        Query Decomposition: Split complex questions into atomic sub-queries.
        
        Only triggered for complex queries (e.g., "Compare X and Y",
        "What are the differences between...").
        
        Returns: List of 2-3 simpler sub-queries
        """
        system = DECOMPOSE_QUERY_PROMPT
        
        result = await self.generate(system, query)
        
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
        
        The embedding of this hypothetical answer is often closer to the 
        embedding of the real answer than the question itself.
        """
        system = HYDE_PROMPT
        
        return await self.generate(system, query)

    async def is_complex_query(self, query: str) -> bool:
        """
        Determine if a query needs decomposition.
        
        Returns True for queries that contain comparisons, multiple concepts,
        or multi-part questions.
        """
        system = IS_COMPLEX_QUERY_PROMPT
        
        result = await self.generate(system, query)
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
